"""
Comprehensive tests for Phase 3 (Stealth Browser Supervisor & Crawl4AI Fallback),
Phase 4 (Celesto Fleet Containment & Snapshot Rollback), and
The 3-Step Fail-Safe Reflex (OmniParser UIA -> Hotkey Fallback -> Clarification Guardrail).
"""
from unittest.mock import MagicMock, patch
import pytest

from hybrid_agent.stealth_browser import StealthBrowserController, ResilientBrowserSupervisor
from tools.scraper_tools import scrape_web_page_crawl4ai
from core.self_healing import self_healing_engine
from spacev.fleet.orchestrator import DetonationOrchestrator
from spacev.fleet.celesto_engine import CelestoSandboxInstance


# ============================================================================
# PHASE 3: STEALTH BROWSER DUAL-PLANE SUPERVISOR & CRAWL4AI FALLBACK
# ============================================================================

def test_stealth_browser_type_into_element_alias():
    """Verify type_into_element alias exists on StealthBrowserController."""
    ctrl = StealthBrowserController(headless=True)
    assert hasattr(ctrl, "type_into_element")
    assert ctrl.type_into_element == ctrl.type_element_by_index


def test_resilient_browser_supervisor_dual_plane_fallback():
    """Verify supervisor falls back to Crawl4AI when Playwright browser is offline."""
    supervisor = ResilientBrowserSupervisor(headless=True)
    
    with patch.object(StealthBrowserController, "page", property(lambda self: None)):
        with patch("tools.scraper_tools.scrape_web_page_crawl4ai") as mock_crawl:
            mock_crawl.return_value = "### Distilled Markdown Output from Crawl4AI"
            
            result = supervisor.navigate_or_fallback("https://example.com/test")
            assert mock_crawl.called
            assert "Distilled Markdown Output from Crawl4AI" in result


def test_scrape_web_page_crawl4ai_clean_markdown():
    """Verify scrape_web_page_crawl4ai parses HTML and strips clutter."""
    mock_html = """
    <html>
      <head><script>alert('noise');</script><style>.ad{color:red;}</style></head>
      <body>
        <nav><a href='/home'>Home</a></nav>
        <main>
          <h1>SpaceV Architecture</h1>
          <p>Autonomous Cybernetic Control Plane for Workstations.</p>
        </main>
        <footer>Copyright 2026 SpaceV</footer>
      </body>
    </html>
    """
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.read.return_value = mock_html.encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        markdown = scrape_web_page_crawl4ai("https://spacev.ai/docs")
        assert "SpaceV Architecture" in markdown
        assert "Autonomous Cybernetic Control Plane for Workstations." in markdown
        assert "alert('noise')" not in markdown
        assert "Copyright 2026" not in markdown


# ============================================================================
# THE 3-STEP FAIL-SAFE REFLEX (CONFUSION & UNKNOWN SYMBOLS)
# ============================================================================

def test_fail_safe_tier2_hotkey_accelerator_fallback():
    """
    Verify Tier 2: When visual clicking on a common action (e.g. 'close', 'save', 'search')
    fails, the self-healing engine automatically switches to deterministic OS hotkeys.
    """
    diag = {
        "category": "UI_ELEMENT_NOT_FOUND",
        "tool": "gui_click_text",
        "args": {"target_text": "close"},
        "locus": "close",
        "original_error": "Could not visually locate 'close' on your screen."
    }
    
    can_heal, new_tool, new_args, msg = self_healing_engine.attempt_remediation(diag, attempt_number=0)
    assert can_heal is True
    assert new_tool == "gui_press_hotkey"
    assert new_args == {"keys": ["alt", "f4"]}
    assert "alt+f4" in msg.lower()


def test_fail_safe_tier2_save_hotkey():
    """Verify clicking 'save' falls back to Ctrl+S."""
    diag = {
        "category": "UI_ELEMENT_NOT_FOUND",
        "tool": "gui_click_control",
        "args": {"target_name": "save"},
        "locus": "save",
        "original_error": "Control 'save' not found in accessibility tree."
    }
    can_heal, new_tool, new_args, msg = self_healing_engine.attempt_remediation(diag, attempt_number=0)
    assert can_heal is True
    assert new_tool == "gui_press_hotkey"
    assert new_args == {"keys": ["ctrl", "s"]}


def test_fail_safe_tier3_clarification_guardrail_on_exhaustion():
    """
    Verify Tier 3: When self-healing attempts are exhausted, the agent halts cleanly
    and produces an Interactive Remediation Card rather than guessing or clicking randomly.
    """
    diag = {
        "category": "UI_ELEMENT_NOT_FOUND",
        "tool": "gui_click_icon",
        "args": {"target_description": "unknown_custom_glyph_32"},
        "locus": "unknown_custom_glyph_32",
        "original_error": "Could not visually locate unknown icon."
    }
    can_heal, new_tool, new_args, msg = self_healing_engine.attempt_remediation(diag, attempt_number=2)
    assert can_heal is False
    assert new_tool is None
    assert "Exhausted" in msg

    # Format the clarification card
    card = self_healing_engine.format_clarification_card(diag)
    assert "SpaceV Live Clarification & Remediation Protocol" in card
    assert "unknown_custom_glyph_32" in card
    assert "Sir, how would you prefer me to proceed?" in card


# ============================================================================
# PHASE 4: CELESTO FLEET CONTAINMENT & SNAPSHOT ROLLBACK
# ============================================================================

def test_celesto_sandbox_snapshot_and_rollback():
    """Verify Celesto sandbox snapshot capture and rollback in microVM driver."""
    sbx = CelestoSandboxInstance(name="sbx-unittest01", network_mode="off")
    try:
        # Snapshot at step 6
        assert sbx.snapshot("snap-clean-state") is True
        assert "snap-clean-state" in sbx.snapshots

        # Mutate state
        sbx.state = "compromised"

        # Rollback to step 6
        assert sbx.rollback("snap-clean-state") is True
        assert sbx.state == "ready"
    finally:
        sbx.close()
        assert sbx.state == "deleted"


def test_detonation_orchestrator_10_step_pipeline_with_rollback():
    """
    Verify the complete 10-step detonation pipeline:
    Step 6 snapshot -> Step 7 attack blocked & crash -> Step 7 rollback -> Step 8 verify -> Step 10 cleanup.
    """
    orchestrator = DetonationOrchestrator(sandbox_name="sbx-deton002")
    res = orchestrator.execute_pipeline()
    
    assert res["status"] == "success"
    assert res["attack_contained"] is True
    assert res["policy_applied"] == "rollback"
    assert res["steps_completed"] == 10
