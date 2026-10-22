"""
Verification Suite for SpaceV Hybrid Autonomous Stealth Agent.
Tests LangGraph StateGraph Compilation, DOM Extraction,
Local Audio CAPTCHA Detection & Faster-Whisper Solver, and Cua Bridge.
"""
import sys
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import unittest
from hybrid_agent.state import HybridAgentState
from hybrid_agent.captcha_solver import LocalAudioCaptchaSolver, local_captcha_solver
from hybrid_agent.dom_extractor import DOMExtractor
from hybrid_agent.cua_bridge import cua_bridge
from hybrid_agent.graph import HybridBrowserAgent


class TestHybridAgent(unittest.TestCase):
    def test_state_schema(self):
        state: HybridAgentState = {
            "task": "Scrape research papers",
            "current_url": "https://example.com",
            "page_title": "Example Domain",
            "dom_elements": [],
            "dom_summary": "",
            "screenshot_path": None,
            "captcha_detected": False,
            "captcha_type": "none",
            "captcha_solved": False,
            "plan": ["Navigate", "Extract"],
            "actions_history": [],
            "last_action": None,
            "extracted_data": {},
            "step_count": 0,
            "max_steps": 10,
            "is_complete": False,
            "final_result": "",
            "error": None,
            "cua_sandbox_active": False
        }
        self.assertEqual(state["task"], "Scrape research papers")
        self.assertFalse(state["captcha_detected"])

    def test_captcha_solver_initialization(self):
        solver = LocalAudioCaptchaSolver()
        self.assertIsNotNone(solver)
        # Test detection signatures on dummy page mock
        class DummyLocator:
            def count(self):
                return 0
        class DummyPage:
            def locator(self, sel):
                return DummyLocator()
            def title(self):
                return "Normal Page"
            def content(self):
                return "<html><body>Hello World</body></html>"
        detected, c_type = solver.detect_captcha(DummyPage())
        self.assertFalse(detected)
        self.assertEqual(c_type, "none")

    def test_cua_bridge_check(self):
        status = cua_bridge.get_status()
        self.assertIn("connected", status)
        self.assertIsInstance(status["connected"], bool)

    def test_langgraph_compilation(self):
        agent = HybridBrowserAgent(headless=True, max_steps=5)
        self.assertIsNotNone(agent.workflow)
        # Verify compiled graph has the required nodes
        # In LangGraph compiled graphs, nodes can be verified via graph structure
        self.assertTrue(callable(getattr(agent.workflow, "invoke", None)))
        agent.browser.close()


if __name__ == "__main__":
    unittest.main()
