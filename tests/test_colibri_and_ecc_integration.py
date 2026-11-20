"""
Test suite for Colibrì Local MoE Integration and ECC Token Optimization Patterns.
Verifies prompt caching prefix alignment, PreCompact memory persistence hooks,
and Colibrì client communication.
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from core.colibri_client import ColibriClient, colibri_client
from core.token_harness import HeadroomSmartCrusher, SpaceVTokenHarness


def test_prompt_caching_prefix_alignment():
    """
    ECC Prompt Caching Prefix Stabilization (skills/prompt-caching-strategy).
    Ensures:
    1. Consolidates multiple system messages into a single canonical message at index 0.
    2. Deterministically sorts tool definitions by name to preserve KV-cache hits.
    3. Retains turn sequence for user and assistant messages.
    """
    harness = SpaceVTokenHarness()

    messages = [
        {"role": "system", "content": "You are SpaceV Cybernetic Assistant."},
        {"role": "user", "content": "Search for AI jobs in Bengaluru."},
        {"role": "system", "content": "Always output concise responses."},
        {"role": "assistant", "content": "Found 5 jobs."},
        {"role": "user", "content": "Save them to desktop."},
    ]

    tools = [
        {"type": "function", "function": {"name": "save_to_desktop", "description": "Save file"}},
        {"type": "function", "function": {"name": "browser_action", "description": "Browse web"}},
        {"type": "function", "function": {"name": "api_harvest", "description": "Harvest data"}},
    ]

    aligned_messages, aligned_tools = harness.align_prefix_for_prompt_caching(messages, tools)

    # 1. System prompt is anchored at index 0
    assert len(aligned_messages) == 4
    assert aligned_messages[0]["role"] == "system"
    assert "SpaceV Cybernetic Assistant" in aligned_messages[0]["content"]
    assert "Always output concise responses" in aligned_messages[0]["content"]

    # 2. Sequence of conversation turns preserved
    assert aligned_messages[1]["role"] == "user"
    assert aligned_messages[1]["content"] == "Search for AI jobs in Bengaluru."
    assert aligned_messages[2]["role"] == "assistant"
    assert aligned_messages[3]["role"] == "user"

    # 3. Tools are deterministically sorted alphabetically by name
    assert aligned_tools is not None
    tool_names = [t["function"]["name"] for t in aligned_tools]
    assert tool_names == ["api_harvest", "browser_action", "save_to_desktop"]


def test_pre_compact_memory_persistence_hook(monkeypatch):
    """
    ECC PreCompact Lifecycle Hook (hooks/memory-persistence).
    Verifies that critical user preferences and tool outcomes are flushed into
    spacev_memory before the crusher summarizes or trims conversation turns.
    """
    crusher = HeadroomSmartCrusher()

    recorded_notes: list[str] = []
    mock_memory = MagicMock()
    mock_memory.append_note.side_effect = lambda note: recorded_notes.append(note)

    # Patch memory import in token_harness
    import core.memory
    monkeypatch.setattr(core.memory, "memory", mock_memory)

    history = [
        {"role": "user", "content": "I prefer dark mode and always save reports to desktop"},
        {"role": "assistant", "content": "Understood, Sir."},
        {"role": "tool", "content": "Successfully harvested 12 jobs in Bengaluru and saved to file."},
        {"role": "user", "content": "Also remember my preferred profile is Person 1"},
        {"role": "assistant", "content": "Noted."},
    ]

    # Trigger compaction
    with patch("core.event_bus.event_bus.publish") as mock_publish:
        compressed = crusher.compress_history(history, max_output_tokens=200, preserve_last_n=1)

        # PreCompact hook must have intercepted and flushed notes
        assert len(recorded_notes) >= 1
        combined_notes = " ".join(recorded_notes)
        assert "prefer dark mode" in combined_notes or "preferred profile" in combined_notes
        assert "Tool: Successfully harvested" in combined_notes

        # Event bus must be notified
        mock_publish.assert_called_with(
            "context.pre_compact",
            {"compressed_count": 4, "checkpoint_facts": pytest.approx(3, abs=2)}
        )


def test_colibri_client_installation_and_discovery():
    """Verifies Colibrì client local installation check and model listing."""
    client = ColibriClient()

    # Client sees local installation in D:\agentSpace\eto\colibri
    assert client.is_installed() is True

    # Server readiness check when offline
    with patch("requests.get", side_effect=Exception("Connection refused")):
        assert client.is_server_running() is False
        models = client.get_available_models()
        assert "colibri-moe-744b" in models


def test_colibri_client_chat_completion_payload():
    """Verifies Colibrì client chat completion payload conforms to OpenAI standard."""
    client = ColibriClient()

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "id": "coli-1234",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Autonomous task executed locally on Colibri MoE with 0 tokens.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 42, "completion_tokens": 15, "total_tokens": 57},
    }

    with patch("requests.post", return_value=fake_response) as mock_post:
        messages = [{"role": "user", "content": "Hello local MoE"}]
        tools = [{"type": "function", "function": {"name": "test_tool"}}]

        result = client.chat_completion(messages=messages, tools=tools, temperature=0.5)

        assert mock_post.called
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["json"]["model"] == "colibri-moe-744b"
        assert call_kwargs["json"]["temperature"] == 0.5
        assert call_kwargs["json"]["messages"] == messages
        assert call_kwargs["json"]["tools"] == tools

        assert result["choices"][0]["message"]["content"] == (
            "Autonomous task executed locally on Colibri MoE with 0 tokens."
        )


def test_cloud_client_colibri_failover():
    """
    Verifies that UniversalBrainClient prioritizes active local Colibrì engine
    before falling back to Ollama when cloud providers are exhausted.
    """
    from core.cloud_client import UniversalBrainClient

    client = UniversalBrainClient()

    messages = [{"role": "user", "content": "Perform offline analysis"}]

    with patch.object(client, "_build_provider_pipeline", return_value=[]), \
         patch.object(client, "_fallback_to_ollama") as mock_ollama, \
         patch("core.colibri_client.colibri_client.is_server_running", return_value=True), \
         patch("core.colibri_client.colibri_client.chat_completion", return_value={
             "choices": [{"message": {"role": "assistant", "content": "Colibri MoE offline response", "tool_calls": []}}]
         }):
        res = client.chat(messages=messages)
        assert res["content"] == "Colibri MoE offline response"
        assert client.last_used_provider == "colibri_local"
        mock_ollama.assert_not_called()


def test_cloud_success_does_not_invoke_colibri():
    """Verify that successful cloud response returns immediately without probing Colibrì."""
    from core.cloud_client import UniversalBrainClient

    client = UniversalBrainClient()
    messages = [{"role": "user", "content": "Hello"}]
    fake_pipeline = [{
        "name": "MockProvider",
        "base_url": "https://api.example.com/v1",
        "api_key": "test-key",
        "model": "test-model",
    }]
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "Cloud response", "tool_calls": []}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }

    with patch.object(client, "_build_provider_pipeline", return_value=fake_pipeline), \
         patch("requests.post", return_value=fake_response), \
         patch("core.colibri_client.colibri_client.is_server_running") as mock_is_running, \
         patch("core.colibri_client.colibri_client.chat_completion") as mock_colibri_chat:
        res = client.chat(messages=messages)
        assert res["content"] == "Cloud response"
        mock_is_running.assert_not_called()
        mock_colibri_chat.assert_not_called()


def test_colibri_unavailable_in_direct_mode_returns_endpoint_error():
    """Verify that when Colibrì is unavailable in direct mode, Ollama is not silently invoked."""
    from core.cloud_client import UniversalBrainClient

    client = UniversalBrainClient(api_key="sk-real-paid-key", routing_mode="direct")
    messages = [{"role": "user", "content": "Perform offline analysis"}]

    with patch.object(client, "_build_provider_pipeline", return_value=[]), \
         patch.object(client, "_fallback_to_ollama") as mock_ollama, \
         patch("core.colibri_client.colibri_client.is_server_running", return_value=False):
        res = client.chat(messages=messages)
        assert "The configured LLM endpoint did not return a usable response" in res["content"]
        assert client.last_used_provider == "configured_endpoint_error"
        mock_ollama.assert_not_called()


def test_colibri_exception_in_direct_mode_does_not_bypass_endpoint_guard():
    """Verify that an exception in Colibrì in direct mode falls through safely to endpoint error."""
    from core.cloud_client import UniversalBrainClient

    client = UniversalBrainClient(api_key="sk-real-paid-key", routing_mode="direct")
    messages = [{"role": "user", "content": "Perform offline analysis"}]

    with patch.object(client, "_build_provider_pipeline", return_value=[]), \
         patch.object(client, "_fallback_to_ollama") as mock_ollama, \
         patch("core.colibri_client.colibri_client.is_server_running", return_value=True), \
         patch("core.colibri_client.colibri_client.chat_completion", side_effect=RuntimeError("Engine crashed")):
        res = client.chat(messages=messages)
        assert "The configured LLM endpoint did not return a usable response" in res["content"]
        assert client.last_used_provider == "configured_endpoint_error"
        mock_ollama.assert_not_called()


@pytest.mark.parametrize("bad_response", [
    None,
    {},
    {"choices": []},
    {"choices": [{}]},
    {"choices": [{"message": {}}]},
    {"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": []}}]},
])
def test_colibri_empty_or_malformed_response_in_direct_mode(bad_response):
    """Verify that empty or malformed Colibrì responses are safely handled and don't bypass direct guard."""
    from core.cloud_client import UniversalBrainClient

    client = UniversalBrainClient(api_key="sk-real-paid-key", routing_mode="direct")
    messages = [{"role": "user", "content": "Perform offline analysis"}]

    with patch.object(client, "_build_provider_pipeline", return_value=[]), \
         patch.object(client, "_fallback_to_ollama") as mock_ollama, \
         patch("core.colibri_client.colibri_client.is_server_running", return_value=True), \
         patch("core.colibri_client.colibri_client.chat_completion", return_value=bad_response):
        res = client.chat(messages=messages)
        assert "The configured LLM endpoint did not return a usable response" in res["content"]
        assert client.last_used_provider == "configured_endpoint_error"
        mock_ollama.assert_not_called()


def test_non_direct_mode_preserves_ollama_fallback_when_colibri_unavailable():
    """Verify that non-direct mode preserves existing Ollama fallback when Colibrì is unavailable."""
    from core.cloud_client import UniversalBrainClient

    client = UniversalBrainClient(api_key="sk-mesh-key", routing_mode="free_mesh")
    messages = [{"role": "user", "content": "Perform offline analysis"}]

    with patch.object(client, "_build_provider_pipeline", return_value=[]), \
         patch("core.colibri_client.colibri_client.is_server_running", return_value=False), \
         patch.object(client, "_fallback_to_ollama", return_value={
             "role": "assistant",
             "content": "Ollama local fallback response",
             "tool_calls": [],
         }) as mock_ollama:
        res = client.chat(messages=messages)
        assert res["content"] == "Ollama local fallback response"
        mock_ollama.assert_called_once()


def test_colibri_tool_call_response_handling():
    """Verify that Colibrì tool calls are returned properly without requiring content."""
    from core.cloud_client import UniversalBrainClient

    client = UniversalBrainClient()
    messages = [{"role": "user", "content": "Run calculator"}]
    expected_tools = [{"id": "call_1", "type": "function", "function": {"name": "calc", "arguments": "{}"}}]

    with patch.object(client, "_build_provider_pipeline", return_value=[]), \
         patch("core.colibri_client.colibri_client.is_server_running", return_value=True), \
         patch("core.colibri_client.colibri_client.chat_completion", return_value={
             "choices": [{"message": {"role": "assistant", "content": "", "tool_calls": expected_tools}}]
         }):
        res = client.chat(messages=messages)
        assert res["tool_calls"] == expected_tools
        assert client.last_used_provider == "colibri_local"
