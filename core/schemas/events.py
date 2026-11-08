"""
SpaceV Core Event Schemas (Volume IV §27).
Type-safe, validated event schemas for the SpaceV EventBus.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class VoiceInputEvent:
    """User speech transcribed to text."""
    text: str
    confidence: float = 0.0
    language: str = "en"
    duration_ms: int = 0
    is_wake_word_triggered: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VoiceInputEvent:
        return cls(**data)


@dataclass
class VoiceActivityEvent:
    """VAD speech onset or offset."""
    is_speaking: bool
    vad_probability: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VoiceActivityEvent:
        return cls(**data)


@dataclass
class WakeWordEvent:
    """Wake word detected."""
    keyword: str = "hey spacev"
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WakeWordEvent:
        return cls(**data)


@dataclass
class ScreenChangeEvent:
    """Significant screen content or active window change."""
    change_type: str           # "app_switch" | "content_change" | "error_dialog"
    similarity_score: float
    active_window_title: str
    timestamp: float = field(default_factory=time.time)
    screenshot_path: str | None = None

    @property
    def is_significant(self) -> bool:
        return self.similarity_score < 0.85

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["is_significant"] = self.is_significant
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScreenChangeEvent:
        clean = {k: v for k, v in data.items() if k != "is_significant"}
        return cls(**clean)


@dataclass
class FileChangeEvent:
    """File system mutation detected by ambient perception."""
    event_type: str            # "created" | "modified" | "deleted" | "moved"
    file_path: str
    relative_path: str
    extension: str
    size_bytes: int
    timestamp: float = field(default_factory=time.time)
    is_directory: bool = False
    is_code_file: bool = False
    is_config_file: bool = False
    is_test_file: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FileChangeEvent:
        return cls(**data)


@dataclass
class TerminalEvent:
    """Terminal output pattern detected."""
    event_type: str            # "python_traceback" | "test_failure" | "test_passed" | "build_failure"
    terminal_id: str
    matched_pattern: str
    matched_text: str
    context_lines: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    severity: str = "info"     # "info" | "warning" | "error" | "critical"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TerminalEvent:
        return cls(**data)


@dataclass
class AgentTaskEvent:
    """Agent task lifecycle event."""
    task_id: str
    agent_role: str
    event_type: str            # "started" | "completed" | "failed"
    instruction: str = ""
    result: Any = None
    tokens_used: int = 0
    duration_sec: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentTaskEvent:
        return cls(**data)


@dataclass
class WorkflowEvent:
    """Workflow lifecycle event."""
    workflow_id: str
    event_type: str            # "started" | "node_done" | "completed" | "failed" | "approval_needed"
    workflow_name: str = ""
    node_id: str = ""
    node_name: str = ""
    total_tokens: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowEvent:
        return cls(**data)


@dataclass
class TokenBudgetEvent:
    """Token budget warning or ceiling event."""
    event_type: str            # "warning" | "critical" | "exhausted"
    used_tokens: int
    max_tokens: int
    utilization_percent: float
    provider: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TokenBudgetEvent:
        return cls(**data)


@dataclass
class RateLimitEvent:
    """Rate limit event (429 or proactive rate limit avoidance)."""
    event_type: str            # "prevented" | "hit_429" | "provider_switched"
    provider: str
    estimated_tokens: int
    available_tokens: int
    fallback_provider: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RateLimitEvent:
        return cls(**data)
