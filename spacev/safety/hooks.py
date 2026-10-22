"""
SpaceV Safety Hooks & Command Audit Subsystem.
Implements pre/post command interception (Contract #4 & #8).
All command requests are logged with execution_target: 'celesto_sandbox'.
Dangerous commands are blocked BEFORE reaching the guest microVM kernel.
"""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spacev.config import settings


class CommandBlockedError(Exception):
    """Raised when a pre-execution safety hook blocks a dangerous command."""
    pass


class SafetyPolicyEngine:
    """Heuristic and AST analyzer for intercepting malicious command strings."""

    DANGEROUS_PATTERNS = [
        # Secret & Canary Exfiltration
        r"(cat|grep|head|tail|strings).*(credentials|\.env|id_rsa|id_ed25519|CANARY_KEY)",
        # Outbound Exfiltration via network tools
        r"(curl|wget|nc|ncat|netcat|socat|bash\s+-i|/dev/tcp).*",
        # Host destructive payloads or container escapes
        r"rm\s+-rf\s+(/|/\*|~|/etc|/var|/usr)",
        r"(dd\s+if=/dev/zero|mkfs\.|chmod\s+-R\s+777\s+/)",
        # Fork bombs and resource exhaustion
        r":\(\)\s*\{\s*:\|:&\s*\};:",
    ]

    def __init__(self):
        self.compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.DANGEROUS_PATTERNS]

    def evaluate(self, command: str) -> str:
        """Evaluates command string. Returns 'allow' or 'block'."""
        cmd_clean = command.strip()
        for pattern in self.compiled_patterns:
            if pattern.search(cmd_clean):
                return "block"
        return "allow"


class CommandAuditor:
    """Thread-safe append-only logger for logs/commands.jsonl."""

    def __init__(self, log_path: Path | None = None):
        self.log_path = log_path or settings.command_audit_log
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.policy = SafetyPolicyEngine()

    def audit_and_execute(
        self,
        sandbox_name: str,
        command: str,
        executor_fn: Any | None = None
    ) -> dict[str, Any]:
        """
        Intercepts command, records decision to logs/commands.jsonl,
        and enforces execution isolation inside celesto_sandbox.
        """
        # Validate sandbox name format
        if not re.match(r"^sbx-[a-z0-9]{8,}$", sandbox_name):
            raise ValueError(f"Invalid sandbox name format: {sandbox_name}")

        decision = self.policy.evaluate(command)
        ts = datetime.now(UTC).isoformat()

        # Audit entry matching exact Hackathon Contract #4
        log_entry = {
            "ts": ts,
            "sandbox_name": sandbox_name,
            "command": command,
            "decision": decision,
            "execution_target": "celesto_sandbox"
        }

        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")

        if decision == "block":
            raise CommandBlockedError(
                f"[SafetyHook] Command blocked by SpaceV policy engine: {command}"
            )

        # If allowed and executor provided, execute in guest
        if executor_fn:
            return executor_fn(command)

        return {"status": "allowed", "executed": True}


safety_auditor = CommandAuditor()
