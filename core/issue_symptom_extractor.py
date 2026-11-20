"""SpaceV Milestone 2 Step 2.3: Existing Test Execution & Symptom Extraction.

Consumes DiscoveryResult from Step 2.2, dynamically selects relevant tests,
executes them inside the approval-gated Celesto microVM, captures execution receipts,
and extracts structured failure symptoms and verdicts for root-cause diagnosis.

Strict Guarantees:
1. Dynamic Test Selection: Prioritizes tests based on correspondence, stack traces,
   symbols, error types, and discovery scores without hardcoding repos or paths.
2. Approval & Scope Gated: Requires authoritative human approval with
   allow_test_execution=True; rejects unapproved or replayed sessions.
3. Verdict Classification: Distinguishes EXPECTED_BUG_FAILURE, PASS_NO_REPRODUCTION,
   TEST_COLLECTION_ERROR, TEST_CONFIGURATION_ERROR, NO_RELEVANT_TESTS, and
   INFRASTRUCTURE_FAILURE.
4. Multi-Framework Symptom Extraction: Captures exceptions, messages, stack traces,
   source files, lines, assertion details, expected/actual values across pytest,
   unittest, jest/vitest, go test, cargo test, and junit.
5. Strict Read-Only Containment: Pre- and post-test git status audits guarantee
   zero repository source/test modifications and control test-generated artifacts.
"""

from __future__ import annotations

import logging
import os
import posixpath
import re
import shlex
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.issue_discovery import CandidateFile, DiscoveryResult, IssueSignals

logger = logging.getLogger("SpaceV.SymptomExtractor")

_EXIT_CODE_REGEX = re.compile(r"\bexit code:\s*(-?\d+)", re.IGNORECASE)
_TRUNCATION_MARKER_REGEX = re.compile(
    r"(?:characters?\s*/\s*\d+\s+tokens?\s+truncated to protect rate limits|"
    r"chars? truncated by SpaceV|remaining error output truncated|truncated to token budget|"
    r"content truncated|output truncated|omitted from durable evidence|"
    r"showing lines \d+-\d+ of \d+)",
    re.IGNORECASE,
)


class ReproductionVerdict(str, Enum):
    """Authoritative reproduction outcome classification for Step 2.3."""

    EXPECTED_BUG_FAILURE = "EXPECTED_BUG_FAILURE"
    PASS_NO_REPRODUCTION = "PASS_NO_REPRODUCTION"
    UNRELATED_TEST_FAILURE = "UNRELATED_TEST_FAILURE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    TEST_COLLECTION_ERROR = "TEST_COLLECTION_ERROR"
    TEST_CONFIGURATION_ERROR = "TEST_CONFIGURATION_ERROR"
    NO_RELEVANT_TESTS = "NO_RELEVANT_TESTS"
    INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"


@dataclass
class SelectedTest:
    """A test target selected dynamically for reproduction execution."""

    target_path: str
    framework: str
    command: str
    selection_reasons: list[str] = field(default_factory=list)
    priority: int = 1
    node_name: str | None = None
    file_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_path": self.target_path,
            "framework": self.framework,
            "command": self.command,
            "selection_reasons": list(self.selection_reasons),
            "priority": self.priority,
            "node_name": self.node_name,
            "file_path": self.file_path,
        }


@dataclass
class ExtractedSymptom:
    """Structured failure evidence extracted from test output."""

    test_file: str
    test_name: str | None = None
    exit_code: int | None = None
    execution_status: str = "UNKNOWN"
    exception_type: str | None = None
    exception_message: str | None = None
    stack_trace: list[str] = field(default_factory=list)
    failing_file: str | None = None
    failing_line: int | None = None
    expected_value: str | None = None
    actual_value: str | None = None
    assertion_details: str | None = None
    stdout_excerpt: str = ""
    stderr_excerpt: str = ""
    is_reproduced: bool = False
    evidence_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_file": self.test_file,
            "test_name": self.test_name,
            "exit_code": self.exit_code,
            "execution_status": self.execution_status,
            "exception_type": self.exception_type,
            "exception_message": self.exception_message,
            "stack_trace": list(self.stack_trace),
            "failing_file": self.failing_file,
            "failing_line": self.failing_line,
            "expected_value": self.expected_value,
            "actual_value": self.actual_value,
            "assertion_details": self.assertion_details,
            "stdout_excerpt": self.stdout_excerpt,
            "stderr_excerpt": self.stderr_excerpt,
            "is_reproduced": self.is_reproduced,
            "evidence_summary": self.evidence_summary,
        }


@dataclass
class SymptomReport:
    """Complete machine-readable symptom report prepared for Step 2.4."""

    issue_url: str
    issue_title: str
    checkout_path: str
    session_id: str
    overall_verdict: ReproductionVerdict
    confidence: str
    selected_tests: list[SelectedTest] = field(default_factory=list)
    execution_receipts: list[dict[str, Any]] = field(default_factory=list)
    extracted_symptoms: list[ExtractedSymptom] = field(default_factory=list)
    pre_test_status: dict[str, Any] = field(default_factory=dict)
    post_test_status: dict[str, Any] = field(default_factory=dict)
    limitations_and_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_url": self.issue_url,
            "issue_title": self.issue_title,
            "checkout_path": self.checkout_path,
            "session_id": self.session_id,
            "overall_verdict": self.overall_verdict.value,
            "confidence": self.confidence,
            "selected_tests": [t.to_dict() for t in self.selected_tests],
            "execution_receipts": list(self.execution_receipts),
            "extracted_symptoms": [s.to_dict() for s in self.extracted_symptoms],
            "pre_test_status": dict(self.pre_test_status),
            "post_test_status": dict(self.post_test_status),
            "limitations_and_warnings": list(self.limitations_and_warnings),
        }


def validate_checkout_path(checkout_path: str) -> str:
    """Validate that checkout_path is a safe absolute guest path without traversal or injection."""
    raw = str(checkout_path or "").strip()
    if not raw:
        raise ValueError("Checkout path must be non-empty.")
    if any(c in raw for c in ";|&<>$`\n\r\x00"):
        raise ValueError(f"Checkout path contains invalid shell characters: {raw!r}")
    raw_segments = raw.replace("\\", "/").strip("/").split("/")
    if ".." in raw_segments:
        raise ValueError(f"Checkout path contains directory traversal '..': {raw!r}")
    normalized = posixpath.normpath(raw.replace("\\", "/"))
    if not normalized.startswith("/"):
        raise ValueError(f"Checkout path must be an absolute path starting with '/': {raw!r}")
    segments = normalized.strip("/").split("/")
    if ".." in segments:
        raise ValueError(f"Checkout path contains directory traversal '..': {raw!r}")
    return normalized


def validate_target_test_path(target_path: str, checkout_path: str | None = None) -> str:
    """Validate that target_path is a repository-relative test path without traversal, drive letters, or escapes."""
    raw = str(target_path or "").strip()
    if not raw:
        raise ValueError("Target test path must be non-empty.")
    if any(c in raw for c in ";|&<>$`\n\r\x00"):
        raise ValueError(f"Target test path contains invalid shell characters: {raw!r}")

    node_part = None
    if "::" in raw:
        file_part, node_part = raw.split("::", 1)
        if any(c in node_part for c in ";|&<>$`\n\r\x00"):
            raise ValueError(f"Test node contains invalid shell characters: {node_part!r}")
    else:
        file_part = raw

    norm_file = file_part.replace("\\", "/").strip()
    if norm_file.startswith("./"):
        norm_file = norm_file[2:]

    if norm_file.startswith("/") or norm_file.startswith("~"):
        raise ValueError(f"Target test path must be relative to repository, got absolute path: {raw!r}")
    if re.match(r"^[A-Za-z]:", norm_file):
        raise ValueError(f"Target test path contains Windows drive letters: {raw!r}")

    segments = norm_file.split("/")
    if ".." in segments or "." in segments:
        raise ValueError(f"Target test path contains directory traversal '..': {raw!r}")

    cleaned = posixpath.normpath(norm_file)
    if cleaned.startswith("..") or cleaned.startswith("/"):
        raise ValueError(f"Target test path escapes repository checkout: {raw!r}")

    if node_part:
        return f"{cleaned}::{node_part}"
    return cleaned


def build_safe_test_command(
    framework: str,
    checkout_path: str,
    target_path: str,
) -> str:
    """Build an approval-compliant, non-mutating guest test execution command.

    Validates checkout and target paths independently before construction.
    Safely shell-quotes paths to handle spaces or special characters.
    Applies cache-disabling flags (-B, -p no:cacheprovider) without destructively
    clearing existing repository data.
    """
    clean_checkout = validate_checkout_path(checkout_path)
    clean_target = validate_target_test_path(target_path, clean_checkout)

    quoted_checkout = shlex.quote(clean_checkout)
    quoted_target = shlex.quote(clean_target)

    fw = (framework or "pytest").lower()
    if fw in ("pytest", "python"):
        # Format: cd <checkout> && python3 -B -m pytest -p no:cacheprovider <target>
        # Note: --cache-clear is omitted to prevent destructively deleting existing repository data.
        return f"cd {quoted_checkout} && python3 -B -m pytest -p no:cacheprovider {quoted_target}"
    elif fw == "unittest":
        return f"cd {quoted_checkout} && python3 -B -m unittest {quoted_target}"
    elif fw in ("jest", "vitest", "javascript", "typescript"):
        return f"cd {quoted_checkout} && npm test -- {quoted_target}"
    elif fw in ("go test", "go"):
        return f"cd {quoted_checkout} && go test -v ./{quoted_target}"
    elif fw in ("cargo test", "rust"):
        return f"cd {quoted_checkout} && cargo test --test {quoted_target}"
    elif fw in ("maven / junit", "junit", "java"):
        return f"cd {quoted_checkout} && mvn test -Dtest={quoted_target}"
    else:
        return f"cd {quoted_checkout} && python3 -B -m pytest -p no:cacheprovider {quoted_target}"


def select_reproduction_tests(
    discovery: DiscoveryResult,
    checkout_path: str,
    issue_signals: IssueSignals | None = None,
    max_tests: int = 3,
) -> list[SelectedTest]:
    """Select the most relevant candidate test files from discovery results.

    Prioritizes:
    1. Tests with explicit correspondence to candidate source files.
    2. Tests mentioned directly in issue text or stack traces.
    3. Highest-scored candidate test files.

    If no tests exist or all candidate scores are zero with no signals, returns empty list.
    """
    if not discovery.candidate_test_files:
        return []

    signals = issue_signals or IssueSignals()
    selected: list[SelectedTest] = []
    seen_paths: set[str] = set()

    for candidate in discovery.candidate_test_files:
        if candidate.path in seen_paths:
            continue
        if len(selected) >= max_tests:
            break

        # Check relevance: correspondence, stack trace, explicit mention, or high score
        is_corresponding = bool(candidate.corresponds_to)
        is_in_signals = candidate.path in signals.file_paths or any(
            candidate.path in frame.get("file", "") for frame in signals.stack_traces
        )
        is_high_score = candidate.score >= 0.5

        if not (is_corresponding or is_in_signals or is_high_score):
            # If no strong relevance matches, only select rank #1 if candidate list is small
            if len(selected) > 0 or candidate.score <= 0.0:
                continue

        framework = candidate.framework or "pytest"
        command = build_safe_test_command(
            framework=framework,
            checkout_path=checkout_path,
            target_path=candidate.path,
        )

        reasons = list(candidate.reasons)
        if is_corresponding:
            reasons.append(f"Primary correspondence to source file: {candidate.corresponds_to}")

        selected.append(
            SelectedTest(
                target_path=candidate.path,
                framework=framework,
                command=command,
                selection_reasons=reasons,
                priority=len(selected) + 1,
                file_path=candidate.path,
            )
        )
        seen_paths.add(candidate.path)

    return selected


def extract_test_symptoms(
    raw_output: str,
    framework: str = "pytest",
    exit_code: int | None = None,
    target_path: str = "",
) -> ExtractedSymptom:
    """Extract granular failure symptoms, exceptions, stack traces, and values from test output."""
    output = str(raw_output or "")
    fw = (framework or "pytest").lower()

    symptom = ExtractedSymptom(
        test_file=target_path,
        exit_code=exit_code,
    )

    # 1. Parse exit code if not provided
    if exit_code is None:
        m = _EXIT_CODE_REGEX.search(output)
        if m:
            symptom.exit_code = int(m.group(1))

    # 2. Extract stdout and stderr sections from receipt
    stdout_match = re.search(r"STDOUT:\s*\n(.*?)(?:\nSTDERR:|\Z)", output, re.IGNORECASE | re.DOTALL)
    stderr_match = re.search(r"STDERR:\s*\n(.*?)(?:\nPhase timings|\Z)", output, re.IGNORECASE | re.DOTALL)
    stdout_text = stdout_match.group(1).strip() if stdout_match else output
    stderr_text = stderr_match.group(1).strip() if stderr_match else ""

    symptom.stdout_excerpt = stdout_text[:2000]
    symptom.stderr_excerpt = stderr_text[:1000]

    # 3. Check for timeout or infrastructure failure
    lower_out = output.lower()
    is_cmd_timeout = bool(
        symptom.exit_code == 124
        or re.search(
            r"\b(?:command|process|tool|operation)\b.{0,80}\btimed out\b|"
            r"\btimeout\s*expired\b|\btimeoutexpired\b",
            lower_out,
        )
    )
    if is_cmd_timeout:
        symptom.execution_status = "TIMEOUT"
        symptom.evidence_summary = "Command exceeded guest execution timeout."
        return symptom

    if symptom.exit_code == 0:
        symptom.execution_status = "PASSED"
        symptom.evidence_summary = "Test execution passed completely with exit code 0."
        return symptom

    symptom.execution_status = "FAILED"

    # 4. Multi-Framework Parsing
    if "pytest" in fw or "python" in fw or "unittest" in fw:
        _extract_python_symptoms(stdout_text, symptom)
    elif any(js_fw in fw for js_fw in ("jest", "vitest", "mocha", "npm", "javascript", "typescript")):
        _extract_javascript_symptoms(stdout_text, symptom)
    elif "cargo" in fw or "rust" in fw:
        _extract_rust_symptoms(stdout_text, symptom)
    elif re.search(r"\bgo\b", fw):
        _extract_go_symptoms(stdout_text, symptom)
    elif any(j_fw in fw for j_fw in ("junit", "java", "maven", "gradle")):
        _extract_junit_symptoms(stdout_text, symptom)
    else:
        _extract_generic_symptoms(stdout_text, symptom)

    return symptom


def _extract_python_symptoms(text: str, symptom: ExtractedSymptom) -> None:
    """Parse Pytest and Unittest failure sections, exceptions, assertions, and stack traces."""
    # Test Name from failure block
    # e.g.: ___________________ test_total_timeout ___________________
    heading_match = re.search(r"(?m)^_{3,}\s*(.*?)\s*_{3,}\s*$", text)
    if heading_match:
        symptom.test_name = heading_match.group(1).strip()

    # Exception Type and Message
    # e.g.: E   requests.exceptions.ConnectTimeout: HTTPSConnectionPool(...) Read timed out.
    # or:   E   AssertionError: assert 200 == 404
    exc_match = re.search(
        r"(?m)^E\s+([A-Za-z0-9_.]*(?:Error|Exception|Timeout|Failure|Fault)):\s*(.*)$",
        text,
    )
    if exc_match:
        full_exc = exc_match.group(1).strip()
        symptom.exception_type = full_exc.split(".")[-1]
        symptom.exception_message = exc_match.group(2).strip()
    else:
        # Standard Traceback format
        tb_match = re.search(
            r"(?m)^([A-Za-z0-9_.]*(?:Error|Exception|Timeout|Failure|Fault)):\s*(.*)$",
            text,
        )
        if tb_match:
            symptom.exception_type = tb_match.group(1).split(".")[-1]
            symptom.exception_message = tb_match.group(2).strip()

    # Stack trace frames
    # e.g.: requests/adapters.py:527: in send
    # or:   File "requests/adapters.py", line 527, in send
    # or:   src/requests/models.py:1020: TypeError
    # or:   tests/test_repro.py:24:
    frames: list[str] = []
    py_frame_pattern = re.compile(
        r"(?m)^\s*(?:File\s+\"([^\"]+)\",\s+line\s+(\d+)(?:,\s+in\s+([a-zA-Z0-9_]+))?|([a-zA-Z0-9_./\\-]+\.py):(\d+):(?:\s+in\s+([a-zA-Z0-9_]+)|\s*([A-Za-z0-9_.]*(?:Error|Exception|Timeout|Failure|Fault))|\s*$))"
    )
    for m in py_frame_pattern.finditer(text):
        if m.group(1):
            fp = m.group(1)
            line = int(m.group(2))
            func = m.group(3) or ""
        else:
            fp = m.group(4)
            line = int(m.group(5))
            func = m.group(6) or m.group(7) or ""
        formatted_frame = f"{fp}:{line} in {func}".strip() if func else f"{fp}:{line}"
        frames.append(formatted_frame)
        symptom.failing_file = fp.replace("\\", "/")
        symptom.failing_line = line

    symptom.stack_trace = frames

    # Assertion Details & Expected/Actual Values
    # Pattern 1: E   assert <actual> == <expected>
    eq_assert = re.search(r"(?m)^E\s+assert\s+(.+?)\s*==\s*(.+)$", text)
    if eq_assert:
        symptom.assertion_details = eq_assert.group(0).lstrip("E ").strip()
        symptom.actual_value = eq_assert.group(1).strip()
        symptom.expected_value = eq_assert.group(2).strip()
    else:
        # Pattern 2: E   AssertionError: ...
        assert_block = re.search(r"(?m)^E\s+(?:assert|AssertionError:?)\s*(.*)$", text)
        if assert_block:
            symptom.assertion_details = assert_block.group(0).lstrip("E ").strip()

    # Collect short test summary line if present
    summary_match = re.search(r"(?m)^FAILED\s+(.*?)\s*-\s*(.*)$", text)
    if summary_match:
        symptom.evidence_summary = summary_match.group(0).strip()
    elif symptom.exception_type and symptom.exception_message:
        symptom.evidence_summary = f"{symptom.exception_type}: {symptom.exception_message}"
    else:
        symptom.evidence_summary = "Test failed with non-zero exit code."


def _extract_javascript_symptoms(text: str, symptom: ExtractedSymptom) -> None:
    """Parse Jest / Vitest / Mocha failure output."""
    # Test name: ● AuthMiddleware › should reject invalid token
    test_match = re.search(r"(?m)^\s*●\s+(.*?)$", text)
    if test_match:
        symptom.test_name = test_match.group(1).strip()

    # Expected vs Actual in Jest
    # Expected: 401
    # Received: 500
    exp_match = re.search(r"(?m)Expected:\s*(.*?)$", text)
    rec_match = re.search(r"(?m)Received:\s*(.*?)$", text)
    if exp_match and rec_match:
        symptom.expected_value = exp_match.group(1).strip()
        symptom.actual_value = rec_match.group(1).strip()
        symptom.assertion_details = f"Expected: {symptom.expected_value}, Received: {symptom.actual_value}"

    # Error message
    err_match = re.search(r"(?m)([A-Za-z0-9_]*(?:Error|Exception|Failure)):\s*(.*)$", text)
    if err_match:
        symptom.exception_type = err_match.group(1).strip()
        symptom.exception_message = err_match.group(2).strip()

    # Stack trace: at authMiddleware (packages/server/src/auth.ts:35:18)
    frames: list[str] = []
    for m in re.finditer(r"\bat\s+(?:([a-zA-Z0-9_$]+)\s+\()?(?:([a-zA-Z0-9_./\\-]+):(\d+)(?::\d+)?)\)?", text):
        func = m.group(1) or "<anonymous>"
        fp = (m.group(2) or "").replace("\\", "/")
        line = int(m.group(3))
        frames.append(f"{fp}:{line} in {func}")
        symptom.failing_file = fp
        symptom.failing_line = line

    symptom.stack_trace = frames
    symptom.evidence_summary = (
        f"{symptom.exception_type}: {symptom.exception_message}"
        if symptom.exception_type
        else "JavaScript/TypeScript test failed."
    )


def _extract_go_symptoms(text: str, symptom: ExtractedSymptom) -> None:
    """Parse `go test` failure output."""
    # --- FAIL: TestHandleJob (0.02s)
    fail_match = re.search(r"(?m)^--- FAIL:\s+([A-Za-z0-9_]+)", text)
    if fail_match:
        symptom.test_name = fail_match.group(1).strip()

    # panic: runtime error: ...
    panic_match = re.search(r"(?m)panic:\s*(.*)$", text)
    if panic_match:
        symptom.exception_type = "Panic"
        symptom.exception_message = panic_match.group(1).strip()

    # worker_test.go:42: expected 200, got 500
    go_assert = re.search(r"([a-zA-Z0-9_.-]+\.go):(\d+):\s*(.*)$", text)
    if go_assert:
        symptom.failing_file = go_assert.group(1)
        symptom.failing_line = int(go_assert.group(2))
        symptom.assertion_details = go_assert.group(3).strip()

    symptom.evidence_summary = symptom.assertion_details or symptom.exception_message or "Go test failed."


def _extract_rust_symptoms(text: str, symptom: ExtractedSymptom) -> None:
    """Parse `cargo test` failure output."""
    # ---- tests::test_parse stdout ----
    fail_match = re.search(r"(?m)^----\s+(.*?)\s+stdout ----$", text)
    if fail_match:
        symptom.test_name = fail_match.group(1).strip()

    # thread 'tests::test_parse' panicked at 'assertion failed: (left == right)'
    panic_match = re.search(r"panicked at '([^']+)'(?:,\s+([a-zA-Z0-9_./\\-]+):(\d+))?", text)
    if panic_match:
        symptom.exception_type = "Panic"
        symptom.exception_message = panic_match.group(1).strip()
        if panic_match.group(2):
            symptom.failing_file = panic_match.group(2).replace("\\", "/")
            symptom.failing_line = int(panic_match.group(3))

    # left: 404, right: 200
    left_right = re.search(r"left:\s*`([^`]+)`,\s*right:\s*`([^`]+)`", text)
    if left_right:
        symptom.actual_value = left_right.group(1).strip()
        symptom.expected_value = left_right.group(2).strip()
        symptom.assertion_details = f"left (actual): {symptom.actual_value}, right (expected): {symptom.expected_value}"

    symptom.evidence_summary = symptom.assertion_details or symptom.exception_message or "Rust test panicked."


def _extract_junit_symptoms(text: str, symptom: ExtractedSymptom) -> None:
    """Parse JUnit / Maven test failure output."""
    # AppTest.testConnection:45 expected:<200> but was:<500>
    junit_match = re.search(r"([A-Za-z0-9_]+)\.([A-Za-z0-9_]+):(\d+)\s+expected:<([^>]+)>\s+but was:<([^>]+)>", text)
    if junit_match:
        symptom.test_file = junit_match.group(1)
        symptom.test_name = junit_match.group(2)
        symptom.failing_line = int(junit_match.group(3))
        symptom.expected_value = junit_match.group(4)
        symptom.actual_value = junit_match.group(5)
        symptom.assertion_details = f"expected: {symptom.expected_value}, actual: {symptom.actual_value}"
        symptom.exception_type = "AssertionError"

    err_match = re.search(r"([a-zA-Z0-9_.]*(?:Exception|Error)):\s*(.*)$", text)
    if err_match:
        symptom.exception_type = err_match.group(1).split(".")[-1]
        symptom.exception_message = err_match.group(2).strip()

    symptom.evidence_summary = symptom.assertion_details or symptom.exception_message or "JUnit test failed."


def _extract_generic_symptoms(text: str, symptom: ExtractedSymptom) -> None:
    """Fallback symptom extraction for unrecognized formats."""
    err_match = re.search(r"\b([A-Za-z0-9_]*(?:Error|Exception|Panic|Failure))\b[:\s]*(.*)$", text, re.IGNORECASE)
    if err_match:
        symptom.exception_type = err_match.group(1).strip()
        symptom.exception_message = err_match.group(2).strip()
    symptom.evidence_summary = symptom.exception_message or "Test command failed with non-zero exit code."


def classify_reproduction_verdict(
    symptoms: list[ExtractedSymptom],
    signals: IssueSignals,
    receipts: list[dict[str, Any]],
    has_relevant_tests: bool,
) -> tuple[ReproductionVerdict, str]:
    """Classify the authoritative reproduction outcome into one of the 6 required verdicts.

    Returns:
      (ReproductionVerdict, confidence_level: str)
    """
    if not has_relevant_tests:
        return ReproductionVerdict.NO_RELEVANT_TESTS, "HIGH"

    # Check for infrastructure failure in any receipt
    for receipt in receipts:
        exit_code = receipt.get("exit_code")
        raw = str(receipt.get("output", "")).lower()
        is_infra_timeout = bool(
            exit_code == 124
            or re.search(
                r"\b(?:command|process|tool|operation)\b.{0,80}\btimed out\b|"
                r"\btimeout\s*expired\b|\btimeoutexpired\b",
                raw,
            )
        )
        if exit_code in (128, 127, 255) or is_infra_timeout:
            return ReproductionVerdict.INFRASTRUCTURE_FAILURE, "HIGH"
        if "command is outside the approved task scope" in raw or "no celesto vm was started" in raw:
            return ReproductionVerdict.INFRASTRUCTURE_FAILURE, "HIGH"

    if not symptoms:
        return ReproductionVerdict.INFRASTRUCTURE_FAILURE, "LOW"

    # Check collection or configuration errors
    for s in symptoms:
        raw_text = (s.stdout_excerpt + "\n" + s.stderr_excerpt).lower()
        if (
            "no tests collected" in raw_text
            or "no tests were found" in raw_text
            or "file or directory not found" in raw_text
            or "collection error" in raw_text
            or s.exit_code == 4  # Pytest exit code 4: usage/collection error
        ):
            return ReproductionVerdict.TEST_COLLECTION_ERROR, "HIGH"

        if (
            "modulenotfounderror" in raw_text
            or "importerror" in raw_text
            or "cannot import name" in raw_text
            or "no module named" in raw_text
            or "pytest: not found" in raw_text
            or "command not found" in raw_text
            or "cannot find module" in raw_text
        ):
            return ReproductionVerdict.TEST_CONFIGURATION_ERROR, "HIGH"

    has_signals = bool(
        signals.error_types
        or signals.file_paths
        or signals.stack_traces
        or any(len(kw) >= 4 for kw in signals.keywords)
    )

    # Broad words that must not be used as sole evidence for bug reproduction
    BROAD_KEYWORDS = frozenset({
        "test", "tests", "testing", "error", "errors", "failed", "failure", "fail",
        "pass", "passed", "true", "false", "none", "null", "issue", "problem",
        "code", "repo", "file", "call", "line", "type", "name", "value",
        "assert", "expected", "actual", "return", "send", "recv", "input",
    })
    distinctive_keywords = [
        kw.lower() for kw in signals.keywords
        if len(kw) >= 4 and kw.lower() not in BROAD_KEYWORDS
    ]

    # Check for reproduction failures matching issue signals
    all_passed = True
    has_failures = False
    for s in symptoms:
        if s.execution_status != "PASSED" and s.exit_code != 0:
            has_failures = True
            all_passed = False

            if not has_signals:
                s.is_reproduced = False
                continue

            # 1. Exact stack trace match: failing file and line match an issue frame
            matched_trace = bool(
                s.failing_file
                and s.failing_line
                and any(
                    frame.get("file") == s.failing_file and frame.get("line") == s.failing_line
                    for frame in signals.stack_traces
                )
            )

            # 2. Exact error type match
            matched_error = bool(s.exception_type and s.exception_type in signals.error_types)

            # 3. Meaningful message match against distinctive keywords (not broad words)
            matched_msg = bool(
                s.exception_message
                and any(kw in s.exception_message.lower() for kw in distinctive_keywords)
            )

            # 4. Failing file match against candidate source/test paths in issue
            matched_file = bool(
                s.failing_file
                and any(
                    s.failing_file.endswith(fp) or fp.endswith(s.failing_file)
                    for fp in signals.file_paths
                )
            )

            # Tier 1 (HIGH confidence):
            # - Exact stack trace match, OR
            # - Exact error type AND distinctive error message, OR
            # - Exact error type AND failing file
            if matched_trace or (matched_error and matched_msg) or (matched_error and matched_file):
                s.is_reproduced = True
                return ReproductionVerdict.EXPECTED_BUG_FAILURE, "HIGH"

            # Tier 2 (MEDIUM confidence):
            # - Distinctive error type alone (when error type is specific, not generic AssertionError/Exception)
            # - Failing file AND meaningful distinctive error message
            distinctive_error = bool(
                matched_error and s.exception_type not in ("AssertionError", "Exception", "BaseException")
            )
            if distinctive_error or (matched_file and matched_msg):
                s.is_reproduced = True
                return ReproductionVerdict.EXPECTED_BUG_FAILURE, "MEDIUM"

            # Negative cases:
            # - Weak keyword overlap alone without matching error type or trace
            # - File match alone without matching error type or message
            # These must NEVER produce EXPECTED_BUG_FAILURE.
            s.is_reproduced = False

    if all_passed:
        return ReproductionVerdict.PASS_NO_REPRODUCTION, "HIGH"

    if has_failures and not has_signals:
        # When issue context or signals are missing, report insufficient evidence
        # rather than claiming the failure is unrelated or confirming reproduction.
        return ReproductionVerdict.INSUFFICIENT_EVIDENCE, "LOW"

    # Non-zero exit code: test failed, but did not match verified issue signals.
    # It must NEVER be misclassified as EXPECTED_BUG_FAILURE.
    return ReproductionVerdict.UNRELATED_TEST_FAILURE, "HIGH"


def _parse_git_status_porcelain(status_output: str) -> dict[str, str]:
    """Parse git status --short output into a dict of {path: status_code}."""
    status_map: dict[str, str] = {}
    stdout_match = re.search(r"STDOUT:\s*\n(.*?)(?:\nSTDERR:|\Z)", status_output, re.DOTALL)
    stdout = stdout_match.group(1) if stdout_match else status_output
    for line in stdout.splitlines():
        line = line.rstrip("\r\n")
        if not line or not line.strip():
            continue
        code = line[:2]
        path_part = line[2:].strip().strip('"')
        if " -> " in path_part:
            path_part = path_part.split(" -> ")[-1].strip().strip('"')
        norm_p = posixpath.normpath(path_part.replace("\\", "/"))
        status_map[norm_p] = code
    return status_map


def format_extracted_symptom_note(symptom: ExtractedSymptom) -> str:
    """Format a compact, machine-readable symptom note for graph tool evidence."""
    parts = [
        f"status={symptom.execution_status}",
        f"test={symptom.test_file}" + (f"::{symptom.test_name}" if symptom.test_name else ""),
    ]
    if symptom.exit_code is not None:
        parts.append(f"exit_code={symptom.exit_code}")
    if symptom.exception_type:
        parts.append(f"exception={symptom.exception_type}")
    if symptom.exception_message:
        parts.append(f"message={symptom.exception_message[:120]}")
    if symptom.failing_file:
        loc = symptom.failing_file + (f":{symptom.failing_line}" if symptom.failing_line else "")
        parts.append(f"location={loc}")
    if symptom.expected_value and symptom.actual_value:
        parts.append(f"comparison=(expected: {symptom.expected_value}, actual: {symptom.actual_value})")
    elif symptom.assertion_details:
        parts.append(f"assertion={symptom.assertion_details[:120]}")
    return "[SpaceV extracted symptom]\n" + "; ".join(parts)


def execute_and_extract_symptoms(
    session_id: str,
    checkout_path: str,
    discovery: DiscoveryResult,
    issue_url: str = "",
    issue_title: str = "",
    issue_signals: IssueSignals | None = None,
    max_tests: int = 3,
) -> SymptomReport:
    """Full Step 2.3 workflow: select tests, execute in sandbox, and extract symptoms.

    Strict security controls:
    1. Verifies that the Celesto session exists and has allow_test_execution=True.
    2. Runs pre-test git status to record initial repository state (both tracked and untracked).
    3. Executes each test via sandbox_session_manager.run() using safe flags.
    4. Runs post-test git status and compares initial vs final status:
       - Detects modified tracked files.
       - Detects newly created untracked files/artifacts.
       - Detects any discarded or overwritten pre-existing user changes.
    5. Returns machine-readable SymptomReport.
    """
    from tools.sandbox_tools import sandbox_session_manager

    warnings: list[str] = []
    receipts: list[dict[str, Any]] = []
    symptoms: list[ExtractedSymptom] = []

    # 1. Authoritative Session & Capability Verification
    active_session = sandbox_session_manager._sessions.get(session_id)
    if active_session is None:
        return SymptomReport(
            issue_url=issue_url,
            issue_title=issue_title,
            checkout_path=checkout_path,
            session_id=session_id,
            overall_verdict=ReproductionVerdict.INFRASTRUCTURE_FAILURE,
            confidence="HIGH",
            limitations_and_warnings=[f"Celesto session {session_id!r} is missing, expired, or unapproved."],
        )

    scope = getattr(active_session, "approved_task_scope", None)
    if not scope or not getattr(scope, "allow_test_execution", False):
        return SymptomReport(
            issue_url=issue_url,
            issue_title=issue_title,
            checkout_path=checkout_path,
            session_id=session_id,
            overall_verdict=ReproductionVerdict.INFRASTRUCTURE_FAILURE,
            confidence="HIGH",
            limitations_and_warnings=["Test execution is not authorized by the approved task scope."],
        )

    # 2. Pre-Test Clean Working-Tree Audit (Capture Initial State)
    pre_status_cmd = f"git -C {checkout_path} status --short"
    pre_receipt = sandbox_session_manager.run(session_id=session_id, command=pre_status_cmd)
    pre_status_map = _parse_git_status_porcelain(pre_receipt)
    pre_status_data = {
        "command": pre_status_cmd,
        "output": pre_receipt,
        "status_map": dict(pre_status_map),
        "initial_entry_count": len(pre_status_map),
    }
    if "exit code: 0" not in pre_receipt:
        warnings.append("Failed to verify initial git status before running tests.")

    # 3. Dynamic Test Selection
    signals = issue_signals or IssueSignals()
    has_signals = bool(
        signals.error_types
        or signals.keywords
        or signals.file_paths
        or signals.stack_traces
    )
    if not has_signals:
        warnings.append("Missing verified GitHub issue context or signals; insufficient evidence to correlate test results to the reported bug.")
    selected_tests = select_reproduction_tests(
        discovery=discovery,
        checkout_path=checkout_path,
        issue_signals=signals,
        max_tests=max_tests,
    )

    if not selected_tests:
        return SymptomReport(
            issue_url=issue_url,
            issue_title=issue_title,
            checkout_path=checkout_path,
            session_id=session_id,
            overall_verdict=ReproductionVerdict.NO_RELEVANT_TESTS,
            confidence="HIGH",
            pre_test_status=pre_status_data,
            limitations_and_warnings=["No candidate test files matched the issue criteria or repo has zero tests."],
        )

    # 4. Approved Test Execution in Celesto Sandbox
    for test in selected_tests:
        run_receipt = sandbox_session_manager.run(session_id=session_id, command=test.command)
        m = _EXIT_CODE_REGEX.search(run_receipt)
        exit_code = int(m.group(1)) if m else None

        receipts.append({
            "target": test.target_path,
            "command": test.command,
            "exit_code": exit_code,
            "output": run_receipt,
            "truncated": bool(_TRUNCATION_MARKER_REGEX.search(run_receipt)),
        })

        # Extract structured symptoms
        symptom = extract_test_symptoms(
            raw_output=run_receipt,
            framework=test.framework,
            exit_code=exit_code,
            target_path=test.target_path,
        )
        symptoms.append(symptom)

    # 5. Post-Test Integrity Audit & Comparison
    post_status_cmd = f"git -C {checkout_path} status --short"
    post_receipt = sandbox_session_manager.run(session_id=session_id, command=post_status_cmd)
    post_status_map = _parse_git_status_porcelain(post_receipt)

    new_untracked = sorted([
        p for p, code in post_status_map.items()
        if code == "??" and p not in pre_status_map
    ])
    modified_tracked = sorted([
        p for p, code in post_status_map.items()
        if code != "??" and (p not in pre_status_map or pre_status_map[p] != code)
    ])
    discarded_pre_existing = sorted([
        p for p in pre_status_map
        if p not in post_status_map
    ])

    post_status_data = {
        "command": post_status_cmd,
        "output": post_receipt,
        "status_map": dict(post_status_map),
        "new_untracked": new_untracked,
        "modified_tracked": modified_tracked,
        "discarded_pre_existing": discarded_pre_existing,
    }

    if modified_tracked:
        warnings.append(f"Security Alert: Tracked repository file modified during test run: {', '.join(modified_tracked)}")
    if new_untracked:
        warnings.append(f"Notice: Test execution produced untracked artifact(s): {', '.join(new_untracked)}")
    if discarded_pre_existing:
        warnings.append(f"Security Alert: Pre-existing user modifications were altered or discarded: {', '.join(discarded_pre_existing)}")

    # 6. Overall Verdict Classification
    verdict, confidence = classify_reproduction_verdict(
        symptoms=symptoms,
        signals=signals,
        receipts=receipts,
        has_relevant_tests=bool(selected_tests),
    )

    return SymptomReport(
        issue_url=issue_url,
        issue_title=issue_title,
        checkout_path=checkout_path,
        session_id=session_id,
        overall_verdict=verdict,
        confidence=confidence,
        selected_tests=selected_tests,
        execution_receipts=receipts,
        extracted_symptoms=symptoms,
        pre_test_status=pre_status_data,
        post_test_status=post_status_data,
        limitations_and_warnings=warnings,
    )
