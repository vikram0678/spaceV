"""Bounded, operation-aware Celesto guest command timeout tests."""

from __future__ import annotations

import threading
import time

import pytest

from spacev.fleet.celesto_engine import CelestoSandboxInstance, SandboxExecutionResult
from tools.sandbox_tools import (
    DEFAULT_GUEST_COMMAND_TIMEOUT_SECONDS,
    SandboxSessionManager,
    _SandboxSession,
    guest_command_timeout_seconds,
)


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git clone https://github.com/psf/requests.git /tmp/requests", 180),
        (
            "git -c core.hooksPath=/dev/null clone --depth=1 -- https://github.com/psf/requests.git /tmp/requests\n"
            "grep -n timeout /tmp/requests/tests/test_requests.py",
            180,
        ),
        ("apk add --no-cache git", 180),
        ("python -m pytest tests/test_example.py::test_case", 300),
        ("grep -n timeout src/client.py", DEFAULT_GUEST_COMMAND_TIMEOUT_SECONDS),
    ],
)
def test_guest_command_timeout_uses_bounded_operation_profile(command, expected):
    assert guest_command_timeout_seconds(command) == expected


def test_guest_command_timeout_can_be_configured_with_env(monkeypatch):
    monkeypatch.setenv("SPACEV_SANDBOX_CLONE_TIMEOUT_SECONDS", "240")
    monkeypatch.setenv("SPACEV_SANDBOX_COMMAND_TIMEOUT_SECONDS", "45")

    assert guest_command_timeout_seconds("git clone https://github.com/example/repo.git /tmp/repo") == 240
    assert guest_command_timeout_seconds("grep -n timeout src/client.py") == 45


@pytest.mark.parametrize("value", ["0", "901", "not-a-number"])
def test_invalid_configured_guest_timeout_falls_back_safely(monkeypatch, value):
    monkeypatch.setenv("SPACEV_SANDBOX_CLONE_TIMEOUT_SECONDS", value)

    assert guest_command_timeout_seconds("git clone https://github.com/example/repo.git /tmp/repo") == 180


def test_celesto_engine_passes_selected_timeout_to_sdk(monkeypatch):
    class FakeComputer:
        def __init__(self):
            self.timeout = None

        def run(self, command, timeout):
            self.timeout = timeout
            return type("Result", (), {"exit_code": 0, "stdout": "done", "stderr": ""})()

    computer = FakeComputer()
    instance = CelestoSandboxInstance.__new__(CelestoSandboxInstance)
    instance.name = "sbx-timeouttest123456"
    instance._live_computer = computer
    instance.state = "ready"
    instance.command_count = 0
    instance.phase_timings_ms = {"command_ms": 0.0}
    monkeypatch.setattr("spacev.fleet.celesto_engine.safety_auditor.audit_and_execute", lambda *_: None)

    result = instance.run("git clone https://github.com/psf/requests.git /tmp/requests", timeout_seconds=180)

    assert result.exit_code == 0, result.stderr
    assert computer.timeout == 180


@pytest.mark.parametrize("timeout", [0, -1, 901, True, 1.5])
def test_celesto_engine_rejects_invalid_timeout(timeout):
    instance = CelestoSandboxInstance.__new__(CelestoSandboxInstance)

    with pytest.raises(ValueError, match="between 1 and 900"):
        instance.run("true", timeout_seconds=timeout)


def test_session_runner_records_timeout_and_uses_clone_profile():
    class FakeInstance:
        name = "sbx-test12345678"
        phase_timings_ms = {"command_ms": 12.0, "vm_startup_ms": 34.0}

        def __init__(self):
            self.timeout = None

        def run(self, command, timeout_seconds):
            self.timeout = timeout_seconds
            return SandboxExecutionResult(0, "cloned", "")

    manager = SandboxSessionManager.__new__(SandboxSessionManager)
    manager._lock = threading.RLock()
    manager._pending = {}
    instance = FakeInstance()
    now = time.monotonic()
    manager._sessions = {
        "session-test123456": _SandboxSession(
            session_id="session-test123456",
            task_description="Clone repo and inspect tests",
            instance=instance,
            started_at=now,
            last_activity=now,
        )
    }

    result = manager.run("session-test123456", "git clone https://github.com/psf/requests.git /tmp/requests")

    assert instance.timeout == 180
    assert "command_timeout_seconds\": 180" in result
    assert "exit code: 0" in result


class FlakyCleanupInstance:
    name = "sbx-cleanup12345678"
    phase_timings_ms = {"command_ms": 0.0, "vm_startup_ms": 2.0, "cleanup_ms": 1.0}

    def __init__(self):
        self.state = "ready"
        self.backend_error = ""
        self.close_attempts = 0
        self.commands = []

    def close(self):
        self.close_attempts += 1
        if self.close_attempts == 1:
            self.state = "cleanup_failed"
            self.backend_error = "Cleanup failed: synthetic delete error"
        else:
            self.state = "deleted"

    def run(self, command, timeout_seconds):
        self.commands.append(command)
        raise AssertionError("commands must not run after cleanup becomes uncertain")


def _manager_with_session(instance, *, started_at=None):
    manager = SandboxSessionManager.__new__(SandboxSessionManager)
    manager._lock = threading.RLock()
    manager._pending = {}
    now = time.monotonic()
    manager._sessions = {
        "session-cleanup123": _SandboxSession(
            session_id="session-cleanup123",
            task_description="Requests issue inspection",
            instance=instance,
            started_at=started_at if started_at is not None else now,
            last_activity=now,
        )
    }
    return manager


def test_failed_cleanup_retains_session_and_allows_explicit_retry():
    instance = FlakyCleanupInstance()
    manager = _manager_with_session(instance)

    first = manager.close("session-cleanup123")

    assert "[CELESTO SESSION CLEANUP FAILED]" in first
    assert manager.active_count() == 1
    assert "only close_sandbox_session" in manager.run("session-cleanup123", "echo unsafe").casefold()
    assert instance.commands == []

    second = manager.close("session-cleanup123")

    assert "[CELESTO SESSION CLOSED]" in second
    assert "state: deleted" in second
    assert manager.active_count() == 0


def test_expired_session_cleanup_failure_is_retained_for_close_only():
    instance = FlakyCleanupInstance()
    manager = _manager_with_session(
        instance,
        started_at=time.monotonic() - SandboxSessionManager.MAX_LIFETIME_SECONDS - 1,
    )

    manager.active_count()  # triggers expiration cleanup

    assert manager.active_count() == 1
    context = manager.continuation_context("close session-cleanup123")
    assert '"state": "cleanup_required"' in context
    assert "only close_sandbox_session" in manager.run("session-cleanup123", "git status --short").casefold()
    assert instance.commands == []
