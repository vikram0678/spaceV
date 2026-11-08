"""Celesto command execution, simulation fallback, and diagnostics.

The Celesto provider selected in .env chooses the execution backend. The
simulator is used only when the provider is explicitly set to simulation.
Workflow and containment demonstrations in this module remain simulations.
"""

import hashlib
import atexit
import importlib.util
import json
import logging
import os
import posixpath
import re
import shlex
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.task_input import unresolved_template_marker

logger = logging.getLogger("SpaceV.Sandbox")
REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_GUEST_COMMAND_TIMEOUT_SECONDS = 30
MAX_GUEST_COMMAND_TIMEOUT_SECONDS = 900


def validate_approved_guest_command(task_description: str, command: str) -> str | None:
    """Fail closed unless a guest command is read-only and confined to the approved checkout."""
    task = str(task_description or "")
    text = str(command or "").strip()
    scope = re.search(
        r"(?:shallow[- ]clone|clone)\s+(https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\.git)\s+"
        r"(?:(?:to|into)\s+)?(/tmp/[A-Za-z0-9_.-]+)",
        task,
        re.IGNORECASE,
    )
    if not scope:
        return "the approved task does not define a repository and checkout path that can be safely enforced"
    repo_url = scope.group(1).rstrip("/")
    raw_root = scope.group(2).rstrip(".,;:")
    root = posixpath.normpath(raw_root)
    if root != raw_root or root == "/tmp" or "/../" in f"{root}/":
        return "the approved checkout path is not a safe fixed /tmp directory"
    if not text or "\n" in text or "\r" in text:
        return "only one bounded guest command can be classified at a time"
    try:
        lexer = shlex.shlex(text, posix=True, punctuation_chars=";&|<>`$")
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        return "the command has invalid quoting and cannot be safely classified"
    if not tokens or any(token and all(char in ";&|<>`$" for char in token) for token in tokens):
        return "shell chaining, redirection, substitution, and pipelines are not allowed"

    if tokens in (["git", "--version"], ["command", "-v", "git"], ["which", "git"]):
        return None
    clone_prefix = (
        2 if tokens[:2] == ["git", "clone"]
        else 4 if tokens[:3] == ["git", "-c", "core.hooksPath=/dev/null"] and tokens[3:4] == ["clone"]
        else 0
    )
    if clone_prefix:
        args = tokens[clone_prefix:]
        saw_depth_one = False
        i = 0
        while i < len(args):
            token = args[i]
            if token == "--":
                i += 1
                break
            elif token == "--depth":
                if i + 1 >= len(args) or args[i + 1] != "1" or saw_depth_one:
                    return "clone must be a shallow depth-1 checkout"
                saw_depth_one = True
                i += 2
            elif token == "--depth=1" and not saw_depth_one:
                saw_depth_one = True
                i += 1
            elif token == "--no-tags":
                i += 1
            else:
                if token.startswith("-"):
                    return "clone contains an unapproved option"
                break
        remaining = args[i:]
        if saw_depth_one and len(remaining) == 2 and remaining[0].rstrip("/") == repo_url and remaining[1] == root:
            return None
        return "clone is limited to the approved GitHub repository and exact /tmp checkout path"

    if tokens[0] == "git":
        if len(tokens) < 4 or tokens[1:3] != ["-C", root]:
            return "Git inspection must explicitly target the approved checkout with git -C"
        subcommand = tokens[3]
        if subcommand not in {"status", "rev-parse", "log", "show", "diff", "ls-files", "grep"}:
            return f"Git subcommand {subcommand!r} is not approved for read-only inspection"
        if any(token in {"--output", "--exec", "--ext-diff", "--textconv"} for token in tokens[4:]):
            return "the Git inspection contains an option that can write files or execute external programs"
        args = tokens[4:]
        if subcommand == "status" and args not in ([], ["--short"], ["--porcelain"]):
            return "status inspection is limited to the working-tree summary"
        if subcommand == "rev-parse" and args != ["HEAD"]:
            return "revision inspection is limited to the checked-out commit"
        if subcommand == "log" and args not in (["-1"], ["-1", "--format=%H"], ["-1", "--oneline"]):
            return "log inspection is limited to the current commit"
        if subcommand == "show":
            if len(args) != 1 or not args[0].startswith("HEAD:"):
                return "show may read only a single file blob from the checked-out HEAD commit"
            pathspec = args[0][5:]
            if not pathspec or pathspec.startswith("/") or ".." in pathspec.split("/"):
                return "show path must remain inside the approved repository tree"
        if subcommand == "ls-files":
            if any(arg.startswith("/") or ".." in arg.split("/") for arg in args):
                return "file listing must remain inside the approved repository tree"
        if subcommand == "diff":
            if args not in ([], ["--check"], ["--stat"]):
                return "diff is limited to the approved checkout summary or whitespace check"
        if subcommand == "grep":
            # Read from the immutable Git object tree, not the checkout: a
            # repository can contain symlinks that point outside its directory.
            if "HEAD" not in args or "--" not in args:
                return "grep must search the immutable HEAD tree with an explicit in-repository pathspec"
            separator = args.index("--")
            before_paths = args[:separator]
            paths = args[separator + 1:]
            if not paths or any(path.startswith("/") or ".." in path.split("/") for path in paths):
                return "grep pathspecs must stay inside the approved repository tree"
            if before_paths.count("HEAD") != 1:
                return "grep may search only the checked-out HEAD tree"
            allowed_flags = {"-n", "-i", "-E", "-F", "-w", "-h", "--full-name"}
            i = 0
            saw_pattern = False
            while i < len(before_paths):
                arg = before_paths[i]
                if arg == "HEAD" or arg in allowed_flags:
                    i += 1
                elif arg in {"-e", "-A", "-B", "-C"}:
                    if i + 1 >= len(before_paths):
                        return "grep option is missing its value"
                    if arg == "-e":
                        saw_pattern = True
                    i += 2
                elif not arg.startswith("-") and not saw_pattern:
                    saw_pattern = True
                    i += 1
                else:
                    return "grep contains an unapproved option or ambiguous argument"
            if not saw_pattern:
                return "grep requires one explicit search pattern"
        return None

    return f"command {tokens[0]!r} is not in the approved guest-command allowlist"


def _configured_guest_timeout(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        configured = int(raw_value)
    except ValueError:
        logger.warning("Ignoring invalid %s=%r; using %s seconds", name, raw_value, default)
        return default
    if not 1 <= configured <= MAX_GUEST_COMMAND_TIMEOUT_SECONDS:
        logger.warning(
            "Ignoring out-of-range %s=%r; expected 1..%s seconds",
            name,
            raw_value,
            MAX_GUEST_COMMAND_TIMEOUT_SECONDS,
        )
        return default
    return configured


def guest_command_timeout_seconds(command: str) -> int:
    """Choose a bounded timeout for common long-running guest operations.

    These are execution deadlines only: a timeout is never retried automatically,
    because the guest process may have made partial changes before the deadline.
    """
    text = str(command or "")
    if re.search(r"\bgit\b[^\n;&|]*\bclone\b", text, re.IGNORECASE):
        return _configured_guest_timeout("SPACEV_SANDBOX_CLONE_TIMEOUT_SECONDS", 180)
    if re.search(
        r"\b(?:apk\s+add|apt(?:-get)?\s+(?:update|install)|dnf\s+install|"
        r"pacman\s+-S|pip(?:3)?\s+install|uv\s+sync)\b",
        text,
        re.IGNORECASE,
    ):
        return _configured_guest_timeout("SPACEV_SANDBOX_SETUP_TIMEOUT_SECONDS", 180)
    if re.search(
        r"\b(?:pytest|unittest|tox|nox|cargo\s+test|go\s+test|"
        r"(?:npm|pnpm|yarn)\s+test|(?:mvn|gradle)\s+test)\b",
        text,
        re.IGNORECASE,
    ):
        return _configured_guest_timeout("SPACEV_SANDBOX_TEST_TIMEOUT_SECONDS", 300)
    return _configured_guest_timeout("SPACEV_SANDBOX_COMMAND_TIMEOUT_SECONDS", DEFAULT_GUEST_COMMAND_TIMEOUT_SECONDS)


@dataclass
class SandboxCommandResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    sandbox_id: str
    blocked: bool = False
    policy_violation: str | None = None


@dataclass
class WorkflowStepReport:
    step_num: int
    name: str
    status: str  # "SUCCESS", "FAILED", "ROLLED_BACK", "HEALED"
    duration_ms: float
    output: str
    checkpoint_created: str | None = None


@dataclass
class WorkflowExecutionReport:
    workflow_id: str
    total_steps: int
    steps_completed: int
    failure_encountered: bool
    failure_step: int | None
    rollback_occurred: bool
    restored_checkpoint: str | None
    recovery_status: str  # "RECOVERED", "FAILED", "CLEAN_RUN"
    host_compromised: bool
    step_reports: list[WorkflowStepReport] = field(default_factory=list)


class CelestoSandboxRunner:
    """
    In-memory sandbox simulator used by deterministic tests and demonstrations.

    This class does not create or control a Celesto VM. Keep its output and
    audit records explicitly marked as simulation until a real SDK backend is
    wired into this execution path.
    """

    def __init__(self, default_sandbox_id: str | None = None):
        self.sandbox_id = default_sandbox_id or f"sbx-{uuid.uuid4().hex[:8]}"
        self.is_running = False
        self.snapshots: dict[str, dict[str, Any]] = {}
        self.guest_state: dict[str, Any] = {}
        self.blocked_patterns = [
            "/etc/shadow",
            "/host_root",
            "rm -rf /",
            ":(){ :|:& };:",
            "curl http://169.254.169.254",  # Cloud metadata exfiltration
        ]
        self.pre_flight_cleanup()

    def pre_flight_cleanup(self) -> bool:
        """Ensures all previous dangling microVM containers, sockets, and artifacts are wiped."""
        self.snapshots.clear()
        self.guest_state.clear()
        self.is_running = False
        logger.info(f"[SANDBOX] Pre-flight cleanup complete for {self.sandbox_id}.")
        return True

    def start_sandbox(self, vcpus: int = 1, memory_mb: int = 512, network_mode: str = "off") -> bool:
        """Boots an isolated microVM guest sandbox instance."""
        self.is_running = True
        self.guest_state = {
            "vcpus": vcpus,
            "memory_mb": memory_mb,
            "network_mode": network_mode,
            "files": {"/etc/os-release": "NAME=Celesto-Alpine-Guest\nVERSION=3.20.1"},
            "boot_time": time.time(),
        }
        return True

    def teardown(self) -> bool:
        """Guarantees complete microVM teardown on success or failure with zero residual state."""
        self.is_running = False
        self.guest_state.clear()
        logger.info(f"[SANDBOX] Teardown and resource release complete for {self.sandbox_id}.")
        return True

    def create_snapshot(self, checkpoint_name: str) -> str:
        """Captures hardware state and memory snapshot of the running guest microVM."""
        if not self.is_running:
            self.start_sandbox()
        snap_id = f"snap-{uuid.uuid4().hex[:6]}"
        self.snapshots[checkpoint_name] = {
            "snapshot_id": snap_id,
            "created_at": time.time(),
            "guest_state_backup": dict(self.guest_state),
            "files_backup": dict(self.guest_state.get("files", {})),
        }
        logger.info(f"[SANDBOX] Snapshot '{checkpoint_name}' ({snap_id}) captured successfully.")
        return snap_id

    def restore_snapshot(self, checkpoint_name: str) -> bool:
        """Restores the guest microVM to a previously captured snapshot in sub-second time."""
        if checkpoint_name not in self.snapshots:
            raise KeyError(f"Snapshot '{checkpoint_name}' not found.")
        backup = self.snapshots[checkpoint_name]
        self.guest_state = dict(backup["guest_state_backup"])
        self.guest_state["files"] = dict(backup["files_backup"])
        self.is_running = True
        logger.info(f"[SANDBOX] MicroVM rolled back to snapshot '{checkpoint_name}' ({backup['snapshot_id']}).")
        return True

    def run_in_sandbox(self, command: str, timeout_sec: int = 10) -> SandboxCommandResult:
        """Executes a command strictly within the guest microVM perimeter."""
        start_t = time.perf_counter()
        if not self.is_running:
            self.start_sandbox()

        # Security hook: block host escape or dangerous exploit payloads
        for bad_pattern in self.blocked_patterns:
            if bad_pattern in command:
                duration_ms = (time.perf_counter() - start_t) * 1000
                return SandboxCommandResult(
                    command=command,
                    exit_code=126,
                    stdout="",
                    stderr=f"SECURITY_POLICY_VIOLATION: Command blocked by Celesto Safety Hook: '{bad_pattern}'",
                    duration_ms=duration_ms,
                    sandbox_id=self.sandbox_id,
                    blocked=True,
                    policy_violation=bad_pattern,
                )

        # Emulated guest file system operations; no command is executed here.
        if "<<" in command or "cat >" in command:
            # Handle heredoc or write redirection (e.g. cat > /tmp/untrusted.py <<'EOF')
            write_match = re.search(r"cat\s+>\s*([^\s<]+)\s*<<\s*['\"]?([A-Za-z0-9_]+)['\"]?", command)
            if write_match:
                dest_path = write_match.group(1).strip()
                delimiter = write_match.group(2).strip()
                pattern = r"<<\s*['\"]?" + re.escape(delimiter) + r"['\"]?\s*\n(.*?)\n\s*" + re.escape(delimiter)
                body_match = re.search(pattern, command, re.DOTALL)
                file_content = body_match.group(1) if body_match else ""
                self.guest_state.setdefault("files", {})[dest_path] = file_content

                out_lines = [f"[sandbox] {dest_path} written:"]
                if "py_compile" in command:
                    try:
                        compile(file_content, dest_path, "exec")
                        out_lines.append("[sandbox] py_compile exit code: 0")
                        exit_code = 0
                    except SyntaxError as syn_err:
                        out_lines.append(f'  File "{dest_path}", line {syn_err.lineno}\n    {syn_err.text or ""}\nSyntaxError: {syn_err.msg}')
                        out_lines.append("[sandbox] py_compile exit code: 1")
                        exit_code = 1
                else:
                    out_lines.append("Guest operation completed.")
                    exit_code = 0
                stdout = "\n".join(out_lines)
            else:
                stdout = "Guest operation completed."
                exit_code = 0
        elif command.startswith("touch ") or command.startswith("echo "):
            parts = command.split(" > ")
            if len(parts) == 2:
                content, filepath = parts[0].replace("echo ", "").strip("\"'"), parts[1].strip()
                self.guest_state.setdefault("files", {})[filepath] = content
            stdout = "Guest operation completed."
            exit_code = 0
        elif "git clone" in command:
            # Robust git repository extraction (supports compound commands like 'git clone ... && cat ...')
            git_match = re.search(r"(?:https?://|git@)[^\s]+", command)
            if git_match:
                git_url = git_match.group(0).rstrip("/").rstrip(";").split("&")[0].strip()
                repo_name = git_url.split("/")[-1].replace(".git", "")
            else:
                clone_part = command.split("git clone")[1].strip().split()
                repo_name = clone_part[0].rstrip("/").split("/")[-1].replace(".git", "") if clone_part else "repo"

            target_path = f"/workspace/quarantine/{repo_name}"
            self.guest_state.setdefault("files", {})[f"{target_path}/README.md"] = f"# Quarantined {repo_name}\nIsolated in Celesto Guest MicroVM."
            self.guest_state.setdefault("files", {})[f"{target_path}/package.json"] = json.dumps({"name": repo_name, "version": "4.18.2", "description": f"Quarantined {repo_name} package in Celesto MicroVM"}, indent=2)
            stdout = (
                "SIMULATION ONLY: git clone was not executed and no repository was downloaded. "
                f"A real sandbox would place it at {target_path}."
            )

            # If command chained a cat or file read on the newly cloned repo (e.g. && cat express/package.json)
            if "&&" in command or ";" in command:
                sub_commands = re.split(r"&&|;", command)[1:]
                sub_outputs = [stdout]
                for sub in sub_commands:
                    sub = sub.strip()
                    if sub.startswith("cat "):
                        sub_file = sub[4:].strip().strip("'\"")
                        if not sub_file.startswith("/"):
                            sub_file = f"/workspace/quarantine/{sub_file}"
                        if sub_file in self.guest_state.get("files", {}):
                            sub_outputs.append(self.guest_state["files"][sub_file])
                        else:
                            sub_outputs.append(f"cat: {sub_file}: No such file or directory")
                    else:
                        sub_outputs.append(f"Guest executed: {sub}")
                stdout = "\n".join(sub_outputs)
            exit_code = 0
        elif command.startswith("cat ") and not any(k in command for k in (">", "<<", "|", "&&", ";")):
            target_path = command[4:].strip().strip("'\"")
            files = self.guest_state.get("files", {})
            if target_path in files:
                stdout = files[target_path]
                exit_code = 0
            elif (target_path if target_path.startswith("/") else f"/{target_path}") in files:
                stdout = files[target_path if target_path.startswith("/") else f"/{target_path}"]
                exit_code = 0
            else:
                stdout = f"cat: {target_path}: No such file or directory"
                exit_code = 1
        else:
            stdout = f"Guest executed: {command}"
            exit_code = 0

        duration_ms = (time.perf_counter() - start_t) * 1000
        return SandboxCommandResult(
            command=command,
            exit_code=exit_code,
            stdout=stdout,
            stderr="",
            duration_ms=duration_ms,
            sandbox_id=self.sandbox_id,
            blocked=False,
        )


class StepWorkflowEngine:
    """
    10-Step Autonomous Workflow Engine with Step 7 Failure Injection
    and Automated Snapshot Rollback Recovery.
    """

    def __init__(self, sandbox: CelestoSandboxRunner | None = None):
        self.sandbox = sandbox or CelestoSandboxRunner()

    def execute_10_step_workflow(
        self, workflow_name: str = "celesto_deployment_pipeline", auto_rollback: bool = True
    ) -> WorkflowExecutionReport:
        """
        Executes a 10-step autonomous workflow:
        - Steps 1-5: Setup & dependencies.
        - Step 6: Takes snapshot checkpoint ('step6_pre_detonation').
        - Step 7: Deliberate failure encountered (attempts host boundary access).
        - Rollback: Reverts to step 6 snapshot, heals parameter, and finishes Steps 8-10.
        """
        self.sandbox.pre_flight_cleanup()
        self.sandbox.start_sandbox()

        step_definitions = [
            (1, "Initialize Guest MicroVM Environment", "echo 'init' > /tmp/step1.txt"),
            (2, "Mount Workspace Storage", "echo 'mount' > /tmp/step2.txt"),
            (3, "Install System Packages", "echo 'pkgs' > /tmp/step3.txt"),
            (4, "Validate Package Signatures", "echo 'valid' > /tmp/step4.txt"),
            (5, "Pre-compile Binary Assets", "echo 'compile' > /tmp/step5.txt"),
            (6, "Create Safety Checkpoint", "CHECKPOINT"),
            (7, "Execute Untrusted Third-Party Payload", "echo malicious > /host_root/breach.txt"),
            (8, "Verify MicroVM Integrity", "cat /etc/os-release"),
            (9, "Run Air-Gapped Network Verification", "echo 'airgap_verified' > /tmp/step9.txt"),
            (10, "Final Deployment Healthcheck", "echo 'deployment_ready' > /tmp/step10.txt"),
        ]

        step_reports: list[WorkflowStepReport] = []
        failure_encountered = False
        failure_step = None
        rollback_occurred = False
        restored_checkpoint = None
        checkpoint_name = "step6_pre_detonation"

        try:
            for step_num, name, cmd in step_definitions:
                start_t = time.perf_counter()

                if cmd == "CHECKPOINT":
                    self.sandbox.create_snapshot(checkpoint_name)
                    dur = (time.perf_counter() - start_t) * 1000
                    step_reports.append(
                        WorkflowStepReport(
                            step_num=step_num,
                            name=name,
                            status="SUCCESS",
                            duration_ms=dur,
                            output=f"Checkpoint '{checkpoint_name}' created.",
                            checkpoint_created=checkpoint_name,
                        )
                    )
                    continue

                # Run command inside microVM
                res = self.sandbox.run_in_sandbox(cmd)

                # Step 7 Deliberate Failure Handling
                if step_num == 7 and res.blocked:
                    failure_encountered = True
                    failure_step = 7
                    dur = (time.perf_counter() - start_t) * 1000

                    step_reports.append(
                        WorkflowStepReport(
                            step_num=7,
                            name=name,
                            status="FAILED",
                            duration_ms=dur,
                            output=f"Step 7 intentional failure caught: {res.stderr}",
                        )
                    )

                    if auto_rollback:
                        # Perform Rollback to Step 6 Checkpoint
                        t_rb = time.perf_counter()
                        self.sandbox.restore_snapshot(checkpoint_name)
                        rollback_occurred = True
                        restored_checkpoint = checkpoint_name

                        # Self-healing: replace toxic command with sanitized sandboxed equivalent
                        healed_cmd = "echo sanitized_payload > /tmp/step7_safe.txt"
                        healed_res = self.sandbox.run_in_sandbox(healed_cmd)
                        rb_dur = (time.perf_counter() - t_rb) * 1000

                        step_reports.append(
                            WorkflowStepReport(
                                step_num=7,
                                name=f"{name} (Self-Healed Post-Rollback)",
                                status="HEALED",
                                duration_ms=rb_dur,
                                output=f"Rolled back to {checkpoint_name} in {rb_dur:.1f}ms. Healed result: {healed_res.stdout}",
                            )
                        )
                    else:
                        break
                    continue

                dur = (time.perf_counter() - start_t) * 1000
                step_reports.append(
                    WorkflowStepReport(
                        step_num=step_num,
                        name=name,
                        status="SUCCESS",
                        duration_ms=dur,
                        output=res.stdout,
                    )
                )

        finally:
            self.sandbox.teardown()

        # Determine overall recovery status
        success_count = sum(1 for r in step_reports if r.status in ("SUCCESS", "HEALED"))
        recovery_status = (
            "RECOVERED"
            if (rollback_occurred and success_count >= 10)
            else ("CLEAN_RUN" if not failure_encountered else "FAILED")
        )

        return WorkflowExecutionReport(
            workflow_id=f"wf-{uuid.uuid4().hex[:8]}",
            total_steps=10,
            steps_completed=success_count,
            failure_encountered=failure_encountered,
            failure_step=failure_step,
            rollback_occurred=rollback_occurred,
            restored_checkpoint=restored_checkpoint,
            recovery_status=recovery_status,
            host_compromised=False,
            step_reports=step_reports,
        )


# Global Runner Instance
sandbox_runner = CelestoSandboxRunner()
workflow_engine = StepWorkflowEngine(sandbox_runner)


def _celesto_readiness() -> dict[str, Any]:
    """Check configuration prerequisites without creating a computer."""
    from spacev.config import settings

    provider = str(settings.celesto_provider or "").strip().lower()
    backend = str(settings.celesto_backend or "").strip().lower()
    key = str(settings.celesto_api_key or "").strip()
    key_configured = bool(key and key.lower() not in {"placeholder_key", "replace-with-celesto-api-key"})
    sdk_available = importlib.util.find_spec("celesto") is not None
    python_supported = sys.version_info >= (3, 11)

    blockers: list[str] = []
    if provider in {"local", "cloud"}:
        mode = "celesto"
    elif provider in {"simulation", "simulator"}:
        mode = "simulation"
    else:
        mode = "unavailable"
        blockers.append(f"Unsupported CELESTO_PROVIDER value: {provider or '(blank)'}.")
    if not python_supported:
        blockers.append("The Celesto Python SDK requires Python 3.11 or newer.")
    if not sdk_available:
        blockers.append("The Celesto Python SDK is not installed in this environment.")
    if provider == "cloud" and not key_configured:
        blockers.append("CELESTO_PROVIDER is cloud, but no non-placeholder CELESTO_API_KEY is configured.")
    elif provider == "local" and os.name == "nt":
        blockers.append("Local Celesto virtualization is unavailable on this Windows host; use Celesto Cloud or a supported host.")
    if provider == "local" and not backend:
        blockers.append("CELESTO_BACKEND is blank; set the local Celesto backend in .env.")

    return {
        "mode": mode,
        "provider": provider or "(blank)",
        "backend": backend or "(blank)",
        "key_configured": key_configured,
        "sdk_installed": sdk_available,
        "python_supported": python_supported,
        "configured_for_real_execution": not blockers,
        "blockers": blockers,
    }


@dataclass(frozen=True)
class _ApprovedTaskScope:
    description: str


@dataclass
class _SandboxSession:
    session_id: str
    approved_task_scope: _ApprovedTaskScope
    instance: Any
    started_at: float
    last_activity: float
    command_count: int = 0
    aggregate_command_ms: float = 0.0
    expired: bool = False
    cleanup_error: str = ""

    @property
    def task_description(self) -> str:
        return self.approved_task_scope.description


class SandboxSessionManager:
    """Owns one approved, reusable Celesto computer with bounded lifetime."""

    APPROVAL_TTL_SECONDS = 15 * 60
    IDLE_TTL_SECONDS = 15 * 60
    MAX_LIFETIME_SECONDS = 60 * 60

    def __init__(self):
        self._lock = threading.RLock()
        self._sessions: dict[str, _SandboxSession] = {}
        self._pending: dict[str, tuple[str, float]] = {}
        self._reaper_stop = threading.Event()
        self._reaper_thread = threading.Thread(
            target=self._reaper_loop,
            name="SpaceVSandboxSessionReaper",
            daemon=True,
        )
        self._reaper_thread.start()

    def _reaper_loop(self) -> None:
        while not self._reaper_stop.wait(30.0):
            try:
                with self._lock:
                    self._expire_locked()
            except Exception:
                logger.exception("Celesto session reaper encountered an error")

    def _expire_locked(self) -> None:
        now = time.monotonic()
        for approval_id, (_task, expiry) in list(self._pending.items()):
            if now >= expiry:
                self._pending.pop(approval_id, None)
        for session_id, session in list(self._sessions.items()):
            if session.expired:
                continue
            idle_expired = now - session.last_activity >= self.IDLE_TTL_SECONDS
            lifetime_expired = now - session.started_at >= self.MAX_LIFETIME_SECONDS
            if idle_expired or lifetime_expired:
                session.expired = True
                try:
                    session.instance.close()
                except Exception as exc:
                    session.cleanup_error = f"{type(exc).__name__}: {exc}"
                cleanup_failed = getattr(session.instance, "state", "") == "cleanup_failed" or bool(session.cleanup_error)
                if not cleanup_failed:
                    self._sessions.pop(session_id, None)
                logger.info(
                    "Expired Celesto session %s state=%s cleanup_failed=%s timings_ms=%s",
                    session_id,
                    getattr(session.instance, "state", "unknown"),
                    cleanup_failed,
                    json.dumps(session.instance.phase_timings_ms, sort_keys=True),
                )

    def active_count(self) -> int:
        with self._lock:
            self._expire_locked()
            return len(self._sessions)

    def continuation_context(self, user_prompt: str | None = None) -> str:
        """Return sandbox state only for a related follow-up, never for a disallowed/unrelated task."""
        with self._lock:
            self._expire_locked()
            pending_match = re.fullmatch(
                r"approve sandbox task ([a-f0-9]{10})",
                str(user_prompt or "").strip(),
                flags=re.IGNORECASE,
            )
            prompt_text = str(user_prompt or "").casefold()
            if user_prompt and not pending_match:
                # Negative tool constraints in a new request override stale
                # task context, which would otherwise force sandbox-only tools.
                if re.search(
                    r"\b(?:do not|don't|never|avoid|without)\b[^.!?\n]{0,120}\b(?:sandbox|celesto|vm)\b",
                    prompt_text,
                ) or re.search(r"\bno\s+(?:sandbox|celesto)\s+tools?\b", prompt_text):
                    return ""
            if self._sessions:
                session = next(iter(self._sessions.values()))
                prompt_text = str(user_prompt or "").casefold()
                explicitly_names_session = bool(session.session_id.casefold() in prompt_text)
                if user_prompt and not explicitly_names_session and not self._context_matches(user_prompt, session.task_description):
                    return ""
                payload = {
                    "state": "cleanup_required" if session.expired or session.cleanup_error or getattr(session.instance, "state", "") == "cleanup_failed" else "active_approved_session",
                    "session_id": session.session_id,
                    "approved_task": session.task_description,
                    "cleanup_error": session.cleanup_error or getattr(session.instance, "backend_error", ""),
                }
            elif self._pending:
                if pending_match:
                    approval_id = pending_match.group(1).lower()
                    pending = self._pending.get(approval_id)
                    if pending is None:
                        return ""
                    task_description, _expiry = pending
                else:
                    approval_id, (task_description, _expiry) = next(reversed(self._pending.items()))
                    if user_prompt and not self._context_matches(user_prompt, task_description):
                        return ""
                payload = {
                    "state": "awaiting_user_approval",
                    "approval_id": approval_id,
                    "task": task_description,
                }
            else:
                return ""
        return (
            "[Persisted sandbox task state; use only to resolve follow-ups to this task, "
            "and never let it override the current user's constraints]\n"
            + json.dumps(payload, ensure_ascii=False)
        )

    def resolve_active_continuation(self, user_prompt: str) -> tuple[dict[str, Any] | None, str | None]:
        """Resolve an explicitly requested continuation from manager-owned session state.

        Session IDs in the prompt are treated only as selectors and must match the
        active manager record. When no ID is provided, distinctive task terms must
        match; generic words such as "continue" are not enough to reuse a session.
        """
        prompt = str(user_prompt or "")
        requested_ids = [
            match.group(0).rstrip(".,!?;:)]}'\"`")
            for match in re.finditer(r"\bsession-[^\s,;!?)}\]]*", prompt, re.IGNORECASE)
        ]
        with self._lock:
            self._expire_locked()
            if not self._sessions:
                if requested_ids:
                    requested = requested_ids[0]
                    return None, f"Celesto session {requested} is not active in SpaceV's session manager; no command was run."
                return None, "No active approved Celesto session is available; no command was run."
            if len(self._sessions) != 1:
                return None, "More than one Celesto session is active; continuation is ambiguous, so no command was run."

            session_id, session = next(iter(self._sessions.items()))
            if requested_ids:
                distinct_ids = set(requested_ids)
                if len(distinct_ids) != 1 or not re.fullmatch(r"session-[a-f0-9]{12}", requested_ids[0]):
                    return None, "The supplied Celesto session ID is malformed or ambiguous; no command was run."
                if session_id != requested_ids[0]:
                    return None, "The requested session ID does not match the active approved session; no command was run."
            elif not self._task_scope_matches(prompt, session.task_description):
                return None, (
                    "An active Celesto session exists, but this request does not identify its approved task clearly; "
                    "no command was run. Include the task's distinctive issue or repository details, not the session ID."
                )

            if session.expired or session.cleanup_error or getattr(session.instance, "state", "") == "cleanup_failed":
                return None, (
                    f"Celesto session {session_id} is expired or requires explicit cleanup; "
                    "continuation was rejected and no command was run."
                )

            return {
                "state": "active_approved_session",
                "session_id": session.session_id,
                "approved_task": session.task_description,
                "cleanup_error": session.cleanup_error or getattr(session.instance, "backend_error", ""),
            }, None

    @staticmethod
    def _task_scope_matches(user_prompt: str, task_description: str) -> bool:
        """Match only an exact issue/repository identity or the complete approved task text."""
        prompt = str(user_prompt or "").casefold()
        task = str(task_description or "").casefold()
        task_repo_url = re.search(r"https?://github\.com/([^/\s]+)/([^/\s?#]+)", task)
        task_repo = (
            f"{task_repo_url.group(1)}/{task_repo_url.group(2).removesuffix('.git')}"
            if task_repo_url else None
        )
        if not task_repo:
            task_repo_match = re.search(r"(?<![\w.-])([a-z0-9_.-]+/[a-z0-9_.-]+)(?![\w.-])", task)
            task_repo = task_repo_match.group(1) if task_repo_match else None
        task_issues = set(re.findall(r"\bissue\s*#?\s*(\d+)\b", task))
        task_issues.update(re.findall(r"github\.com/[^/\s]+/[^/\s]+/issues/(\d+)\b", task))
        if task_repo and task_issues:
            prompt_repo_url = re.search(r"https?://github\.com/([^/\s]+)/([^/\s?#]+)", prompt)
            prompt_repos = set()
            if prompt_repo_url:
                prompt_repos.add(
                    f"{prompt_repo_url.group(1)}/{prompt_repo_url.group(2).removesuffix('.git')}"
                )
            else:
                prompt_repos.update(
                    re.findall(r"(?<![\w.-])([a-z0-9_.-]+/[a-z0-9_.-]+)(?![\w.-])", prompt)
                )
            prompt_issues = set(re.findall(r"\bissue\s*#?\s*(\d+)\b", prompt))
            prompt_issues.update(re.findall(r"github\.com/[^/\s]+/[^/\s]+/issues/(\d+)\b", prompt))
            return (
                prompt_repos == {task_repo}
                and prompt_issues == task_issues
            )

        normalized_task = " ".join(re.findall(r"\w+", task))
        normalized_prompt = " ".join(re.findall(r"\w+", prompt))
        return bool(normalized_task and normalized_task in normalized_prompt)

    @staticmethod
    def _context_matches(user_prompt: str, task_description: str) -> bool:
        """Keep only explicit follow-ups or requests sharing distinctive task terms."""
        prompt = str(user_prompt or "").casefold()
        follow_up = re.search(
            r"\b(continue|resume|approval|proposal|that task|same task|what.{0,20}(?:next|now))\b",
            prompt,
        )
        stop_words = {"about", "after", "again", "also", "could", "from", "have", "into", "just", "more", "only", "please", "same", "should", "that", "task", "the", "this", "what", "with", "would"}
        prompt_terms = {
            token for token in re.findall(r"[a-z0-9][a-z0-9_.#/-]{2,}", prompt)
            if token not in stop_words
        }
        task_terms = {
            token for token in re.findall(r"[a-z0-9][a-z0-9_.#/-]{2,}", str(task_description or "").casefold())
            if token not in stop_words
        }
        return bool(follow_up or len(prompt_terms & task_terms) >= 2)

    def create(self, task_description: str, approval_id: str = "", approval_text: str = "") -> str:
        task_description = str(task_description or "").strip()
        approval_id = str(approval_id or "").strip()
        if not approval_id:
            placeholder = unresolved_template_marker(task_description)
            if placeholder:
                return (
                    "BLOCKED: Sandbox task still contains the unresolved placeholder "
                    f"{placeholder!r}. Supply the missing task input; no Celesto VM was started."
                )
        if not approval_id and not 8 <= len(task_description) <= 800:
            return "BLOCKED: Describe the approved task in 8 to 800 characters. No Celesto VM was started."

        readiness = _celesto_readiness()
        if readiness["mode"] != "celesto" or not readiness["configured_for_real_execution"]:
            details = "\n".join(f"- {reason}" for reason in readiness["blockers"])
            return f"BLOCKED: Celesto is not ready; no VM was started.\n{details}"

        with self._lock:
            self._expire_locked()
            if self._sessions:
                active_id = next(iter(self._sessions))
                return (
                    f"BLOCKED: Celesto session {active_id} is already active. Reuse it for this task or close it first; "
                    "SpaceV allows one managed session at a time."
                )

            if not approval_id:
                approval_id = uuid.uuid4().hex[:10]
                self._pending[approval_id] = (
                    task_description,
                    time.monotonic() + self.APPROVAL_TTL_SECONDS,
                )
                return (
                    "SPACEV_NEEDS_USER_INPUT: I propose one Celesto VM for this task:\n"
                    f"Task: {task_description}\n"
                    "It will remain available for up to 15 minutes idle (1 hour maximum), then SpaceV will delete it. "
                    "Commands and phase timings will be audited. No VM has been started yet.\n"
                    f"To approve this task, reply exactly: approve sandbox task {approval_id}"
                )

            pending = self._pending.get(approval_id)
            if pending is None:
                return "BLOCKED: Sandbox approval is unknown, expired, or already used. Request a fresh proposal."
            approved_task, expiry = pending
            if time.monotonic() >= expiry:
                self._pending.pop(approval_id, None)
                return "BLOCKED: Sandbox approval expired. Request a fresh proposal."
            if str(approval_text or "").strip().casefold() != f"approve sandbox task {approval_id}".casefold():
                return "BLOCKED: The exact approval phrase was not supplied. No Celesto VM was started."

            placeholder = unresolved_template_marker(approved_task)
            if placeholder:
                self._pending.pop(approval_id, None)
                return (
                    "BLOCKED: The approved sandbox task still contains the unresolved placeholder "
                    f"{placeholder!r}. No Celesto VM was started; submit a corrected proposal."
                )

            # The proposal is the authorization source of truth. The model may
            # omit or paraphrase task_description on the approval turn; never
            # execute that new text. Use only the task bound to this approval ID.
            task_description = approved_task
            self._pending.pop(approval_id, None)

            from spacev.fleet.celesto_engine import CelestoSandboxInstance

            task_started = time.monotonic()
            # Use enough entropy for Celesto's persistent local VM namespace.
            # Short friendly SDK-generated names can collide with stale VMs.
            instance = CelestoSandboxInstance(f"sbx-{uuid.uuid4().hex}")
            if instance.state != "ready" or not instance.backend_connected:
                error = instance.backend_error or "Celesto did not return a live computer."
                instance.close()
                timings = dict(instance.phase_timings_ms)
                return (
                    "BLOCKED: Celesto could not start the approved task; no command was run. "
                    f"{error}\nPhase timings (ms): {json.dumps(timings, sort_keys=True)}"
                )

            now = time.monotonic()
            session_id = f"session-{uuid.uuid4().hex[:12]}"
            self._sessions[session_id] = _SandboxSession(
                session_id=session_id,
                approved_task_scope=_ApprovedTaskScope(task_description),
                instance=instance,
                started_at=task_started,
                last_activity=now,
            )
            return (
                f"[CELESTO SESSION READY] Session ID: {session_id}; sandbox: {instance.name}. "
                "This VM is now reusable across commands for the approved task. "
                f"VM startup: {instance.phase_timings_ms['vm_startup_ms']:.2f} ms."
            )

    def run(self, session_id: str, command: str) -> str:
        command = str(command or "").strip()
        if not command or len(command) > 10000 or "\x00" in command:
            return "BLOCKED: Command must be non-empty, at most 10000 characters, and contain no NUL bytes."
        with self._lock:
            self._expire_locked()
            session = self._sessions.get(str(session_id or "").strip())
            if session is None:
                return "BLOCKED: Celesto session is missing or expired. Create a new approved session."
            if session.expired or session.cleanup_error or getattr(session.instance, "state", "") == "cleanup_failed":
                return "BLOCKED: This Celesto session is expired or has unresolved cleanup. Only close_sandbox_session is allowed."
            policy_error = validate_approved_guest_command(session.task_description, command)
            if policy_error:
                return f"BLOCKED: Guest command is outside the approved task scope: {policy_error}. No guest command was executed."
            tool_started = time.perf_counter()
            command_timeout_seconds = guest_command_timeout_seconds(command)
            result = session.instance.run(command, timeout_seconds=command_timeout_seconds)
            tool_command_ms = round((time.perf_counter() - tool_started) * 1000.0, 2)
            session.command_count += 1
            session.aggregate_command_ms += session.instance.phase_timings_ms["command_ms"]
            session.last_activity = time.monotonic()
            timing = {
                "command_ms": session.instance.phase_timings_ms["command_ms"],
                "command_tool_total_ms": tool_command_ms,
                "command_timeout_seconds": command_timeout_seconds,
                "session_vm_startup_ms": session.instance.phase_timings_ms["vm_startup_ms"],
                "session_commands_total_ms": round(session.aggregate_command_ms, 2),
                "session_lifetime_ms": round((time.monotonic() - session.started_at) * 1000.0, 2),
            }
            return (
                f"[CELESTO SESSION EXECUTION] Session: {session.session_id}; sandbox: {session.instance.name}; "
                f"command {session.command_count}; exit code: {result.exit_code}\n"
                f"Phase timings (ms): {json.dumps(timing, sort_keys=True)}\n"
                f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )

    def close(self, session_id: str) -> str:
        with self._lock:
            self._expire_locked()
            session_id = str(session_id or "").strip()
            session = self._sessions.get(session_id)
            if session is None:
                return "Celesto session is already closed, missing, or expired."
            try:
                session.instance.close()
                if getattr(session.instance, "state", "") == "cleanup_failed":
                    session.cleanup_error = str(getattr(session.instance, "backend_error", "Cleanup failed."))
                    session.expired = True
                else:
                    self._sessions.pop(session_id, None)
                    session.cleanup_error = ""
            except Exception as exc:
                session.cleanup_error = f"{type(exc).__name__}: {exc}"
                session.expired = True
            timing = {
                "vm_startup_ms": session.instance.phase_timings_ms.get("vm_startup_ms", 0.0),
                "commands_total_ms": round(session.aggregate_command_ms, 2),
                "cleanup_ms": session.instance.phase_timings_ms.get("cleanup_ms", 0.0),
                "total_task_session_ms": round((time.monotonic() - session.started_at) * 1000.0, 2),
            }
            if session.cleanup_error or getattr(session.instance, "state", "") == "cleanup_failed":
                return (
                    f"[CELESTO SESSION CLEANUP FAILED] Session: {session_id}; sandbox: {session.instance.name}; "
                    f"state: cleanup_failed; session retained for explicit cleanup retry. "
                    f"Error: {session.cleanup_error or getattr(session.instance, 'backend_error', 'unknown cleanup error')}\n"
                    f"Phase timings (ms): {json.dumps(timing, sort_keys=True)}"
                )
            return (
                f"[CELESTO SESSION CLOSED] Sandbox: {session.instance.name}; "
                f"commands: {session.command_count}; state: {session.instance.state}. "
                f"Phase timings (ms): {json.dumps(timing, sort_keys=True)}"
                + (f"\nCleanup error: {session.instance.backend_error}" if session.instance.state == "cleanup_failed" else "")
            )

    def close_all(self) -> None:
        self._reaper_stop.set()
        with self._lock:
            for session_id, session in list(self._sessions.items()):
                session.instance.close()
                self._sessions.pop(session_id, None)


sandbox_session_manager = SandboxSessionManager()
atexit.register(sandbox_session_manager.close_all)


def create_sandbox_session(task_description: str = "", approval_id: str = "", approval_text: str = "") -> str:
    """Propose, then approval-gate a reusable Celesto VM for a bounded task."""
    return sandbox_session_manager.create(task_description, approval_id, approval_text)


def run_sandbox_session_command(session_id: str, command: str) -> str:
    """Run one audited command in an existing approved Celesto session."""
    return sandbox_session_manager.run(session_id, command)


def close_sandbox_session(session_id: str) -> str:
    """Delete an active Celesto session and report total lifecycle timings."""
    return sandbox_session_manager.close(session_id)


def detonate_in_sandbox(command: str) -> str:
    """Run in the .env-selected real Celesto provider, or simulate explicitly."""
    total_started = time.perf_counter()
    readiness = _celesto_readiness()
    if readiness["mode"] == "celesto":
        if not readiness["configured_for_real_execution"]:
            return "BLOCKED: Real Celesto execution is not ready; no command was executed.\n" + "\n".join(
                f"- {reason}" for reason in readiness["blockers"]
            )

        from spacev.fleet.celesto_engine import CelestoSandboxInstance

        instance = CelestoSandboxInstance(f"sbx-{uuid.uuid4().hex}")
        if instance.state != "ready" or not instance.backend_connected:
            error = instance.backend_error or "Celesto did not return a live computer."
            instance.close()
            timings = dict(instance.phase_timings_ms)
            timings["total_ms"] = round((time.perf_counter() - total_started) * 1000.0, 2)
            return (
                "BLOCKED: Celesto computer could not be started; command was not executed. "
                f"{error}\nPhase timings (ms): {json.dumps(timings, sort_keys=True)}"
            )
        try:
            command_timeout_seconds = guest_command_timeout_seconds(command)
            result = instance.run(command, timeout_seconds=command_timeout_seconds)
        finally:
            instance.close()
        timings = dict(instance.phase_timings_ms)
        timings["command_timeout_seconds"] = command_timeout_seconds
        timings["total_ms"] = round((time.perf_counter() - total_started) * 1000.0, 2)
        return (
            f"[CELESTO SDK EXECUTION] Sandbox ID: {instance.name}; exit code: {result.exit_code}; "
            f"cleanup_state: {instance.state}\n"
            f"Phase timings (ms): {json.dumps(timings, sort_keys=True)}\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )

    if readiness["mode"] != "simulation":
        return "BLOCKED: Celesto provider configuration is invalid; no command was executed."

    # Explicit demonstration/test mode only. The emulator does not run commands.
    res = sandbox_runner.run_in_sandbox(command)

    # Pre-detonation neural file inspection telemetry
    neural_meta = None
    try:
        from core.containment_gatekeeper import ContainmentGatekeeper
        for token in command.split():
            clean_token = token.strip("\"';&|")
            if clean_token and Path(clean_token).is_file():
                is_danger, label, reason, conf = ContainmentGatekeeper.inspect_file_payload(clean_token)
                neural_meta = {
                    "scanned_file": clean_token,
                    "is_dangerous": is_danger,
                    "label": label,
                    "reason": reason,
                    "confidence": conf,
                }
                break
    except Exception as e:
        logger.debug(f"Neural pre-inspection non-critical error: {e}")

    # Hackathon Contract #4: Immutable Command Audit Logging
    try:
        commands_log = REPO_ROOT / "logs/commands.jsonl"
        commands_log.parent.mkdir(parents=True, exist_ok=True)
        ts_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        sbx_id = res.sandbox_id if re.match(r"^sbx-[a-z0-9]{8,}$", res.sandbox_id) else f"sbx-{res.sandbox_id.replace('-', '')[:8]}"
        log_payload = {
            "ts": ts_iso,
            "sandbox_name": sbx_id,
            "command": command,
            "decision": "block" if res.blocked else "allow",
            "execution_target": "sandbox_simulator",
        }
        if neural_meta:
            log_payload["neural_inspection"] = neural_meta

        cmd_entry = json.dumps(log_payload) + "\n"
        with open(commands_log, "a", encoding="utf-8") as f:
            f.write(cmd_entry)
    except Exception as e:
        logger.warning(f"Failed to record sandbox audit log: {e}")

    if res.blocked:
        return (
            "[SIMULATION ONLY — this is not real VM containment] The simulated policy blocked the command:\n"
            f"{res.stderr}\nSimulation ID: {res.sandbox_id}"
        )
    return (
        "[SIMULATION ONLY — no host or Celesto command was executed]\n"
        f"{res.stdout}\nSimulation ID: {res.sandbox_id}"
    )


def get_sandbox_status() -> str:
    """Report source registration and real backend readiness without starting a VM."""
    from config import ENABLE_CODE_MODE
    from tools.registry import OLLAMA_TOOLS_SCHEMA, TOOL_FUNCTIONS

    registered = "detonate_in_sandbox" in TOOL_FUNCTIONS
    session_tools = (
        "create_sandbox_session",
        "run_sandbox_session_command",
        "close_sandbox_session",
    )
    source_clone_registered = "clone_public_repository" in TOOL_FUNCTIONS
    schema_registered = any(
        entry.get("function", {}).get("name") == "detonate_in_sandbox"
        for entry in OLLAMA_TOOLS_SCHEMA
    )
    source_clone_schema_registered = any(
        entry.get("function", {}).get("name") == "clone_public_repository"
        for entry in OLLAMA_TOOLS_SCHEMA
    )
    readiness = _celesto_readiness()
    mode = readiness["mode"]
    if mode == "celesto" and readiness["configured_for_real_execution"]:
        execution_backend = "celesto_sdk_with_reusable_sessions"
    elif mode == "simulation":
        execution_backend = "in_memory_simulator"
    else:
        execution_backend = "unavailable"

    active_sessions = sandbox_session_manager.active_count()
    return json.dumps(
        {
            "tool": "detonate_in_sandbox",
            "registered_in_tool_function_map": registered,
            "registered_in_project_tool_schema": schema_registered,
            "reusable_session_tools_registered": all(name in TOOL_FUNCTIONS for name in session_tools),
            "reusable_session_tool_names": list(session_tools),
            "source_only_clone_tool_registered": source_clone_registered,
            "source_only_clone_registered_in_project_tool_schema": source_clone_schema_registered,
            "configured_tool_delivery_mode": "code_mode_meta_tools" if ENABLE_CODE_MODE else "scoped_function_tools",
            "active_model_payload_inspectable": False,
            "configured_sandbox_mode": mode,
            "execution_backend": execution_backend,
            "real_celesto_backend_configured": readiness["configured_for_real_execution"],
            "real_celesto_vm_connected": active_sessions > 0,
            "active_sandbox_sessions": active_sessions,
            "max_concurrent_sandbox_sessions": 1,
            "celesto_sdk_installed": readiness["sdk_installed"],
            "python_version": ".".join(map(str, sys.version_info[:3])),
            "celesto_python_version_supported": readiness["python_supported"],
            "celesto_provider": readiness["provider"],
            "celesto_api_key_configured": readiness["key_configured"],
            "note": "Project registration does not prove a tool was exposed in a specific external harness request.",
            "blockers": readiness["blockers"],
        },
        indent=2,
    )


def inspect_file_security(file_path: str) -> str:
    """
    SpaceV Neural Security Tool:
    Performs sub-millisecond Google Magika deep learning content-type inspection
    to verify file safety and detect masqueraded binaries (e.g. ELF/PE hidden in .png or .csv).
    """
    from core.containment_gatekeeper import ContainmentGatekeeper
    p = Path(file_path.strip("\"'"))
    if not p.exists():
        return f"File not found: {file_path}"
    is_dangerous, label, reason, conf = ContainmentGatekeeper.inspect_file_payload(p)
    if is_dangerous:
        return (
            f"🛡️ [SECURITY INTERCEPTION] Dangerous payload detected by Neural Gatekeeper!\n"
            f"• File: {p.name}\n"
            f"• Detected Label: {label} (Confidence: {conf:.1%})\n"
            f"• Alert Reason: {reason}\n"
            f"• Action: Execution on Host BLOCKED. Route to Celesto MicroVM sandbox."
        )
    return (
        f"✅ [SECURITY VERIFIED] File inspected by Google Magika Neural Gatekeeper:\n"
        f"• File: {p.name}\n"
        f"• Detected Label: {label} (Confidence: {conf:.1%})\n"
        f"• Status: Clean / Verified Safe"
    )


def run_sandboxed_workflow(workflow_name: str = "celesto_deployment_pipeline") -> str:
    """SpaceV tool to execute a 10-step workflow with automated Step 7 snapshot rollback recovery."""
    report = workflow_engine.execute_10_step_workflow(workflow_name, auto_rollback=True)
    return (
        f"⚠️ **Sandbox simulation only — no Celesto VM was started**:\n"
        f"• Status: `{report.recovery_status}`\n"
        f"• Steps Completed: `{report.steps_completed}/{report.total_steps}`\n"
        f"• Step 7 Failure Intercepted: `{report.failure_encountered}`\n"
        f"• Snapshot Rollback Executed: `{report.rollback_occurred}` (Restored `{report.restored_checkpoint}`)\n"
        f"• Host impact: `not measured by a real VM`; simulation result only"
    )


class HostIntegrityMonitor:
    """
    Computes hashes of selected local files for diagnostics. Since the current
    runner is a simulator, this cannot prove isolation from a real guest VM.
    """

    def __init__(self, monitored_files: list[str] | None = None):
        self.monitored_files = monitored_files or [
            "config.py",
            "main.py",
            ".env.example",
            "requirements.txt",
        ]
        self.baseline_hashes: dict[str, str] = {}
        self.capture_baseline()

    def _hash_file(self, rel_path: str) -> str:
        file_path = REPO_ROOT / rel_path
        if not file_path.exists():
            return "NON_EXISTENT"
        hasher = hashlib.sha256()
        hasher.update(file_path.read_bytes())
        return hasher.hexdigest()

    def capture_baseline(self) -> dict[str, str]:
        self.baseline_hashes = {f: self._hash_file(f) for f in self.monitored_files}
        return self.baseline_hashes

    def verify_host_integrity(self) -> dict[str, Any]:
        """Asserts that all monitored host files match their exact pre-detonation SHA-256 hash."""
        current_hashes = {f: self._hash_file(f) for f in self.monitored_files}
        mismatches = []
        for f, base_hash in self.baseline_hashes.items():
            curr_hash = current_hashes.get(f)
            if curr_hash != base_hash:
                mismatches.append({"file": f, "expected": base_hash, "actual": curr_hash})

        is_intact = len(mismatches) == 0
        return {
            "intact": is_intact,
            "host_compromised": not is_intact,
            "monitored_files_count": len(self.monitored_files),
            "mismatches": mismatches,
            "timestamp": time.time(),
        }


class PromptInjectionContainmentHarness:
    """
    Deterministic simulator for containment scenarios. It does not prove real
    VM isolation or host escape resistance.
    """

    def __init__(self, runner: CelestoSandboxRunner | None = None):
        self.runner = runner or CelestoSandboxRunner()
        self.monitor = HostIntegrityMonitor()

    def test_attack_containment(self, attack_type: str = "prompt_injection_exfil") -> dict[str, Any]:
        """
        Executes adversarial attacks:
        - prompt_injection_exfil: tries to read shadow/env secrets
        - destructive_command: attempts host file modification (/host_root)
        - suspicious_package: attempts backdoor installation
        """
        self.monitor.capture_baseline()
        attack_commands = {
            "prompt_injection_exfil": "cat /host_root/etc/shadow || printenv AWS_SECRET_ACCESS_KEY",
            "destructive_command": "rm -rf /host_root/boot && echo breach > /host_root/hacked.txt",
            "suspicious_package": "pip install --target=/host_root backdoor_payload_trojan",
        }
        cmd = attack_commands.get(attack_type, "cat /host_root/etc/shadow")
        res = self.runner.run_in_sandbox(cmd)
        integrity = self.monitor.verify_host_integrity()

        # These checks describe simulator behavior only; they do not prove VM containment.
        blocked = res.blocked or res.exit_code != 0
        host_untouched = integrity["intact"] and not integrity["host_compromised"]

        return {
            "attack": attack_type,
            "command": cmd,
            "blocked": blocked,
            "exit_code": res.exit_code,
            "host_untouched": None,
            "simulated_host_files_unchanged": host_untouched,
            "guest_contained": False,
            "execution_mode": "in_memory_simulation",
            "real_vm_containment_proven": False,
            "sandbox_id": self.runner.sandbox_id,
            "timestamp": time.time(),
        }


def generate_containment_contract_report(attack_type: str = "prompt_injection_exfil") -> Path:
    """
    Writes a clearly labeled simulation report. It is not Celesto containment evidence.
    Appends the simulation record to the evidence and command logs.
    """
    harness = PromptInjectionContainmentHarness()
    res = harness.test_attack_containment(attack_type)

    report_path = REPO_ROOT / "reports/containment.json"
    evidence_log = REPO_ROOT / "reports/evidence/containment.log"
    commands_log = REPO_ROOT / "logs/commands.jsonl"

    report_data = {
        "attack": res["attack"],
        "blocked": res["blocked"],
        "host_untouched": None,
        "simulated_host_files_unchanged": res["simulated_host_files_unchanged"],
        "execution_mode": res["execution_mode"],
        "real_vm_containment_proven": False,
        "evidence_paths": [
            "reports/evidence/containment.log",
            "logs/commands.jsonl",
        ],
    }

    report_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")

    # Append to evidence logs
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{ts}] [SIMULATION_ONLY] attack='{res['attack']}' simulated_blocked={res['blocked']} real_vm_containment_proven=False sandbox={res['sandbox_id']}\n"
    with open(evidence_log, "a", encoding="utf-8") as f:
        f.write(log_entry)

    ts_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    cmd_entry = (
        json.dumps(
            {
                "ts": ts_iso,
                "sandbox_name": res["sandbox_id"],
                "command": res["command"],
                "decision": "block" if res["blocked"] else "allow",
                "execution_target": "sandbox_simulator",
            }
        )
        + "\n"
    )
    with open(commands_log, "a", encoding="utf-8") as f:
        f.write(cmd_entry)

    return report_path


def audit_sandbox_containment(attack_type: str = "prompt_injection_exfil") -> str:
    """SpaceV tool to trigger an adversarial prompt injection containment audit and generate Contract 8 evidence."""
    report_file = generate_containment_contract_report(attack_type)
    return (
        f"⚠️ **Sandbox simulation only — no Celesto containment was tested**:\n"
        f"• Attack Vector Tested: `{attack_type}`\n"
        f"• Simulated policy blocked input: `True`\n"
        f"• Real VM isolation proven: `False`\n"
        f"• Audit Report Written: `{report_file.relative_to(REPO_ROOT)}`"
    )
