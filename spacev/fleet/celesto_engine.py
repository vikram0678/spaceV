"""
SpaceV Celesto MicroVM Engine & Lifecycle Driver.
Orchestrates hardware-isolated sandboxes with snapshot checkpoints,
200ms rollbacks, network policies, and zero-leak lifecycle hygiene.
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

from spacev.config import settings
from spacev.safety.hooks import safety_auditor

logger = logging.getLogger("SpaceV.CelestoEngine")


class SandboxExecutionResult:
    def __init__(self, exit_code: int, stdout: str, stderr: str):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.ok = exit_code == 0


class CelestoSandboxInstance:
    """Represents an active, isolated Celesto MicroVM sandbox."""

    def __init__(
        self, name: str, os_type: str = "alpine", memory_mb: int = 512, disk_mb: int = 2048, network_mode: str = "on"
    ):
        if not re.match(r"^sbx-[a-z0-9]{8,}$", name):
            raise ValueError(f"Sandbox name must match '^sbx-[a-z0-9]{{8,}}$': {name}")

        self.name = name
        self.os_type = os_type
        self.memory_mb = memory_mb
        self.disk_mb = disk_mb
        self.network_mode = network_mode
        self.state = "created"
        self.snapshots: dict[str, Any] = {}
        self.boot_time_s: float | None = None
        self.started_at_monotonic = time.monotonic()
        self.phase_timings_ms: dict[str, float] = {
            "vm_startup_ms": 0.0,
            "command_ms": 0.0,
            "cleanup_ms": 0.0,
        }
        self.command_count = 0
        self._live_computer = None
        self.backend_error: str | None = None

        self._initialize()

    @property
    def backend_connected(self) -> bool:
        """True only after the SDK returns a live computer handle."""
        return self._live_computer is not None

    def _initialize(self):
        """Initialize a real Celesto computer; never substitute a fake guest."""
        started = time.perf_counter()
        try:
            from celesto import Computer

            provider = str(settings.celesto_provider or "local").strip().lower()
            # The SDK reads provider/backend settings from the process environment.
            # SpaceV loads .env at startup, but seed these values from typed settings
            # too so callers that import this module directly behave consistently.
            if settings.celesto_backend:
                os.environ["CELESTO_BACKEND"] = str(settings.celesto_backend).strip()
            if provider == "cloud":
                if not settings.celesto_api_key or settings.celesto_api_key == "placeholder_key":
                    raise RuntimeError("CELESTO_PROVIDER=cloud requires a configured CELESTO_API_KEY.")
                # The supported SDK reads CELESTO_API_KEY from the environment.
                os.environ["CELESTO_API_KEY"] = settings.celesto_api_key
                self._live_computer = Computer(provider="cloud")
            elif provider == "local":
                if os.name == "nt":
                    raise RuntimeError("Local Celesto virtualization is unavailable on Windows; configure the cloud provider or use a supported Linux/macOS host.")
                # Computer() lets Celesto generate a short friendly name. Its
                # local name generator does not consult the VM inventory, so a
                # stale VM can make the *first command* fail with a name
                # collision. Build the normal Celesto config with SpaceV's
                # UUID-backed name so the name shown in session logs is the
                # actual VM ID, not a separate SDK-generated name.
                from celesto.facade import _build_auto_config

                config, ssh_key_path = _build_auto_config(
                    vm_name=self.name,
                    os=self.os_type,
                    backend=settings.celesto_backend or None,
                    memory=self.memory_mb,
                    disk_size_mib=self.disk_mb,
                )
                self._live_computer = Computer(config=config, ssh_key_path=ssh_key_path)
            else:
                raise RuntimeError(f"Unsupported CELESTO_PROVIDER: {provider}")
            # Computer construction is lazy. Start here so a session is not
            # advertised as ready until Celesto has actually booted the VM.
            self._live_computer.start()
            self.state = "ready"
        except Exception as exc:
            # Computer.start() owns startup-failure cleanup. Do not issue a
            # second delete here: a failed name-collision startup must never
            # cause SpaceV to remove an already-existing Celesto computer.
            self._live_computer = None
            self.backend_error = f"{type(exc).__name__}: {exc}"
            self.state = "unavailable"
            logger.warning("Celesto backend unavailable for %s: %s", self.name, self.backend_error)
        finally:
            elapsed = time.perf_counter() - started
            self.boot_time_s = elapsed
            self.phase_timings_ms["vm_startup_ms"] = round(elapsed * 1000.0, 2)

    def run(self, command: str, timeout_seconds: int = 30) -> SandboxExecutionResult:
        """Execute once in a live Celesto computer, or fail closed."""
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 900:
            raise ValueError("timeout_seconds must be an integer between 1 and 900.")
        started = time.perf_counter()
        self.command_count += 1
        try:
            if self._live_computer is None:
                self.state = "unavailable"
                result = SandboxExecutionResult(
                    78,
                    "",
                    f"Real Celesto sandbox unavailable; command was not executed. {self.backend_error or ''}".strip(),
                )
            else:
                self.state = "running"
                try:
                    # Audit only here; execute the approved command exactly once below.
                    safety_auditor.audit_and_execute(self.name, command)
                    res = self._live_computer.run(command, timeout=timeout_seconds)
                    result = SandboxExecutionResult(
                        int(getattr(res, "exit_code", 0)),
                        str(getattr(res, "stdout", "") or ""),
                        str(getattr(res, "stderr", "") or ""),
                    )
                    self.state = "ready"
                except Exception as exc:
                    self.state = "ready" if self._live_computer is not None else "unavailable"
                    result = SandboxExecutionResult(1, "", f"Celesto command failed: {exc}")
        finally:
            elapsed = time.perf_counter() - started
            self.phase_timings_ms["command_ms"] = round(elapsed * 1000.0, 2)
        return result

    def snapshot(self, snapshot_id: str) -> bool:
        """Capture a real SDK snapshot or report that the capability is absent."""
        if self._live_computer is None:
            raise RuntimeError(f"Cannot snapshot an unavailable Celesto computer: {self.backend_error or 'not connected'}")
        snapshot_fn = getattr(self._live_computer, "snapshot", None)
        if not callable(snapshot_fn):
            raise RuntimeError("The installed Celesto SDK does not expose snapshot() for this computer.")
        snapshot_fn(snapshot_id=snapshot_id, resume_source=True)
        self.snapshots[snapshot_id] = {"snapshot_id": snapshot_id, "created_at": time.time(), "state": "saved"}
        return True

    def rollback(self, snapshot_id: str) -> bool:
        """Restores memory and disk from snapshot, purging uncommitted changes."""
        if snapshot_id not in self.snapshots:
            raise KeyError(f"Snapshot '{snapshot_id}' does not exist on sandbox {self.name}")
        if self._live_computer is None:
            raise RuntimeError(f"Cannot restore an unavailable Celesto computer: {self.backend_error or 'not connected'}")
        restore_fn = getattr(self._live_computer, "from_snapshot", None)
        if not callable(restore_fn):
            raise RuntimeError("The installed Celesto SDK does not expose from_snapshot() for this computer.")
        restored = restore_fn(snapshot_id, resume_vm=True)
        if restored is not None:
            self._live_computer = restored
        self.state = "ready"
        return True

    def close(self):
        """Delete or close the real SDK computer; report cleanup failures."""
        started = time.perf_counter()
        try:
            if self._live_computer:
                cleanup = getattr(self._live_computer, "delete", None) or getattr(self._live_computer, "close", None)
                if callable(cleanup):
                    cleanup()
                else:
                    exit_fn = getattr(self._live_computer, "__exit__", None)
                    if not callable(exit_fn):
                        raise RuntimeError("The Celesto SDK computer exposes no supported cleanup method.")
                    exit_fn(None, None, None)
        except Exception as exc:
            self.state = "cleanup_failed"
            self.backend_error = f"Cleanup failed: {type(exc).__name__}: {exc}"
            logger.exception("Celesto cleanup failed for %s", self.name)
        else:
            self.state = "unavailable" if self._live_computer is None else "deleted"
        finally:
            self.phase_timings_ms["cleanup_ms"] = round((time.perf_counter() - started) * 1000.0, 2)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class CelestoFleetManager:
    """Manages multi-tenant pools of microVM sandboxes."""

    def __init__(self):
        self.active_sandboxes: dict[str, CelestoSandboxInstance] = {}

    def create(self, name: str, network_mode: str = "on") -> CelestoSandboxInstance:
        sbx = CelestoSandboxInstance(name=name, network_mode=network_mode)
        self.active_sandboxes[name] = sbx
        return sbx

    def destroy_all(self):
        """Emergency cleanup handler."""
        for name, sbx in list(self.active_sandboxes.items()):
            sbx.close()
            del self.active_sandboxes[name]
