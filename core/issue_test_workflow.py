"""Conservative evidence classification for Issue-to-Failing-Test runs."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

_TEST_COMMAND = re.compile(
    r"\bpytest\b|\bpython\s+-m\s+(?:pytest|unittest)\b|\b(?:unittest|tox|nox)\b|"
    r"\bcargo\s+test\b|\bgo\s+test\b|\b(?:npm|pnpm|yarn)\s+test\b|\b(?:mvn|gradle)\s+test\b",
    re.IGNORECASE,
)
_EXIT_CODE = re.compile(r"\bexit code:\s*(-?\d+)", re.IGNORECASE)
_PORCELAIN = re.compile(r"^(?:\?\?|[ MADRCUT?!S]{2})\s+(.+)$")
_MAX_TEST_PATCH_PATHS = 2


def parse_github_issue_url(url: str) -> dict[str, Any]:
    """Validate and normalize a public github.com issue URL; reject PRs/SSRF forms."""
    raw = str(url or "").strip()
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid GitHub issue URL authority or port.") from exc
    if (
        parsed.scheme.casefold() != "https"
        or (parsed.hostname or "").casefold() != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Issue URL must be an HTTPS github.com issue link without credentials, query, or fragment.")
    parts = [unquote(part) for part in parsed.path.strip("/").split("/")]
    if len(parts) != 4 or parts[2] != "issues" or not parts[3].isdigit() or int(parts[3]) < 1:
        raise ValueError("Expected a public GitHub issue URL: /OWNER/REPO/issues/NUMBER (pull requests are not issues).")
    owner, repo, _, number = parts
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", owner) or not re.fullmatch(
        r"[A-Za-z0-9_.-]{1,100}", repo
    ):
        raise ValueError("Owner or repository name contains unsupported characters.")
    canonical = urlunsplit(("https", "github.com", f"/{owner}/{repo}/issues/{int(number)}", "", ""))
    return {
        "issue_url": canonical,
        "repository_url": f"https://github.com/{owner}/{repo}",
        "clone_url": f"https://github.com/{owner}/{repo}.git",
        "owner": owner,
        "repository": repo,
        "issue_number": int(number),
    }


def detect_guest_environment(os_release: str, python_version: str = "", uname: str = "") -> dict[str, Any]:
    """Build a small environment profile from read-only guest command output."""
    fields: dict[str, str] = {}
    for line in str(os_release or "").splitlines():
        key, separator, value = line.partition("=")
        if separator and key in {"ID", "NAME", "VERSION_ID", "VERSION_CODENAME", "PRETTY_NAME"}:
            fields[key] = value.strip().strip('"\'')
    distro = fields.get("ID", "").casefold()
    package_manager = {
        "alpine": "apk",
        "ubuntu": "apt",
        "debian": "apt",
        "fedora": "dnf",
        "rhel": "dnf",
        "centos": "dnf",
        "rocky": "dnf",
        "arch": "pacman",
        "manjaro": "pacman",
    }.get(distro)
    return {
        "os": fields.get("PRETTY_NAME") or fields.get("NAME") or "unknown",
        "distribution_id": distro or "unknown",
        "distribution_version": fields.get("VERSION_ID", "unknown"),
        "package_manager": package_manager or "unknown",
        "python_version": str(python_version or "unknown").strip(),
        "architecture": str(uname or "unknown").strip(),
    }


def format_guest_environment(profile: dict[str, Any]) -> str:
    """Format a compact, structured environment receipt for the issue analyst."""
    return (
        "[SpaceV guest environment profile]\n"
        f"os={profile.get('os', 'unknown')}; distro={profile.get('distribution_id', 'unknown')} "
        f"{profile.get('distribution_version', 'unknown')}; "
        f"package_manager={profile.get('package_manager', 'unknown')}; "
        f"python={profile.get('python_version', 'unknown')}; "
        f"architecture={profile.get('architecture', 'unknown')}"
    )


def _is_test_path(path: str) -> bool:
    normalized = path.strip().strip('"').replace("\\", "/").casefold()
    name = normalized.rsplit("/", 1)[-1]
    return (
        re.search(r"(?:^|/)(?:tests?|testing)/", normalized) is not None
        or re.match(r"test_[^/]+\.(?:py|js|jsx|ts|tsx|go|rs|java)$", name) is not None
        or re.search(r"_[Tt]est\.(?:py|js|jsx|ts|tsx|go|rs|java)$", name) is not None
        or ".spec." in name
    )


def _target_test_from_command(command: str) -> str | None:
    """Extract the narrowest pytest node/file target named in a command."""
    text = str(command or "")
    node_match = re.search(r"(?:^|\s)([^\s]+?\.py(?:::[^\s]+)+)", text, re.IGNORECASE)
    if node_match:
        return node_match.group(1).strip("'\"")
    file_match = re.search(r"(?:^|\s)([^\s]+\.py)(?:\s|$)", text, re.IGNORECASE)
    return file_match.group(1).strip("'\"") if file_match else None


def _target_failure_contains_signal(command: str, output: str, expected_signal: str) -> bool:
    """Require the expected phrase in the target test's failure block/summary."""
    target = _target_test_from_command(command)
    signal = str(expected_signal or "").strip().casefold()
    if not target or not signal:
        return False

    target_node = target.casefold()
    target_name = target_node.rsplit("::", 1)[-1]
    target_path = target_node.split("::", 1)[0].rsplit("/", 1)[-1]
    text = str(output or "")
    headings = list(re.finditer(r"(?m)^_{3,}\s*(.*?)\s*_{3,}\s*$", text))
    for index, heading in enumerate(headings):
        heading_name = heading.group(1).strip().casefold()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        summary = re.search(r"(?m)^=+ short test summary info =+\s*$", text[heading.end():end])
        if summary:
            end = heading.end() + summary.start()
        block = text[heading.start():end].casefold()
        identifies_target = target_name in heading_name or (
            "::" not in target and target_path in block.casefold()
        )
        if identifies_target and signal in block:
            return True

    # Pytest's one-line failure summary is also tied to a concrete node ID.
    for line in text.splitlines():
        lower_line = line.casefold()
        if "failed" in lower_line and signal in lower_line and (
            target_name in lower_line or target_path in lower_line or target_node in lower_line
        ):
            return True
    return False


def classify_test_execution(command: str, tool_output: str, expected_signal: str = "") -> dict[str, Any] | None:
    """Classify a captured test command without treating generic failure as bug proof.

    `EXPECTED_BUG_FAILURE` requires a non-zero test exit and an explicit,
    issue-derived expected signal in the captured output. Otherwise uncertain
    failures stay inconclusive or are assigned a concrete setup category.
    """
    if not _TEST_COMMAND.search(str(command or "")):
        return None

    output = str(tool_output or "")
    lower = output.casefold()
    code_match = _EXIT_CODE.search(output)
    exit_code = int(code_match.group(1)) if code_match else None

    if re.search(r"timed out|timeoutexpired|command timed out", lower):
        classification, reason = "TIMEOUT", "The command exceeded its execution timeout."
    elif re.search(r"no tests? (?:were )?found|no tests collected|test file not found|not found:.*test", lower):
        classification, reason = "TEST_DISCOVERY_ERROR", "The requested test was not discovered or its path was not found."
    elif re.search(
        r"no matching distribution|could not find a version|failed to install|dependency resolution|pytest: not found",
        lower,
    ):
        classification, reason = "DEPENDENCY_ERROR", "The output indicates dependency resolution or installation failed."
    elif re.search(r"modulenotfounderror|no module named|importerror|cannot import name|failed to import", lower):
        classification, reason = "IMPORT_ERROR", "The test could not import the required module or symbol."
    elif exit_code is None:
        classification, reason = "INCONCLUSIVE", "No test exit code was captured."
    elif exit_code == 0:
        classification, reason = "PASS_NO_REPRODUCTION", "The test command passed; this run did not reproduce a failure."
    else:
        failed_marker = bool(re.search(r"assertionerror|assert .* failed|\bfailed\b|\berror\b", lower))
        signal = str(expected_signal or "").strip()
        if signal and failed_marker and _target_failure_contains_signal(command, output, signal):
            classification = "EXPECTED_BUG_FAILURE"
            reason = "The explicitly targeted test's failure output contains the expected issue symptom."
        elif re.search(r"assertionerror|assert .* failed|\bfailed\b", lower):
            classification = "INCONCLUSIVE"
            reason = (
                "The test command failed, but the target test's failure output does not establish the issue's expected symptom. "
                "A non-zero exit or a matching phrase elsewhere is not proof of reproduction."
            )
        else:
            classification = "ENVIRONMENT_ERROR"
            reason = "The test command failed without a captured assertion matching the reported behavior."

    return {
        "classification": classification,
        "exit_code": exit_code,
        "expected_signal": str(expected_signal or "").strip() or None,
        "expected_signal_observed": bool(expected_signal and _target_failure_contains_signal(command, output, expected_signal)),
        "reason": reason,
    }


def classify_git_status(command: str, tool_output: str) -> dict[str, Any] | None:
    """Classify a captured `git status --short` snapshot without overclaiming baseline cleanliness."""
    if not re.search(r"git\s+status\s+--short\b", str(command or ""), re.IGNORECASE):
        return None
    output = str(tool_output or "")
    stdout_match = re.search(r"STDOUT:\s*\n(.*?)(?:\nSTDERR:|\Z)", output, re.IGNORECASE | re.DOTALL)
    stdout = stdout_match.group(1) if stdout_match else output
    paths = [match.group(1).strip() for line in stdout.splitlines() if (match := _PORCELAIN.match(line))]
    if not paths:
        classification = "CLEAN_WORKTREE"
        note = "This status snapshot reports no changed paths."
    elif all(
        all(_is_test_path(part) for part in path.split(" -> "))
        for path in paths
    ):
        classification = "TEST_FILES_ONLY"
        note = "This status snapshot lists only test-like paths; compare it with the pre-edit baseline before claiming production files stayed unchanged."
    else:
        classification = "NON_TEST_FILES_CHANGED"
        note = "This status snapshot includes at least one path outside recognized test locations/names."
    return {"classification": classification, "paths": paths, "reason": note}


def classify_test_patch_paths(command: str, tool_output: str) -> dict[str, Any] | None:
    """Audit changed paths from git output; never infer safety from a test result.

    Accepts `git diff --name-only` and `git status --short` snapshots. A path is
    considered test-only only if it is repository-relative, contains no parent
    traversal, and matches a conventional test directory or test filename.
    This is an evidence classifier; callers must still stop if output is
    truncated or the command failed.
    """
    command_text = str(command or "")
    is_name_only = bool(re.search(r"git\s+diff\b[^\n]*--name-only\b", command_text, re.IGNORECASE))
    is_porcelain = bool(re.search(r"git\s+status\s+--short\b", command_text, re.IGNORECASE))
    if not (is_name_only or is_porcelain):
        return None

    output = str(tool_output or "")
    exit_match = _EXIT_CODE.search(output)
    exit_code = int(exit_match.group(1)) if exit_match else None
    stdout_match = re.search(r"STDOUT:\s*\n(.*?)(?:\nSTDERR:|\Z)", output, re.IGNORECASE | re.DOTALL)
    stdout = stdout_match.group(1) if stdout_match else output
    paths: list[str] = []
    for line in stdout.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        if is_porcelain:
            match = _PORCELAIN.match(line)
            if not match:
                continue
            candidate = match.group(1).strip()
            # A rename records two paths; audit both sides.
            paths.extend(part.strip().strip('"') for part in candidate.split(" -> "))
        else:
            paths.append(candidate.strip('"'))

    unsafe_paths = []
    for path in paths:
        normalized = path.replace("\\", "/").strip()
        segments = normalized.split("/")
        if normalized.startswith("/") or re.match(r"^[a-z]:", normalized, re.IGNORECASE) or ".." in segments:
            unsafe_paths.append(path)

    if exit_code != 0:
        classification = "PATCH_AUDIT_COMMAND_FAILED"
        reason = f"The git path audit command did not provide a successful exit code (captured: {exit_code})."
    elif unsafe_paths:
        classification = "PATCH_PATH_UNSAFE"
        reason = "The audit contains absolute or parent-traversal paths."
    elif len(paths) > _MAX_TEST_PATCH_PATHS:
        classification = "PATCH_TOO_MANY_FILES"
        reason = f"The patch lists {len(paths)} paths; the pilot limit is {_MAX_TEST_PATCH_PATHS}."
    elif paths and all(_is_test_path(path) for path in paths):
        classification = "TEST_FILES_ONLY"
        reason = "All reported changed paths match recognized test paths."
    elif paths:
        classification = "NON_TEST_FILES_CHANGED"
        reason = "At least one reported changed path is outside recognized test paths."
    else:
        classification = "NO_CHANGED_PATHS"
        reason = "The command returned no changed paths; this does not prove a proposed patch is safe."

    return {
        "classification": classification,
        "paths": paths,
        "unsafe_paths": unsafe_paths,
        "exit_code": exit_code,
        "reason": reason,
    }


def format_test_classification(result: dict[str, Any]) -> str:
    """Render a compact machine-derived note for the model and evidence report."""
    return (
        "[SpaceV test-run classification]\n"
        f"classification={result['classification']}; exit_code={result['exit_code']}; "
        f"expected_signal_observed={str(result['expected_signal_observed']).lower()}\n"
        f"reason={result['reason']}"
    )


def format_git_status_classification(result: dict[str, Any]) -> str:
    paths = ", ".join(result["paths"]) if result["paths"] else "(none)"
    return (
        "[SpaceV changed-path audit]\n"
        f"classification={result['classification']}; paths={paths}\n"
        f"note={result['reason']}"
    )


def format_test_patch_audit(result: dict[str, Any]) -> str:
    paths = ", ".join(result["paths"]) if result["paths"] else "(none)"
    unsafe = ", ".join(result["unsafe_paths"]) if result["unsafe_paths"] else "(none)"
    return (
        "[SpaceV test-patch path audit]\n"
        f"classification={result['classification']}; exit_code={result['exit_code']}; "
        f"paths={paths}; unsafe_paths={unsafe}\n"
        f"reason={result['reason']}"
    )
