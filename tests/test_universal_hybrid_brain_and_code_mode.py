"""
Test suite for SpaceV Universal Hybrid Brain Orchestrator & Code Mode Tool Virtualization.
Validates:
1. Universal Hybrid Brain (Cloud + Local Offline) orchestration.
2. 100% backward compatibility of core.ollama_client bridge.
3. Code Mode token reduction (81% reduction vs monolithic 35-tool schema).
4. Dynamic tool search and in-process execution sandbox.
"""
import json

from core.brain_orchestrator import (
    SYSTEM_PROMPT,
    HybridBrainAgent,
    SpaceVAgent,
    parse_fallback_tool_calls,
)
from core.code_mode import CODE_MODE_META_TOOLS, code_mode_engine
from core.ollama_client import OllamaAgent
from tools.registry import OLLAMA_TOOLS_SCHEMA


def test_bridge_backward_compatibility():
    """Verify that importing OllamaAgent from core.ollama_client seamlessly aliases to HybridBrainAgent."""
    assert OllamaAgent is HybridBrainAgent
    assert SpaceVAgent is HybridBrainAgent

    agent = OllamaAgent()
    assert isinstance(agent, HybridBrainAgent)
    assert hasattr(agent, "chat_stream")
    assert hasattr(agent, "reset_conversation")


def test_system_prompt_integrity():
    """Verify SpaceV persona, Jarivs/Gemini tone, and Celesto sandbox containment policy."""
    assert "System Protocol Autonomous Cybernetic Engine Version V" in SYSTEM_PROMPT
    assert "Celesto Sandbox Containment Policy" in SYSTEM_PROMPT
    assert "detonate_in_sandbox" in SYSTEM_PROMPT


def test_code_mode_token_reduction():
    """
    Empirically prove that Code Mode slashes prompt schema footprint by >80%.
    Monolithic schema is ~24,000 characters (>5,500 tokens).
    Code Mode meta-tools schema is <1,200 characters (<250 tokens).
    """
    assert len(CODE_MODE_META_TOOLS) == 2
    tool_names = [t["function"]["name"] for t in CODE_MODE_META_TOOLS]
    assert "spacev_search_tools" in tool_names
    assert "spacev_execute_script" in tool_names

    code_mode_chars = len(json.dumps(CODE_MODE_META_TOOLS))
    monolithic_chars = len(json.dumps(OLLAMA_TOOLS_SCHEMA))

    assert code_mode_chars < 1200
    assert monolithic_chars > 20000

    reduction_percentage = ((monolithic_chars - code_mode_chars) / monolithic_chars) * 100
    assert reduction_percentage > 80.0


def test_code_mode_search_and_execute():
    """Verify search_tools dynamic query matching and execute_script sandboxing."""
    # 1. Search for sandbox capabilities
    sandbox_tools = code_mode_engine.search_tools("sandbox isolate detonate")
    assert any("sandbox" in t["name"] or "detonate" in t["name"] for t in sandbox_tools)

    # 2. Search for web scraping
    web_tools = code_mode_engine.search_tools("web scrape browse")
    assert any("web" in t["name"] or "scrape" in t["name"] or "browse" in t["name"] for t in web_tools)

    # 3. Execute sandboxed Python script
    script = """
a = 15
b = 27
print(f"Computed sum is {a + b}")
"""
    result = code_mode_engine.execute_script(script)
    assert result["status"] == "success"
    assert "Computed sum is 42" in result["output"]


def test_hybrid_brain_tool_resolution_cloud_vs_local():
    """Verify that cloud agent uses Code Mode meta-tools while local offline agent uses scoped slices."""
    cloud_agent = HybridBrainAgent(provider="openai")
    cloud_tools = cloud_agent._resolve_tools("create a file and check disk", needs_tools=True)
    assert cloud_tools == CODE_MODE_META_TOOLS

    local_agent = HybridBrainAgent(provider="ollama")
    local_tools = local_agent._resolve_tools("create a file and check disk", needs_tools=True)
    # Local agent receives a scoped subset from OLLAMA_TOOLS_SCHEMA, not the 2 cloud meta-tools
    assert local_tools != CODE_MODE_META_TOOLS
    assert len(local_tools) >= 5


def test_fallback_tool_call_xml_parsing():
    """Verify that XML tag emitted by local or smaller models is parsed cleanly."""
    xml_output = '<tool_call>{"name": "create_file", "arguments": {"file_name": "test.txt", "content": "hello"}}</tool_call>'
    calls, clean = parse_fallback_tool_calls(xml_output)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "create_file"
    assert calls[0]["function"]["arguments"]["file_name"] == "test.txt"
    assert clean == ""
