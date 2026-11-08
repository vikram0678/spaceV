"""
Unit and integration tests for SpaceV Data Contracts, Schemas & Token Accounting Ledger (Volume IV).
Tests:
- §27 Core Event Schemas (all 10 event dataclasses)
- §28 Agent Message Protocols & validation
- §29 DAG Node and Edge specifications & acyclic graph validation
- §30 Token Accounting Ledger (append-only JSONL, daily rotation, analytics)
"""
from __future__ import annotations

import json
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

from core.schemas.dag import (
    validate_dag_graph,
    validate_edge_schema,
    validate_node_schema,
)
from core.schemas.events import (
    AgentTaskEvent,
    FileChangeEvent,
    RateLimitEvent,
    ScreenChangeEvent,
    TerminalEvent,
    TokenBudgetEvent,
    VoiceActivityEvent,
    VoiceInputEvent,
    WakeWordEvent,
    WorkflowEvent,
)
from core.schemas.protocols import (
    AuditResultMessage,
    CodeReadyMessage,
    PlanReadyMessage,
    validate_agent_message,
)
from core.token_harness import SpaceVTokenHarness
from core.token_ledger import TokenLedger


class TestEventSchemas:
    """Tests §27 Core Event Schemas."""

    def test_voice_input_event(self):
        ev = VoiceInputEvent(text="create a microservice", confidence=0.98, language="en", duration_ms=1200, is_wake_word_triggered=True)
        d = asdict(ev)
        assert d["text"] == "create a microservice"
        assert d["confidence"] == 0.98
        assert d["is_wake_word_triggered"] is True

    def test_voice_activity_event(self):
        ev = VoiceActivityEvent(is_speaking=True, vad_probability=0.92, timestamp=time.time())
        d = asdict(ev)
        assert d["is_speaking"] is True
        assert d["vad_probability"] == 0.92

    def test_wake_word_event(self):
        ev = WakeWordEvent(keyword="hey spacev", confidence=0.99)
        d = asdict(ev)
        assert d["keyword"] == "hey spacev"
        assert d["confidence"] == 0.99

    def test_screen_change_event(self):
        ev = ScreenChangeEvent(
            change_type="app_switch",
            similarity_score=0.45,
            active_window_title="VS Code - main.py",
            timestamp=time.time(),
            screenshot_path="/tmp/shot.png",
        )
        d = asdict(ev)
        assert d["change_type"] == "app_switch"
        assert d["active_window_title"] == "VS Code - main.py"
        assert d["screenshot_path"] == "/tmp/shot.png"

    def test_file_change_event(self):
        ev = FileChangeEvent(
            event_type="modified",
            file_path="/home/user/project/main.py",
            relative_path="main.py",
            extension=".py",
            size_bytes=1024,
            timestamp=time.time(),
            is_directory=False,
            is_code_file=True,
            is_config_file=False,
            is_test_file=False,
        )
        d = asdict(ev)
        assert d["event_type"] == "modified"
        assert d["is_code_file"] is True

    def test_terminal_event(self):
        ev = TerminalEvent(
            event_type="error_detected",
            terminal_id="term_1",
            matched_pattern="Traceback",
            matched_text="Traceback (most recent call last):",
            context_lines=["Traceback", "  File 'main.py', line 10"],
            timestamp=time.time(),
            severity="error",
        )
        d = asdict(ev)
        assert d["event_type"] == "error_detected"
        assert len(d["context_lines"]) == 2

    def test_agent_task_event(self):
        ev = AgentTaskEvent(
            task_id="task_123",
            agent_role="planner",
            event_type="completed",
            instruction="Create DAG plan",
            result={"status": "ok"},
            tokens_used=450,
            duration_sec=1.2,
        )
        d = asdict(ev)
        assert d["task_id"] == "task_123"
        assert d["tokens_used"] == 450

    def test_workflow_event(self):
        ev = WorkflowEvent(
            workflow_id="wf_001",
            event_type="node_done",
            workflow_name="code_gen",
            node_id="node_1",
            node_name="implement_auth",
            total_tokens=1200,
        )
        d = asdict(ev)
        assert d["workflow_id"] == "wf_001"
        assert d["node_id"] == "node_1"

    def test_token_budget_event(self):
        ev = TokenBudgetEvent(
            event_type="warning",
            used_tokens=4800,
            max_tokens=6000,
            utilization_percent=80.0,
            provider="groq",
        )
        d = asdict(ev)
        assert d["event_type"] == "warning"
        assert d["utilization_percent"] == 80.0

    def test_rate_limit_event(self):
        ev = RateLimitEvent(
            event_type="provider_switched",
            provider="groq",
            estimated_tokens=1500,
            available_tokens=200,
            fallback_provider="cerebras",
        )
        d = asdict(ev)
        assert d["event_type"] == "provider_switched"
        assert d["fallback_provider"] == "cerebras"


class TestAgentMessageProtocols:
    """Tests §28 Agent Message Protocols."""

    def test_planner_to_coder_valid(self):
        payload = {
            "workflow_id": "wf_123",
            "node_instructions": ["Step 1: Create model", "Step 2: Add endpoint"],
            "context_ref": ".spacev/workflows/wf_123.json",
        }
        msg = PlanReadyMessage(
            workflow_id=payload["workflow_id"],
            node_instructions=payload["node_instructions"],
            context_ref=payload["context_ref"],
        )
        assert msg.to_dict()["workflow_id"] == "wf_123"
        valid, err = validate_agent_message("planner_to_coder", payload)
        assert valid is True
        assert err == ""

    def test_planner_to_coder_missing_field(self):
        payload = {
            "workflow_id": "wf_123",
            # missing node_instructions and context_ref
        }
        valid, err = validate_agent_message("planner_to_coder", payload)
        assert valid is False
        assert "Missing required field" in err

    def test_coder_to_auditor_valid(self):
        payload = {
            "files_changed": ["core/auth.py", "tests/test_auth.py"],
            "diff_ref": ".spacev/diffs/diff_1.diff",
            "test_command": "pytest tests/test_auth.py",
        }
        msg = CodeReadyMessage(
            files_changed=payload["files_changed"],
            diff_ref=payload["diff_ref"],
            test_command=payload["test_command"],
        )
        assert msg.files_changed == ["core/auth.py", "tests/test_auth.py"]
        valid, _ = validate_agent_message("coder_to_auditor", payload)
        assert valid is True

    def test_auditor_result_valid_and_invalid(self):
        valid_payload = {
            "verdict": "PASS",
            "evidence": "All 5 tests passed in 0.45s",
            "issues": [],
        }
        msg = AuditResultMessage(
            verdict="PASS",
            evidence="All 5 tests passed in 0.45s",
            issues=[],
        )
        assert msg.verdict == "PASS"
        valid, _ = validate_agent_message("auditor_result", valid_payload)
        assert valid is True

        # Invalid verdict
        invalid_payload = {
            "verdict": "MAYBE",
            "evidence": "Not sure",
            "issues": [],
        }
        valid, err = validate_agent_message("auditor_result", invalid_payload)
        assert valid is False
        assert "Verdict must be 'PASS' or 'FAIL'" in err

    def test_token_limit_exceeded(self):
        # Auditor max tokens is 200 (~800 characters)
        bloated_evidence = "x" * 2000
        payload = {
            "verdict": "FAIL",
            "evidence": bloated_evidence,
            "issues": ["Issue 1"],
        }
        valid, err = validate_agent_message("auditor_result", payload)
        assert valid is False
        assert "exceeds maximum allowed" in err


class TestDAGSchemaAndValidation:
    """Tests §29 DAG Node & Edge Definitions."""

    def test_node_schema_validation(self):
        # Valid action node
        action_node = {
            "node_id": "node_1",
            "name": "Write code",
            "agent": "coder",
            "action": "generate_code",
            "type": "action",
        }
        valid, err = validate_node_schema("action", action_node)
        assert valid is True
        assert err == ""

        # Missing required field in action node
        invalid_action = {
            "node_id": "node_1",
            "name": "Write code",
            # missing agent and action
        }
        valid, err = validate_node_schema("action", invalid_action)
        assert valid is False
        assert "Missing required field 'agent'" in err

        # Valid condition node
        cond_node = {
            "node_id": "node_cond",
            "name": "Check Tests",
            "condition": "tests_passed == True",
        }
        valid, _ = validate_node_schema("condition", cond_node)
        assert valid is True

    def test_edge_schema_validation(self):
        valid, err = validate_edge_schema("dependency")
        assert valid is True

        valid, err = validate_edge_schema("unknown_edge_type")
        assert valid is False
        assert "Unknown edge type" in err

    def test_dag_graph_validation_acyclic(self):
        nodes = [
            {"node_id": "plan", "name": "Plan", "type": "action", "agent": "planner", "action": "create_plan"},
            {"node_id": "code", "name": "Code", "type": "action", "agent": "coder", "action": "write_code"},
            {"node_id": "audit", "name": "Audit", "type": "action", "agent": "auditor", "action": "review_code"},
        ]
        edges = [
            {"source": "plan", "target": "code", "type": "dependency"},
            {"source": "code", "target": "audit", "type": "dependency"},
        ]
        valid, err = validate_dag_graph(nodes, edges)
        assert valid is True
        assert err == ""

    def test_dag_graph_validation_cycle_detection(self):
        nodes = [
            {"node_id": "node_a", "name": "A", "type": "action", "agent": "coder", "action": "step_a"},
            {"node_id": "node_b", "name": "B", "type": "action", "agent": "coder", "action": "step_b"},
        ]
        # Circular edge: A -> B and B -> A
        edges = [
            {"source": "node_a", "target": "node_b", "type": "dependency"},
            {"source": "node_b", "target": "node_a", "type": "dependency"},
        ]
        valid, err = validate_dag_graph(nodes, edges)
        assert valid is False
        assert "Cycle detected" in err

    def test_dag_graph_missing_target_node(self):
        nodes = [
            {"node_id": "node_a", "name": "A", "type": "action", "agent": "coder", "action": "step_a"},
        ]
        edges = [
            {"source": "node_a", "target": "missing_node", "type": "dependency"},
        ]
        valid, err = validate_dag_graph(nodes, edges)
        assert valid is False
        assert "references non-existent target" in err


class TestTokenLedger:
    """Tests §30 Token Accounting Ledger."""

    def test_ledger_append_and_rotation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = TokenLedger(ledger_dir=tmpdir)

            entry1 = ledger.record_turn(
                provider="groq",
                model="llama-3.3-70b-versatile",
                agent="coder",
                input_tokens=800,
                output_tokens=300,
                pre_tokens=2400,
                post_tokens=800,
                bucket_before=5000,
                bucket_after=3900,
                workflow_id="wf_test",
                node_id="n_code",
            )

            assert entry1.turn_number == 1
            assert entry1.total_tokens == 1100
            assert entry1.reduction_percent == 66.67

            entry2 = ledger.record_turn(
                provider="cerebras",
                model="llama-3.3-70b",
                agent="auditor",
                input_tokens=400,
                output_tokens=150,
                pre_tokens=1200,
                post_tokens=400,
            )

            assert entry2.turn_number == 2
            assert entry2.total_tokens == 550

            # Verify files on disk
            primary_file = Path(tmpdir) / "token_ledger.jsonl"
            assert primary_file.exists()

            with open(primary_file, encoding="utf-8") as f:
                lines = [json.loads(line.strip()) for line in f if line.strip()]
            assert len(lines) == 2
            assert lines[0]["provider"] == "groq"
            assert lines[1]["provider"] == "cerebras"

            # Verify daily rotated file exists
            today_str = time.strftime("%Y-%m-%d")
            daily_file = Path(tmpdir) / f"token_ledger_{today_str}.jsonl"
            assert daily_file.exists()

            # Verify query
            entries = ledger.get_entries(limit=10)
            assert len(entries) == 2
            assert entries[0].provider == "groq"
            assert entries[1].provider == "cerebras"

            # Verify summary analytics
            summary = ledger.get_summary()
            assert summary["total_turns"] == 2
            assert summary["total_tokens_consumed"] == 1650
            assert summary["total_tokens_saved"] == (2400 - 800) + (1200 - 400)
            assert summary["tokens_by_provider"]["groq"] == 1100
            assert summary["tokens_by_provider"]["cerebras"] == 550
            assert summary["tokens_by_agent"]["coder"] == 1100
            assert summary["tokens_by_agent"]["auditor"] == 550

    def test_harness_integration_with_ledger(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_ledger = TokenLedger(ledger_dir=tmpdir)
            import core.token_ledger
            monkeypatch.setattr(core.token_ledger, "token_ledger", test_ledger)

            harness = SpaceVTokenHarness()
            harness.record_usage(
                provider="groq",
                input_tokens=600,
                output_tokens=200,
                model="llama-3.3-70b-versatile",
                agent="planner",
            )

            entries = test_ledger.get_entries(limit=1)
            assert len(entries) == 1
            assert entries[0].agent == "planner"
            assert entries[0].total_tokens == 800
