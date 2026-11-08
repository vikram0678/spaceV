"""
Rate Limit Stress & Performance Benchmark Test Suite (Volume V §34.1 #4 & #5).
Validates:
1. 50 rapid requests against rate limiter with zero unhandled 429s.
2. Automatic multi-provider failover cascade.
3. EventBus dispatch latency benchmark (< 1ms).
4. Voice interruption protocol latency benchmark (< 200ms).
5. Browser-Use visual grounding & Crawl4AI web extraction.
6. Scratchpad goal-backward verification.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from core.event_bus import EventPriority, SpaceVEventBus
from core.rate_limiter import OmniRouteRateLimiter
from core.scratchpad import SpaceVScratchpad, StepStatus
from core.token_harness import estimate_tokens
from core.vision_grounding import BrowserGroundingElement, find_interactive_element
from tools.scraper_tools import CrawlResult, scrape_web_page_crawl4ai
from voice.interrupt_handler import InterruptionProtocol


def test_50_rapid_calls_rate_limiter_prevents_429():
    """
    Simulates 50 rapid API calls against a single provider to verify that
    OmniRouteRateLimiter proactively gates requests, preventing 429s and
    signaling provider rotation.
    """
    limiter = OmniRouteRateLimiter()
    # Configure Groq with 30 RPM limit for deterministic testing
    limiter.set_provider_limits("groq", rpm=30, tpm=6000)

    accepted_calls = 0
    throttled_calls = 0

    for i in range(50):
        # Attempt immediate acquisition without waiting
        slot_acquired = limiter.acquire_slot("groq", estimated_tokens=150, max_wait_sec=0.0)
        if slot_acquired:
            accepted_calls += 1
            limiter.record_consumption("groq", 150)
        else:
            throttled_calls += 1

    # Verify that rate limiter accepted up to safe capacity and gated the rest
    assert accepted_calls > 0
    assert throttled_calls > 0
    assert accepted_calls + throttled_calls == 50

    # Verify fallback provider selection engages when primary is throttled
    from core.provider_failover import ProviderFailoverRouter

    router = ProviderFailoverRouter()
    eligible = router.get_eligible_providers("groq")
    assert len(eligible) > 1
    assert "cerebras" in eligible or "gemini" in eligible


def test_performance_benchmarks():
    """
    Benchmarks §34.1 #5 performance criteria:
    - Event dispatch latency: < 1ms
    - Token estimation: bounded
    - Voice interruption latency: < 200ms
    """
    # 1. EventBus dispatch latency benchmark (< 1.0 ms)
    bus = SpaceVEventBus()
    received = []

    def benchmark_handler(ev):
        received.append(ev)

    bus.subscribe("benchmark.event", benchmark_handler, priority=EventPriority.CRITICAL)

    t0 = time.perf_counter()
    iterations = 50
    for i in range(iterations):
        bus.publish("benchmark.event", {"idx": i}, priority=EventPriority.CRITICAL)
    t_dur_ms = (time.perf_counter() - t0) * 1000.0
    avg_latency_ms = t_dur_ms / iterations

    print(f"\n[BENCHMARK] EventBus dispatch average latency: {avg_latency_ms:.3f} ms")
    assert avg_latency_ms < 1.0, f"Event dispatch latency ({avg_latency_ms:.3f} ms) exceeded 1.0 ms threshold!"

    # 2. Token estimation benchmark
    sample_text = "SpaceV autonomous desktop AI agent with cognitive scratchpad and token optimizer."
    tok = estimate_tokens(sample_text)
    assert 5 <= tok <= 30

    # 3. Voice interruption latency benchmark (< 200 ms)
    mock_tts = MagicMock()
    mock_pipeline = MagicMock()
    handler = InterruptionProtocol(pipeline=mock_pipeline, tts=mock_tts)

    t_int_start = time.perf_counter()
    ev = handler.handle_interruption(reason="user_barge_in")
    t_int_dur_ms = (time.perf_counter() - t_int_start) * 1000.0

    print(f"[BENCHMARK] Voice interruption latency: {t_int_dur_ms:.2f} ms")
    assert t_int_dur_ms < 200.0, f"Voice interruption latency ({t_int_dur_ms:.2f} ms) exceeded 200 ms threshold!"
    assert ev.tts_halted is True
    assert ev.reason == "user_barge_in"


def test_scratchpad_goal_backward_verification():
    """Verifies Planning-with-Files goal-backward verification and audit in SpaceVScratchpad."""
    scratchpad = SpaceVScratchpad(goal="Implement user authentication")
    scratchpad.create_plan(["1. Design auth schema", "2. Implement endpoint", "3. Run integration tests"])

    assert len(scratchpad.plan) == 3
    assert scratchpad.plan[0].status == StepStatus.IN_PROGRESS

    # 1. Reject step completion if no empirical evidence provided
    rejected = scratchpad.verify_and_complete_step(step_id=1, evidence="")
    assert rejected is False
    assert scratchpad.plan[0].status == StepStatus.FAILED

    # 2. Accept step completion with empirical evidence
    verified = scratchpad.verify_and_complete_step(
        step_id=1,
        evidence="Schema defined in core/schemas/auth.py with UserModel and TokenModel dataclasses.",
        tool_name="write_file",
    )
    assert verified is True
    assert scratchpad.plan[0].status == StepStatus.COMPLETED
    assert scratchpad.plan[0].verification_evidence is not None

    # Verify Step 2 is now activated
    assert scratchpad.plan[1].status == StepStatus.IN_PROGRESS

    # 3. Complete Step 2 and Step 3 with evidence
    scratchpad.verify_and_complete_step(2, "POST /login and POST /refresh endpoints implemented in auth_routes.py.")
    scratchpad.verify_and_complete_step(3, "Executed pytest tests/test_auth.py: 8/8 passed in 0.42s.")

    # 4. Goal-backward audit passes when all steps have evidence
    passed, gaps = scratchpad.goal_backward_audit()
    assert passed is True
    assert len(gaps) == 0


def test_browser_use_and_crawl4ai_enhancements():
    """Verifies Browser-Use grounding and Crawl4AI web extraction tools."""
    # 1. Browser-Use element model
    elem = BrowserGroundingElement(
        element_id=1,
        label="Submit Button",
        role="button",
        bbox=(100, 200, 180, 240),
        center=(140, 220),
        interactivity_score=0.95,
        is_interactive=True,
    )
    d = elem.to_dict()
    assert d["role"] == "button"
    assert d["is_interactive"] is True

    # 2. Crawl4AI crawl result model
    crawl_res = CrawlResult(
        url="https://example.com",
        title="Example Domain",
        markdown="# Example Domain\n\nThis is a sample page for testing.",
        links=["https://example.com/docs"],
        status_code=200,
        success=True,
    )
    assert crawl_res.status_code == 200
    assert len(crawl_res.links) == 1

    # 3. Test find_interactive_element graceful none
    # `image=None` intentionally inspects the live desktop. Keep this unit test
    # independent from dialogs/windows opened by the developer's environment.
    with patch("core.vision_grounding.capture_screen_pil", return_value=None):
        found = find_interactive_element("Submit Button", image=None)
    assert found is None

    # 4. Test scrape_web_page_crawl4ai
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"<html><head><title>Test Page</title></head><body><p>Hello world</p><a href='https://example.com/link1'>Link</a></body></html>"
        mock_resp.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_resp
        scraped = scrape_web_page_crawl4ai("https://example.com", return_json=True)
        assert "Test Page" in scraped
