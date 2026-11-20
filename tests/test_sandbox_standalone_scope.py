"""Regression tests for immutable standalone Celesto task scopes."""

import re
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tools.sandbox_tools import (
    SandboxSessionManager,
    _SandboxSession,
    _build_approved_task_scope,
    validate_approved_guest_command,
)


SESSION_ID = "session-0123456789ab"
REPO_TASK = (
    "Inspect psf/requests issue #7639. Shallow-clone "
    "https://github.com/psf/requests.git to /tmp/requests-7639."
)


CALCULATOR_TASK = (
    "Create a Python calculator inside a new Celesto microVM. Inspect the environment, "
    "check Python availability, install Python if necessary, create a calculator, and test it. "
    "All operations must remain inside the Celesto guest. No host fallback or SpaceV project-file access is permitted."
)


def _manager_with_scope(task: str):
    manager = SandboxSessionManager()
    manager._reaper_stop.set()
    now = time.monotonic()
    instance = SimpleNamespace(
        state="ready",
        backend_error="",
        name="sbx-test",
        phase_timings_ms={"command_ms": 1.0, "vm_startup_ms": 0.0},
        run=Mock(return_value=SimpleNamespace(exit_code=0, stdout="ok", stderr="")),
    )
    scope = _build_approved_task_scope(task, workspace_id="0123456789ab")
    manager._sessions = {
        SESSION_ID: _SandboxSession(
            session_id=SESSION_ID,
            approved_task_scope=scope,
            instance=instance,
            started_at=now,
            last_activity=now,
        )
    }
    return manager, instance, scope


def test_repository_scope_keeps_existing_checkout_policy():
    scope = _build_approved_task_scope(REPO_TASK)

    assert scope.task_type == "repository"
    assert scope.repository_url == "https://github.com/psf/requests.git"
    assert scope.checkout_path == "/tmp/requests-7639"
    assert validate_approved_guest_command(
        scope,
        "git -C /tmp/requests-7639 grep -n -C 8 -E timeout HEAD -- src/requests/models.py",
    ) is None
    assert validate_approved_guest_command(scope, "git -C /tmp/other status --short")


def test_standalone_task_gets_a_unique_guest_workspace_bound_to_scope():
    scope = _build_approved_task_scope(CALCULATOR_TASK, workspace_id="0123456789ab")

    assert scope.task_type == "standalone"
    assert scope.workspace_path == "/tmp/spacev-task-0123456789ab"
    assert f"Approved guest workspace: {scope.workspace_path}" in scope.description
    assert scope.allow_install and scope.allow_file_changes and scope.allow_test_execution


def test_standalone_environment_inspection_chain_is_allowed_inside_guest():
    manager, instance, scope = _manager_with_scope(CALCULATOR_TASK)

    result = manager.run(
        SESSION_ID,
        "nproc && free -h && cat /etc/os-release && python3 --version",
    )

    assert "[CELESTO SESSION EXECUTION]" in result
    instance.run.assert_called_once()
    assert validate_approved_guest_command(scope, "nproc && free -h && cat /etc/os-release") is None


def test_standalone_install_file_creation_and_script_execution_require_approved_task():
    scope = _build_approved_task_scope(CALCULATOR_TASK, workspace_id="0123456789ab")
    workspace = scope.workspace_path

    assert validate_approved_guest_command(scope, "apk add --no-cache python3") is None
    assert validate_approved_guest_command(scope, f"mkdir -p {workspace}") is None
    assert validate_approved_guest_command(
        scope,
        f"cat > {workspace}/calculator.py <<'PY'\nprint(2 + 2)\nPY",
    ) is None
    assert validate_approved_guest_command(scope, f"python3 {workspace}/calculator.py") is None


def test_standalone_task_blocks_unapproved_commands_and_installation():
    scope = _build_approved_task_scope(
        "Inspect the environment and check the Python version.",
        workspace_id="0123456789ab",
    )

    assert validate_approved_guest_command(scope, "curl https://example.com")
    assert validate_approved_guest_command(scope, "apk add --no-cache python3")
    assert validate_approved_guest_command(scope, "rm -rf /tmp/spacev-task-0123456789ab")


def test_standalone_paths_outside_workspace_are_blocked():
    scope = _build_approved_task_scope(CALCULATOR_TASK, workspace_id="0123456789ab")

    assert validate_approved_guest_command(scope, "python3 /tmp/outside.py")
    assert validate_approved_guest_command(scope, "mkdir -p /tmp/other")
    assert validate_approved_guest_command(
        scope,
        "cat > /tmp/spacev-task-0123456789ab/../outside.py <<'PY'\nprint(1)\nPY",
    )


def test_denial_language_does_not_grant_install_edit_or_test_permissions():
    scope = _build_approved_task_scope(
        "Do not install dependencies, edit files, or run tests. Only inspect Python availability.",
        workspace_id="0123456789ab",
    )

    assert not scope.allow_install
    assert not scope.allow_file_changes
    assert not scope.allow_test_execution


def test_proposal_binds_workspace_to_exact_approval_and_session(monkeypatch):
    import tools.sandbox_tools as sandbox_tools

    manager = SandboxSessionManager()
    manager._reaper_stop.set()
    monkeypatch.setattr(
        sandbox_tools,
        "_celesto_readiness",
        lambda: {"mode": "celesto", "configured_for_real_execution": True, "blockers": []},
    )

    class FakeInstance:
        def __init__(self, name):
            self.state = "ready"
            self.backend_connected = True
            self.backend_error = ""
            self.name = name
            self.phase_timings_ms = {"vm_startup_ms": 1.0, "command_ms": 0.0, "cleanup_ms": 0.0}

        def close(self):
            self.state = "deleted"

    monkeypatch.setattr("spacev.fleet.celesto_engine.CelestoSandboxInstance", FakeInstance)
    proposal = manager.create(CALCULATOR_TASK)
    approval = re.search(r"approve sandbox task ([a-f0-9]{10})", proposal).group(0)
    approval_id = approval.rsplit(" ", 1)[1]
    approved_scope = manager._pending[approval_id][0]

    assert approved_scope.task_type == "standalone"
    assert approved_scope.workspace_path in proposal
    ready = manager.create("", approval_id=approval_id, approval_text=approval)

    assert "[CELESTO SESSION READY]" in ready
    session = next(iter(manager._sessions.values()))
    assert session.approved_task_scope is approved_scope
    assert session.approved_task_scope.workspace_path == approved_scope.workspace_path
    manager.close(session.session_id)


def test_invalid_approval_does_not_start_vm(monkeypatch):
    import tools.sandbox_tools as sandbox_tools

    manager = SandboxSessionManager()
    manager._reaper_stop.set()
    monkeypatch.setattr(
        sandbox_tools,
        "_celesto_readiness",
        lambda: {"mode": "celesto", "configured_for_real_execution": True, "blockers": []},
    )
    constructor = Mock(side_effect=AssertionError("VM must not start without exact approval"))
    monkeypatch.setattr("spacev.fleet.celesto_engine.CelestoSandboxInstance", constructor)
    proposal = manager.create(CALCULATOR_TASK)
    approval_id = re.search(r"approve sandbox task ([a-f0-9]{10})", proposal).group(1)

    result = manager.create("", approval_id=approval_id, approval_text="approve sandbox task wrong")

    assert result.startswith("BLOCKED: The exact approval phrase")
    constructor.assert_not_called()


def test_missing_session_does_not_execute_command():
    manager = SandboxSessionManager()
    manager._reaper_stop.set()

    result = manager.run(SESSION_ID, "nproc")

    assert result.startswith("BLOCKED: Celesto session is missing or expired")


def test_standalone_scope_is_immutable():
    manager, _instance, _scope = _manager_with_scope(CALCULATOR_TASK)

    with pytest.raises(AttributeError):
        manager._sessions[SESSION_ID].approved_task_scope.workspace_path = "/tmp/other"


def test_workspace_id_handling_is_idempotent_and_stable():
    initial_scope = _build_approved_task_scope(CALCULATOR_TASK, workspace_id="0123456789ab")
    assert initial_scope.workspace_path == "/tmp/spacev-task-0123456789ab"

    # Re-parsing the scoped description without passing workspace_id must preserve the existing ID
    second_scope = _build_approved_task_scope(initial_scope.description)
    assert second_scope.workspace_path == "/tmp/spacev-task-0123456789ab"
    assert second_scope.description.count("Approved guest workspace:") == 1

    # Re-parsing with the matching workspace_id is also idempotent
    matching_scope = _build_approved_task_scope(initial_scope.description, workspace_id="0123456789ab")
    assert matching_scope.workspace_path == "/tmp/spacev-task-0123456789ab"
    assert matching_scope.description.count("Approved guest workspace:") == 1


def test_conflicting_workspace_id_is_safely_rejected():
    task_with_workspace = f"{CALCULATOR_TASK}\nApproved guest workspace: /tmp/spacev-task-0123456789ab"

    with pytest.raises(ValueError, match="conflicts with existing approved workspace ID"):
        _build_approved_task_scope(task_with_workspace, workspace_id="fedcba987654")


def test_multiple_conflicting_workspaces_are_safely_rejected():
    task_with_conflicts = (
        f"{CALCULATOR_TASK}\n"
        "Approved guest workspace: /tmp/spacev-task-0123456789ab\n"
        "Approved guest workspace: /tmp/spacev-task-fedcba987654"
    )

    with pytest.raises(ValueError, match="multiple conflicting approved guest workspaces"):
        _build_approved_task_scope(task_with_conflicts)


def test_malformed_existing_workspace_path_is_rejected():
    task_with_malformed = f"{CALCULATOR_TASK}\nApproved guest workspace: /tmp/spacev-task-badid"

    with pytest.raises(ValueError, match="not a valid isolated workspace path"):
        _build_approved_task_scope(task_with_malformed)


def test_plain_unapproved_string_fails_closed_in_validator():
    # Plain strings must NEVER be synthesized into an approved standalone scope
    result1 = validate_approved_guest_command(CALCULATOR_TASK, "cat /etc/os-release")
    assert result1 == "the approved task does not define a repository and checkout path that can be safely enforced"

    result2 = validate_approved_guest_command("Install dependencies and create files", "apk add --no-cache python3")
    assert result2 == "the approved task does not define a repository and checkout path that can be safely enforced"

    # Only an authentic _ApprovedTaskScope can authorize standalone execution
    valid_scope = _build_approved_task_scope(CALCULATOR_TASK, workspace_id="0123456789ab")
    assert validate_approved_guest_command(valid_scope, "cat /etc/os-release") is None

