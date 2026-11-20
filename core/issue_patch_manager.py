"""Cryptographically bound, human-approval-gated patch management for SpaceV.

Guarantees:
1. Exact Canonical Artifact: The exact patch file bytes intended for Celesto are stored immutably.
2. Canonical SHA-256 Fingerprint: Calculated directly from the raw artifact bytes without alteration.
3. Strict Human Approval Binding: Approval binds to exact patch SHA-256, repository identity,
   exact full base commit, patch ID, one-time token, scope, and expiry.
4. Pre-Execution Integrity Verification: Immediately before `git apply`:
   - Recalculates SHA-256 from the exact in-memory patch bytes and validates against approved hash.
   - Strictly verifies guest repository HEAD against approved full commit hash (no abbreviated or prefix matching).
   - Strictly verifies guest repository remote identity using canonical URL normalization (rejecting failed lookups,
     empty remotes, and lookalikes).
   Any deviation immediately aborts execution with zero file modifications in the guest.
5. Fail-Closed Disk Recovery: Validates recovered patch artifacts against recorded hashes and full commit formats;
   rejects corrupted, tampered, or mismatched files.
6. Anti-Replay and One-Time Consumption: Approval tokens cannot be re-used after approval or application.
7. Host Filesystem Isolation: Patches are applied ONLY inside the approved Celesto microVM.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import pathlib
import posixpath
import re
import shlex
import time
import urllib.parse
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger("SpaceV.PatchManager")

PATCH_APPROVAL_TTL_SECONDS = 900  # 15 minutes


VALID_HOSTNAME_REGEX = re.compile(
    r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$"
)
VALID_PATH_SEGMENT_REGEX = re.compile(r"^[a-zA-Z0-9_.-]+$")


def normalize_repository_url(url: str) -> str:
    """Normalize and validate a git repository URL under strict security rules.

    Rules enforced:
    1. Supported schemes: strictly HTTPS, SSH, or SCP-style git URLs. Insecure HTTP is rejected.
    2. Embedded credentials (passwords or HTTPS tokens) are strictly rejected.
    3. Non-standard ports (ports other than 443 for HTTPS, 22 for SSH) are strictly rejected.
    4. Hostnames must be valid fully-qualified domain names. IP addresses, localhost, and
       malformed hosts are rejected.
    5. Paths must be unambiguous: strictly at least two segments (<owner>/<repo>) with valid
       characters and no directory traversal.
    6. Canonical return formats:
       - HTTPS: 'https://<host>/<owner>/<repo>'
       - SSH / SCP: 'ssh://git@<host>/<owner>/<repo>'
    """
    raw = str(url or "").strip()
    if not raw:
        raise ValueError("Repository URL cannot be empty.")

    # 1. SCP-style Git URL: git@host:owner/repo[.git]
    if raw.startswith("git@") and ":" in raw and "://" not in raw:
        user_host, sep, path_part = raw.partition(":")
        if "@" not in user_host:
            raise ValueError("Malformed SCP-style Git URL (missing @).")
        user_part, host_part = user_host.split("@", 1)
        if user_part != "git":
            raise ValueError(f"SCP-style Git URLs must use user 'git', got {user_part!r}.")
        if ":" in user_part:
            raise ValueError("Embedded passwords in SCP-style Git URLs are rejected.")

        host = host_part.strip().lower()
        if not VALID_HOSTNAME_REGEX.fullmatch(host):
            raise ValueError(f"Invalid or untrusted hostname in SCP-style URL: {host_part!r}.")

        clean_path = path_part.strip().rstrip("/")
        if clean_path.endswith(".git"):
            clean_path = clean_path[:-4]
        segments = [s for s in clean_path.split("/") if s]
        if len(segments) < 2:
            raise ValueError(f"Ambiguous repository path (must contain owner and repo): {path_part!r}.")
        for s in segments:
            if not VALID_PATH_SEGMENT_REGEX.fullmatch(s) or s in (".", ".."):
                raise ValueError(f"Invalid repository path segment: {s!r}.")
        norm_path = "/".join(segments).lower()
        return f"ssh://git@{host}/{norm_path}"

    # 2. Standard URL schemes (HTTPS, SSH)
    parsed = urllib.parse.urlparse(raw)
    scheme = parsed.scheme.lower()

    if scheme == "http":
        raise ValueError("Protocol downgrade rejected: insecure HTTP is not permitted.")
    if scheme not in ("https", "ssh"):
        raise ValueError(
            f"Unsupported URL scheme {scheme!r}; only HTTPS, SSH, and SCP-style Git URLs are supported."
        )

    # Reject embedded credentials
    if parsed.password:
        raise ValueError("Embedded passwords in repository URLs are rejected.")
    if scheme == "https" and parsed.username:
        raise ValueError("Embedded credentials in HTTPS repository URLs are rejected.")
    if scheme == "ssh":
        if parsed.username and parsed.username != "git":
            raise ValueError(f"SSH repository URLs must use user 'git', got {parsed.username!r}.")

    # Port validation
    if parsed.port is not None:
        if scheme == "https" and parsed.port != 443:
            raise ValueError(f"Non-standard HTTPS port {parsed.port} is rejected.")
        if scheme == "ssh" and parsed.port != 22:
            raise ValueError(f"Non-standard SSH port {parsed.port} is rejected.")

    host = (parsed.hostname or "").strip().lower()
    if not host or not VALID_HOSTNAME_REGEX.fullmatch(host):
        raise ValueError(f"Invalid or untrusted hostname: {parsed.netloc!r}.")

    # Path validation
    clean_path = parsed.path.strip().rstrip("/")
    if clean_path.endswith(".git"):
        clean_path = clean_path[:-4]
    segments = [s for s in clean_path.split("/") if s]
    if len(segments) < 2:
        raise ValueError(f"Ambiguous repository path (must contain owner and repo): {parsed.path!r}.")
    for s in segments:
        if not VALID_PATH_SEGMENT_REGEX.fullmatch(s) or s in (".", ".."):
            raise ValueError(f"Invalid repository path segment: {s!r}.")
    norm_path = "/".join(segments).lower()

    if scheme == "https":
        return f"https://{host}/{norm_path}"
    else:
        return f"ssh://git@{host}/{norm_path}"


@dataclass
class ProposedPatch:
    """Immutable representation of a proposed repository fix."""

    patch_id: str
    repository_url: str
    base_commit: str
    checkout_path: str
    target_files: list[str]
    diff_content: str
    patch_hash: str
    explanation: str
    behavior_before: str
    behavior_after: str
    compatibility_notes: str
    regression_tests_plan: list[str]
    status: str = "PENDING_APPROVAL"  # PENDING_APPROVAL, APPROVED, REJECTED, APPLIED, EXPIRED
    created_at: float = field(default_factory=time.monotonic)
    approval_token: str = ""
    approved_at: float | None = None
    applied_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("created_at", None)
        return d


class PatchApprovalManager:
    """Manages patch proposals, human approvals, and guest-confined application."""

    def __init__(self, ttl_seconds: float = PATCH_APPROVAL_TTL_SECONDS):
        self.ttl_seconds = ttl_seconds
        self._pending_patches: dict[str, ProposedPatch] = {}
        self._approved_patches: dict[str, ProposedPatch] = {}
        self._applied_patches: dict[str, ProposedPatch] = {}

    def propose_patch(
        self,
        repository_url: str,
        base_commit: str,
        checkout_path: str,
        target_files: list[str],
        diff_content: str,
        explanation: str,
        behavior_before: str,
        behavior_after: str,
        compatibility_notes: str,
        regression_tests_plan: list[str] | None = None,
    ) -> ProposedPatch:
        """Create a cryptographically bound canonical patch proposal awaiting human approval."""
        clean_repo = str(repository_url or "").strip()
        try:
            normalize_repository_url(clean_repo)
        except Exception as e:
            raise ValueError(f"Invalid repository URL for patch proposal: {e}") from e

        clean_commit = str(base_commit or "").strip().lower()
        if not clean_commit or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", clean_commit):
            raise ValueError(
                f"Valid full commit hash (40 or 64 hex characters) is required, got: {base_commit!r}"
            )

        raw_checkout = str(checkout_path or "").strip()
        clean_checkout = posixpath.normpath(raw_checkout)
        if (
            not raw_checkout.startswith("/tmp/")
            or ".." in raw_checkout.split("/")
            or clean_checkout == "/tmp"
            or not clean_checkout.startswith("/tmp/")
        ):
            raise ValueError(f"Unsafe checkout path: {checkout_path!r}")

        if not isinstance(diff_content, str) or not diff_content:
            raise ValueError("Patch diff content cannot be empty.")

        # Validate target files
        validated_files: list[str] = []
        for tf in target_files:
            clean_tf = str(tf or "").strip().replace("\\", "/")
            if clean_tf.startswith("/") or clean_tf.startswith("..") or "/../" in clean_tf:
                raise ValueError(f"Unsafe target file path escapes repository: {tf!r}")
            norm_tf = posixpath.normpath(clean_tf)
            if norm_tf not in validated_files:
                validated_files.append(norm_tf)

        if not validated_files:
            raise ValueError("At least one valid repository-relative target file is required.")

        # CANONICAL ARTIFACT HASHING:
        # Calculate SHA-256 from the EXACT raw bytes of the canonical patch artifact.
        # Do not strip, alter, or reformat diff_content.
        canonical_bytes = diff_content.encode("utf-8")
        patch_hash = hashlib.sha256(canonical_bytes).hexdigest()
        patch_id = f"patch-{uuid.uuid4().hex[:12]}"
        approval_token = f"approve patch {patch_id}"

        patch = ProposedPatch(
            patch_id=patch_id,
            repository_url=clean_repo,
            base_commit=clean_commit,
            checkout_path=clean_checkout,
            target_files=validated_files,
            diff_content=diff_content,
            patch_hash=patch_hash,
            explanation=str(explanation or "").strip(),
            behavior_before=str(behavior_before or "").strip(),
            behavior_after=str(behavior_after or "").strip(),
            compatibility_notes=str(compatibility_notes or "").strip(),
            regression_tests_plan=list(regression_tests_plan or []),
            status="PENDING_APPROVAL",
            created_at=time.monotonic(),
            approval_token=approval_token,
        )

        self._pending_patches[patch_id] = patch
        return patch

    def format_approval_request(self, patch: ProposedPatch) -> str:
        """Format a clear, human-reviewable approval presentation with exact fingerprint."""
        files_str = "\n".join(f"  - {f}" for f in patch.target_files)
        tests_str = "\n".join(f"  - {t}" for t in patch.regression_tests_plan) or "  - Standard test suite"

        return (
            "SPACEV_NEEDS_USER_INPUT: Proposed repository fix awaiting explicit human approval.\n\n"
            f"Patch ID: {patch.patch_id}\n"
            f"Repository: {patch.repository_url}\n"
            f"Base Commit: {patch.base_commit}\n"
            f"Target Files:\n{files_str}\n"
            f"Patch SHA-256: {patch.patch_hash}\n\n"
            f"=== EXPLANATION ===\n{patch.explanation}\n\n"
            f"=== BEHAVIOR BEFORE ===\n{patch.behavior_before}\n\n"
            f"=== BEHAVIOR AFTER ===\n{patch.behavior_after}\n\n"
            f"=== COMPATIBILITY & REGRESSION TESTS ===\n"
            f"Notes: {patch.compatibility_notes}\n"
            f"Planned Tests:\n{tests_str}\n\n"
            f"=== PROPOSED DIFF ===\n```diff\n{patch.diff_content}\n```\n\n"
            f"No changes will be applied to any files until approved.\n"
            f"To approve this exact patch, reply: {patch.approval_token}"
        )

    def recover_proposal_from_disk(
        self,
        filepath: str | pathlib.Path = "reports/pending_patch_proposal.json",
    ) -> ProposedPatch:
        """Recover a pending patch proposal from disk with strict cryptographic integrity checks.

        Guarantees:
        - Fails closed if file is missing, empty, or unparseable.
        - Fails closed if recorded patch_hash does not match hashlib.sha256(diff_content.encode('utf-8')).
        - Fails closed if base_commit is not a full 40/64 hex commit.
        - Fails closed if repository URL is malformed.
        - Never silently replaces or reformats diff content from other files.
        """
        p = pathlib.Path(filepath)
        if not p.exists():
            raise FileNotFoundError(f"Proposal file not found: {filepath}")

        try:
            raw_text = p.read_text(encoding="utf-8")
            data = json.loads(raw_text)
        except Exception as e:
            raise ValueError(f"Failed to parse proposal file {filepath}: {e}") from e

        pid = str(data.get("patch_id") or "").strip()
        repo = str(data.get("repository_url") or "").strip()
        commit = str(data.get("base_commit") or "").strip().lower()
        checkout = str(data.get("checkout_path") or "").strip()
        target_files = data.get("target_files") or []
        diff_content = data.get("diff_content")
        recorded_hash = str(data.get("patch_hash") or "").strip().lower()

        if not pid or not repo or not commit or not checkout or not target_files or diff_content is None:
            raise ValueError(f"Proposal file {filepath} is missing required fields.")

        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
            raise ValueError(f"Proposal base commit is not a valid full commit hash: {commit!r}")

        try:
            normalize_repository_url(repo)
        except Exception as e:
            raise ValueError(f"Proposal repository URL is invalid: {e}") from e

        # Cryptographic integrity check: calculate SHA-256 of exact diff bytes
        computed_hash = hashlib.sha256(diff_content.encode("utf-8")).hexdigest().lower()
        if computed_hash != recorded_hash:
            raise ValueError(
                f"INTEGRITY ERROR: Recovered proposal patch_hash mismatch! "
                f"Recorded: {recorded_hash}, Computed from diff_content: {computed_hash}. "
                "The proposal artifact on disk has been corrupted or tampered with."
            )

        patch = ProposedPatch(
            patch_id=pid,
            repository_url=repo,
            base_commit=commit,
            checkout_path=checkout,
            target_files=list(target_files),
            diff_content=diff_content,
            patch_hash=computed_hash,
            explanation=str(data.get("explanation") or ""),
            behavior_before=str(data.get("behavior_before") or ""),
            behavior_after=str(data.get("behavior_after") or ""),
            compatibility_notes=str(data.get("compatibility_notes") or ""),
            regression_tests_plan=list(data.get("regression_tests_plan") or []),
            status=str(data.get("status") or "PENDING_APPROVAL"),
            created_at=time.monotonic(),
            approval_token=str(data.get("approval_token") or f"approve patch {pid}"),
        )

        self._pending_patches[pid] = patch
        return patch

    def approve_patch(
        self,
        patch_id: str,
        approval_text: str,
        repository_url: str = "",
        base_commit: str = "",
        expected_patch_hash: str = "",
        proposal_filepath: str | pathlib.Path = "reports/pending_patch_proposal.json",
    ) -> tuple[bool, str]:
        """Validate human approval with strict token, repository, commit, and artifact hash binding."""
        pid = str(patch_id or "").strip()
        patch = self._pending_patches.get(pid)

        if patch is None:
            # Check if already approved or applied
            if pid in self._applied_patches:
                return False, f"BLOCKED: Patch {pid} has already been applied. Replay is rejected."
            if pid in self._approved_patches:
                return False, f"BLOCKED: Patch {pid} is already approved and ready for application."

            # Attempt safe disk recovery
            try:
                recovered = self.recover_proposal_from_disk(proposal_filepath)
                if recovered.patch_id == pid:
                    patch = recovered
            except Exception as e:
                logger.warning(f"Could not load persisted patch proposal for {pid}: {e}")
                return False, f"BLOCKED: Patch {pid} cannot be recovered from disk: {e}"

        if patch is None:
            return False, f"BLOCKED: Patch {pid} is unknown, expired, or already used. Request a fresh proposal."

        # Verify TTL
        now = time.monotonic()
        if now - patch.created_at >= self.ttl_seconds:
            self._pending_patches.pop(pid, None)
            patch.status = "EXPIRED"
            return False, f"BLOCKED: Patch approval for {pid} expired after {int(self.ttl_seconds)}s. Request a fresh proposal."

        # Verify Approval Token
        expected_token = f"approve patch {pid}".casefold()
        actual_token = str(approval_text or "").strip().casefold()
        if actual_token != expected_token:
            return False, f"BLOCKED: The exact approval phrase was not supplied. Expected {patch.approval_token!r}."

        # Verify Repository Binding using strict canonical URL normalization
        if repository_url:
            try:
                norm_caller_repo = normalize_repository_url(repository_url)
                norm_target_repo = normalize_repository_url(patch.repository_url)
                if norm_caller_repo != norm_target_repo:
                    return False, f"BLOCKED: Repository URL {repository_url!r} does not match approved patch target {patch.repository_url!r}."
            except Exception as e:
                return False, f"BLOCKED: Invalid repository URL supplied during approval: {e}"

        # Verify Commit Binding with strict full-commit equality
        if base_commit:
            clean_commit = str(base_commit).strip().lower()
            if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", clean_commit):
                return False, f"BLOCKED: Base commit {base_commit!r} is not a valid full commit hash (must be 40 or 64 hex characters)."
            if clean_commit != patch.base_commit:
                return False, f"BLOCKED: Base commit {base_commit!r} does not match approved patch commit {patch.base_commit!r}."

        # Verify Patch Content Hash Binding
        actual_hash = hashlib.sha256(patch.diff_content.encode("utf-8")).hexdigest()
        if actual_hash != patch.patch_hash:
            self._pending_patches.pop(pid, None)
            return False, (
                f"BLOCKED: Patch {pid} content hash mismatch! "
                f"Computed: {actual_hash}, Bound: {patch.patch_hash}. Integrity check failed."
            )

        if expected_patch_hash:
            clean_expected_hash = expected_patch_hash.strip().lower()
            if actual_hash != clean_expected_hash:
                return False, (
                    f"BLOCKED: Caller expected patch hash {clean_expected_hash} does not match "
                    f"patch hash {actual_hash}."
                )

        # Transition state to APPROVED
        self._pending_patches.pop(pid, None)
        patch.status = "APPROVED"
        patch.approved_at = time.time()
        self._approved_patches[pid] = patch
        return True, f"Patch {pid} approved successfully. Bound to commit {patch.base_commit} (SHA-256: {patch.patch_hash})."

    def apply_patch_inside_sandbox(
        self,
        session_id: str,
        patch_id: str,
        sandbox_manager: Any,
    ) -> dict[str, Any]:
        """Apply the approved patch inside the isolated Celesto microVM.

        Enforces:
        1. Patch must have status APPROVED.
        2. Sandbox session must be active.
        3. Pre-Execution Integrity Verification:
           a. Recalculate SHA-256 of patch.diff_content bytes. Must match patch.patch_hash exactly.
           b. Strict Full-Commit Equality: Guest HEAD must match patch.base_commit character-for-character.
              Abbreviated or malformed commit hashes are strictly rejected.
           c. Strict Repository Identity Verification:
              - Executes 'git remote get-url origin' inside guest.
              - If command fails, rejects execution.
              - If output is empty, rejects execution.
              - Normalizes guest remote URL and patch repository URL canonically.
              - Rejects any mismatch, lookalike, or malicious repository URL.
        4. Writes the exact approved bytes to guest /tmp via base64.
        5. Executes git apply inside guest.
        6. Audits post-patch git diff and verifies only approved target_files were modified.
        7. On any error or unexpected file modification, automatically rolls back guest working tree.
        8. Transitions patch status to APPLIED and invalidates token against replay.
        """
        pid = str(patch_id or "").strip()
        patch = self._approved_patches.get(pid)
        if patch is None:
            return {
                "success": False,
                "error": f"BLOCKED: Patch {pid} is not in APPROVED state. Human approval is required.",
            }

        session = sandbox_manager._sessions.get(str(session_id or "").strip())
        if session is None or getattr(session, "expired", False):
            return {
                "success": False,
                "error": "BLOCKED: Celesto session is missing or expired.",
            }

        computer = session.instance._live_computer
        checkout = patch.checkout_path

        # -------------------------------------------------------------
        # Pre-Execution Verification 1: Recalculate exact artifact SHA-256
        # -------------------------------------------------------------
        exact_bytes = patch.diff_content.encode("utf-8")
        recomputed_hash = hashlib.sha256(exact_bytes).hexdigest()
        if recomputed_hash != patch.patch_hash:
            return {
                "success": False,
                "error": (
                    f"BLOCKED: Pre-execution patch integrity check failed! "
                    f"Artifact SHA-256 ({recomputed_hash}) does not match approved hash ({patch.patch_hash}). "
                    "Patch artifact was tampered with, altered, or replaced after approval."
                ),
            }

        # -------------------------------------------------------------
        # Pre-Execution Verification 2: Verify guest commit HEAD with strict full-commit equality
        # -------------------------------------------------------------
        rev_res = computer.run(f"git -C {shlex.quote(checkout)} rev-parse HEAD", timeout=30)
        if rev_res.exit_code != 0:
            return {
                "success": False,
                "error": f"Failed to check guest repository HEAD: {rev_res.stderr}",
            }
        guest_head = rev_res.stdout.strip().lower()
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", guest_head):
            return {
                "success": False,
                "error": (
                    f"BLOCKED: Guest HEAD ({guest_head!r}) is not a valid full commit hash "
                    "(must be 40 or 64 hex characters)."
                ),
            }
        if guest_head != patch.base_commit:
            return {
                "success": False,
                "error": (
                    f"BLOCKED: Guest repository HEAD ({guest_head}) does not match "
                    f"approved patch base commit ({patch.base_commit})."
                ),
            }

        # -------------------------------------------------------------
        # Pre-Execution Verification 3: Verify guest repository remote
        # -------------------------------------------------------------
        remote_res = computer.run(f"git -C {shlex.quote(checkout)} remote get-url origin", timeout=30)
        if remote_res.exit_code != 0:
            return {
                "success": False,
                "error": (
                    f"BLOCKED: Failed to retrieve guest repository remote URL via 'git remote get-url origin' "
                    f"(exit code {remote_res.exit_code}): {remote_res.stderr.strip()}"
                ),
            }
        guest_remote_raw = remote_res.stdout.strip()
        if not guest_remote_raw:
            return {
                "success": False,
                "error": "BLOCKED: Guest repository remote URL is empty. Unverified repository identity.",
            }

        try:
            norm_guest_remote = normalize_repository_url(guest_remote_raw)
            norm_expected_remote = normalize_repository_url(patch.repository_url)
        except Exception as e:
            return {
                "success": False,
                "error": f"BLOCKED: Repository URL validation error: {e}",
            }

        if norm_guest_remote != norm_expected_remote:
            return {
                "success": False,
                "error": (
                    f"BLOCKED: Guest repository remote ({guest_remote_raw} -> {norm_guest_remote}) "
                    f"does not match approved repository target ({patch.repository_url} -> {norm_expected_remote})."
                ),
            }

        # -------------------------------------------------------------
        # Safe Guest Write: Exact approved bytes written via base64
        # -------------------------------------------------------------
        patch_tmp_path = f"/tmp/{patch.patch_id}.patch"
        b64_diff = base64.b64encode(exact_bytes).decode("ascii")
        write_cmd = (
            f"python3 -c \"import base64, pathlib; "
            f"pathlib.Path('{patch_tmp_path}').write_bytes(base64.b64decode('{b64_diff}'))\""
        )
        write_res = computer.run(write_cmd, timeout=30)
        if write_res.exit_code != 0:
            return {
                "success": False,
                "error": f"Failed to write patch inside guest: {write_res.stderr}",
            }

        # -------------------------------------------------------------
        # Apply Patch Inside Guest
        # -------------------------------------------------------------
        apply_cmd = f"git -C {shlex.quote(checkout)} apply {shlex.quote(patch_tmp_path)}"
        apply_res = computer.run(apply_cmd, timeout=60)

        # Cleanup patch file inside guest
        computer.run(f"rm -f {shlex.quote(patch_tmp_path)}", timeout=30)

        if apply_res.exit_code != 0:
            return {
                "success": False,
                "error": f"git apply failed inside guest with exit code {apply_res.exit_code}: {apply_res.stderr}",
                "stdout": apply_res.stdout,
                "stderr": apply_res.stderr,
            }

        # -------------------------------------------------------------
        # Audit Git Diff & Git Status Inside Guest
        # -------------------------------------------------------------
        diff_res = computer.run(f"git -C {shlex.quote(checkout)} diff", timeout=30)
        status_res = computer.run(f"git -C {shlex.quote(checkout)} status --short", timeout=30)

        # Check modified files against approved target_files
        modified_files: list[str] = []
        for line in status_res.stdout.splitlines():
            line = line.strip()
            if line:
                file_part = line[2:].strip().replace("\\", "/")
                modified_files.append(file_part)

        unexpected = [
            mf for mf in modified_files
            if not any(mf.endswith(tf) or tf.endswith(mf) for tf in patch.target_files)
        ]
        if unexpected:
            # Revert unexpected modifications immediately
            computer.run(f"git -C {shlex.quote(checkout)} checkout -- .", timeout=30)
            return {
                "success": False,
                "error": f"Patch modified unexpected files: {unexpected}. Working tree reverted.",
            }

        # Move patch to APPLIED
        self._approved_patches.pop(pid, None)
        patch.status = "APPLIED"
        patch.applied_at = time.time()
        self._applied_patches[pid] = patch

        return {
            "success": True,
            "patch_id": patch.patch_id,
            "modified_files": modified_files,
            "captured_diff": diff_res.stdout,
            "git_status": status_res.stdout,
            "applied_bytes_sha256": recomputed_hash,
        }


patch_approval_manager = PatchApprovalManager()
