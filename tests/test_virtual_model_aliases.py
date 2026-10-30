"""
Tests for SpaceV Virtual Model Aliases and Providers YAML Configuration (Option A).
Verifies:
1. VirtualModelRouter resolves virtual aliases (spacev/auto, spacev/fast, spacev/coder, spacev/smart).
2. Key pools and models are loaded from config/providers.yaml.
3. UniversalBrainClient prioritizes correct provider pipelines according to the alias.
4. Backward compatibility with direct BYOK mode and standard model strings.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch
import pytest

from core.virtual_router import VirtualModelRouter, virtual_router
from core.cloud_client import UniversalBrainClient


def test_virtual_model_router_alias_detection():
    router = VirtualModelRouter()

    assert router.is_virtual_alias("spacev/auto") is True
    assert router.is_virtual_alias("spacev/fast") is True
    assert router.is_virtual_alias("spacev/coder") is True
    assert router.is_virtual_alias("spacev/smart") is True
    assert router.is_virtual_alias("auto") is True
    assert router.is_virtual_alias("openai/gpt-4o") is False
    assert router.is_virtual_alias("deepseek/deepseek-v4.1-flash") is False
    assert router.is_virtual_alias(None) is False


def test_virtual_model_router_dynamic_auto_resolution():
    router = VirtualModelRouter()

    # Coding task
    assert router.resolve_alias("spacev/auto", prompt="Write a python function to parse JSON") == "spacev/coder"
    assert router.resolve_alias("spacev/auto", prompt="Debug this git merge conflict in repo") == "spacev/coder"

    # Vision / Deep Reasoning task
    assert router.resolve_alias("spacev/auto", prompt="Please take a screenshot of my screen") == "spacev/smart"
    assert router.resolve_alias("spacev/auto", prompt="x" * 5000) == "spacev/smart"

    # Fast conversational greeting
    assert router.resolve_alias("spacev/auto", prompt="Hello there, what is the weather today?") == "spacev/fast"

    # Explicit aliases remain unchanged
    assert router.resolve_alias("spacev/fast", prompt="Write python code") == "spacev/fast"
    assert router.resolve_alias("spacev/coder", prompt="Hello") == "spacev/coder"
    assert router.resolve_alias("spacev/smart", prompt="Hello") == "spacev/smart"

    # Concrete model name passes through
    assert router.resolve_alias("deepseek/deepseek-v4.1-flash", prompt="Hello") == "deepseek/deepseek-v4.1-flash"


def test_yaml_config_loading_and_keys():
    router = VirtualModelRouter()
    groq_keys = router.get_provider_keys("groq")
    assert len(groq_keys) >= 1
    assert any("gsk_" in k for k in groq_keys)

    gemini_keys = router.get_provider_keys("gemini")
    assert len(gemini_keys) >= 1
    assert any("AQ." in k for k in gemini_keys)


def test_cloud_client_pipeline_with_virtual_alias_fast():
    client = UniversalBrainClient(
        routing_mode="hybrid",
        api_key="mock_key",
    )
    # When requesting spacev/fast, fast pool candidates (cerebras fast / groq fast) should appear at top
    pipeline = client._build_provider_pipeline(prompt="Quick hello", requested_model="spacev/fast")
    assert len(pipeline) > 0
    first_names = [p["name"] for p in pipeline[:3]]
    assert any("Fast" in name or "Groq" in name or "Cerebras" in name for name in first_names)


def test_cloud_client_pipeline_with_virtual_alias_coder():
    client = UniversalBrainClient(
        routing_mode="hybrid",
        api_key="mock_key",
    )
    # When requesting spacev/coder, coder specialists (Mistral/Codestral or Groq) should be prioritized
    pipeline = client._build_provider_pipeline(prompt="def solve(): pass", requested_model="spacev/coder")
    assert len(pipeline) > 0
    first_names = [p["name"] for p in pipeline[:4]]
    assert any("Mistral" in name or "Groq" in name for name in first_names)


def test_cloud_client_pipeline_with_virtual_alias_smart():
    client = UniversalBrainClient(
        routing_mode="hybrid",
        api_key="mock_key",
    )
    # When requesting spacev/smart, high-context providers (Gemini / SambaNova) should be prioritized
    pipeline = client._build_provider_pipeline(prompt="Deep analysis", requested_model="spacev/smart")
    assert len(pipeline) > 0
    first_names = [p["name"] for p in pipeline[:4]]
    assert any("Gemini" in name or "SambaNova" in name for name in first_names)


def test_cloud_client_direct_mode_with_virtual_alias():
    client = UniversalBrainClient(
        base_url="https://api.airouter.in/v1",
        api_key="sk-air-v1-test",
        default_model="deepseek/deepseek-v4.1-flash",
        routing_mode="direct",
    )
    # In direct mode with spacev/auto, it should cleanly fall back to default paid model without crashing
    pipeline = client._build_provider_pipeline(prompt="hello", requested_model="spacev/auto")
    assert len(pipeline) == 1
    assert pipeline[0]["name"] == "Direct Paid API"
    assert pipeline[0]["model"] == "deepseek/deepseek-v4.1-flash"

