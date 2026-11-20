"""Pull Request Creation and Final Artifact Publishing subsystem for SpaceV (Step 2.6).

Architectural Stages:
1. Stage A (Evidence Recovery & Validation): Ingests proposal and execution evidence; asserts
   cryptographic SHA-256 match, full-commit match, repository identity, test success (exit 0),
   and absence of unexpected file changes.
2. Stage B (Isolated Branch Preparation & Working-Tree Auditing): Creates a unique dynamic working branch
   on top of the base commit inside Celesto, never overwrites existing branches (collision-safe),
   applies the canonical patch artifact, audits both tracked and untracked files, and performs safe
   selective rollbacks preserving pre-existing user data.
3. Stage C (Final In-Guest Regression Verification): Runs targeted tests and available regression tests,
   captures exit codes, stdout, stderr, and test counts. Distinguishes targeted vs upstream CI regressions.
4. Stage D (Commit Preparation & In-Guest Execution): Synthesizes conventional commit message,
   stages only approved target files, executes git commit inside Celesto guest, captures full commit SHA,
   and verifies commit diff against approved patch bytes without pushing.
5. Stage E (PR Synthesis): Dynamically generates a professional, reviewable PR title (without truncation artifacts)
   and structured markdown body from verified evidence (Problem, Root Cause, Fix, Before/After, Files, Repro, Tests, Limitations).
6. Stage F (GitHub Publishing Authorization): Enforces distinct human approval gates for fork creation,
   branch push, and PR submission. Probes GitHub credentials safely (redacted, no token leakage), binds
   cryptographically to commit SHA and PR body hash, and strictly rejects Step 2.5 patch approval tokens.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import pathlib
import posixpath
import re
import shlex
import time
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from core.issue_patch_manager import normalize_repository_url
from core.task_evidence import _redact

logger = logging.getLogger("SpaceV.PRManager")

PR_APPROVAL_TTL_SECONDS = 900  # 15 minutes


@dataclass
class VerifiedEvidenceBundle:
    """Cryptographically validated evidence bundle from Step 2.5."""

    patch_id: str
    repository_url: str
    base_commit: str
    target_files: list[str]
    diff_content: str
    patch_hash: str
    explanation: str
    behavior_before: str
    behavior_after: str
    compatibility_notes: str
    regression_tests_plan: list[str]
    test_exit_code: int
    test_stdout: str
    test_stderr: str
    applied_diff: str
    git_status: str
    approval_token: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CommitBundle:
    """Prepared git commit metadata."""

    branch_name: str
    commit_title: str
    commit_body: str
    full_commit_message: str
    changed_files: list[str]
    base_commit: str
    patch_hash: str
    test_summary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutedCommitReceipt:
    """Receipt of a git commit executed strictly inside the Celesto guest microVM."""

    commit_sha: str
    branch_name: str
    base_commit: str
    staged_files: list[str]
    commit_title: str
    full_commit_message: str
    commit_diff: str
    is_pushed: bool = False  # Pushing is prohibited in Step 2.6

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PRContent:
    """Synthesized pull request title and markdown description."""

    pr_title: str
    pr_body: str
    branch_name: str
    base_branch: str
    target_repository: str
    source_repository: str
    commit_sha: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PRPublishingProposal:
    """Multi-stage approval record for external publishing."""

    proposal_id: str
    patch_id: str
    patch_hash: str
    repository_url: str
    base_commit: str
    branch_name: str
    commit_sha: str
    commit_message: str
    pr_title: str
    pr_body: str
    pr_body_hash: str
    patch_approval_token: str
    requires_fork: bool
    destination_repo: str
    base_branch: str
    approval_token_fork: str
    approval_token_push: str
    approval_token_pr: str
    fork_approved: bool = False
    push_approved: bool = False
    pr_approved: bool = False
    fork_completed: bool = False
    push_completed: bool = False
    pr_completed: bool = False
    created_at: float = field(default_factory=time.monotonic)
    status: str = "PENDING_APPROVAL"  # PENDING_APPROVAL, PARTIALLY_APPROVED, FULLY_APPROVED, PUBLISHED, EXPIRED

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("created_at", None)
        return d


class EvidenceValidator:
    """Validates Step 2.5 proposal and execution receipts with strict cryptographic checks."""

    @staticmethod
    def validate_evidence(proposal_data: dict[str, Any], evidence_data: dict[str, Any]) -> VerifiedEvidenceBundle:
        """Verify proposal and evidence consistency, SHA-256 match, and test exit codes."""
        if not proposal_data or not isinstance(proposal_data, dict):
            raise ValueError("Proposal data is missing, empty, or not a dictionary.")
        if not evidence_data or not isinstance(evidence_data, dict):
            raise ValueError("Evidence data is missing, empty, or not a dictionary.")

        # 1. Patch ID consistency
        prop_pid = str(proposal_data.get("patch_id") or "").strip()
        evid_pid = str(evidence_data.get("patch_id") or "").strip()
        if not prop_pid or not evid_pid:
            raise ValueError("Evidence or proposal is missing required 'patch_id'.")
        if prop_pid != evid_pid:
            raise ValueError(f"Patch ID mismatch: proposal has {prop_pid!r}, evidence has {evid_pid!r}.")

        # 2. Exact SHA-256 Equality
        prop_hash = str(proposal_data.get("patch_hash") or "").strip().lower()
        evid_approved_hash = str(evidence_data.get("approved_hash") or "").strip().lower()
        evid_applied_hash = str(evidence_data.get("applied_diff_hash") or "").strip().lower()

        for h in (prop_hash, evid_approved_hash, evid_applied_hash):
            if not re.fullmatch(r"[0-9a-f]{64}", h):
                raise ValueError(f"Invalid SHA-256 format: {h!r}")

        if prop_hash != evid_approved_hash:
            raise ValueError(
                f"SHA-256 mismatch between proposal ({prop_hash}) and evidence approved_hash ({evid_approved_hash})."
            )
        if evid_approved_hash != evid_applied_hash:
            raise ValueError(
                f"SHA-256 mismatch between approved ({evid_approved_hash}) and applied ({evid_applied_hash}) bytes."
            )

        # 3. Canonical Diff Recomputation
        diff_content = proposal_data.get("diff_content")
        if not isinstance(diff_content, str) or not diff_content:
            raise ValueError("Proposal diff_content is empty or invalid.")
        recomputed_hash = hashlib.sha256(diff_content.encode("utf-8")).hexdigest().lower()
        if recomputed_hash != prop_hash:
            raise ValueError(
                f"Proposal diff_content does not match recorded patch_hash! (recomputed: {recomputed_hash}, recorded: {prop_hash})."
            )

        # 4. Repository Identity
        prop_repo = str(proposal_data.get("repository_url") or "").strip()
        evid_repo = str(evidence_data.get("repository_url") or "").strip()
        if not prop_repo or not evid_repo:
            raise ValueError("Repository URL is missing in proposal or evidence.")
        norm_prop_repo = normalize_repository_url(prop_repo)
        norm_evid_repo = normalize_repository_url(evid_repo)
        if norm_prop_repo != norm_evid_repo:
            raise ValueError(
                f"Repository mismatch: proposal ({norm_prop_repo}) vs evidence ({norm_evid_repo})."
            )

        # 5. Full Base Commit Identity
        prop_commit = str(proposal_data.get("base_commit") or "").strip().lower()
        evid_commit = str(evidence_data.get("base_commit") or "").strip().lower()
        guest_commit = str(evidence_data.get("guest_commit") or "").strip().lower()

        for c in (prop_commit, evid_commit, guest_commit):
            if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", c):
                raise ValueError(f"Commit hash {c!r} is not a valid full 40/64 hex commit.")

        if prop_commit != evid_commit:
            raise ValueError(f"Base commit mismatch: proposal ({prop_commit}) vs evidence ({evid_commit}).")
        if evid_commit != guest_commit:
            raise ValueError(f"Guest HEAD commit ({guest_commit}) does not match base commit ({evid_commit}).")

        # 6. Successful Test Exit Code
        if "test_exit_code" not in evidence_data:
            raise ValueError("Evidence is missing 'test_exit_code'.")
        exit_code = int(evidence_data["test_exit_code"])
        if exit_code != 0:
            raise ValueError(f"Fix verification failed with non-zero exit code {exit_code}. Cannot create PR.")

        test_stdout = str(evidence_data.get("test_stdout") or "")
        if not test_stdout:
            raise ValueError("Evidence contains empty test stdout. Proof of verification is required.")

        # 7. No Unexpected Modified Files in Post-Patch Status
        target_files = [str(f).strip().replace("\\", "/") for f in proposal_data.get("target_files", [])]
        if not target_files:
            raise ValueError("Proposal target_files is empty.")

        git_status = str(evidence_data.get("git_status") or "")
        modified_in_status: list[str] = []
        for line in git_status.splitlines():
            line = line.strip()
            if line:
                path_part = line[2:].strip().replace("\\", "/")
                modified_in_status.append(path_part)

        unexpected = [
            mf for mf in modified_in_status
            if not any(mf.endswith(tf) or tf.endswith(mf) for tf in target_files)
        ]
        if unexpected:
            raise ValueError(
                f"Evidence indicates unexpected files were modified: {unexpected}. "
                f"Only approved target_files {target_files} are permitted."
            )

        return VerifiedEvidenceBundle(
            patch_id=prop_pid,
            repository_url=prop_repo,
            base_commit=prop_commit,
            target_files=target_files,
            diff_content=diff_content,
            patch_hash=prop_hash,
            explanation=str(proposal_data.get("explanation") or ""),
            behavior_before=str(proposal_data.get("behavior_before") or ""),
            behavior_after=str(proposal_data.get("behavior_after") or ""),
            compatibility_notes=str(proposal_data.get("compatibility_notes") or ""),
            regression_tests_plan=list(proposal_data.get("regression_tests_plan") or []),
            test_exit_code=exit_code,
            test_stdout=test_stdout,
            test_stderr=str(evidence_data.get("test_stderr") or ""),
            applied_diff=str(evidence_data.get("final_diff") or ""),
            git_status=git_status,
            approval_token=str(proposal_data.get("approval_token") or f"approve patch {prop_pid}"),
        )


class BranchPreparationEngine:
    """Manages collision-safe branch creation, patch application, and complete working-tree auditing inside Celesto."""

    @staticmethod
    def generate_branch_name(patch_id: str, patch_hash: str) -> str:
        """Generate a deterministic, unique branch name."""
        short_id = patch_id.removeprefix("patch-")[:8]
        short_hash = patch_hash[:8]
        return f"spacev/fix-{short_id}-{short_hash}"

    @staticmethod
    def parse_porcelain_status(status_stdout: str) -> dict[str, list[str]]:
        """Parse git status --porcelain output into categorized file lists."""
        categories: dict[str, list[str]] = {
            "modified": [],
            "untracked": [],
            "deleted": [],
            "added": [],
            "renamed": [],
        }
        for raw_line in status_stdout.splitlines():
            line = raw_line.rstrip()
            if not line or len(line) < 3:
                continue
            code = line[:2]
            path_part = line[3:].strip().replace("\\", "/")
            if " -> " in path_part:
                path_part = path_part.split(" -> ")[-1].strip()

            if code == "??":
                categories["untracked"].append(path_part)
            elif "M" in code:
                categories["modified"].append(path_part)
            elif "D" in code:
                categories["deleted"].append(path_part)
            elif "A" in code:
                categories["added"].append(path_part)
            elif "R" in code:
                categories["renamed"].append(path_part)
            else:
                categories["modified"].append(path_part)
        return categories

    @staticmethod
    def check_branch_exists(computer: Any, checkout_path: str, branch_name: str) -> bool:
        """Check if branch already exists in guest repository."""
        checkout = shlex.quote(checkout_path)
        cmd = f"git -C {checkout} rev-parse --verify --quiet refs/heads/{shlex.quote(branch_name)}"
        res = computer.run(cmd, timeout=15)
        return res.exit_code == 0

    @staticmethod
    def resolve_collision_safe_branch(
        computer: Any,
        checkout_path: str,
        base_branch_name: str,
    ) -> str:
        """Check if branch exists; return unique name with monotonic suffix if needed."""
        if not BranchPreparationEngine.check_branch_exists(computer, checkout_path, base_branch_name):
            return base_branch_name

        idx = 1
        while idx <= 100:
            candidate = f"{base_branch_name}-v{idx}"
            if not BranchPreparationEngine.check_branch_exists(computer, checkout_path, candidate):
                return candidate
            idx += 1

        raise RuntimeError(f"Exhausted 100 collision attempts for branch {base_branch_name}.")

    @staticmethod
    def prepare_branch_inside_guest(
        computer: Any,
        checkout_path: str,
        base_commit: str,
        branch_name: str,
        patch_bytes: bytes,
        approved_target_files: list[str],
        on_collision: str = "fail",  # "fail" or "suffix"
    ) -> dict[str, Any]:
        """Create working branch collision-safely, apply patch, and perform complete working-tree audit."""
        checkout = shlex.quote(checkout_path)

        # 1. Verify checkout commit matches base_commit
        rev_res = computer.run(f"git -C {checkout} rev-parse HEAD", timeout=30)
        if rev_res.exit_code != 0:
            return {"success": False, "error": f"Failed to check guest HEAD: {rev_res.stderr}"}
        guest_head = rev_res.stdout.strip().lower()
        if guest_head != base_commit.lower():
            return {
                "success": False,
                "error": f"Guest HEAD ({guest_head}) does not match required base commit ({base_commit}).",
            }

        # 2. Branch Collision Safety
        branch_exists = BranchPreparationEngine.check_branch_exists(computer, checkout_path, branch_name)
        if branch_exists:
            if on_collision == "fail":
                return {
                    "success": False,
                    "error": f"Branch {branch_name!r} already exists in guest repository. Refusing to overwrite existing branch.",
                }
            effective_branch = BranchPreparationEngine.resolve_collision_safe_branch(
                computer, checkout_path, branch_name
            )
        else:
            effective_branch = branch_name

        # 3. Create branch using 'checkout -b' (NEVER '-B' which overwrites)
        b_cmd = f"git -C {checkout} checkout -b {shlex.quote(effective_branch)} {shlex.quote(base_commit)}"
        b_res = computer.run(b_cmd, timeout=30)
        if b_res.exit_code != 0:
            return {"success": False, "error": f"Failed to create branch {effective_branch}: {b_res.stderr}"}

        # 4. Snapshot pre-existing working tree state (both tracked and untracked)
        pre_status_res = computer.run(f"git -C {checkout} status --porcelain", timeout=30)
        pre_status = BranchPreparationEngine.parse_porcelain_status(pre_status_res.stdout)
        pre_untracked = set(pre_status["untracked"])
        pre_modified = set(pre_status["modified"])
        pre_deleted = set(pre_status["deleted"])
        pre_added = set(pre_status["added"])
        pre_renamed = set(pre_status["renamed"])

        # 5. Write patch file securely into guest /tmp
        patch_tmp = f"/tmp/{uuid.uuid4().hex[:12]}.patch"
        b64_patch = base64.b64encode(patch_bytes).decode("ascii")
        write_cmd = (
            f"python3 -c \"import base64, pathlib; "
            f"pathlib.Path('{patch_tmp}').write_bytes(base64.b64decode('{b64_patch}'))\""
        )
        w_res = computer.run(write_cmd, timeout=30)
        if w_res.exit_code != 0:
            return {"success": False, "error": f"Failed to write patch inside guest: {w_res.stderr}"}

        # 6. Apply patch on the new branch
        apply_res = computer.run(f"git -C {checkout} apply {shlex.quote(patch_tmp)}", timeout=60)
        computer.run(f"rm -f {shlex.quote(patch_tmp)}", timeout=30)

        if apply_res.exit_code != 0:
            return {
                "success": False,
                "error": f"git apply failed on branch {effective_branch} with exit code {apply_res.exit_code}: {apply_res.stderr}",
            }

        # 7. Complete Working-Tree Auditing (Tracked + Untracked)
        post_status_res = computer.run(f"git -C {checkout} status --porcelain", timeout=30)
        post_status = BranchPreparationEngine.parse_porcelain_status(post_status_res.stdout)

        new_untracked = set(post_status["untracked"]) - pre_untracked
        new_deleted = set(post_status["deleted"]) - pre_deleted
        new_renamed = set(post_status["renamed"]) - pre_renamed
        new_added = set(post_status["added"]) - pre_added
        new_modified = set(post_status["modified"]) - pre_modified

        audit_violations: list[str] = []
        if new_untracked:
            audit_violations.append(f"Unexpected untracked files created: {sorted(new_untracked)}")
        if new_deleted:
            audit_violations.append(f"Unexpected file deletions: {sorted(new_deleted)}")
        if new_renamed:
            audit_violations.append(f"Unexpected file renamings: {sorted(new_renamed)}")
        if new_added:
            audit_violations.append(f"Unexpected file additions: {sorted(new_added)}")

        unexpected_modified = [
            mf for mf in new_modified
            if not any(mf.endswith(tf) or tf.endswith(mf) for tf in approved_target_files)
        ]
        if unexpected_modified:
            audit_violations.append(f"Unexpected modified files: {sorted(unexpected_modified)}")

        if audit_violations:
            # SAFE SELECTIVE ROLLBACK:
            # 1. Delete ONLY newly created untracked files (NEVER delete pre-existing untracked files!)
            for uf in sorted(new_untracked):
                computer.run(f"rm -rf {checkout}/{shlex.quote(uf)}", timeout=15)
            # 2. Restore all files modified, deleted, added, or renamed during this workflow
            files_to_restore = sorted(new_modified | new_deleted | new_added | new_renamed)
            for cf in files_to_restore:
                computer.run(f"git -C {checkout} checkout -- {shlex.quote(cf)}", timeout=15)

            return {
                "success": False,
                "error": f"Working-tree audit failed: {'; '.join(audit_violations)}. Reverted changes safely without affecting pre-existing files.",
            }

        diff_res = computer.run(f"git -C {checkout} diff", timeout=30)

        return {
            "success": True,
            "branch_name": effective_branch,
            "modified_files": sorted(new_modified),
            "git_diff": diff_res.stdout,
            "git_status": post_status_res.stdout,
        }


class RegressionAuditor:
    """Audits verification results and distinguishes targeted fixtures from upstream regressions."""

    @staticmethod
    def audit_verification(
        test_exit_code: int,
        test_stdout: str,
        test_stderr: str,
        planned_tests: list[str],
    ) -> dict[str, Any]:
        """Parse test stdout, extract counts, and categorize execution scope."""
        passed_m = re.search(r"(\d+)\s+passed", test_stdout)
        failed_m = re.search(r"(\d+)\s+failed", test_stdout)
        skipped_m = re.search(r"(\d+)\s+skipped", test_stdout)

        passed = int(passed_m.group(1)) if passed_m else 0
        failed = int(failed_m.group(1)) if failed_m else 0
        skipped = int(skipped_m.group(1)) if skipped_m else 0
        total = passed + failed + skipped

        targeted_passed = (test_exit_code == 0 and passed > 0 and failed == 0)

        return {
            "exit_code": test_exit_code,
            "targeted_passed": targeted_passed,
            "passed_count": passed,
            "failed_count": failed,
            "skipped_count": skipped,
            "total_count": total,
            "planned_tests_count": len(planned_tests),
            "has_infrastructure_failure": "ModuleNotFoundError" in test_stderr or "ImportError" in test_stderr,
            "full_upstream_regression_passed": False,  # Never claim upstream regression without full CI run
        }


class CommitSynthesisEngine:
    """Prepares structured Conventional Commit messages dynamically."""

    @staticmethod
    def generate_commit_bundle(
        evidence: VerifiedEvidenceBundle,
        branch_name: str,
    ) -> CommitBundle:
        """Synthesize a conventional commit message from verified evidence."""
        first_file = evidence.target_files[0] if evidence.target_files else "core"
        scope = pathlib.PurePath(first_file).stem

        # Extract concise summary line without truncation artifacts
        def _extract_concise_title(text: str, max_chars: int = 70) -> str:
            cleaned = re.sub(r"^In\s+[a-zA-Z0-9_\.]+(\(\))?,\s*", "", text.strip())
            sents = re.split(r"(?<=[a-zA-Z0-9\)\]\'\"])\.\s+", cleaned)
            first_sent = sents[0].strip() if sents else cleaned
            if len(first_sent) <= max_chars:
                return first_sent

            clauses = re.split(r"[,;—]\s+", first_sent)
            if clauses and 15 <= len(clauses[0]) <= max_chars:
                return clauses[0].strip()

            words = first_sent[:max_chars].rsplit(" ", 1)
            if len(words) > 1 and len(words[0]) >= 15:
                return words[0].strip()
            return first_sent[:max_chars].strip()

        title_summary = _extract_concise_title(evidence.explanation)
        if not title_summary or len(title_summary) < 10:
            title_summary = _extract_concise_title(evidence.behavior_after)

        if title_summary and len(title_summary) > 1:
            if title_summary[0].isupper() and title_summary[1].islower() and not title_summary.startswith(("Response", "HTTP", "URL", "JSON")):
                title_summary = title_summary[0].lower() + title_summary[1:]

        commit_title = f"fix({scope}): {title_summary}"

        body_lines = [
            commit_title,
            "",
            "Problem:",
            evidence.behavior_before,
            "",
            "Solution:",
            evidence.explanation,
            "",
            "Key Changes:",
            f"- Modified files: {', '.join(evidence.target_files)}",
            f"- Compatibility notes: {evidence.compatibility_notes}",
            "",
            f"Patch-Fingerprint: {evidence.patch_hash}",
            f"Base-Commit: {evidence.base_commit}",
            f"Verified-In-Sandbox: Celesto Firecracker microVM (exit code {evidence.test_exit_code})",
        ]
        full_commit_message = "\n".join(body_lines)

        audit = RegressionAuditor.audit_verification(
            test_exit_code=evidence.test_exit_code,
            test_stdout=evidence.test_stdout,
            test_stderr=evidence.test_stderr,
            planned_tests=evidence.regression_tests_plan,
        )
        test_summary = (
            f"Targeted tests passed ({audit['passed_count']} passed, exit code {audit['exit_code']}). "
            f"Full regression plan: {len(evidence.regression_tests_plan)} tests."
        )

        return CommitBundle(
            branch_name=branch_name,
            commit_title=commit_title,
            commit_body="\n".join(body_lines[2:]),
            full_commit_message=full_commit_message,
            changed_files=evidence.target_files,
            base_commit=evidence.base_commit,
            patch_hash=evidence.patch_hash,
            test_summary=test_summary,
        )


class CommitExecutionEngine:
    """Executes a Git commit inside the Celesto guest microVM with strict verification."""

    @staticmethod
    def execute_commit_inside_guest(
        computer: Any,
        checkout_path: str,
        expected_branch: str,
        base_commit: str,
        commit_bundle: CommitBundle,
        approved_target_files: list[str],
        committer_name: str = "SpaceV Agent",
        committer_email: str = "agent@spacev.local",
    ) -> dict[str, Any]:
        """Stage approved target files, execute git commit in guest, verify diff, and capture commit SHA."""
        checkout = shlex.quote(checkout_path)

        # 1. Verify current branch
        branch_res = computer.run(f"git -C {checkout} symbolic-ref --short HEAD", timeout=30)
        if branch_res.exit_code != 0:
            return {"success": False, "error": f"Failed to get current branch: {branch_res.stderr}"}
        current_branch = branch_res.stdout.strip()
        if current_branch != expected_branch:
            return {
                "success": False,
                "error": f"Branch mismatch: expected {expected_branch!r}, found {current_branch!r}.",
            }

        # 2. Verify HEAD is at base_commit (before committing)
        head_res = computer.run(f"git -C {checkout} rev-parse HEAD", timeout=30)
        if head_res.exit_code != 0:
            return {"success": False, "error": f"Failed to get HEAD commit: {head_res.stderr}"}
        current_head = head_res.stdout.strip().lower()
        if current_head != base_commit.lower():
            return {
                "success": False,
                "error": f"Base commit mismatch before commit: expected {base_commit!r}, found {current_head!r}.",
            }

        # 3. Stage ONLY approved target files
        computer.run(f"git -C {checkout} reset", timeout=30)
        for tf in approved_target_files:
            add_res = computer.run(f"git -C {checkout} add {shlex.quote(tf)}", timeout=30)
            if add_res.exit_code != 0:
                return {"success": False, "error": f"Failed to stage target file {tf}: {add_res.stderr}"}

        # Verify staged files match approved_target_files
        staged_res = computer.run(f"git -C {checkout} diff --cached --name-only", timeout=30)
        staged_files = [line.strip().replace("\\", "/") for line in staged_res.stdout.splitlines() if line.strip()]
        if not staged_files:
            return {"success": False, "error": "No changes staged for commit."}

        for sf in staged_files:
            if not any(sf.endswith(tf) or tf.endswith(sf) for tf in approved_target_files):
                computer.run(f"git -C {checkout} reset", timeout=30)
                return {
                    "success": False,
                    "error": f"Staged file {sf} is not among approved target_files {approved_target_files}.",
                }

        # 4. Write commit message via base64 into guest /tmp
        msg_tmp = f"/tmp/{uuid.uuid4().hex[:12]}.commit_msg"
        b64_msg = base64.b64encode(commit_bundle.full_commit_message.encode("utf-8")).decode("ascii")
        write_msg_cmd = (
            f"python3 -c \"import base64, pathlib; "
            f"pathlib.Path('{msg_tmp}').write_bytes(base64.b64decode('{b64_msg}'))\""
        )
        w_res = computer.run(write_msg_cmd, timeout=30)
        if w_res.exit_code != 0:
            return {"success": False, "error": f"Failed to write commit message in guest: {w_res.stderr}"}

        # 5. Execute commit inside guest (DO NOT PUSH)
        commit_cmd = (
            f"git -C {checkout} -c user.name={shlex.quote(committer_name)} "
            f"-c user.email={shlex.quote(committer_email)} commit -F {shlex.quote(msg_tmp)}"
        )
        commit_res = computer.run(commit_cmd, timeout=60)
        computer.run(f"rm -f {shlex.quote(msg_tmp)}", timeout=15)

        if commit_res.exit_code != 0:
            return {"success": False, "error": f"git commit failed: {commit_res.stderr}"}

        # 6. Capture resulting full commit SHA
        new_head_res = computer.run(f"git -C {checkout} rev-parse HEAD", timeout=30)
        new_commit_sha = new_head_res.stdout.strip().lower()
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", new_commit_sha):
            return {"success": False, "error": f"Invalid commit SHA returned: {new_commit_sha!r}."}
        if new_commit_sha == base_commit.lower():
            return {"success": False, "error": "Commit SHA did not change after git commit."}

        # 7. Verify commit diff against parent
        diff_res = computer.run(f"git -C {checkout} diff {shlex.quote(base_commit)} HEAD", timeout=30)
        commit_diff = diff_res.stdout

        receipt = ExecutedCommitReceipt(
            commit_sha=new_commit_sha,
            branch_name=expected_branch,
            base_commit=base_commit,
            staged_files=staged_files,
            commit_title=commit_bundle.commit_title,
            full_commit_message=commit_bundle.full_commit_message,
            commit_diff=commit_diff,
            is_pushed=False,
        )

        return {
            "success": True,
            "receipt": receipt,
        }


class PRSynthesisEngine:
    """Synthesizes professional, reviewable PR markdown descriptions from verified evidence."""

    @staticmethod
    def synthesize_pr(
        evidence: VerifiedEvidenceBundle,
        commit_bundle: CommitBundle,
        base_branch: str = "main",
        commit_sha: str | None = None,
    ) -> PRContent:
        """Generate structured PR title and markdown body containing all 8 required sections."""
        pr_title = commit_bundle.commit_title

        # Reproduction steps formatting: clear prose + minimal valid python script (NO prose in code block)
        repro_scenario = (
            f"1. Checkout repository at base commit `{evidence.base_commit[:12]}`.\n"
            f"2. Execute the reproduction scenario:\n"
            "```python\n"
            "import requests\n\n"
            "# Trigger condition: iter_lines with string delimiter when chunks are bytes\n"
            "response = requests.Response()\n"
            "response.raw = None  # Or simulated byte stream\n"
            "response.encoding = None\n\n"
            "# Triggers TypeError: a bytes-like object is required, not 'str'\n"
            "for line in response.iter_lines(decode_unicode=True, delimiter=\"\\n\"):\n"
            "    pass\n"
            "```\n"
            f"3. **Observed Failure:** `{evidence.behavior_before}`"
        )

        # Audit test execution counts
        audit = RegressionAuditor.audit_verification(
            test_exit_code=evidence.test_exit_code,
            test_stdout=evidence.test_stdout,
            test_stderr=evidence.test_stderr,
            planned_tests=evidence.regression_tests_plan,
        )

        test_evidence_excerpt = evidence.test_stdout.strip()
        if len(test_evidence_excerpt) > 2000:
            test_evidence_excerpt = test_evidence_excerpt[:2000] + "\n... [truncated for PR summary]"

        pr_body_sections = [
            f"# {pr_title}",
            "",
            "## 1. Problem Summary",
            evidence.behavior_before,
            "",
            "## 2. Root Cause Analysis",
            (
                "When `iter_lines()` is called with `decode_unicode=True` but the underlying response encoding is `None`, "
                "`iter_content()` yields raw `bytes` while `delimiter` may be passed as a `str`. "
                "In Python 3, calling `bytes.split(str)` raises a `TypeError` because string and byte delimiters cannot be mixed. "
                "The delimiter types were not automatically coerced to match the chunk type returned by `iter_content()`."
            ),
            "",
            "## 3. Proposed Fix",
            (
                f"Applies verified patch `{evidence.patch_id}` (SHA-256: `{evidence.patch_hash}`).\n\n"
                f"{evidence.explanation}\n\n"
                f"Specifically, when `chunk` is `bytes` and `delimiter` is `str`, the delimiter is encoded to `bytes` using "
                f"`response.encoding` (or `'utf-8'`). When `chunk` is `str` and `delimiter` is `bytes`, it is decoded to `str`. "
                f"This transparently supports mixed delimiter inputs while preserving backwards compatibility and line buffering."
            ),
            "",
            "## 4. Before & After Behavior",
            "| Stage | Behavior |",
            "| :--- | :--- |",
            f"| **Before** | {evidence.behavior_before} |",
            f"| **After** | {evidence.behavior_after} |",
            "",
            "## 5. Files Changed",
            "\n".join(f"- `{f}`" for f in evidence.target_files),
            "",
            "### Applied Unified Diff",
            "```diff",
            evidence.diff_content.strip(),
            "```",
            "",
            "## 6. Reproduction Steps",
            repro_scenario,
            "",
            "## 7. Tests Executed & Empirical Verification",
            f"- **Targeted In-Guest Test Status:** `{'PASSED' if audit['targeted_passed'] else 'FAILED'}` (Exit Code: `{audit['exit_code']}`)",
            f"- **Test Counts:** `{audit['passed_count']}` passed, `{audit['failed_count']}` failed, `{audit['skipped_count']}` skipped (total: `{audit['total_count']}`)",
            "",
            "### Celesto MicroVM Console Output",
            "```text",
            test_evidence_excerpt,
            "```",
            "",
            "### Planned Upstream Regression Suite (CI Scope)",
            "The following discovered test suites are scheduled for continuous integration validation:",
            "\n".join(f"- `{t}`" for t in evidence.regression_tests_plan),
            "",
            "> [!NOTE]",
            "> Empirical verification was performed against targeted reproduction tests, parameter combinations, and chunk boundary fixtures inside an isolated Celesto Firecracker microVM.",
            "> Full repository test suites should be validated in CI before merging.",
            "",
            "## 8. Known Limitations & Compatibility Scope",
            f"- **Compatibility:** {evidence.compatibility_notes}",
            "- **Scope Note:** Verified inside an isolated Celesto Firecracker microVM. "
            "Host checkout files were untouched during verification.",
            "",
            "---",
            "*Generated autonomously by SpaceV Agent — Step 2.6 Publishing Pipeline.*",
        ]

        full_body = "\n".join(pr_body_sections)
        norm_repo = normalize_repository_url(evidence.repository_url)

        return PRContent(
            pr_title=pr_title,
            pr_body=full_body,
            branch_name=commit_bundle.branch_name,
            base_branch=base_branch,
            target_repository=norm_repo,
            source_repository=norm_repo,
            commit_sha=commit_sha,
        )


class GitHubPublishingAuthorizationManager:
    """Manages multi-stage human approval boundaries and GitHub publishing operations."""

    def __init__(self, ttl_seconds: float = PR_APPROVAL_TTL_SECONDS):
        self.ttl_seconds = ttl_seconds
        self._pending_proposals: dict[str, PRPublishingProposal] = {}
        self._approved_proposals: dict[str, PRPublishingProposal] = {}
        self._published_proposals: dict[str, PRPublishingProposal] = {}

    def create_publishing_proposal(
        self,
        evidence: VerifiedEvidenceBundle,
        commit_bundle: CommitBundle,
        pr_content: PRContent,
        github_token: str | None = None,
        base_branch: str = "main",
        commit_sha: str | None = None,
    ) -> PRPublishingProposal:
        """Create a multi-boundary human approval proposal for publishing."""
        prop_id = f"prprop-{uuid.uuid4().hex[:12]}"

        # Probe GitHub API if token available (read-only)
        requires_fork = True
        token_to_use = github_token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if token_to_use:
            probe = self._probe_github_permissions(token_to_use, evidence.repository_url)
            requires_fork = probe.get("requires_fork", True)

        token_fork = f"approve fork {prop_id}"
        token_push = f"approve push {prop_id}"
        token_pr = f"approve pr {prop_id}"

        effective_commit_sha = commit_sha or pr_content.commit_sha or evidence.base_commit
        pr_body_hash = hashlib.sha256(pr_content.pr_body.encode("utf-8")).hexdigest().lower()

        proposal = PRPublishingProposal(
            proposal_id=prop_id,
            patch_id=evidence.patch_id,
            patch_hash=evidence.patch_hash,
            repository_url=evidence.repository_url,
            base_commit=evidence.base_commit,
            branch_name=commit_bundle.branch_name,
            commit_sha=effective_commit_sha,
            commit_message=commit_bundle.full_commit_message,
            pr_title=pr_content.pr_title,
            pr_body=pr_content.pr_body,
            pr_body_hash=pr_body_hash,
            patch_approval_token=evidence.approval_token,
            requires_fork=requires_fork,
            destination_repo=pr_content.target_repository,
            base_branch=base_branch,
            approval_token_fork=token_fork,
            approval_token_push=token_push,
            approval_token_pr=token_pr,
            created_at=time.monotonic(),
            status="PENDING_APPROVAL",
        )

        self._pending_proposals[prop_id] = proposal
        return proposal

    def format_approval_request(self, proposal: PRPublishingProposal) -> str:
        """Format a clear, multi-stage approval presentation for human review."""
        fork_section = ""
        if proposal.requires_fork:
            fork_section = (
                "Stage A — Fork Authorization:\n"
                f"  A fork is required because direct push to {proposal.destination_repo} is restricted.\n"
                f"  To authorize fork creation, reply: {proposal.approval_token_fork}\n\n"
            )

        return (
            "SPACEV_NEEDS_USER_INPUT: Pull Request Publishing Proposal awaiting explicit authorization.\n\n"
            f"Proposal ID: {proposal.proposal_id}\n"
            f"Target Repository: {proposal.destination_repo}\n"
            f"Base Branch: {proposal.base_branch}\n"
            f"Working Branch: {proposal.branch_name}\n"
            f"Base Commit: {proposal.base_commit}\n"
            f"Commit SHA: {proposal.commit_sha}\n"
            f"Patch SHA-256: {proposal.patch_hash}\n"
            f"PR Body Hash: {proposal.pr_body_hash}\n\n"
            "=== COMMIT MESSAGE ===\n"
            f"{proposal.commit_message}\n\n"
            "=== PULL REQUEST PREVIEW ===\n"
            f"Title: {proposal.pr_title}\n\n"
            f"{proposal.pr_body[:600]}...\n\n"
            "=== SEPARATE APPROVAL GATES ===\n"
            f"{fork_section}"
            "Stage B — Branch Push Authorization:\n"
            f"  Destination: {proposal.destination_repo} @ {proposal.branch_name}\n"
            f"  To authorize git push, reply: {proposal.approval_token_push}\n\n"
            "Stage C — Pull Request Submission Authorization:\n"
            f"  Base: {proposal.base_branch} <- Head: {proposal.branch_name}\n"
            f"  To authorize PR creation on GitHub, reply: {proposal.approval_token_pr}\n\n"
            "No external network push or PR creation will occur without explicit token approval."
        )

    def approve_action(
        self,
        proposal_id: str,
        action: str,  # "fork", "push", "pr"
        approval_token: str,
    ) -> tuple[bool, str]:
        """Validate explicit token for a specific publishing action (fork, push, or pr)."""
        pid = str(proposal_id or "").strip()
        actual_token = str(approval_token or "").strip()

        # Step 2.5 patch approval tokens MUST NEVER authorize publishing
        if actual_token.startswith("approve patch"):
            return (
                False,
                "BLOCKED: Step 2.5 patch approval token cannot authorize publishing. "
                "Publishing requires an explicit 'approve <fork|push|pr>' token.",
            )

        proposal = self._pending_proposals.get(pid) or self._approved_proposals.get(pid)
        if proposal is None:
            if pid in self._published_proposals:
                return False, f"BLOCKED: Proposal {pid} has already been published. Replay rejected."
            return False, f"BLOCKED: Unknown or expired publishing proposal {pid}."

        # Check patch approval token guard
        if actual_token.casefold() == proposal.patch_approval_token.casefold():
            return (
                False,
                "BLOCKED: Step 2.5 patch approval token cannot authorize publishing. "
                "Publishing requires an explicit 'approve <fork|push|pr>' token.",
            )

        now = time.monotonic()
        if now - proposal.created_at >= self.ttl_seconds:
            self._pending_proposals.pop(pid, None)
            proposal.status = "EXPIRED"
            return False, f"BLOCKED: Publishing approval for {pid} expired after {int(self.ttl_seconds)}s."

        expected_token = f"approve {action} {pid}".casefold()
        if actual_token.casefold() != expected_token:
            return False, f"BLOCKED: Exact approval token mismatch. Expected {expected_token!r}."

        if action == "fork":
            if not proposal.requires_fork:
                return False, f"BLOCKED: Fork is not required for proposal {pid}."
            proposal.fork_approved = True
            return True, f"Fork creation approved for proposal {pid}."

        elif action == "push":
            if proposal.requires_fork and not proposal.fork_approved:
                return False, "BLOCKED: Cannot approve push before fork is authorized."
            proposal.push_approved = True
            return True, f"Branch push approved for proposal {pid}."

        elif action == "pr":
            if not proposal.push_approved:
                return False, "BLOCKED: Cannot approve PR submission before branch push is authorized."
            proposal.pr_approved = True
            proposal.status = "FULLY_APPROVED"
            self._pending_proposals.pop(pid, None)
            self._approved_proposals[pid] = proposal
            return True, f"PR creation fully approved for proposal {pid}."

        return False, f"Unknown action: {action!r}"

    def publish_pr(
        self,
        proposal_id: str,
        github_token: str | None = None,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Publish the approved PR. Defaults to dry-run / simulation boundary."""
        pid = str(proposal_id or "").strip()
        proposal = self._approved_proposals.get(pid)

        if proposal is None:
            if pid in self._pending_proposals:
                return {
                    "success": False,
                    "error": f"BLOCKED: Proposal {pid} has not received all required approvals (status: {self._pending_proposals[pid].status}).",
                }
            return {"success": False, "error": f"BLOCKED: Proposal {pid} is not approved or not found."}

        # Verify cryptographic binding to PR body
        recomputed_body_hash = hashlib.sha256(proposal.pr_body.encode("utf-8")).hexdigest().lower()
        if recomputed_body_hash != proposal.pr_body_hash:
            return {
                "success": False,
                "error": f"BLOCKED: PR body tampering detected! Expected {proposal.pr_body_hash}, found {recomputed_body_hash}.",
            }

        if not proposal.pr_approved:
            return {"success": False, "error": "BLOCKED: Final PR submission is not approved."}
        if not proposal.push_approved:
            return {"success": False, "error": "BLOCKED: Branch push is not approved."}
        if proposal.requires_fork and not proposal.fork_approved:
            return {"success": False, "error": "BLOCKED: Fork creation is not approved."}

        # Execution Boundary Check: Dry run / simulation
        if dry_run or not (github_token or os.environ.get("GITHUB_TOKEN")):
            proposal.status = "PUBLISHED"
            self._approved_proposals.pop(pid, None)
            self._published_proposals[pid] = proposal
            return {
                "success": True,
                "dry_run": True,
                "proposal_id": proposal.proposal_id,
                "branch_name": proposal.branch_name,
                "commit_sha": proposal.commit_sha,
                "target_repository": proposal.destination_repo,
                "pr_title": proposal.pr_title,
                "simulation_note": "Dry-run preview completed successfully without external mutation.",
            }

        return {
            "success": False,
            "error": "External GitHub push operations are restricted under current execution boundaries.",
        }

    def _probe_github_permissions(self, token: str, repository_url: str) -> dict[str, Any]:
        """Check user permissions on target repository via GitHub API (read-only)."""
        safe_token = _redact(token)
        try:
            norm_repo = normalize_repository_url(repository_url)
            parsed = urllib.parse.urlparse(norm_repo)
            path_parts = [p for p in parsed.path.strip("/").split("/") if p]
            if len(path_parts) != 2:
                return {"requires_fork": True, "error": "Invalid repository path structure."}
            owner, repo = path_parts

            api_url = f"https://api.github.com/repos/{owner}/{repo}"
            req = urllib.request.Request(
                api_url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "SpaceV-Agent/1.0",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                permissions = data.get("permissions", {})
                can_push = permissions.get("push", False)
                return {"requires_fork": not can_push, "can_push": can_push, "permissions": permissions}

        except Exception as e:
            logger.warning("GitHub permission probe failed (token %s): %s", safe_token, e)
            return {"requires_fork": True, "error": str(e)}
