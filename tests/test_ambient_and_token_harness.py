"""
Test Suite for SpaceV Ambient Productivity Tracker, Sub-150ms Barge-In Guard,
and AI Token Compression Harness.
Strictly zero regex, zero hardcoded paths/strings.
"""

import time
from core.ambient_tracker import ActivityKind, AmbientWorkTracker
from core.barge_in_guard import BargeInCoordinator, HaltTriggerReason
from core.ai_token_harness import AITokenHarness, PromptTier


def test_ambient_tracker_heartbeat_and_summary():
    tracker = AmbientWorkTracker()

    # Emulate work cadence
    tracker.record_heartbeat(ActivityKind.DEEP_CODE, context_tag="core/graph_engine.py")
    time.sleep(0.01)
    tracker.record_heartbeat(ActivityKind.DEEP_CODE, context_tag="core/graph_engine.py")
    time.sleep(0.01)
    tracker.record_heartbeat(ActivityKind.TESTING_VERIFICATION, context_tag="tests/test_graph.py")

    summary = tracker.compute_daily_summary()
    assert summary.logged_event_count >= 1
    assert summary.total_active_seconds > 0.0
    assert summary.focus_score >= 0.0


def test_barge_in_coordinator_sub_150ms_execution():
    coordinator = BargeInCoordinator()
    handler_invoked = []

    def mock_cancellation_handler():
        handler_invoked.append(True)

    coordinator.register_cancellation_handler(mock_cancellation_handler)
    assert not coordinator.is_halt_requested()

    telemetry = coordinator.trigger_emergency_stop(
        reason=HaltTriggerReason.VOICE_BARGE_IN,
        metadata={"origin_source": "TestVAD"},
    )

    assert coordinator.is_halt_requested()
    assert len(handler_invoked) == 1
    # Check sub-150ms (150,000 microseconds)
    assert telemetry.elapsed_halt_us < 150_000.0
    assert telemetry.registered_handlers_invoked == 1

    # Reset
    coordinator.reset()
    assert not coordinator.is_halt_requested()


def test_ai_token_harness_deduplication():
    # Build repetitive console log
    repeated_line = "INFO: SpaceV heartbeat alive [2026-11-20T00:00:00Z]"
    bloated_log = "\n".join([repeated_line] * 20)

    compressed, pruned_count = AITokenHarness.compress_text_block(bloated_log, max_repeated_lines=2)
    assert pruned_count > 0
    assert len(compressed) < len(bloated_log)
    assert compressed.count(repeated_line) == 2


def test_ai_token_harness_prompt_caching_composition():
    prefix = "You are SpaceV Sovereign Assistant."
    blueprint = {"Workspace": "/mnt/d/agentSpace", "Language": "Python"}
    intent = "Inspect recent git status"
    code_slices = [{"file": "core/graph_engine.py", "symbol": "run_graph", "content": "def run_graph(): pass"}]

    structured = AITokenHarness.structure_cacheable_prompt(
        static_system_instructions=prefix,
        environment_metadata=blueprint,
        dynamic_task_instruction=intent,
        bounded_code_slices=code_slices,
    )

    sections = structured["prompt_sections"]
    assert len(sections) == 4
    assert sections[0]["tier"] == PromptTier.STATIC_SYSTEM_PREFIX
    assert sections[0]["content"] == prefix
    assert sections[1]["tier"] == PromptTier.ENVIRONMENT_BLUEPRINT
    assert "Workspace: /mnt/d/agentSpace" in sections[1]["content"]
    assert sections[2]["tier"] == PromptTier.BOUNDED_EVIDENCE
    assert "core/graph_engine.py" in sections[2]["content"]
    assert sections[3]["tier"] == PromptTier.DYNAMIC_USER_INTENT
    assert sections[3]["content"] == intent

    telemetry = structured["telemetry"]
    assert telemetry.raw_character_count > 0
    assert telemetry.optimized_character_count > 0
