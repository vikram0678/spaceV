"""
SpaceV Parallel Firecracker MicroVM Fleet Pool.
Provides pre-warmed standby microVM sandboxes, dynamic lease management,
parallel hypothesis sharding, and collision-safe sandbox lifecycle reaping.
Strictly abolishes hardcoded sandbox names, fixed pool limits, and host-bound assumptions.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Generator, List, Optional

from spacev.fleet.celesto_engine import CelestoSandboxInstance, SandboxExecutionResult

logger = logging.getLogger("SpaceV.FleetPool")


def generate_sandbox_id(prefix: str = "fleet") -> str:
    """Generates a collision-safe sandbox identifier satisfying Celesto's contract."""
    clean_prefix = "".join(c for c in prefix.lower() if c.isalnum())[:5] or "flt"
    unique_suffix = uuid.uuid4().hex[:10]
    return f"sbx-{clean_prefix}{unique_suffix}"


@dataclass
class ParallelTaskResult:
    """Immutable outcome of a task executed in an isolated microVM."""
    task_id: str
    sandbox_name: str
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_s: float
    ok: bool


class CelestoFleetPool:
    """
    High-throughput microVM pool supporting standby pre-warming,
    concurrency-bounded leasing, and parallel hypothesis sharding.
    """

    def __init__(
        self,
        max_pool_size: int = 8,
        warm_standby_target: int = 0,
        sandbox_factory: Optional[Callable[[str], CelestoSandboxInstance]] = None,
        os_type: str = "alpine",
        memory_mb: int = 512,
        disk_mb: int = 2048,
    ):
        if max_pool_size < 1:
            raise ValueError("max_pool_size must be >= 1")
        if warm_standby_target > max_pool_size:
            raise ValueError("warm_standby_target cannot exceed max_pool_size")

        self.max_pool_size = max_pool_size
        self.warm_standby_target = warm_standby_target
        self.os_type = os_type
        self.memory_mb = memory_mb
        self.disk_mb = disk_mb

        self._factory = sandbox_factory or self._default_factory
        self._available_pool: list[CelestoSandboxInstance] = []
        self._busy_instances: dict[str, CelestoSandboxInstance] = {}
        self._lock = asyncio.Lock()
        self._is_shutdown = False

    def _default_factory(self, name: str) -> CelestoSandboxInstance:
        return CelestoSandboxInstance(
            name=name,
            os_type=self.os_type,
            memory_mb=self.memory_mb,
            disk_mb=self.disk_mb,
            network_mode="on",
        )

    @property
    def total_instances(self) -> int:
        return len(self._available_pool) + len(self._busy_instances)

    @property
    def available_count(self) -> int:
        return len(self._available_pool)

    @property
    def busy_count(self) -> int:
        return len(self._busy_instances)

    def prewarm_sync(self) -> int:
        """Pre-warms standby microVM instances up to warm_standby_target."""
        warmed = 0
        while self.total_instances < self.warm_standby_target:
            sbx_name = generate_sandbox_id()
            try:
                sbx = self._factory(sbx_name)
                self._available_pool.append(sbx)
                warmed += 1
            except Exception as e:
                logger.error("Failed to prewarm standby sandbox %s: %s", sbx_name, e)
                break
        return warmed

    @contextmanager
    def lease_sandbox(self) -> Generator[CelestoSandboxInstance, None, None]:
        """Synchronous context manager to lease a sandbox and return it upon exit."""
        if self._is_shutdown:
            raise RuntimeError("Cannot lease from a shut-down fleet pool.")

        sbx: Optional[CelestoSandboxInstance] = None
        if self._available_pool:
            sbx = self._available_pool.pop()
        elif self.total_instances < self.max_pool_size:
            sbx = self._factory(generate_sandbox_id())
        else:
            raise RuntimeError(f"Fleet pool capacity reached ({self.max_pool_size} active).")

        self._busy_instances[sbx.name] = sbx
        try:
            yield sbx
        finally:
            self._busy_instances.pop(sbx.name, None)
            if not self._is_shutdown and sbx.state != "unavailable":
                # Ensure guest state hygiene before allowing sandbox recycling
                is_sterile = self._sanitize_for_reuse(sbx)
                if is_sterile:
                    self._available_pool.append(sbx)
                else:
                    self._terminate_instance(sbx)
            else:
                self._terminate_instance(sbx)

    def _sanitize_for_reuse(self, sbx: CelestoSandboxInstance) -> bool:
        """Restores a sterile guest state before recycling a sandbox into the warm pool."""
        try:
            rollback_fn = getattr(sbx, "rollback", None)
            snapshots = getattr(sbx, "snapshots", {})
            if callable(rollback_fn) and "pristine" in snapshots:
                rollback_fn("pristine")
                return True
            res = sbx.run("git reset --hard HEAD 2>/dev/null; git clean -fdx 2>/dev/null", timeout_seconds=10)
            return res.ok or res.exit_code == 0
        except Exception:
            return False

    def _terminate_instance(self, sbx: CelestoSandboxInstance) -> None:
        """Safely reaps a sandbox instance without leaking resources."""
        try:
            terminate_fn = getattr(sbx, "terminate", None)
            if callable(terminate_fn):
                terminate_fn()
        except Exception as e:
            logger.debug("Failed terminating sandbox %s: %s", getattr(sbx, "name", "unknown"), e)

    def execute_parallel_commands(
        self,
        commands: list[str],
        timeout_seconds: int = 60,
        max_workers: int = 4,
    ) -> list[ParallelTaskResult]:
        """
        Executes a batch of commands concurrently across isolated microVM sandboxes.
        """
        if not commands:
            return []

        concurrency = min(max_workers, self.max_pool_size, len(commands))
        results: list[ParallelTaskResult] = []

        def _worker_exec(cmd: str, task_idx: int) -> ParallelTaskResult:
            t0 = time.perf_counter()
            try:
                with self.lease_sandbox() as sbx:
                    res = sbx.run(cmd, timeout_seconds=timeout_seconds)
                    dur = time.perf_counter() - t0
                    return ParallelTaskResult(
                        task_id=f"task-{task_idx}",
                        sandbox_name=sbx.name,
                        command=cmd,
                        exit_code=res.exit_code,
                        stdout=res.stdout,
                        stderr=res.stderr,
                        duration_s=round(dur, 3),
                        ok=res.ok,
                    )
            except Exception as exc:
                dur = time.perf_counter() - t0
                return ParallelTaskResult(
                    task_id=f"task-{task_idx}",
                    sandbox_name="failed-to-lease",
                    command=cmd,
                    exit_code=127,
                    stdout="",
                    stderr=str(exc),
                    duration_s=round(dur, 3),
                    ok=False,
                )

        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            future_to_idx = {
                executor.submit(_worker_exec, cmd, i): i
                for i, cmd in enumerate(commands)
            }
            indexed_results: list[tuple[int, ParallelTaskResult]] = []
            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                indexed_results.append((idx, future.result()))

        # Preserve original order of commands
        indexed_results.sort(key=lambda x: x[0])
        return [r for _, r in indexed_results]

    def shard_hypotheses(
        self,
        hypotheses: list[Callable[[CelestoSandboxInstance], Any]],
        max_workers: int = 4,
    ) -> list[Any]:
        """
        Runs independent Python test reproduction hypotheses in parallel across microVM sandboxes.
        """
        if not hypotheses:
            return []

        concurrency = min(max_workers, self.max_pool_size, len(hypotheses))

        def _worker_hypothesis(fn: Callable[[CelestoSandboxInstance], Any]) -> Any:
            with self.lease_sandbox() as sbx:
                return fn(sbx)

        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(_worker_hypothesis, h) for h in hypotheses]
            return [f.result() for f in futures]

    def shutdown_all(self) -> int:
        """Terminates all sandboxes in the fleet pool."""
        self._is_shutdown = True
        terminated = 0
        all_instances = list(self._available_pool) + list(self._busy_instances.values())
        self._available_pool.clear()
        self._busy_instances.clear()

        for inst in all_instances:
            try:
                terminate_fn = getattr(inst, "terminate", None)
                if callable(terminate_fn):
                    terminate_fn()
                terminated += 1
            except Exception as e:
                logger.warning("Error terminating sandbox %s: %s", inst.name, e)

        return terminated
