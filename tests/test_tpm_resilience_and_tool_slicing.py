"""
Unit and integration tests for TPM resilience, dynamic tool schema slicing,
and multi-cloud pipeline routing in SpaceV.
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from core.cloud_client import UniversalBrainClient
from tools.registry import (
    CORE_TOOL_NAMES,
    DEFAULT_ESSENTIAL_TOOL_NAMES,
    GUI_TOOL_NAMES,
    OLLAMA_TOOLS_SCHEMA,
    WEB_TOOL_NAMES,
    get_scoped_tools,
)


def test_scoped_tools_token_reduction():
    """Verify that get_scoped_tools reduces schema size by >50% compared to all 50+ tools."""
    assert len(OLLAMA_TOOLS_SCHEMA) > 30

    full_json_len = len(json.dumps(OLLAMA_TOOLS_SCHEMA))
    scoped = get_scoped_tools("write a python script to calculate fibonacci", OLLAMA_TOOLS_SCHEMA)
    scoped_json_len = len(json.dumps(scoped))

    # Assert significant token reduction
    assert len(scoped) < 20
    assert scoped_json_len < (full_json_len * 0.45), f"Scoped len: {scoped_json_len}, Full len: {full_json_len}"

    # Assert core tools are present
    scoped_names = {t["function"]["name"] for t in scoped}
    assert "create_file" in scoped_names
    assert "read_file_content" in scoped_names
    assert "execute_code_block" in scoped_names


def test_scoped_tools_category_routing():
    """Verify GUI and Web keywords trigger their respective tool categories."""
    # GUI Intent
    gui_scoped = get_scoped_tools("click the icon on my desktop screen", OLLAMA_TOOLS_SCHEMA)
    gui_names = {t["function"]["name"] for t in gui_scoped}
    assert any(name in gui_names for name in GUI_TOOL_NAMES)

    # Web Intent
    web_scoped = get_scoped_tools("search google for latest news and scrape the webpage", OLLAMA_TOOLS_SCHEMA)
    web_names = {t["function"]["name"] for t in web_scoped}
    assert "search_google" in web_names or "read_web_page" in web_names


def test_cloud_client_token_estimation_with_tools():
    """Verify that _build_provider_pipeline accounts for tools in token budgeting."""
    client = UniversalBrainClient(
        api_key="gsk_mock_groq",
        gemini_api_key="mock_gemini",
        cerebras_api_key="mock_cerebras",
    )

    # Small message + no tools -> Groq first
    messages_small = [{"role": "user", "content": "hello world"}]
    pipeline_small = client._build_provider_pipeline(
        prompt="hello world",
        messages=messages_small,
        tools=None
    )
    assert pipeline_small[0]["name"] == "Groq"

    # Small message + massive tools (>4800 tokens total) -> Gemini/Cerebras first
    # 50 tools is ~3500 tokens, if messages has ~6000 chars (1500 tokens), total > 4800 tokens
    messages_medium = [{"role": "user", "content": "x" * 6000}]
    pipeline_with_tools = client._build_provider_pipeline(
        prompt="inspect",
        messages=messages_medium,
        tools=OLLAMA_TOOLS_SCHEMA
    )
    # Since tokens > 4800, high-capacity provider should be first
    assert pipeline_with_tools[0]["name"] in ("Google Gemini", "Cerebras")


def test_groq_429_model_hopping():
    """Verify Groq 429 cascades to llama-3.1-8b-instant."""
    client = UniversalBrainClient(
        api_key="gsk_mock_groq",
        gemini_api_key="",
        cerebras_api_key="",
        sambanova_api_key="",
    )

    # Mock requests.post:
    # First call with default model returns 429
    # Second call with llama-3.1-8b-instant returns 200
    mock_resp_429 = MagicMock()
    mock_resp_429.status_code = 429
    mock_resp_429.headers = {"x-ratelimit-reset-tokens": "0.1s"}
    mock_resp_429.json.return_value = {"error": {"message": "Rate limit exceeded on TPM"}}

    mock_resp_200 = MagicMock()
    mock_resp_200.status_code = 200
    mock_resp_200.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "Recovered via 8b model"}}]
    }

    with patch("requests.post", side_effect=[mock_resp_429, mock_resp_200]):
        res = client.chat(
            messages=[{"role": "user", "content": "test"}]
        )
        assert res["content"] == "Recovered via 8b model"
        assert "llama-3.1-8b-instant" in client.last_used_provider
