"""Regression tests for evidence-safe Issue-to-Failing-Test classification."""

import pytest

from core.issue_test_workflow import (
    IssueWorkflowController,
    IssueWorkflowPhase,
    build_issue_test_sandbox_description,
    classify_git_status,
    classify_test_execution,
    classify_test_patch_paths,
    is_issue_test_workflow_request,
    parse_github_issue_url,
    sandbox_proposal_requested,
    sandbox_task_description_error,
)
from core.agent_configs import ISSUE_TEST_AGENT_CONFIG


@pytest.mark.parametrize(
    ("phase", "next_phase"),
    [
        (IssueWorkflowPhase.ISSUE_VALIDATION, IssueWorkflowPhase.ISSUE_ANALYSIS),
        (IssueWorkflowPhase.ISSUE_ANALYSIS, IssueWorkflowPhase.SANDBOX_APPROVAL),
        (IssueWorkflowPhase.SANDBOX_APPROVAL, IssueWorkflowPhase.REPOSITORY_CHECKOUT),
        (IssueWorkflowPhase.REPOSITORY_CHECKOUT, IssueWorkflowPhase.SOURCE_INSPECTION),
        (IssueWorkflowPhase.SOURCE_INSPECTION, IssueWorkflowPhase.TEST_PROPOSAL),
        (IssueWorkflowPhase.TEST_PROPOSAL, IssueWorkflowPhase.DIFF_APPROVAL),
        (IssueWorkflowPhase.DIFF_APPROVAL, IssueWorkflowPhase.BASELINE_VERIFICATION),
        (IssueWorkflowPhase.BASELINE_VERIFICATION, IssueWorkflowPhase.TEST_APPROVAL),
        (IssueWorkflowPhase.TEST_APPROVAL, IssueWorkflowPhase.TEST_EXECUTION),
        (IssueWorkflowPhase.TEST_EXECUTION, IssueWorkflowPhase.FINAL_REPORT),
    ],
)
def test_issue_workflow_controller_allows_only_each_declared_transition(phase, next_phase):
    controller = IssueWorkflowController(phase)

    assert controller.advance(next_phase) is next_phase
    assert controller.phase is next_phase


@pytest.mark.parametrize(
    ("phase", "invalid_target"),
    [
        (IssueWorkflowPhase.ISSUE_VALIDATION, IssueWorkflowPhase.SANDBOX_APPROVAL),
        (IssueWorkflowPhase.ISSUE_ANALYSIS, IssueWorkflowPhase.REPOSITORY_CHECKOUT),
        (IssueWorkflowPhase.SANDBOX_APPROVAL, IssueWorkflowPhase.SOURCE_INSPECTION),
        (IssueWorkflowPhase.REPOSITORY_CHECKOUT, IssueWorkflowPhase.TEST_PROPOSAL),
        (IssueWorkflowPhase.SOURCE_INSPECTION, IssueWorkflowPhase.DIFF_APPROVAL),
        (IssueWorkflowPhase.TEST_PROPOSAL, IssueWorkflowPhase.BASELINE_VERIFICATION),
        (IssueWorkflowPhase.DIFF_APPROVAL, IssueWorkflowPhase.TEST_EXECUTION),
        (IssueWorkflowPhase.BASELINE_VERIFICATION, IssueWorkflowPhase.FINAL_REPORT),
        (IssueWorkflowPhase.TEST_APPROVAL, IssueWorkflowPhase.FINAL_REPORT),
        (IssueWorkflowPhase.TEST_EXECUTION, IssueWorkflowPhase.ISSUE_VALIDATION),
    ],
)
def test_issue_workflow_controller_rejects_skipped_or_wrong_prerequisites(phase, invalid_target):
    controller = IssueWorkflowController(phase)

    with pytest.raises(ValueError, match="only .* is allowed"):
        controller.advance(invalid_target)

    assert controller.phase is phase


def test_issue_workflow_controller_rejects_unknown_and_terminal_transitions():
    with pytest.raises(ValueError, match="Unknown Issue-to-Failing-Test phase"):
        IssueWorkflowController("MODEL_DECIDES_WHAT_IS_NEXT")

    controller = IssueWorkflowController(IssueWorkflowPhase.FINAL_REPORT)
    with pytest.raises(ValueError, match="FINAL_REPORT is terminal"):
        controller.advance(IssueWorkflowPhase.FINAL_REPORT)


def test_final_report_phase_does_not_claim_workflow_success():
    controller = IssueWorkflowController(IssueWorkflowPhase.FINAL_REPORT)

    assert controller.phase is IssueWorkflowPhase.FINAL_REPORT
    assert not hasattr(controller, "is_success")


def test_issue_test_request_detector_requires_validated_issue_and_specific_intent():
    url = "Please write a minimal failing test for https://github.com/psf/requests/issues/7639"
    desktop = "Open Notepad and create a blank document"

    assert is_issue_test_workflow_request(url, issue_validated=True)
    assert not is_issue_test_workflow_request(url, issue_validated=False)
    assert not is_issue_test_workflow_request(desktop, issue_validated=True)


def test_parse_github_issue_url_normalizes_issue_identity():
    parsed = parse_github_issue_url("https://github.com/psf/requests/issues/7639")

    assert parsed["issue_url"] == "https://github.com/psf/requests/issues/7639"
    assert parsed["clone_url"] == "https://github.com/psf/requests.git"
    assert parsed["issue_number"] == 7639


def test_approval_proposal_synonym_builds_bounded_issue_task_and_keeps_restrictions():
    prompt = (
        "Prepare a fresh approval proposal for the same task. Use one disposable Celesto VM, "
        "shallow-clone Requests, inspect the timeout test, and show a minimal test-only diff. "
        "Do not fetch the issue; do not access the host or SpaceV checkout; do not install, edit, or test."
    )
    context = "Issue: https://github.com/psf/requests/issues/7639"

    task = build_issue_test_sandbox_description(prompt, context)

    assert sandbox_proposal_requested(prompt)
    assert task is not None
    assert len(task) <= 800
    assert "https://github.com/psf/requests.git" in task
    assert "/tmp/requests-7639" in task
    assert "Do not fetch the issue" in task
    assert "Do not access the host or SpaceV checkout" in task
    assert "do not install dependencies, edit files, or run tests" in task.casefold()


def test_issue_test_task_builder_does_not_invent_repository_identity():
    prompt = "Prepare a Celesto sandbox proposal to inspect an issue and show a test-only diff."

    assert build_issue_test_sandbox_description(prompt) is None


def test_ordinary_sandbox_issue_discussion_is_not_misclassified_as_issue_test_proposal():
    prompt = "Prepare a Celesto sandbox proposal about issues with window layout on my desktop."

    assert not sandbox_proposal_requested(prompt)
    assert build_issue_test_sandbox_description(prompt) is None


def test_sandbox_task_description_limit_is_checked_without_truncation():
    assert sandbox_task_description_error("x" * 801) == (
        "Sandbox task description is 801 characters; the limit is 800. No VM was started."
    )
    assert sandbox_task_description_error("x" * 800) is None
    overlong_with_whitespace = " " + ("x" * 799) + " "
    assert sandbox_task_description_error(overlong_with_whitespace) == (
        "Sandbox task description is 801 characters; the limit is 800. No VM was started."
    )


def test_issue_test_agent_cannot_select_host_clone_tool():
    assert "clone_public_repository" not in ISSUE_TEST_AGENT_CONFIG.allowed_tools
    assert "create_sandbox_session" in ISSUE_TEST_AGENT_CONFIG.allowed_tools
    assert "run_sandbox_session_command" in ISSUE_TEST_AGENT_CONFIG.allowed_tools


def test_expected_bug_failure_requires_target_test_symptom():
    output = """[CELESTO SESSION EXECUTION] exit code: 1
STDOUT:
=================================== FAILURES ===================================
___________________ TestTimeout.test_stream_timeout ____________________
tests/test_requests.py:123: AssertionError
E       AssertionError: Read timed out
=========================== short test summary info ============================
FAILED tests/test_requests.py::TestTimeout::test_stream_timeout
STDERR:
"""

    result = classify_test_execution(
        "pytest tests/test_requests.py::TestTimeout::test_stream_timeout",
        output,
        expected_signal="Read timed out",
    )

    assert result["classification"] == "EXPECTED_BUG_FAILURE"
    assert result["expected_signal_observed"] is True
    assert result["output_truncated"] is False


def test_similarly_named_test_cannot_prove_target_failure():
    output = """[CELESTO SESSION EXECUTION] exit code: 1
STDOUT:
___________________ TestTimeout.test_stream_timeout_extra ____________________
tests/test_requests.py:123: AssertionError
E       AssertionError: Read timed out
=========================== short test summary info ============================
FAILED tests/test_requests.py::TestTimeout::test_stream_timeout_extra
STDERR:
"""

    result = classify_test_execution(
        "pytest tests/test_requests.py::TestTimeout::test_stream_timeout",
        output,
        expected_signal="Read timed out",
    )

    assert result["classification"] == "INCONCLUSIVE"
    assert result["expected_signal_observed"] is False


def test_file_level_failure_is_not_attributed_to_one_target_test():
    output = """[CELESTO SESSION EXECUTION] exit code: 1
STDOUT:
___________________ TestTimeout.test_stream_timeout ____________________
tests/test_requests.py:123: AssertionError
E       AssertionError: Read timed out
=========================== short test summary info ============================
FAILED tests/test_requests.py::TestTimeout::test_stream_timeout
STDERR:
"""

    result = classify_test_execution(
        "pytest tests/test_requests.py",
        output,
        expected_signal="Read timed out",
    )

    assert result["classification"] == "INCONCLUSIVE"
    assert result["expected_signal_observed"] is False


def test_truncated_target_failure_is_inconclusive():
    output = """[CELESTO SESSION EXECUTION] exit code: 1
STDOUT:
___________________ TestTimeout.test_stream_timeout ____________________
E       AssertionError: Read timed out
⚠️ ... [9000 characters / 2250 tokens truncated to protect rate limits. Full output spooled]
STDERR:
"""

    result = classify_test_execution(
        "pytest tests/test_requests.py::TestTimeout::test_stream_timeout",
        output,
        expected_signal="Read timed out",
    )

    assert result["classification"] == "INCONCLUSIVE"
    assert result["expected_signal_observed"] is False
    assert result["output_truncated"] is True


def test_execution_timeout_is_classified_as_infrastructure_timeout():
    result = classify_test_execution(
        "pytest tests/test_requests.py::TestTimeout::test_stream_timeout",
        "[CELESTO SESSION EXECUTION] exit code: 1\nSTDERR:\n"
        "Celesto command failed: Operation 'vsock run: pytest' timed out after 30s",
        expected_signal="Read timed out",
    )

    assert result["classification"] == "TIMEOUT"
    assert result["expected_signal_observed"] is False


def test_failed_git_status_is_never_reported_clean():
    result = classify_git_status(
        "git status --short",
        "[CELESTO SESSION EXECUTION] exit code: 1\nSTDOUT:\nSTDERR:\nfatal: not a git repository",
    )

    assert result["classification"] == "GIT_STATUS_COMMAND_FAILED"
    assert result["paths"] == []
    assert result["exit_code"] == 1


def test_truncated_git_status_does_not_claim_clean_checkout():
    result = classify_git_status(
        "git status --short",
        "[CELESTO SESSION EXECUTION] exit code: 0\nSTDOUT:\n⚠️ ... [100 characters / 25 tokens truncated to protect rate limits]\nSTDERR:\n",
    )

    assert result["classification"] == "GIT_STATUS_OUTPUT_TRUNCATED"
    assert result["paths"] == []
    assert result["output_truncated"] is True


def test_truncated_patch_path_audit_fails_closed():
    result = classify_test_patch_paths(
        "git status --short",
        "[CELESTO SESSION EXECUTION] exit code: 0\nSTDOUT:\n M tests/test_issue.py\n"
        "⚠️ ... [100 characters / 25 tokens truncated to protect rate limits]\nSTDERR:\n",
    )

    assert result["classification"] == "PATCH_AUDIT_OUTPUT_TRUNCATED"
    assert result["output_truncated"] is True
