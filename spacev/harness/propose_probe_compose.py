"""
SpaceV Harnessing Subsystem: Propose–Probe–Compose Task-Level Self-Healing Engine.
Engineered from Harness² (Google LLC 2026) for ground-truth-free contrastive recovery.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional
from .experience_library import ExperienceLibrary, OperationalLesson


@dataclass
class ProbeCandidate:
    candidate_id: str
    description: str
    action_fn: Callable[[], bool]
    expected_outcome: str


@dataclass
class ProbeExecutionResult:
    candidate_id: str
    success: bool
    latency_ms: float
    error: Optional[str] = None
    trajectory_evidence: str = ""


@dataclass
class ComposedHealingPlan:
    winning_candidate_id: str
    winning_description: str
    lesson: OperationalLesson
    probes_run: int
    resolved: bool


class ProposeProbeComposeEngine:
    """
    Executes contrastive task-level self-healing without ground-truth labels.
    """

    def __init__(self, library: Optional[ExperienceLibrary] = None):
        self.library = library

    def heal_failure(
        self,
        domain: str,
        task_id: str,
        failure_signature: str,
        candidates: List[ProbeCandidate],
    ) -> ComposedHealingPlan:
        probe_results: List[ProbeExecutionResult] = []

        # 1. Probe candidate actions
        winning_candidate: Optional[ProbeCandidate] = None
        winning_result: Optional[ProbeExecutionResult] = None

        for cand in candidates:
            start = time.perf_counter()
            try:
                ok = cand.action_fn()
                lat = (time.perf_counter() - start) * 1000.0
                res = ProbeExecutionResult(
                    candidate_id=cand.candidate_id,
                    success=ok,
                    latency_ms=lat,
                    trajectory_evidence=f"Action '{cand.description}' returned {ok} in {lat:.1f}ms",
                )
                probe_results.append(res)
                if ok and not winning_candidate:
                    winning_candidate = cand
                    winning_result = res
            except Exception as e:
                lat = (time.perf_counter() - start) * 1000.0
                res = ProbeExecutionResult(
                    candidate_id=cand.candidate_id,
                    success=False,
                    latency_ms=lat,
                    error=str(e),
                    trajectory_evidence=f"Action '{cand.description}' raised exception: {str(e)}",
                )
                probe_results.append(res)

        # 2. Compose winning lesson
        if winning_candidate and winning_result:
            lesson = OperationalLesson(
                task_id=task_id,
                cue=failure_signature,
                lesson=f"When encountering '{failure_signature}', use candidate {winning_candidate.candidate_id}: {winning_candidate.description}.",
                evidence=f"Contrastive probe {winning_candidate.candidate_id} succeeded in {winning_result.latency_ms:.1f}ms while alternatives failed.",
                confidence=0.96,
                category=domain,
            )
            if self.library:
                self.library.record_lesson(domain, lesson)

            return ComposedHealingPlan(
                winning_candidate_id=winning_candidate.candidate_id,
                winning_description=winning_candidate.description,
                lesson=lesson,
                probes_run=len(candidates),
                resolved=True,
            )

        # If all probes failed
        fallback_lesson = OperationalLesson(
            task_id=task_id,
            cue=failure_signature,
            lesson="All proposed automated probes failed. Escalate to human supervisor.",
            evidence=f"All {len(candidates)} probes exhausted without resolution.",
            confidence=0.30,
            category=domain,
        )
        return ComposedHealingPlan(
            winning_candidate_id="NONE",
            winning_description="Exhausted all candidates",
            lesson=fallback_lesson,
            probes_run=len(candidates),
            resolved=False,
        )
