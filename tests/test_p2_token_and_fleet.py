"""
Unit tests for Priority P2:
1. Prompt Caching & CodeAct Token Harness (core/ai_token_harness.py & core/cloud_client.py)
2. Pre-Warmed Snapshot Fleet Pool (<50ms Boot) (core/fleet_pool.py & spacev/fleet/celesto_engine.py)
Strictly zero regex and zero hardcoded paths.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import Mock, patch

import pytest
from core.ai_token_harness import (
    AITokenHarness,
    CacheProvider,
    PromptTier,
    ai_token_harness,
)
from core.fleet_pool import CelestoFleetPool, generate_sandbox_id
from spacev.fleet.celesto_engine import CelestoSandboxInstance, SandboxExecutionResult


class MockSnapshotSandbox:
    def __init__(self, name: str):
        self.name = name
        self.state = "ready"
        self.snapshots: dict[str, Any] = {}
        self.guest_files: dict[str, str] = {}
        self.terminated = False

    def create_pristine_snapshot(self) -> bool:
        self.snapshots["pristine"] = {
            "snapshot_id": "pristine",
            "files": dict(self.guest_files),
        }
        return True

    def fast_rollback(self, snapshot_id: str = "pristine") -> float:
        if snapshot_id not in self.snapshots:
            raise KeyError(snapshot_id)
        # Restore state
        self.guest_files = dict(self.snapshots[snapshot_id]["files"])
        self.state = "ready"
        return 0.5  # Sub-millisecond mock rollback

    def run(self, command: str, timeout_seconds: int = 30) -> SandboxExecutionResult:
        if "mutate" in command:
            self.guest_files["/tmp/state.txt"] = "mutated"
        return SandboxExecutionResult(0, "ok", "")

    def terminate(self) -> None:
        self.terminated = True
        self.state = "terminated"


def test_ai_token_harness_anthropic_prompt_caching():
    system_prompt = "You are SpaceV Cybernetic Assistant. Follow strict security rules."
    messages = [
        {"role": "user", "content": "Execute analysis."},
        {"role": "assistant", "content": "Running analysis."},
        {"role": "user", "content": "Report findings."},
    ]
    tools = [
        {"name": "fetch_logs", "description": "Fetches logs", "parameters": {}},
        {"name": "analyze_diff", "description": "Analyzes git diff", "parameters": {}},
    ]

    payload = ai_token_harness.build_provider_cache_payload(
        provider=CacheProvider.ANTHROPIC,
        system_prompt=system_prompt,
        messages=messages,
        tools=tools,
    )

    # 1. System block contains cache_control ephemeral breakpoint
    assert "system" in payload
    assert isinstance(payload["system"], list)
    assert payload["system"][0]["type"] == "text"
    assert payload["system"][0]["cache_control"] == {"type": "ephemeral"}

    # 2. Tools are deterministically sorted and final tool has cache_control
    assert "tools" in payload
    assert len(payload["tools"]) == 2
    assert payload["tools"][0]["name"] == "analyze_diff"
    assert payload["tools"][1]["name"] == "fetch_logs"
    assert "cache_control" in payload["tools"][1]
    assert payload["tools"][1]["cache_control"] == {"type": "ephemeral"}

    # 3. Prompt caching beta header present
    assert payload["headers"]["anthropic-beta"] == "prompt-caching-2024-07-31"
    assert payload["estimated_discount"] == 0.85


def test_ai_token_harness_openai_and_groq_prefix_stabilization():
    system_prompt = "Deterministic System Prompt"
    messages = [
        {"role": "user", "content": "List files."},
    ]
    tools = [
        {"name": "z_tool", "parameters": {}},
        {"name": "a_tool", "parameters": {}},
    ]

    payload = ai_token_harness.build_provider_cache_payload(
        provider=CacheProvider.OPENAI,
        system_prompt=system_prompt,
        messages=messages,
        tools=tools,
    )

    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][0]["content"] == system_prompt
    assert payload["tools"][0]["name"] == "a_tool"
    assert payload["tools"][1]["name"] == "z_tool"


def test_codeact_script_synthesis_and_token_reduction():
    tool_invocations = [
        {"tool": "find_file", "args": {"pattern": "*.py"}},
        {"tool": "grep_content", "args": {"symbol": "AgenticEngine"}},
        {"tool": "run_test", "args": {"test_name": "test_core"}},
        {"tool": "generate_report", "args": {"format": "json"}},
    ]

    codeact_script, record = ai_token_harness.synthesize_codeact_script(tool_invocations)

    assert record.tool_calls_count == 4
    # Conventional tool turns: 4 * 350 = 1400 tokens
    assert record.raw_turn_tokens == 1400
    assert record.codeact_tokens < 300
    # Slashes token overhead by over 75%
    assert record.reduction_ratio >= 0.75
    assert "execute_tool('find_file'" in codeact_script
    assert "execute_tool('run_test'" in codeact_script


def test_ast_symbol_slice_extraction_zero_regex():
    sample_code = (
        "import os\n\n"
        "def compute_hash(data: str) -> str:\n"
        "    # Computes SHA-256\n"
        "    import hashlib\n"
        "    return hashlib.sha256(data.encode()).hexdigest()\n\n"
        "class CyberneticEngine:\n"
        "    def run(self):\n"
        "        return True\n"
    )

    func_slice = ai_token_harness.extract_ast_symbol_slice(sample_code, "compute_hash")
    assert func_slice is not None
    assert "def compute_hash" in func_slice
    assert "return hashlib.sha256" in func_slice
    assert "CyberneticEngine" not in func_slice

    class_slice = ai_token_harness.extract_ast_symbol_slice(sample_code, "CyberneticEngine")
    assert class_slice is not None
    assert "class CyberneticEngine:" in class_slice
    assert "def run(self):" in class_slice
    assert "def compute_hash" not in class_slice

    # Missing symbol
    assert ai_token_harness.extract_ast_symbol_slice(sample_code, "non_existent") is None


def test_ast_symbol_slice_extraction_with_decorators():
    sample_code = (
        "@classmethod\n"
        "def factory_method(cls, name: str) -> None:\n"
        "    return None\n"
    )
    slice_res = ai_token_harness.extract_ast_symbol_slice(sample_code, "factory_method")
    assert slice_res is not None
    assert "@classmethod" in slice_res
    assert "def factory_method" in slice_res


def test_codeact_script_synthesis_with_string_json_args():
    tool_invocations = [
        {"tool": "find_file", "args": '{"pattern": "*.ts"}'},
    ]
    script, record = ai_token_harness.synthesize_codeact_script(tool_invocations)
    assert 'params_1 = {"pattern": "*.ts"}' in script
    assert "execute_tool('find_file'" in script


def test_compress_tool_turn_output():
    bloated_lines = [f"LOG ROW #{i}: test stdout line trace data" for i in range(100)]
    raw_output = "\n".join(bloated_lines)

    compressed = ai_token_harness.compress_tool_turn(raw_output, max_head_lines=5, max_tail_lines=5)
    lines = compressed.splitlines()

    assert len(lines) == 11  # 5 head + 1 indicator + 5 tail
    assert "LOG ROW #0:" in lines[0]
    assert "LOG ROW #4:" in lines[4]
    assert "pruned by SpaceV Token Harness" in lines[5]
    assert "LOG ROW #99:" in lines[-1]


def test_prewarmed_snapshot_fleet_pool_sub_50ms_checkout_and_rollback():
    pool = CelestoFleetPool(
        max_pool_size=4,
        warm_standby_target=2,
        sandbox_factory=lambda name: MockSnapshotSandbox(name),
    )

    # 1. Prewarm snapshots
    warmed = pool.prewarm_snapshots_sync()
    assert warmed == 2
    assert pool.snapshot_pool_count == 2

    # 2. Sub-50ms lease checkout from pre-warmed snapshot pool
    t0 = time.perf_counter()
    with pool.lease_sandbox(use_snapshot=True) as sbx:
        checkout_ms = (time.perf_counter() - t0) * 1000.0
        assert checkout_ms < 50.0, f"Checkout must be <50ms, took {checkout_ms}ms"
        assert pool.busy_count == 1
        assert pool.snapshot_pool_count == 1

        # Mutate sandbox state inside lease
        sbx.run("mutate state")
        assert sbx.guest_files.get("/tmp/state.txt") == "mutated"

    # 3. Post-lease automatic rollback (<50ms)
    assert pool.busy_count == 0
    assert pool.snapshot_pool_count == 2

    # Re-lease to verify state was rolled back to pristine baseline
    with pool.lease_sandbox(use_snapshot=True) as recycled_sbx:
        assert "/tmp/state.txt" not in recycled_sbx.guest_files

    # 4. Telemetry verification
    telemetry = pool.get_fleet_telemetry()
    assert telemetry.total_leases_served == 2
    assert telemetry.total_rollbacks_completed == 2
    assert telemetry.avg_checkout_latency_ms < 50.0
    assert telemetry.avg_rollback_latency_ms < 50.0


def test_fleet_pool_shutdown_all():
    sandboxes: list[MockSnapshotSandbox] = []

    def mock_factory(name: str):
        sbx = MockSnapshotSandbox(name)
        sandboxes.append(sbx)
        return sbx

    pool = CelestoFleetPool(max_pool_size=3, warm_standby_target=2, sandbox_factory=mock_factory)
    pool.prewarm_snapshots_sync()
    assert len(sandboxes) == 2

    terminated = pool.shutdown_all()
    assert terminated == 2
    assert all(s.terminated for s in sandboxes)
    assert pool.available_count == 0


def test_prewarmed_snapshot_fleet_pool_concurrent_leasing():
    import concurrent.futures
    pool = CelestoFleetPool(
        max_pool_size=4,
        warm_standby_target=4,
        sandbox_factory=lambda name: MockSnapshotSandbox(name),
    )
    pool.prewarm_snapshots_sync()
    assert pool.snapshot_pool_count == 4

    def _worker(thread_id: int):
        with pool.lease_sandbox(use_snapshot=True) as sbx:
            sbx.run(f"mutate from worker {thread_id}")
            time.sleep(0.01)
        return thread_id

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(_worker, i) for i in range(8)]
        results = [f.result() for f in futures]

    assert len(results) == 8
    # All 4 returned back cleanly to snapshot pool
    assert pool.busy_count == 0
    assert pool.snapshot_pool_count == 4
    telemetry = pool.get_fleet_telemetry()
    assert telemetry.total_leases_served == 8
    assert telemetry.total_rollbacks_completed == 8

