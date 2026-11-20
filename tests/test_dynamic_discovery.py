"""Tests for Dynamic Discovery Subsystem (Zero-Hardcoding Verification)."""

from __future__ import annotations

import pathlib
import pytest

from core.dynamic_discovery import (
    BuildToolchain,
    GitMetadata,
    ProjectBlueprint,
    ProjectEcosystem,
    ProjectInspector,
)


class MockRunner:
    def __init__(self, exit_code: int = 0, stdout: str = "", stderr: str = ""):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr

    def run(self, cmd: str, timeout: int = 30):
        if "remote get-url origin" in cmd:
            return MockRunner(0, "https://github.com/universal/engine.git\n")
        elif "rev-parse --abbrev-ref HEAD" in cmd:
            return MockRunner(0, "develop\n")
        elif "rev-parse HEAD" in cmd:
            return MockRunner(0, "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2\n")
        elif "status --porcelain" in cmd:
            return MockRunner(0, " M src/core.py\n?? scratch.txt\n")
        return MockRunner(self.exit_code, self.stdout, self.stderr)


def test_inspect_git_metadata_dynamic(tmp_path: pathlib.Path):
    runner = MockRunner()
    git_meta = ProjectInspector._inspect_git(tmp_path, runner)

    assert git_meta.canonical_repo_url == "https://github.com/universal/engine.git"
    assert git_meta.current_branch == "develop"
    assert git_meta.head_commit == "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
    assert git_meta.is_clean is False
    assert git_meta.untracked_files == ["scratch.txt"]
    assert git_meta.modified_files == ["src/core.py"]


def test_detect_python_toolchain_pyproject(tmp_path: pathlib.Path):
    # Setup mock Python project with poetry
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[project]
name = "cyber-core"
version = "0.1.0"

[tool.poetry]
name = "cyber-core"

[tool.pytest.ini_options]
minversion = "7.0"
""",
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hello')", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("def test_it(): pass", encoding="utf-8")

    bp = ProjectInspector.inspect(tmp_path, MockRunner())
    assert bp.project_name == "cyber-core"
    assert bp.toolchain.ecosystem == ProjectEcosystem.PYTHON
    assert bp.toolchain.package_manager == "poetry"
    assert bp.toolchain.test_runner == "pytest"
    assert "pytest" in bp.toolchain.test_command
    assert "src/main.py" in bp.source_files
    assert "tests/test_main.py" in bp.discovered_tests


def test_detect_rust_toolchain_cargo(tmp_path: pathlib.Path):
    # Setup mock Rust project
    cargo = tmp_path / "Cargo.toml"
    cargo.write_text(
        """
[package]
name = "spacev-engine"
version = "1.0.0"
edition = "2021"
""",
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "lib.rs").write_text("pub fn run() {}", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_engine.rs").write_text("#[test] fn test_it() {}", encoding="utf-8")

    bp = ProjectInspector.inspect(tmp_path, MockRunner())
    assert bp.project_name == "spacev-engine"
    assert bp.toolchain.ecosystem == ProjectEcosystem.RUST
    assert bp.toolchain.package_manager == "cargo"
    assert bp.toolchain.test_command == "cargo test"
    assert "src/lib.rs" in bp.source_files
    assert "tests/test_engine.rs" in bp.discovered_tests


def test_detect_node_toolchain_package_json(tmp_path: pathlib.Path):
    # Setup mock Node project
    pkg = tmp_path / "package.json"
    pkg.write_text(
        """
{
  "name": "cyber-frontend",
  "version": "1.0.0",
  "scripts": {
    "test": "vitest run",
    "build": "vite build"
  }
}
""",
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "index.ts").write_text("export const a = 1;", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "index.test.ts").write_text("test('it', () => {});", encoding="utf-8")

    bp = ProjectInspector.inspect(tmp_path, MockRunner())
    assert bp.project_name == "cyber-frontend"
    assert bp.toolchain.ecosystem == ProjectEcosystem.NODE
    assert bp.toolchain.test_command == "npm test"
    assert "src/index.ts" in bp.source_files
    assert "tests/index.test.ts" in bp.discovered_tests


def test_detect_go_toolchain_go_mod(tmp_path: pathlib.Path):
    # Setup mock Go project
    go_mod = tmp_path / "go.mod"
    go_mod.write_text("module github.com/cyber/backend\n\ngo 1.22\n", encoding="utf-8")
    (tmp_path / "server.go").write_text("package main", encoding="utf-8")
    (tmp_path / "server_test.go").write_text("package main", encoding="utf-8")

    bp = ProjectInspector.inspect(tmp_path, MockRunner())
    assert bp.project_name == "github.com/cyber/backend"
    assert bp.toolchain.ecosystem == ProjectEcosystem.GO
    assert bp.toolchain.test_command == "go test ./..."
    assert "server.go" in bp.source_files
    assert "server_test.go" in bp.discovered_tests
