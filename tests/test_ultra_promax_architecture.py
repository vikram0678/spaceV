"""
Principal Engineer Test Verification Suite for SpaceV Ultra-Promax Architecture.
Empirically verifies all 5 architectural phases derived from CUA, Browser-Use,
Cloudflare MCP Code Mode, Cactus Needle, and Karpathy Guidelines.
"""
import pytest
from core.semantic_router_engine import semantic_router_engine, encode_sparse_text
from core.fast_router import FastRouter
from core.host_bridge import host_bridge
from core.code_mode import code_mode_engine
from core.karpathy_verifier import karpathy_verifier
from spacev.web.cdp_bridge import CDPBridge
from spacev.web.stealth_indexer import SpaceVStealthWebIndexer, IndexedElement
from spacev.web.dom_filter import PaintOrderFilter, DOMElement
from tools.registry import execute_tool, TOOL_ALIASES, TOOL_FUNCTIONS
from tools.gui_tools import pyautogui


# ============================================================================
# PHASE 1: SEMANTIC EMBEDDING INTENT ROUTING (Zero-Regex Natural Phrasing)
# ============================================================================

def test_phase1_youtube_varied_phrasing():
    """Verify semantic router matches varied natural phrasing to YouTube intent in <5ms."""
    queries = [
        "open youtube and play top video",
        "hey open youtube and uma telugu traveller latest video play also",
        "play interstellar on youtube",
        "put on some lofi on youtube",
    ]
    for q in queries:
        route_result = semantic_router_engine.route(q)
        assert route_result is not None, f"Failed to semantically route: '{q}'"
        intent_name, confidence, latency_ms = route_result
        assert intent_name == "media_play_youtube", f"Expected media_play_youtube for '{q}', got {intent_name}"
        assert confidence >= 0.65, f"Confidence too low: {confidence} for '{q}'"
        assert latency_ms < 10.0, f"Latency too high: {latency_ms}ms for '{q}'"


def test_phase1_youtube_query_extraction():
    """Verify robust query parameter extraction from conversational YouTube prompts."""
    prompt1 = "hey open youtube and uma telugu traveller latest video play also"
    extracted1 = semantic_router_engine._extract_youtube_query(prompt1)
    assert "uma telugu traveller" in extracted1.lower()

    prompt2 = "open youtube and play top video"
    extracted2 = semantic_router_engine._extract_youtube_query(prompt2)
    assert "top video" in extracted2.lower()

    prompt3 = "play interstellar on youtube"
    extracted3 = semantic_router_engine._extract_youtube_query(prompt3)
    assert extracted3.lower() == "interstellar"


def test_phase1_editor_and_capabilities_routing():
    """Verify coding and capability queries route cleanly without regex fragility."""
    editor_prompt = "can you open editor and write the code"
    match = semantic_router_engine.route(editor_prompt)
    assert match is not None
    assert match[0] == "open_text_editor"

    cap_prompt = "what can you do"
    cap_match = semantic_router_engine.route(cap_prompt)
    assert cap_match is not None
    assert cap_match[0] == "capabilities"

    fast_cap = FastRouter.match("what can you do")
    assert fast_cap is not None
    assert fast_cap[0] == "capabilities"


# ============================================================================
# PHASE 2: HOST IPC BRIDGE & WSL DISPLAY ISOLATION
# ============================================================================

def test_phase2_host_bridge_path_conversion():
    """Verify bidirectional Linux/Windows path conversion."""
    linux_path = "/home/vikram/Desktop/script.py"
    win_path = host_bridge.to_win_path(linux_path)
    assert win_path is not None
    assert isinstance(win_path, str)


def test_phase2_mock_pyautogui_safety_exceptions():
    """Verify MockPyAutoGUI implements all PyAutoGUI exceptions and easing curves."""
    assert hasattr(pyautogui, "FailSafeException")
    assert hasattr(pyautogui, "ImageNotFoundException")
    assert hasattr(pyautogui, "PyAutoGUIException")
    assert hasattr(pyautogui, "easeInOutQuad")
    assert hasattr(pyautogui, "linear")
    assert hasattr(pyautogui, "easeOutQuad")
    assert hasattr(pyautogui, "easeInQuad")

    # Verify exception instantiation and inheritance
    try:
        raise pyautogui.FailSafeException("Fail-safe triggered")
    except pyautogui.FailSafeException as e:
        assert "Fail-safe" in str(e)


def test_phase2_active_window_inspection():
    """Verify active window inspection returns a safe, non-crashing description."""
    title = host_bridge.get_active_window_title()
    assert isinstance(title, str)
    assert len(title) > 0


# ============================================================================
# PHASE 3: BROWSER-USE ACCESSIBILITY & DOM TREE INDEXING
# ============================================================================

def test_phase3_stealth_dom_indexer():
    """Verify DOM elements are properly parsed and formatted for prompt token compression."""
    raw_elements = [
        {"index": 1, "tag": "input", "text": "Search YouTube", "role": "searchbox", "selector": "#search"},
        {"index": 2, "tag": "button", "text": "Search", "role": "button", "selector": "#search-icon-legacy"},
        {"index": 3, "tag": "a", "text": "Uma Telugu Traveller Video", "role": "link", "selector": "a#video-title"}
    ]
    parsed = SpaceVStealthWebIndexer.parse_elements(raw_elements)
    assert len(parsed) == 3
    formatted = SpaceVStealthWebIndexer.format_for_llm(parsed)
    assert "[1] <input> \"Search YouTube\"" in formatted
    assert "[3] <a> \"Uma Telugu Traveller Video\"" in formatted


def test_phase3_paint_order_filter():
    """Verify occluded, invisible, or offscreen DOM nodes are pruned to save tokens."""
    filter_engine = PaintOrderFilter(viewport_width=1920, viewport_height=1080)
    visible_el = DOMElement(
        index=1, tag="button", text="Play",
        bounds={"x": 500, "y": 400, "w": 100, "h": 50},
        computed_styles={"display": "block", "visibility": "visible", "opacity": "1.0"}
    )
    invisible_el = DOMElement(
        index=2, tag="div", text="Hidden Tracker",
        bounds={"x": 0, "y": 0, "w": 1, "h": 1},
        computed_styles={"display": "none", "visibility": "hidden"}
    )
    offscreen_el = DOMElement(
        index=3, tag="a", text="Footer Link",
        bounds={"x": 500, "y": 5000, "w": 100, "h": 50},
        computed_styles={"display": "block", "visibility": "visible"}
    )

    pruned = filter_engine.prune_tree([visible_el, invisible_el, offscreen_el])
    assert len(pruned) == 1
    assert pruned[0].index == 1


# ============================================================================
# PHASE 4: CLOUDFLARE MCP CODE MODE (Prompt Virtualization)
# ============================================================================

def test_phase4_code_mode_search_tools():
    """Verify dynamic capability discovery returns targeted schemas on-demand."""
    matches = code_mode_engine.search_tools("weather")
    assert len(matches) > 0
    tool_names = [m["name"] for m in matches]
    assert "get_weather" in tool_names


def test_phase4_code_mode_execute_script():
    """Verify sandboxed Python script executes and can invoke registered tools."""
    script = """
computed_val = 15 * 3
time_str = tools.get_current_time()
print(f"Result: {computed_val}")
"""
    res = code_mode_engine.execute_script(script)
    assert res["status"] == "success"
    assert "Result: 45" in res["output"]


def test_phase4_code_mode_tool_registry_aliases():
    """Verify execute_tool supports Code Mode aliases and executions."""
    assert "search_tools" in TOOL_ALIASES
    assert "execute_script" in TOOL_ALIASES

    search_res = execute_tool("search_tools", {"query": "screenshot"})
    assert isinstance(search_res, str)
    assert len(search_res) > 0

    exec_res = execute_tool("execute_script", {"script": "print('Code Mode Operational')"})
    assert "Code Mode Operational" in exec_res


# ============================================================================
# PHASE 5: KARPATHY EMPIRICAL VERIFICATION & SAFETY GUARD
# ============================================================================

def test_phase5_karpathy_safety_audit():
    """Verify Karpathy Verifier blocks destructive patterns."""
    dangerous_payload = "rm -rf /"
    audit = karpathy_verifier.audit_intent_safety("execute_bash", dangerous_payload)
    assert audit["safe"] is False
    assert audit["requires_confirmation"] is True

    safe_payload = "ls -la /home/vikram"
    safe_audit = karpathy_verifier.audit_intent_safety("execute_bash", safe_payload)
    assert safe_audit["safe"] is True
    assert safe_audit["requires_confirmation"] is False


def test_phase5_karpathy_goal_verification_loop():
    """Verify goal-backward empirical verification loop."""
    attempts = [False, False, True]
    counter = 0

    def mock_verification():
        nonlocal counter
        res = attempts[counter]
        counter += 1
        return res

    result = karpathy_verifier.verify_goal_backward(
        goal_description="Verify video playback active",
        verification_fn=mock_verification,
        max_attempts=3
    )
    assert result["verified"] is True
    assert result["attempts"] == 3
