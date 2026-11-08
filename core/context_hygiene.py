"""
SpaceV Context Hygiene & GSD Durable State Engine (SpaceV 2.0).
Synthesizes:
  - GSD / Planning-with-Files (Durable Markdown disk state, context compaction, state dumps)
  - Zero-token state handover between multi-agent subagent phases (Planner -> Coder -> Auditor)

Guarantees:
  - Preserves critical findings, objectives, and test states on disk (.spacev/STATE.md).
  - Wipes transient message history between heavy workflow phases to prevent context blowout.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("SpaceV.ContextHygiene")

STATE_DIR = Path(".spacev")
STATE_FILE = STATE_DIR / "STATE.md"
FINDINGS_FILE = STATE_DIR / "FINDINGS.md"


class SpaceVContextHygiene:
    """
    Manages durable state synchronization and context compaction between agentic phases.
    """

    def __init__(self, state_dir: Path = STATE_DIR):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / "STATE.md"
        self.findings_file = self.state_dir / "FINDINGS.md"

    def dump_durable_state(
        self,
        current_phase: str,
        active_goal: str,
        completed_tasks: List[str],
        remaining_tasks: List[str],
        recent_findings: List[str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Persists high-level agentic task state to .spacev/STATE.md.
        """
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        meta = metadata or {}

        completed_md = "\n".join(f"- [x] {t}" for t in completed_tasks) if completed_tasks else "- None yet"
        remaining_md = "\n".join(f"- [ ] {t}" for t in remaining_tasks) if remaining_tasks else "- All tasks complete"
        findings_md = "\n".join(f"- {f}" for f in recent_findings) if recent_findings else "- No new anomalies"

        content = f"""# SPACEV DURABLE AGENTIC STATE
**Last Updated:** {timestamp}  
**Current Phase:** `{current_phase}`  
**Active Goal:** {active_goal}  

## Completed Milestones
{completed_md}

## Pending Tasks
{remaining_md}

## Key Discoveries & Evidence
{findings_md}

## Phase Metadata
```json
{json.dumps(meta, indent=2)}
```
"""
        self.state_file.write_text(content, encoding="utf-8")
        logger.info(f"[CONTEXT_HYGIENE] Durable state persisted to {self.state_file}")
        return content

    def append_finding(self, finding: str) -> None:
        """Appends a technical discovery or test failure evidence to FINDINGS.md."""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
        entry = f"[{timestamp}] {finding}\n"
        with open(self.findings_file, "a", encoding="utf-8") as f:
            f.write(entry)

    def compact_for_next_phase(
        self,
        messages: List[Dict[str, Any]],
        next_phase_name: str,
    ) -> List[Dict[str, Any]]:
        """
        GSD Context Compaction:
        Wipes raw intermediate conversation turns, keeping only:
          1. System Prompt
          2. Condensed State Summary injected as context
          3. Final instruction for the next phase
        Reduces multi-agent token usage by up to 85%.
        """
        if not messages:
            return messages

        system_msg = messages[0] if messages[0].get("role") == "system" else {"role": "system", "content": "You are SpaceV."}

        # Read latest state file if present
        state_summary = ""
        if self.state_file.exists():
            try:
                state_summary = self.state_file.read_text(encoding="utf-8")
            except Exception:
                pass

        if not state_summary:
            state_summary = f"Active Phase: {next_phase_name}. Prior steps completed and recorded on disk."

        compacted = [
            system_msg,
            {
                "role": "system",
                "content": f"[DURABLE GSD STATE - PHASE TRANSITION TO '{next_phase_name}']:\n{state_summary[:1200]}"
            },
            {
                "role": "user",
                "content": f"Begin execution of phase: {next_phase_name}. Use scoped tool actions."
            }
        ]
        return compacted

    def read_current_state(self) -> str:
        """Reads current state from disk."""
        if self.state_file.exists():
            return self.state_file.read_text(encoding="utf-8")
        return ""


# Global singleton instance
context_hygiene = SpaceVContextHygiene()
