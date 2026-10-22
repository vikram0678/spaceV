"""
Phase 7 Tests: Run Ledger Service, 20 Fresh Evals & SpaceV Audit Integration.
Validates persistent microVM execution ledger (seeds/01_runs.sql), statistical
evaluation math (success rate, median latency, p90 latency), and SpaceV tool integration.
"""

import re
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.run_ledger import (
    RunLedgerService,
    SandboxRunRecord,
    get_run_ledger_summary,
)
from tools.registry import execute_tool


def test_run_ledger_schema_and_idempotency():
    """Verify RunLedgerService creates SQLite database and idempotent tables matching seeds/01_runs.sql."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ledger.db"
        service = RunLedgerService(db_path=db_path)

        # Verify file exists
        assert db_path.exists()

        # Verify schema
        with service.get_connection() as conn:
            cursor = conn.execute("PRAGMA table_info(runs);")
            cols = {row["name"] for row in cursor.fetchall()}
            expected_cols = {
                "id",
                "run_id",
                "sandbox_name",
                "problem_id",
                "state",
                "execution_target",
                "wall_clock_s",
                "boot_to_ready_s",
                "cost_usd",
                "success",
                "fresh",
                "created_at",
            }
            assert expected_cols.issubset(cols)

        # Verify idempotency
        service.init_db()
        service.seed_20_fresh_eval_runs()
        stats = service.get_ledger_stats()
        assert stats["total_runs"] == 20


def test_run_ledger_20_fresh_evals():
    """Verify 20 runs have unique sbx-* names, fresh=True, and valid execution targets."""
    service = RunLedgerService()
    runs = service.get_all_runs()

    assert len(runs) >= 20
    sandbox_names = set()
    for run in runs:
        sbx_name = run["sandbox_name"]
        assert re.match(r"^sbx-[a-z0-9]{8,}$", sbx_name), f"Invalid sandbox name: {sbx_name}"
        assert sbx_name not in sandbox_names, f"Duplicate sandbox name: {sbx_name}"
        sandbox_names.add(sbx_name)
        assert run["fresh"] == 1
        assert run["execution_target"] == "celesto_sandbox"


def test_run_ledger_statistics_math():
    """Verify median, p90, and success rate arithmetic calculations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_math.db"
        service = RunLedgerService(db_path=db_path)
        stats = service.get_ledger_stats()

        # 17 successes out of 20 = 85.0%
        assert stats["total_runs"] == 20
        assert stats["success_count"] == 17
        assert stats["success_rate"] == 0.85
        assert stats["median_wall_clock_s"] == 4.74
        assert stats["p90_wall_clock_s"] == 5.65
        assert stats["median_boot_to_ready_s"] == 0.51
        assert stats["total_cost_usd"] > 0.0


def test_record_run_update_conflict():
    """Verify recording a new run and updating via conflict resolution."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_rec.db"
        service = RunLedgerService(db_path=db_path)

        new_record = SandboxRunRecord(
            run_id="run-custom01",
            sandbox_name="sbx-custom001",
            problem_id="prob-custom",
            state="in_progress",
            execution_target="celesto_sandbox",
            wall_clock_s=2.5,
            boot_to_ready_s=0.45,
            cost_usd=0.0001,
            success=False,
            fresh=True,
        )
        service.record_run(new_record)

        runs = [r for r in service.get_all_runs() if r["sandbox_name"] == "sbx-custom001"]
        assert len(runs) == 1
        assert runs[0]["state"] == "in_progress"
        assert runs[0]["success"] == 0

        # Update run to completed / success
        updated_record = SandboxRunRecord(
            run_id="run-custom01",
            sandbox_name="sbx-custom001",
            problem_id="prob-custom",
            state="completed",
            execution_target="celesto_sandbox",
            wall_clock_s=3.1,
            boot_to_ready_s=0.45,
            cost_usd=0.00015,
            success=True,
            fresh=True,
        )
        service.record_run(updated_record)

        runs = [r for r in service.get_all_runs() if r["sandbox_name"] == "sbx-custom001"]
        assert len(runs) == 1
        assert runs[0]["state"] == "completed"
        assert runs[0]["success"] == 1
        assert runs[0]["wall_clock_s"] == 3.1


def test_spacev_run_ledger_summary():
    """Verify get_run_ledger_summary formatting and key metrics display."""
    summary = get_run_ledger_summary()
    assert "SpaceV Sandbox Fleet Run Ledger & Evals" in summary
    assert "Total Evaluated Runs: `20`" in summary
    assert "85.0%" in summary
    assert "Median Execution Latency:" in summary
    assert "run_ledger.db" in summary


def test_registry_tool_execution():
    """Verify tool execution via SpaceV registry."""
    result = execute_tool("get_run_ledger_summary", {})
    assert "SpaceV Sandbox Fleet Run Ledger & Evals" in result
    assert "Celesto MicroVMs" in result
