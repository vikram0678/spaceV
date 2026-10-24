"""
Tests for Autonomous Task Execution & Anti-Hallucination Governance (SpaceV).
Validates:
1. Atomic code block execution (Python/Bash) with output capture & containment.
2. Anti-hallucination guard in graph engine routing.
3. Local file URI handling and argument auto-correction in read_web_page.
4. Self-healing path resolution across /tmp and /tmp/test.
5. Elimination of remediation card deadlocks on generic errors.
"""
import os
import tempfile
from pathlib import Path

from core.graph_engine import SpaceVGraphEngine
from core.ollama_client import OllamaAgent
from core.self_healing import self_healing_engine
from tools.system_tools import execute_code_block
from tools.web_tools import read_web_page


def test_execute_code_block_python_reverse_number():
    """Verify execute_code_block executes Python code and captures output."""
    code = (
        "num = 12345\n"
        "reversed_num = int(str(num)[::-1])\n"
        "print(f'OUTPUT: {reversed_num}')\n"
    )
    res = execute_code_block(language="python", code=code)
    assert "Exit Code: 0" in res
    assert "OUTPUT: 54321" in res


def test_execute_code_block_with_stdin():
    """Verify execute_code_block provides stdin input correctly."""
    code = (
        "import sys\n"
        "val = sys.stdin.read().strip()\n"
        "print(f'REVERSED: {val[::-1]}')\n"
    )
    res = execute_code_block(language="python", code=code, input_data="98765\n")
    assert "Exit Code: 0" in res
    assert "REVERSED: 56789" in res


def test_execute_code_block_bash():
    """Verify execute_code_block executes bash commands."""
    code = "echo 'TEST_BASH_EXEC_SUCCESS'"
    res = execute_code_block(language="bash", code=code)
    assert "Exit Code: 0" in res
    assert "TEST_BASH_EXEC_SUCCESS" in res


def test_execute_code_block_containment_audit():
    """Verify Celesto Gatekeeper blocks dangerous payload inside code block."""
    dangerous_code = "pip install untrusted-pypi-package"
    res = execute_code_block(language="bash", code=dangerous_code)
    assert "AUTO-CONTAINED" in res or "Containment Gate" in res


def test_read_web_page_file_uri_direct_read():
    """Verify read_web_page resolves file:// URIs directly from disk without DNS/urllib errors."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("SPACEV_LOCAL_FILE_VERIFIED_CONTENT")
        tmp_path = f.name

    try:
        file_uri = f"file://{tmp_path}"
        res = read_web_page(url=file_uri)
        assert "SPACEV_LOCAL_FILE_VERIFIED_CONTENT" in res
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_read_web_page_misplaced_file_name_args():
    """Verify read_web_page delegates when invoked with file_name_or_path instead of url."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("print('hello from delegated file')")
        tmp_path = f.name

    try:
        # Simulate LLM passing file_name_or_path to read_web_page
        res = read_web_page(file_name_or_path=tmp_path)
        assert "hello from delegated file" in res
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_anti_hallucination_guard_extracts_markdown_code_block():
    """Verify graph engine converts model markdown code block to execute_code_block tool call."""
    agent = OllamaAgent()
    engine = SpaceVGraphEngine(agent=agent)

    state = {
        "user_prompt": "create reverse_number.py, run it and verify output is 54321",
        "messages": [],
        "tool_calls": [],
        "tool_results": [],
        "active_window": "",
        "stuck_detected": False,
        "clarification_question": None,
        "final_response": "Here is the script to reverse the number:\n```python\nn = 12345\nprint(int(str(n)[::-1]))\n```",
        "iteration": 0,
        "is_complete": False,
        "healing_attempts": 0,
        "last_error": None,
        "scratchpad": {}
    }

    route = engine._route_after_reasoning(state)
    assert route == "execute_tools"
    assert len(state["tool_calls"]) == 1
    t_call = state["tool_calls"][0]
    assert t_call["function"]["name"] == "execute_code_block"
    assert "12345" in t_call["function"]["arguments"]["code"]
    assert t_call["function"]["arguments"]["language"] == "python"


def test_anti_hallucination_guard_extracts_file_creation():
    """Verify graph engine converts imperative file creation command to create_file tool call."""
    agent = OllamaAgent()
    engine = SpaceVGraphEngine(agent=agent)

    state = {
        "user_prompt": "create recovery_test.txt containing OLD",
        "messages": [],
        "tool_calls": [],
        "tool_results": [],
        "active_window": "",
        "stuck_detected": False,
        "clarification_question": None,
        "final_response": "I have created recovery_test.txt containing OLD.",
        "iteration": 0,
        "is_complete": False,
        "healing_attempts": 0,
        "last_error": None,
        "scratchpad": {}
    }

    route = engine._route_after_reasoning(state)
    assert route == "execute_tools"
    assert len(state["tool_calls"]) == 1
    t_call = state["tool_calls"][0]
    assert t_call["function"]["name"] == "create_file"
    assert "recovery_test.txt" in t_call["function"]["arguments"]["file_name"]
    assert "OLD" in t_call["function"]["arguments"]["content"]


def test_self_healing_path_resolution_tmp():
    """Verify self-healing engine resolves missing files in /tmp and /tmp/test."""
    test_dir = Path("/tmp/test")
    test_dir.mkdir(parents=True, exist_ok=True)
    target_file = test_dir / "target_remediation_test.py"
    target_file.write_text("print('RESOLVED_OK')")

    try:
        diag = self_healing_engine.diagnose_failure(
            "run_python_script",
            {"file_name_or_path": "target_remediation_test.py"},
            "Failed: Python script 'target_remediation_test.py' was not found"
        )
        assert diag["category"] == "PATH_NOT_FOUND"

        can_heal, new_tool, new_args, _ = self_healing_engine.attempt_remediation(diag, 0)
        assert can_heal is True
        assert new_tool == "run_python_script"
        assert str(target_file) in new_args.get("file_name_or_path", "")
    finally:
        if target_file.exists():
            target_file.unlink()


def test_self_healing_generic_error_diagnostic_retry():
    """Verify generic error on attempt 0 routes to loop_reasoning with diagnostic message."""
    agent = OllamaAgent()
    engine = SpaceVGraphEngine(agent=agent)

    state = {
        "user_prompt": "test generic error",
        "messages": [],
        "tool_calls": [],
        "tool_results": [{"name": "some_tool", "args": {"k": "v"}}],
        "active_window": "",
        "stuck_detected": False,
        "clarification_question": None,
        "final_response": "",
        "iteration": 0,
        "is_complete": False,
        "healing_attempts": 0,
        "last_error": "Unexpected tool crash: 500 internal error",
        "scratchpad": {}
    }

    res = engine._self_healing_node(state)
    # Verify diagnostic message was added and not marked stuck
    assert res.get("stuck_detected") is None or res.get("stuck_detected") is False
    assert len(res.get("messages", [])) == 1
    assert "[TOOL FAILURE DIAGNOSTIC]" in res["messages"][0]["content"]

    state.update(res)
    route = engine._route_after_healing(state)
    assert route == "loop_reasoning"


def test_sanitize_tool_output_disk_spooling_and_head_tail():
    """Verify sanitize_tool_output preserves head/tail and spools full content to disk."""
    from tools.system_tools import sanitize_tool_output, SPOOL_DIR

    # 1. Short output is untouched
    short_text = "Standard concise command output."
    assert sanitize_tool_output(short_text, max_chars=8000) == short_text

    # 2. Large output (> 8,000 chars) is bounded with Head + Tail
    large_text = "HEAD_START_" + ("X" * 20000) + "_TAIL_END"
    sanitized = sanitize_tool_output(large_text, max_chars=8000)

    assert len(sanitized) <= 8500
    assert sanitized.startswith("HEAD_START_")
    assert sanitized.endswith("_TAIL_END")
    assert "truncated to protect rate limits" in sanitized
    assert "Full output (20020 chars) spooled to:" in sanitized

    # Check spool file exists and contains full verbatim output
    spool_files = list(SPOOL_DIR.glob("tool_output_*.log"))
    assert len(spool_files) > 0
    latest_spool = max(spool_files, key=lambda p: p.stat().st_mtime)
    assert latest_spool.read_text(encoding="utf-8") == large_text


def test_terminal_command_output_bounded():
    """Verify execute_terminal_command clamps massive shell stdout and protects context."""
    from tools.system_tools import execute_terminal_command
    # Generates ~100,000 chars of stdout
    res = execute_terminal_command("python3 -c \"for i in range(2500): print(f'line_{i}_abcdefghijklmnopqrstuvwxyz')\"")
    assert len(res) <= 10000
    assert "truncated to protect rate limits" in res
    assert "spooled to:" in res
    assert "Command succeeded (Exit 0):" in res


def test_graph_engine_tool_node_clamps_messages():
    """Verify SpaceVGraphEngine._tool_node sanitizes unbounded tool outputs before appending to history."""
    agent = OllamaAgent()
    engine = SpaceVGraphEngine(agent=agent)

    huge_output = "START_" + ("Z" * 30000) + "_END"

    def mock_huge_tool(**kwargs):
        return huge_output

    from tools.registry import TOOL_FUNCTIONS
    TOOL_FUNCTIONS["mock_huge_tool"] = mock_huge_tool

    try:
        state = {
            "user_prompt": "run huge tool",
            "messages": [],
            "tool_calls": [{"function": {"name": "mock_huge_tool", "arguments": {}}, "id": "call_mock_123"}],
            "tool_results": [],
            "scratchpad": {},
            "active_window": "",
            "stuck_detected": False,
            "clarification_question": None,
            "final_response": "",
            "iteration": 0,
            "is_complete": False,
            "healing_attempts": 0,
            "last_error": None,
        }

        result_state = engine._tool_executor_node(state)
        tool_msgs = [m for m in result_state["messages"] if m.get("role") == "tool"]
        assert len(tool_msgs) == 1
        assert len(tool_msgs[0]["content"]) <= 8500
        assert "truncated to protect rate limits" in tool_msgs[0]["content"]
    finally:
        TOOL_FUNCTIONS.pop("mock_huge_tool", None)


def test_cloud_client_preflight_large_context_routes_gemini():
    """Verify UniversalBrainClient routes to Gemini first when context > 6,000 tokens to protect Groq TPM."""
    from core.cloud_client import UniversalBrainClient
    client = UniversalBrainClient(
        api_key="mock_groq_key",
        gemini_api_key="mock_gemini_key",
        sambanova_api_key="mock_sambanova_key"
    )

    # Standard short prompt routes Groq first
    pipeline_normal = client._build_provider_pipeline(prompt="list files")
    assert pipeline_normal[0]["name"] == "Groq"

    # Context with heavy history (>20,000 chars / ~6,000 tokens) routes Gemini first
    heavy_messages = [
        {"role": "user", "content": "hello"},
        {"role": "tool", "content": "A" * 25000}
    ]
    pipeline_heavy = client._build_provider_pipeline(prompt="summarize", messages=heavy_messages)
    assert pipeline_heavy[0]["name"] == "Google Gemini"

