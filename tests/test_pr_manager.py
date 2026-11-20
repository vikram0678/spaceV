"""Unit, security, and workflow tests for SpaceV Step 2.6 Pull Request Creation and Publishing."""

from __future__ import annotations

import hashlib
import json
import time
from unittest.mock import MagicMock, patch

import pytest

from core.issue_pr_manager import (
    BranchPreparationEngine,
    CommitBundle,
    CommitExecutionEngine,
    CommitSynthesisEngine,
    EvidenceValidator,
    ExecutedCommitReceipt,
    GitHubPublishingAuthorizationManager,
    PRContent,
    PRPublishingProposal,
    PRSynthesisEngine,
    RegressionAuditor,
    VerifiedEvidenceBundle,
)

VALID_COMMIT = "3c7baaa05ab4aa49cc819ce3a819d260de19c157"
VALID_NEW_COMMIT = "8f9a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a"
VALID_DIFF = "--- a/src/requests/models.py\n+++ b/src/requests/models.py\n@@ -1017,1 +1017,1 @@\n"
VALID_HASH = hashlib.sha256(VALID_DIFF.encode("utf-8")).hexdigest()


def make_valid_proposal_and_evidence():
    proposal = {
        "patch_id": "patch-77ca97735008",
        "repository_url": "https://github.com/psf/requests.git",
        "base_commit": VALID_COMMIT,
        "checkout_path": "/tmp/requests-7645",
        "target_files": ["src/requests/models.py"],
        "diff_content": VALID_DIFF,
        "patch_hash": VALID_HASH,
        "explanation": "In Response.iter_lines(), coerce delimiter between str and bytes to match chunk type.",
        "behavior_before": "Calling iter_lines crashes with TypeError on bytes.split(str).",
        "behavior_after": "Coerces string delimiter to bytes cleanly.",
        "compatibility_notes": "100% backwards-compatible.",
        "regression_tests_plan": [
            "test_iter_lines_str_delimiter_none_encoding",
            "test_iter_lines_bytes_delimiter",
        ],
        "status": "APPROVED",
        "approval_token": "approve patch patch-77ca97735008",
    }
    evidence = {
        "patch_id": "patch-77ca97735008",
        "approved_hash": VALID_HASH,
        "applied_diff_hash": VALID_HASH,
        "repository_url": "https://github.com/psf/requests.git",
        "base_commit": VALID_COMMIT,
        "guest_commit": VALID_COMMIT,
        "target_file": "src/requests/models.py",
        "final_diff": VALID_DIFF,
        "git_status": " M src/requests/models.py\n",
        "test_exit_code": 0,
        "test_stdout": "3 passed in 0.01s",
        "test_stderr": "",
    }
    return proposal, evidence


# ---------------------------------------------------------------------------
# Phase 1: Evidence Validation Tests
# ---------------------------------------------------------------------------

def test_evidence_validator_success():
    prop, evid = make_valid_proposal_and_evidence()
    bundle = EvidenceValidator.validate_evidence(prop, evid)
    assert bundle.patch_id == "patch-77ca97735008"
    assert bundle.patch_hash == VALID_HASH
    assert bundle.test_exit_code == 0
    assert bundle.target_files == ["src/requests/models.py"]


def test_evidence_validator_rejects_patch_id_mismatch():
    prop, evid = make_valid_proposal_and_evidence()
    evid["patch_id"] = "patch-mismatch999"
    with pytest.raises(ValueError, match="Patch ID mismatch"):
        EvidenceValidator.validate_evidence(prop, evid)


def test_evidence_validator_rejects_patch_hash_mismatch():
    prop, evid = make_valid_proposal_and_evidence()
    evid["approved_hash"] = "0" * 64
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        EvidenceValidator.validate_evidence(prop, evid)


def test_evidence_validator_rejects_diff_content_tampering():
    prop, evid = make_valid_proposal_and_evidence()
    prop["diff_content"] = "tampered diff"
    with pytest.raises(ValueError, match="does not match recorded patch_hash"):
        EvidenceValidator.validate_evidence(prop, evid)


def test_evidence_validator_rejects_repository_mismatch():
    prop, evid = make_valid_proposal_and_evidence()
    evid["repository_url"] = "https://github.com/pallets/flask.git"
    with pytest.raises(ValueError, match="Repository mismatch"):
        EvidenceValidator.validate_evidence(prop, evid)


def test_evidence_validator_rejects_commit_mismatch():
    prop, evid = make_valid_proposal_and_evidence()
    evid["guest_commit"] = "1" * 40
    with pytest.raises(ValueError, match="Guest HEAD commit .* does not match base commit"):
        EvidenceValidator.validate_evidence(prop, evid)


def test_evidence_validator_rejects_non_zero_test_exit_code():
    prop, evid = make_valid_proposal_and_evidence()
    evid["test_exit_code"] = 1
    with pytest.raises(ValueError, match="Fix verification failed with non-zero exit code 1"):
        EvidenceValidator.validate_evidence(prop, evid)


def test_evidence_validator_rejects_unexpected_modified_files():
    prop, evid = make_valid_proposal_and_evidence()
    evid["git_status"] = " M src/requests/models.py\n M setup.py\n"
    with pytest.raises(ValueError, match="unexpected files were modified"):
        EvidenceValidator.validate_evidence(prop, evid)


def test_evidence_validator_rejects_missing_fields():
    prop, evid = make_valid_proposal_and_evidence()
    del prop["target_files"]
    with pytest.raises(ValueError, match="Proposal target_files is empty"):
        EvidenceValidator.validate_evidence(prop, evid)


# ---------------------------------------------------------------------------
# Phase 2: Branch Safety & Complete Working-Tree Auditing Tests
# ---------------------------------------------------------------------------

def test_branch_name_generation_deterministic():
    b1 = BranchPreparationEngine.generate_branch_name("patch-77ca97735008", VALID_HASH)
    b2 = BranchPreparationEngine.generate_branch_name("patch-77ca97735008", VALID_HASH)
    assert b1 == b2
    assert b1.startswith("spacev/fix-77ca9773-")


def test_branch_preparation_inside_guest_success():
    mock_computer = MagicMock()
    mock_computer.run.side_effect = [
        MagicMock(exit_code=0, stdout=f"{VALID_COMMIT}\n"),                         # rev-parse HEAD
        MagicMock(exit_code=1),                                                     # rev-parse refs/heads/branch (does not exist)
        MagicMock(exit_code=0, stdout="Switched to a new branch 'spacev/fix'\n"),    # checkout -b
        MagicMock(exit_code=0, stdout=""),                                          # status --porcelain (pre-audit snapshot)
        MagicMock(exit_code=0, stdout=""),                                          # write patch
        MagicMock(exit_code=0, stdout=""),                                          # git apply
        MagicMock(exit_code=0),                                                     # rm patch
        MagicMock(exit_code=0, stdout=" M src/requests/models.py\n"),               # status --porcelain (post-audit)
        MagicMock(exit_code=0, stdout=VALID_DIFF),                                  # diff
    ]

    res = BranchPreparationEngine.prepare_branch_inside_guest(
        computer=mock_computer,
        checkout_path="/tmp/requests-7645",
        base_commit=VALID_COMMIT,
        branch_name="spacev/fix-test",
        patch_bytes=VALID_DIFF.encode("utf-8"),
        approved_target_files=["src/requests/models.py"],
        on_collision="fail",
    )

    assert res["success"] is True
    assert res["branch_name"] == "spacev/fix-test"
    assert res["modified_files"] == ["src/requests/models.py"]

    # Verify checkout -b was used (NEVER -B)
    checkout_call = [call for call in mock_computer.run.call_args_list if "checkout" in str(call)][0]
    assert "checkout -b" in str(checkout_call)
    assert "checkout -B" not in str(checkout_call)


def test_branch_preparation_does_not_overwrite_existing_branch_fails_safely():
    mock_computer = MagicMock()
    mock_computer.run.side_effect = [
        MagicMock(exit_code=0, stdout=f"{VALID_COMMIT}\n"),  # rev-parse HEAD
        MagicMock(exit_code=0),                              # rev-parse refs/heads/branch (EXISTS!)
    ]

    res = BranchPreparationEngine.prepare_branch_inside_guest(
        computer=mock_computer,
        checkout_path="/tmp/requests-7645",
        base_commit=VALID_COMMIT,
        branch_name="spacev/fix-test",
        patch_bytes=VALID_DIFF.encode("utf-8"),
        approved_target_files=["src/requests/models.py"],
        on_collision="fail",
    )

    assert res["success"] is False
    assert "already exists in guest repository. Refusing to overwrite" in res["error"]


def test_branch_preparation_collision_safe_generates_unique_suffix():
    mock_computer = MagicMock()
    mock_computer.run.side_effect = [
        MagicMock(exit_code=0, stdout=f"{VALID_COMMIT}\n"),  # rev-parse HEAD
        MagicMock(exit_code=0),                              # check spacev/fix-test (EXISTS)
        MagicMock(exit_code=0),                              # resolve: check spacev/fix-test (EXISTS)
        MagicMock(exit_code=1),                              # resolve: check spacev/fix-test-v1 (DOES NOT EXIST -> WINNER)
        MagicMock(exit_code=0),                              # checkout -b spacev/fix-test-v1
        MagicMock(exit_code=0, stdout=""),                   # pre-audit
        MagicMock(exit_code=0),                              # write patch
        MagicMock(exit_code=0),                              # git apply
        MagicMock(exit_code=0),                              # rm patch
        MagicMock(exit_code=0, stdout=" M src/requests/models.py\n"),  # post-audit
        MagicMock(exit_code=0, stdout=VALID_DIFF),           # diff
    ]

    res = BranchPreparationEngine.prepare_branch_inside_guest(
        computer=mock_computer,
        checkout_path="/tmp/requests-7645",
        base_commit=VALID_COMMIT,
        branch_name="spacev/fix-test",
        patch_bytes=VALID_DIFF.encode("utf-8"),
        approved_target_files=["src/requests/models.py"],
        on_collision="suffix",
    )

    assert res["success"] is True
    assert res["branch_name"] == "spacev/fix-test-v1"


def test_branch_preparation_detects_unexpected_untracked_files_and_cleans_only_them():
    mock_computer = MagicMock()
    # Pre-status has pre-existing user data 'user_scratch.txt'
    # Post-status has 'user_scratch.txt' AND newly created 'evil_untracked.py'
    mock_computer.run.side_effect = [
        MagicMock(exit_code=0, stdout=f"{VALID_COMMIT}\n"),
        MagicMock(exit_code=1),  # branch does not exist
        MagicMock(exit_code=0),  # checkout -b
        MagicMock(exit_code=0, stdout="?? user_scratch.txt\n"),  # pre-audit snapshot
        MagicMock(exit_code=0),  # write patch
        MagicMock(exit_code=0),  # apply
        MagicMock(exit_code=0),  # rm patch
        MagicMock(exit_code=0, stdout="?? user_scratch.txt\n?? evil_untracked.py\n M src/requests/models.py\n"),  # post-audit
        MagicMock(exit_code=0),  # rm -rf evil_untracked.py (selective cleanup)
        MagicMock(exit_code=0),  # git checkout -- models.py
    ]

    res = BranchPreparationEngine.prepare_branch_inside_guest(
        computer=mock_computer,
        checkout_path="/tmp/requests-7645",
        base_commit=VALID_COMMIT,
        branch_name="spacev/fix-test",
        patch_bytes=VALID_DIFF.encode("utf-8"),
        approved_target_files=["src/requests/models.py"],
    )

    assert res["success"] is False
    assert "Unexpected untracked files created: ['evil_untracked.py']" in res["error"]

    # Verify selective rollback only deleted 'evil_untracked.py' and DID NOT delete 'user_scratch.txt'
    rm_calls = [str(call) for call in mock_computer.run.call_args_list if "rm -rf" in str(call)]
    assert any("evil_untracked.py" in c for c in rm_calls)
    assert not any("user_scratch.txt" in c for c in rm_calls)


def test_branch_preparation_detects_unexpected_file_deletion():
    mock_computer = MagicMock()
    mock_computer.run.side_effect = [
        MagicMock(exit_code=0, stdout=f"{VALID_COMMIT}\n"),
        MagicMock(exit_code=1),  # branch does not exist
        MagicMock(exit_code=0),  # checkout -b
        MagicMock(exit_code=0, stdout=""),  # pre-audit
        MagicMock(exit_code=0),  # write patch
        MagicMock(exit_code=0),  # apply
        MagicMock(exit_code=0),  # rm patch
        MagicMock(exit_code=0, stdout=" D unexpected_deleted.py\n M src/requests/models.py\n"),  # post-audit
        MagicMock(exit_code=0),  # git checkout -- unexpected_deleted.py
        MagicMock(exit_code=0),  # git checkout -- models.py
    ]

    res = BranchPreparationEngine.prepare_branch_inside_guest(
        computer=mock_computer,
        checkout_path="/tmp/requests-7645",
        base_commit=VALID_COMMIT,
        branch_name="spacev/fix-test",
        patch_bytes=VALID_DIFF.encode("utf-8"),
        approved_target_files=["src/requests/models.py"],
    )

    assert res["success"] is False
    assert "Unexpected file deletions: ['unexpected_deleted.py']" in res["error"]


def test_branch_preparation_detects_unexpected_file_renaming():
    mock_computer = MagicMock()
    mock_computer.run.side_effect = [
        MagicMock(exit_code=0, stdout=f"{VALID_COMMIT}\n"),
        MagicMock(exit_code=1),  # branch does not exist
        MagicMock(exit_code=0),  # checkout -b
        MagicMock(exit_code=0, stdout=""),  # pre-audit
        MagicMock(exit_code=0),  # write patch
        MagicMock(exit_code=0),  # apply
        MagicMock(exit_code=0),  # rm patch
        MagicMock(exit_code=0, stdout=" R old.py -> new.py\n M src/requests/models.py\n"),  # post-audit
        MagicMock(exit_code=0),  # git checkout -- new.py
        MagicMock(exit_code=0),  # git checkout -- models.py
    ]

    res = BranchPreparationEngine.prepare_branch_inside_guest(
        computer=mock_computer,
        checkout_path="/tmp/requests-7645",
        base_commit=VALID_COMMIT,
        branch_name="spacev/fix-test",
        patch_bytes=VALID_DIFF.encode("utf-8"),
        approved_target_files=["src/requests/models.py"],
    )

    assert res["success"] is False
    assert "Unexpected file renamings: ['new.py']" in res["error"]


# ---------------------------------------------------------------------------
# Phase 3: Actual Commit Execution Inside Guest Tests
# ---------------------------------------------------------------------------

def test_commit_execution_inside_guest_success():
    prop, evid = make_valid_proposal_and_evidence()
    bundle = EvidenceValidator.validate_evidence(prop, evid)
    commit_bundle = CommitSynthesisEngine.generate_commit_bundle(bundle, "spacev/fix-test")

    mock_computer = MagicMock()
    mock_computer.run.side_effect = [
        MagicMock(exit_code=0, stdout="spacev/fix-test\n"),        # symbolic-ref HEAD (branch check)
        MagicMock(exit_code=0, stdout=f"{VALID_COMMIT}\n"),        # rev-parse HEAD (base commit check)
        MagicMock(exit_code=0),                                    # git reset
        MagicMock(exit_code=0),                                    # git add src/requests/models.py
        MagicMock(exit_code=0, stdout="src/requests/models.py\n"), # diff --cached --name-only
        MagicMock(exit_code=0),                                    # write commit message
        MagicMock(exit_code=0, stdout="[spacev/fix-test 8f9a2b3]"),# git commit
        MagicMock(exit_code=0),                                    # rm commit msg
        MagicMock(exit_code=0, stdout=f"{VALID_NEW_COMMIT}\n"),    # rev-parse HEAD (new commit SHA)
        MagicMock(exit_code=0, stdout=VALID_DIFF),                 # diff base_commit HEAD
    ]

    res = CommitExecutionEngine.execute_commit_inside_guest(
        computer=mock_computer,
        checkout_path="/tmp/requests-7645",
        expected_branch="spacev/fix-test",
        base_commit=VALID_COMMIT,
        commit_bundle=commit_bundle,
        approved_target_files=["src/requests/models.py"],
    )

    assert res["success"] is True
    receipt: ExecutedCommitReceipt = res["receipt"]
    assert receipt.commit_sha == VALID_NEW_COMMIT
    assert receipt.branch_name == "spacev/fix-test"
    assert receipt.base_commit == VALID_COMMIT
    assert receipt.staged_files == ["src/requests/models.py"]
    assert receipt.is_pushed is False  # Strictly False (no remote push)

    # Verify no git push was called
    for call in mock_computer.run.call_args_list:
        assert "git push" not in str(call)


def test_commit_execution_rejects_branch_mismatch():
    prop, evid = make_valid_proposal_and_evidence()
    bundle = EvidenceValidator.validate_evidence(prop, evid)
    commit_bundle = CommitSynthesisEngine.generate_commit_bundle(bundle, "spacev/fix-test")

    mock_computer = MagicMock()
    mock_computer.run.return_value = MagicMock(exit_code=0, stdout="main\n")  # Wrong branch

    res = CommitExecutionEngine.execute_commit_inside_guest(
        computer=mock_computer,
        checkout_path="/tmp/requests-7645",
        expected_branch="spacev/fix-test",
        base_commit=VALID_COMMIT,
        commit_bundle=commit_bundle,
        approved_target_files=["src/requests/models.py"],
    )

    assert res["success"] is False
    assert "Branch mismatch" in res["error"]


def test_commit_execution_rejects_base_commit_mismatch():
    prop, evid = make_valid_proposal_and_evidence()
    bundle = EvidenceValidator.validate_evidence(prop, evid)
    commit_bundle = CommitSynthesisEngine.generate_commit_bundle(bundle, "spacev/fix-test")

    mock_computer = MagicMock()
    mock_computer.run.side_effect = [
        MagicMock(exit_code=0, stdout="spacev/fix-test\n"),
        MagicMock(exit_code=0, stdout="0" * 40 + "\n"),  # Base commit mismatch
    ]

    res = CommitExecutionEngine.execute_commit_inside_guest(
        computer=mock_computer,
        checkout_path="/tmp/requests-7645",
        expected_branch="spacev/fix-test",
        base_commit=VALID_COMMIT,
        commit_bundle=commit_bundle,
        approved_target_files=["src/requests/models.py"],
    )

    assert res["success"] is False
    assert "Base commit mismatch before commit" in res["error"]


def test_commit_execution_rejects_unapproved_staged_files():
    prop, evid = make_valid_proposal_and_evidence()
    bundle = EvidenceValidator.validate_evidence(prop, evid)
    commit_bundle = CommitSynthesisEngine.generate_commit_bundle(bundle, "spacev/fix-test")

    mock_computer = MagicMock()
    mock_computer.run.side_effect = [
        MagicMock(exit_code=0, stdout="spacev/fix-test\n"),
        MagicMock(exit_code=0, stdout=f"{VALID_COMMIT}\n"),
        MagicMock(exit_code=0),  # reset
        MagicMock(exit_code=0),  # add
        MagicMock(exit_code=0, stdout="src/requests/models.py\nevil.py\n"),  # Unapproved staged file!
        MagicMock(exit_code=0),  # reset rollback
    ]

    res = CommitExecutionEngine.execute_commit_inside_guest(
        computer=mock_computer,
        checkout_path="/tmp/requests-7645",
        expected_branch="spacev/fix-test",
        base_commit=VALID_COMMIT,
        commit_bundle=commit_bundle,
        approved_target_files=["src/requests/models.py"],
    )

    assert res["success"] is False
    assert "Staged file evil.py is not among approved target_files" in res["error"]


# ---------------------------------------------------------------------------
# Phase 4 & 5: Commit & PR Synthesis Quality Tests
# ---------------------------------------------------------------------------

def test_pr_title_has_no_truncation_artifacts():
    prop, evid = make_valid_proposal_and_evidence()
    # Provide a long explanation to test clean clause/word boundary extraction without trailing '...'
    prop["explanation"] = (
        "In Response.iter_lines(), coerce delimiter between str and bytes to match chunk type returned by iter_content()."
    )
    bundle = EvidenceValidator.validate_evidence(prop, evid)
    commit = CommitSynthesisEngine.generate_commit_bundle(bundle, "spacev/fix-test")

    assert commit.commit_title.startswith("fix(models):")
    assert not commit.commit_title.endswith("...")
    assert not commit.commit_title.endswith("..")
    assert len(commit.commit_title) <= 85


def test_pr_synthesis_contains_all_8_sections():
    prop, evid = make_valid_proposal_and_evidence()
    bundle = EvidenceValidator.validate_evidence(prop, evid)
    commit = CommitSynthesisEngine.generate_commit_bundle(bundle, "spacev/fix-test")
    pr = PRSynthesisEngine.synthesize_pr(bundle, commit, base_branch="main", commit_sha=VALID_NEW_COMMIT)

    assert "## 1. Problem Summary" in pr.pr_body
    assert "## 2. Root Cause Analysis" in pr.pr_body
    assert "## 3. Proposed Fix" in pr.pr_body
    assert "## 4. Before & After Behavior" in pr.pr_body
    assert "## 5. Files Changed" in pr.pr_body
    assert "## 6. Reproduction Steps" in pr.pr_body
    assert "## 7. Tests Executed & Empirical Verification" in pr.pr_body
    assert "## 8. Known Limitations & Compatibility Scope" in pr.pr_body
    assert pr.target_repository == "https://github.com/psf/requests"
    assert pr.branch_name == "spacev/fix-test"
    assert pr.commit_sha == VALID_NEW_COMMIT


def test_pr_reproduction_steps_valid_markdown_no_prose_in_code_block():
    prop, evid = make_valid_proposal_and_evidence()
    bundle = EvidenceValidator.validate_evidence(prop, evid)
    commit = CommitSynthesisEngine.generate_commit_bundle(bundle, "spacev/fix-test")
    pr = PRSynthesisEngine.synthesize_pr(bundle, commit)

    # Extract reproduction steps section
    repro_section = pr.pr_body.split("## 6. Reproduction Steps")[1].split("## 7. Tests Executed")[0]

    # Verify python block inside repro section contains only valid python code, not conversational prose
    assert "```python" in repro_section
    py_code = repro_section.split("```python")[1].split("```")[0]
    compile(py_code, "<string>", "exec")  # Raises SyntaxError if invalid python!


def test_pr_distinguishes_executed_from_planned_tests_with_counts():
    prop, evid = make_valid_proposal_and_evidence()
    bundle = EvidenceValidator.validate_evidence(prop, evid)
    commit = CommitSynthesisEngine.generate_commit_bundle(bundle, "spacev/fix-test")
    pr = PRSynthesisEngine.synthesize_pr(bundle, commit)

    test_section = pr.pr_body.split("## 7. Tests Executed")[1].split("## 8. Known Limitations")[0]
    assert "**Targeted In-Guest Test Status:** `PASSED` (Exit Code: `0`)" in test_section
    assert "**Test Counts:** `3` passed, `0` failed, `0` skipped" in test_section
    assert "Planned Upstream Regression Suite (CI Scope)" in test_section
    assert "Full repository test suites should be validated in CI before merging" in test_section


# ---------------------------------------------------------------------------
# Phase 6: Publishing Authorization & Multi-Boundary Gates
# ---------------------------------------------------------------------------

def test_publishing_rejects_step_2_5_patch_approval_token():
    prop, evid = make_valid_proposal_and_evidence()
    bundle = EvidenceValidator.validate_evidence(prop, evid)
    commit = CommitSynthesisEngine.generate_commit_bundle(bundle, "spacev/fix-test")
    pr = PRSynthesisEngine.synthesize_pr(bundle, commit)

    manager = GitHubPublishingAuthorizationManager()
    proposal = manager.create_publishing_proposal(bundle, commit, pr)
    pid = proposal.proposal_id

    # Attempting to use the Step 2.5 patch approval token to authorize publishing must be rejected
    patch_token = "approve patch patch-77ca97735008"
    ok, msg = manager.approve_action(pid, "pr", patch_token)
    assert ok is False
    assert "Step 2.5 patch approval token cannot authorize publishing" in msg


def test_publishing_proposal_binds_to_exact_commit_and_pr_body_hash():
    prop, evid = make_valid_proposal_and_evidence()
    bundle = EvidenceValidator.validate_evidence(prop, evid)
    commit = CommitSynthesisEngine.generate_commit_bundle(bundle, "spacev/fix-test")
    pr = PRSynthesisEngine.synthesize_pr(bundle, commit)

    manager = GitHubPublishingAuthorizationManager()
    proposal = manager.create_publishing_proposal(bundle, commit, pr, commit_sha=VALID_NEW_COMMIT)

    assert proposal.commit_sha == VALID_NEW_COMMIT
    assert len(proposal.pr_body_hash) == 64

    # Approve all stages
    pid = proposal.proposal_id
    manager.approve_action(pid, "fork", f"approve fork {pid}")
    manager.approve_action(pid, "push", f"approve push {pid}")
    manager.approve_action(pid, "pr", f"approve pr {pid}")

    # Tamper with PR body in storage
    proposal.pr_body = proposal.pr_body + "\n[TAMPERED CONTENT]"

    # Publishing must reject tampered body
    res = manager.publish_pr(pid, dry_run=True)
    assert res["success"] is False
    assert "PR body tampering detected" in res["error"]


def test_publishing_requires_distinct_approval_gates():
    prop, evid = make_valid_proposal_and_evidence()
    bundle = EvidenceValidator.validate_evidence(prop, evid)
    commit = CommitSynthesisEngine.generate_commit_bundle(bundle, "spacev/fix-test")
    pr = PRSynthesisEngine.synthesize_pr(bundle, commit)

    manager = GitHubPublishingAuthorizationManager()
    proposal = manager.create_publishing_proposal(bundle, commit, pr)
    pid = proposal.proposal_id

    # 1. Approve fork
    ok_fork, msg_fork = manager.approve_action(pid, "fork", f"approve fork {pid}")
    assert ok_fork is True
    assert proposal.fork_approved is True

    # 2. Approve push
    ok_push, msg_push = manager.approve_action(pid, "push", f"approve push {pid}")
    assert ok_push is True
    assert proposal.push_approved is True

    # 3. Approve PR
    ok_pr, msg_pr = manager.approve_action(pid, "pr", f"approve pr {pid}")
    assert ok_pr is True
    assert proposal.pr_approved is True
    assert proposal.status == "FULLY_APPROVED"


def test_publishing_rejects_action_without_approval():
    prop, evid = make_valid_proposal_and_evidence()
    bundle = EvidenceValidator.validate_evidence(prop, evid)
    commit = CommitSynthesisEngine.generate_commit_bundle(bundle, "spacev/fix-test")
    pr = PRSynthesisEngine.synthesize_pr(bundle, commit)

    manager = GitHubPublishingAuthorizationManager()
    proposal = manager.create_publishing_proposal(bundle, commit, pr)

    # Attempt to publish before approval
    res = manager.publish_pr(proposal.proposal_id, dry_run=True)
    assert res["success"] is False
    assert "has not received all required approvals" in res["error"]


def test_publishing_rejects_pr_approval_before_push_approval():
    prop, evid = make_valid_proposal_and_evidence()
    bundle = EvidenceValidator.validate_evidence(prop, evid)
    commit = CommitSynthesisEngine.generate_commit_bundle(bundle, "spacev/fix-test")
    pr = PRSynthesisEngine.synthesize_pr(bundle, commit)

    manager = GitHubPublishingAuthorizationManager()
    proposal = manager.create_publishing_proposal(bundle, commit, pr)
    pid = proposal.proposal_id

    # Attempting to approve PR directly skips push approval
    ok, msg = manager.approve_action(pid, "pr", f"approve pr {pid}")
    assert ok is False
    assert "Cannot approve PR submission before branch push is authorized" in msg


def test_publishing_rejects_push_approval_before_fork_approval_when_fork_required():
    prop, evid = make_valid_proposal_and_evidence()
    bundle = EvidenceValidator.validate_evidence(prop, evid)
    commit = CommitSynthesisEngine.generate_commit_bundle(bundle, "spacev/fix-test")
    pr = PRSynthesisEngine.synthesize_pr(bundle, commit)

    manager = GitHubPublishingAuthorizationManager()
    proposal = manager.create_publishing_proposal(bundle, commit, pr)
    proposal.requires_fork = True
    pid = proposal.proposal_id

    # Attempting push approval before fork
    ok, msg = manager.approve_action(pid, "push", f"approve push {pid}")
    assert ok is False
    assert "Cannot approve push before fork is authorized" in msg


def test_publishing_rejects_token_replay_after_published():
    prop, evid = make_valid_proposal_and_evidence()
    bundle = EvidenceValidator.validate_evidence(prop, evid)
    commit = CommitSynthesisEngine.generate_commit_bundle(bundle, "spacev/fix-test")
    pr = PRSynthesisEngine.synthesize_pr(bundle, commit)

    manager = GitHubPublishingAuthorizationManager()
    proposal = manager.create_publishing_proposal(bundle, commit, pr)
    pid = proposal.proposal_id

    # Approve all stages
    manager.approve_action(pid, "fork", f"approve fork {pid}")
    manager.approve_action(pid, "push", f"approve push {pid}")
    manager.approve_action(pid, "pr", f"approve pr {pid}")

    # Publish dry run
    res = manager.publish_pr(pid, dry_run=True)
    assert res["success"] is True

    # Replay approval
    ok_replay, msg_replay = manager.approve_action(pid, "pr", f"approve pr {pid}")
    assert ok_replay is False
    assert "already been published. Replay rejected" in msg_replay


def test_github_permission_probe_mock_direct_push_vs_fork():
    manager = GitHubPublishingAuthorizationManager()

    # Mock direct push permitted (owner/maintainer)
    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"permissions": {"push": True}}).encode("utf-8")
        mock_url.return_value.__enter__.return_value = mock_resp

        probe_direct = manager._probe_github_permissions("fake_token_12345", "https://github.com/psf/requests.git")
        assert probe_direct["requires_fork"] is False
        assert probe_direct["can_push"] is True

    # Mock push not permitted (external contributor, requires fork)
    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"permissions": {"push": False}}).encode("utf-8")
        mock_url.return_value.__enter__.return_value = mock_resp

        probe_fork = manager._probe_github_permissions("fake_token_12345", "https://github.com/psf/requests.git")
        assert probe_fork["requires_fork"] is True
        assert probe_fork["can_push"] is False
