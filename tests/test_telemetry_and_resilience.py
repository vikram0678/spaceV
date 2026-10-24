"""
Unit and Integration Test Suite for SpaceV Observability,
Dual-Sink JSONL Flight Recorder, and Multi-Turn XML Self-Healing.
Validates all Production Gates (G1 - G5) in master_telemetry_and_resilience_blueprint.md.
"""
import json
import tempfile
import time
from unittest.mock import MagicMock

import pytest

from core.ollama_client import parse_fallback_tool_calls
from core.telemetry import SpaceVTelemetry, telemetry
from tools.file_tools import read_file_content
from tools.registry import execute_tool
from tools.schemas import CreateFileInput, OpenAppInput, PlayYoutubeInput, ReadFileInput

# =============================================================================
# GATE 2 & 4: TELEMETRY ENGINE & DUAL-SINK ATOMIC PERSISTENCE TESTS
# =============================================================================

class TestTelemetryEngine:
    """Tests the Dual-Sink Telemetry Dispatcher, Span Lifecycle, and JSONL Black Box."""

    def test_span_lifecycle_success(self):
        """Verifies high-resolution span timing and successful completion."""
        span_obj = None
        with telemetry.span("test_stage") as sp:
            time.sleep(0.01)  # 10ms
            span_obj = sp

        assert span_obj is not None
        assert span_obj.status == "success"
        assert span_obj.duration_ms >= 8.0  # At least ~10ms
        assert span_obj.finish_time > span_obj.start_time

    def test_span_lifecycle_failure_handling(self):
        """Verifies that unhandled exceptions mark the span as 'failed' and preserve error metadata."""
        span_obj = None
        with pytest.raises(ValueError, match="Synthetic failure"):
            with telemetry.span("critical_io") as sp:
                span_obj = sp
                raise ValueError("Synthetic failure")

        assert span_obj is not None
        assert span_obj.status == "failed"
        assert "Synthetic failure" in (span_obj.error or "")
        assert span_obj.duration_ms >= 0.0

    def test_dual_sink_jsonl_atomic_writes(self, tmp_path):
        """Verifies atomic append-only JSONL writes with complete schema integrity."""
        custom_telemetry = SpaceVTelemetry(log_dir=tmp_path)
        log_file = tmp_path / "spacev_flight_recorder.jsonl"

        # Simulate Turn 1
        trace_id_1 = custom_telemetry.start_turn("open vscode and create main.py", channel="voice")
        custom_telemetry.record_stage_time("vad_listen_window", 2100.0)
        custom_telemetry.record_stage_time("stt_whisper", 340.5)
        custom_telemetry.record_stage_time("fast_router", 0.9)
        custom_telemetry.record_tool_execution(
            name="open_application",
            args={"app_name": "vscode"},
            status="success",
            duration_ms=45.2,
            result_preview="Launched vscode"
        )
        record_1 = custom_telemetry.end_turn(outcome_status="success")
        assert record_1["turn_id"] == 1

        # Simulate Turn 2
        trace_id_2 = custom_telemetry.start_turn("yes continue", channel="voice")
        custom_telemetry.record_xml_healing("read_file_content", "<function=read_file>main.py</function>")
        custom_telemetry.record_tool_execution(
            name="read_file_content",
            args={"file_path": "main.py"},
            status="success",
            duration_ms=12.4,
            result_preview="print('hello')",
            intercepted_from_xml=True
        )
        record_2 = custom_telemetry.end_turn(outcome_status="success")
        assert record_2["turn_id"] == 2

        assert log_file.exists(), "Flight recorder JSONL file must exist on disk."

        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2, f"Expected exactly 2 JSONL records, found {len(lines)}"

        # Validate Turn 1 record schema
        data_1 = json.loads(lines[0])
        assert data_1["trace_id"] == trace_id_1
        assert data_1["turn_id"] == 1
        assert data_1["waterfall_ms"]["vad_listen_window"] == 2100.0
        assert data_1["waterfall_ms"]["stt_whisper"] == 340.5
        assert data_1["waterfall_ms"]["tool_execution"] == 45.2
        assert len(data_1["tools"]) == 1
        assert data_1["tools"][0]["name"] == "open_application"
        assert data_1["outcome"]["status"] == "success"

        # Validate Turn 2 record schema & XML healing audit
        data_2 = json.loads(lines[1])
        assert data_2["trace_id"] == trace_id_2
        assert data_2["turn_id"] == 2
        assert data_2["outcome"]["xml_leak_detected"] is True
        assert data_2["outcome"]["xml_leak_healed"] is True
        assert data_2["outcome"]["healed_tool"] == "read_file_content"
        assert len(data_2["tools"]) == 1
        assert data_2["tools"][0]["intercepted_from_xml"] is True

    def test_telemetry_overhead_performance_gate(self):
        """GATE 4: Observability overhead must be <= 0.1ms per telemetry operation."""
        custom_telemetry = SpaceVTelemetry(log_dir=tempfile.gettempdir())
        custom_telemetry.start_turn("test benchmark")

        iterations = 500
        start = time.perf_counter()
        for i in range(iterations):
            custom_telemetry.record_stage_time(f"stage_{i % 5}", 1.23)
            custom_telemetry.record_tool_execution(
                name="test_tool",
                args={"k": "v"},
                status="success",
                duration_ms=0.5
            )
        elapsed_sec = time.perf_counter() - start
        avg_overhead_ms = (elapsed_sec / (iterations * 2)) * 1000.0

        # Must execute comfortably under 0.1ms
        assert avg_overhead_ms < 0.1, f"Telemetry overhead too high: {avg_overhead_ms:.4f}ms per call"


# =============================================================================
# GATE 3: QWEN / LLAMA XML TOOL INTERCEPTION & SELF-HEALING TESTS
# =============================================================================

class TestXmlToolTagSelfHealing:
    """Verifies extraction and healing of pre-training XML tool tags."""

    def test_qwen_xml_single_parameter_extraction(self):
        """Verifies extraction of <function=read_file><parameter=file_path>main.py</parameter></function>."""
        raw_llm_response = (
            "<tool_call>\n"
            "<function=read_file>\n"
            "<parameter=file_path>\n"
            "main.py\n"
            "</parameter>\n"
            "</function>\n"
            "</tool_call>"
        )
        extracted, clean = parse_fallback_tool_calls(raw_llm_response)

        assert len(extracted) == 1
        call = extracted[0]
        # Should resolve 'read_file' alias to canonical 'read_file_content'
        assert call["function"]["name"] == "read_file_content"
        assert call["function"]["arguments"]["file_path"] == "main.py"
        assert call.get("intercepted_from_xml") is True
        # Cleaned text should be completely stripped of XML tags
        assert "<tool_call>" not in clean
        assert "<function" not in clean
        assert "</tool_call>" not in clean
        assert clean == ""

    def test_qwen_xml_multi_parameter_extraction(self):
        """Verifies extraction of XML tags with multiple parameter elements."""
        raw_llm_response = (
            "I will create the code file for you.\n"
            "<tool_call>\n"
            "<function=open_text_editor>\n"
            "<parameter=file_name>reverse_number.py</parameter>\n"
            "<parameter=content>def reverse_num(n):\n    return int(str(n)[::-1])</parameter>\n"
            "<parameter=editor>code</parameter>\n"
            "</function>\n"
            "</tool_call>"
        )
        extracted, clean = parse_fallback_tool_calls(raw_llm_response)

        assert len(extracted) == 1
        func = extracted[0]["function"]
        assert func["name"] == "open_text_editor"
        args = func["arguments"]
        assert args["file_name"] == "reverse_number.py"
        assert "def reverse_num" in args["content"]
        assert args["editor"] == "code"
        assert "I will create the code file for you." in clean

    def test_qwen_xml_attribute_syntax_variation(self):
        """Verifies XML with attribute format: <function name="create_file"><parameter name="file_name">..."""
        raw_llm_response = (
            '<tool_call>'
            '<function name="create_file">'
            '<parameter name="file_name">script.py</parameter>'
            '<parameter name="content">print("Hello SpaceV")</parameter>'
            '</function>'
            '</tool_call>'
        )
        extracted, clean = parse_fallback_tool_calls(raw_llm_response)

        assert len(extracted) == 1
        assert extracted[0]["function"]["name"] == "create_file"
        assert extracted[0]["function"]["arguments"]["file_name"] == "script.py"
        assert clean == ""

    def test_qwen_xml_json_parameter_parsing(self):
        """Verifies that JSON arrays/objects inside parameter tags are parsed cleanly."""
        raw_llm_response = (
            "<tool_call>\n"
            "<function=scratchpad_set_plan>\n"
            "<parameter=steps>[\"Step 1: Check window\", \"Step 2: Read main.py\"]</parameter>\n"
            "</function>\n"
            "</tool_call>"
        )
        extracted, _ = parse_fallback_tool_calls(raw_llm_response)

        assert len(extracted) == 1
        args = extracted[0]["function"]["arguments"]
        assert isinstance(args["steps"], list)
        assert len(args["steps"]) == 2
        assert args["steps"][0] == "Step 1: Check window"


# =============================================================================
# POSTEL'S LAW & PYDANTIC SCHEMA TOLERANCE TESTS
# =============================================================================

class TestPostelsLawTolerance:
    """Verifies that tools and schemas liberally accept slight parameter name variations."""

    def test_read_file_input_schema_tolerance(self):
        """ReadFileInput must accept file_path, path, or filename and normalize to file_name_or_path."""
        m1 = ReadFileInput(**{"file_path": "main.py"})
        assert m1.file_name_or_path == "main.py"

        m2 = ReadFileInput(**{"path": "/tmp/test.py"})
        assert m2.file_name_or_path == "/tmp/test.py"

        m3 = ReadFileInput(**{"filename": "reverse.py"})
        assert m3.file_name_or_path == "reverse.py"

    def test_create_file_input_schema_tolerance(self):
        """CreateFileInput must accept filename, file_path, path and normalize to file_name."""
        m1 = CreateFileInput(**{"filename": "app.py", "content": "# test"})
        assert m1.file_name == "app.py"

        m2 = CreateFileInput(**{"file_path": "app.py", "content": "# test"})
        assert m2.file_name == "app.py"

    def test_open_app_input_schema_tolerance(self):
        """OpenAppInput must accept app, application, application_name and normalize to app_name."""
        m1 = OpenAppInput(**{"app": "vscode"})
        assert m1.app_name == "vscode"

        m2 = OpenAppInput(**{"application": "firefox"})
        assert m2.app_name == "firefox"

    def test_play_youtube_input_schema_tolerance(self):
        """PlayYoutubeInput must accept query, title, song_name and normalize to video_query."""
        m1 = PlayYoutubeInput(**{"query": "interstellar soundtrack"})
        assert m1.video_query == "interstellar soundtrack"

        m2 = PlayYoutubeInput(**{"song_name": "hotel california"})
        assert m2.video_query == "hotel california"

    def test_read_file_content_execution_with_file_path_kwarg(self, tmp_path):
        """Direct test of read_file_content called with file_path instead of file_name_or_path."""
        test_file = tmp_path / "hello.py"
        test_file.write_text("print('hello world')", encoding="utf-8")

        # Call with file_path keyword argument (what Qwen emits!)
        result = read_file_content(file_path=str(test_file))
        assert "hello world" in result
        assert "Failed to read file" not in result

    def test_execute_tool_with_alias_and_kwarg(self, tmp_path):
        """Verifies execute_tool('read_file', {'file_path': '...'}) completes cleanly."""
        test_file = tmp_path / "sample.txt"
        test_file.write_text("SpaceV Autonomous Workstation", encoding="utf-8")

        result = execute_tool("read_file", {"file_path": str(test_file)})
        assert "SpaceV Autonomous Workstation" in result


# =============================================================================
# GRAPH ENGINE MULTI-TURN RESILIENCE INTEGRATION TEST
# =============================================================================

class TestGraphEngineResilience:
    """Verifies that the state machine catches XML tool tags and completes execution."""

    def test_state_machine_self_heals_xml_output(self, monkeypatch, tmp_path):
        """Simulates Turn 2 where Ollama returns raw Qwen XML, verifying it is intercepted and healed."""
        from core.graph_engine import SpaceVGraphEngine
        from core.telemetry import SpaceVTelemetry

        temp_telemetry = SpaceVTelemetry(log_dir=tmp_path)
        monkeypatch.setattr("core.graph_engine.telemetry", temp_telemetry)

        engine = SpaceVGraphEngine()
        engine.agent.provider = "ollama"

        test_file = tmp_path / "target.py"
        test_file.write_text("x = 42\nprint(x)", encoding="utf-8")

        xml_response = (
            "<tool_call>\n"
            "<function=read_file>\n"
            f"<parameter=file_path>{test_file}</parameter>\n"
            "</function>\n"
            "</tool_call>"
        )

        # Mock requests.post in reasoning node to return the XML response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {
                "role": "assistant",
                "content": xml_response,
                "tool_calls": []  # Native tool calling returned empty!
            }
        }

        # Mock requests.post for reasoning and streaming synthesizer
        def mock_post(url, *args, **kwargs):
            if kwargs.get("stream"):
                stream_mock = MagicMock()
                stream_mock.status_code = 200
                stream_mock.iter_lines.return_value = [
                    json.dumps({"message": {"content": "I have read the file. The value of x is 42."}}).encode("utf-8")
                ]
                return stream_mock
            return mock_response

        monkeypatch.setattr("requests.post", mock_post)
        monkeypatch.setattr("tools.vision_tools.get_active_window_info", lambda: "VS Code")

        # Execute prompt through graph
        reply = engine.run("yes continue reading target.py")

        assert "The value of x is 42" in reply or "Action completed" in reply
        # Verify XML tag was not printed to user
        assert "<tool_call>" not in reply
        assert "<function=" not in reply

        # Verify telemetry flight recorder recorded the healed event
        log_file = tmp_path / "spacev_flight_recorder.jsonl"
        assert log_file.exists()
        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) >= 1
        record = json.loads(lines[-1])
        assert record["outcome"]["xml_leak_detected"] is True
        assert record["outcome"]["xml_leak_healed"] is True

    def test_cloud_dual_brain_self_heals_xml_output(self, monkeypatch, tmp_path):
        """Simulates Cloud LLM returning raw XML tags, verifying it is intercepted and healed."""
        from core.graph_engine import SpaceVGraphEngine
        from core.telemetry import SpaceVTelemetry

        temp_telemetry = SpaceVTelemetry(log_dir=tmp_path)
        monkeypatch.setattr("core.graph_engine.telemetry", temp_telemetry)

        engine = SpaceVGraphEngine()
        engine.agent.provider = "openai"

        test_file = tmp_path / "cloud_target.py"
        test_file.write_text("status = 'Cloud operational'", encoding="utf-8")

        xml_response = (
            "<tool_call>\n"
            "<function=read_file>\n"
            f"<parameter=file_path>{test_file}</parameter>\n"
            "</function>\n"
            "</tool_call>"
        )

        mock_cloud_client = MagicMock()
        mock_cloud_client.select_cloud_model.return_value = "cloud-model-v1"
        mock_cloud_client.chat.side_effect = [
            {"content": xml_response, "tool_calls": []},
            {"content": "Cloud verified file content: status is Cloud operational."},
            {"content": "Cloud verified file content: status is Cloud operational."}
        ]
        engine.agent.cloud_client = mock_cloud_client
        monkeypatch.setattr("core.fast_router.FastRouter.match", lambda text: None)
        monkeypatch.setattr("tools.vision_tools.get_active_window_info", lambda: "Desktop")

        reply = engine.run("inspect and read cloud_target.py")
        assert "Cloud verified" in reply or "operational" in reply
        assert "<tool_call>" not in reply
