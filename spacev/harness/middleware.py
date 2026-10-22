"""
SpaceV Harnessing Subsystem: In-the-Loop Tool Middleware & Observation Sanitizer.
Engineered from Harness² (Google LLC 2026) plugin & middleware architecture.
"""

from __future__ import annotations


class ObservationSanitizerMiddleware:
    """
    Acts inside the tool execution loop to sanitize and truncate noisy observations
    before they can crowd and degrade the LLM context window.
    """

    def __init__(self, max_chars: int = 2500, max_lines: int = 60):
        self.max_chars = max_chars
        self.max_lines = max_lines

    def sanitize(self, tool_name: str, raw_output: str) -> tuple[str, bool]:
        """
        Returns (sanitized_output, was_truncated).
        """
        if not raw_output:
            return "", False

        lines = raw_output.splitlines()
        truncated = False

        # 1. Truncate repetitive line patterns (e.g., progress bars, repeated logs)
        cleaned_lines = []
        prev_line = None
        repeat_count = 0

        for line in lines:
            if line == prev_line:
                repeat_count += 1
                if repeat_count < 3:
                    cleaned_lines.append(line)
                elif repeat_count == 3:
                    cleaned_lines.append("... [Repeated lines suppressed] ...")
            else:
                repeat_count = 0
                cleaned_lines.append(line)
                prev_line = line

        # 2. Line count capping
        if len(cleaned_lines) > self.max_lines:
            head = cleaned_lines[: self.max_lines // 2]
            tail = cleaned_lines[-(self.max_lines // 2) :]
            omitted = len(cleaned_lines) - len(head) - len(tail)
            cleaned_lines = head + [f"\n... [{omitted} lines omitted for context efficiency] ...\n"] + tail
            truncated = True

        joined = "\n".join(cleaned_lines)

        # 3. Byte/Character capping
        if len(joined) > self.max_chars:
            omitted_chars = len(joined) - self.max_chars
            joined = joined[: self.max_chars] + f"\n... [{omitted_chars} characters truncated] ..."
            truncated = True

        return joined, truncated
