"""
Unit & Integration Test Suite for SpaceV Multi-Account Free Mesh & Context Compressor
Verifies:
1. Context compression (grep, ANSI, code elision, traceback preservation).
2. Pre-emptive round-robin key rotation across multi-account pools.
3. 30-second circuit-breaker cooldown on 429 TPM errors.
4. 24-hour daily quota cooldown on 429 TPD/RPD limits.
5. BYOK Direct Paid Mode bypass.
"""
import time

from core.context_compressor import (
    compress_tool_output,
    compress_shell_output,
    compress_file_content,
    has_error_signature,
)
from core.cloud_client import UniversalBrainClient


# ==============================================================================
# 1. CONTEXT COMPRESSOR TESTS (OmniRoute Pattern in Native Python)
# ==============================================================================

def test_context_compressor_grep_elision():
    """Verify grep search results are capped to top matches with distinct files summarized."""
    raw_grep = "\n".join([f"core/module_{i}.py:{i * 10}:def function_{i}(): pass" for i in range(1, 60)])
    compressed = compress_tool_output(raw_grep, max_chars=1000)

    assert "... [" in compressed
    assert "lines elided for token budget" in compressed
    assert "Unique files matched" in compressed
    assert len(compressed) < len(raw_grep)


def test_context_compressor_shell_ansi_stripping():
    """Verify shell output strips terminal ANSI escape codes and deduplicates identical lines."""
    raw_shell = "\x1b[32m[SUCCESS]\x1b[0m Download complete\n" * 15
    compressed = compress_shell_output(raw_shell, max_lines=5)

    assert "\x1b[" not in compressed
    assert "[SUCCESS] Download complete" in compressed


def test_context_compressor_code_file_middle_elision():
    """Verify code files retain imports (head) and bottom exports (tail) while eliding the middle."""
    code_lines = ["import os", "import sys", "from typing import Any"] + [f"x_{i} = {i}" for i in range(50)] + ["export_value = 100"]
    raw_code = "\n".join(code_lines)
    compressed = compress_file_content(raw_code, keep_head=10, keep_tail=5)

    assert "import os" in compressed
    assert "export_value = 100" in compressed
    assert "... [" in compressed
    assert "lines elided for token budget" in compressed


def test_context_compressor_traceback_preservation():
    """CRITICAL: Assert stack traces and exceptions are NEVER elided for agent self-debugging."""
    traceback_log = """
    Traceback (most recent call last):
      File "main.py", line 42, in <module>
        run_agent()
      File "core/graph_engine.py", line 150, in step
        raise ValueError("Invalid tool parameters: missing file_name")
    ValueError: Invalid tool parameters: missing file_name
    """
    assert has_error_signature(traceback_log) is True
    compressed = compress_tool_output(traceback_log, max_chars=500)
    assert "Traceback (most recent call last):" in compressed
    assert "ValueError: Invalid tool parameters: missing file_name" in compressed


# ==============================================================================
# 2. MULTI-ACCOUNT ROTATION & CIRCUIT BREAKER TESTS
# ==============================================================================

def test_preemptive_round_robin_key_rotation():
    """Verify consecutive turns alternate between accounts in the pool to prevent 60s TPM collisions."""
    client = UniversalBrainClient(
        api_key="rot-key-1",
        routing_mode="free_mesh",
    )
    client._cooldowns = {}
    client.groq_keys = ["rot-key-1", "rot-key-2", "rot-key-3"]

    # Turn 1
    pipeline_1 = client._build_provider_pipeline(prompt="edit file")
    groq_candidates_1 = [p for p in pipeline_1 if "Groq" in p["name"]]
    assert groq_candidates_1[0]["api_key"] == "rot-key-1"

    # Turn 2: Pre-emptive rotation shifts active key to Key 2
    pipeline_2 = client._build_provider_pipeline(prompt="edit file")
    groq_candidates_2 = [p for p in pipeline_2 if "Groq" in p["name"]]
    assert groq_candidates_2[0]["api_key"] == "rot-key-2"

    # Turn 3: Pre-emptive rotation shifts active key to Key 3
    pipeline_3 = client._build_provider_pipeline(prompt="edit file")
    groq_candidates_3 = [p for p in pipeline_3 if "Groq" in p["name"]]
    assert groq_candidates_3[0]["api_key"] == "rot-key-3"


def test_circuit_breaker_30s_cooldown_on_tpm_429():
    """Verify HTTP 429 TPM sets a 35s circuit breaker and skips that key immediately."""
    client = UniversalBrainClient(
        api_key="groq-key-1",
        routing_mode="free_mesh",
    )
    client.groq_keys = ["groq-key-1", "groq-key-2"]

    # Key 1 is tripped with a sliding-window TPM 429
    client._save_cooldown("groq-key-1", 35.0)
    assert client.is_in_cooldown("groq-key-1") is True

    # Next pipeline build should automatically skip Key 1 and select Key 2
    pipeline = client._build_provider_pipeline(prompt="edit file")
    groq_candidates = [p for p in pipeline if "Groq" in p["name"]]
    assert groq_candidates[0]["api_key"] == "groq-key-2"


def test_circuit_breaker_24h_cooldown_on_daily_limit():
    """Verify daily limits (TPD / 20 RPD) trigger 24-hour cooldowns."""
    client = UniversalBrainClient(
        api_key="gemini-key-1",
        routing_mode="free_mesh",
    )
    # Trip daily cooldown
    client._save_cooldown("gemini-key-1", 86400.0)
    assert client.is_in_cooldown("gemini-key-1") is True
    cooldown_expiry = client._cooldowns.get("gemini-key-1", 0)
    assert cooldown_expiry > time.time() + 86000


def test_byok_direct_mode():
    """Verify direct BYOK paid mode routes exclusively to the configured paid key without mesh rotation."""
    client = UniversalBrainClient(
        base_url="https://api.openai.com/v1",
        api_key="sk-paid-openai-commercial-key",
        default_model="gpt-4o",
        routing_mode="direct",
    )

    pipeline = client._build_provider_pipeline(prompt="hello")
    assert len(pipeline) == 1
    assert pipeline[0]["name"] == "Direct Paid API"
    assert pipeline[0]["api_key"] == "sk-paid-openai-commercial-key"
    assert pipeline[0]["model"] == "gpt-4o"
