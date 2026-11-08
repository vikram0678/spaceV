"""
Unit & Integration Tests for CodeMode Sandbox Safe Imports, Batch Browser Tools,
and Error-Masking Prevention.
"""
from unittest.mock import MagicMock, patch
import pytest

from core.code_mode import code_mode_engine
from core.graph_engine import determine_tool_status, generate_tool_summary
from tools.registry import execute_tool_normalized
from tools.web_tools import open_browser_urls


def test_code_mode_allows_safe_imports():
    """Verify that csv, io, json, re, math, and time can be imported and executed inside sandbox."""
    script = """
import csv, io, json, re, math, time
raw_csv = "Title,Company\\nAI Engineer,Google\\nML Researcher,Anthropic"
reader = list(csv.DictReader(io.StringIO(raw_csv)))
payload = json.dumps({"count": len(reader), "first": reader[0]["Title"]})
print(f"OUTPUT:{payload}")
"""
    res = code_mode_engine.execute_script(script)
    assert res.get("status") == "success"
    assert "OUTPUT:{\"count\": 2, \"first\": \"AI Engineer\"}" in res.get("output", "")


def test_code_mode_blocks_dangerous_modules():
    """Verify that unauthorized modules like socket or ctypes are strictly blocked."""
    script = "import socket"
    res = code_mode_engine.execute_script(script)
    assert res.get("status") == "error"
    assert "restricted" in res.get("error", "").lower()


def test_determine_tool_status_detects_dictionary_error_envelopes():
    """Verify that stringified dict error envelopes are accurately classified as failed."""
    dict_err = {"status": "error", "error": "ImportError: __import__ not found"}
    assert determine_tool_status("spacev_execute_script", dict_err) == "failed"

    str_dict_err = "{'status': 'error', 'error': 'ImportError: __import__ not found'}"
    assert determine_tool_status("spacev_execute_script", str_dict_err) == "failed"


def test_generate_tool_summary_never_masks_error_as_success():
    """Verify that errors produce factual failure summaries rather than 'Executed {name}'."""
    tool_events = [{
        "name": "spacev_execute_script",
        "result": "{'status': 'error', 'error': 'ImportError: __import__ not found'}",
        "status": "failed",
    }]
    summary = generate_tool_summary(tool_events)
    assert "encountered an issue" in summary
    assert "Executed spacev_execute_script" not in summary


def test_graph_engine_never_reports_success_on_tool_error():
    """Verify Section 14.2 blueprint requirement: error status must never report execution success."""
    tool_events = [{
        "name": "spacev_execute_script",
        "status": "error",
        "result": {"status": "error", "error": "ImportError: __import__ not found"}
    }]
    summary = generate_tool_summary(tool_events)
    assert ("issue" in summary.lower() or "error" in summary.lower() or "failed" in summary.lower())
    assert "executed spacev_execute_script" not in summary.lower()


def test_open_browser_urls_list_and_string_parsing():
    """Verify open_browser_urls accepts lists and formatted strings."""
    with patch("core.platform_adapter.PlatformAdapter.open_url", return_value="Opened") as mock_open:
        # 1. Test list input
        res1 = open_browser_urls(["https://example.com/1", "https://example.com/2"], delay_sec=0.01)
        assert "Successfully opened 2 of 2" in res1
        assert mock_open.call_count == 2

        mock_open.reset_mock()

        # 2. Test string input
        res2 = open_browser_urls("https://example.com/3, https://example.com/4", delay_sec=0.01)
        assert "Successfully opened 2 of 2" in res2
        assert mock_open.call_count == 2


def test_open_browser_urls_normalized_tool_registry():
    """Verify tool execution via registry executes without error."""
    with patch("core.platform_adapter.PlatformAdapter.open_url", return_value="Opened"):
        res = execute_tool_normalized(
            "open_browser_urls",
            {"urls": ["https://turing.com/job1", "https://turing.com/job2"], "delay_sec": 0.01}
        )
        assert res.success is True
        assert "Successfully opened 2 of 2" in str(res.data)


def test_sanitize_url_tokens_strips_cloudflare_anti_bot_parameters():
    """Verify stale Cloudflare challenge tokens (__cf_chl_rt_tk) are cleanly stripped."""
    from tools.gui_tools import sanitize_url_tokens

    raw = "https://www.glassdoor.com/job-listing/j?jl=1010292826490&__cf_chl_rt_tk=Uv6x0ZoWz7hXrQJA2lwLFhTe88B9dm8uRJZxg2SA.1M-1793527523-1.0.1.1-vjrtUoTB6dbf8p4ROE0pX8gfjeSAcric90I.dhOeeFc"
    cleaned = sanitize_url_tokens(raw)
    assert "__cf_chl_rt_tk" not in cleaned
    assert "jl=1010292826490" in cleaned
    assert cleaned == "https://www.glassdoor.com/job-listing/j?jl=1010292826490"


def test_autonomous_cursor_mode_delegates_to_gui_open_browser_urls():
    """Verify that when Cursor Mode is active, open_browser_urls uses human GUI navigation."""
    from tools.gui_tools import safety

    orig_state = safety.autonomous_mode_enabled
    try:
        safety.autonomous_mode_enabled = True
        with patch("tools.gui_tools.gui_open_browser_urls", return_value="Human GUI Opened") as mock_gui:
            res = open_browser_urls(["https://example.com/job1"])
            assert res == "Human GUI Opened"
            assert mock_gui.call_count == 1
    finally:
        safety.autonomous_mode_enabled = orig_state


def test_gui_human_search_and_open_tool_registration():
    """Verify human-like Google search and click tool is properly registered."""
    from tools.registry import TOOL_FUNCTIONS, execute_tool_normalized

    mock_fn = MagicMock(return_value="Searched & Clicked")
    with patch.dict(TOOL_FUNCTIONS, {"gui_human_search_and_open": mock_fn}):
        res = execute_tool_normalized("gui_human_search_and_open", {"query": "AI Engineer Jobs"})
        assert res.success is True
        assert res.data == "Searched & Clicked"
        assert mock_fn.call_count == 1



def test_modal_interceptor_detects_chrome_profiles_dynamically():
    """Verify modal interceptor dynamically enumerates Chrome profiles without hardcoding."""
    from core.modal_interceptor import get_detected_chrome_profiles, modal_interceptor

    profiles = get_detected_chrome_profiles()
    # If Chrome Local State exists, verify profile structure universally
    if profiles:
        assert isinstance(profiles, list)
        for p in profiles:
            assert "display" in p
            assert "id" in p

    with patch.object(modal_interceptor, "inspect_active_window", return_value=("Who's using Chrome?", "chrome", "Chrome_WidgetWin_1")), \
         patch("core.modal_interceptor.get_detected_chrome_profiles", return_value=[{"id": "Default", "display": "Work", "name": "Work", "email": ""}, {"id": "Profile 1", "display": "Personal", "name": "Personal", "email": ""}]), \
         patch("core.memory.memory.get", return_value=None), \
         patch("core.memory.memory.get_preference", return_value=None):
        modal = modal_interceptor.detect()
        assert modal is not None
        assert modal.domain == "chrome"
        assert modal.property_key == "profile"
        assert "Who's using Chrome?" in modal.question
        assert len(modal.options) >= 2


def test_gui_human_search_and_open_stops_on_modal_blocker():
    """Verify gui_human_search_and_open halts immediately and returns modal blocker when profile selector appears."""
    from tools.gui_tools import gui_human_search_and_open

    with patch("tools.gui_tools.SafetyController.check", return_value=None), \
         patch("core.platform_adapter.PlatformAdapter.launch_app"), \
         patch("tools.gui_tools.resolve_chrome_profile_guard", return_value="⚠️ Modal Blocker: Which profile?"):
        res = gui_human_search_and_open("AI Engineer jobs Glassdoor")
        assert "Modal Blocker" in res
        assert "clicked the top organic result" not in res


def test_fast_router_asks_user_on_chrome_profile_modal():
    """Verify FastRouter returns modal_disambiguation instead of reporting fake success."""
    from core.fast_router import FastRouter

    with patch("tools.gui_tools.gui_human_search_and_open", return_value="⚠️ Modal Blocker: Which profile shall I open?"):
        match = FastRouter.match("search google for AI Engineer jobs Glassdoor and click the first result")
        assert match is not None
        action, payload, reply = match
        assert action == "modal_disambiguation"
        assert "Which profile shall I open?" in reply
        assert "Right away, Sir." not in reply


def test_fast_router_disambiguation_continuation_resumes_search():
    """Verify answering the disambiguation question saves preference and resumes search."""
    from core.fast_router import FastRouter
    from core.memory import memory

    memory.set_suspended_disambiguation({
        "domain": "chrome",
        "property_key": "profile",
        "question": "Which profile?",
        "options": [("👤 Primary Profile", "Profile 1"), ("👤 Secondary Profile", "Profile 2")],
        "suspended_task": "search google for AI Engineer jobs Glassdoor and click the first result",
        "timestamp": 123456789.0
    })

    with patch("tools.gui_tools.gui_human_search_and_open", return_value="Successfully clicked top job link!") as mock_search, \
         patch("core.platform_adapter.PlatformAdapter.launch_app"):
        match = FastRouter.match("1")
        assert match is not None
        action, opt_val, reply = match
        assert action == "resolve_disambiguation"
        assert opt_val == "Profile 1"
        assert "Saved **'👤 Primary Profile'** for Chrome" in reply
        assert "Successfully clicked top job link!" in reply
        assert memory.get_preference("chrome", "profile") == "Profile 1"
        assert memory.get_suspended_disambiguation() is None


def test_query_parser_isolates_clean_query_and_followup():
    """Verify parse_search_intent isolates pure query from platform and follow-up clauses."""
    from core.query_parser import parse_search_intent

    prompt = "search ml basic learn in the chrome and ask me which is better which link and source"
    clean_q, followup, meta = parse_search_intent(prompt)
    assert clean_q == "ml basic learn"
    assert "ask me which is better which link and source" in followup
    assert meta["has_comparison"] is True


def test_fast_router_ml_basic_learn_searches_clean_query_and_recommends_sources():
    """Verify ReflexGatekeeper routes complex comparison to brain, and FastRouter cleanly isolates queries."""
    from core.fast_router import FastRouter
    from core.reflex_gatekeeper import ReflexGatekeeper

    complex_prompt = "search ml basic learn in the chrome and ask me which is better which link and source"
    # 1. Complex prompt with analysis & question must bypass FastRouter to let LLM brain reason dynamically
    assert ReflexGatekeeper.should_bypass_fast_router(complex_prompt) is True

    # 2. Reflex prompt without follow-up noise is cleanly dispatched with ONLY pure target query
    pure_prompt = "search ml basic learn in the chrome"
    with patch("tools.web_tools.search_google") as mock_search:
        mock_search.return_value = "Opened Google search"
        match = FastRouter.match(pure_prompt)
        assert match is not None
        action, target_q, reply = match
        assert action == "search_google"
        assert target_q == "Opened Google search"
        # Search called with ONLY pure query, never leaking 'in the chrome'!
        mock_search.assert_called_with("ml basic learn")


def test_fast_router_source_selection_opens_chosen_url():
    """Verify selecting a recommended source opens that URL in the browser."""
    from core.fast_router import FastRouter
    from core.memory import memory

    memory.set_suspended_disambiguation({
        "domain": "web",
        "property_key": "selected_source",
        "question": "Which link?",
        "options": [
            ("1. Kaggle Learn", "https://www.kaggle.com/learn/intro-to-machine-learning"),
            ("2. Coursera", "https://www.coursera.org/specializations/machine-learning-introduction")
        ],
        "suspended_task": None,
        "timestamp": 123456789.0
    })

    with patch("tools.web_tools.open_url") as mock_open:
        mock_open.return_value = "Opened URL"
        match = FastRouter.match("1")
        assert match is not None
        action, opt_val, reply = match
        assert action == "open_url"
        assert opt_val == "https://www.kaggle.com/learn/intro-to-machine-learning"
        mock_open.assert_called_once_with("https://www.kaggle.com/learn/intro-to-machine-learning")
        assert "Opening **'1. Kaggle Learn'**" in reply
