"""
Pydantic Schemas for SpaceV Run Ledger API (Contract #11).
Strictly validates sandbox naming regex, allowed states, and execution_target: 'celesto_sandbox'.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, field_validator

ALLOWED_STATES = {"created", "ready", "running", "succeeded", "failed", "deleted"}


class RunCreateRequest(BaseModel):
    run_id: str
    sandbox_name: str
    problem_id: str
    state: str
    execution_target: str

    @field_validator("sandbox_name")
    def validate_sandbox_name(cls, v: str) -> str:
        if not re.match(r"^sbx-[a-z0-9]{8,}$", v):
            raise ValueError(
                "sandbox_name must match '^sbx-[a-z0-9]{8,}$' (sbx- followed by 8+ lowercase alphanumeric chars)"
            )
        return v

    @field_validator("state")
    def validate_state(cls, v: str) -> str:
        if v not in ALLOWED_STATES:
            raise ValueError(f"state must be one of {ALLOWED_STATES}, got '{v}'")
        return v

    @field_validator("execution_target")
    def validate_execution_target(cls, v: str) -> str:
        if v != "celesto_sandbox":
            raise ValueError(
                f"execution_target must be exactly 'celesto_sandbox', got '{v}'"
            )
        return v


class RunResponse(BaseModel):
    id: int
    run_id: str
    sandbox_name: str
    problem_id: str
    state: str
    execution_target: str
    created_at: Optional[str] = None
