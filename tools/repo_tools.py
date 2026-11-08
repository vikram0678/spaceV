"""Narrow, approval-gated tools for acquiring source-only GitHub checkouts."""

from __future__ import annotations

import os
import secrets
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

from config import BASE_DIR

_PENDING_CLONES: dict[str, tuple[str, str, float]] = {}
_PENDING_LOCK = threading.Lock()
_APPROVAL_TTL_SECONDS = 15 * 60


def _validate_clone_target(repository_url: str, destination: str) -> tuple[str, Path]:
    """Validate a public GitHub URL and an absolute, new path outside SpaceV."""
    parsed = urlparse(str(repository_url).strip())
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or len(parts) != 2
        or not parts[0]
        or not parts[1]
    ):
        raise ValueError("Only a public https://github.com/owner/repository URL is allowed.")

    repository_name = parts[1]
    if repository_name.endswith(".git"):
        repository_name = repository_name[:-4]
    if not repository_name or repository_name in {".", ".."}:
        raise ValueError("The repository URL does not contain a valid repository name.")
    normalized_url = f"https://github.com/{parts[0]}/{repository_name}.git"

    target = Path(str(destination).strip())
    if not target.is_absolute():
        raise ValueError("The checkout destination must be an absolute path.")
    resolved_target = target.resolve(strict=False)
    resolved_project = BASE_DIR.resolve()
    try:
        resolved_target.relative_to(resolved_project)
    except ValueError:
        pass
    else:
        raise ValueError("The checkout destination must be outside the SpaceV project directory.")

    if resolved_target == Path(resolved_target.anchor):
        raise ValueError("A drive or filesystem root cannot be used as the checkout destination.")
    if resolved_target.exists() or resolved_target.is_symlink():
        raise FileExistsError(f"The checkout destination already exists: {resolved_target}")

    return normalized_url, resolved_target


def clone_public_repository(
    repository_url: str,
    destination: str,
    approval_id: str = "",
    approval_text: str = "",
) -> str:
    """Clone source-only from GitHub after a separate, exact user approval.

    First call creates a short-lived proposal and performs no filesystem or
    network operation. A second call must present the returned approval ID and
    the same URL and destination. The clone is shallow, non-recursive, uses no
    shell, and disables configured Git hooks and system/global Git config.
    """
    try:
        normalized_url, target = _validate_clone_target(repository_url, destination)
    except (OSError, ValueError) as exc:
        return f"Failed: {exc}"

    approval_id = str(approval_id or "").strip()
    if not approval_id:
        approval_id = secrets.token_hex(4)
        expires_at = time.monotonic() + _APPROVAL_TTL_SECONDS
        with _PENDING_LOCK:
            for stale_id, (_url, _target, stale_expiry) in list(_PENDING_CLONES.items()):
                if stale_expiry < time.monotonic():
                    _PENDING_CLONES.pop(stale_id, None)
            _PENDING_CLONES[approval_id] = (normalized_url, str(target), expires_at)
        git_null_device = "NUL" if os.name == "nt" else "/dev/null"
        return (
            "SPACEV_NEEDS_USER_INPUT: I propose a source-only clone:\n"
            f"Repository: {normalized_url}\n"
            f"Destination: {target}\n"
            f"Command: git -c core.hooksPath={git_null_device} clone --depth=1 --no-tags -- {normalized_url} {target}\n"
            "This downloads source files only. It will not install dependencies, run repository code, or access the SpaceV project.\n"
            f"To approve this exact operation, reply: approve clone {approval_id}"
        )

    with _PENDING_LOCK:
        pending = _PENDING_CLONES.pop(approval_id, None)
    if pending is None:
        return "Failed: This clone approval is unknown, expired, or already used. Ask SpaceV to prepare a new proposal."
    expected_url, expected_target, expires_at = pending
    if time.monotonic() > expires_at:
        return "Failed: This clone approval expired. Ask SpaceV to prepare a new proposal."
    if normalized_url != expected_url or str(target) != expected_target:
        return "Failed: The repository or destination differs from the approved proposal. Ask SpaceV to prepare a new proposal."
    if str(approval_text).strip().casefold() != f"approve clone {approval_id}".casefold():
        return "Failed: The exact user approval phrase was not supplied. No clone was performed."

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["GIT_CONFIG_NOSYSTEM"] = "1"
        env["GIT_CONFIG_GLOBAL"] = os.devnull
        process = subprocess.run(
            [
                "git",
                "-c",
                f"core.hooksPath={os.devnull}",
                "clone",
                "--depth=1",
                "--no-tags",
                "--",
                normalized_url,
                str(target),
            ],
            shell=False,
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
            check=False,
        )
    except FileNotFoundError:
        return "Failed: Git is not installed or is not available on SpaceV's PATH. No clone was performed."
    except subprocess.TimeoutExpired:
        return f"Failed: The clone timed out. Check whether a partial checkout exists at {target}."
    except OSError as exc:
        return f"Failed: Git could not start the clone: {exc}"

    if process.returncode != 0:
        detail = (process.stderr or process.stdout or "Git returned no diagnostic output").strip()[-2000:]
        return f"Failed: Git clone exited with code {process.returncode}. No repository code was run.\n{detail}"

    return (
        f"Cloned source-only checkout to {target}. No dependencies were installed and no repository code was run.\n"
        f"{process.stdout.strip()}"
    )
