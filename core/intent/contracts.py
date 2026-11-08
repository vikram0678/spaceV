"""
Canonical Structured Intent & Capability Contracts for SpaceV.
Defines typed models for intent resolution, capabilities, parameter schemas,
constraints, verification policies, and execution plans.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class IntentType(str, Enum):
    """Classification category of the user's intent."""
    SIMPLE_ACTION = "simple_action"          # Direct execution of a single capability (volume, app launch, screenshot)
    CONVERSATIONAL = "conversational"        # Greetings, fare-wells, identity, capabilities overview
    CONTEXTUAL = "contextual"                # Action depending on preceding state ("do that again", "open that file")
    COMPOSITE_TASK = "composite_task"        # Multi-step task requiring sequential planning
    CLARIFICATION = "clarification"          # Ambiguous or incomplete request needing user clarification
    NEGATED = "negated"                      # Explicit instruction NOT to perform an action ("don't mute audio")
    UNSUPPORTED = "unsupported"              # Outside SpaceV's capability boundary


class RiskLevel(str, Enum):
    """Risk classification for capabilities and actions."""
    SAFE = "safe"                            # Read-only or completely benign (time, stats, active window)
    LOW = "low"                              # Non-destructive UI/app actions (open app, take screenshot, volume)
    MEDIUM = "medium"                        # State modifications (create file, open folder, web navigation)
    HIGH = "high"                            # Potentially destructive (kill process, empty recycle bin, run shell command, delete)


class VerificationStrategy(str, Enum):
    """Strategy used to verify whether a requested outcome was genuinely achieved."""
    NONE = "none"                            # No observable state change expected (e.g. conversational)
    FILE_EXISTENCE = "file_existence"        # File must exist on disk with minimum size
    PROCESS_RUNNING = "process_running"      # Target process must appear in operating system process table
    WINDOW_FOCUSED = "window_focused"        # Window title or process must match expected foreground state
    AUDIO_STATE = "audio_state"              # System audio mute/volume level changed
    BRIGHTNESS_LEVEL = "brightness_level"    # System brightness level matched
    OUTPUT_SCHEMA = "output_schema"          # Tool output must satisfy structured JSON/CSV schema


@dataclass
class ParameterRequirement:
    """Schema definition for a capability parameter."""
    name: str
    param_type: str                          # "str", "int", "float", "bool", "path", "app_name", "url"
    required: bool = True
    default: Any = None
    description: str = ""


@dataclass
class Capability:
    """Structured representation of an agent capability."""
    name: str                                # Unique identifier: e.g. "os.media_control"
    description: str                         # Natural language semantic description of the capability
    supported_outcomes: list[str]            # What real-world outcomes this capability accomplishes
    tool_name: str                           # Registered function name in tools.registry
    parameters: list[ParameterRequirement] = field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.SAFE
    verification_strategy: VerificationStrategy = VerificationStrategy.NONE
    verification_args: dict[str, Any] = field(default_factory=dict)
    default_response: str = ""               # Poised Jarvis-style response template


@dataclass
class IntentResolution:
    """
    Canonical representation of a resolved natural-language request.
    Produced by UnifiedIntentResolver before any planning or execution begins.
    """
    raw_prompt: str
    intent: str                              # e.g. "os.media_control.mute", "os.launch_app", "general.greeting"
    intent_type: IntentType
    description: str
    capability_name: Optional[str] = None
    tool_name: Optional[str] = None
    parameters: dict[str, Any] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=dict)     # e.g. {"negated": True, "delta_only": True}
    context: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    is_ambiguous: bool = False
    ambiguity_reason: Optional[str] = None
    clarification_question: Optional[str] = None
    requires_planning: bool = False
    requires_confirmation: bool = False
    resolution_source: str = "semantic"     # "deterministic", "semantic_retrieval", "contextual", "planner"
    candidate_intents: list[tuple[str, float]] = field(default_factory=list)
    missing_parameters: list[str] = field(default_factory=list)
    verification_strategy: VerificationStrategy = VerificationStrategy.NONE
    verification_args: dict[str, Any] = field(default_factory=dict)

    @property
    def is_executable(self) -> bool:
        """Determines if the resolution can be dispatched to tool execution immediately."""
        return (
            self.intent_type == IntentType.SIMPLE_ACTION
            and self.tool_name is not None
            and not self.is_ambiguous
            and not self.missing_parameters
            and not self.constraints.get("negated", False)
        )


@dataclass
class OutcomeVerification:
    """Result of evaluating whether the requested real-world outcome occurred."""
    check_type: VerificationStrategy
    passed: bool
    expected: Any
    observed: Any
    evidence: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

