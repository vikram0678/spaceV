"""
SpaceV Finite State Machine & Task Lifecycle Engine.
Defines formal states, strict transition invariants, step-by-step history tracking,
and bounded retries for autonomous workforce execution.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("SpaceV.TaskStateMachine")

TASK_STATES = {
    "CREATED", "PLANNED", "READY", "RUNNING", "VERIFYING",
    "COMPLETED", "PARTIAL", "BLOCKED", "RETRY_PENDING",
    "FAILED", "TIMED_OUT", "CANCELLED", "RECOVERY_PENDING"
}

ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
    "CREATED": {"PLANNED", "CANCELLED", "FAILED"},
    "PLANNED": {"READY", "BLOCKED", "CANCELLED", "FAILED"},
    "READY": {"RUNNING", "CANCELLED", "FAILED"},
    "RUNNING": {"VERIFYING", "FAILED", "TIMED_OUT", "CANCELLED", "BLOCKED"},
    "VERIFYING": {"COMPLETED", "PARTIAL", "RETRY_PENDING", "RECOVERY_PENDING", "FAILED", "BLOCKED"},
    "RETRY_PENDING": {"READY", "FAILED", "CANCELLED"},
    "RECOVERY_PENDING": {"READY", "FAILED", "CANCELLED"},
    "PARTIAL": {"COMPLETED", "FAILED", "CANCELLED"},
    "BLOCKED": {"READY", "FAILED", "CANCELLED"},
    # Terminal states (cannot transition unless explicitly revived)
    "COMPLETED": set(),
    "FAILED": {"RECOVERY_PENDING"},
    "TIMED_OUT": {"RETRY_PENDING", "FAILED"},
    "CANCELLED": set()
}


@dataclass
class TaskStep:
    step_id: str
    name: str
    status: str = "PENDING"
    attempt: int = 1
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None
    verification_evidence: Dict[str, Any] = field(default_factory=dict)


class TaskStateMachine:
    """
    Manages task lifecycle, ensuring only valid state transitions occur
    and recording all transitions in an immutable audit trail.
    """

    def __init__(self, task_id: str, objective: str, max_retries: int = 2):
        self.task_id = task_id
        self.objective = objective
        self.current_state = "CREATED"
        self.max_retries = max_retries
        self.retry_count = 0
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.finished_at: Optional[str] = None
        self.history: List[Dict[str, Any]] = [
            {"from": None, "to": "CREATED", "timestamp": self.created_at, "reason": "Task initialized"}
        ]
        self.steps: Dict[str, TaskStep] = {}

    def transition_to(self, new_state: str, reason: str = "") -> bool:
        """
        Attempts a transition to new_state.
        Returns True if successful, raises ValueError if transition is invalid.
        """
        if new_state not in TASK_STATES:
            raise ValueError(f"Unknown task state: '{new_state}'. Allowed states: {TASK_STATES}")

        allowed = ALLOWED_TRANSITIONS.get(self.current_state, set())
        if new_state not in allowed:
            err_msg = (
                f"Illegal state transition from '{self.current_state}' to '{new_state}'. "
                f"Allowed transitions: {allowed}"
            )
            logger.error(err_msg)
            raise ValueError(err_msg)

        old_state = self.current_state
        self.current_state = new_state
        ts = datetime.now(timezone.utc).isoformat()
        self.history.append({
            "from": old_state,
            "to": new_state,
            "timestamp": ts,
            "reason": reason
        })

        if new_state in ("COMPLETED", "FAILED", "TIMED_OUT", "CANCELLED"):
            self.finished_at = ts

        logger.info(f"Task {self.task_id} transitioned: {old_state} -> {new_state} ({reason})")
        return True

    def can_retry(self) -> bool:
        """Checks if task is eligible for retry under the bounded retry budget."""
        return self.retry_count < self.max_retries

    def increment_retry(self, reason: str = "") -> bool:
        """Increments retry count and transitions to RETRY_PENDING if within budget."""
        if not self.can_retry():
            self.transition_to("FAILED", f"Retry budget exhausted ({self.max_retries} attempts)")
            return False
        self.retry_count += 1
        self.transition_to("RETRY_PENDING", f"Retry attempt {self.retry_count}: {reason}")
        return True

    def add_step(self, step_id: str, name: str) -> TaskStep:
        step = TaskStep(step_id=step_id, name=name)
        self.steps[step_id] = step
        return step

    def update_step(self, step_id: str, status: str, error: Optional[str] = None, evidence: Optional[Dict[str, Any]] = None):
        if step_id in self.steps:
            s = self.steps[step_id]
            s.status = status
            s.error = error
            if evidence:
                s.verification_evidence.update(evidence)
            if status in ("COMPLETED", "FAILED", "ROLLED_BACK"):
                s.finished_at = datetime.now(timezone.utc).isoformat()

    def is_terminal(self) -> bool:
        return self.current_state in ("COMPLETED", "FAILED", "CANCELLED")
