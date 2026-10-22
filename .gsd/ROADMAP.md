# ROADMAP.md

> **Current Phase**: Phase 3 Complete (Milestone Complete)
> **Milestone**: v1.0 — Hackathon Submission Release
> **Progress**: 3 / 3 Phases Complete (100%)

## Must-Haves (from SPEC)
- [x] Celesto sandbox execution & cleanup lifecycle
- [x] Step 7/10 failure detection and snapshot rollback
- [x] Host containment against prompt-injected commands
- [x] 20 scored evaluation runs logged in Run Ledger
- [x] 58/58 SpaceV unit & contract tests green

## Phases

### Phase 1: Celesto MicroVM Isolation & Rollback Engine
**Status**: ✅ Complete  
**Objective**: Build reliable Firecracker microVM execution with explicit cleanup on success/failure and automatic recovery when step 7 of 10 fails.  
**Requirements**: REQ-01, REQ-02  
**Target Files**: `tools/sandbox_tools.py`, `tests/test_phase5_celesto_sandbox.py`

### Phase 2: Host Containment & Prompt-Injection Defense
**Status**: ✅ Complete  
**Objective**: Detonate malicious prompt-injected code inside guest microVM and prove mathematically that zero hostile commands or file modifications escape to the host.  
**Requirements**: REQ-03  
**Target Files**: `tools/sandbox_tools.py`, `tests/test_phase6_containment.py`

### Phase 3: Run Ledger, 20 Evals & Hackathon Audit Package
**Status**: ✅ Complete  
**Objective**: Connect PostgreSQL / SQLite run ledger, execute batch evaluation generating at least 20 scored fresh runs, and package audit documentation.  
**Requirements**: REQ-04, REQ-05  
**Target Files**: `reports/`, `seeds/01_runs.sql`, `generate_evals.py`, `core/run_ledger.py`
