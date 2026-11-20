"""
Unit tests for core/fleet_pool.py: Parallel Firecracker MicroVM Fleet Pool.
"""

from __future__ import annotations

import re
import time
from core.fleet_pool import CelestoFleetPool, generate_sandbox_id, ParallelTaskResult
from spacev.fleet.celesto_engine import SandboxExecutionResult


class MockSandbox:
    def __init__(self, name: str):
        self.name = name
        self.state = "ready"
        self.commands_run: list[str] = []
        self.terminated = False

    def run(self, command: str, timeout_seconds: int = 30) -> SandboxExecutionResult:
        self.commands_run.append(command)
        if "sleep" in command:
            time.sleep(0.05)
        if "fail" in command:
            return SandboxExecutionResult(exit_code=1, stdout="", stderr="command failed")
        return SandboxExecutionResult(exit_code=0, stdout=f"out: {command}", stderr="")

    def terminate(self) -> None:
        self.terminated = True
        self.state = "terminated"


def test_generate_sandbox_id_format():
    for _ in range(50):
        sid = generate_sandbox_id("test")
        assert re.match(r"^sbx-[a-z0-9]{8,}$", sid), f"Invalid ID format: {sid}"
        assert sid.startswith("sbx-test")


def test_fleet_pool_leasing_and_recycling():
    created: list[MockSandbox] = []

    def mock_factory(name: str):
        sbx = MockSandbox(name)
        created.append(sbx)
        return sbx

    pool = CelestoFleetPool(max_pool_size=3, sandbox_factory=mock_factory)

    # 1. Lease a sandbox
    with pool.lease_sandbox() as sbx1:
        assert sbx1.name.startswith("sbx-")
        assert pool.busy_count == 1
        assert pool.available_count == 0

    # 2. Returned to pool
    assert pool.busy_count == 0
    assert pool.available_count == 1

    # 3. Next lease reuses the recycled sandbox
    with pool.lease_sandbox() as sbx2:
        assert sbx2.name == sbx1.name
        assert pool.busy_count == 1
        assert len(created) == 1  # No new creation needed


def test_fleet_pool_capacity_limit():
    pool = CelestoFleetPool(max_pool_size=2, sandbox_factory=lambda name: MockSandbox(name))

    with pool.lease_sandbox() as s1:
        with pool.lease_sandbox() as s2:
            assert pool.total_instances == 2
            try:
                with pool.lease_sandbox():
                    assert False, "Should have raised RuntimeError for capacity limit"
            except RuntimeError as e:
                assert "capacity reached" in str(e).lower()


def test_execute_parallel_commands_concurrency():
    pool = CelestoFleetPool(max_pool_size=4, sandbox_factory=lambda name: MockSandbox(name))

    commands = [
        "sleep 1 && echo job-A",
        "sleep 1 && echo job-B",
        "fail-this-command",
        "echo job-C",
    ]

    t0 = time.perf_counter()
    results = pool.execute_parallel_commands(commands, max_workers=4)
    elapsed = time.perf_counter() - t0

    assert len(results) == 4
    # Check order is preserved
    assert results[0].command == commands[0]
    assert results[1].command == commands[1]
    assert results[2].command == commands[2]
    assert results[3].command == commands[3]

    # Verify execution outputs
    assert results[0].ok is True
    assert "job-A" in results[0].stdout
    assert results[2].ok is False
    assert results[2].exit_code == 1

    # Verify concurrency took significantly less time than sequential execution
    # 2 sleeps of 0.05s ran concurrently in ~0.05-0.08s, not 0.10s+
    assert elapsed < 0.20


def test_shard_hypotheses_parallel():
    pool = CelestoFleetPool(max_pool_size=3, sandbox_factory=lambda name: MockSandbox(name))

    def hypothesis_alpha(sbx: MockSandbox):
        sbx.run("test_alpha")
        return {"hypothesis": "alpha", "passed": True}

    def hypothesis_beta(sbx: MockSandbox):
        sbx.run("test_beta")
        return {"hypothesis": "beta", "passed": False}

    results = pool.shard_hypotheses([hypothesis_alpha, hypothesis_beta], max_workers=2)
    assert len(results) == 2
    assert results[0]["hypothesis"] == "alpha"
    assert results[1]["hypothesis"] == "beta"


def test_fleet_pool_shutdown():
    sandboxes: list[MockSandbox] = []

    def mock_factory(name: str):
        sbx = MockSandbox(name)
        sandboxes.append(sbx)
        return sbx

    pool = CelestoFleetPool(max_pool_size=2, warm_standby_target=2, sandbox_factory=mock_factory)
    warmed = pool.prewarm_sync()
    assert warmed == 2
    assert len(sandboxes) == 2

    terminated_count = pool.shutdown_all()
    assert terminated_count == 2
    assert all(s.terminated for s in sandboxes)
