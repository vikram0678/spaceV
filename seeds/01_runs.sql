-- ==============================================================================
-- SpaceV Run Ledger Database Initialization & Seed Script
-- Idempotent schema definition and initial demo seed row
-- ==============================================================================

CREATE TABLE IF NOT EXISTS runs (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(128) UNIQUE NOT NULL,
    sandbox_name VARCHAR(128) UNIQUE NOT NULL,
    problem_id VARCHAR(128) NOT NULL,
    state VARCHAR(64) NOT NULL,
    execution_target VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Seed row for verification contract (Contract #1 & #11)
-- Re-running this script will NOT duplicate or error out.
INSERT INTO runs (run_id, sandbox_name, problem_id, state, execution_target, created_at)
VALUES (
    'run-seed-001',
    'sbx-seeddemo1',
    'prob-spacev-detonation',
    'deleted',
    'celesto_sandbox',
    CURRENT_TIMESTAMP
)
ON CONFLICT (sandbox_name) DO UPDATE SET
    state = EXCLUDED.state,
    execution_target = EXCLUDED.execution_target;
