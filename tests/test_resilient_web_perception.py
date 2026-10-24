"""
Industrial Verification Suite for SpaceV Resilient Web Perception & Extraction.
Tests the Crawl4AI dual-engine content cascade, stealth browser hardening,
and self-healing browser failover without relying on live external networks.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.self_healing import SelfHealingEngine, self_healing_engine
from hybrid_agent.stealth_browser import StealthBrowserController
from tools.registry import OLLAMA_TOOLS_SCHEMA, TOOL_ALIASES, TOOL_FUNCTIONS, execute_tool
from tools.schemas import PYDANTIC_TOOL_MODELS
from tools.web_tools import browse_interactive_dom, browse_website_stealth, fetch_github_repo_summary, read_web_page


class TestGitHubFastPathAndSemanticDistiller:
    """Tests the Crawl4AI-grade zero-browser GitHub and Web distillation."""

    def test_fetch_github_repo_summary_parsing(self):
        """Verifies GitHub repo URL pattern extraction and README fetching."""
        mock_meta = b'{"description": "Fast Web Crawler for LLMs", "stargazers_count": 25000, "forks_count": 2000, "language": "Python", "topics": ["ai", "scraper"]}'
        mock_readme = b"# Crawl4AI\n\nCrawl4AI is an open-source, LLM-friendly web crawler designed for AI agents."

        def mock_urlopen(req, timeout=8):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            resp = MagicMock()
            if "api.github.com" in url:
                resp.read.return_value = mock_meta
            else:
                resp.read.return_value = mock_readme
            resp.__enter__.return_value = resp
            return resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            res = fetch_github_repo_summary("https://github.com/unclecode/crawl4AI")
            assert res is not None
            assert "unclecode/crawl4AI" in res
            assert "Fast Web Crawler for LLMs" in res
            assert "Crawl4AI is an open-source, LLM-friendly web crawler" in res

    def test_read_web_page_github_fast_path(self):
        """read_web_page must prioritize GitHub fast path for github.com URLs."""
        with patch("tools.web_tools.fetch_github_repo_summary", return_value="### Mocked Crawl4AI Repo Overview"):
            output = read_web_page("https://github.com/unclecode/crawl4AI")
            assert "=== Distilled Repository Content ===" in output
            assert "Mocked Crawl4AI Repo Overview" in output

    def test_read_web_page_general_http_fallback(self):
        """read_web_page extracts readable content from standard HTML websites."""
        sample_html = b"<html><head><title>Test Page</title></head><body><h1>Welcome to SpaceV</h1><p>Cybernetic automation active.</p></body></html>"
        resp = MagicMock()
        resp.read.return_value = sample_html
        resp.__enter__.return_value = resp

        with patch("urllib.request.urlopen", return_value=resp):
            out = read_web_page("https://example.com/docs")
            assert "=== Distilled Content from https://example.com/docs ===" in out
            assert "SpaceV" in out or "Cybernetic" in out or "Welcome" in out


class TestStealthBrowserHardening:
    """Tests that missing Playwright binaries or display failures never raise NoneType.goto."""

    def test_stealth_browser_is_available_and_none_safe(self):
        ctrl = StealthBrowserController(headless=True)
        # Mock Playwright missing or throwing on launch
        with patch.object(ctrl, "start", return_value=None):
            assert ctrl.is_available() is False
            with pytest.raises(RuntimeError, match="Stealth browser engine is offline"):
                ctrl.navigate("https://example.com")

    def test_browse_interactive_dom_cascades_to_semantic_reader_on_browser_offline(self):
        """browse_interactive_dom must fall back to read_web_page when browser is offline."""
        with patch("tools.web_tools._get_stealth_controller", return_value=None):
            with patch("tools.web_tools.read_web_page", return_value="=== Distilled Fallback Markdown ===") as mock_reader:
                res = browse_interactive_dom("https://github.com/unclecode/crawl4AI")
                mock_reader.assert_called_once_with("https://github.com/unclecode/crawl4AI")
                assert res == "=== Distilled Fallback Markdown ==="

    def test_browse_website_stealth_degrades_gracefully_on_navigation_error(self):
        """browse_website_stealth catches any launch/navigate exceptions and returns Crawl4AI content."""
        mock_ctrl = MagicMock()
        mock_ctrl.navigate.side_effect = RuntimeError("Playwright binary not installed")
        mock_ctrl.is_available.return_value = True

        with patch("tools.web_tools._get_stealth_controller", return_value=mock_ctrl):
            with patch("tools.web_tools.read_web_page", return_value="=== Fallback Repo Content ==="):
                res = browse_website_stealth("https://github.com/unclecode/crawl4AI")
                assert "Stealth Browser Degraded" in res
                assert "Fallback Repo Content" in res


class TestSelfHealingBrowserFailureRemediation:
    """Verifies that the SelfHealingEngine catches browser crashes and mutates tool calls."""

    def test_diagnose_browser_runtime_failure(self):
        err = "Stealth navigation failed ('NoneType' object has no attribute 'goto'), opening in standard browser"
        diagnosis = SelfHealingEngine.diagnose_failure(
            "browse_interactive_dom",
            {"url": "https://github.com/unclecode/crawl4AI"},
            err
        )
        assert diagnosis["category"] == "BROWSER_RUNTIME_FAILURE"
        assert diagnosis["strategy"] == "fallback_to_semantic_reader"

    def test_attempt_remediation_mutates_to_read_web_page(self):
        diagnosis = {
            "category": "BROWSER_RUNTIME_FAILURE",
            "tool": "browse_interactive_dom",
            "args": {"url": "https://github.com/unclecode/crawl4AI"},
            "explanation": "Interactive browser engine encountered a runtime failure"
        }
        can_heal, new_tool, new_args, msg = self_healing_engine.attempt_remediation(diagnosis, 0)
        assert can_heal is True
        assert new_tool == "read_web_page"
        assert new_args == {"url": "https://github.com/unclecode/crawl4AI"}
        assert "Degraded to Crawl4AI semantic reader" in msg


class TestToolRegistryAndPydanticSchemaParity:
    """Verifies full registry, alias, and Pydantic schema declaration for read_web_page."""

    def test_read_web_page_registered_in_registry_and_aliases(self):
        assert "read_web_page" in TOOL_FUNCTIONS
        assert "read_web" in TOOL_ALIASES
        assert "read_url" in TOOL_ALIASES
        assert "fetch_web_page" in TOOL_ALIASES
        assert "read_web_page" in PYDANTIC_TOOL_MODELS

    def test_read_web_page_schema_in_ollama_tools_schema(self):
        schemas = [f["function"]["name"] for f in OLLAMA_TOOLS_SCHEMA if "function" in f]
        assert "read_web_page" in schemas

    def test_execute_tool_read_web_page_with_pydantic_validation(self):
        with patch.dict(TOOL_FUNCTIONS, {"read_web_page": MagicMock(return_value="=== Distilled Content ===")}):
            res = execute_tool("read_web", {"link": "https://github.com/unclecode/crawl4AI"})
            assert res == "=== Distilled Content ==="

