"""
SpaceV Token Accounting Ledger Engine (Volume IV §30).
Maintains an immutable, append-only JSON Lines ledger in .spacev/token_ledger.jsonl
with daily automatic rotation and detailed token economy metrics:
  - Input, output, and total tokens per LLM turn
  - Compression efficiency (pre-harness vs post-harness)
  - Rate-limiting bucket state (before and after calls)
  - Attribution by agent role (Planner, Coder, Auditor, Direct) and provider (Groq, Cerebras, Gemini, etc.)
"""
from __future__ import annotations

import datetime
import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("SpaceV.TokenLedger")


@dataclass
class TokenLedgerEntry:
    """A single atomic record in the SpaceV token accounting ledger."""
    timestamp: float
    turn_number: int

    # Request routing
    provider: str              # "groq" | "gemini" | "cerebras" | "sambanova" | "mistral" | "ollama"
    model: str                 # Exact model string
    agent: str                 # "planner" | "coder" | "auditor" | "direct"

    # Token counts
    input_tokens: int
    output_tokens: int
    total_tokens: int

    # Compression metrics
    pre_optimization_tokens: int
    post_optimization_tokens: int
    reduction_percent: float

    # Rate limiting telemetry
    provider_bucket_before: int
    provider_bucket_after: int

    # Workflow context
    workflow_id: str = ""
    node_id: str = ""

    # Reliability & failover tracking
    was_rate_limited: bool = False
    failover_count: int = 0
    final_provider: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TokenLedgerEntry:
        return cls(**data)


class TokenLedger:
    """
    Append-only persistent ledger for LLM token transactions.
    Stores records in .spacev/token_ledger.jsonl with daily date partitioning.
    """

    def __init__(self, ledger_dir: Path | str = ".spacev"):
        self.ledger_dir = Path(ledger_dir)
        self.ledger_dir.mkdir(parents=True, exist_ok=True)
        self._turn_counter: int = 0
        self._in_memory_recent: list[TokenLedgerEntry] = []

    def get_ledger_path(self, date_str: str | None = None) -> Path:
        """Computes daily rotated ledger path."""
        ds = date_str or datetime.date.today().strftime("%Y-%m-%d")
        return self.ledger_dir / f"token_ledger_{ds}.jsonl"

    @property
    def primary_ledger_path(self) -> Path:
        """Main symlink/reference ledger path."""
        return self.ledger_dir / "token_ledger.jsonl"

    def record_entry(self, entry: TokenLedgerEntry) -> TokenLedgerEntry:
        """
        Appends an entry to both the primary ledger and today's rotated ledger file.
        """
        self._turn_counter = max(self._turn_counter, entry.turn_number)
        self._in_memory_recent.append(entry)
        if len(self._in_memory_recent) > 100:
            self._in_memory_recent.pop(0)

        line = json.dumps(entry.to_dict()) + "\n"

        # Append to primary ledger
        try:
            with open(self.primary_ledger_path, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError as e:
            logger.error(f"[TOKEN_LEDGER] Error writing to primary ledger: {e}")

        # Append to daily rotated ledger
        daily_path = self.get_ledger_path()
        try:
            with open(daily_path, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError as e:
            logger.error(f"[TOKEN_LEDGER] Error writing to daily ledger: {e}")

        logger.debug(
            f"[TOKEN_LEDGER] Recorded turn {entry.turn_number} for {entry.provider} "
            f"({entry.total_tokens} tokens, {entry.reduction_percent:.1f}% reduction)"
        )
        return entry

    def record_turn(
        self,
        provider: str,
        model: str,
        agent: str,
        input_tokens: int,
        output_tokens: int,
        pre_tokens: int = 0,
        post_tokens: int = 0,
        bucket_before: int = 0,
        bucket_after: int = 0,
        workflow_id: str = "",
        node_id: str = "",
        was_rate_limited: bool = False,
        failover_count: int = 0,
        final_provider: str = "",
    ) -> TokenLedgerEntry:
        """Convenience method to construct and record a ledger entry."""
        self._turn_counter += 1
        pre_tokens = pre_tokens or input_tokens
        post_tokens = post_tokens or input_tokens

        reduction = 0.0
        if pre_tokens > 0:
            reduction = max(0.0, ((pre_tokens - post_tokens) / pre_tokens) * 100.0)

        entry = TokenLedgerEntry(
            timestamp=time.time(),
            turn_number=self._turn_counter,
            provider=provider,
            model=model,
            agent=agent,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            pre_optimization_tokens=pre_tokens,
            post_optimization_tokens=post_tokens,
            reduction_percent=round(reduction, 2),
            provider_bucket_before=bucket_before,
            provider_bucket_after=bucket_after,
            workflow_id=workflow_id,
            node_id=node_id,
            was_rate_limited=was_rate_limited,
            failover_count=failover_count,
            final_provider=final_provider or provider,
        )
        return self.record_entry(entry)

    def get_entries(self, limit: int = 50, date_str: str | None = None) -> list[TokenLedgerEntry]:
        """Reads recent ledger entries from disk."""
        target = self.get_ledger_path(date_str) if date_str else self.primary_ledger_path
        if not target.exists():
            return list(self._in_memory_recent[-limit:])

        entries: list[TokenLedgerEntry] = []
        try:
            with open(target, encoding="utf-8") as f:
                for line in f:
                    line_clean = line.strip()
                    if line_clean:
                        try:
                            entries.append(TokenLedgerEntry.from_dict(json.loads(line_clean)))
                        except Exception:
                            continue
        except OSError as e:
            logger.error(f"[TOKEN_LEDGER] Error reading ledger: {e}")

        return entries[-limit:]

    def get_summary(self, date_str: str | None = None) -> dict[str, Any]:
        """Calculates cumulative aggregate statistics from the ledger."""
        entries = self.get_entries(limit=10000, date_str=date_str)
        if not entries:
            return {
                "total_turns": 0,
                "total_tokens_consumed": 0,
                "total_tokens_saved": 0,
                "avg_reduction_percent": 0.0,
                "tokens_by_provider": {},
                "tokens_by_agent": {},
            }

        total_consumed = sum(e.total_tokens for e in entries)
        total_pre = sum(e.pre_optimization_tokens for e in entries)
        total_post = sum(e.post_optimization_tokens for e in entries)
        tokens_saved = max(0, total_pre - total_post)

        avg_reduction = round((tokens_saved / max(1, total_pre)) * 100.0, 2) if total_pre > 0 else 0.0

        by_provider: dict[str, int] = {}
        by_agent: dict[str, int] = {}

        for e in entries:
            by_provider[e.provider] = by_provider.get(e.provider, 0) + e.total_tokens
            by_agent[e.agent] = by_agent.get(e.agent, 0) + e.total_tokens

        return {
            "total_turns": len(entries),
            "total_tokens_consumed": total_consumed,
            "total_tokens_saved": tokens_saved,
            "avg_reduction_percent": avg_reduction,
            "tokens_by_provider": by_provider,
            "tokens_by_agent": by_agent,
        }

    def clear(self):
        """Clears in-memory ledger state (files on disk preserved unless deleted separately)."""
        self._turn_counter = 0
        self._in_memory_recent.clear()


# Global default instance
token_ledger = TokenLedger()
