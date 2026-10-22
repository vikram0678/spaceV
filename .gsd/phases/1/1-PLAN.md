---
phase: 1
plan: 1
wave: 1
---

# Plan 1.1: Celesto MicroVM Isolation & Rollback Engine

## Objective
Implement reliable Celesto Firecracker MicroVM execution for SpaceV with explicit guest isolation, automatic pre-flight & teardown cleanup, and automated snapshot rollback recovery when step 7 of a 10-step autonomous workflow encounters a failure.

## Context
- .gsd/SPEC.md
- .gsd/ARCHITECTURE.md
- tools/gui_tools.py
- config.py

## Tasks

<task type="auto">
  <name>Implement CelestoSandboxRunner</name>
  <files>tools/sandbox_tools.py</files>
  <action>
    Create `CelestoSandboxRunner` class with:
    - `run_in_sandbox(command: str, timeout_sec: int)`: Executes commands inside guest microVM / sandbox.
    - `pre_flight_cleanup()` and `teardown()`: Guarantees zero residual state, uncleaned containers, or leaked sockets on both success and failure.
    - Air-gapped guest environment isolation: untrusted commands never execute on the host OS.
  </action>
  <verify>.venv/bin/python -c "from tools.sandbox_tools import CelestoSandboxRunner; r = CelestoSandboxRunner(); assert hasattr(r, 'run_in_sandbox')"</verify>
  <done>CelestoSandboxRunner is importable and implements execution + cleanup lifecycle.</done>
</task>

<task type="auto">
  <name>Implement Step 7/10 Rollback Recovery Engine</name>
  <files>tools/sandbox_tools.py</files>
  <action>
    Create `StepWorkflowEngine` inside `tools/sandbox_tools.py`:
    - Executes multi-step agent plans (steps 1 through 10).
    - Takes automatic microVM snapshot checkpoints before risky steps (at step 6).
    - Injects or detects failure at step 7.
    - Automatically rolls back to the step 6 snapshot checkpoint, heals the execution parameter/tool call, and resumes forward to complete step 10 successfully.
  </action>
  <verify>.venv/bin/python -c "from tools.sandbox_tools import StepWorkflowEngine; e = StepWorkflowEngine(); assert hasattr(e, 'execute_10_step_workflow')"</verify>
  <done>StepWorkflowEngine successfully detects step 7 failure, executes snapshot rollback, and completes steps 1-10.</done>
</task>

<task type="auto">
  <name>Create Phase 1 Pytest Suite</name>
  <files>tests/test_phase5_celesto_sandbox.py</files>
  <action>
    Write comprehensive unit and integration tests:
    - Test 1: Verify pre-flight and post-execution cleanup works on success and exception.
    - Test 2: Verify deliberate failure at Step 7 is caught and isolated.
    - Test 3: Verify rollback to Step 6 snapshot and successful progression through Step 10.
    - Test 4: Verify zero host file modification during guest execution.
  </action>
  <verify>.venv/bin/pytest tests/test_phase5_celesto_sandbox.py -v</verify>
  <done>All Phase 1 tests pass 100% green.</done>
</task>

## Success Criteria
- [ ] `tools/sandbox_tools.py` created with `CelestoSandboxRunner` and `StepWorkflowEngine`
- [ ] Automatic cleanup operates on success and failure
- [ ] Step 7/10 failure triggers snapshot rollback recovery to step 10
- [ ] `pytest tests/test_phase5_celesto_sandbox.py` passes 100%
- [ ] Existing 41 SpaceV tests remain 100% green
