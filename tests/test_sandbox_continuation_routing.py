"""Focused regression tests for safe Celesto session continuation routing."""

import time
import sys
import types
from types import SimpleNamespace
from unittest.mock import Mock

# The graph imports an optional UI thread class at module load. Keep this
# headless routing test independent from the workstation's PyQt installation.
try:
    import PyQt6.QtCore  # noqa: F401
except ImportError:
    pyqt_package = types.ModuleType("PyQt6")
    pyqt_core = types.ModuleType("PyQt6.QtCore")
    pyqt_core.QThread = type("QThread", (), {})
    pyqt_core.pyqtSignal = lambda *_args, **_kwargs: object()
    pyqt_package.QtCore = pyqt_core
    sys.modules.setdefault("PyQt6", pyqt_package)
    sys.modules.setdefault("PyQt6.QtCore", pyqt_core)

import core.graph_engine as graph_engine_module
from core.graph_engine import (
    SpaceVGraphEngine,
    active_sandbox_tool_names,
    bind_active_sandbox_session_id,
    sandbox_continuation_requested,
)
from tools.sandbox_tools import SandboxSessionManager, _ApprovedTaskScope, _SandboxSession


SESSION_ID = "session-0123456789ab"
SANDBOX_CONTEXT = (
    "[Persisted sandbox task state]\n"
    '{"state":"active_approved_session","session_id":"session-0123456789ab",'
    '"approved_task":"Inspect psf/requests issue #7639 timeout handling. Shallow-clone '
    'https://github.com/psf/requests.git to /tmp/requests-7639.","cleanup_error":""}'
)


def _manager_with_active_session():
    manager = SandboxSessionManager()
    manager._reaper_stop.set()
    now = time.monotonic()
    instance = SimpleNamespace(state="ready", backend_error="")
    manager._sessions = {
        SESSION_ID: _SandboxSession(
            session_id=SESSION_ID,
            approved_task_scope=_ApprovedTaskScope(
                "Inspect psf/requests issue #7639 timeout handling. Shallow-clone "
                "https://github.com/psf/requests.git to /tmp/requests-7639."
            ),
            instance=instance,
            started_at=now,
            last_activity=now,
        )
    }
    return manager


def test_manager_resolves_active_session_from_user_supplied_id_without_vm():
    manager = _manager_with_active_session()

    payload, error = manager.resolve_active_continuation(
        f"Continue the approved task in existing Celesto session {SESSION_ID}."
    )

    assert error is None
    assert payload["session_id"] == SESSION_ID
    assert payload["state"] == "active_approved_session"


def test_manager_resolves_by_matching_task_without_asking_for_session_id():
    manager = _manager_with_active_session()

    payload, error = manager.resolve_active_continuation(
        "Continue the approved psf/requests issue #7639 timeout inspection in the existing Celesto session."
    )

    assert error is None
    assert payload["session_id"] == SESSION_ID


def test_malformed_explicit_session_id_is_rejected_without_task_fallback():
    manager = _manager_with_active_session()

    payload, error = manager.resolve_active_continuation(
        "Continue the approved psf/requests issue #7639 timeout task in session-not-a-valid-id."
    )

    assert payload is None
    assert "malformed" in error
    assert sandbox_continuation_requested("Continue session-session-0123456789ab/other")


def test_different_issue_number_cannot_match_same_repository_task():
    manager = _manager_with_active_session()

    payload, error = manager.resolve_active_continuation(
        "Continue the approved psf/requests issue #7640 timeout inspection."
    )

    assert payload is None
    assert "does not identify" in error

    payload, url_error = manager.resolve_active_continuation(
        "Continue the approved task https://github.com/psf/requests/issues/7640."
    )
    assert payload is None
    assert "does not identify" in url_error


def test_generic_shared_keywords_cannot_select_a_session():
    manager = _manager_with_active_session()

    assert not manager._task_scope_matches(
        "Continue the Requests issue timeout task",
        "Inspect psf/requests issue #7639 timeout handling",
    )


def test_manager_rejects_session_or_task_scope_mismatch():
    manager = _manager_with_active_session()

    payload, id_error = manager.resolve_active_continuation(
        "Continue the approved task in existing Celesto session session-aaaaaaaaaaaa."
    )
    assert payload is None
    assert "does not match" in id_error

    payload, task_error = manager.resolve_active_continuation(
        "Continue a different Celesto task for another repository."
    )
    assert payload is None
    assert "does not identify" in task_error


def test_manager_rejects_expired_session_for_continuation():
    manager = _manager_with_active_session()
    manager._sessions[SESSION_ID].expired = True

    payload, error = manager.resolve_active_continuation(
        f"Continue the approved task in Celesto session {SESSION_ID}."
    )

    assert payload is None
    assert "expired" in error
    assert "no command was run" in error


def test_active_continuation_bypasses_goal_json_and_never_proposes_new_session(monkeypatch):
    manager = Mock()
    manager.resolve_active_continuation.return_value = (
        {
            "state": "active_approved_session",
            "session_id": SESSION_ID,
            "approved_task": "Inspect psf/requests issue #7639 timeout handling",
            "cleanup_error": "",
        },
        None,
    )
    manager.create.side_effect = AssertionError("continuation must not create a session")
    monkeypatch.setattr("tools.sandbox_tools.sandbox_session_manager", manager)
    parse_goal = Mock(side_effect=AssertionError("continuation must not need goal JSON"))
    monkeypatch.setattr("core.grounded_agent.interpret_goal", parse_goal)
    engine = SpaceVGraphEngine(agent=SimpleNamespace(messages=[]))
    prompt = f"Continue the approved Requests issue #7639 task in existing Celesto session {SESSION_ID}."

    result = engine._goal_interpreter_node({"user_prompt": prompt})

    assert result["goal_interpretation"] == "active_sandbox_continuation"
    assert result["sandbox_continuation"] is True
    assert SESSION_ID in result["sandbox_context"]
    assert result.get("tool_calls", []) == []
    assert engine._route_after_goal(result) == "action"
    assert active_sandbox_tool_names(continuation=result["sandbox_continuation"]) == {
        "run_sandbox_session_command"
    }
    manager.create.assert_not_called()
    parse_goal.assert_not_called()


def test_missing_active_session_fails_without_new_session_or_tool_call(monkeypatch):
    manager = Mock()
    manager.resolve_active_continuation.return_value = (
        None,
        f"Celesto session {SESSION_ID} is not active in SpaceV's session manager; no command was run.",
    )
    manager.create.side_effect = AssertionError("missing-session path must not create a VM")
    monkeypatch.setattr("tools.sandbox_tools.sandbox_session_manager", manager)
    engine = SpaceVGraphEngine(agent=SimpleNamespace(messages=[]))

    result = engine._goal_interpreter_node(
        {"user_prompt": f"Continue the approved task in existing Celesto session {SESSION_ID}."}
    )

    assert result["is_complete"] is True
    assert result["tool_calls"] == []
    assert "not active" in result["final_response"]
    manager.create.assert_not_called()


def test_unavailable_guest_tool_fails_without_closing_or_creating(monkeypatch):
    manager = Mock()
    manager.resolve_active_continuation.return_value = (
        {
            "state": "active_approved_session",
            "session_id": SESSION_ID,
            "approved_task": "Inspect psf/requests issue #7639 timeout handling",
            "cleanup_error": "",
        },
        None,
    )
    manager.create.side_effect = AssertionError("must not create")
    manager.close.side_effect = AssertionError("must not close")
    monkeypatch.setattr("tools.sandbox_tools.sandbox_session_manager", manager)
    monkeypatch.setattr(
        graph_engine_module,
        "OLLAMA_TOOLS_SCHEMA",
        [tool for tool in graph_engine_module.OLLAMA_TOOLS_SCHEMA
         if tool.get("function", {}).get("name") != "run_sandbox_session_command"],
    )
    engine = SpaceVGraphEngine(agent=SimpleNamespace(messages=[]))

    result = engine._goal_interpreter_node(
        {"user_prompt": f"Continue the approved Requests issue #7639 task in existing Celesto session {SESSION_ID}."}
    )

    assert result["is_complete"] is True
    assert result["tool_calls"] == []
    assert "guest-command tool is unavailable" in result["final_response"]
    manager.create.assert_not_called()
    manager.close.assert_not_called()


def test_guest_tool_session_id_is_injected_from_manager_context_and_conflicts_fail():
    arguments, error = bind_active_sandbox_session_id(
        "run_sandbox_session_command", {"command": "git --version"}, SANDBOX_CONTEXT
    )
    assert error is None
    assert arguments == {"command": "git --version", "session_id": SESSION_ID}

    _, conflict = bind_active_sandbox_session_id(
        "run_sandbox_session_command",
        {"command": "git --version", "session_id": "session-aaaaaaaaaaaa"},
        SANDBOX_CONTEXT,
    )
    assert conflict and "conflicts" in conflict


def test_tool_executor_passes_manager_session_id_to_guest_tool(monkeypatch):
    captured = {}

    def fake_execute_tool(name, arguments):
        captured["name"] = name
        captured["arguments"] = dict(arguments)
        return "[CELESTO SESSION EXECUTION] exit code: 0"

    monkeypatch.setattr("core.graph_engine.execute_tool", fake_execute_tool)
    monkeypatch.setattr("core.task_evidence.task_evidence_store.record_tool", lambda **_kwargs: None)
    engine = SpaceVGraphEngine(agent=SimpleNamespace(messages=[]))
    state = {
        "user_prompt": "Continue the approved Requests issue #7639 task",
        "goal_contract": {"tool_domains": ["sandbox"], "requires_action": True},
        "sandbox_context": SANDBOX_CONTEXT,
        "sandbox_continuation": True,
        "tool_calls": [
            {"id": "call-guest", "function": {"name": "run_sandbox_session_command", "arguments": {"command": "git --version"}}}
        ],
        "tool_results": [],
        "messages": [],
        "scratchpad": {},
    }

    result = engine._tool_executor_node(state)

    assert captured["name"] == "run_sandbox_session_command"
    assert captured["arguments"] == {"command": "git --version", "session_id": SESSION_ID}
    assert result["tool_results"][-1]["status"] == "success"


def test_continuation_tool_allowlist_excludes_new_vm_and_other_tools():
    assert active_sandbox_tool_names(continuation=True) == {"run_sandbox_session_command"}
    assert active_sandbox_tool_names(failed_guest_command=True) == {"close_sandbox_session"}
    assert active_sandbox_tool_names(continuation=True, failed_guest_command=True) == set()
    assert not sandbox_continuation_requested("Open Notepad")


def test_continuation_executor_blocks_session_closure(monkeypatch):
    import pytest

    monkeypatch.setattr("core.graph_engine.execute_tool", lambda *_args: pytest.fail("close tool executed"))
    monkeypatch.setattr("core.task_evidence.task_evidence_store.record_tool", lambda **_kwargs: None)
    engine = SpaceVGraphEngine(agent=SimpleNamespace(messages=[]))
    state = {
        "user_prompt": "Continue the approved task",
        "goal_contract": {"tool_domains": ["sandbox"], "requires_action": True},
        "sandbox_context": SANDBOX_CONTEXT,
        "sandbox_continuation": True,
        "tool_calls": [
            {"id": "call-close", "function": {"name": "close_sandbox_session", "arguments": {"session_id": SESSION_ID}}}
        ],
        "tool_results": [], "messages": [], "scratchpad": {},
    }

    result = engine._tool_executor_node(state)

    assert result["tool_results"][-1]["status"] == "blocked"
    assert "cannot create or close" in result["tool_results"][-1]["result"]


def test_failed_guest_command_in_continuation_does_not_auto_close(monkeypatch):
    captured = []

    def fake_execute_tool(name, arguments):
        captured.append(name)
        return "guest command failed"

    monkeypatch.setattr("core.graph_engine.execute_tool", fake_execute_tool)
    monkeypatch.setattr("core.graph_engine.determine_tool_status", lambda *_args: "failed")
    monkeypatch.setattr("core.task_evidence.task_evidence_store.record_tool", lambda **_kwargs: None)
    engine = SpaceVGraphEngine(agent=SimpleNamespace(messages=[]))
    state = {
        "user_prompt": "Continue the approved task",
        "goal_contract": {"tool_domains": ["sandbox"], "requires_action": True},
        "sandbox_context": SANDBOX_CONTEXT,
        "sandbox_continuation": True,
        "tool_calls": [
            {"id": "call-guest", "function": {"name": "run_sandbox_session_command", "arguments": {"command": "git --version"}}}
        ],
        "tool_results": [], "messages": [], "scratchpad": {},
    }

    result = engine._tool_executor_node(state)

    assert captured == ["run_sandbox_session_command"]
    assert result["tool_results"][-1]["status"] == "failed"


def test_manager_command_policy_blocks_writes_tests_installs_host_and_issue_fetch():
    manager = _manager_with_active_session()
    instance = manager._sessions[SESSION_ID].instance
    instance.run = Mock(return_value=SimpleNamespace(
        exit_code=0, stdout="ok", stderr="", phase_timings_ms={"command_ms": 1.0, "vm_startup_ms": 0.0}
    ))
    instance.phase_timings_ms = {"command_ms": 1.0, "vm_startup_ms": 0.0}
    instance.name = "sbx-test"

    prohibited = [
        "apk add --no-cache git",
        "sed -i 's/a/b/' /tmp/requests-7639/src/requests/models.py",
        "pytest /tmp/requests-7639/tests/test_requests.py",
        "python -c 'print(1)'",
        "cat /mnt/d/agentSpace/README.md",
        "curl https://github.com/psf/requests/issues/7639",
        "git clone https://github.com/other/repo.git /tmp/requests-7639",
        "grep timeout /tmp/requests-7639/src/requests/models.py; rm -rf /tmp/requests-7639",
    ]
    for command in prohibited:
        result = manager.run(SESSION_ID, command)
        assert result.startswith("BLOCKED:"), (command, result)
    instance.run.assert_not_called()


def test_manager_command_policy_allows_scoped_read_only_inspection():
    manager = _manager_with_active_session()
    instance = manager._sessions[SESSION_ID].instance
    instance.run = Mock(return_value=SimpleNamespace(
        exit_code=0,
        stdout="line",
        stderr="",
        phase_timings_ms={"command_ms": 1.0, "vm_startup_ms": 0.0},
    ))
    instance.phase_timings_ms = {"command_ms": 1.0, "vm_startup_ms": 0.0}
    instance.name = "sbx-test"

    result = manager.run(
        SESSION_ID,
        "git -C /tmp/requests-7639 grep -n -C 8 -E timeout HEAD -- src/requests/models.py",
    )

    assert "exit code: 0" in result
    instance.run.assert_called_once()


def test_manager_command_policy_allows_only_exact_shallow_clone():
    from tools.sandbox_tools import validate_approved_guest_command

    task = _manager_with_active_session()._sessions[SESSION_ID].task_description
    assert validate_approved_guest_command(
        task,
        "git -c core.hooksPath=/dev/null clone --depth=1 --no-tags -- "
        "https://github.com/psf/requests.git /tmp/requests-7639",
    ) is None
    assert validate_approved_guest_command(
        task,
        "git clone --depth=1 https://github.com/other/repo.git /tmp/requests-7639",
    )


def test_approved_task_scope_is_immutable():
    from dataclasses import FrozenInstanceError
    import pytest

    manager = _manager_with_active_session()
    scope = manager._sessions[SESSION_ID].approved_task_scope

    with pytest.raises(FrozenInstanceError):
        scope.description = "Inspect another repository issue #7640"


def test_sandbox_scoped_host_command_is_blocked_without_execution(monkeypatch):
    import pytest

    engine = SpaceVGraphEngine(agent=SimpleNamespace(messages=[]))
    monkeypatch.setattr("core.graph_engine.execute_tool", lambda *_args, **_kwargs: pytest.fail("host tool executed"))
    monkeypatch.setattr("core.task_evidence.task_evidence_store.record_tool", lambda **_kwargs: None)
    state = {
        "user_prompt": "Continue the approved sandbox task",
        "goal_contract": {"tool_domains": ["sandbox"], "requires_action": True},
        "sandbox_context": SANDBOX_CONTEXT,
        "tool_calls": [
            {"id": "call-host", "function": {"name": "execute_terminal_command", "arguments": {"command": "echo host"}}}
        ],
        "tool_results": [],
        "messages": [],
        "scratchpad": {},
    }

    result = engine._tool_executor_node(state)

    assert result["tool_results"][-1]["status"] == "blocked"
    assert "Host tools cannot be used" in result["tool_results"][-1]["result"]


def test_ordinary_desktop_prompt_is_not_claimed_as_sandbox_continuation():
    assert not sandbox_continuation_requested("Open Notepad and create a blank document.")


def test_ordinary_desktop_request_still_uses_structured_goal_path(monkeypatch):
    from core.grounded_agent import GroundedGoal

    manager = Mock()
    manager.continuation_context.return_value = ""
    monkeypatch.setattr("tools.sandbox_tools.sandbox_session_manager", manager)
    monkeypatch.setattr(
        "core.grounded_agent.interpret_goal",
        lambda *_args, **_kwargs: (
            GroundedGoal(objective="Open Notepad", tool_domains=["gui"], requires_action=True, confidence=0.9),
            "model",
        ),
    )
    monkeypatch.setattr("core.task_evidence.task_evidence_store.retrieve_context", lambda *_args, **_kwargs: "")
    engine = SpaceVGraphEngine(agent=SimpleNamespace(messages=[]))

    result = engine._goal_interpreter_node({"user_prompt": "Open Notepad"})

    assert result["goal_interpretation"] == "model"
    assert result["goal_contract"]["tool_domains"] == ["gui"]
    assert "sandbox_continuation" not in result
    manager.resolve_active_continuation.assert_not_called()


def test_issue_to_failing_test_request_starts_in_controller_validation_phase(monkeypatch):
    from core.grounded_agent import GroundedGoal

    manager = Mock()
    manager.continuation_context.return_value = ""
    monkeypatch.setattr("tools.sandbox_tools.sandbox_session_manager", manager)
    monkeypatch.setattr(
        "core.grounded_agent.interpret_goal",
        lambda *_args, **_kwargs: (
            GroundedGoal(
                objective="Create a minimal failing test",
                tool_domains=["sandbox"],
                requires_action=True,
                confidence=0.9,
            ),
            "model",
        ),
    )
    monkeypatch.setattr("core.task_evidence.task_evidence_store.retrieve_context", lambda *_args, **_kwargs: "")
    engine = SpaceVGraphEngine(agent=SimpleNamespace(messages=[]))

    result = engine._goal_interpreter_node(
        {
            "user_prompt": (
                "Create a minimal failing test for "
                "https://github.com/psf/requests/issues/7639"
            )
        }
    )

    assert result["issue_workflow_phase"] == "ISSUE_VALIDATION"
    assert result["issue_workflow_issue"]["issue_number"] == 7639
    assert result["issue_workflow_issue"]["repository_url"] == "https://github.com/psf/requests"


def test_ordinary_desktop_request_does_not_enter_issue_workflow(monkeypatch):
    from core.grounded_agent import GroundedGoal

    manager = Mock()
    manager.continuation_context.return_value = ""
    monkeypatch.setattr("tools.sandbox_tools.sandbox_session_manager", manager)
    monkeypatch.setattr(
        "core.grounded_agent.interpret_goal",
        lambda *_args, **_kwargs: (
            GroundedGoal(objective="Open Notepad", tool_domains=["gui"], requires_action=True, confidence=0.9),
            "model",
        ),
    )
    monkeypatch.setattr("core.task_evidence.task_evidence_store.retrieve_context", lambda *_args, **_kwargs: "")
    engine = SpaceVGraphEngine(agent=SimpleNamespace(messages=[]))

    result = engine._goal_interpreter_node({"user_prompt": "Open Notepad"})

    assert result["goal_interpretation"] == "model"
    assert result.get("issue_workflow_phase") is None


def test_valid_github_issue_request_routes_to_existing_reader_before_model(monkeypatch):
    engine = SpaceVGraphEngine(agent=SimpleNamespace(messages=[]))

    result = engine._goal_interpreter_node(
        {"user_prompt": "Summarize this issue https://github.com/psf/requests/issues/7634"}
    )

    assert result["goal_interpretation"] == "github_issue_intake"
    assert result["github_issue_identity"]["owner"] == "psf"
    assert result["github_issue_identity"]["repository"] == "requests"
    assert result["github_issue_identity"]["issue_number"] == 7634
    assert result["tool_calls"][0]["function"]["name"] == "read_web_page"
    assert result["tool_calls"][0]["function"]["arguments"]["url"] == (
        "https://github.com/psf/requests/issues/7634"
    )
    assert result["tool_calls"][0]["function"]["arguments"]["include_comments"] is False
    assert len(result["tool_calls"]) == 1
    assert engine._route_after_goal(result) == "issue_intake_fetch"


def test_user_requested_discussion_enables_comments_in_the_single_issue_fetch():
    engine = SpaceVGraphEngine(agent=SimpleNamespace(messages=[]))

    result = engine._goal_interpreter_node({
        "user_prompt": "Summarize this issue and its comments https://github.com/psf/requests/issues/7634"
    })

    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["function"]["name"] == "read_web_page"
    assert result["tool_calls"][0]["function"]["arguments"]["include_comments"] is True


def test_summary_approval_survives_worker_recreation_and_is_consumed_without_tools():
    from core.issue_test_workflow import parse_github_issue_url

    source_prompt = "Summarize this issue https://github.com/psf/requests/issues/7634"
    summary_response = (
        "The issue reports a timeout problem. Would you like me to inspect the repository next?"
    )
    identity = parse_github_issue_url("https://github.com/psf/requests/issues/7634")
    shared_agent = SimpleNamespace(messages=[
        {"role": "user", "content": source_prompt},
        {"role": "assistant", "content": summary_response},
    ])
    first_worker_engine = SpaceVGraphEngine(agent=shared_agent)
    first_worker_engine._cached_github_issue = {
        "identity": identity,
        "content": {"content": "# Timeout\nIssue: " + identity["issue_url"]},
    }
    first_worker_engine._pending_github_issue_approval = {
        "identity": identity,
        "source_prompt": source_prompt,
        "summary_response": summary_response,
    }

    # ChatWindow constructs a new AgentWorker (and graph engine) per message.
    next_worker_engine = SpaceVGraphEngine(agent=shared_agent)

    result = next_worker_engine._goal_interpreter_node({"user_prompt": "yes"})

    assert result["goal_interpretation"] == "github_issue_inspection_approved_not_implemented"
    assert result["tool_calls"] == []
    assert result["is_complete"] is True
    assert "did not fetch the issue again" in result["final_response"]
    assert next_worker_engine._pending_github_issue_approval is None


def test_issue_approval_with_changed_summary_context_fails_closed():
    from core.issue_test_workflow import parse_github_issue_url

    source_prompt = "Summarize this issue https://github.com/psf/requests/issues/7634"
    summary_response = "Summary. Would you like me to inspect the repository next?"
    identity = parse_github_issue_url("https://github.com/psf/requests/issues/7634")
    shared_agent = SimpleNamespace(messages=[
        {"role": "user", "content": "A different conversation turn"},
        {"role": "assistant", "content": summary_response},
    ])
    engine = SpaceVGraphEngine(agent=shared_agent)
    engine._cached_github_issue = {"identity": identity, "content": {"content": "issue"}}
    engine._pending_github_issue_approval = {
        "identity": identity,
        "source_prompt": source_prompt,
        "summary_response": summary_response,
    }

    result = engine._goal_interpreter_node({"user_prompt": "yes"})

    assert result["goal_interpretation"] == "github_issue_approval_context_unavailable"
    assert result["tool_calls"] == []
    assert result["is_complete"] is True


def test_new_issue_intake_clears_previous_retry_cache_before_fetch():
    from core.issue_test_workflow import parse_github_issue_url

    previous_identity = parse_github_issue_url("https://github.com/psf/requests/issues/7634")
    engine = SpaceVGraphEngine(agent=SimpleNamespace(messages=[]))
    engine._cached_github_issue = {
        "identity": previous_identity,
        "content": {"content": "old issue A"},
    }

    result = engine._goal_interpreter_node({
        "user_prompt": "Summarize this issue https://github.com/psf/requests/issues/7635"
    })

    assert result["goal_interpretation"] == "github_issue_intake"
    assert result["github_issue_identity"]["issue_number"] == 7635
    assert result["tool_calls"][0]["function"]["arguments"]["url"].endswith("/7635")
    assert engine._cached_github_issue is None


def test_failed_summary_cannot_be_approved_for_repository_inspection():
    engine = SpaceVGraphEngine(agent=SimpleNamespace(messages=[]))
    engine._last_github_issue_summary_failed = True
    engine._cached_github_issue = {"identity": {"repository": "requests"}, "content": {"content": "issue"}}

    result = engine._goal_interpreter_node({"user_prompt": "yes"})

    assert result["goal_interpretation"] == "github_issue_inspection_not_approved_after_summary_failure"
    assert result["tool_calls"] == []
    assert "summary did not succeed" in result["final_response"]


def test_summary_retry_uses_cached_issue_without_a_fetch_tool():
    from core.issue_test_workflow import parse_github_issue_url

    engine = SpaceVGraphEngine(agent=SimpleNamespace(messages=[]))
    identity = parse_github_issue_url("https://github.com/psf/requests/issues/7634")
    content = {"content": "# Timeout\nIssue: https://github.com/psf/requests/issues/7634\n## Issue description\nTimeout"}
    engine._cached_github_issue = {"identity": identity, "content": content}

    result = engine._goal_interpreter_node({"user_prompt": "Retry the issue summary"})

    assert result["goal_interpretation"] == "github_issue_summary_retry_from_cache"
    assert result["tool_calls"] == []
    assert result["github_issue_content"] is content
    assert engine._route_after_goal(result) == "issue_intake_summary"


def test_bare_retry_reuses_issue_across_worker_recreation_without_tools():
    from core.issue_test_workflow import parse_github_issue_url

    identity = parse_github_issue_url("https://github.com/psf/requests/issues/7639")
    validated_content = {
        "ok": True,
        "issue_url": identity["issue_url"],
        "content": "# Timeout\nIssue: " + identity["issue_url"] + "\n## Issue description\nTimeout",
    }
    shared_agent = SimpleNamespace(messages=[])
    first_worker_engine = SpaceVGraphEngine(agent=shared_agent)
    first_worker_engine._cached_github_issue = {
        "identity": identity,
        "content": validated_content,
    }
    first_worker_engine._last_github_issue_summary_failed = True

    next_worker_engine = SpaceVGraphEngine(agent=shared_agent)
    result = next_worker_engine._goal_interpreter_node({"user_prompt": "retry"})

    assert result["goal_interpretation"] == "github_issue_summary_retry_from_cache"
    assert result["github_issue_identity"] == identity
    assert result["github_issue_content"] is validated_content
    assert result["tool_calls"] == []
    assert next_worker_engine._last_github_issue_summary_failed is False
    assert next_worker_engine._cached_github_issue["identity"] == identity


def test_bare_retry_without_retained_content_fails_without_tools_or_false_claim():
    engine = SpaceVGraphEngine(agent=SimpleNamespace(messages=[]))
    engine._last_github_issue_summary_failed = True
    engine._cached_github_issue = None

    result = engine._goal_interpreter_node({"user_prompt": "retry"})

    assert result["goal_interpretation"] == "github_issue_summary_retry_content_unavailable"
    assert result["tool_calls"] == []
    assert result["is_complete"] is True
    assert "couldn't confirm" in result["final_response"]
    assert "retained" not in result["final_response"]


def test_yes_after_issue_summary_without_pending_state_never_plans_tools():
    source_prompt = "Summarize this issue https://github.com/psf/requests/issues/7634"
    shared_agent = SimpleNamespace(messages=[
        {"role": "user", "content": source_prompt},
        {"role": "assistant", "content": "Summary. Would you like me to inspect the repository next?"},
    ])
    result = SpaceVGraphEngine(agent=shared_agent)._goal_interpreter_node({"user_prompt": "yes"})

    assert result["goal_interpretation"] == "github_issue_approval_context_unavailable"
    assert result["tool_calls"] == []
    assert result["is_complete"] is True


def test_summary_failure_response_does_not_append_approval_question():
    engine = SpaceVGraphEngine(agent=SimpleNamespace(provider="ollama", model="test-model"))
    result = engine._complete_github_issue_summary(
        {"github_issue_intake": True},
        "The configured LLM endpoint did not return a usable response. Check settings and try again.",
        [],
    )

    assert result["github_issue_summary_succeeded"] is False
    assert "retrieved" in result["final_response"]
    assert "could not confirm that the issue content is retained" in result["final_response"]
    assert "Would you like me to inspect" not in result["final_response"]


def test_summary_failure_claims_retention_only_for_matching_validated_cache():
    from core.issue_test_workflow import parse_github_issue_url

    identity = parse_github_issue_url("https://github.com/psf/requests/issues/7639")
    content = {"ok": True, "issue_url": identity["issue_url"], "content": "issue source"}
    engine = SpaceVGraphEngine(agent=SimpleNamespace(provider="ollama", model="test-model"))
    engine._cached_github_issue = {"identity": identity, "content": content}
    result = engine._complete_github_issue_summary(
        {
            "github_issue_intake": True,
            "github_issue_intake_validated": True,
            "github_issue_identity": identity,
            "github_issue_content": content,
        },
        "The configured LLM endpoint did not return a usable response. Check settings and try again.",
        [],
    )

    assert "retained in this running SpaceV session" in result["final_response"]


def test_successful_summary_asks_for_approval_and_marks_summary_usable():
    engine = SpaceVGraphEngine(agent=SimpleNamespace(provider="ollama", model="test-model"))
    result = engine._complete_github_issue_summary(
        {"github_issue_intake": True},
        "The issue reports that timeout tests can pass without an assertion when the expected timeout is not raised.",
        [],
    )

    assert result["github_issue_summary_succeeded"] is True
    assert result["final_response"].endswith("Would you like me to inspect the repository next?")


def test_invalid_github_issue_url_fails_without_fetching(monkeypatch):
    engine = SpaceVGraphEngine(agent=SimpleNamespace(messages=[]))

    result = engine._goal_interpreter_node(
        {"user_prompt": "Explain this issue http://github.com/psf/requests/issues/7634"}
    )

    assert result["goal_interpretation"] == "github_issue_url_invalid"
    assert result["tool_calls"] == []
    assert result["is_complete"] is True
    assert "No issue content was fetched" in result["final_response"]


def test_github_issue_fetch_failure_is_reported_without_synthesis_or_retry():
    engine = SpaceVGraphEngine(agent=SimpleNamespace(provider="ollama", model="test-model"))
    state = {
        "github_issue_intake": True,
        "github_issue_intake_error": "GitHub API unavailable",
        "final_response": "I couldn't retrieve the issue. Details: GitHub API unavailable",
        "messages": [],
        "tool_results": [{"name": "read_web_page", "status": "failed", "result": "Failed: timeout"}],
    }

    route = engine._route_after_tools(state)
    response = engine._response_synthesizer_node(state)

    assert route == "synthesize"
    assert response["final_response"] == state["final_response"]
    assert response["is_complete"] is True

