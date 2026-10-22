# SPEC.md — SpaceV + Celesto Sandbox Detonator

> **Status**: `FINALIZED`
> **Milestone**: v1.0 — Hackathon Submission Release

## Vision
SpaceV is a cybernetic desktop AI copilot that orchestrates autonomous desktop workflows and detonates untrusted, prompt-injected, or heavy tasks inside isolated Celesto Firecracker MicroVM sandboxes with automated snapshot rollback and a verifiable run ledger.

## Goals
1. **Celesto MicroVM Isolation**: Route untrusted agent tool execution into guest sandboxes with automated cleanup on success and failure.
2. **Step 7/10 Failure Recovery**: Implement automatic checkpointing and rollback when step 7 of a 10-step autonomous workflow fails.
3. **Prompt-Injection Defense**: Prove that hostile or prompt-injected payload commands remain confined to the guest microVM and never reach the host OS.
4. **Scored Run Ledger**: Record and score at least 20 fresh evaluation runs in the PostgreSQL/SQLite run ledger.
5. **Zero Regression**: Retain 100% passing test suite across SpaceV's existing 41 unit and integration tests.

## Non-Goals (Out of Scope)
- Direct uncontained execution of untrusted scripts on the host.
- Custom kernel or hypervisor development (relies on Celesto / Firecracker).
- Cloud deployment infrastructure (runs on host / WSL2 Ubuntu).

## Users
- AI Engineers, security auditors, and hackathon evaluators seeking verifiable, sandboxed agent autonomy.

## Constraints
- **Timeline**: Hackathon deadline (24 Oct 2026).
- **Environment**: Ubuntu x86_64 / Linux container with Firecracker support.
- **Python**: Python 3.12 virtual environment (`.venv/bin/python`).

## Success Criteria
- [ ] At least 20 fresh runs recorded and scored in the Run Ledger.
- [ ] Step 7/10 deliberate failure triggers automated rollback and recovery.
- [ ] Host file integrity verified after prompt-injection attacks.
- [ ] 100% pytest test suite pass rate (`pytest tests/`).
