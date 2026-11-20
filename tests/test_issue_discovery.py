"""Comprehensive regression tests for SpaceV Milestone 2 Step 2.2: Dynamic Source & Test Discovery.

Verifies:
1. Dynamic repository inspection across flat, standard, nested, and monorepo layouts.
2. Signal extraction from untrusted issue text (paths, stack traces, symbols, keywords).
3. Test discovery across supported languages (Python, JS/TS, Go, Rust, Java).
4. Deterministic relevance ranking with correspondence alignment and audit reasons.
5. Robust handling of edge cases (zero tests, large repos, polyglot projects).
6. Strict read-only boundary enforcement (no traversals, escapes, writes, or execution).
7. Celesto sandbox integration with mock session manager.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.issue_discovery import (
    CandidateFile,
    DiscoveryResult,
    IssueSignals,
    _compute_file_score,
    _scan_directory_files,
    detect_file_language,
    detect_test_framework,
    discover_issue_targets_from_sandbox,
    discover_repository_targets,
    extract_issue_signals,
    is_ignored_path,
    is_source_file_path,
    is_test_file_path,
    sanitize_repository_path,
)


class TestPathSanitizationAndBoundaries:
    """Verifies strict path sanitization and directory traversal protections."""

    def test_sanitize_valid_relative_paths(self):
        assert sanitize_repository_path("src/app.py") == "src/app.py"
        assert sanitize_repository_path("./src/app.py") == "src/app.py"
        assert sanitize_repository_path("packages/core/src/index.ts") == "packages/core/src/index.ts"
        assert sanitize_repository_path("tests/test_client.py") == "tests/test_client.py"

    @pytest.mark.parametrize(
        "invalid_path",
        [
            "/etc/passwd",
            "/absolute/path/file.py",
            "../secret.txt",
            "src/../../secret.txt",
            "foo/bar/../../../root",
            "~/.ssh/id_rsa",
            "C:/Windows/System32/cmd.exe",
            "C:\\Windows\\System32\\calc.exe",
            "D:/repo/file.py",
            "",
            "   ",
            ".",
            "./",
        ],
    )
    def test_sanitize_rejects_traversals_and_absolutes(self, invalid_path: str):
        assert sanitize_repository_path(invalid_path) is None

    def test_sanitize_with_repo_root_boundary(self, tmp_path: Path):
        root = tmp_path / "repo"
        root.mkdir()
        safe_file = root / "src" / "main.py"
        safe_file.parent.mkdir()
        safe_file.write_text("print('hello')", encoding="utf-8")

        # In-boundary path
        assert sanitize_repository_path("src/main.py", repo_root=root) == "src/main.py"

        # Out-of-boundary path using symlink
        outside = tmp_path / "outside.txt"
        outside.write_text("secret", encoding="utf-8")
        escaped_symlink = root / "src" / "escaped.txt"
        try:
            escaped_symlink.symlink_to(outside)
            assert sanitize_repository_path("src/escaped.txt", repo_root=root) is None
        except (OSError, NotImplementedError):
            # Windows unprivileged symlinks may not be enabled; pass if OS forbids creation
            pass


class TestPathClassification:
    """Verifies accurate categorization of ignored, source, and test paths."""

    @pytest.mark.parametrize(
        "path",
        [
            "node_modules/express/index.js",
            ".git/HEAD",
            ".git/objects/abc",
            "vendor/bundle/gems/foo.rb",
            ".venv/lib/python3.10/site-packages/pkg.py",
            "build/lib/module.py",
            "dist/bundle.js",
            "target/debug/app.exe",
            "__pycache__/foo.cpython-310.pyc",
            ".pytest_cache/v/cache/nodeids",
            "coverage/lcov.info",
            "bundle.min.js",
            "styles.min.css",
            "app.js.map",
            "image.png",
            "font.woff2",
            "binary.exe",
            "lib.so",
        ],
    )
    def test_is_ignored_path(self, path: str):
        assert is_ignored_path(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "src/client.py",
            "tests/test_client.py",
            "packages/core/src/index.ts",
            "pkg/api/handler.go",
            "src/main.rs",
        ],
    )
    def test_is_not_ignored_path(self, path: str):
        assert is_ignored_path(path) is False

    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            # Python tests
            ("tests/test_client.py", True),
            ("tests/client_test.py", True),
            ("test_engine.py", True),
            ("tests/subpkg/test_helpers.py", True),
            ("tests/conftest.py", True),
            ("src/client.py", False),
            ("src/test_runner_utility.py", True),
            # JS / TS tests
            ("src/components/Button.test.tsx", True),
            ("src/services/api.spec.ts", True),
            ("test/integration.test.js", True),
            ("__tests__/App.js", True),
            ("src/components/Button.tsx", False),
            ("src/services/api.ts", False),
            # Go tests
            ("pkg/auth/token_test.go", True),
            ("pkg/auth/token.go", False),
            # Rust tests
            ("tests/integration_test.rs", True),
            ("src/parser_test.rs", True),
            ("src/parser.rs", False),
            # Java tests
            ("src/test/java/com/example/UserServiceTest.java", True),
            ("src/test/java/com/example/OrderTestCase.java", True),
            ("src/main/java/com/example/UserService.java", False),
        ],
    )
    def test_is_test_file_path(self, path: str, expected: bool):
        assert is_test_file_path(path) is expected

    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("src/client.py", True),
            ("src/components/Button.tsx", True),
            ("pkg/auth/token.go", True),
            ("src/parser.rs", True),
            ("src/main/java/com/example/UserService.java", True),
            # Tests are NOT candidate sources
            ("tests/test_client.py", False),
            ("src/components/Button.test.tsx", False),
            # Ignored files are NOT candidate sources
            ("node_modules/foo/index.js", False),
            ("__pycache__/foo.cpython-310.pyc", False),
        ],
    )
    def test_is_source_file_path(self, path: str, expected: bool):
        assert is_source_file_path(path) is expected


class TestLanguageAndFrameworkDetection:
    """Verifies language and test framework inference across multiple ecosystems."""

    def test_detect_file_language(self):
        assert detect_file_language("src/foo.py") == "Python"
        assert detect_file_language("src/foo.ts") == "TypeScript"
        assert detect_file_language("src/foo.tsx") == "TypeScript"
        assert detect_file_language("src/foo.js") == "JavaScript"
        assert detect_file_language("src/foo.go") == "Go"
        assert detect_file_language("src/foo.rs") == "Rust"
        assert detect_file_language("src/foo.java") == "Java"
        assert detect_file_language("src/foo.unknown") == "unknown"

    def test_detect_test_framework(self):
        repo_files_pytest = ["src/client.py", "pytest.ini", "tests/test_client.py"]
        assert detect_test_framework("tests/test_client.py", repo_files_pytest) == "pytest"

        repo_files_jest = ["src/app.ts", "jest.config.js", "tests/app.test.ts"]
        assert detect_test_framework("tests/app.test.ts", repo_files_jest) == "jest"

        repo_files_vitest = ["src/app.ts", "vitest.config.ts", "tests/app.test.ts"]
        assert detect_test_framework("tests/app.test.ts", repo_files_vitest) == "vitest"

        repo_files_go = ["pkg/server.go", "pkg/server_test.go"]
        assert detect_test_framework("pkg/server_test.go", repo_files_go) == "go test"

        repo_files_rust = ["src/lib.rs", "tests/integration_test.rs"]
        assert detect_test_framework("tests/integration_test.rs", repo_files_rust) == "cargo test"

        repo_files_maven = ["pom.xml", "src/test/java/AppTest.java"]
        assert detect_test_framework("src/test/java/AppTest.java", repo_files_maven) == "maven / junit"


class TestSignalExtraction:
    """Verifies robust signal extraction from untrusted issue titles and bodies."""

    def test_extract_python_stack_trace_and_paths(self):
        title = "ConnectionError raised during Client.send with custom retry adapter"
        body = """
        When configuring custom retries, we encounter an unhandled exception:

        Traceback (most recent call last):
          File "requests/adapters.py", line 428, in send
            raise ConnectionError(e, request=request)
        requests.exceptions.ConnectionError: ('Connection aborted.', RemoteDisconnected())

        Also observed in `Session.request` and see tests in tests/test_adapters.py.
        """
        signals = extract_issue_signals(title, body)

        assert "requests/adapters.py" in signals.file_paths
        assert "tests/test_adapters.py" in signals.file_paths
        assert any(
            f["file"] == "requests/adapters.py" and f["line"] == 428 and f["function"] == "send"
            for f in signals.stack_traces
        )
        assert "ConnectionError" in signals.error_types
        assert "Client" in signals.symbols
        assert "send" in signals.symbols
        assert "adapters" in signals.keywords

    def test_extract_javascript_stack_trace(self):
        title = "TypeError: Cannot read properties of undefined in authMiddleware"
        body = """
        Server crashes on unauthenticated request:
        TypeError: Cannot read properties of undefined (reading 'headers')
            at authMiddleware (packages/server/src/middleware/auth.ts:35:18)
            at Layer.handle [as handle_request] (packages/server/src/router.ts:100:12)
        """
        signals = extract_issue_signals(title, body)

        assert "packages/server/src/middleware/auth.ts" in signals.file_paths
        assert "packages/server/src/router.ts" in signals.file_paths
        assert "TypeError" in signals.error_types
        assert any(
            f["file"] == "packages/server/src/middleware/auth.ts" and f["line"] == 35
            for f in signals.stack_traces
        )


class TestRelevanceRanking:
    """Verifies deterministic ranking order and score weights."""

    def test_stack_trace_ranks_above_symbol_and_keyword(self):
        signals = IssueSignals(
            file_paths=["src/client.py"],
            stack_traces=[{"file": "src/client.py", "line": 50, "function": "get"}],
            symbols=["client", "parser"],
            keywords=["timeout", "network"],
        )

        score_trace, reasons_trace = _compute_file_score("src/client.py", is_test=False, signals=signals)
        score_sym, _ = _compute_file_score("src/parser.py", is_test=False, signals=signals)
        score_kw, _ = _compute_file_score("src/network_utils.py", is_test=False, signals=signals)

        assert score_trace > score_sym > score_kw
        assert any("stack trace" in r for r in reasons_trace)

    def test_correspondence_alignment(self):
        repo_files = [
            "src/parser.py",
            "src/encoder.py",
            "tests/test_parser.py",
            "tests/test_encoder.py",
        ]
        result = discover_repository_targets(
            repo_input=repo_files,
            issue_title="ParserError when parsing unexpected EOF in parser.py",
            issue_body="Calling `parser.parse()` raises ParserError",
        )

        assert len(result.candidate_source_files) > 0
        top_source = result.candidate_source_files[0]
        assert top_source.path == "src/parser.py"
        assert top_source.corresponds_to == "tests/test_parser.py"

        assert len(result.candidate_test_files) > 0
        top_test = result.candidate_test_files[0]
        assert top_test.path == "tests/test_parser.py"
        assert top_test.corresponds_to == "src/parser.py"
        assert any("Corresponds to candidate source file" in r for r in top_test.reasons)


class TestRepositoryStructures:
    """Verifies discovery across flat, standard, deeply nested, and monorepo layouts."""

    def test_flat_repository_structure(self):
        repo_files = [
            "app.py",
            "database.py",
            "utils.py",
            "test_app.py",
            "test_database.py",
        ]
        result = discover_repository_targets(
            repo_input=repo_files,
            issue_title="Database connection timeout in database.py",
            issue_body="DatabasePool.connect hangs indefinitely",
        )

        assert result.candidate_source_files[0].path == "database.py"
        assert result.candidate_test_files[0].path == "test_database.py"
        assert "Python" in result.detected_languages

    def test_standard_src_layout(self):
        repo_files = [
            "src/my_lib/session.py",
            "src/my_lib/transport.py",
            "tests/test_session.py",
            "tests/test_transport.py",
            "pytest.ini",
        ]
        result = discover_repository_targets(
            repo_input=repo_files,
            issue_title="Session.close() does not release underlying transport",
            issue_body="Traceback in src/my_lib/session.py line 85",
        )

        assert result.candidate_source_files[0].path == "src/my_lib/session.py"
        assert result.candidate_test_files[0].path == "tests/test_session.py"
        assert result.candidate_test_files[0].framework == "pytest"

    def test_polyglot_monorepo_structure(self):
        repo_files = [
            "packages/frontend/src/App.tsx",
            "packages/frontend/src/__tests__/App.test.tsx",
            "packages/frontend/jest.config.js",
            "packages/backend/src/main.rs",
            "packages/backend/tests/integration_test.rs",
            "services/worker/worker.go",
            "services/worker/worker_test.go",
        ]
        result = discover_repository_targets(
            repo_input=repo_files,
            issue_title="Worker panic when handling nil payload in worker.go",
            issue_body="Worker process panics inside worker.go handleJob",
        )

        assert result.candidate_source_files[0].path == "services/worker/worker.go"
        assert result.candidate_test_files[0].path == "services/worker/worker_test.go"
        assert "Go" in result.detected_languages
        assert "TypeScript" in result.detected_languages
        assert "Rust" in result.detected_languages
        assert "go test" in result.detected_frameworks


class TestEdgeCasesAndSafety:
    """Verifies handling of zero tests, large repositories, directory scanning, and read-only behavior."""

    def test_repository_with_zero_tests(self):
        repo_files = ["src/module_a.py", "src/module_b.py", "README.md"]
        result = discover_repository_targets(
            repo_input=repo_files,
            issue_title="Bug in module_a",
            issue_body="module_a fails with IndexError",
        )

        assert len(result.candidate_source_files) > 0
        assert result.candidate_test_files == []
        assert any("No existing test files detected" in w for w in result.limitations_and_warnings)

    def test_large_repository_file_capping(self):
        # Generate 10,500 fake file paths
        fake_files = [f"src/file_{i}.py" for i in range(10_500)]
        fake_files.append("tests/test_special.py")

        result = discover_repository_targets(
            repo_input=fake_files,
            issue_title="Special bug in file_42.py",
            issue_body="Issue occurs in file_42",
        )

        assert any("capped inspection" in w for w in result.limitations_and_warnings)
        # Should not crash and should still discover targets within cap
        assert len(result.candidate_source_files) <= 15
        assert result.candidate_source_files[0].path == "src/file_42.py"

    def test_directory_scan_ignores_vendor_and_cache(self, tmp_path: Path):
        repo = tmp_path / "test_repo"
        repo.mkdir()
        (repo / "src").mkdir()
        (repo / "src" / "app.py").write_text("def app(): pass", encoding="utf-8")

        # Create ignored dirs
        (repo / "node_modules").mkdir()
        (repo / "node_modules" / "bad.js").write_text("console.log()", encoding="utf-8")
        (repo / ".git").mkdir()
        (repo / ".git" / "HEAD").write_text("ref: master", encoding="utf-8")
        (repo / "__pycache__").mkdir()
        (repo / "__pycache__" / "cached.pyc").write_text("bytes", encoding="utf-8")

        files, warnings = _scan_directory_files(repo, max_files=100)
        assert "src/app.py" in files
        assert not any("node_modules" in f for f in files)
        assert not any(".git" in f for f in files)
        assert not any("__pycache__" in f for f in files)

    def test_read_only_guarantee_on_real_directory(self, tmp_path: Path):
        repo = tmp_path / "immutable_repo"
        repo.mkdir()
        src = repo / "src"
        src.mkdir()
        file_a = src / "core.py"
        file_a.write_text("def run(): pass", encoding="utf-8")

        # Snapshot directory state
        files_before = {p: (p.stat().st_mtime, p.stat().st_size) for p in repo.rglob("*")}

        result = discover_repository_targets(
            repo_input=repo,
            issue_title="Error in core.py",
            issue_body="core.py crashes on start",
        )

        # Snapshot after discovery
        files_after = {p: (p.stat().st_mtime, p.stat().st_size) for p in repo.rglob("*")}

        assert files_before == files_after
        assert result.candidate_source_files[0].path == "src/core.py"


class TestSandboxIntegrationAndSerialization:
    """Verifies sandbox command execution and structured dictionary serialization."""

    def test_discover_issue_targets_from_sandbox_success(self):
        fake_receipt = """COMMAND: git -C /workspace/repo ls-files
EXIT CODE: exit code: 0
DURATION: 0.12s
STDOUT:
src/network.py
src/models.py
tests/test_network.py
tests/test_models.py
STDERR:
"""
        with patch("tools.sandbox_tools.sandbox_session_manager.run", return_value=fake_receipt) as mock_run:
            result = discover_issue_targets_from_sandbox(
                session_id="session-mock-1234",
                checkout_path="/workspace/repo",
                issue_title="Network failure in network.py",
                issue_body="src/network.py raises NetworkError",
            )

            mock_run.assert_called_once_with(
                session_id="session-mock-1234",
                command="git -C /workspace/repo ls-files",
            )
            assert result.candidate_source_files[0].path == "src/network.py"
            assert result.candidate_test_files[0].path == "tests/test_network.py"
            assert not result.limitations_and_warnings

    def test_discover_issue_targets_from_sandbox_failure(self):
        fake_receipt = """COMMAND: git -C /workspace/repo ls-files
EXIT CODE: exit code: 128
DURATION: 0.05s
STDOUT:
STDERR:
fatal: not a git repository
"""
        with patch("tools.sandbox_tools.sandbox_session_manager.run", return_value=fake_receipt):
            result = discover_issue_targets_from_sandbox(
                session_id="session-mock-5678",
                checkout_path="/workspace/repo",
                issue_title="Network failure",
                issue_body="network.py",
            )

            assert len(result.limitations_and_warnings) == 1
            assert "Failed to list repository files inside Celesto sandbox" in result.limitations_and_warnings[0]
            assert result.candidate_source_files == []
            assert result.candidate_test_files == []

    def test_discovery_result_to_dict_structure(self):
        candidate_src = CandidateFile(
            path="src/app.py",
            score=1.85,
            reasons=["Explicitly mentioned in issue text", "Corresponds to candidate test file 'tests/test_app.py'"],
            language="Python",
            corresponds_to="tests/test_app.py",
        )
        candidate_test = CandidateFile(
            path="tests/test_app.py",
            score=2.35,
            reasons=["Explicitly mentioned in issue text", "Corresponds to candidate source file 'src/app.py'"],
            language="Python",
            framework="pytest",
            corresponds_to="src/app.py",
        )
        res = DiscoveryResult(
            candidate_source_files=[candidate_src],
            candidate_test_files=[candidate_test],
            detected_languages=["Python"],
            detected_frameworks=["pytest"],
            query_signals={"file_paths": ["src/app.py"]},
            limitations_and_warnings=["Test warning"],
        )

        d = res.to_dict()
        assert d["candidate_source_files"][0]["path"] == "src/app.py"
        assert d["candidate_source_files"][0]["corresponds_to"] == "tests/test_app.py"
        assert d["candidate_test_files"][0]["framework"] == "pytest"
        assert d["detected_languages"] == ["Python"]
        assert d["detected_frameworks"] == ["pytest"]
        assert d["limitations_and_warnings"] == ["Test warning"]

