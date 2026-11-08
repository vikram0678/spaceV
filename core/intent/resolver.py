"""
Unified Intent Resolution Engine for SpaceV.
The single authoritative pipeline for natural language intent understanding,
semantic capability retrieval, contextual reasoning, negation and constraint analysis,
parameter extraction, confidence calibration, and ambiguity detection.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Optional

from core.intent.capability_registry import capability_registry
from core.intent.contracts import (
    Capability,
    IntentResolution,
    IntentType,
    RiskLevel,
    VerificationStrategy,
)
from core.intent.parameter_extractor import ParameterExtractor
from core.intent.semantic_retriever import semantic_retriever
from core.memory import memory
from core.reflex_gatekeeper import ReflexGatekeeper

logger = logging.getLogger("SpaceV.UnifiedIntentResolver")


class UnifiedIntentResolver:
    """
    Authoritative cognitive intent resolution pipeline.
    Transforms raw natural language utterances into structured, validated IntentResolution contracts.
    """

    CONFIDENCE_HIGH = 0.72
    CONFIDENCE_MODERATE = 0.45
    CONFIDENCE_MINIMUM = 0.32

    # Recognized vague or ambiguous phrases that require clarification
    AMBIGUOUS_PATTERNS = [
        (re.compile(r"^(?:open|launch|start)\s+(?:something|an?\s+app|a\s+program|it|stuff)$", re.I),
         "Which specific application or document would you like me to open for you, Sir?"),
        (re.compile(r"^(?:clean|fix|optimize)\s+(?:everything|my\s+computer|my\s+pc|the\s+system|it|stuff)$", re.I),
         "Would you prefer me to optimize RAM memory, clean the recycle bin, or run system diagnostics, Sir?"),
        (re.compile(r"^(?:close|kill)\s+(?:everything|all|stuff|windows)$", re.I),
         "Would you like me to close all background applications, or do you have a specific program in mind to terminate, Sir?"),
        (re.compile(r"^(?:make\s+it\s+better|fix\s+the\s+problem|help\s+me)$", re.I),
         "Could you specify what workstation task or system issue you would like me to tackle, Sir?"),
        (re.compile(r"^(?:do\s+that\s+again|repeat\s+that|do\s+it\s+again)$", re.I),
         "Which recent task or action would you like me to repeat for you, Sir?"),
    ]

    def __init__(self, retriever=None, registry=None):
        self.retriever = retriever or semantic_retriever
        self.registry = registry or capability_registry

    def resolve(
        self,
        user_prompt: str,
        context: Optional[dict[str, Any]] = None,
    ) -> IntentResolution:
        """
        Processes a user prompt through the unified understanding pipeline.
        Returns a typed IntentResolution contract.
        """
        raw = (user_prompt or "").strip()
        t0 = time.perf_counter()

        # 0. Empty Prompt Guard
        if not raw:
            return IntentResolution(
                raw_prompt="",
                intent="system.noop",
                intent_type=IntentType.UNSUPPORTED,
                description="Empty user prompt received.",
                confidence=0.0,
            )

        # 1. Context Assembly
        assembled_context = self._assemble_context(context)

        # 2. Check for Ambiguous / Incomplete Goal Templates
        for pattern, clar_q in self.AMBIGUOUS_PATTERNS:
            if pattern.search(raw):
                return IntentResolution(
                    raw_prompt=raw,
                    intent="clarification.ambiguous_request",
                    intent_type=IntentType.CLARIFICATION,
                    description="User prompt is conceptually ambiguous and requires clarification.",
                    is_ambiguous=True,
                    ambiguity_reason="Underspecified target in prompt.",
                    clarification_question=clar_q,
                    confidence=0.95,
                    resolution_source="deterministic_ambiguity_guard",
                )

        # 3. Negation & Constraint Analysis
        constraints = ParameterExtractor.extract_constraints(raw)

        # 4. Cognitive Reflex & Composite Task Check
        # If the task involves code generation, deep research, or sequential steps ("and then", "after that"):
        is_cognitive = ReflexGatekeeper.should_bypass_fast_router(raw)
        has_composite_connectors = any(k in raw.lower() for k in [
            " and then ", " then open ", " and write ", " after that ",
            " and compare ", " then execute ", " and execute "
        ])

        if has_composite_connectors or (is_cognitive and any(k in raw.lower() for k in ["write", "create", "implement", "script", "solve"])):
            return IntentResolution(
                raw_prompt=raw,
                intent="planner.composite_task",
                intent_type=IntentType.COMPOSITE_TASK,
                description="Multi-step or generative cognitive task requiring agentic planning and tool chaining.",
                requires_planning=True,
                confidence=0.88,
                constraints=constraints,
                context=assembled_context,
                resolution_source="cognitive_gatekeeper",
            )

        # 5. Semantic Capability Retrieval
        candidates = self.retriever.retrieve(raw, top_k=4)

        # Explicit single-token app launch disambiguation guard (e.g. "open blender_fictional_app")
        app_launch_match = re.match(r"^(?:open|launch|start|run)\s+([a-zA-Z0-9_\-]+)$", raw.strip(), re.I)
        is_url_like = any(k in raw.lower() for k in ["://", "www.", ".com", ".org", ".net", ".io", ".dev", ".ai", "website", "url"])
        if app_launch_match and not is_url_like:
            target_token = app_launch_match.group(1).lower()
            if target_token not in ("something", "anything", "everything", "it", "this"):
                app_cap = self.registry.get("os.launch_app")
                if app_cap:
                    candidates = [(app_cap, 0.95)] + [c for c in candidates if c[0].name != "os.launch_app"]

        # Domain validation: career job harvesting requires career context
        has_career_kw = any(k in raw.lower() for k in [
            "job", "jobs", "career", "careers", "intern", "internship", "internships",
            "hiring", "opening", "openings", "vacancy", "vacancies", "position", "positions", "harvest"
        ])
        candidates = [c for c in candidates if c[0].name != "career.search_jobs" or has_career_kw]

        if not candidates:
            return IntentResolution(
                raw_prompt=raw,
                intent="general.unknown",
                intent_type=IntentType.UNSUPPORTED,
                description="No matching capability found with sufficient semantic confidence.",
                confidence=0.10,
                resolution_source="semantic_retrieval",
            )

        top_cap, top_score = candidates[0]
        margin, is_margin_ambiguous = self.retriever.evaluate_separation(candidates)

        # Build candidate tuple list for inspection
        candidate_summary = [(c.name, s) for c, s in candidates]

        # 6. Ambiguity Gate
        # Compatible domain capability families (e.g. launching an app vs opening an editor)
        # do not trigger false ambiguity prompts
        COMPATIBLE_FAMILIES = [
            {"os.launch_app", "fs.open_editor"},
            {"web.search_google", "web.open_url", "web.gui_search"},
            {"general.presence", "general.identity"},
            {"os.get_system_stats", "os.list_running_apps"},
        ]

        cand1_name = candidates[0][0].name
        cand2_name = candidates[1][0].name if len(candidates) > 1 else ""
        are_compatible = any(cand1_name in fam and cand2_name in fam for fam in COMPATIBLE_FAMILIES)

        if is_margin_ambiguous and not are_compatible:
            clar_q = f"Did you mean to {candidates[0][0].description.lower()} or {candidates[1][0].description.lower() if len(candidates) > 1 else 'something else'}, Sir?"
            return IntentResolution(
                raw_prompt=raw,
                intent="clarification.margin_ambiguity",
                intent_type=IntentType.CLARIFICATION,
                description="Multiple capabilities matched with overlapping confidence scores.",
                is_ambiguous=True,
                ambiguity_reason=f"Close match margin between {cand1_name} and {cand2_name}",
                clarification_question=clar_q,
                confidence=top_score,
                candidate_intents=candidate_summary,
                resolution_source="semantic_retrieval",
            )

        # 7. Parameter Extraction for Target Capability
        extracted_params, missing_params = ParameterExtractor.extract_for_capability(
            top_cap.name,
            raw,
            context=assembled_context,
        )

        # 8. Handling Negated Actions (e.g. "don't mute the audio", "never lock my screen")
        if constraints.get("negated", False):
            # Check if negation applies to this capability action
            neg_verbs = ["mute", "lock", "close", "delete", "purge", "play", "kill", "empty"]
            if any(v in raw.lower() for v in neg_verbs):
                msg = f"Understood, Sir. I will NOT execute {top_cap.name} as requested."
                return IntentResolution(
                    raw_prompt=raw,
                    intent=f"{top_cap.name}.negated",
                    intent_type=IntentType.NEGATED,
                    description=f"User explicitly instructed not to perform {top_cap.name}.",
                    capability_name=top_cap.name,
                    constraints=constraints,
                    confidence=top_score,
                    candidate_intents=candidate_summary,
                    clarification_question=msg,
                    resolution_source="negation_gatekeeper",
                )

        # 9. Missing Required Parameters Check
        if missing_params:
            missing_desc = ", ".join(missing_params)
            clar_q = f"Please specify the required {missing_desc} to proceed with {top_cap.name}, Sir."
            return IntentResolution(
                raw_prompt=raw,
                intent=f"{top_cap.name}.missing_parameters",
                intent_type=IntentType.CLARIFICATION,
                description=f"Missing required parameters: {missing_desc}",
                capability_name=top_cap.name,
                parameters=extracted_params,
                missing_parameters=missing_params,
                is_ambiguous=True,
                clarification_question=clar_q,
                confidence=top_score,
                candidate_intents=candidate_summary,
                resolution_source="parameter_extractor",
            )

        # 10. Classify Final Intent Type
        if top_cap.name.startswith("general."):
            intent_type = IntentType.CONVERSATIONAL
        else:
            intent_type = IntentType.SIMPLE_ACTION

        # Calibrate final confidence:
        # High semantic match + complete parameters = high confidence
        calibrated_confidence = min(0.99, max(0.20, top_score))

        return IntentResolution(
            raw_prompt=raw,
            intent=top_cap.name,
            intent_type=intent_type,
            description=top_cap.description,
            capability_name=top_cap.name,
            tool_name=top_cap.tool_name,
            parameters=extracted_params,
            constraints=constraints,
            context=assembled_context,
            confidence=round(calibrated_confidence, 3),
            is_ambiguous=False,
            requires_planning=False,
            requires_confirmation=(top_cap.risk_level == RiskLevel.HIGH),
            resolution_source="semantic_retrieval",
            candidate_intents=candidate_summary,
            missing_parameters=[],
            verification_strategy=top_cap.verification_strategy,
            verification_args=top_cap.verification_args,
        )

    def _assemble_context(self, override_context: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Assembles contextual evidence from memory and working state."""
        ctx: dict[str, Any] = {}
        if override_context:
            ctx.update(override_context)

        try:
            ctx["user_name"] = memory.get("user_name", "Sir")
            ctx["preferred_browser_profile"] = memory.get("preferred_browser_profile", "Default")
            ctx["last_task"] = memory.get("last_task", "")
        except Exception:
            pass

        return ctx


unified_resolver = UnifiedIntentResolver()

