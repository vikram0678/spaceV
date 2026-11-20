"""Unit, regression, and security tests for SpaceV's Fix Generation and Patch Approval Gate."""

from __future__ import annotations

import hashlib
import json
import time
from unittest.mock import MagicMock

import pytest

from core.issue_patch_manager import PatchApprovalManager, ProposedPatch, normalize_repository_url

VALID_COMMIT = "3c7baaa05ab4aa49cc819ce3a819d260de19c157"
VALID_COMMIT_2 = "abcdef1234567890abcdef1234567890abcdef12"


def test_normalize_repository_url_canonical_matrix():
    """Verify supported HTTPS, SSH, and SCP-style URLs canonicalize correctly."""
    assert (
        normalize_repository_url("https://github.com/psf/requests.git")
        == "https://github.com/psf/requests"
    )
    assert (
        normalize_repository_url("https://github.com/psf/requests")
        == "https://github.com/psf/requests"
    )
    assert (
        normalize_repository_url("https://github.com/psf/requests/")
        == "https://github.com/psf/requests"
    )
    assert (
        normalize_repository_url("https://github.com:443/psf/requests.git")
        == "https://github.com/psf/requests"
    )
    assert (
        normalize_repository_url("git@github.com:psf/requests.git")
        == "ssh://git@github.com/psf/requests"
    )
    assert (
        normalize_repository_url("ssh://git@github.com/psf/requests.git")
        == "ssh://git@github.com/psf/requests"
    )
    assert (
        normalize_repository_url("ssh://git@github.com:22/psf/requests.git")
        == "ssh://git@github.com/psf/requests"
    )


def test_normalize_repository_url_rejects_protocol_downgrade():
    """Verify that insecure HTTP URLs are rejected to prevent protocol downgrade attacks."""
    with pytest.raises(ValueError, match="Protocol downgrade rejected: insecure HTTP is not permitted"):
        normalize_repository_url("http://github.com/psf/requests.git")
    with pytest.raises(ValueError, match="Protocol downgrade rejected: insecure HTTP is not permitted"):
        normalize_repository_url("http://github.com/psf/requests")


def test_normalize_repository_url_rejects_non_standard_ports():
    """Verify that non-standard ports (anything other than 443 for HTTPS or 22 for SSH) are rejected."""
    with pytest.raises(ValueError, match="Non-standard HTTPS port 8443 is rejected"):
        normalize_repository_url("https://github.com:8443/psf/requests.git")
    with pytest.raises(ValueError, match="Non-standard HTTPS port 8080 is rejected"):
        normalize_repository_url("https://github.com:8080/psf/requests.git")
    with pytest.raises(ValueError, match="Non-standard SSH port 2222 is rejected"):
        normalize_repository_url("ssh://git@github.com:2222/psf/requests.git")


def test_normalize_repository_url_rejects_embedded_credentials():
    """Verify that embedded credentials, tokens, or passwords are strictly rejected."""
    with pytest.raises(ValueError, match="Embedded passwords in repository URLs are rejected"):
        normalize_repository_url("https://user:password@github.com/psf/requests.git")
    with pytest.raises(ValueError, match="Embedded credentials in HTTPS repository URLs are rejected"):
        normalize_repository_url("https://token@github.com/psf/requests.git")
    with pytest.raises(ValueError, match="Embedded passwords in repository URLs are rejected"):
        normalize_repository_url("ssh://git:secret@github.com/psf/requests.git")
    with pytest.raises(ValueError, match="SSH repository URLs must use user 'git'"):
        normalize_repository_url("ssh://admin@github.com/psf/requests.git")


def test_normalize_repository_url_rejects_lookalike_and_untrusted_hosts():
    """Verify that lookalike, IP-based, and untrusted hostnames are rejected or do not match target."""
    target_canonical = "https://github.com/psf/requests"

    # Distinct lookalike domains normalize to their own domain and NEVER match github.com
    assert normalize_repository_url("https://evil-github.com/psf/requests.git") != target_canonical
    assert normalize_repository_url("https://github.com.attacker.com/psf/requests.git") != target_canonical
    assert normalize_repository_url("https://github.com/attacker/requests.git") != target_canonical

    # IP addresses, localhost, and single-label hosts are rejected outright
    with pytest.raises(ValueError, match="Invalid or untrusted hostname"):
        normalize_repository_url("https://192.168.1.1/psf/requests.git")
    with pytest.raises(ValueError, match="Invalid or untrusted hostname"):
        normalize_repository_url("https://127.0.0.1/psf/requests.git")
    with pytest.raises(ValueError, match="Invalid or untrusted hostname"):
        normalize_repository_url("https://localhost/psf/requests.git")


def test_normalize_repository_url_rejects_ambiguous_and_malformed_paths():
    """Verify that missing paths, single-segment paths, traversal, and empty URLs raise ValueError."""
    invalid = [
        "",
        "   ",
        "not_a_url",
        "https://",
        "https://github.com",
        "https://github.com/",
        "https://github.com/psf",
        "https://github.com/psf/requests/../evil",
        "git@github.com:",
        "git@github.com:psf",
        "ftp://github.com/psf/requests.git",
        "file:///tmp/requests",
    ]
    for inv in invalid:
        with pytest.raises(ValueError):
            normalize_repository_url(inv)


def test_propose_patch_creates_valid_bound_proposal():
    manager = PatchApprovalManager()
    diff = "--- a/src/requests/models.py\n+++ b/src/requests/models.py\n@@ -1020,1 +1020,1 @@\n"
    patch = manager.propose_patch(
        repository_url="https://github.com/psf/requests.git",
        base_commit=VALID_COMMIT,
        checkout_path="/tmp/requests-7645",
        target_files=["src/requests/models.py"],
        diff_content=diff,
        explanation="Coerce delimiter to match chunk type.",
        behavior_before="Raises TypeError on bytes.split(str)",
        behavior_after="Splits cleanly without type collision",
        compatibility_notes="Preserves all existing string and bytes behavior",
        regression_tests_plan=["test_iter_lines_str_delimiter_none_encoding"],
    )

    assert patch.patch_id.startswith("patch-")
    assert patch.status == "PENDING_APPROVAL"
    assert len(patch.patch_hash) == 64
    assert patch.patch_hash == hashlib.sha256(diff.encode("utf-8")).hexdigest()
    assert patch.approval_token == f"approve patch {patch.patch_id}"
    assert "src/requests/models.py" in patch.target_files


def test_propose_patch_rejects_abbreviated_and_malformed_commits():
    """Verify that abbreviated or malformed commits are rejected at proposal time."""
    manager = PatchApprovalManager()

    # Abbreviated 7-char commit
    with pytest.raises(ValueError, match="Valid full commit hash"):
        manager.propose_patch(
            repository_url="https://github.com/psf/requests.git",
            base_commit="abc1234",
            checkout_path="/tmp/requests-7645",
            target_files=["src/file.py"],
            diff_content="diff",
            explanation="e",
            behavior_before="b",
            behavior_after="a",
            compatibility_notes="c",
        )

    # Malformed non-hex commit
    with pytest.raises(ValueError, match="Valid full commit hash"):
        manager.propose_patch(
            repository_url="https://github.com/psf/requests.git",
            base_commit="zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz",
            checkout_path="/tmp/requests-7645",
            target_files=["src/file.py"],
            diff_content="diff",
            explanation="e",
            behavior_before="b",
            behavior_after="a",
            compatibility_notes="c",
        )

    # Empty commit
    with pytest.raises(ValueError, match="Valid full commit hash"):
        manager.propose_patch(
            repository_url="https://github.com/psf/requests.git",
            base_commit="",
            checkout_path="/tmp/requests-7645",
            target_files=["src/file.py"],
            diff_content="diff",
            explanation="e",
            behavior_before="b",
            behavior_after="a",
            compatibility_notes="c",
        )


def test_propose_patch_rejects_unsafe_paths_and_traversal():
    manager = PatchApprovalManager()

    # Traversal in target files
    with pytest.raises(ValueError, match="Unsafe target file path escapes repository"):
        manager.propose_patch(
            repository_url="https://github.com/psf/requests.git",
            base_commit=VALID_COMMIT,
            checkout_path="/tmp/requests-7645",
            target_files=["../outside.py"],
            diff_content="diff content",
            explanation="test",
            behavior_before="b",
            behavior_after="a",
            compatibility_notes="c",
        )

    # Absolute path in target files
    with pytest.raises(ValueError, match="Unsafe target file path escapes repository"):
        manager.propose_patch(
            repository_url="https://github.com/psf/requests.git",
            base_commit=VALID_COMMIT,
            checkout_path="/tmp/requests-7645",
            target_files=["/etc/passwd"],
            diff_content="diff content",
            explanation="test",
            behavior_before="b",
            behavior_after="a",
            compatibility_notes="c",
        )

    # Traversal in checkout path
    with pytest.raises(ValueError, match="Unsafe checkout path"):
        manager.propose_patch(
            repository_url="https://github.com/psf/requests.git",
            base_commit=VALID_COMMIT,
            checkout_path="/tmp/repo/../../etc",
            target_files=["file.py"],
            diff_content="diff content",
            explanation="test",
            behavior_before="b",
            behavior_after="a",
            compatibility_notes="c",
        )


def test_exact_approved_patch_successfully_applies():
    manager = PatchApprovalManager()
    exact_diff = "--- a/src/requests/models.py\n+++ b/src/requests/models.py\n@@ -1020,1 +1020,1 @@\n"
    patch = manager.propose_patch(
        repository_url="https://github.com/psf/requests.git",
        base_commit=VALID_COMMIT,
        checkout_path="/tmp/requests-7645",
        target_files=["src/requests/models.py"],
        diff_content=exact_diff,
        explanation="test",
        behavior_before="b",
        behavior_after="a",
        compatibility_notes="c",
    )

    # Cannot apply before approval
    res_unapproved = manager.apply_patch_inside_sandbox("s1", patch.patch_id, MagicMock())
    assert res_unapproved["success"] is False
    assert "not in APPROVED state" in res_unapproved["error"]

    # Approve
    ok, msg = manager.approve_patch(
        patch_id=patch.patch_id,
        approval_text=f"approve patch {patch.patch_id}",
        repository_url="https://github.com/psf/requests.git",
        base_commit=VALID_COMMIT,
    )
    assert ok is True
    assert patch.status == "APPROVED"

    # Mock Celesto session
    mock_computer = MagicMock()
    mock_computer.run.side_effect = [
        MagicMock(exit_code=0, stdout=f"{VALID_COMMIT}\n", stderr=""),                  # rev-parse HEAD
        MagicMock(exit_code=0, stdout="https://github.com/psf/requests.git\n"),        # remote get-url origin
        MagicMock(exit_code=0, stdout="", stderr=""),                                  # base64 write
        MagicMock(exit_code=0, stdout="", stderr=""),                                  # git apply
        MagicMock(),                                                                   # rm -f
        MagicMock(exit_code=0, stdout="applied diff content", stderr=""),              # git diff
        MagicMock(exit_code=0, stdout=" M src/requests/models.py\n", stderr=""),      # git status --short
    ]

    mock_session = MagicMock(expired=False)
    mock_session.instance._live_computer = mock_computer
    mock_sandbox_manager = MagicMock(_sessions={"s1": mock_session})

    res = manager.apply_patch_inside_sandbox("s1", patch.patch_id, mock_sandbox_manager)
    assert res["success"] is True
    assert res["modified_files"] == ["src/requests/models.py"]
    assert res["applied_bytes_sha256"] == patch.patch_hash
    assert patch.status == "APPLIED"


def test_failed_remote_lookup_rejects_execution():
    """Verify that if 'git remote get-url origin' fails, execution is rejected."""
    manager = PatchApprovalManager()
    patch = manager.propose_patch(
        repository_url="https://github.com/psf/requests.git",
        base_commit=VALID_COMMIT,
        checkout_path="/tmp/requests-7645",
        target_files=["src/requests/models.py"],
        diff_content="diff",
        explanation="test",
        behavior_before="b",
        behavior_after="a",
        compatibility_notes="c",
    )
    manager.approve_patch(patch.patch_id, f"approve patch {patch.patch_id}")

    mock_computer = MagicMock()
    mock_computer.run.side_effect = [
        MagicMock(exit_code=0, stdout=f"{VALID_COMMIT}\n"),                                 # rev-parse HEAD (ok)
        MagicMock(exit_code=128, stdout="", stderr="fatal: No such remote 'origin'\n"),    # remote get-url fails!
    ]
    mock_session = MagicMock(expired=False)
    mock_session.instance._live_computer = mock_computer
    mock_sandbox_manager = MagicMock(_sessions={"s1": mock_session})

    res = manager.apply_patch_inside_sandbox("s1", patch.patch_id, mock_sandbox_manager)
    assert res["success"] is False
    assert "Failed to retrieve guest repository remote URL" in res["error"]
    assert "No such remote 'origin'" in res["error"]


def test_empty_remote_lookup_rejects_execution():
    """Verify that if 'git remote get-url origin' outputs empty whitespace, execution is rejected."""
    manager = PatchApprovalManager()
    patch = manager.propose_patch(
        repository_url="https://github.com/psf/requests.git",
        base_commit=VALID_COMMIT,
        checkout_path="/tmp/requests-7645",
        target_files=["src/requests/models.py"],
        diff_content="diff",
        explanation="test",
        behavior_before="b",
        behavior_after="a",
        compatibility_notes="c",
    )
    manager.approve_patch(patch.patch_id, f"approve patch {patch.patch_id}")

    mock_computer = MagicMock()
    mock_computer.run.side_effect = [
        MagicMock(exit_code=0, stdout=f"{VALID_COMMIT}\n"),   # rev-parse HEAD (ok)
        MagicMock(exit_code=0, stdout="   \n"),              # remote get-url is empty!
    ]
    mock_session = MagicMock(expired=False)
    mock_session.instance._live_computer = mock_computer
    mock_sandbox_manager = MagicMock(_sessions={"s1": mock_session})

    res = manager.apply_patch_inside_sandbox("s1", patch.patch_id, mock_sandbox_manager)
    assert res["success"] is False
    assert "Guest repository remote URL is empty" in res["error"]


def test_mismatched_and_lookalike_remote_rejects_execution():
    """Verify that lookalike or malicious repository URLs are rejected."""
    manager = PatchApprovalManager()
    patch = manager.propose_patch(
        repository_url="https://github.com/psf/requests.git",
        base_commit=VALID_COMMIT,
        checkout_path="/tmp/requests-7645",
        target_files=["src/requests/models.py"],
        diff_content="diff",
        explanation="test",
        behavior_before="b",
        behavior_after="a",
        compatibility_notes="c",
    )
    manager.approve_patch(patch.patch_id, f"approve patch {patch.patch_id}")

    malicious_urls = [
        "https://evil-github.com/psf/requests.git",
        "https://github.com/attacker/requests.git",
        "https://github.com.attacker.com/psf/requests.git",
        "https://github.com/psf/requests-backdoor.git",
    ]

    for bad_url in malicious_urls:
        mock_computer = MagicMock()
        mock_computer.run.side_effect = [
            MagicMock(exit_code=0, stdout=f"{VALID_COMMIT}\n"),
            MagicMock(exit_code=0, stdout=f"{bad_url}\n"),
        ]
        mock_session = MagicMock(expired=False)
        mock_session.instance._live_computer = mock_computer
        mock_sandbox_manager = MagicMock(_sessions={"s1": mock_session})

        res = manager.apply_patch_inside_sandbox("s1", patch.patch_id, mock_sandbox_manager)
        assert res["success"] is False
        assert "does not match approved repository target" in res["error"]


def test_strict_full_commit_equality_in_guest():
    """Verify that guest commit HEAD matching requires exact full equality, rejecting prefixes."""
    manager = PatchApprovalManager()
    patch = manager.propose_patch(
        repository_url="https://github.com/psf/requests.git",
        base_commit=VALID_COMMIT,
        checkout_path="/tmp/requests-7645",
        target_files=["src/requests/models.py"],
        diff_content="diff",
        explanation="test",
        behavior_before="b",
        behavior_after="a",
        compatibility_notes="c",
    )
    manager.approve_patch(patch.patch_id, f"approve patch {patch.patch_id}")

    # Case 1: Abbreviated commit from guest
    mock_computer = MagicMock()
    mock_computer.run.return_value = MagicMock(exit_code=0, stdout=f"{VALID_COMMIT[:7]}\n")
    mock_session = MagicMock(expired=False)
    mock_session.instance._live_computer = mock_computer
    mock_sandbox_manager = MagicMock(_sessions={"s1": mock_session})

    res = manager.apply_patch_inside_sandbox("s1", patch.patch_id, mock_sandbox_manager)
    assert res["success"] is False
    assert "not a valid full commit hash" in res["error"]

    # Case 2: One-character altered full commit
    altered_commit = VALID_COMMIT[:-1] + ("0" if VALID_COMMIT[-1] != "0" else "1")
    mock_computer.run.return_value = MagicMock(exit_code=0, stdout=f"{altered_commit}\n")
    res2 = manager.apply_patch_inside_sandbox("s1", patch.patch_id, mock_sandbox_manager)
    assert res2["success"] is False
    assert "does not match approved patch base commit" in res2["error"]


def test_one_byte_patch_modification_is_rejected():
    """Verify that altering even a single byte in the patch artifact after approval causes pre-execution rejection."""
    manager = PatchApprovalManager()
    diff = "--- a/src/requests/models.py\n+++ b/src/requests/models.py\n@@ -1020,1 +1020,1 @@\n-line\n+line_new\n"
    patch = manager.propose_patch(
        repository_url="https://github.com/psf/requests.git",
        base_commit=VALID_COMMIT,
        checkout_path="/tmp/requests-7645",
        target_files=["src/requests/models.py"],
        diff_content=diff,
        explanation="test",
        behavior_before="b",
        behavior_after="a",
        compatibility_notes="c",
    )
    manager.approve_patch(patch.patch_id, f"approve patch {patch.patch_id}")

    # One byte modification: change 'line_new' to 'line_nex'
    tampered_diff = diff.replace("line_new", "line_nex")
    patch.diff_content = tampered_diff

    mock_computer = MagicMock()
    mock_session = MagicMock(expired=False)
    mock_session.instance._live_computer = mock_computer
    mock_sandbox_manager = MagicMock(_sessions={"s1": mock_session})

    res = manager.apply_patch_inside_sandbox("s1", patch.patch_id, mock_sandbox_manager)
    assert res["success"] is False
    assert "Pre-execution patch integrity check failed" in res["error"]
    assert "tampered with" in res["error"]
    mock_computer.run.assert_not_called()


def test_changed_hunk_header_rejected_if_it_changes_approved_artifact_bytes():
    """Verify that adding/modifying hunk header comments (e.g. 'class Response:') is rejected."""
    manager = PatchApprovalManager()
    diff = "--- a/src/requests/models.py\n+++ b/src/requests/models.py\n@@ -1017,7 +1017,12 @@\n"
    patch = manager.propose_patch(
        repository_url="https://github.com/psf/requests.git",
        base_commit=VALID_COMMIT,
        checkout_path="/tmp/requests-7645",
        target_files=["src/requests/models.py"],
        diff_content=diff,
        explanation="test",
        behavior_before="b",
        behavior_after="a",
        compatibility_notes="c",
    )
    manager.approve_patch(patch.patch_id, f"approve patch {patch.patch_id}")

    # Alter hunk header by adding 'class Response:'
    patch.diff_content = "--- a/src/requests/models.py\n+++ b/src/requests/models.py\n@@ -1017,7 +1017,12 @@ class Response:\n"

    mock_computer = MagicMock()
    mock_session = MagicMock(expired=False)
    mock_session.instance._live_computer = mock_computer
    mock_sandbox_manager = MagicMock(_sessions={"s1": mock_session})

    res = manager.apply_patch_inside_sandbox("s1", patch.patch_id, mock_sandbox_manager)
    assert res["success"] is False
    assert "Pre-execution patch integrity check failed" in res["error"]
    mock_computer.run.assert_not_called()


def test_changed_trailing_whitespace_rejected():
    """Verify that modifying trailing whitespace or trailing newlines is rejected."""
    manager = PatchApprovalManager()
    diff = "--- a/src/requests/models.py\n+++ b/src/requests/models.py\n@@ -1020,1 +1020,1 @@\n"
    patch = manager.propose_patch(
        repository_url="https://github.com/psf/requests.git",
        base_commit=VALID_COMMIT,
        checkout_path="/tmp/requests-7645",
        target_files=["src/requests/models.py"],
        diff_content=diff,
        explanation="test",
        behavior_before="b",
        behavior_after="a",
        compatibility_notes="c",
    )
    manager.approve_patch(patch.patch_id, f"approve patch {patch.patch_id}")

    # Add trailing whitespace
    patch.diff_content = diff + " \n"

    mock_computer = MagicMock()
    mock_session = MagicMock(expired=False)
    mock_session.instance._live_computer = mock_computer
    mock_sandbox_manager = MagicMock(_sessions={"s1": mock_session})

    res = manager.apply_patch_inside_sandbox("s1", patch.patch_id, mock_sandbox_manager)
    assert res["success"] is False
    assert "Pre-execution patch integrity check failed" in res["error"]
    mock_computer.run.assert_not_called()


def test_replaced_patch_file_rejected_during_recovery(tmp_path):
    """Verify that if proposal file is modified or replaced on disk, recovery fails closed."""
    manager = PatchApprovalManager()
    diff = "--- a/src/file.py\n+++ b/src/file.py\n@@ -1,1 +1,1 @@\n"
    patch = manager.propose_patch(
        repository_url="https://github.com/psf/requests.git",
        base_commit=VALID_COMMIT,
        checkout_path="/tmp/requests-7645",
        target_files=["src/file.py"],
        diff_content=diff,
        explanation="test",
        behavior_before="b",
        behavior_after="a",
        compatibility_notes="c",
    )

    proposal_file = tmp_path / "proposal.json"
    proposal_data = patch.to_dict()
    proposal_file.write_text(json.dumps(proposal_data), encoding="utf-8")

    # Tamper with diff_content on disk while leaving patch_hash unchanged
    proposal_data["diff_content"] = "--- a/src/file.py\n+++ b/src/file.py\n@@ -1,1 +1,1 @@\nTAMPERED\n"
    proposal_file.write_text(json.dumps(proposal_data), encoding="utf-8")

    new_manager = PatchApprovalManager()
    with pytest.raises(ValueError, match="INTEGRITY ERROR: Recovered proposal patch_hash mismatch"):
        new_manager.recover_proposal_from_disk(proposal_file)


def test_changed_repository_or_base_commit_rejected_at_approval():
    """Verify that mismatching repo URL or base commit is rejected at approval time."""
    manager = PatchApprovalManager()
    patch = manager.propose_patch(
        repository_url="https://github.com/psf/requests.git",
        base_commit=VALID_COMMIT,
        checkout_path="/tmp/requests-7645",
        target_files=["src/requests/models.py"],
        diff_content="diff content",
        explanation="test",
        behavior_before="b",
        behavior_after="a",
        compatibility_notes="c",
    )

    # 1. Approval-time rejection: repo mismatch
    ok_repo, msg_repo = manager.approve_patch(
        patch_id=patch.patch_id,
        approval_text=f"approve patch {patch.patch_id}",
        repository_url="https://github.com/pallets/flask.git",
    )
    assert ok_repo is False
    assert "does not match approved patch target" in msg_repo

    # 2. Approval-time rejection: commit mismatch
    ok_commit, msg_commit = manager.approve_patch(
        patch_id=patch.patch_id,
        approval_text=f"approve patch {patch.patch_id}",
        base_commit=VALID_COMMIT_2,
    )
    assert ok_commit is False
    assert "does not match approved patch commit" in msg_commit


def test_expired_approval_rejected():
    manager = PatchApprovalManager(ttl_seconds=0.01)
    patch = manager.propose_patch(
        repository_url="https://github.com/psf/requests.git",
        base_commit=VALID_COMMIT,
        checkout_path="/tmp/requests-7645",
        target_files=["src/requests/models.py"],
        diff_content="diff content",
        explanation="test",
        behavior_before="b",
        behavior_after="a",
        compatibility_notes="c",
    )

    time.sleep(0.02)
    ok, msg = manager.approve_patch(
        patch_id=patch.patch_id,
        approval_text=f"approve patch {patch.patch_id}",
    )
    assert ok is False
    assert "expired" in msg


def test_approval_token_replay_rejected():
    """Verify that once approved and applied, approval tokens and patch IDs cannot be replayed."""
    manager = PatchApprovalManager()
    patch = manager.propose_patch(
        repository_url="https://github.com/psf/requests.git",
        base_commit=VALID_COMMIT,
        checkout_path="/tmp/requests-7645",
        target_files=["src/requests/models.py"],
        diff_content="diff content",
        explanation="test",
        behavior_before="b",
        behavior_after="a",
        compatibility_notes="c",
    )

    # First approval succeeds
    ok1, _ = manager.approve_patch(
        patch_id=patch.patch_id,
        approval_text=f"approve patch {patch.patch_id}",
    )
    assert ok1 is True

    # Replay while in APPROVED state
    ok2, msg2 = manager.approve_patch(
        patch_id=patch.patch_id,
        approval_text=f"approve patch {patch.patch_id}",
    )
    assert ok2 is False
    assert "already approved" in msg2

    # Apply patch
    mock_computer = MagicMock()
    mock_computer.run.side_effect = [
        MagicMock(exit_code=0, stdout=f"{VALID_COMMIT}\n", stderr=""),
        MagicMock(exit_code=0, stdout="https://github.com/psf/requests.git\n"),
        MagicMock(exit_code=0),
        MagicMock(exit_code=0),
        MagicMock(),
        MagicMock(exit_code=0, stdout="diff"),
        MagicMock(exit_code=0, stdout=" M src/requests/models.py\n"),
    ]
    mock_session = MagicMock(expired=False)
    mock_session.instance._live_computer = mock_computer
    mock_sandbox_manager = MagicMock(_sessions={"s1": mock_session})

    res = manager.apply_patch_inside_sandbox("s1", patch.patch_id, mock_sandbox_manager)
    assert res["success"] is True

    # Replay while in APPLIED state
    ok3, msg3 = manager.approve_patch(
        patch_id=patch.patch_id,
        approval_text=f"approve patch {patch.patch_id}",
    )
    assert ok3 is False
    assert "already been applied" in msg3
    assert "Replay is rejected" in msg3


def test_recovery_with_mismatched_patch_and_hash_rejected(tmp_path):
    """Verify that recovery rejects files where recorded hash != sha256(diff_content)."""
    bad_proposal = {
        "patch_id": "patch-tampered123",
        "repository_url": "https://github.com/psf/requests.git",
        "base_commit": VALID_COMMIT,
        "checkout_path": "/tmp/requests-7645",
        "target_files": ["src/requests/models.py"],
        "diff_content": "innocent looking patch",
        "patch_hash": "deadbeef1234567890abcdefdeadbeef1234567890abcdefdeadbeef12345678",
        "explanation": "test",
        "behavior_before": "b",
        "behavior_after": "a",
        "compatibility_notes": "c",
    }
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad_proposal), encoding="utf-8")

    manager = PatchApprovalManager()
    with pytest.raises(ValueError, match="INTEGRITY ERROR: Recovered proposal patch_hash mismatch"):
        manager.recover_proposal_from_disk(p)


def test_no_source_modification_occurs_when_verification_fails():
    """Verify that when pre-execution verification fails, no files are written or modified inside guest."""
    manager = PatchApprovalManager()
    patch = manager.propose_patch(
        repository_url="https://github.com/psf/requests.git",
        base_commit=VALID_COMMIT,
        checkout_path="/tmp/requests-7645",
        target_files=["src/requests/models.py"],
        diff_content="canonical diff",
        explanation="test",
        behavior_before="b",
        behavior_after="a",
        compatibility_notes="c",
    )
    manager.approve_patch(patch.patch_id, f"approve patch {patch.patch_id}")

    # Tamper with patch in-memory
    patch.diff_content = "tampered diff"

    mock_computer = MagicMock()
    mock_session = MagicMock(expired=False)
    mock_session.instance._live_computer = mock_computer
    mock_sandbox_manager = MagicMock(_sessions={"s1": mock_session})

    res = manager.apply_patch_inside_sandbox("s1", patch.patch_id, mock_sandbox_manager)
    assert res["success"] is False
    mock_computer.run.assert_not_called()


def test_apply_patch_reverts_if_unexpected_files_modified():
    manager = PatchApprovalManager()
    patch = manager.propose_patch(
        repository_url="https://github.com/psf/requests.git",
        base_commit=VALID_COMMIT,
        checkout_path="/tmp/requests-7645",
        target_files=["src/requests/models.py"],
        diff_content="mock diff",
        explanation="test",
        behavior_before="b",
        behavior_after="a",
        compatibility_notes="c",
    )
    manager.approve_patch(patch.patch_id, f"approve patch {patch.patch_id}")

    mock_computer = MagicMock()
    mock_computer.run.side_effect = [
        MagicMock(exit_code=0, stdout=f"{VALID_COMMIT}\n"),                           # rev-parse
        MagicMock(exit_code=0, stdout="https://github.com/psf/requests.git\n"),       # remote URL
        MagicMock(exit_code=0),                                                      # write
        MagicMock(exit_code=0),                                                      # git apply
        MagicMock(),                                                                 # rm
        MagicMock(exit_code=0, stdout="diff"),                                       # diff
        MagicMock(exit_code=0, stdout=" M src/requests/models.py\n M setup.py\n"),   # unexpected setup.py!
        MagicMock(exit_code=0),                                                      # checkout -- . (rollback)
    ]

    mock_session = MagicMock(expired=False)
    mock_session.instance._live_computer = mock_computer
    mock_sandbox_manager = MagicMock(_sessions={"s1": mock_session})

    res = manager.apply_patch_inside_sandbox("s1", patch.patch_id, mock_sandbox_manager)
    assert res["success"] is False
    assert "unexpected files" in res["error"]
    assert "setup.py" in res["error"]
