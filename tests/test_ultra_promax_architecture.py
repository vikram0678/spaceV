"""
Unit and Integration Tests for SpaceV Ultra-Promax Architecture.
Validates:
1. Universal Cloud Brain Client & Model Selection
2. Cloudflare Code Mode & Tool Virtualization Engine
3. Crawl4AI-Style Semantic HTML Distiller
4. Cryptographic Action Authority & Single-Use Tokens
5. Karpathy Goal-Driven Verification
"""
import pytest
from core.cloud_client import UniversalBrainClient
from core.code_mode import CodeModeEngine, CODE_MODE_META_TOOLS
from tools.semantic_distiller import distill_html_to_markdown
from core.action_authority import ActionAuthority
from core.karpathy_verifier import KarpathyVerifier


def test_universal_brain_model_selection():
    """Verifies dynamic model routing based on task intent."""
    client = UniversalBrainClient()

    # Coding task -> CODING_ENGINEER_MODEL
    model_code = client.select_cloud_model("Write a python script to test my bash pipeline")
    assert "poolside" in model_code or "laguna" in model_code or "code" in model_code

    # GUI task -> AUTONOMOUS_AGENT_MODEL
    model_gui = client.select_cloud_model("Click the button on my screen in the desktop browser")
    assert "nemotron" in model_gui or "super-vl" in model_gui

    # Fast chat -> FAST_CHAT_CLOUD_MODEL
    model_fast = client.select_cloud_model("Good morning, how are you?", requires_tools=False)
    assert "gemma" in model_fast


def test_code_mode_engine_dynamic_discovery():
    """Verifies that CodeModeEngine searches tool signatures on demand without token bloat."""
    engine = CodeModeEngine()

    # Search for file capabilities
    results = engine.search_tools("create file document")
    assert len(results) > 0
    tool_names = [r.get("name") for r in results]
    assert any("file" in name for name in tool_names)

    # Search for sandboxed workflow capabilities
    sandbox_results = engine.search_tools("sandboxed workflow execution")
    assert len(sandbox_results) > 0
    sandbox_names = [r.get("name") for r in sandbox_results]
    assert any("sandbox" in name for name in sandbox_names)


def test_code_mode_script_execution_sandbox():
    """Verifies in-process sandboxed Python execution for batch tool calls."""
    engine = CodeModeEngine()
    script = """
x = [1, 2, 3, 4]
total = sum(x)
print(f"Computed total: {total}")
"""
    res = engine.execute_script(script)
    assert res["status"] == "success"
    assert "Computed total: 10" in res["output"]


def test_semantic_distiller_noise_removal():
    """Verifies that raw HTML with scripts, styles, and SVG is stripped down to clean Markdown."""
    noisy_html = """
    <html>
      <head>
        <script>var tracker = 12345;</script>
        <style>.ads { color: red; }</style>
      </head>
      <body>
        <nav><a href="/home">Home</a><a href="/login">Login</a></nav>
        <div class="cookie-banner">Please accept all cookies to continue.</div>
        <main>
          <h1>SpaceV Core System</h1>
          <p>SpaceV is an autonomous cybernetic desktop assistant.</p>
          <svg><path d="M0,0 L10,10"/></svg>
        </main>
        <footer>Copyright 2026 SpaceV Inc.</footer>
      </body>
    </html>
    """
    distilled = distill_html_to_markdown(noisy_html)

    # Content must contain core information
    assert "SpaceV Core System" in distilled
    assert "autonomous cybernetic desktop assistant" in distilled

    # Noisy tags must be removed
    assert "var tracker" not in distilled
    assert "cookie-banner" not in distilled
    assert "Please accept all cookies" not in distilled
    assert "svg" not in distilled.lower()


def test_action_authority_single_use_and_window_validation():
    """Verifies cryptographic single-use capture_id enforcement and window matching."""
    authority = ActionAuthority(validity_window_sec=5.0)

    # Register observation
    elements = [{"id": 1, "name": "SubmitButton"}, {"id": 2, "name": "CancelButton"}]
    token = authority.register_observation(window_title="Calculator", elements=elements)
    assert token.startswith("cap_")

    # Authorize action (First time -> Must succeed)
    auth1 = authority.authorize_action(capture_id=token, element_id=1, expected_window="Calculator")
    assert auth1["authorized"] is True
    assert auth1["element"]["name"] == "SubmitButton"

    # Re-using the same token -> Must be rejected (single-use enforcement)
    auth2 = authority.authorize_action(capture_id=token, element_id=1, expected_window="Calculator")
    assert auth2["authorized"] is False
    assert "already been consumed" in auth2["error"]


def test_action_authority_rejects_window_mismatch():
    """Verifies that actions targeting the wrong window are immediately rejected."""
    authority = ActionAuthority(validity_window_sec=5.0)
    token = authority.register_observation(window_title="Google Chrome", elements=[{"id": 1, "name": "Tab"}])

    auth = authority.authorize_action(capture_id=token, element_id=1, expected_window="Visual Studio Code")
    assert auth["authorized"] is False
    assert "Target window mismatch" in auth["error"]


def test_karpathy_verifier_destructive_detection():
    """Verifies that high-risk destructive commands trigger confirmation flags."""
    verifier = KarpathyVerifier()

    # Destructive rm -rf
    check_bad = verifier.audit_intent_safety("bash", "rm -rf /")
    assert check_bad["safe"] is False
    assert check_bad["requires_confirmation"] is True

    # Safe command
    check_good = verifier.audit_intent_safety("bash", "ls -la reports/")
    assert check_good["safe"] is True
    assert check_good["requires_confirmation"] is False


def test_karpathy_verifier_goal_loop():
    """Verifies empirical goal-driven verification loop."""
    verifier = KarpathyVerifier()
    counter = 0

    def mock_test():
        nonlocal counter
        counter += 1
        return counter >= 2  # Succeeds on attempt 2

    res = verifier.verify_goal_backward("Generate Report File", mock_test, max_attempts=3)
    assert res["verified"] is True
    assert res["attempts"] == 2
