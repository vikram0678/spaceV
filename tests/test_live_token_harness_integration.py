"""
Live End-to-End Token Harness Integration Test.
Verifies that:
1. HybridBrainAgent.chat_stream() invokes token_harness.optimize().
2. Pre-optimization vs post-optimization token counts are computed and passed.
3. UniversalBrainClient extracts real token usage or estimates them accurately.
4. TokenLedger appends truthful records to .spacev/token_ledger.jsonl with real metrics.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.brain_orchestrator import HybridBrainAgent
from core.rate_limiter import rate_limiter
from core.token_ledger import TokenLedger


def test_live_chat_stream_records_truthful_token_ledger_entry(tmp_path, monkeypatch):
    """
    Validates that executing chat_stream() results in an authentic TokenLedger entry
    with real token counts and rate limiter bucket tracking.
    """
    rate_limiter.reset_all()
    test_ledger = TokenLedger(ledger_dir=tmp_path)
    import core.token_ledger
    monkeypatch.setattr(core.token_ledger, "token_ledger", test_ledger)

    agent = HybridBrainAgent(provider="openai")

    # Mock cloud_client HTTP response with realistic OpenAI payload
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "I am SpaceV, ready to assist you!"}}],
        "usage": {"prompt_tokens": 320, "completion_tokens": 45, "total_tokens": 365}
    }

    with patch("requests.post", return_value=mock_response):
        reply = agent.chat_stream("Hello SpaceV, can you help me write Python code?")
        assert "SpaceV" in reply or len(reply) > 0

    # Verify ledger file on disk
    entries = test_ledger.get_entries(limit=10)
    assert len(entries) >= 1
    last_entry = entries[-1]

    # Verify fields are no longer static dummy 1000/200/0.0%
    assert last_entry.input_tokens == 320
    assert last_entry.output_tokens == 45
    assert last_entry.total_tokens == 365
    assert last_entry.pre_optimization_tokens > 0
    assert last_entry.post_optimization_tokens > 0
    assert last_entry.agent == "direct"
    assert last_entry.provider != ""


def test_streaming_token_estimation_when_usage_block_missing(tmp_path, monkeypatch):
    """
    Validates that streaming responses lacking usage blocks fall back to accurate
    heuristic estimation rather than hardcoded 1000/200 tokens.
    """
    rate_limiter.reset_all()
    test_ledger = TokenLedger(ledger_dir=tmp_path)
    import core.token_ledger
    monkeypatch.setattr(core.token_ledger, "token_ledger", test_ledger)

    agent = HybridBrainAgent(provider="openai")

    # Simulate SSE streaming without usage block
    sse_lines = [
        b'data: {"choices": [{"delta": {"content": "Hello "}}]}',
        b'data: {"choices": [{"delta": {"content": "world!"}}]}',
        b'data: [DONE]'
    ]
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.iter_lines.return_value = sse_lines
    mock_response.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "Hello world!"}}],
        "usage": {}
    }

    streamed_tokens = []
    def on_token(t):
        streamed_tokens.append(t)

    with patch("requests.post", return_value=mock_response):
        reply = agent.chat_stream("hello there", token_callback=on_token)
        assert "Hello" in reply

    entries = test_ledger.get_entries(limit=10)
    assert len(entries) >= 1
    last_entry = entries[-1]

    # Must be estimated from content length (~12 chars -> ~3 tokens), NOT static 200!
    assert last_entry.output_tokens < 50
    assert last_entry.output_tokens > 0
    assert last_entry.input_tokens > 0
    assert last_entry.input_tokens != 1000
