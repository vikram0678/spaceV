"""
Token Budget Regression Test Suite (Volume V §34.1 #3).
Validates:
1. Standardized 20-turn multi-step developer conversation.
2. Total tokens consumed across 20 turns < 15,000 tokens (vs ~42,000 baseline).
3. No individual turn exceeds 3,000 tokens.
4. SmartCrusher, CacheAligner, and ToolCleanup deliver ≥ 60% compression efficiency.
5. VRAM governor safety verification.
"""
from __future__ import annotations

import tempfile

from core.token_harness import SpaceVTokenHarness, estimate_messages_tokens
from core.token_ledger import TokenLedger
from core.vram_manager import GPUMemoryManager


def test_standardized_20_turn_token_regression():
    """
    Simulates a 20-turn developer session with tool outputs, file logs, and iterative debugging.
    Verifies that SpaceVTokenHarness maintains total tokens under 15,000 (baseline: 42,000+).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger = TokenLedger(ledger_dir=tmpdir)
        harness = SpaceVTokenHarness()

        system_prompt = (
            "You are SpaceV, an ultra-fast agentic AI coding companion with high-fidelity "
            "desktop control, proactive perception, and strict token efficiency."
        )

        conversation_history: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt}
        ]

        # Standard tool schema (40 tools simulated)
        dummy_tools = [
            {"type": "function", "function": {"name": f"tool_{i}", "description": f"Executes task {i}", "parameters": {"type": "object", "properties": {"arg": {"type": "string"}}}}}
            for i in range(25)
        ]

        # 20 diverse representative turns
        prompts = [
            "Hello SpaceV, let's start working on the project.",
            "Read the configuration file config.py and summarize settings.",
            "Run python -m pytest tests/ to see the current failure state.",
            "Here is the traceback log from pytest:\n" + ("Traceback (most recent call last):\n  File 'test_core.py', line 45\n    assert x == 42\nAssertionError\n" * 15),
            "Inspect the database schema in core/models.py.",
            "Refactor the authenticate_user method to support JWT tokens.",
            "Here is the AST file content of core/models.py:\n" + ("class UserModel:\n    id: int\n    username: str\n    email: str\n" * 20),
            "Add rate limiting to the login endpoint.",
            "Check if Redis connection is working properly.",
            "Here is the server error output:\n" + ("2026-10-28 04:00:00 [ERROR] ConnectionRefusedError: [Errno 111] Connection refused\n" * 20),
            "Switch to the fallback in-memory cache.",
            "Generate unit tests for the caching layer.",
            "Verify all tests pass with code coverage.",
            "Here is the test coverage report:\n" + ("Name                  Stmts   Miss  Cover\ncore/cache.py            45      2    95%\n" * 15),
            "Optimize the memory footprint of the active worker queue.",
            "Deploy the microservice to the local Docker container.",
            "Here is the docker build log:\n" + ("Step 1/10 : FROM python:3.12-slim\n ---> 398247291a\nStep 2/10 : WORKDIR /app\n" * 25),
            "Check the health endpoint via curl http://localhost:8080/health.",
            "Here is the JSON health response:\n" + ("{'status': 'healthy', 'uptime': 3600, 'workers': 4, 'memory_mb': 128}\n" * 10),
            "Summarize all changes made during this session and generate a release tag.",
        ]

        total_unoptimized_tokens = 0
        total_optimized_tokens = 0
        turn_token_records: list[int] = []

        for turn_idx, user_query in enumerate(prompts, start=1):
            conversation_history.append({"role": "user", "content": user_query})

            # Calculate baseline unoptimized token count (all messages + all tools)
            raw_in = estimate_messages_tokens(conversation_history)
            raw_tools = len(dummy_tools) * 30
            raw_turn_tokens = raw_in + raw_tools
            total_unoptimized_tokens += raw_turn_tokens

            # Apply SpaceVTokenHarness 4-tier optimization
            opt_msgs, opt_tools = harness.optimize(
                messages=conversation_history,
                tools=dummy_tools,
                user_prompt=user_query,
            )

            opt_in = estimate_messages_tokens(opt_msgs)
            opt_tools_tok = (len(opt_tools) * 30) if opt_tools else 0
            opt_turn_tokens = opt_in + opt_tools_tok

            total_optimized_tokens += opt_turn_tokens
            turn_token_records.append(opt_turn_tokens)

            # Record turn in TokenLedger
            ledger.record_turn(
                provider="groq",
                model="llama-3.3-70b-versatile",
                agent="coder",
                input_tokens=opt_in,
                output_tokens=150,
                pre_tokens=raw_turn_tokens,
                post_tokens=opt_turn_tokens,
            )

            # Assert individual turn never exceeds 3,000 tokens
            assert opt_turn_tokens < 3000, f"Turn {turn_idx} exceeded 3,000 tokens: {opt_turn_tokens} tokens"

            # Simulate assistant response for ongoing conversation history
            conversation_history.append({
                "role": "assistant",
                "content": f"Understood, completed Turn {turn_idx} task efficiently, Sir."
            })

        # Calculate overall reduction
        reduction_percent = (
            (total_unoptimized_tokens - total_optimized_tokens) / max(total_unoptimized_tokens, 1)
        ) * 100.0

        print(f"\n[TOKEN_REGRESSION] Unoptimized: {total_unoptimized_tokens} tokens")
        print(f"[TOKEN_REGRESSION] Optimized:   {total_optimized_tokens} tokens")
        print(f"[TOKEN_REGRESSION] Reduction:   {reduction_percent:.1f}%")
        print(f"[TOKEN_REGRESSION] Max Turn:    {max(turn_token_records)} tokens")

        # §34.1 Mandatory Assertions:
        # 1. Total tokens consumed across 20 turns < 15,000 tokens (vs ~42,000 baseline)
        assert total_optimized_tokens < 15000, (
            f"Total tokens ({total_optimized_tokens}) exceeded 15,000 ceiling! Baseline: {total_unoptimized_tokens}"
        )

        # 2. Assert no individual turn exceeds 3,000 tokens
        assert max(turn_token_records) < 3000

        # 3. Assert reduction is at least 60%
        assert reduction_percent >= 60.0, f"Reduction was only {reduction_percent:.1f}%, expected >= 60%"


def test_vram_governor_budget_safety():
    """Verifies §33 VRAM memory budget allocations for RTX 3050 (4,096 MB)."""
    governor = GPUMemoryManager(total_vram_mb=4096)

    # 1. Chat mode: 2,450 MB allocated, plenty of headroom
    assert governor.get_current_mode() == "chat"
    assert governor.get_allocated_vram_mb() == 2450
    assert governor.get_headroom_mb() == 4096 - 2450

    # 2. Vision mode switch: 3,050 MB allocated (< 4096 MB)
    can_vision, _ = governor.can_switch_mode("vision")
    assert can_vision is True
    assert governor.request_mode_switch("vision") is True
    assert governor.get_allocated_vram_mb() == 3050

    # 3. Heavy Code mode (Zero VRAM cloud): 600 MB
    assert governor.request_mode_switch("heavy_code") is True
    assert governor.get_allocated_vram_mb() == 600

    # 4. Reject unsafe allocation exceeding 4096 MB
    can_unsafe, _ = governor.can_switch_mode("unsafe_mode_8gb")
    assert can_unsafe is False

    # 5. Status report validity
    report = governor.get_status_report()
    assert report["is_safe"] is True
    assert report["total_vram_mb"] == 4096
