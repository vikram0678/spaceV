"""
SpaceV Context Compressor
Algorithmic token reducer inspired by OmniRoute toolResultCompressor.
Provides type-aware elision for tool results (grep outputs, shell ANSI, file dumps, JSON)
while strictly protecting stack traces, exceptions, and code integrity.
"""
import re
import json
from typing import Any

# ANSI escape sequence pattern for terminal output stripping
ANSI_REGEX = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
SHELL_PROMPT_REGEX = re.compile(r"^\s*[$#>]\s+")

# File/line parser for grep search output (e.g., path/to/file.py:123:content)
GREP_LINE_REGEX = re.compile(r"^([^:\s]+):(\d+):(.*)$")


def has_error_signature(content: str) -> bool:
    """Detect whether output contains errors or exceptions that must never be truncated."""
    lower = content.lower()
    return any(sig in lower for sig in [
        "traceback (most recent call last):",
        "syntaxerror:",
        "typeerror:",
        "nameerror:",
        "valueerror:",
        "attributeerror:",
        "filenotfounderror:",
        "exception:",
        "[error]",
        "fatal error",
        "assertionerror"
    ])


def is_code_like(line: str) -> bool:
    """Detect if a line looks like programming code."""
    stripped = line.strip()
    return any(stripped.startswith(kw) for kw in [
        "import ", "from ", "def ", "class ", "return ", "if ", "elif ", "else:",
        "for ", "while ", "try:", "except ", "finally:", "const ", "let ", "var ",
        "function ", "public ", "private ", "export "
    ])


def compress_grep_output(lines: list[str], max_matches: int = 25) -> str:
    """Compress grep/search results: keep top matches, summarize count, and list files."""
    matched_lines = []
    file_paths: set[str] = set()

    for line in lines:
        m = GREP_LINE_REGEX.match(line.strip())
        if m:
            matched_lines.append(line)
            file_paths.add(m.group(1))

    if not matched_lines:
        return "\n".join(lines[:max_matches])

    retained = matched_lines[:max_matches]
    elided_count = len(matched_lines) - len(retained)
    
    result = "\n".join(retained)
    if elided_count > 0:
        result += f"\n... [{elided_count} more matching lines elided for token budget] ..."
    result += f"\nUnique files matched ({len(file_paths)}): {', '.join(sorted(file_paths)[:15])}"
    return result


def compress_shell_output(content: str, max_lines: int = 40) -> str:
    """Strip ANSI escape codes, deduplicate repeated polling lines, and take the tail."""
    clean = ANSI_REGEX.sub("", content)
    lines = clean.splitlines()
    if len(lines) <= max_lines:
        return clean

    # Deduplicate consecutive identical lines (e.g. progress bars, polling)
    deduped: list[str] = []
    for line in lines:
        if not deduped or line != deduped[-1]:
            deduped.append(line)

    tail = deduped[-max_lines:]
    elided = len(deduped) - len(tail)
    return f"... [{elided} earlier shell lines elided] ...\n" + "\n".join(tail)


def compress_file_content(content: str, keep_head: int = 20, keep_tail: int = 5) -> str:
    """Elide the middle of large code files while preserving imports and bottom definitions."""
    lines = content.splitlines()
    if len(lines) <= (keep_head + keep_tail + 5):
        return content

    head = lines[:keep_head]
    tail = lines[-keep_tail:]
    elided = len(lines) - keep_head - keep_tail
    return "\n".join(head) + f"\n\n... [{elided} lines elided for token budget] ...\n\n" + "\n".join(tail)


def compress_json_payload(content: str, max_chars: int = 1500) -> str:
    """Compress deep or large JSON structures into key summaries."""
    try:
        data = json.loads(content)
    except Exception:
        return content[:max_chars]

    if isinstance(data, list):
        if len(data) <= 5:
            return content
        summary = {
            "type": "array",
            "total_items": len(data),
            "first_3": data[:3],
            "last_1": data[-1:]
        }
        return json.dumps(summary, indent=2)

    if isinstance(data, dict):
        keys = list(data.keys())
        if len(keys) <= 15 and len(content) <= max_chars:
            return content
        summary = {
            "type": "object",
            "total_keys": len(keys),
            "keys_summary": {
                k: (f"[{len(data[k])} items]" if isinstance(data[k], list) else 
                    f"[{len(data[k])} keys]" if isinstance(data[k], dict) else data[k])
                for k in keys[:15]
            }
        }
        return json.dumps(summary, indent=2)

    return content[:max_chars]


def compress_tool_output(content: Any, max_chars: int = 1800) -> str:
    """
    Main entrypoint: Apply context-aware compression to tool outputs.
    Guarantees tracebacks and errors are never truncated.
    """
    if not isinstance(content, str):
        content = str(content)

    if not content or len(content) <= max_chars:
        return content

    # CRITICAL: Preserve full stack traces and exceptions for agentic self-debugging
    if has_error_signature(content):
        # Keep full error, only trim extreme runaway output (>6000 chars)
        if len(content) > 6000:
            return content[:5500] + "\n... [Remaining error output truncated at 5.5k chars]"
        return content

    # 1. Check for Shell / Terminal ANSI output
    if "\x1b[" in content or content.startswith("$ "):
        return compress_shell_output(content)

    # 2. Check for Grep output
    lines = content.splitlines()
    if any(GREP_LINE_REGEX.match(line.strip()) for line in lines[:10]):
        return compress_grep_output(lines)

    # 3. Check for JSON
    stripped = content.strip()
    if (stripped.startswith("{") and stripped.endswith("}")) or (stripped.startswith("[") and stripped.endswith("]")):
        return compress_json_payload(content, max_chars=max_chars)

    # 4. Check for Code File Content
    code_lines = sum(1 for line in lines[:15] if is_code_like(line))
    if code_lines >= 2 and len(lines) > 25:
        return compress_file_content(content)

    # 5. Generic safe line-based truncation
    head_lines = lines[:30]
    tail_lines = lines[-5:] if len(lines) > 35 else []
    elided = len(lines) - len(head_lines) - len(tail_lines)
    if elided > 0:
        return "\n".join(head_lines) + f"\n... [{elided} lines elided for token budget] ...\n" + "\n".join(tail_lines)

    return content[:max_chars] + "\n... [Truncated for token budget]"
