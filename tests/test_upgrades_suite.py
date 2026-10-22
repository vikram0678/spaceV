"""
Comprehensive Verification Test Suite for SpaceV Upgraded Architecture.
Validates integrations inspired by Harness², Browser-Use, Crawl4AI, and Langflow/LFX.
"""

import time
from pathlib import Path

from spacev.control_plane.macro_controller import MacroAction, MacroController
from spacev.harness.experience_library import ExperienceLibrary, OperationalLesson
from spacev.harness.middleware import ObservationSanitizerMiddleware
from spacev.harness.propose_probe_compose import (
    ProbeCandidate,
    ProposeProbeComposeEngine,
)
from spacev.safety.antibot_detector import AntiBotDetector
from spacev.services.registry import AdapterRegistry, ServiceType, register_adapter
from spacev.services.telemetry import WorkflowTelemetry
from spacev.web.cdp_bridge import CDPBridge
from spacev.web.content_extractor import ContentExtractor
from spacev.web.dom_filter import DOMElement, PaintOrderFilter


# ---------------------------------------------------------------------------
# 1. Anti-Bot Heuristic Detection Tests (Crawl4AI)
# ---------------------------------------------------------------------------
def test_antibot_detector_tier1_cloudflare():
    cf_payload = """
    <html><head><title>Just a moment</title></head>
    <body>
    <form id="challenge-form" action="/login?__cf_chl_f_tk=AbC123xyz">
    <span class="cf-error-code">1020</span>
    </form>
    </body></html>
    """
    res = AntiBotDetector.analyze(cf_payload, status_code=200)
    assert res.is_blocked is True
    assert res.provider == "Cloudflare"
    assert res.tier == 1
    assert res.action == "rotate_stealth_profile"


def test_antibot_detector_tier1_akamai():
    akamai_payload = "<html><body>Reference # 18.2d351ab8.1557333295.a4e16ab Pardon Our Interruption</body></html>"
    res = AntiBotDetector.analyze(akamai_payload, status_code=403)
    assert res.is_blocked is True
    assert res.provider == "Akamai"
    assert res.tier == 1


def test_antibot_detector_tier2_access_denied():
    short_err = "<html><body><h1>Access Denied</h1><p>You don't have permission.</p></body></html>"
    res = AntiBotDetector.analyze(short_err, status_code=403)
    assert res.is_blocked is True
    assert res.tier == 2


def test_antibot_detector_performance_under_5ms():
    sample = "<html>" + ("<div>safe content</div>" * 500) + "</html>"
    start = time.perf_counter()
    res = AntiBotDetector.analyze(sample, status_code=200)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    assert res.is_blocked is False
    assert elapsed_ms < 5.0  # Must be sub-5ms


# ---------------------------------------------------------------------------
# 2. Paint-Order & Viewport DOM Pruning Tests (Browser-Use)
# ---------------------------------------------------------------------------
def test_paint_order_pruning():
    flt = PaintOrderFilter(viewport_width=1920, viewport_height=1080)
    elements = [
        DOMElement(index=1, tag="button", text="Visible Button", bounds={"x": 100, "y": 100, "w": 80, "h": 30}),
        DOMElement(index=2, tag="div", text="Hidden Display", computed_styles={"display": "none"}, bounds={"x": 100, "y": 150, "w": 80, "h": 30}),
        DOMElement(index=3, tag="div", text="Hidden Opacity", computed_styles={"opacity": "0"}, bounds={"x": 100, "y": 200, "w": 80, "h": 30}),
        DOMElement(index=4, tag="div", text="Off Viewport Below", bounds={"x": 100, "y": 3000, "w": 80, "h": 30}),
        DOMElement(index=5, tag="img", text="Tracking Pixel", bounds={"x": 0, "y": 0, "w": 1, "h": 1}),
        DOMElement(index=6, tag="input", text="", role="searchbox", bounds={"x": 200, "y": 50, "w": 200, "h": 35}),
    ]

    survivors = flt.prune_tree(elements)
    assert len(survivors) == 2
    assert [s.index for s in survivors] == [1, 6]

    prompt = flt.format_interactive_prompt(elements)
    assert '[1] <button> "Visible Button"' in prompt
    assert "[6] [searchbox]" in prompt


# ---------------------------------------------------------------------------
# 3. Multi-Action Macro Execution Tests (Browser-Use)
# ---------------------------------------------------------------------------
def test_macro_controller_batch_execution():
    actions = [
        MacroAction("click", target="[1]", duration_ms=5),
        MacroAction("type", target="[6]", value="SpaceV Automation", duration_ms=5),
        MacroAction("key", key="Enter", duration_ms=5),
    ]

    controller = MacroController()
    result = controller.execute_batch(actions)

    assert result.total_steps == 3
    assert result.successful_steps == 3
    assert result.all_success is True
    assert result.total_duration_ms < 100.0  # Fast sub-100ms batch


def test_macro_controller_early_failure_stop():
    def failing_executor(action: MacroAction) -> bool:
        return action.action_type != "type"

    actions = [
        MacroAction("click", target="[1]", duration_ms=1),
        MacroAction("type", value="bad", duration_ms=1),
        MacroAction("key", key="Enter", duration_ms=1),
    ]

    controller = MacroController(action_executor=failing_executor)
    result = controller.execute_batch(actions)

    assert result.successful_steps == 1
    assert result.failed_steps == 1
    assert result.all_success is False
    assert len(result.step_results) == 2  # Third step was cancelled


# ---------------------------------------------------------------------------
# 4. High-Density LLM Markdown & Table Extractor Tests (Crawl4AI)
# ---------------------------------------------------------------------------
def test_content_extractor_markdown_and_tables():
    raw_html = """
    <html>
      <head><title>Financial Quarterly Overview</title></head>
      <body>
        <nav><a href="/home">Home</a><a href="/login">Login</a></nav>
        <script>console.log("analytics tracking");</script>
        <div id="cookie-banner">Accept cookies to continue</div>
        <h1>Financial Report Q3</h1>
        <p>Overall revenue grew by 15% year-over-year.</p>
        <table>
          <tr><th>Quarter</th><th>Revenue ($M)</th><th>Growth</th></tr>
          <tr><td>Q1</td><td>105.4</td><td>+8%</td></tr>
          <tr><td>Q2</td><td>114.2</td><td>+11%</td></tr>
          <tr><td>Q3</td><td>128.9</td><td>+15%</td></tr>
        </table>
        <footer>Copyright 2026 SpaceV Corp. All rights reserved.</footer>
      </body>
    </html>
    """

    res = ContentExtractor.to_clean_markdown(raw_html)
    assert res.title == "Financial Quarterly Overview"
    assert "analytics tracking" not in res.markdown
    assert "Accept cookies" not in res.markdown
    assert "Copyright 2026" not in res.markdown
    assert "| Quarter | Revenue ($M) | Growth |" in res.markdown
    assert "| Q3 | 128.9 | +15% |" in res.markdown
    assert res.tables_found == 1
    assert res.compression_ratio > 0.40  # Significant token savings


# ---------------------------------------------------------------------------
# 5. Experience Library Tests (Harness²)
# ---------------------------------------------------------------------------
def test_experience_library_lifecycle(tmp_path: Path):
    lib = ExperienceLibrary(root_dir=tmp_path / "app_library")

    lesson1 = OperationalLesson(
        task_id="excel_pivot_export",
        cue="Excel macro dialog freezes on export",
        lesson="Send ESC key before calling COM Dispatch to dismiss background dialog.",
        evidence="Run hash: f89a712e9, solved in 12ms",
        confidence=0.98,
        category="excel",
    )
    lib.record_lesson("excel", lesson1)

    index_file = tmp_path / "app_library" / "excel" / "INDEX.md"
    assert index_file.is_file()
    index_text = index_file.read_text(encoding="utf-8")
    assert "excel_pivot_export" in index_text
    assert "Excel macro dialog freezes on export" in index_text

    # Retrieval test
    retrieved = lib.retrieve_relevant_lessons("excel", "How to resolve dialog freezes in Excel?")
    assert len(retrieved) == 1
    assert retrieved[0].task_id == "excel_pivot_export"
    assert "Send ESC key" in retrieved[0].lesson


# ---------------------------------------------------------------------------
# 6. Propose–Probe–Compose Self-Healing Tests (Harness²)
# ---------------------------------------------------------------------------
def test_propose_probe_compose_contrastive_resolution(tmp_path: Path):
    lib = ExperienceLibrary(root_dir=tmp_path / "test_lib")
    engine = ProposeProbeComposeEngine(library=lib)

    probe_a = ProbeCandidate(
        candidate_id="probe_gui_click",
        description="Click element by ID directly",
        action_fn=lambda: False,  # Simulates failure
        expected_outcome="Element clicked",
    )

    probe_b = ProbeCandidate(
        candidate_id="probe_com_shortcut",
        description="Invoke COM object SaveAs directly",
        action_fn=lambda: True,  # Simulates success
        expected_outcome="Workbook saved",
    )

    plan = engine.heal_failure(
        domain="excel",
        task_id="save_corrupt_sheet",
        failure_signature="ElementNotInteractableException on Save button",
        candidates=[probe_a, probe_b],
    )

    assert plan.resolved is True
    assert plan.winning_candidate_id == "probe_com_shortcut"
    assert plan.probes_run == 2
    assert "probe_com_shortcut" in plan.lesson.lesson


# ---------------------------------------------------------------------------
# 7. Pluggable Services & Adapter Registry Tests (Langflow LFX)
# ---------------------------------------------------------------------------
def test_pluggable_adapter_registry():
    AdapterRegistry.clear()

    @register_adapter(ServiceType.LLM, "ollama_local")
    class MockOllamaAdapter:
        def __init__(self, endpoint="http://localhost:11434"):
            self.endpoint = endpoint

        def generate(self, prompt: str) -> str:
            return f"Ollama response to: {prompt}"

    @register_adapter(ServiceType.TTS, "piper_edge")
    class MockPiperTTS:
        def synthesize(self, text: str) -> bytes:
            return b"AUDIO_BYTES"

    assert "ollama_local" in AdapterRegistry.list_adapters(ServiceType.LLM)
    assert "piper_edge" in AdapterRegistry.list_adapters(ServiceType.TTS)

    inst1 = AdapterRegistry.get_instance(ServiceType.LLM, "ollama_local")
    inst2 = AdapterRegistry.get_instance(ServiceType.LLM, "ollama_local")
    assert inst1 is inst2  # Singleton caching verification
    assert inst1.generate("ping") == "Ollama response to: ping"


# ---------------------------------------------------------------------------
# 8. Workflow Telemetry Stream Tests (Langflow LFX)
# ---------------------------------------------------------------------------
def test_workflow_telemetry_events():
    telem = WorkflowTelemetry()
    events_captured = []

    telem.subscribe(lambda e: events_captured.append(e))

    telem.start_node("perception_node", {"source": "screen"})
    time.sleep(0.01)
    duration = telem.finish_node("perception_node", {"elements": 12})
    telem.record_tool_call("click_tool", {"index": 4}, duration_ms=4.2, success=True)

    assert len(events_captured) == 3
    assert events_captured[0].event_type == "node_start"
    assert events_captured[1].event_type == "node_finish"
    assert events_captured[1].duration_ms >= 9.0
    assert events_captured[2].event_type == "tool_call"
    assert events_captured[2].metadata["success"] is True


# ---------------------------------------------------------------------------
# 9. In-the-Loop Middleware Sanitizer Tests (Harness²)
# ---------------------------------------------------------------------------
def test_observation_sanitizer_middleware():
    sanitizer = ObservationSanitizerMiddleware(max_chars=300, max_lines=10)

    # 1. Repetitive lines
    noisy_output = "\n".join(["Building module..."] * 20)
    cleaned, truncated = sanitizer.sanitize("bash", noisy_output)
    assert "[Repeated lines suppressed]" in cleaned

    # 2. Huge character dump
    huge_output = "X" * 1000
    cleaned_chars, truncated_chars = sanitizer.sanitize("cat_file", huge_output)
    assert len(cleaned_chars) <= 360
    assert truncated_chars is True


# ---------------------------------------------------------------------------
# 10. CDP Remote Port Bridge Target Test (Browser-Use)
# ---------------------------------------------------------------------------
def test_cdp_bridge_safe_handling():
    bridge = CDPBridge(port=9999)  # Port not open
    assert bridge.is_browser_available() is False
    assert bridge.get_version() is None
    assert bridge.list_targets() == []
    assert bridge.get_active_page() is None
