"""Dynamic Project & Environment Discovery Subsystem for SpaceV.

Abolishes hardcoded repository paths, framework-specific runners, and static heuristics.
Inspects any project root (Python, Rust, Node/TypeScript, Go) and dynamically infers:
1. Project ecosystem & build toolchain.
2. Source roots, test roots, and entrypoints.
3. Idiomatic test execution commands.
4. Git repository identity, current branch, base commit, and working-tree status.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import shlex
import tomllib
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, Field

logger = logging.getLogger("SpaceV.DynamicDiscovery")


class ProjectEcosystem(str, Enum):
    PYTHON = "python"
    RUST = "rust"
    NODE = "node"
    GO = "go"
    UNKNOWN = "unknown"


class BuildToolchain(BaseModel):
    """Dynamically detected language, package manager, and test runner configuration."""

    ecosystem: ProjectEcosystem
    package_manager: str = "unknown"
    test_runner: str = "unknown"
    test_command: str
    build_command: str | None = None
    source_roots: list[str] = Field(default_factory=list)
    test_roots: list[str] = Field(default_factory=list)
    detected_manifests: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GitMetadata(BaseModel):
    """Dynamically discovered Git version control status."""

    root_dir: str
    canonical_repo_url: str
    current_branch: str
    head_commit: str
    is_clean: bool = True
    untracked_files: list[str] = Field(default_factory=list)
    modified_files: list[str] = Field(default_factory=list)


class ProjectBlueprint(BaseModel):
    """Complete dynamic blueprint of any software project."""

    project_name: str
    root_path: str
    toolchain: BuildToolchain
    git: GitMetadata
    discovered_tests: list[str] = Field(default_factory=list)
    source_files: list[str] = Field(default_factory=list)


class CommandRunner(Protocol):
    """Protocol for executing inspection commands (Host or Celesto MicroVM Guest)."""

    def run(self, cmd: str, timeout: int = 30) -> Any: ...


class LocalCommandRunner:
    """Default command runner using host subprocess."""

    def run(self, cmd: str, timeout: int = 30) -> Any:
        import subprocess

        res = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        class Result:
            exit_code = res.returncode
            stdout = res.stdout
            stderr = res.stderr

        return Result()


class ProjectInspector:
    """Discovers project architecture and toolchain dynamically with zero hardcoding."""

    @staticmethod
    def inspect(
        root_dir: pathlib.Path | str,
        runner: CommandRunner | None = None,
    ) -> ProjectBlueprint:
        """Inspects any directory and synthesizes an executable ProjectBlueprint."""
        root = pathlib.Path(root_dir).resolve()
        cmd_runner = runner or LocalCommandRunner()

        # 1. Inspect Git Metadata dynamically
        git_meta = ProjectInspector._inspect_git(root, cmd_runner)

        # 2. Inspect Ecosystem & Toolchain dynamically
        toolchain = ProjectInspector._detect_toolchain(root)

        # 3. Discover Source & Test Files dynamically
        source_files, test_files = ProjectInspector._discover_files(root, toolchain)

        project_name = root.name
        if toolchain.metadata.get("name"):
            project_name = str(toolchain.metadata["name"])

        return ProjectBlueprint(
            project_name=project_name,
            root_path=str(root).replace("\\", "/"),
            toolchain=toolchain,
            git=git_meta,
            discovered_tests=test_files,
            source_files=source_files,
        )

    @staticmethod
    def _inspect_git(root: pathlib.Path, runner: CommandRunner) -> GitMetadata:
        """Dynamically extract Git state without assuming remote or branch names."""
        r_str = shlex.quote(str(root).replace("\\", "/"))

        # Remote URL
        url_res = runner.run(f"git -C {r_str} remote get-url origin")
        repo_url = url_res.stdout.strip() if url_res.exit_code == 0 else ""

        # Branch
        branch_res = runner.run(f"git -C {r_str} rev-parse --abbrev-ref HEAD")
        branch = branch_res.stdout.strip() if branch_res.exit_code == 0 else "HEAD"

        # Commit
        commit_res = runner.run(f"git -C {r_str} rev-parse HEAD")
        commit = commit_res.stdout.strip().lower() if commit_res.exit_code == 0 else "0" * 40

        # Status
        status_res = runner.run(f"git -C {r_str} status --porcelain")
        untracked: list[str] = []
        modified: list[str] = []

        if status_res.exit_code == 0:
            for raw_line in status_res.stdout.splitlines():
                if not raw_line or len(raw_line) < 3:
                    continue
                code = raw_line[:2]
                path_part = raw_line[3:].strip().replace("\\", "/")
                if " -> " in path_part:
                    path_part = path_part.split(" -> ")[-1].strip()

                if code == "??":
                    untracked.append(path_part)
                else:
                    modified.append(path_part)

        return GitMetadata(
            root_dir=str(root).replace("\\", "/"),
            canonical_repo_url=repo_url,
            current_branch=branch,
            head_commit=commit,
            is_clean=len(untracked) == 0 and len(modified) == 0,
            untracked_files=untracked,
            modified_files=modified,
        )

    @staticmethod
    def _detect_toolchain(root: pathlib.Path) -> BuildToolchain:
        """Infers language ecosystem, package manager, and test runner from manifests."""
        manifests = [p.name for p in root.iterdir() if p.is_file()]

        # 1. Rust Ecosystem
        if "Cargo.toml" in manifests:
            return ProjectInspector._detect_rust(root)

        # 2. Python Ecosystem
        if any(m in manifests for m in ("pyproject.toml", "setup.py", "setup.cfg", "Pipfile", "requirements.txt")):
            return ProjectInspector._detect_python(root)

        # 3. Node/TypeScript Ecosystem
        if "package.json" in manifests:
            return ProjectInspector._detect_node(root)

        # 4. Go Ecosystem
        if "go.mod" in manifests:
            return ProjectInspector._detect_go(root)

        # Fallback / Generic
        return BuildToolchain(
            ecosystem=ProjectEcosystem.UNKNOWN,
            package_manager="unknown",
            test_runner="unknown",
            test_command="echo 'No test runner detected'",
            detected_manifests=manifests,
        )

    @staticmethod
    def _detect_python(root: pathlib.Path) -> BuildToolchain:
        """Inspects Python project manifests to infer pytest/unittest and package manager."""
        manifests: list[str] = []
        metadata: dict[str, Any] = {}
        pkg_manager = "pip"
        test_runner = "pytest"
        test_cmd = "pytest"

        # Check pyproject.toml
        pyproject_file = root / "pyproject.toml"
        if pyproject_file.is_file():
            manifests.append("pyproject.toml")
            try:
                data = tomllib.loads(pyproject_file.read_text(encoding="utf-8"))
                project_info = data.get("project", {})
                if "name" in project_info:
                    metadata["name"] = project_info["name"]

                tool_section = data.get("tool", {})
                if "poetry" in tool_section:
                    pkg_manager = "poetry"
                    test_cmd = "poetry run pytest"
                    if "name" in tool_section["poetry"]:
                        metadata["name"] = tool_section["poetry"]["name"]
                elif "uv" in tool_section:
                    pkg_manager = "uv"
                    test_cmd = "uv run pytest"
                elif "pdm" in tool_section:
                    pkg_manager = "pdm"
                    test_cmd = "pdm run pytest"

                # Check if pytest configured
                if "pytest" in tool_section:
                    test_runner = "pytest"
            except Exception as e:
                logger.warning("Failed to parse pyproject.toml: %s", e)

        # Check setup.py
        if (root / "setup.py").is_file():
            manifests.append("setup.py")

        # Check requirements.txt
        if (root / "requirements.txt").is_file():
            manifests.append("requirements.txt")

        # Discover source and test roots dynamically
        source_roots: list[str] = []
        for cand in ("src", "lib", metadata.get("name", "")):
            if cand and (root / cand).is_dir():
                source_roots.append(cand)
        if not source_roots:
            source_roots.append(".")

        test_roots: list[str] = []
        for cand in ("tests", "test", "testing"):
            if (root / cand).is_dir():
                test_roots.append(cand)
        if not test_roots:
            test_roots.append(".")

        return BuildToolchain(
            ecosystem=ProjectEcosystem.PYTHON,
            package_manager=pkg_manager,
            test_runner=test_runner,
            test_command=test_cmd,
            source_roots=source_roots,
            test_roots=test_roots,
            detected_manifests=manifests,
            metadata=metadata,
        )

    @staticmethod
    def _detect_rust(root: pathlib.Path) -> BuildToolchain:
        """Inspects Cargo.toml to configure cargo test."""
        manifests = ["Cargo.toml"]
        metadata: dict[str, Any] = {}
        cargo_file = root / "Cargo.toml"
        try:
            data = tomllib.loads(cargo_file.read_text(encoding="utf-8"))
            if "package" in data and "name" in data["package"]:
                metadata["name"] = data["package"]["name"]
        except Exception:
            pass

        return BuildToolchain(
            ecosystem=ProjectEcosystem.RUST,
            package_manager="cargo",
            test_runner="cargo test",
            test_command="cargo test",
            build_command="cargo build",
            source_roots=["src"] if (root / "src").is_dir() else ["."],
            test_roots=["tests"] if (root / "tests").is_dir() else ["src"],
            detected_manifests=manifests,
            metadata=metadata,
        )

    @staticmethod
    def _detect_node(root: pathlib.Path) -> BuildToolchain:
        """Inspects package.json to configure npm/yarn/pnpm/bun test scripts."""
        manifests = ["package.json"]
        metadata: dict[str, Any] = {}
        pkg_file = root / "package.json"
        pkg_mgr = "npm"
        test_cmd = "npm test"
        build_cmd = None

        if (root / "pnpm-lock.yaml").is_file():
            pkg_mgr = "pnpm"
            test_cmd = "pnpm test"
        elif (root / "yarn.lock").is_file():
            pkg_mgr = "yarn"
            test_cmd = "yarn test"
        elif (root / "bun.lockb").is_file():
            pkg_mgr = "bun"
            test_cmd = "bun test"

        try:
            data = json.loads(pkg_file.read_text(encoding="utf-8"))
            metadata["name"] = data.get("name", root.name)
            scripts = data.get("scripts", {})
            if "test" in scripts:
                test_cmd = f"{pkg_mgr} test"
            if "build" in scripts:
                build_cmd = f"{pkg_mgr} run build"
        except Exception:
            pass

        return BuildToolchain(
            ecosystem=ProjectEcosystem.NODE,
            package_manager=pkg_mgr,
            test_runner="npm-script",
            test_command=test_cmd,
            build_command=build_cmd,
            source_roots=["src"] if (root / "src").is_dir() else ["."],
            test_roots=["test", "tests", "__tests__"] if any((root / d).is_dir() for d in ("test", "tests", "__tests__")) else ["."],
            detected_manifests=manifests,
            metadata=metadata,
        )

    @staticmethod
    def _detect_go(root: pathlib.Path) -> BuildToolchain:
        """Inspects go.mod to configure go test ./..."""
        manifests = ["go.mod"]
        metadata: dict[str, Any] = {}
        go_mod_file = root / "go.mod"
        try:
            for line in go_mod_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("module "):
                    metadata["name"] = line.split()[1].strip()
                    break
        except Exception:
            pass

        return BuildToolchain(
            ecosystem=ProjectEcosystem.GO,
            package_manager="go",
            test_runner="go test",
            test_command="go test ./...",
            build_command="go build ./...",
            source_roots=["."],
            test_roots=["."],
            detected_manifests=manifests,
            metadata=metadata,
        )

    @staticmethod
    def _discover_files(
        root: pathlib.Path,
        toolchain: BuildToolchain,
    ) -> tuple[list[str], list[str]]:
        """Dynamically indexes all source and test files without scanning ignored directories."""
        ignored_dirs = {
            ".git",
            ".venv",
            "venv",
            "__pycache__",
            "node_modules",
            "target",
            "dist",
            "build",
            ".pytest_cache",
            ".mypy_cache",
        }

        source_files: list[str] = []
        test_files: list[str] = []

        extensions = {
            ProjectEcosystem.PYTHON: {".py"},
            ProjectEcosystem.RUST: {".rs"},
            ProjectEcosystem.NODE: {".js", ".ts", ".jsx", ".tsx"},
            ProjectEcosystem.GO: {".go"},
            ProjectEcosystem.UNKNOWN: {".py", ".rs", ".js", ".ts", ".go"},
        }.get(toolchain.ecosystem, {".py"})

        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in ignored_dirs for part in path.parts):
                continue
            if path.suffix not in extensions:
                continue

            rel = str(path.relative_to(root)).replace("\\", "/")
            name = path.name.lower()

            # Dynamic test pattern recognition
            is_test = (
                name.startswith("test_")
                or name.endswith("_test.py")
                or name.endswith("_test.go")
                or ".test." in name
                or ".spec." in name
                or any(tr in path.parts for tr in toolchain.test_roots if tr != ".")
            )

            if is_test:
                test_files.append(rel)
            else:
                source_files.append(rel)

        return sorted(source_files), sorted(test_files)
