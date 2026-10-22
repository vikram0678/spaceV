"""
Phase 5 Tests: Celesto MicroVM Isolation & Rollback Engine.
Validates sandbox lifecycles, safety hooks, cleanup on success/failure,
Step 7 deliberate failure detection, and automated snapshot rollback recovery.
"""
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.sandbox_tools import (
    CelestoSandboxRunner,
    StepWorkflowEngine,
    detonate_in_sandbox,
    run_sandboxed_workflow,
)


def test_sandbox_lifecycle_and_cleanup():
    """Verify pre-flight cleanup and post-execution teardown leave zero residual state."""
    runner = CelestoSandboxRunner(default_sandbox_id="sbx-test-clean")
    assert runner.pre_flight_cleanup() is True
    assert runner.is_running is False
    assert len(runner.snapshots) == 0

    # Start sandbox and capture snapshot
    runner.start_sandbox(vcpus=1, memory_mb=512)
    assert runner.is_running is True
    snap_id = runner.create_snapshot("checkpoint-1")
    assert "checkpoint-1" in runner.snapshots
    assert snap_id.startswith("snap-")

    # Teardown
    runner.teardown()
    assert runner.is_running is False
    assert len(runner.guest_state) == 0


def test_safety_hook_blocks_malicious_commands():
    """Verify that dangerous commands targeting host paths or exploit payloads are blocked by safety hooks."""
    runner = CelestoSandboxRunner(default_sandbox_id="sbx-test-sec")
    runner.start_sandbox()

    # Attempting to access protected host root
    res = runner.run_in_sandbox("cat /host_root/etc/shadow")
    assert res.blocked is True
    assert res.exit_code == 126
    assert "SECURITY_POLICY_VIOLATION" in res.stderr
    assert res.policy_violation in ("/host_root", "/etc/shadow")

    runner.teardown()


def test_snapshot_restore_integrity():
    """Verify state restoration rewinds guest microVM state to the exact snapshot point."""
    runner = CelestoSandboxRunner(default_sandbox_id="sbx-test-rollback")
    runner.start_sandbox()

    # State before snapshot
    runner.run_in_sandbox("echo 'pristine_version' > /tmp/app.py")
    assert runner.guest_state["files"].get("/tmp/app.py") == "pristine_version"

    # Take snapshot
    runner.create_snapshot("clean_state")

    # Corrupt or modify guest state
    runner.run_in_sandbox("echo 'corrupted_version' > /tmp/app.py")
    assert runner.guest_state["files"].get("/tmp/app.py") == "corrupted_version"

    # Restore snapshot
    runner.restore_snapshot("clean_state")
    assert runner.guest_state["files"].get("/tmp/app.py") == "pristine_version"

    runner.teardown()


def test_10_step_workflow_step_7_rollback_recovery():
    """Verify full 10-step workflow catches Step 7 failure, rolls back to Step 6, and heals to Step 10."""
    engine = StepWorkflowEngine()
    report = engine.execute_10_step_workflow("test_pipeline", auto_rollback=True)

    # Validate report metrics
    assert report.total_steps == 10
    assert report.steps_completed == 10
    assert report.failure_encountered is True
    assert report.failure_step == 7
    assert report.rollback_occurred is True
    assert report.restored_checkpoint == "step6_pre_detonation"
    assert report.recovery_status == "RECOVERED"
    assert report.host_compromised is False

    # Verify step reports structure
    step_nums = [r.step_num for r in report.step_reports]
    assert 6 in step_nums
    assert 7 in step_nums
    assert 10 in step_nums

    # Verify that step 7 has both a FAILED report and a subsequent HEALED report
    step7_reports = [r for r in report.step_reports if r.step_num == 7]
    assert len(step7_reports) == 2
    assert step7_reports[0].status == "FAILED"
    assert step7_reports[1].status == "HEALED"


def test_spacev_tool_integration():
    """Verify SpaceV native tool functions format clean user-facing reports."""
    # Test detonate_in_sandbox
    res_clean = detonate_in_sandbox("cat /etc/os-release")
    assert "CELLESTO MICROVM OUTPUT" in res_clean

    res_blocked = detonate_in_sandbox("echo hack > /host_root/bad.txt")
    assert "SANDBOX CONTAINMENT ALERT" in res_blocked

    # Test run_sandboxed_workflow
    wf_res = run_sandboxed_workflow("production_eval")
    assert "Celesto MicroVM 10-Step Workflow Complete" in wf_res
    assert "RECOVERED" in wf_res
    assert "Snapshot Rollback Executed: `True`" in wf_res
    assert "Host OS Compromised: `False`" in wf_res
