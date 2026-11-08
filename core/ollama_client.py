"""
Legacy Compatibility Bridge for SpaceV Agent.
Redirects OllamaAgent to HybridBrainAgent in core.brain_orchestrator.
SpaceV is a Universal Hybrid Agent supporting both Free Offline Models and Cloud APIs.
"""
from core.brain_orchestrator import (
    SYSTEM_PROMPT,
    HybridBrainAgent,
    HybridBrainAgent as OllamaAgent,
    SpaceVAgent,
    parse_fallback_tool_calls,
)

__all__ = [
    "SYSTEM_PROMPT",
    "HybridBrainAgent",
    "OllamaAgent",
    "SpaceVAgent",
    "parse_fallback_tool_calls",
]
