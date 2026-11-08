"""
SpaceV Unified Intent Resolution & Autonomous Execution Subsystem.
"""

from core.intent.contracts import (
    Capability,
    IntentResolution,
    IntentType,
    OutcomeVerification,
    ParameterRequirement,
    RiskLevel,
    VerificationStrategy,
)
from core.intent.capability_registry import capability_registry, CapabilityRegistry
from core.intent.semantic_retriever import semantic_retriever, SemanticCapabilityRetriever
from core.intent.parameter_extractor import ParameterExtractor
from core.intent.resolver import unified_resolver, UnifiedIntentResolver
from core.intent.verifier import outcome_verifier, OutcomeVerifier

__all__ = [
    "Capability",
    "CapabilityRegistry",
    "capability_registry",
    "IntentResolution",
    "IntentType",
    "OutcomeVerification",
    "ParameterExtractor",
    "ParameterRequirement",
    "RiskLevel",
    "SemanticCapabilityRetriever",
    "semantic_retriever",
    "UnifiedIntentResolver",
    "unified_resolver",
    "VerificationStrategy",
    "OutcomeVerifier",
    "outcome_verifier",
]

