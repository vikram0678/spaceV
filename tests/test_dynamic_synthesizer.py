"""Tests for Dynamic Commit and PR Synthesizer (Zero-Hardcoding Verification)."""

from __future__ import annotations

import pytest

from core.dynamic_discovery import BuildToolchain, GitMetadata, ProjectBlueprint, ProjectEcosystem
from core.dynamic_synthesizer import DynamicSynthesizer


def make_test_blueprint(ecosystem: ProjectEcosystem = ProjectEcosystem.PYTHON) -> ProjectBlueprint:
    return ProjectBlueprint(
        project_name="universal-app",
        root_path="/projects/universal-app",
        toolchain=BuildToolchain(
            ecosystem=ecosystem,
            package_manager="cargo" if ecosystem == ProjectEcosystem.RUST else "pip",
            test_runner="cargo test" if ecosystem == ProjectEcosystem.RUST else "pytest",
            test_command="cargo test" if ecosystem == ProjectEcosystem.RUST else "pytest",
        ),
        git=GitMetadata(
            root_dir="/projects/universal-app",
            canonical_repo_url="https://github.com/org/repo.git",
            current_branch="feature",
            head_commit="f1e2d3c4b5a6f1e2d3c4b5a6f1e2d3c4b5a6f1e2",
        ),
    )


def test_infer_scope_dynamically():
    # Python nested
    assert DynamicSynthesizer.infer_scope(["src/requests/models.py"]) == "models"
    # Python root
    assert DynamicSynthesizer.infer_scope(["utils.py"]) == "utils"
    # Rust nested crate
    assert DynamicSynthesizer.infer_scope(["crates/network/src/lib.rs"]) == "network"
    # Go package
    assert DynamicSynthesizer.infer_scope(["pkg/auth/tokens.go"]) == "tokens"
    # Fallback
    assert DynamicSynthesizer.infer_scope([]) == "core"


def test_extract_concise_action_without_truncation_artifacts():
    # Long sentence that should break cleanly on word boundary, NEVER ending in '...'
    long_desc = "In Response.iter_lines(), coerce delimiter between str and bytes to match the chunk type returned by stream."
    action = DynamicSynthesizer.extract_concise_action(long_desc)
    assert not action.endswith("...")
    assert not action.endswith("..")
    assert len(action) <= 72
    assert "coerce delimiter between str and bytes" in action


def test_synthesize_commit_dynamic():
    bp = make_test_blueprint(ProjectEcosystem.PYTHON)
    commit = DynamicSynthesizer.synthesize_commit(
        blueprint=bp,
        target_files=["src/requests/models.py"],
        patch_hash="f474841ac23aea1ae664b801ae1aa40fc6b5a868880eb887f944f5a5e63770cc",
        problem_summary="Crashes with TypeError on mixed delimiter types.",
        solution_rationale="In models, coerce delimiter type dynamically to match incoming chunk bytes.",
        test_exit_code=0,
    )

    assert commit.scope == "models"
    assert commit.action_title.startswith("fix(models):")
    assert "Problem:" in commit.full_commit_message
    assert "Solution:" in commit.full_commit_message
    assert f"Base-Commit: {bp.git.head_commit}" in commit.full_commit_message
    assert "Patch-Fingerprint: f474841ac23aea1ae664b801ae1aa40fc6b5a868880eb887f944f5a5e63770cc" in commit.full_commit_message


def test_synthesize_pr_markdown_adapts_to_ecosystem():
    # Rust Blueprint
    bp_rust = make_test_blueprint(ProjectEcosystem.RUST)
    commit_rust = DynamicSynthesizer.synthesize_commit(
        blueprint=bp_rust,
        target_files=["crates/engine/src/lib.rs"],
        patch_hash="11223344556677889900aabbccddeeff11223344556677889900aabbccddeeff",
        problem_summary="Panics on zero-length buffer slice.",
        solution_rationale="Guard buffer index before slice operation.",
    )

    pr = DynamicSynthesizer.synthesize_pr_markdown(
        blueprint=bp_rust,
        commit_bundle=commit_rust,
        diff_content="--- a/lib.rs\n+++ b/lib.rs\n",
        behavior_before="Panics on zero-length buffer.",
        behavior_after="Returns None cleanly.",
        solution_rationale="Guard buffer index before slice.",
        test_counts={"passed": 5, "failed": 0, "skipped": 0},
        guest_test_output="test result: ok. 5 passed",
        planned_tests=["tests/integration_test.rs"],
    )

    assert "## 1. Problem Summary" in pr.body
    assert "## 2. Root Cause Analysis" in pr.body
    assert "## 6. Reproduction Steps" in pr.body
    assert "```rust" in pr.body  # Language fence matches Rust!
    assert "cargo test" in pr.body  # Test command matches Rust!
    assert "**Test Counts:** `5` passed, `0` failed, `0` skipped" in pr.body
