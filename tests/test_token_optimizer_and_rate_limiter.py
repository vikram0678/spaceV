"""
Comprehensive Verification and Test Suite for SpaceV 2.0 Token Optimization,
SmartCrusher, CacheAligner, Rate Limiting, and Multi-Provider Failover.
"""
import json
import pytest
import time
from unittest.mock import MagicMock, patch

from core.token_optimizer import SpaceVTokenOptimizer, token_optimizer
from core.rate_limiter import ProviderRateLimiter, rate_limiter
from core.provider_failover import ProviderFailoverRouter, provider_failover
from core.context_hygiene import SpaceVContextHygiene, context_hygiene
from core.model_router import model_router


def test_pytest_log_compression_preserves_failures_and_drops_70_percent():
    """Verify SmartCrusher compresses verbose test logs by >= 70% while keeping exact failure evidence."""
    optimizer = SpaceVTokenOptimizer()

    # Generate a realistic 300-line pytest failure traceback
    passing_lines = [f"tests/unit/test_module_{i}.py::test_case_{i} PASSED [ {i}%]" for i in range(1, 200)]
    failing_block = [
        "=================================== FAILURES ===================================",
        "______________________________ test_critical_auth ______________________________",
        "def test_critical_auth():",
        "    token = generate_session_token('admin')",
        ">       assert token.is_valid is True",
        "E       AssertionError: assert False is True",
        "tests/test_auth.py:42: AssertionError",
        "----------------------------- Captured stderr call -----------------------------",
        "DEBUG: Token expiration timestamp: 1718000000",
        "=========================== short test summary info ============================",
        "FAILED tests/test_auth.py::test_critical_auth - AssertionError: assert False is True",
        "========================= 1 failed, 199 passed in 4.12s =========================="
    ]
    raw_log = "\n".join(passing_lines + failing_block)
    raw_len = len(raw_log)

    compressed = optimizer.compress_tool_result("pytest", raw_log)
    comp_len = len(compressed)

    # 1. Assert significant compression (>= 70% reduction)
    reduction = (raw_len - comp_len) / raw_len * 100
    assert reduction >= 70.0, f"Expected >= 70% reduction, achieved {reduction:.1f}%"

    # 2. Assert zero lost semantic failure evidence
    assert "AssertionError: assert False is True" in compressed
    assert "tests/test_auth.py:42" in compressed
    assert "test_critical_auth" in compressed
    assert "1 failed, 199 passed" in compressed


def test_smartcrusher_json_array_deduplication():
    """Verify SmartCrusher JSON handler truncates repetitive arrays while keeping valid JSON."""
    optimizer = SpaceVTokenOptimizer()

    data = [
        {"id": i, "file_name": f"item_{i}.py", "size": i * 1024, "status": "active"}
        for i in range(25)
    ]
    raw_json = json.dumps(data)

    compressed = optimizer.compress_tool_result("list_directory", raw_json)
    parsed = json.loads(compressed)

    assert isinstance(parsed, list)
    assert len(parsed) == 4  # 3 items + 1 omitted summary dict
    assert parsed[-1]["_spacev_smartcrusher_omitted_count"] == 22
    assert parsed[0]["file_name"] == "item_0.py"


def test_file_content_head_tail_slicing():
    """Verify long file contents have middle lines sliced with SpaceV omission banner."""
    optimizer = SpaceVTokenOptimizer()

    lines = [f"line {i}: var_{i} = compute_value({i})" for i in range(150)]
    raw_code = "\n".join(lines)

    compressed = optimizer.compress_tool_result("read_file", raw_code)

    assert "line 0: var_0" in compressed
    assert "line 149: var_149" in compressed
    assert "omitted by SpaceV AST/File Slicer" in compressed
    assert len(compressed) < len(raw_code) * 0.65


def test_cache_aligner_purges_stale_intermediate_tool_outputs():
    """Verify optimize_messages_for_cache anchors system prompt and tombstones stale intermediate tool outputs."""
    optimizer = SpaceVTokenOptimizer(protect_recent=4)

    messages = [
        {"role": "system", "content": "You are SpaceV."},
        {"role": "user", "content": "Check project files"},
        {"role": "tool", "tool_call_id": "call_1", "content": "File 1 " * 80},  # Stale, should be tombstoned
        {"role": "assistant", "content": "Found 10 files."},
        {"role": "user", "content": "Inspect main.py"},
        {"role": "tool", "tool_call_id": "call_2", "content": "Main.py content " * 80},  # Stale, should be tombstoned
        {"role": "assistant", "content": "Main looks good."},
        {"role": "user", "content": "Now run test"},
        {"role": "tool", "tool_call_id": "call_3", "content": "Test output recent"},  # Recent (within 4)
        {"role": "assistant", "content": "Tests finished."},
    ]

    optimized = optimizer.optimize_messages_for_cache(messages)

    # System prompt remains intact (cache anchor)
    assert optimized[0]["content"] == "You are SpaceV."
    # Stale tool outputs tombstoned
    assert optimized[2]["content"] == "[Prior tool execution output archived to durable STATE.md]"
    assert optimized[5]["content"] == "[Prior tool execution output archived to durable STATE.md]"
    # Recent tool output preserved
    assert optimized[8]["content"] == "Test output recent"


def test_rate_limiter_rpm_and_tpm_throttling():
    """Verify ProviderRateLimiter enforces RPM ceilings and rejects burst over-limit calls."""
    limiter = ProviderRateLimiter(window_sec=60.0)
    limiter.reset_all()

    # Groq has limit of 30 RPM
    for i in range(30):
        allowed = limiter.acquire_slot("groq", estimated_tokens=100)
        assert allowed is True, f"Slot {i+1} should be accepted"

    # 31st request must be rejected under non-blocking check
    rejected = limiter.acquire_slot("groq", estimated_tokens=100, max_wait_sec=0.0)
    assert rejected is False, "Call 31 should be rejected due to 30 RPM limit"

    status = limiter.get_provider_status("groq")
    assert status["rpm_used"] == 30
    assert status["rpm_remaining"] == 0


def test_rate_limiter_circuit_breaker_on_429():
    """Verify record_429 trips circuit breaker and locks provider."""
    limiter = ProviderRateLimiter(window_sec=60.0)
    limiter.reset_all()

    assert limiter.is_available("deepseek") is True
    limiter.record_429("deepseek", retry_after=10.0)

    # Immediately unavailable
    assert limiter.is_available("deepseek") is False
    assert limiter.acquire_slot("deepseek", max_wait_sec=0.0) is False

    status = limiter.get_provider_status("deepseek")
    assert status["is_circuit_breaker_active"] is True
    assert status["circuit_breaker_remaining_sec"] > 0


def test_multi_provider_failover_routing():
    """Verify ProviderFailoverRouter automatically falls back when primary is rate limited or returns 429."""
    limiter = ProviderRateLimiter(window_sec=60.0)
    limiter.reset_all()
    router = ProviderFailoverRouter(cascade=["groq", "cerebras", "deepseek", "ollama"])

    # Simulate groq being locked out
    limiter.record_429("groq", retry_after=30.0)

    # Dispatch mock that returns success on cerebras
    def mock_dispatch(provider: str):
        if provider == "groq":
            raise RuntimeError("Should not be called because groq is rate-limited")
        if provider == "cerebras":
            return {"reply": "Success from Cerebras"}
        return {"reply": "Fallback"}

    # Mock global rate_limiter in failover module
    with patch("core.provider_failover.rate_limiter", limiter):
        result, successful_provider = router.execute_with_failover(
            dispatch_fn=mock_dispatch,
            requested_provider="groq"
        )
        assert successful_provider == "cerebras"
        assert result == {"reply": "Success from Cerebras"}


def test_context_hygiene_durable_state_and_compaction(tmp_path):
    """Verify SpaceVContextHygiene dumps markdown state and compacts multi-turn contexts."""
    hygiene = SpaceVContextHygiene(state_dir=tmp_path)

    state_md = hygiene.dump_durable_state(
        current_phase="Phase 2 - Testing",
        active_goal="Verify token reduction engine",
        completed_tasks=["SmartCrusher", "RateLimiter"],
        remaining_tasks=["Integration Verification"],
        recent_findings=["82% token reduction verified empirically"],
        metadata={"build_status": "green"}
    )

    assert "Phase 2 - Testing" in state_md
    assert "- [x] SmartCrusher" in state_md
    assert "- [ ] Integration Verification" in state_md
    assert hygiene.state_file.exists()

    # Test context compaction
    messages = [
        {"role": "system", "content": "You are SpaceV."},
        {"role": "user", "content": "Step 1"},
        {"role": "assistant", "content": "Done 1"},
        {"role": "user", "content": "Step 2"},
        {"role": "assistant", "content": "Done 2"},
    ]

    compacted = hygiene.compact_for_next_phase(messages, next_phase_name="Phase 3 - Multi-Agent Swarm")
    assert len(compacted) == 3
    assert compacted[0]["role"] == "system"
    assert "DURABLE GSD STATE" in compacted[1]["content"]
    assert "Phase 3 - Multi-Agent Swarm" in compacted[2]["content"]


def test_model_router_fallback_chain_integration():
    """Verify model_router exposes priority fallback chain and selects available provider."""
    chain = model_router.get_cloud_provider_fallback_chain()
    assert "groq" in chain
    assert "cerebras" in chain
    assert "deepseek" in chain
    assert "ollama" in chain

    # Health check returns a valid provider
    healthy = model_router.select_healthy_cloud_provider(preferred="groq")
    assert healthy in chain
