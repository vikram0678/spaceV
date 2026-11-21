"""
SpaceV Ambient Productivity & Work Tracking Subsystem ("SpaceV Eye").
Provides non-intrusive focus session tracking, developer activity metering,
and episodic productivity rollups.
Strictly abolishes regex parsing, hardcoded project paths, and fixed heuristics.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class ActivityKind(str, Enum):
    """Semantic classifications for detected developer activities."""
    DEEP_CODE = "deep_code"
    TESTING_VERIFICATION = "testing_verification"
    RESEARCH_DOCUMENTATION = "research_documentation"
    SYSTEM_DIAGNOSTICS = "system_diagnostics"
    IDLE = "idle"


@dataclass
class ActivityRecord:
    """Discrete, privacy-preserving event capturing developer work state."""
    timestamp: float
    activity_kind: ActivityKind
    context_tag: str
    duration_seconds: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DailyProductivitySummary:
    """Consolidated daily productivity metric rollup."""
    total_active_seconds: float
    deep_work_seconds: float
    testing_seconds: float
    research_seconds: float
    focus_score: float  # Ratio of deep work + testing to total time (0.0 to 1.0)
    top_context_tags: List[Tuple[str, float]]
    logged_event_count: int


class AmbientWorkTracker:
    """
    Tracks developer productivity, logs work sessions, and maintains
    a lightweight episodic work ledger without invasive keystroke recording.
    """

    def __init__(self, ledger_dir: Optional[Path] = None):
        self.ledger_dir = ledger_dir
        self.sessions: List[ActivityRecord] = []
        self._current_activity: Optional[ActivityRecord] = None
        self._last_heartbeat: float = time.monotonic()

    def record_heartbeat(
        self,
        kind: ActivityKind,
        context_tag: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Records ongoing active work cadence. Accumulates time automatically.
        """
        now = time.monotonic()
        delta = now - self._last_heartbeat
        self._last_heartbeat = now

        # Cap delta to prevent unbounded accumulation after system suspend (e.g., > 300s)
        bounded_delta = min(max(delta, 0.0), 300.0)

        if self._current_activity and self._current_activity.activity_kind == kind and self._current_activity.context_tag == context_tag:
            self._current_activity.duration_seconds += bounded_delta
        else:
            if self._current_activity and self._current_activity.duration_seconds > 0.0:
                self.sessions.append(self._current_activity)

            self._current_activity = ActivityRecord(
                timestamp=time.time(),
                activity_kind=kind,
                context_tag=context_tag,
                duration_seconds=bounded_delta,
                metadata=metadata or {},
            )

    def flush_current_session(self) -> None:
        """Flushes in-flight activity record to completed sessions list."""
        if self._current_activity and self._current_activity.duration_seconds > 0.0:
            self.sessions.append(self._current_activity)
            self._current_activity = None

    def compute_daily_summary(self) -> DailyProductivitySummary:
        """
        Derives mathematical focus metrics, time totals, and dominant work contexts.
        Zero regex, pure temporal aggregation.
        """
        self.flush_current_session()

        total_active = 0.0
        deep_work = 0.0
        testing_time = 0.0
        research_time = 0.0
        context_durations: Dict[str, float] = defaultdict(float)

        for record in self.sessions:
            dur = record.duration_seconds
            total_active += dur
            context_durations[record.context_tag] += dur

            if record.activity_kind == ActivityKind.DEEP_CODE:
                deep_work += dur
            elif record.activity_kind == ActivityKind.TESTING_VERIFICATION:
                testing_time += dur
            elif record.activity_kind == ActivityKind.RESEARCH_DOCUMENTATION:
                research_time += dur

        productive_time = deep_work + testing_time
        focus_score = round(productive_time / total_active, 4) if total_active > 0.0 else 0.0

        sorted_contexts = sorted(
            context_durations.items(),
            key=lambda item: item[1],
            reverse=True,
        )

        return DailyProductivitySummary(
            total_active_seconds=round(total_active, 2),
            deep_work_seconds=round(deep_work, 2),
            testing_seconds=round(testing_time, 2),
            research_seconds=round(research_time, 2),
            focus_score=focus_score,
            top_context_tags=sorted_contexts[:5],
            logged_event_count=len(self.sessions),
        )

    def clear(self) -> None:
        self.sessions.clear()
        self._current_activity = None
        self._last_heartbeat = time.monotonic()


# Tracker singleton
ambient_tracker = AmbientWorkTracker()
