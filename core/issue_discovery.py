"""Dynamic source and test discovery for the generic GitHub Issue Solver Agent.

Step 2.2 guarantees:
1. Dynamic repository inspection across flat, standard, nested, and monorepo layouts.
2. Signal extraction from untrusted issue text (paths, stack traces, symbols, keywords).
3. Test discovery across supported languages (Python, JS/TS, Go, Rust, Java).
4. Deterministic relevance ranking with correspondence alignment and audit reasons.
5. Robust handling of edge cases (zero tests, large repos, polyglot projects).
6. Strict read-only boundary enforcement (no traversals, escapes, writes, or execution).
"""

from __future__ import annotations

import logging
import os
import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("SpaceV.IssueDiscovery")

MAX_FILES_SCANNED = 10_000
MAX_CANDIDATES_RETURNED = 15

# Common directory trees to ignore during repository inspection
IGNORED_DIR_NAMES = frozenset({
    ".git",
    "node_modules",
    "vendor",
    "venv",
    ".venv",
    "env",
    ".env",
    "dist",
    "build",
    "target",
    "bin",
    "obj",
    "out",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    ".nox",
    "coverage",
    ".coverage",
    "htmlcov",
    ".idea",
    ".vscode",
    ".next",
    ".nuxt",
    ".output",
    "bower_components",
    "bundle",
    ".bundle",
})

IGNORED_FILE_EXTENSIONS = frozenset({
    ".min.js",
    ".min.css",
    ".map",
    ".lock",
    ".pyc",
    ".pyo",
    ".class",
    ".o",
    ".obj",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".zip",
    ".tar",
    ".gz",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
})

LANGUAGE_EXTENSIONS: dict[str, str] = {
    ".py": "Python",
    ".pyi": "Python",
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".mts": "TypeScript",
    ".cts": "TypeScript",
    ".tsx": "TypeScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".hpp": "C++",
    ".hxx": "C++",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".scala": "Scala",
    ".sh": "Shell",
    ".bash": "Shell",
}

STOP_WORDS = frozenset({
    "the", "and", "with", "this", "that", "from", "issue", "bug", "error",
    "expected", "actual", "version", "when", "what", "where", "how", "why",
    "does", "not", "cannot", "failed", "failure", "fail", "reproduce",
    "reproduction", "steps", "details", "problem", "behavior", "using",
    "please", "help", "thanks", "test", "tests", "testing", "file", "code",
    "repo", "repository", "true", "false", "none", "null", "undefined",
    "some", "more", "also", "then", "into", "over", "under", "after", "before",
})


@dataclass
class CandidateFile:
    """Ranked candidate file discovered during repository analysis."""

    path: str
    score: float
    reasons: list[str] = field(default_factory=list)
    language: str = "unknown"
    framework: str | None = None
    corresponds_to: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "path": self.path,
            "score": round(self.score, 3),
            "reasons": list(self.reasons),
            "language": self.language,
        }
        if self.framework:
            d["framework"] = self.framework
        if self.corresponds_to:
            d["corresponds_to"] = self.corresponds_to
        return d


@dataclass
class IssueSignals:
    """Signals parsed from untrusted issue text for candidate file matching."""

    file_paths: list[str] = field(default_factory=list)
    stack_traces: list[dict[str, Any]] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    error_types: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_paths": list(self.file_paths),
            "stack_traces": [dict(f) for f in self.stack_traces],
            "symbols": list(self.symbols),
            "error_types": list(self.error_types),
            "keywords": list(self.keywords),
        }


@dataclass
class DiscoveryResult:
    """Structured result of dynamic source and test file discovery."""

    candidate_source_files: list[CandidateFile] = field(default_factory=list)
    candidate_test_files: list[CandidateFile] = field(default_factory=list)
    detected_languages: list[str] = field(default_factory=list)
    detected_frameworks: list[str] = field(default_factory=list)
    query_signals: dict[str, Any] = field(default_factory=dict)
    limitations_and_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_source_files": [f.to_dict() for f in self.candidate_source_files],
            "candidate_test_files": [f.to_dict() for f in self.candidate_test_files],
            "detected_languages": list(self.detected_languages),
            "detected_frameworks": list(self.detected_frameworks),
            "query_signals": dict(self.query_signals),
            "limitations_and_warnings": list(self.limitations_and_warnings),
        }


def sanitize_repository_path(path: str, repo_root: Path | None = None) -> str | None:
    """Normalize and validate that a path is strictly inside the repository boundary.

    Rejects absolute paths, parent traversals (..), drive letters, and symlinks
    escaping the repository root.
    """
    raw = str(path or "").strip().replace("\\", "/")
    if not raw:
        return None
    if raw.startswith("./"):
        raw = raw[2:]
    if raw.startswith("/") or raw.startswith("~") or re.match(r"^[a-zA-Z]:", raw):
        return None
    segments = raw.split("/")
    if ".." in segments or "." in segments or not all(segments):
        return None
    cleaned = posixpath.normpath(raw)
    if cleaned.startswith("..") or cleaned.startswith("/"):
        return None

    if repo_root is not None:
        try:
            full_path = (repo_root / cleaned).resolve()
            full_path.relative_to(repo_root.resolve())
        except (ValueError, OSError):
            return None

    return cleaned


def is_ignored_path(path: str) -> bool:
    """Check if a path falls into an ignored build, vendor, or cache directory."""
    normalized = path.replace("\\", "/").strip().lower()
    parts = normalized.split("/")
    if any(part in IGNORED_DIR_NAMES for part in parts[:-1]):
        return True
    filename = parts[-1]
    if any(filename.endswith(ext) for ext in IGNORED_FILE_EXTENSIONS):
        return True
    return False


def is_test_file_path(path: str) -> bool:
    """Determine whether a repository-relative path represents a test file."""
    normalized = path.replace("\\", "/").strip().strip('"')
    if normalized.startswith("./"):
        normalized = normalized[2:]
    lower = normalized.lower()
    parts = lower.split("/")
    filename = parts[-1]
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    ext = ("." + filename.rsplit(".", 1)[1]) if "." in filename else ""

    test_dir_markers = {"test", "tests", "testing", "spec", "specs", "__tests__", "__test__", "t"}
    in_test_dir = any(part in test_dir_markers for part in parts[:-1])

    if ext in {".py", ".pyi"}:
        if filename.startswith("test_") or filename.endswith("_test.py"):
            return True
        if in_test_dir and (filename.startswith("test") or stem.endswith("test")):
            return True
        if in_test_dir and filename.endswith(".py") and not filename.startswith("__"):
            return True

    if ext in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
        if ".test." in filename or ".spec." in filename:
            return True
        if filename.startswith("test_") or filename.startswith("test-") or filename.endswith("_test" + ext):
            return True
        if in_test_dir and ext in {".js", ".jsx", ".ts", ".tsx"}:
            return True

    if ext == ".go" and filename.endswith("_test.go"):
        return True

    if ext == ".rs":
        if filename.endswith("_test.rs") or filename.startswith("test_"):
            return True
        if in_test_dir and filename.endswith(".rs"):
            return True

    if ext in {".java", ".kt"}:
        if (
            stem.endswith("Test")
            or stem.endswith("Tests")
            or stem.endswith("TestCase")
            or stem.startswith("Test")
        ):
            return True
        if in_test_dir and (stem.endswith("test") or "test" in stem):
            return True

    if ext == ".rb" and (
        filename.startswith("test_") or filename.endswith("_test.rb") or filename.endswith("_spec.rb")
    ):
        return True

    if ext in {".c", ".cpp", ".cc", ".cxx"} and in_test_dir and "test" in filename:
        return True

    return False


def is_source_file_path(path: str) -> bool:
    """Determine whether a path is a candidate source file (not a test, build artifact, or vendor file)."""
    normalized = path.replace("\\", "/").strip().strip('"')
    if normalized.startswith("./"):
        normalized = normalized[2:]
    lower = normalized.lower()

    if is_ignored_path(lower):
        return False
    if is_test_file_path(normalized):
        return False

    ext = ("." + lower.rsplit(".", 1)[1]) if "." in lower else ""
    return ext in LANGUAGE_EXTENSIONS


def detect_file_language(path: str) -> str:
    """Return the programming language name associated with the file extension."""
    lower = path.replace("\\", "/").lower()
    ext = ("." + lower.rsplit(".", 1)[1]) if "." in lower else ""
    return LANGUAGE_EXTENSIONS.get(ext, "unknown")


def detect_test_framework(test_path: str, repo_files: list[str]) -> str | None:
    """Infer the test framework for a candidate test file based on conventions and repo configs."""
    lower_path = test_path.replace("\\", "/").lower()
    ext = ("." + lower_path.rsplit(".", 1)[1]) if "." in lower_path else ""
    repo_files_lower = {f.replace("\\", "/").lower() for f in repo_files}

    if ext in {".py", ".pyi"}:
        if any(
            f in repo_files_lower
            for f in ("pytest.ini", "pyproject.toml", "conftest.py", "setup.cfg", "tox.ini")
        ):
            return "pytest"
        return "pytest"

    if ext in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
        if any("jest.config" in f for f in repo_files_lower):
            return "jest"
        if any("vitest.config" in f for f in repo_files_lower):
            return "vitest"
        if any("playwright.config" in f for f in repo_files_lower):
            return "playwright"
        if any("cypress.config" in f for f in repo_files_lower):
            return "cypress"
        if any("mocha" in f for f in repo_files_lower):
            return "mocha"
        return "jest"

    if ext == ".go":
        return "go test"

    if ext == ".rs":
        return "cargo test"

    if ext in {".java", ".kt"}:
        if any("pom.xml" in f for f in repo_files_lower):
            return "maven / junit"
        if any("build.gradle" in f for f in repo_files_lower):
            return "gradle / junit"
        return "junit"

    return None


def extract_issue_signals(title: str, body: str) -> IssueSignals:
    """Extract candidate file paths, stack traces, symbols, errors, and keywords from issue text."""
    combined = f"{title}\n{body}"
    signals = IssueSignals()

    # 1. Explicit file paths
    # Matches patterns like src/foo/bar.py or httpx/_client.py or tests/test_timeout.ts
    path_pattern = re.compile(
        r"(?:^|[\s\"'`(\[])([a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.-]+)+\.(?:py|js|jsx|ts|tsx|go|rs|java|c|cpp|h|hpp|rb|php|cs))\b"
    )
    for m in path_pattern.finditer(combined):
        raw_p = m.group(1).strip()
        sanitized = sanitize_repository_path(raw_p)
        if sanitized and not sanitized.startswith("github.com/") and sanitized not in signals.file_paths:
            signals.file_paths.append(sanitized)

    # 2. Stack traces and error traces
    # Python: File "foo/bar.py", line 123, in send
    py_trace = re.compile(r'File\s+"([^"]+)",\s+line\s+(\d+)(?:,\s+in\s+([a-zA-Z0-9_]+))?')
    for m in py_trace.finditer(combined):
        fp = m.group(1).replace("\\", "/").strip()
        # strip guest prefixes like /tmp/.../
        if "/tmp/" in fp:
            fp = fp.split("/tmp/", 1)[1]
            parts = fp.split("/", 1)
            fp = parts[1] if len(parts) > 1 else fp
        sanitized = sanitize_repository_path(fp)
        func = m.group(3) or ""
        frame = {
            "file": sanitized or fp,
            "line": int(m.group(2)),
            "function": func,
        }
        signals.stack_traces.append(frame)
        if sanitized and sanitized not in signals.file_paths:
            signals.file_paths.append(sanitized)
        if func and func not in STOP_WORDS and len(func) >= 3 and func not in signals.symbols:
            signals.symbols.append(func)

    # Node / JS: at Class.method (src/foo.ts:12:34) or at src/foo.js:12:34
    js_trace = re.compile(r'\bat\s+(?:([a-zA-Z0-9_$]+)\s+\()?(?:([a-zA-Z0-9_./\\-]+):(\d+)(?::\d+)?)\)?')
    for m in js_trace.finditer(combined):
        fp = (m.group(2) or "").replace("\\", "/").strip()
        if "/tmp/" in fp:
            fp = fp.split("/tmp/", 1)[1]
            parts = fp.split("/", 1)
            fp = parts[1] if len(parts) > 1 else fp
        sanitized = sanitize_repository_path(fp)
        if sanitized:
            func = m.group(1) or ""
            frame = {
                "file": sanitized,
                "line": int(m.group(3)),
                "function": func,
            }
            signals.stack_traces.append(frame)
            if sanitized not in signals.file_paths:
                signals.file_paths.append(sanitized)
            if func and func not in STOP_WORDS and len(func) >= 3 and func not in signals.symbols:
                signals.symbols.append(func)

    # 3. Error types
    err_pattern = re.compile(r"\b([A-Z][a-zA-Z0-9]*(?:Error|Exception|Panic|Failure|Fault|Timeout))\b")
    for m in err_pattern.finditer(combined):
        err = m.group(1)
        if err not in signals.error_types and len(err) > 4:
            signals.error_types.append(err)

    # 4. Code symbols
    # Dot-notation method / attribute invocations: Client.send or obj.method
    dot_pattern = re.compile(r"\b([a-zA-Z][a-zA-Z0-9_]*)\.([a-zA-Z][a-zA-Z0-9_]*)\b")
    for m in dot_pattern.finditer(combined):
        s1, s2 = m.group(1), m.group(2)
        for s in (s1, s2):
            if len(s) >= 3 and s not in STOP_WORDS and s not in signals.symbols:
                signals.symbols.append(s)

    # Backticked code tokens: `Client.get` -> Client, get
    backtick_pattern = re.compile(r"`([a-zA-Z0-9_.]+)`")
    for m in backtick_pattern.finditer(combined):
        token = m.group(1).strip()
        for subtoken in token.split("."):
            if len(subtoken) >= 3 and subtoken not in STOP_WORDS and subtoken not in signals.symbols:
                signals.symbols.append(subtoken)

    # PascalCase symbols (classes, types)
    pascal_pattern = re.compile(r"\b([A-Z][a-zA-Z0-9]{2,})\b")
    for m in pascal_pattern.finditer(combined):
        sym = m.group(1)
        if sym not in STOP_WORDS and sym not in signals.error_types and sym not in signals.symbols:
            signals.symbols.append(sym)

    # snake_case / camelCase function/variable symbols
    ident_pattern = re.compile(r"\b([a-z0-9]+(?:_[a-z0-9]+)+)\b")
    for m in ident_pattern.finditer(combined):
        sym = m.group(1)
        if sym not in STOP_WORDS and len(sym) >= 4 and sym not in signals.symbols:
            signals.symbols.append(sym)

    # 5. Domain keywords from title and body
    # Tokenize words >= 3 chars, letters only
    words = re.findall(r"\b[a-zA-Z]{3,}\b", title.lower())
    for w in words:
        if w not in STOP_WORDS and w not in signals.keywords:
            signals.keywords.append(w)

    body_words = re.findall(r"\b[a-zA-Z]{3,}\b", body.lower())
    for w in body_words:
        if w not in STOP_WORDS and w not in signals.keywords:
            signals.keywords.append(w)
        if len(signals.keywords) >= 30:
            break

    return signals


def _compute_file_score(
    rel_path: str,
    is_test: bool,
    signals: IssueSignals,
) -> tuple[float, list[str]]:
    """Compute deterministic relevance score and human-readable audit reasons for a file."""
    score = 0.0
    reasons: list[str] = []
    norm_path = rel_path.replace("\\", "/").lower()
    parts = norm_path.split("/")
    filename = parts[-1]
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    # Remove test_ or _test prefixes/suffixes for clean matching
    clean_stem = re.sub(r"^test[_-]|[-_]test$", "", stem)

    # 1. Stack trace match (highest priority)
    for frame in signals.stack_traces:
        frame_file = frame.get("file", "").lower()
        if frame_file and (frame_file == norm_path or norm_path.endswith("/" + frame_file) or frame_file.endswith("/" + norm_path)):
            lineno = frame.get("line")
            score += 1.5
            reasons.append(f"Directly referenced in stack trace (line {lineno})")
            break

    # 2. Explicit path in issue text
    for ep in signals.file_paths:
        ep_lower = ep.lower()
        if ep_lower == norm_path or norm_path.endswith("/" + ep_lower) or ep_lower.endswith("/" + norm_path):
            if "Directly referenced in stack trace" not in " ".join(reasons):
                score += 1.2
                reasons.append("Explicitly mentioned in issue text")
            break

    # 3. Stem exact match against symbols or error names
    all_target_symbols = signals.symbols + signals.error_types
    for sym in all_target_symbols:
        sym_lower = sym.lower()
        if clean_stem == sym_lower or stem == sym_lower:
            score += 0.6
            reasons.append(f"File stem '{stem}' matches issue symbol '{sym}'")
            break

    # 4. Symbol substring in path
    matched_syms = 0
    for sym in all_target_symbols:
        sym_lower = sym.lower()
        if len(sym_lower) >= 4 and sym_lower in norm_path:
            score += 0.25
            matched_syms += 1
            if matched_syms <= 3:
                reasons.append(f"Path matches issue symbol '{sym}'")
            if matched_syms >= 4:
                break

    # 5. Keyword token overlap with path segments and stem
    path_tokens = set(re.split(r"[/_.-]+", norm_path))
    kw_overlap = [kw for kw in signals.keywords if kw in path_tokens]
    if kw_overlap:
        kw_score = min(0.4, len(kw_overlap) * 0.1)
        score += kw_score
        preview = ", ".join(kw_overlap[:3])
        reasons.append(f"Path contains keyword(s): {preview}")

    return round(score, 3), reasons


def discover_repository_targets(
    repo_input: list[str] | Path | str,
    issue_title: str = "",
    issue_body: str = "",
    max_candidates: int = MAX_CANDIDATES_RETURNED,
) -> DiscoveryResult:
    """Dynamically discover and rank candidate source and test files related to an issue.

    Parameters:
      repo_input: Either a list of repository-relative path strings or a Path/str to a cloned repo directory.
      issue_title: Untrusted GitHub issue title.
      issue_body: Untrusted GitHub issue description/body.
      max_candidates: Maximum candidate files to return per category.

    Returns:
      DiscoveryResult containing candidate source files, candidate test files,
      detected languages/frameworks, extracted signals, and warnings.
    """
    warnings: list[str] = []
    raw_files: list[str] = []

    # 1. Acquire and sanitize file paths
    if isinstance(repo_input, (str, Path)) and (os.path.isdir(str(repo_input))):
        scanned_files, scan_warnings = _scan_directory_files(Path(repo_input), MAX_FILES_SCANNED)
        raw_files = scanned_files
        warnings.extend(scan_warnings)
    elif isinstance(repo_input, list):
        if len(repo_input) > MAX_FILES_SCANNED:
            warnings.append(
                f"Repository contains {len(repo_input)} files; capped inspection to first {MAX_FILES_SCANNED} files."
            )
            repo_input = repo_input[:MAX_FILES_SCANNED]
        for item in repo_input:
            sanitized = sanitize_repository_path(str(item))
            if sanitized:
                raw_files.append(sanitized)
            elif item and any(c in str(item) for c in ("..", ":", "~")):
                warnings.append(f"Rejected invalid or out-of-boundary path: {item!r}")
    else:
        # String representing newline-separated files or missing dir
        text = str(repo_input or "").strip()
        if "\n" in text or text.endswith((".py", ".js", ".ts", ".go", ".rs", ".java")):
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            for item in lines[:MAX_FILES_SCANNED]:
                sanitized = sanitize_repository_path(item)
                if sanitized:
                    raw_files.append(sanitized)
        else:
            warnings.append(f"Repository input could not be resolved as a directory or path list: {repo_input!r}")

    # Deduplicate while preserving order
    seen_paths: set[str] = set()
    valid_paths: list[str] = []
    for p in raw_files:
        if p not in seen_paths and not is_ignored_path(p):
            seen_paths.add(p)
            valid_paths.append(p)

    # 2. Extract signals from issue text
    signals = extract_issue_signals(issue_title, issue_body)

    # 3. Partition into source vs test files and detect languages/frameworks
    source_candidates_raw: list[tuple[str, float, list[str]]] = []
    test_candidates_raw: list[tuple[str, float, list[str]]] = []
    detected_languages_set: set[str] = set()
    detected_frameworks_set: set[str] = set()

    for path in valid_paths:
        lang = detect_file_language(path)
        if lang != "unknown":
            detected_languages_set.add(lang)

        if is_test_file_path(path):
            score, reasons = _compute_file_score(path, is_test=True, signals=signals)
            test_candidates_raw.append((path, score, reasons))
            fw = detect_test_framework(path, valid_paths)
            if fw:
                detected_frameworks_set.add(fw)
        elif is_source_file_path(path):
            score, reasons = _compute_file_score(path, is_test=False, signals=signals)
            source_candidates_raw.append((path, score, reasons))

    # 4. Calculate Test-to-Source and Source-to-Test Correspondence
    source_by_clean_stem: dict[str, list[str]] = {}
    for p, _, _ in source_candidates_raw:
        stem = p.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
        clean = re.sub(r"^test[_-]|[-_]test$", "", stem)
        source_by_clean_stem.setdefault(clean, []).append(p)

    test_by_clean_stem: dict[str, list[str]] = {}
    for p, _, _ in test_candidates_raw:
        stem = p.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
        clean = re.sub(r"^test[_-]|[-_]test$", "", stem)
        test_by_clean_stem.setdefault(clean, []).append(p)

    # Build final CandidateFile objects
    candidate_sources: list[CandidateFile] = []
    for path, score, reasons in source_candidates_raw:
        stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
        clean = re.sub(r"^test[_-]|[-_]test$", "", stem)
        corresponds = None
        if clean in test_by_clean_stem:
            matching_test = test_by_clean_stem[clean][0]
            corresponds = matching_test
            score += 0.35
            reasons.append(f"Corresponds to candidate test file '{matching_test}'")

        candidate_sources.append(
            CandidateFile(
                path=path,
                score=round(score, 3),
                reasons=reasons or ["Repository source file (low keyword overlap)"],
                language=detect_file_language(path),
                corresponds_to=corresponds,
            )
        )

    candidate_tests: list[CandidateFile] = []
    for path, score, reasons in test_candidates_raw:
        stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
        clean = re.sub(r"^test[_-]|[-_]test$", "", stem)
        corresponds = None
        if clean in source_by_clean_stem:
            matching_source = source_by_clean_stem[clean][0]
            corresponds = matching_source
            score += 0.5
            reasons.append(f"Corresponds to candidate source file '{matching_source}'")

        candidate_tests.append(
            CandidateFile(
                path=path,
                score=round(score, 3),
                reasons=reasons or ["Repository test file (low keyword overlap)"],
                language=detect_file_language(path),
                framework=detect_test_framework(path, valid_paths),
                corresponds_to=corresponds,
            )
        )

    # 5. Sort candidates by descending score
    candidate_sources.sort(key=lambda c: (-c.score, c.path))
    candidate_tests.sort(key=lambda c: (-c.score, c.path))

    # Fallback: if zero scored files, retain top entry points / files
    top_sources = candidate_sources[:max_candidates]
    top_tests = candidate_tests[:max_candidates]

    if not candidate_tests and not warnings:
        warnings.append("No existing test files detected in repository.")

    result = DiscoveryResult(
        candidate_source_files=top_sources,
        candidate_test_files=top_tests,
        detected_languages=sorted(detected_languages_set),
        detected_frameworks=sorted(detected_frameworks_set),
        query_signals=signals.to_dict(),
        limitations_and_warnings=warnings,
    )
    return result


def _scan_directory_files(root: Path, max_files: int) -> tuple[list[str], list[str]]:
    """Walk a cloned repository directory safely with boundary checks."""
    resolved_root = root.resolve()
    files: list[str] = []
    warnings: list[str] = []
    scanned = 0

    for current_dir, dirs, filenames in os.walk(resolved_root, followlinks=False):
        # Prune ignored directory trees
        dirs[:] = [d for d in dirs if d not in IGNORED_DIR_NAMES and not d.startswith(".")]

        rel_dir = Path(current_dir).relative_to(resolved_root)
        for fname in filenames:
            scanned += 1
            if scanned > max_files:
                warnings.append(
                    f"Repository contains over {max_files} files; capped inspection to first {max_files} files."
                )
                return files, warnings

            if fname.startswith("."):
                continue

            file_path = Path(current_dir) / fname
            if file_path.is_symlink():
                try:
                    resolved_sym = file_path.resolve()
                    resolved_sym.relative_to(resolved_root)
                except (ValueError, OSError):
                    warnings.append(f"Skipped symlink pointing outside repository boundary: {rel_dir / fname}")
                    continue

            rel_file = str((rel_dir / fname).as_posix())
            sanitized = sanitize_repository_path(rel_file, repo_root=resolved_root)
            if sanitized:
                files.append(sanitized)

    return files, warnings


def discover_issue_targets_from_sandbox(
    session_id: str,
    checkout_path: str,
    issue_title: str = "",
    issue_body: str = "",
    max_candidates: int = MAX_CANDIDATES_RETURNED,
) -> DiscoveryResult:
    """Execute read-only `git -C <checkout> ls-files` inside an active Celesto VM and discover targets."""
    from tools.sandbox_tools import sandbox_session_manager

    command = f"git -C {checkout_path} ls-files"
    receipt = sandbox_session_manager.run(session_id=session_id, command=command)
    if "exit code: 0" not in receipt:
        return DiscoveryResult(
            limitations_and_warnings=[
                f"Failed to list repository files inside Celesto sandbox (session {session_id}): {receipt[:200]}"
            ]
        )

    stdout_match = re.search(r"STDOUT:\s*\n(.*?)(?:\nSTDERR:|\Z)", receipt, re.DOTALL)
    stdout = stdout_match.group(1) if stdout_match else ""
    tracked_files = [line.strip() for line in stdout.splitlines() if line.strip()]

    return discover_repository_targets(
        repo_input=tracked_files,
        issue_title=issue_title,
        issue_body=issue_body,
        max_candidates=max_candidates,
    )
