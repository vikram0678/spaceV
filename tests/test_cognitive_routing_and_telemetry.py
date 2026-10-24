"""
Industrial Verification Suite for Cognitive Reflex Gating and Telemetry Parity.
Tests the 5 pillars specified in master_agentic_architecture_and_deepdive_plan.md:
1. ReflexGatekeeper System 1 vs System 2 boundary.
2. FastRouter immunity against generative code and composite tasks.
3. SemanticRouterEngine centroid re-balancing and route pruning.
4. Fast-path tool telemetry parity in the flight recorder.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.fast_router import FastRouter
from core.reflex_gatekeeper import ReflexGatekeeper
from core.semantic_router_engine import semantic_router_engine
from core.telemetry import SpaceVTelemetry


class TestCognitiveReflexGatekeeper:
    """Verifies that Kahneman System 1 (Reflex) never hijacks System 2 (Cognitive) tasks."""

    @pytest.mark.parametrize("prompt", [
        "write the anagram program in python3 in the vscode",
        "write an anagram checker in python in vscode",
        "write python program to reverse a number in vscode",
        "create a python script for web scraping in vscode",
        "implement binary search in python in the editor",
        "solve two sum problem in python3",
        "code a rest api in flask in vscode",
        "open chrome and search for latest job application on the ai engineer",
        "open browser and search for machine learning jobs and list them",
        "then write a python script to test this",
    ])
    def test_generative_and_composite_prompts_bypass_fast_router(self, prompt: str):
        """Generative code requests and composite tasks must return True (bypass)."""
        assert ReflexGatekeeper.should_bypass_fast_router(prompt) is True

    @pytest.mark.parametrize("prompt", [
        "what time is it",
        "what is the time",
        "hi",
        "hello spacev",
        "how are you",
        "mute",
        "volume up",
        "volume down",
        "lock screen",
        "lock workstation",
        "clean ram",
        "optimize memory",
        "open notepad",
        "open calculator",
        "open chrome",
        "open vscode",
        "launch vscode",
        "play interstellar on youtube",
    ])
    def test_genuine_reflex_commands_do_not_bypass(self, prompt: str):
        """Zero-latency OS reflex commands must return False (stay on fast path)."""
        assert ReflexGatekeeper.should_bypass_fast_router(prompt) is False


class TestFastRouterCognitiveProtection:
    """Verifies FastRouter.match correctly routes or defers prompts."""

    def test_fast_router_defers_code_generation_to_brain(self):
        """FastRouter must return None for 'write the anagram program in python3 in the vscode'."""
        match = FastRouter.match("write the anagram program in python3 in the vscode")
        assert match is None, f"Expected None (deferred to LLM brain), got: {match}"

    def test_fast_router_defers_composite_job_search(self):
        """FastRouter must return None for composite browser job scraping."""
        match = FastRouter.match("open chrome and search for latest job application on the ai engineer")
        assert match is None, f"Expected None (deferred to LLM brain), got: {match}"

    def test_fast_router_executes_trivial_greeting(self):
        """FastRouter must execute greetings in sub-millisecond reflex."""
        match = FastRouter.match("hi")
        assert match is not None
        tool_name, _tool_output, reply = match
        assert tool_name == "greeting"
        assert "SpaceV" in reply

    def test_fast_router_executes_time_query(self):
        """FastRouter must execute time query in sub-millisecond reflex."""
        match = FastRouter.match("what time is it")
        assert match is not None
        tool_name, tool_output, _reply = match
        assert tool_name == "get_current_time"
        assert ":" in str(tool_output)

    def test_fast_router_executes_pure_app_launch(self):
        """Opening an app without code generation instructions stays on fast path."""
        match = FastRouter.match("open vscode")
        assert match is not None
        tool_name, _tool_output, _reply = match
        assert tool_name in ["open_application", "open_text_editor"]


class TestSemanticRouterPruning:
    """Verifies that vector centroids do not collide on generative words."""

    def test_semantic_router_rejects_code_generation(self):
        """Semantic router route() must return None for code generation prompts."""
        res = semantic_router_engine.route("write the anagram program in python3 in the vscode")
        assert res is None

    def test_semantic_router_matches_clean_editor_launch(self):
        """Semantic router route() correctly matches clean text editor launch queries."""
        res = semantic_router_engine.route("open text editor")
        assert res is not None
        intent_name, confidence, _latency_ms = res
        assert intent_name == "open_text_editor"
        assert confidence >= 0.65


class TestTelemetryFastPathParity:
    """Verifies that fast-path executions record tools into the flight recorder."""

    def test_fast_router_telemetry_records_tool_execution(self, tmp_path):
        """Fast router match must write executed tool into flight recorder jsonl."""
        log_file = tmp_path / "spacev_flight_recorder.jsonl"
        t = SpaceVTelemetry(log_dir=tmp_path)

        # Simulate start turn
        trace_id = t.start_turn("what time is it", channel="console")

        # Fast router match occurs and calls record_tool_execution
        t.record_stage_time("fast_router", 8.5)
        t.record_tool_execution(
            name="get_current_time",
            args={"prompt": "what time is it"},
            status="success",
            duration_ms=8.5,
            result_preview="Current Time: 22:30",
            intercepted_from_xml=False
        )

        t.end_turn(outcome_status="success")

        # Verify disk persistence
        assert log_file.exists()
        with open(log_file, encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        assert len(lines) == 1
        record = lines[0]
        assert record["trace_id"] == trace_id
        assert len(record["tools"]) == 1
        assert record["tools"][0]["name"] == "get_current_time"
        assert record["tools"][0]["status"] == "success"
        assert record["waterfall_ms"]["fast_router"] == 8.5
        assert record["waterfall_ms"]["tool_execution"] == 8.5


class TestConversationalInterlinkingAndExecution:
    """
    Empirical Verification for the 5-Pillar Blueprint:
    Pillar 1: Multi-Turn Rolling Context Interlinking
    Pillar 2: Anti-Zombie Scratchpad Plan Lifecycle Guard
    Pillar 3: Workstation Script & Terminal Execution Tools
    Pillar 4: Dynamic Entity Resolution from Working Memory
    Pillar 5: XML Tool Speech Sanitizer
    """

    def test_scratchpad_anti_zombie_plan_guard(self):
        from core.scratchpad import SpaceVScratchpad
        sp = SpaceVScratchpad()
        sp.set_goal("open vscode and create reverse number program")
        sp.create_plan(["Open VSCode", "Create file", "Write reverse algorithm"])
        sp.set_note("last_file_name", "reverse_number.py")
        sp.set_note("last_app_name", "vscode")

        assert sp.has_pending_steps() is True
        assert len(sp.plan) == 3

        # Turn 2: User issues new command -> set_goal must clear the old checklist
        sp.set_goal("now execute that program in vscode")
        assert sp.has_pending_steps() is False
        assert len(sp.plan) == 0
        # Working memory notes must be preserved across turns
        assert sp.get_note("last_file_name") == "reverse_number.py"
        assert sp.get_note("last_app_name") == "vscode"

    def test_run_python_script_execution_and_auto_eof_recovery(self, tmp_path, monkeypatch):
        from tools.system_tools import run_python_script
        script_file = tmp_path / "interactive_reverse.py"
        script_file.write_text(
            "import sys\n"
            "n = int(input('Enter number: '))\n"
            "print(f'Reversed: {str(n)[::-1]}')\n",
            encoding="utf-8"
        )

        # 1. Run with explicit input
        out = run_python_script(str(script_file), input_data="9876\n")
        assert "Exit Code: 0" in out
        assert "Reversed: 6789" in out

        # 2. Run without input -> Auto-recovery from EOFError with mock input
        out_auto = run_python_script(str(script_file))
        assert "Exit Code: 0" in out_auto
        assert "Reversed: 54321" in out_auto

    def test_run_python_script_entity_resolution(self, tmp_path, monkeypatch):
        from core.scratchpad import active_scratchpad
        from tools.system_tools import run_python_script

        script_file = tmp_path / "fibonacci.py"
        script_file.write_text("print('Fibonacci sequence computed successfully')\n", encoding="utf-8")

        active_scratchpad.set_note("last_file_name", str(script_file))

        # Pass an anaphoric reference like "that program"
        res = run_python_script("that program")
        assert "Exit Code: 0" in res
        assert "Fibonacci sequence computed successfully" in res

    def test_graph_engine_rolling_context_interlinking(self):
        from core.graph_engine import SpaceVGraphEngine

        engine = SpaceVGraphEngine()
        engine.agent.messages = [
            {"role": "user", "content": "create a python script reverse_number.py in vscode"},
            {"role": "assistant", "content": "The Python script reverse_number.py has been created in VSCode."}
        ]

        state = {
            "user_prompt": "now execute that program in vscode",
            "messages": [],
            "scratchpad": {}
        }
        res = engine._perception_guard_node(state)
        seeded_messages = res["messages"]

        # Verify system prompt + rolling history (Turn 1 user + assistant) + Turn 2 user prompt
        assert len(seeded_messages) >= 4
        assert seeded_messages[0]["role"] == "system"
        assert seeded_messages[1]["role"] == "user"
        assert "reverse_number.py" in seeded_messages[1]["content"]
        assert seeded_messages[2]["role"] == "assistant"
        assert seeded_messages[3]["role"] == "user"
        assert seeded_messages[3]["content"] == "now execute that program in vscode"

    def test_xml_speech_sanitizer_removes_naked_tool_call(self):
        from core.graph_engine import sanitize_speech_output
        leaked_xml = "<tool_call>scratchpad_view</tool_call>"
        clean = sanitize_speech_output(leaked_xml)
        assert "<tool_call>" not in clean
        assert "scratchpad_view" not in clean
        assert "Sir" in clean

    def test_resolve_interpreter_command_eliminates_exit_code_126(self, tmp_path):
        from tools.system_tools import resolve_interpreter_command

        script = tmp_path / "test_prog.py"
        script.write_text("print('hello')", encoding="utf-8")

        # 1. Bare .py command must be resolved with python3 -u
        res1 = resolve_interpreter_command(str(script))
        assert res1.startswith("python3 -u ") or res1.startswith(f"{sys.executable} -u ")
        assert str(script) in res1

        # 2. Command with args
        res2 = resolve_interpreter_command(f"{script} 1234555")
        assert " -u " in res2
        assert "1234555" in res2

        # 3. Already qualified command is untouched
        res3 = resolve_interpreter_command(f"python3 {script}")
        assert res3 == f"python3 {script}"

    def test_run_python_script_dual_pipe_stdin_binding(self, tmp_path):
        from tools.system_tools import run_python_script
        script_file = tmp_path / "interactive_number.py"
        script_file.write_text(
            "import sys\n"
            "user_in = input('Enter number: ')\n"
            "print(f'Processed Input: {user_in}')\n",
            encoding="utf-8"
        )

        # args is passed ('1234555') and stdin_input is None; dual-pipe binds args to stdin
        out = run_python_script(str(script_file), args="1234555")
        assert "Exit Code: 0" in out
        assert "Processed Input: 1234555" in out

    def test_execution_prompts_bypass_fast_router_and_editor_misroute(self):
        from core.fast_router import FastRouter
        from core.reflex_gatekeeper import ReflexGatekeeper

        prompt1 = "yes i want to run direclty in the vscode terminal"
        prompt2 = "run reverse_number.py in the terminal"
        prompt3 = "execute that script in vscode terminal"

        # Gatekeeper must bypass fast-path reflex execution
        assert ReflexGatekeeper.should_bypass_fast_router(prompt1) is True
        assert ReflexGatekeeper.should_bypass_fast_router(prompt2) is True
        assert ReflexGatekeeper.should_bypass_fast_router(prompt3) is True

        # FastRouter must defer to brain (return None), NEVER triggering open_text_editor
        assert FastRouter.match(prompt1) is None
        assert FastRouter.match(prompt2) is None
        assert FastRouter.match(prompt3) is None

    def test_prune_conversation_trauma_eliminates_learned_helplessness(self):
        from core.graph_engine import prune_conversation_trauma

        traumatized_history = [
            {"role": "user", "content": "run reverse_number.py"},
            {"role": "assistant", "content": "I apologize for the unexpected failure state. [Errno 13] Permission denied. I am unable to proceed with executing the script."},
            {"role": "user", "content": "input number is 1234555"},
        ]

        sanitized = prune_conversation_trauma(traumatized_history)
        assert len(sanitized) == 3
        # Assistant message must be stripped of apology/trauma
        assistant_msg = sanitized[1]["content"]
        assert "apologize" not in assistant_msg.lower()
        assert "permission denied" not in assistant_msg.lower()
        assert "operational" in assistant_msg.lower()
        # User messages must be preserved intact
        assert sanitized[0]["content"] == "run reverse_number.py"
        assert sanitized[2]["content"] == "input number is 1234555"

    def test_execute_in_vscode_terminal_registry_and_pydantic_schema(self, tmp_path):
        from tools.registry import OLLAMA_TOOLS_SCHEMA, TOOL_ALIASES, TOOL_FUNCTIONS, execute_tool
        from tools.schemas import PYDANTIC_TOOL_MODELS

        # Tool registered in canonical registry
        assert "execute_in_vscode_terminal" in TOOL_FUNCTIONS
        assert "vscode_terminal" in TOOL_ALIASES
        assert "run_in_vscode_terminal" in TOOL_ALIASES
        assert "execute_in_vscode_terminal" in PYDANTIC_TOOL_MODELS

        # Schema declared in Ollama function calling definitions
        schema_names = [f["function"]["name"] for f in OLLAMA_TOOLS_SCHEMA if "function" in f]
        assert "execute_in_vscode_terminal" in schema_names

        # Execution check
        test_script = tmp_path / "hello.py"
        test_script.write_text("print('VSCode Execution Verified')", encoding="utf-8")
        result = execute_tool("execute_in_vscode_terminal", {"command": f"python3 {test_script}"})
        assert "VSCode Execution Verified" in result or "Exit Code: 0" in result

    def test_pure_polarity_and_conversational_closures_bypass_reflex(self):
        """Verify single-token polarity answers ('no', 'nope', 'nah', etc.) NEVER match capabilities or fast path."""
        from core.fast_router import FastRouter
        from core.reflex_gatekeeper import ReflexGatekeeper
        from core.semantic_router_engine import semantic_router_engine

        polarity_prompts = ["no", "no thanks", "nope", "nah", "nevermind", "cancel", "dont", "don't"]
        for p in polarity_prompts:
            assert ReflexGatekeeper.should_bypass_fast_router(p) is True
            assert FastRouter.match(p) is None
            semantic_res = semantic_router_engine.route(p)
            assert semantic_res is None or semantic_res[0] != "capabilities"

    def test_negative_polarity_constraints_prevent_youtube_autoplay(self):
        """Verify negative constraints ('dont play anything just open youtube') NEVER trigger play_youtube."""
        from core.fast_router import FastRouter
        from core.reflex_gatekeeper import ReflexGatekeeper
        from core.semantic_router_engine import semantic_router_engine

        negative_prompts = [
            "i dont want to play any video just open thats it",
            "dont play anything just open youtube",
            "dont play any song",
            "open youtube and dont play anything",
            "just open youtube"
        ]
        for p in negative_prompts:
            assert ReflexGatekeeper.should_bypass_fast_router(p) is True
            match_res = FastRouter.match(p)
            assert match_res is None or match_res[0] != "play_youtube"
            semantic_res = semantic_router_engine.route(p)
            assert semantic_res is None or semantic_res[0] != "media_play_youtube"

    def test_conversational_singing_and_jokes_bypass_media_hardware_keys(self):
        """Verify conversational queries ('could you sing a song') NEVER trigger hardware media key events."""
        from core.fast_router import FastRouter
        from core.reflex_gatekeeper import ReflexGatekeeper
        from core.semantic_router_engine import semantic_router_engine

        conversational_prompts = [
            "could you sing a song",
            "sing me a song",
            "tell me a joke",
            "sing a song for me"
        ]
        for p in conversational_prompts:
            assert ReflexGatekeeper.should_bypass_fast_router(p) is True
            assert FastRouter.match(p) is None
            semantic_res = semantic_router_engine.route(p)
            assert semantic_res is None or semantic_res[0] not in ("media_previous", "media_next", "media_play_pause")

    def test_honest_dialogue_fallback_when_zero_tools_executed(self):
        """Verify empty responses with 0 tools executed return honest clarification, not phantom success."""
        from core.graph_engine import sanitize_speech_output

        # When 0 tools executed (has_tools=False) and text is empty:
        response = sanitize_speech_output("", has_error=False, has_tools=False)
        assert "Action completed successfully" not in response
        assert "I understand, Sir" in response
        assert "what you would like to do next" in response

        # When tools WERE executed (has_tools=True) and text is empty:
        tool_executed_response = sanitize_speech_output("", has_error=False, has_tools=True)
        assert "Action completed successfully" in tool_executed_response

    def test_deterministic_fast_path_intents_preserved(self):
        """Verify genuine OS commands still execute in 0ms without regression."""
        from core.fast_router import FastRouter

        # Time check
        time_res = FastRouter.match("what time is it")
        assert time_res is not None
        assert time_res[0] == "get_current_time"

        # Lock screen
        lock_res = FastRouter.match("lock screen")
        assert lock_res is not None
        assert lock_res[0] == "lock_workstation"

        # Mute audio
        mute_res = FastRouter.match("mute volume")
        assert mute_res is not None
        assert mute_res[0] == "media_control"


class TestMultiAgentExecutionAndReliability:
    """Verifies architectural fixes for multi-step tasks, sequential mutating execution, and verification gates."""

    def test_dual_stream_stdio_preserves_stderr_on_exit_code_zero(self, tmp_path):
        """Exit code 0 with non-empty stderr must output both STDOUT and STDERR."""
        from tools.system_tools import execute_code_block

        code = "import sys\nsys.stdout.write('HELLO_STDOUT\\n')\nsys.stderr.write('WARNING_STDERR\\n')\n"
        res = execute_code_block(code=code)
        assert "Code execution successful" in res
        assert "STDOUT:\nHELLO_STDOUT" in res
        assert "STDERR:\nWARNING_STDERR" in res

    def test_open_url_preserves_custom_uri_schemes(self, monkeypatch):
        """URI schemes like ms-settings: must never be mangled with https://."""
        from core.platform_adapter import PlatformAdapter
        import subprocess

        captured_cmds = []

        def mock_popen(args, **kwargs):
            captured_cmds.append(args)
            return None

        monkeypatch.setattr(PlatformAdapter, "is_wsl", lambda: True)
        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        # Test custom Windows settings URI
        PlatformAdapter.open_url("ms-settings:network-wifi")
        assert any("ms-settings:network-wifi" in cmd for cmd in captured_cmds)
        assert not any("https://ms-settings" in str(cmd) for cmd in captured_cmds)

        # Test standard domain without scheme
        captured_cmds.clear()
        PlatformAdapter.open_url("google.com")
        assert any("https://google.com" in cmd for cmd in captured_cmds)

    def test_goal_backward_verification_gate_keeps_looping(self):
        """_route_after_tools must not synthesize until requested verification read tools execute."""
        from core.graph_engine import SpaceVGraphEngine
        from core.scratchpad import SpaceVScratchpad

        engine = SpaceVGraphEngine()
        scratchpad = SpaceVScratchpad()

        state = {
            "user_prompt": "Create test.txt with data and then read back the file content to verify",
            "iteration": 1,
            "scratchpad": scratchpad.to_dict(),
            "tool_results": [{"name": "create_file", "args": {"filename": "test.txt"}, "status": "success"}]
        }

        # Gate should force another reasoning loop because verification read has not occurred
        next_step = engine._route_after_tools(state)
        assert next_step == "loop_reasoning"

        # Once verification tool has run, it can transition to synthesize
        state["tool_results"].append({"name": "read_file_content", "args": {"filename": "test.txt"}, "status": "success"})
        assert engine._route_after_tools(state) == "synthesize"

    def test_nested_folder_guard_prevents_premature_exit(self):
        """_route_after_tools ensures all segments of a nested folder path are created before exiting."""
        from core.graph_engine import SpaceVGraphEngine
        from core.scratchpad import SpaceVScratchpad

        engine = SpaceVGraphEngine()
        scratchpad = SpaceVScratchpad()

        state = {
            "user_prompt": "create nested directories alpha/beta/gamma on desktop",
            "iteration": 1,
            "scratchpad": scratchpad.to_dict(),
            "tool_results": [{"name": "create_folder", "args": {"folder_name": "alpha"}, "status": "success"}]
        }

        # Alpha is created, but beta and gamma are still pending
        assert engine._route_after_tools(state) == "loop_reasoning"

        # Add remaining folders
        state["tool_results"].append({"name": "create_folder", "args": {"folder_name": "beta"}, "status": "success"})
        state["tool_results"].append({"name": "create_folder", "args": {"folder_name": "gamma"}, "status": "success"})
        assert engine._route_after_tools(state) == "synthesize"

    def test_cloud_client_disables_provider_on_http_402(self, monkeypatch):
        """HTTP 402 or PAYMENT_METHOD_REQUIRED instantly disables the failing provider."""
        from core.cloud_client import UniversalBrainClient
        import requests

        client = UniversalBrainClient()

        class MockResponse:
            status_code = 402
            text = '{"error": {"code": "PAYMENT_METHOD_REQUIRED", "message": "Credits depleted"}}'
            headers = {}

            def iter_lines(self):
                return []

        monkeypatch.setattr(requests, "post", lambda *a, **kw: MockResponse())
        # Mock fallback to prevent trying Ollama in unit test
        monkeypatch.setattr(client, "_fallback_to_ollama", lambda m, t, c: {"role": "assistant", "content": "mocked fallback"})

        res = client.chat(messages=[{"role": "user", "content": "test"}])
        assert res["content"] == "mocked fallback"
        assert len(client.disabled_providers) > 0

    def test_semantic_router_does_not_hijack_open_settings(self):
        """'open settings and wifi settings' must never be routed to get_network_info."""
        from core.semantic_router_engine import semantic_router_engine

        result = semantic_router_engine.route("open settings and wifi settings")
        if result is not None:
            intent, _confidence, _ = result
            assert intent != "get_network_info"

    def test_doubt_driven_gate_prevents_synthesizing_on_mutating_failure(self):
        """_route_after_tools must not synthesize if a mutating tool returned an error or failure string."""
        from core.graph_engine import SpaceVGraphEngine
        from core.scratchpad import SpaceVScratchpad

        engine = SpaceVGraphEngine()
        scratchpad = SpaceVScratchpad()

        state = {
            "user_prompt": "run the cleanup script on the desktop",
            "iteration": 1,
            "scratchpad": scratchpad.to_dict(),
            "tool_results": [
                {
                    "name": "execute_code_block",
                    "args": {"code": "rm -rf /"},
                    "status": "error",
                    "content": "Failed: ContainmentGatekeeper blocked execution."
                }
            ]
        }

        # Gate disproves phantom success and forces another loop (self-healing or reflection)
        assert engine._route_after_tools(state) == "loop_reasoning"

    def test_read_file_content_with_error_string_does_not_fail(self):
        """Reading code with 'error' or 'except' must evaluate to status='success' and last_error=None."""
        from core.graph_engine import SpaceVGraphEngine, determine_tool_status

        mock_code_content = "Content of 'main.py' (46 lines):\n\n```python\ntry:\n    do_something()\nexcept ValueError as error:\n    logger.error('failed')\n```"
        status = determine_tool_status("read_file_content", mock_code_content)
        assert status == "success"

        engine = SpaceVGraphEngine()
        tool_call = {
            "id": "call_123",
            "function": {
                "name": "read_file_content",
                "arguments": {"file_name_or_path": "main.py"}
            }
        }
        state = {
            "user_prompt": "inspect main.py",
            "iteration": 1,
            "tool_calls": [tool_call],
            "tool_results": [],
            "messages": [],
            "scratchpad": {}
        }

        # Monkeypatch execute_tool to return the mock code
        from unittest.mock import patch
        with patch("core.graph_engine.execute_tool", return_value=mock_code_content):
            new_state = engine._tool_executor_node(state)

        assert new_state["last_error"] is None
        assert new_state["tool_results"][0]["status"] == "success"
        assert engine._route_after_tools(new_state) != "self_healing"

    def test_resolve_path_workspace_location(self):
        """resolve_path must resolve 'workspace', 'project', and 'agentspace' to the workspace root."""
        from tools.file_tools import WORKSPACE_DIR, read_file_content, resolve_path

        assert resolve_path("workspace") == WORKSPACE_DIR
        assert resolve_path("project") == WORKSPACE_DIR
        assert resolve_path("repo") == WORKSPACE_DIR
        assert resolve_path("agentspace") == WORKSPACE_DIR
        assert resolve_path("workspace/config.py") == WORKSPACE_DIR / "config.py"

        # Reading file with location='workspace'
        res = read_file_content("config.py", location="workspace")
        assert "Content of 'config.py'" in res
        assert not res.startswith("Failed")

    def test_list_workspace_files_excludes_ignored_directories(self):
        """list_workspace_files must list active workspace files and prune .venv, .git, and cache."""
        from tools.file_tools import list_workspace_files

        listing = list_workspace_files(max_files=100)
        assert "Workspace files (" in listing
        assert "main.py" in listing or "config.py" in listing

        # Ensure excluded directories are pruned
        assert ".venv/" not in listing
        assert ".git/" not in listing
        assert "__pycache__/" not in listing

    def test_speech_synthesis_fallback_includes_tool_summary(self):
        """Speech synthesis fallback must incorporate honest tool summaries and eliminate phantom success."""
        from core.graph_engine import generate_tool_summary, sanitize_speech_output

        tool_results = [
            {
                "name": "read_file_content",
                "args": {"file_name_or_path": "main.py"},
                "result": "Content of 'main.py' (46 lines):\n\n```python\nimport os\n```",
                "status": "success"
            }
        ]
        summary = generate_tool_summary(tool_results)
        assert "Read main.py" in summary

        # When LLM text is empty, speech output uses the tool summary
        speech = sanitize_speech_output("", has_error=False, has_tools=True, tool_summary=summary)
        assert "Action completed. Read main.py" in speech

    def test_create_file_empty_content_warning(self, tmp_path):
        """create_file must report absolute path, file size, and warn if content was empty."""
        from tools.file_tools import create_file

        # 1. Non-empty file
        res = create_file("sample.py", content="print('hello')", location=str(tmp_path))
        assert "Successfully created file 'sample.py' (size: 14 bytes) at:" in res
        assert str(tmp_path) in res

        # 2. Empty file
        res_empty = create_file("empty.txt", content="", location=str(tmp_path))
        assert "Created empty file 'empty.txt' (0 bytes) at:" in res_empty
        assert "Note: No content was provided." in res_empty

    def test_groq_429_multi_model_bucket_hopping(self, monkeypatch):
        """When Groq returns 429 on primary model, it must hop to llama-3.1-8b-instant (20k TPM bucket)."""
        import requests
        from core.cloud_client import UniversalBrainClient

        client = UniversalBrainClient(
            base_url="https://api.groq.com/openai/v1",
            api_key="mock_key",
            default_model="openai/gpt-oss-120b"
        )

        call_models = []

        class MockResponse:
            def __init__(self, model):
                self.model = model
                if "120b" in model:
                    self.status_code = 429
                    self.text = '{"error": {"message": "Rate limit reached for 120b"}}'
                    self.headers = {"x-ratelimit-reset-tokens": "10s"}
                else:
                    self.status_code = 200
                    self.text = '{"choices": [{"message": {"role": "assistant", "content": "hopped to 8b"}}]}'
                    self.headers = {}

            def json(self):
                return json.loads(self.text)

            def iter_lines(self):
                return []

        def mock_post(url, headers=None, json=None, stream=False, timeout=None):
            m = json.get("model", "")
            call_models.append(m)
            return MockResponse(m)

        monkeypatch.setattr(requests, "post", mock_post)

        res = client.chat(messages=[{"role": "user", "content": "test message"}])
        assert res["content"] == "hopped to 8b"
        assert "llama-3.1-8b-instant" in call_models
        assert "openai/gpt-oss-120b" in call_models





