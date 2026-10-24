"""
SpaceV Comprehensive Reliability, Truth Gatekeeper, State Machine, and Ledger Test Suite.
Validates:
1. Karpathy Truth Gatekeeper (File, JSON, CSV, Python AST syntax postconditions)
2. Anti-Hallucination & Truth Enforcement (Zero false-positive success reporting)
3. Task State Machine (Allowed vs Illegal transitions, Bounded retries, Cancellation)
4. Durable SQLite WAL Ledger (ACID logging, Verification records, Interrupted task recovery)
5. Tool Execution & Strict Argument Validation (Normalized envelope, Environment tagging)
6. Autonomous Mission Commander (Topological task dependencies, Postcondition verification)
"""

import json
import os
import tempfile
import pytest
from pathlib import Path

from core.truth_gatekeeper import truth_gatekeeper, VerificationResult
from core.task_state_machine import TaskStateMachine, TASK_STATES
from core.durable_ledger import DurableLedger
from core.mission_commander import MissionCommander
from tools.registry import execute_tool, execute_tool_normalized


# ============================================================================
# 1. TRUTH GATEKEEPER TESTS
# ============================================================================

def test_truth_gatekeeper_nonexistent_file():
    """TST-01: Proves gatekeeper rejects claim of file creation when file is missing."""
    res = truth_gatekeeper.verify_file_postcondition("nonexistent_ghost_file_12345.txt", location="Desktop")
    assert not res.passed
    assert res.status == "FAIL"
    assert "does not exist on disk" in res.error


def test_truth_gatekeeper_valid_file_and_content():
    """TST-02: Verifies file existence, minimum byte size, and content matching."""
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as tf:
        tf.write("SpaceV Autonomous Workforce Telemetry 2026\nStatus: Verified\n")
        temp_path = tf.name

    try:
        # Check passes with matching content
        res = truth_gatekeeper.verify_file_postcondition(temp_path, expected_content="Status: Verified", min_bytes=10)
        assert res.passed
        assert res.evidence.get("sha256") is not None
        assert res.evidence.get("file_size") > 0

        # Check fails when content doesn't match
        res_mismatch = truth_gatekeeper.verify_file_postcondition(temp_path, expected_content="NONEXISTENT_KEYWORD")
        assert not res_mismatch.passed
        assert "does not contain expected snippet" in res_mismatch.error
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_truth_gatekeeper_json_validation():
    """TST-03: Proves gatekeeper validates JSON syntax and catches missing required keys."""
    # Valid JSON
    valid_json = '{"mission_id": "msn_001", "status": "COMPLETED", "tasks_count": 5}'
    res_valid = truth_gatekeeper.verify_json_postcondition(valid_json, required_keys=["mission_id", "status"])
    assert res_valid.passed

    # Missing required key
    res_missing = truth_gatekeeper.verify_json_postcondition(valid_json, required_keys=["mission_id", "cost_usd"])
    assert not res_missing.passed
    assert "missing required keys" in res_missing.error

    # Malformed JSON
    malformed_json = '{"mission_id": "msn_001", "status": '
    res_malformed = truth_gatekeeper.verify_json_postcondition(malformed_json)
    assert not res_malformed.passed
    assert "not valid JSON" in res_malformed.error


def test_truth_gatekeeper_csv_validation():
    """TST-04: Verifies CSV structure, row count, and required column headers."""
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".csv") as tf:
        tf.write("id,hostname,status\n1,sbx-worker01,active\n2,sbx-worker02,standby\n")
        temp_csv = tf.name

    try:
        # Valid CSV check
        res = truth_gatekeeper.verify_csv_postcondition(temp_csv, min_rows=2, required_columns=["id", "hostname", "status"])
        assert res.passed
        assert res.observed.get("data_row_count") == 2

        # Missing column check
        res_col_fail = truth_gatekeeper.verify_csv_postcondition(temp_csv, required_columns=["id", "ip_address"])
        assert not res_col_fail.passed
        assert "missing required columns" in res_col_fail.error

        # Row count failure check
        res_row_fail = truth_gatekeeper.verify_csv_postcondition(temp_csv, min_rows=10)
        assert not res_row_fail.passed
        assert "expected at least 10" in res_row_fail.error
    finally:
        if os.path.exists(temp_csv):
            os.remove(temp_csv)


def test_truth_gatekeeper_python_syntax():
    """TST-05: Proves AST parser detects syntax errors and passes valid code."""
    valid_code = "def calculate_hash(data):\n    return data.strip().upper()\n"
    res_valid = truth_gatekeeper.verify_python_syntax(valid_code)
    assert res_valid.passed

    invalid_code = "def broken_func(:\n    return False\n"
    res_invalid = truth_gatekeeper.verify_python_syntax(invalid_code)
    assert not res_invalid.passed
    assert "SyntaxError" in res_invalid.error


# ============================================================================
# 2. ANTI-HALLUCINATION & TRUTHFUL REPORTING TESTS
# ============================================================================

def test_truth_enforcement_overrides_false_success():
    """TST-06: Proves false-success narrative is overridden when tool execution failed."""
    failing_tool_results = [
        {"name": "create_file", "args": {"file_name": "audit.csv"}, "status": "failed", "result": "Failed: Permission denied"}
    ]
    hallucinated_model_response = "I have successfully created your audit.csv file on your desktop, Sir. All done!"

    truthful_response = truth_gatekeeper.audit_and_enforce_truth(
        hallucinated_model_response,
        failing_tool_results,
        user_prompt="Create audit.csv"
    )

    # Must NOT claim success!
    assert "successfully created" not in truthful_response.lower()
    assert "roadblock" in truthful_response.lower() or "encountered" in truthful_response.lower()
    assert "create_file" in truthful_response


def test_truth_enforcement_preserves_genuine_success():
    """TST-07: Proves genuine successful responses are untouched."""
    successful_tool_results = [
        {"name": "get_system_stats", "args": {}, "status": "success", "result": "CPU: 12%, RAM: 42%"}
    ]
    model_response = "Your system is currently running optimally at 12% CPU usage, Sir."

    clean_response = truth_gatekeeper.audit_and_enforce_truth(
        model_response,
        successful_tool_results,
        user_prompt="Check system stats"
    )

    assert clean_response == model_response


# ============================================================================
# 3. TASK STATE MACHINE TESTS
# ============================================================================

def test_task_state_machine_valid_lifecycle():
    """TST-08: Verifies formal state lifecycle transitions."""
    sm = TaskStateMachine("task_001", "Run security audit")
    assert sm.current_state == "CREATED"

    sm.transition_to("PLANNED", "Decomposed into steps")
    assert sm.current_state == "PLANNED"

    sm.transition_to("READY", "Worker allocated")
    assert sm.current_state == "READY"

    sm.transition_to("RUNNING", "Worker execution active")
    assert sm.current_state == "RUNNING"

    sm.transition_to("VERIFYING", "Running postcondition checks")
    assert sm.current_state == "VERIFYING"

    sm.transition_to("COMPLETED", "Postconditions passed")
    assert sm.current_state == "COMPLETED"
    assert sm.is_terminal()
    assert len(sm.history) == 6


def test_task_state_machine_illegal_transition_rejection():
    """TST-09: Proves state machine rejects illegal transition (e.g. RUNNING directly to COMPLETED)."""
    sm = TaskStateMachine("task_002", "Compile code")
    sm.transition_to("PLANNED")
    sm.transition_to("READY")
    sm.transition_to("RUNNING")

    with pytest.raises(ValueError) as excinfo:
        # Bypassing VERIFYING directly to COMPLETED is prohibited by invariant
        sm.transition_to("COMPLETED")

    assert "Illegal state transition" in str(excinfo.value)
    assert sm.current_state == "RUNNING"


def test_task_state_machine_bounded_retries():
    """TST-10: Proves bounded retry budget is strictly enforced (max 2 retries)."""
    sm = TaskStateMachine("task_003", "Connect to service", max_retries=2)
    sm.transition_to("PLANNED")
    sm.transition_to("READY")
    sm.transition_to("RUNNING")
    sm.transition_to("VERIFYING")

    # Retry 1
    assert sm.increment_retry("Transient network error")
    assert sm.current_state == "RETRY_PENDING"
    assert sm.retry_count == 1

    sm.transition_to("READY")
    sm.transition_to("RUNNING")
    sm.transition_to("VERIFYING")

    # Retry 2
    assert sm.increment_retry("Second timeout")
    assert sm.current_state == "RETRY_PENDING"
    assert sm.retry_count == 2

    sm.transition_to("READY")
    sm.transition_to("RUNNING")
    sm.transition_to("VERIFYING")

    # Retry 3 -> Budget exhausted, transitions to FAILED
    can_retry = sm.increment_retry("Third failure")
    assert not can_retry
    assert sm.current_state == "FAILED"
    assert sm.is_terminal()


# ============================================================================
# 4. DURABLE SQLITE WAL LEDGER TESTS
# ============================================================================

def test_durable_ledger_wal_mode_and_acid_persistence():
    """TST-11: Verifies SQLite database operates in WAL mode with ACID durability."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_db = Path(tf.name)

    try:
        ledger = DurableLedger(db_path=temp_db)
        with ledger._get_connection() as conn:
            cursor = conn.execute("PRAGMA journal_mode;")
            journal_mode = cursor.fetchone()[0]
            assert journal_mode.lower() == "wal"

        # Record mission and task nodes
        ledger.record_mission("msn_test_100", "Detonation pipeline", "RUNNING")
        ledger.record_task_node("task_101", "Provision MicroVM", "SandboxExecutor", "COMPLETED", mission_id="msn_test_100")
        ledger.record_event("task_101", "SNAPSHOT_CAPTURED", {"step": 6, "name": "pre_detonation"})
        ledger.record_verification("task_101", "file_exists", "PASS", {"path": "test.txt"}, {"path": "test.txt"})

        # Query uncompleted tasks
        ledger.record_task_node("task_102", "Detonate Untrusted Package", "SandboxExecutor", "RUNNING", mission_id="msn_test_100")
        uncompleted = ledger.get_uncompleted_tasks()
        assert len(uncompleted) == 1
        assert uncompleted[0]["task_id"] == "task_102"
    finally:
        if os.path.exists(temp_db):
            os.remove(temp_db)


# ============================================================================
# 5. TOOL NORMALIZATION & ARGUMENT VALIDATION TESTS
# ============================================================================

def test_tool_normalized_execution_and_environment_tagging():
    """TST-12: Verifies execute_tool_normalized tags host vs celesto_microvm environment."""
    # Host tool
    host_res = execute_tool_normalized("get_current_time", {})
    assert host_res.success
    assert host_res.status == "success"
    assert host_res.metadata.get("environment") == "host_process"

    # Sandbox tool
    sandbox_res = execute_tool_normalized("audit_sandbox_containment", {})
    assert sandbox_res.metadata.get("environment") == "celesto_microvm"

    # Unknown tool
    unknown_res = execute_tool_normalized("nonexistent_fake_tool_xyz", {})
    assert not unknown_res.success
    assert unknown_res.status == "invocation_error"
    assert "not recognized" in unknown_res.error


# ============================================================================
# 6. AUTONOMOUS MISSION COMMANDER TESTS
# ============================================================================

def test_mission_commander_end_to_end_execution():
    """TST-13: Verifies end-to-end topological mission execution with postcondition checks."""
    cmdr = MissionCommander(objective="Create and verify status report")

    task_plan = [
        {
            "task_id": "step_1_create",
            "name": "Create report file",
            "worker_role": "ResearchWorker",
            "payload": {
                "tool_name": "create_file",
                "arguments": {
                    "file_name": "test_mission_report.txt",
                    "content": "Status: All Systems Operational 2026\n",
                    "location": "Workspace"
                }
            },
            "postcondition_check": "file_exists",
            "postcondition_args": {"file_name": "test_mission_report.txt", "location": "Workspace"}
        }
    ]

    cmdr.plan_mission(task_plan)
    assert cmdr.state_machine.current_state == "READY"

    mission_summary = cmdr.execute_mission()
    assert mission_summary["status"] == "COMPLETED"
    assert mission_summary["completed_tasks"] == 1
    assert mission_summary["failed_tasks"] == 0

    # Cleanup created test file
    test_file = Path("test_mission_report.txt")
    if test_file.exists():
        test_file.unlink()
