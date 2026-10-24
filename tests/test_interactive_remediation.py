"""
Tests for Live Interactive Remediation Protocol (IRP) & Human-In-The-Loop Execution.
Validates Crawl4AI-style diagnostic extraction, Browser-Use style non-destructive pause,
and in-situ resume flows.
"""
import pytest
from core.self_healing import self_healing_engine, SelfHealingEngine
from core.graph_engine import SpaceVGraphEngine
from core.ollama_client import OllamaAgent
from core.proactive_companion import ProactiveCompanion


def test_diagnose_failure_browser_runtime_structured():
    """Verify BROWSER_RUNTIME_FAILURE yields locus and 3 actionable options."""
    tool = "browse_interactive_dom"
    args = {"url": "https://github.com/unclecode/crawl4ai"}
    err = "AttributeError: 'NoneType' object has no attribute 'goto' - playwright offline"

    diag = self_healing_engine.diagnose_failure(tool, args, err)
    assert diag["category"] == "BROWSER_RUNTIME_FAILURE"
    assert diag["locus"] == "https://github.com/unclecode/crawl4ai"
    assert len(diag["remediation_options"]) == 3

    opt1, opt2, opt3 = diag["remediation_options"]
    assert opt1["index"] == 1
    assert "playwright install" in opt1.get("action", "")
    assert opt2["index"] == 2
    assert opt2.get("tool") == "read_web_page"
    assert opt3["index"] == 3
    assert opt3.get("action_type") == "manual"


def test_diagnose_failure_dependency_missing():
    """Verify DEPENDENCY_MISSING correctly captures missing package/command."""
    tool = "execute_terminal_command"
    args = {"command": "python -m beautifulsoup4"}
    err = "ModuleNotFoundError: No module named 'bs4'"

    diag = self_healing_engine.diagnose_failure(tool, args, err)
    assert diag["category"] == "DEPENDENCY_MISSING"
    assert diag["locus"] == "bs4"
    assert len(diag["remediation_options"]) == 3

    opt1 = diag["remediation_options"][0]
    assert "pip install bs4" in opt1.get("action", "")


def test_format_clarification_card():
    """Verify the clarification card is formatted cleanly without defeatist apologies."""
    diag = {
        "tool": "browse_interactive_dom",
        "locus": "https://github.com/unclecode/crawl4ai",
        "category": "BROWSER_RUNTIME_FAILURE",
        "explanation": "Playwright Chromium browser binary missing.",
        "remediation_options": [
            {"index": 1, "name": "Auto-Install", "description": "Install Chromium binaries."},
            {"index": 2, "name": "Semantic Reader", "description": "Degrade to HTTP markdown reader."},
            {"index": 3, "name": "Manual Review", "description": "Fix in terminal and continue."}
        ]
    }
    card = self_healing_engine.format_clarification_card(diag)
    assert "⏸️ **SpaceV Live Clarification & Remediation Protocol**" in card
    assert "browse_interactive_dom" in card
    assert "https://github.com/unclecode/crawl4ai" in card
    assert "[1] Auto-Install" in card
    assert "[2] Semantic Reader" in card
    assert "[3] Manual Review" in card
    # Ensure no defeatist apologies
    assert "sorry" not in card.lower()
    assert "apologize" not in card.lower()


def test_proactive_companion_followup_chips_for_clarification():
    """Verify clarification card triggers 1, 2, continue quick action chips in UI."""
    sample_reply = (
        "⏸️ **SpaceV Live Clarification & Remediation Protocol**\n"
        "I encountered an issue executing `browse_interactive_dom`."
    )
    chips = ProactiveCompanion.get_follow_up_chips(tool_name="browse_interactive_dom", reply_text=sample_reply)
    assert len(chips) == 3
    labels = [c[0] for c in chips]
    actions = [c[1] for c in chips]
    assert any("Auto-Repair" in l for l in labels)
    assert "1" in actions
    assert "2" in actions
    assert "continue" in actions


def test_graph_engine_active_paused_frame_resume_option2():
    """Verify responding with '2' or 'alternative' executes option 2 tool directly."""
    agent = OllamaAgent()
    engine = SpaceVGraphEngine(agent=agent)

    # Set up an active paused frame simulating a failed browser call
    agent.active_paused_frame = {
        "tool": "browse_interactive_dom",
        "args": {"url": "https://github.com/unclecode/crawl4ai"},
        "diagnosis": {
            "category": "BROWSER_RUNTIME_FAILURE",
            "explanation": "Browser launch offline."
        },
        "remediation_options": [
            {"index": 1, "name": "Auto-Install", "action": "playwright install chromium"},
            {"index": 2, "name": "Alternative Tool", "tool": "read_web_page", "args": {"url": "https://github.com/unclecode/crawl4ai"}},
            {"index": 3, "name": "Manual", "action_type": "manual"}
        ],
        "user_prompt": "what is inside crawl4ai"
    }

    state = {
        "user_prompt": "2",
        "messages": [],
        "fast_path_result": None,
        "tool_calls": [],
        "tool_results": [],
        "active_window": "",
        "stuck_detected": False,
        "clarification_question": None,
        "final_response": "",
        "iteration": 0,
        "is_complete": False,
        "healing_attempts": 0,
        "last_error": None,
        "scratchpad": {}
    }

    res = engine._fast_router_node(state)
    assert res.get("tool_calls") is not None
    assert len(res["tool_calls"]) == 1
    assert res["tool_calls"][0]["function"]["name"] == "read_web_page"
    assert res["tool_calls"][0]["function"]["arguments"]["url"] == "https://github.com/unclecode/crawl4ai"
    # Verify frame was consumed
    assert agent.active_paused_frame is None

    # Verify conditional edge routes to tool_executor
    route = engine._route_after_fast_router(res)
    assert route == "direct_tools"


def test_graph_engine_active_paused_frame_resume_option3_continue():
    """Verify responding with 'continue' resumes original paused tool call."""
    agent = OllamaAgent()
    engine = SpaceVGraphEngine(agent=agent)

    agent.active_paused_frame = {
        "tool": "browse_interactive_dom",
        "args": {"url": "https://github.com/unclecode/crawl4ai"},
        "diagnosis": {"category": "BROWSER_RUNTIME_FAILURE"},
        "remediation_options": [
            {"index": 1, "name": "Auto-Install", "action": "playwright install"},
            {"index": 2, "name": "Alternative", "tool": "read_web_page"},
            {"index": 3, "name": "Manual Takeover"}
        ],
        "user_prompt": "check crawl4ai"
    }

    state = {
        "user_prompt": "continue",
        "messages": [],
        "fast_path_result": None,
        "tool_calls": [],
        "tool_results": [],
        "active_window": "",
        "stuck_detected": False,
        "clarification_question": None,
        "final_response": "",
        "iteration": 0,
        "is_complete": False,
        "healing_attempts": 0,
        "last_error": None,
        "scratchpad": {}
    }

    res = engine._fast_router_node(state)
    assert res.get("tool_calls") is not None
    assert res["tool_calls"][0]["function"]["name"] == "browse_interactive_dom"
    assert agent.active_paused_frame is None
    assert engine._route_after_fast_router(res) == "direct_tools"
