"""
Unit and integration tests for zero-click display brightness control,
HostBridge WSL click dispatching, and truth-preserving self-healing escalation.
"""
from unittest.mock import MagicMock, patch
import pytest

from core.fast_router import FastRouter
from core.host_bridge import HostBridge
from core.graph_engine import sanitize_speech_output, SpaceVGraphEngine
from tools.system_tools import set_system_brightness
from tools.registry import TOOL_FUNCTIONS, OLLAMA_TOOLS_SCHEMA


def test_set_system_brightness_in_registry():
    """Verify set_system_brightness is registered with schema."""
    assert "set_system_brightness" in TOOL_FUNCTIONS
    schema_names = [f["function"]["name"] for f in OLLAMA_TOOLS_SCHEMA]
    assert "set_system_brightness" in schema_names


def test_set_system_brightness_execution():
    """Verify set_system_brightness clamps level and executes without error."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = ""
        
        res = set_system_brightness(50)
        assert "50%" in res
        
        # Test boundary clamping
        res_high = set_system_brightness(150)
        assert "100%" in res_high
        
        res_low = set_system_brightness(-20)
        assert "0%" in res_low


def test_fast_router_brightness_intents():
    """Verify natural language brightness commands route directly to set_system_brightness."""
    queries = [
        "open settings and decrease the brightness to 50%",
        "decrease the brightness to 50%",
        "set brightness to 70%",
        "lower brightness to 40%",
        "dim brightness",
        "boost brightness",
        "brightness 50"
    ]
    with patch("tools.system_tools.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""
        for q in queries:
            matched = FastRouter.match(q)
            assert matched is not None, f"Query '{q}' failed to match FastRouter"
            assert matched[0] == "set_system_brightness"
            assert "brightness" in matched[2].lower()


def test_sanitize_speech_output_anti_lie():
    """Verify sanitize_speech_output NEVER claims success when has_error is True."""
    # When text is empty and error occurred:
    reply_on_error = sanitize_speech_output("", has_error=True)
    assert "Action completed successfully" not in reply_on_error
    assert "roadblock" in reply_on_error.lower()
    
    # When text is empty and no error:
    reply_normal = sanitize_speech_output("", has_error=False)
    assert "Action completed successfully" in reply_normal


def test_route_after_tools_exhausted_healing():
    """Verify _route_after_tools routes to 'stuck' (not 'synthesize') when healing attempts are exhausted."""
    engine = SpaceVGraphEngine(agent=MagicMock())
    
    state = {
        "user_prompt": "open settings and decrease the brightness to 50%",
        "last_error": "Could not visually locate 'System' on your screen.",
        "healing_attempts": 2, # Exhausted (max 2)
        "stuck_detected": False,
        "tool_results": [{"name": "gui_click_icon", "args": {"target_description": "System"}, "result": "Failed"}]
    }
    
    route = engine._route_after_tools(state)
    assert route == "stuck", f"Expected 'stuck' but got '{route}'"
    assert state.get("stuck_detected") is True
    assert state.get("clarification_question") is not None
    assert "Roadblock Encountered" in state["clarification_question"] or "SpaceV" in state["clarification_question"]


def test_host_bridge_click_host_coordinate():
    """Verify HostBridge.click_host_coordinate generates correct PowerShell script."""
    with patch.object(HostBridge, "execute_powershell") as mock_ps:
        mock_ps.return_value = (0, "True", "")
        with patch.object(HostBridge, "is_wsl", return_value=True):
            res = HostBridge.click_host_coordinate(400, 300)
            assert res is True
            assert mock_ps.called
            ps_script = mock_ps.call_args[0][0]
            assert "SetCursorPos(400, 300)" in ps_script
            assert "mouse_event" in ps_script
