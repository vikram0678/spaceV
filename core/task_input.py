"""Validation helpers for detecting unresolved request-template inputs."""

import re

_UNRESOLVED_TEMPLATE_MARKER = re.compile(
    r"\[\s*(?:paste|insert|replace|fill in|enter|placeholder)\b[^\]]{0,200}\]"
    r"|\{\{\s*(?:ISSUE|ISSUE_TEXT|ISSUE_URL|REPO|REPO_URL|URL|TASK)[^}]*\}\}"
    r"|<\s*(?:ISSUE(?:_TEXT|_URL)?|REPO(?:_URL)?|URL|TASK(?:_TEXT)?)\s*>",
    re.IGNORECASE,
)


def unresolved_template_marker(text: str) -> str | None:
    """Return the first common unfilled template marker found in *text*."""
    match = _UNRESOLVED_TEMPLATE_MARKER.search(str(text or ""))
    return match.group(0) if match else None
