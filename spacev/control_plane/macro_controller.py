"""
SpaceV Control Plane: Multi-Action Macro Controller.
Engineered from Browser-Use Controller for atomic, single-turn multi-step UI execution.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class MacroAction:
    action_type: str  # 'click', 'type', 'key', 'wait', 'scroll'
    target: str | None = None
    value: str | None = None
    key: str | None = None
    duration_ms: int = 50


@dataclass
class StepResult:
    step_index: int
    action_type: str
    success: bool
    latency_ms: float
    error: str | None = None


@dataclass
class MacroExecutionResult:
    total_steps: int
    successful_steps: int
    failed_steps: int
    total_duration_ms: float
    step_results: list[StepResult] = field(default_factory=list)

    @property
    def all_success(self) -> bool:
        return self.failed_steps == 0 and self.successful_steps == self.total_steps


class MacroController:
    """
    Executes multiple UI operations in a single atomic inference turn,
    eliminating multi-roundtrip LLM latency.
    """

    def __init__(self, action_executor: Callable[[MacroAction], bool] | None = None):
        self.action_executor = action_executor or self._default_executor

    def _default_executor(self, action: MacroAction) -> bool:
        # Simulated execution hook (can be bound to native Win32/X11 or CDP handler)
        time.sleep(action.duration_ms / 1000.0)
        return True

    def execute_batch(self, actions: list[MacroAction]) -> MacroExecutionResult:
        start_time = time.perf_counter()
        step_results: list[StepResult] = []
        successful = 0
        failed = 0

        for i, action in enumerate(actions):
            step_start = time.perf_counter()
            try:
                ok = self.action_executor(action)
                step_lat = (time.perf_counter() - step_start) * 1000.0
                if ok:
                    successful += 1
                    step_results.append(StepResult(i, action.action_type, True, step_lat))
                else:
                    failed += 1
                    step_results.append(StepResult(i, action.action_type, False, step_lat, "Action returned False"))
                    break  # Stop execution on failure
            except Exception as e:
                step_lat = (time.perf_counter() - step_start) * 1000.0
                failed += 1
                step_results.append(StepResult(i, action.action_type, False, step_lat, str(e)))
                break

        total_duration = (time.perf_counter() - start_time) * 1000.0
        return MacroExecutionResult(
            total_steps=len(actions),
            successful_steps=successful,
            failed_steps=failed,
            total_duration_ms=total_duration,
            step_results=step_results,
        )
