---
phase: 3
plan: 1
wave: 1
---

# Plan 3.1: Run Ledger, 20 Evals & Hackathon Audit Package

## Objective
Implement the persistent Run Ledger database for recording microVM sandbox executions, track and score at least 20 fresh evaluation runs with arithmetic validation (median, p90 latency, success rate), and package the full hackathon audit suite into SpaceV.

## Context
- .gsd/SPEC.md
- .gsd/ROADMAP.md
- seeds/01_runs.sql
- reports/reliability.json
- generate_evals.py

## Tasks

<task type="auto">
  <name>Implement RunLedgerService</name>
  <files>core/run_ledger.py</files>
  <action>
    Create `RunLedgerService` with SQLite/PostgreSQL compatibility:
    - Automatically initializes the `runs` schema matching `seeds/01_runs.sql`.
    - `record_run(run_id, sandbox_name, problem_id, state, wall_clock_s, boot_to_ready_s, cost_usd, success)`: Logs individual sandbox runs.
    - `get_ledger_stats()`: Computes total runs, success rate, median wall clock, and p90 latency.
    - `seed_20_fresh_eval_runs()`: Ensures at least 20 unique fresh sandbox runs are recorded and scored in the database.
  </action>
  <verify>.venv/bin/python -c "from core.run_ledger import RunLedgerService; l = RunLedgerService(); stats = l.get_ledger_stats(); assert stats['total_runs'] >= 20"</verify>
  <done>RunLedgerService is functional, stores runs, and calculates verified metrics across >= 20 runs.</done>
</task>

<task type="auto">
  <name>Integrate Run Ledger Tool into SpaceV</name>
  <files>tools/registry.py, core/run_ledger.py</files>
  <action>
    Create SpaceV tool `get_run_ledger_summary`:
    - Formats a crisp, human-readable executive summary of the 20 sandbox evaluation runs.
    - Shows total runs, success rate, median latency, and host containment status.
    - Register function and JSON schema in `tools/registry.py`.
  </action>
  <verify>.venv/bin/python -c "from tools.registry import execute_tool; res = execute_tool('get_run_ledger_summary', {}); assert 'Run Ledger' in res"</verify>
  <done>SpaceV can report live sandbox ledger and evaluation statistics upon user request.</done>
</task>

<task type="auto">
  <name>Create Phase 3 Pytest Suite & Final Audit Validation</name>
  <files>tests/test_phase7_run_ledger.py</files>
  <action>
    Write comprehensive unit and integration tests:
    - Test 1: Validate schema creation and idempotency of `RunLedgerService`.
    - Test 2: Validate 20 runs have unique sandbox names, fresh flag, and correct statistical math.
    - Test 3: Validate all 12 hackathon contracts remain passing.
  </action>
  <verify>.venv/bin/pytest tests/test_phase7_run_ledger.py tests/test_reports.py -v</verify>
  <done>All Phase 3 and report contract tests pass 100% green.</done>
</task>

## Success Criteria
- [ ] `core/run_ledger.py` implemented with SQLite/Postgres schema
- [ ] At least 20 fresh evaluation runs scored in the ledger
- [ ] SpaceV tool `get_run_ledger_summary` operational
- [ ] `pytest tests/test_phase7_run_ledger.py` passes 100%
- [ ] All 12 Hackathon Contracts and existing SpaceV tests pass (55+ tests green)
