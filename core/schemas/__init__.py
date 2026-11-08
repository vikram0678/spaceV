"""
SpaceV Schema Package (Volume IV).
Provides type-safe data contracts, event structures, agent protocols, and DAG definitions.
"""
from __future__ import annotations

from core.schemas.dag import (
    DAG_EDGE_TYPES,
    DAG_NODE_TYPES,
    validate_dag_graph,
    validate_node_schema,
)
from core.schemas.events import (
    AgentTaskEvent,
    FileChangeEvent,
    RateLimitEvent,
    ScreenChangeEvent,
    TerminalEvent,
    TokenBudgetEvent,
    VoiceActivityEvent,
    VoiceInputEvent,
    WakeWordEvent,
    WorkflowEvent,
)
from core.schemas.protocols import (
    AGENT_PROTOCOLS,
    AuditResultMessage,
    CodeReadyMessage,
    PlanReadyMessage,
    validate_agent_message,
)

__all__ = [
    "AGENT_PROTOCOLS",
    "AgentTaskEvent",
    "AuditResultMessage",
    "CodeReadyMessage",
    "DAG_EDGE_TYPES",
    "DAG_NODE_TYPES",
    "FileChangeEvent",
    "PlanReadyMessage",
    "RateLimitEvent",
    "ScreenChangeEvent",
    "TerminalEvent",
    "TokenBudgetEvent",
    "VoiceActivityEvent",
    "VoiceInputEvent",
    "WakeWordEvent",
    "WorkflowEvent",
    "validate_agent_message",
    "validate_dag_graph",
    "validate_node_schema",
]
