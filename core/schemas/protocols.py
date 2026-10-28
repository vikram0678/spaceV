"""
SpaceV Agent Message Protocols (Volume IV §28).
Defines inter-agent communication protocols over the EventBus:
  - Planner → Coder: "agent.plan_ready"
  - Coder → Auditor: "agent.code_ready"
  - Auditor → Planner: "agent.audit_result"
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

AGENT_PROTOCOLS: dict[str, dict[str, Any]] = {
    "planner_to_coder": {
        "topic": "agent.plan_ready",
        "payload": {
            "workflow_id": "str",
            "node_instructions": "list[str]",
            "context_ref": "str",
        },
        "max_tokens": 400,
    },
    "coder_to_auditor": {
        "topic": "agent.code_ready",
        "payload": {
            "files_changed": "list[str]",
            "diff_ref": "str",
            "test_command": "str",
        },
        "max_tokens": 300,
    },
    "auditor_result": {
        "topic": "agent.audit_result",
        "payload": {
            "verdict": "PASS | FAIL",
            "evidence": "str",
            "issues": "list[str]",
        },
        "max_tokens": 200,
    },
}


@dataclass
class PlanReadyMessage:
    """Message sent from Planner to Coder with a constructed DAG workflow."""
    workflow_id: str
    node_instructions: list[str] = field(default_factory=list)
    context_ref: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlanReadyMessage:
        return cls(**data)


@dataclass
class CodeReadyMessage:
    """Message sent from Coder to Auditor after modifying code or running tools."""
    files_changed: list[str] = field(default_factory=list)
    diff_ref: str = ""
    test_command: str = "pytest"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CodeReadyMessage:
        return cls(**data)


@dataclass
class AuditResultMessage:
    """Message sent by Auditor summarizing verification verdict and evidence."""
    verdict: str               # "PASS" | "FAIL"
    evidence: str              # Specific test output or diff snippet
    issues: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.verdict.upper() == "PASS"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["passed"] = self.passed
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuditResultMessage:
        clean = {k: v for k, v in data.items() if k != "passed"}
        return cls(**clean)


def validate_agent_message(protocol_name: str, payload: dict[str, Any]) -> tuple[bool, str]:
    """
    Validates that a message dictionary conforms to the specified agent protocol schema.
    Returns (is_valid, error_message).
    """
    proto = AGENT_PROTOCOLS.get(protocol_name)
    if not proto:
        return False, f"Unknown protocol: {protocol_name}"

    expected_fields = proto["payload"]
    for field_name in expected_fields:
        if field_name not in payload:
            return False, f"Missing required field '{field_name}' for protocol '{protocol_name}'"

    # Specific contract checks
    if protocol_name == "auditor_result":
        verdict = str(payload.get("verdict", "")).upper()
        if verdict not in ("PASS", "FAIL"):
            return False, "Verdict must be 'PASS' or 'FAIL'"

    # Token budget check (heuristic: 1 token ~= 4 chars)
    payload_str = str(payload)
    est_tokens = max(1, len(payload_str) // 4)
    max_tokens = proto.get("max_tokens", 500)
    if est_tokens > max_tokens:
        return False, f"Payload token count (~{est_tokens}) exceeds maximum allowed ({max_tokens}) for '{protocol_name}'"

    return True, ""
