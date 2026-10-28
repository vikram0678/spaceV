"""
SpaceV EventBus & Full-Duplex Interruption Protocol Verification Suite.
Validates:
  - SpaceVEventBus: priority dispatch, wildcard topic resolution ("voice.*", "**"), dead letters, history limits
  - InterruptionProtocol: microsecond buffer purging, LLM cancel triggers, token savings tracking, EventBus integration
"""
from __future__ import annotations

import asyncio
import pytest

from core.event_bus import (
    Event,
    EventPriority,
    SpaceVEventBus,
)
from voice.interrupt_handler import (
    InterruptionProtocol,
)


# ═══════════════════════════════════════════════════════════════════
# EVENT BUS TESTS
# ═══════════════════════════════════════════════════════════════════

def test_event_bus_wildcard_matching():
    """Verify hierarchical topic matching rules."""
    assert SpaceVEventBus._topic_matches("voice.input", "voice.input") is True
    assert SpaceVEventBus._topic_matches("voice.input", "voice.output") is False

    # Segment wildcard
    assert SpaceVEventBus._topic_matches("voice.*", "voice.input") is True
    assert SpaceVEventBus._topic_matches("voice.*", "voice.wake") is True
    assert SpaceVEventBus._topic_matches("voice.*", "screen.change") is False

    # Universal wildcard
    assert SpaceVEventBus._topic_matches("**", "voice.input.raw") is True
    assert SpaceVEventBus._topic_matches("**", "system.heartbeat") is True


def test_event_bus_sync_delivery_and_priority_sorting():
    """Verify synchronous delivery and priority-ordered dispatch."""
    bus = SpaceVEventBus()
    received_order: list[str] = []

    def low_handler(ev: Event):
        received_order.append(f"low:{ev.topic}")

    def critical_handler(ev: Event):
        received_order.append(f"critical:{ev.topic}")

    # Subscribe with priority filters
    bus.subscribe("system.alert", low_handler, priority_filter=EventPriority.LOW)
    bus.subscribe("system.alert", critical_handler, priority_filter=EventPriority.CRITICAL)

    # Publish CRITICAL event
    ev = bus.publish("system.alert", {"msg": "Memory pressure"}, priority=EventPriority.CRITICAL)
    assert ev.priority == EventPriority.CRITICAL

    # Critical handler must run first
    assert received_order == ["critical:system.alert", "low:system.alert"]


def test_event_bus_dead_letter_queue_and_history():
    """Verify unhandled events land in dead letter queue and history is maintained."""
    bus = SpaceVEventBus()

    # Publish to an unsubscribed topic
    bus.publish("unhandled.orphan.topic", payload={"data": 123})

    stats = bus.get_stats()
    assert stats["dead_letters"] == 1
    assert stats["events_published"] == 1

    # Verify history
    history = bus.get_recent_events()
    assert len(history) == 1
    assert history[0].topic == "unhandled.orphan.topic"


@pytest.mark.asyncio
async def test_event_bus_async_dispatch_loop():
    """Verify async event queue processing and coroutine handler execution."""
    bus = SpaceVEventBus()
    received_events: list[Event] = []

    async def async_handler(ev: Event):
        received_events.append(ev)

    bus.subscribe("voice.*", async_handler, subscriber_id="test_worker")

    await bus.start()
    try:
        bus.publish("voice.wake", payload="hey spacev")
        bus.publish("voice.input", payload="what is the time?")

        # Allow async worker to process queue
        await asyncio.sleep(0.1)

        assert len(received_events) == 2
        assert received_events[0].topic == "voice.wake"
        assert received_events[1].topic == "voice.input"
    finally:
        await bus.stop()


# ═══════════════════════════════════════════════════════════════════
# INTERRUPTION PROTOCOL TESTS
# ═══════════════════════════════════════════════════════════════════

def test_interruption_protocol_barge_in_execution():
    """Verify barge-in halts TTS, flushes pipeline, triggers callbacks, and computes token savings."""
    bus = SpaceVEventBus()
    interrupted_events = []
    bus.subscribe("voice.interrupt", lambda ev: interrupted_events.append(ev))

    cancelled = {"llm_aborted": False, "tts_stopped": False}

    class MockTTS:
        def stop_speaking(self):
            cancelled["tts_stopped"] = True

    class MockPipeline:
        def flush_microsecond(self, reason: str = ""):
            return {"duration_us": 42.5, "items_cleared": 3}

    protocol = InterruptionProtocol(bus=bus, pipeline=MockPipeline(), tts=MockTTS())
    protocol.register_llm_cancel_callback(lambda: cancelled.update({"llm_aborted": True}))

    # Partial response that was interrupted (200 characters ~ 50 tokens)
    partial_text = "The quick brown fox jumps over the lazy dog. " * 5
    ev = protocol.handle_interruption(reason="conversational_turn_taking", partial_response=partial_text)

    # 1. State assertions
    assert protocol.is_interrupted is True
    assert ev.reason == "conversational_turn_taking"
    assert ev.tts_halted is True
    assert ev.llm_cancelled is True
    assert ev.discarded_chars == len(partial_text)
    assert ev.discarded_tokens == len(partial_text) // 4
    assert ev.flush_latency_us > 0.0

    # 2. Callback assertions
    assert cancelled["llm_aborted"] is True
    assert cancelled["tts_stopped"] is True

    # 3. EventBus integration
    assert len(interrupted_events) == 1
    assert interrupted_events[0].priority == EventPriority.CRITICAL
    assert interrupted_events[0].payload["reason"] == "conversational_turn_taking"

    # Reset
    protocol.reset()
    assert protocol.is_interrupted is False
