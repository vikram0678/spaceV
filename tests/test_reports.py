import json
import math
import os
import re
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def test_contract_1_docker_compose_and_dockerfile():
    """Requirement 1: docker-compose.yml and Dockerfile exist and have required services."""
    dockerfile = REPO_ROOT / "Dockerfile"
    compose_file = REPO_ROOT / "docker-compose.yml"

    assert dockerfile.exists(), "Dockerfile must exist at repository root"
    assert compose_file.exists(), "docker-compose.yml must exist at repository root"

    compose_text = compose_file.read_text(encoding="utf-8")
    assert "api:" in compose_text, "docker-compose.yml must define 'api' service"
    assert "ledger:" in compose_text, "docker-compose.yml must define 'ledger' service"
    assert "pg_isready" in compose_text, "ledger healthcheck must use pg_isready"
    assert "http://localhost:8080/health" in compose_text or "curl" in compose_text, "api healthcheck must check health"
    assert "seeds" in compose_text, "ledger must mount ./seeds"


def test_contract_2_env_hygiene():
    """Requirement 2: .env.example has required keys and .env does NOT exist."""
    env_example = REPO_ROOT / ".env.example"
    live_env = REPO_ROOT / ".env"

    assert env_example.exists(), ".env.example must exist"
    assert ".env" in (REPO_ROOT / ".gitignore").read_text(encoding="utf-8"), ".env must be listed in .gitignore"

    env_text = env_example.read_text(encoding="utf-8")
    required_keys = [
        "CELESTO_PROVIDER",
        "CELESTO_API_KEY",
        "LLM_API_KEY",
        "LLM_MODEL",
        "DATABASE_URL",
        "API_PORT"
    ]
    for key in required_keys:
        assert f"{key}=" in env_text, f".env.example must include {key}"


def test_contract_3_problem_statement():
    """Requirement 3: reports/problem.json schema and length constraints."""
    prob_path = REPO_ROOT / "reports/problem.json"
    assert prob_path.exists(), "reports/problem.json must exist"

    data = json.loads(prob_path.read_text(encoding="utf-8"))
    assert len(data.get("who", "")) >= 40, "'who' must be at least 40 chars"
    assert len(data.get("agent_work", "")) >= 40, "'agent_work' must be at least 40 chars"
    assert len(data.get("proof_output", "")) >= 20, "'proof_output' must be at least 20 chars"
    assert data.get("idea_source") in ("idea_bank", "original"), "'idea_source' must be idea_bank or original"


def test_contract_4_command_audit_log():
    """Requirement 4: logs/commands.jsonl format and celesto_sandbox target."""
    log_path = REPO_ROOT / "logs/commands.jsonl"
    assert log_path.exists(), "logs/commands.jsonl must exist"

    lines = [line.strip() for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) >= 1, "logs/commands.jsonl must have at least one line"

    for line in lines:
        entry = json.loads(line)
        assert "ts" in entry, "ts must exist"
        assert re.match(r"^sbx-[a-z0-9]{8,}$", entry.get("sandbox_name", "")), f"Invalid sandbox_name: {entry.get('sandbox_name')}"
        assert entry.get("command"), "command must not be empty"
        assert entry.get("decision") in ("allow", "block"), f"decision must be allow or block: {entry.get('decision')}"
        assert entry.get("execution_target") == "celesto_sandbox", f"execution_target must be exactly celesto_sandbox: {entry.get('execution_target')}"


def test_contract_5_capabilities():
    """Requirement 5: reports/capabilities.json has >= 2 valid unique capabilities."""
    cap_path = REPO_ROOT / "reports/capabilities.json"
    assert cap_path.exists(), "reports/capabilities.json must exist"

    data = json.loads(cap_path.read_text(encoding="utf-8"))
    caps = data.get("capabilities", [])
    assert len(caps) >= 2, "capabilities must have at least 2 objects"

    allowed_ids = {
        "persistence", "snapshots", "celestofs", "browser", "published_ports",
        "network_policy", "safety_hooks", "host_mounts", "coding_agent_preset", "agentor_durable"
    }

    seen_ids = set()
    for cap in caps:
        cid = cap.get("id")
        assert cid in allowed_ids, f"Invalid capability ID: {cid}"
        assert cid not in seen_ids, f"Duplicate capability ID: {cid}"
        seen_ids.add(cid)

        assert len(cap.get("why", "")) >= 80, f"Capability {cid} 'why' must be at least 80 chars"
        ev_path = REPO_ROOT / cap.get("evidence_path", "")
        assert ev_path.exists(), f"evidence_path does not exist: {cap.get('evidence_path')}"


def test_contract_6_lifecycle_hygiene():
    """Requirement 6: reports/lifecycle.json has all cleanup flags true and names cross-referenced."""
    lc_path = REPO_ROOT / "reports/lifecycle.json"
    assert lc_path.exists(), "reports/lifecycle.json must exist"

    data = json.loads(lc_path.read_text(encoding="utf-8"))
    assert data.get("cleanup_on_success") is True
    assert data.get("cleanup_on_failure") is True
    assert data.get("cleanup_on_interrupt") is True

    names = data.get("sandbox_names", [])
    assert len(names) > 0, "sandbox_names must not be empty"
    assert len(names) == len(set(names)), "sandbox_names must be unique"

    # Cross reference with logs/commands.jsonl or reports/reliability.json
    commands_text = (REPO_ROOT / "logs/commands.jsonl").read_text(encoding="utf-8")
    reliability_text = (REPO_ROOT / "reports/reliability.json").read_text(encoding="utf-8")

    for name in names:
        assert re.match(r"^sbx-[a-z0-9]{8,}$", name), f"Invalid name format: {name}"
        assert (name in commands_text) or (name in reliability_text), f"Name {name} not found in commands or reliability"


def test_contract_7_reliability_statistics():
    """Requirement 7: reports/reliability.json has >= 20 runs and matches discrete math."""
    rel_path = REPO_ROOT / "reports/reliability.json"
    assert rel_path.exists(), "reports/reliability.json must exist"

    data = json.loads(rel_path.read_text(encoding="utf-8"))
    runs = data.get("runs", [])
    n = len(runs)
    assert n >= 20, "Must have at least 20 runs"
    assert data.get("run_count") == n

    # Unique names and fresh true
    names = [r["sandbox_name"] for r in runs]
    assert len(names) == len(set(names)), "sandbox names must be unique"
    for r in runs:
        assert r.get("fresh") is True
        assert re.match(r"^sbx-[a-z0-9]{8,}$", r.get("sandbox_name", ""))
        assert r.get("wall_clock_s") >= 0
        assert r.get("boot_to_ready_s") >= 0
        assert r.get("cost_usd") >= 0

    # Arithmetic checks
    successes = sum(1 for r in runs if r["success"] is True)
    expected_sr = successes / n
    assert abs(data.get("success_rate", 0) - expected_sr) <= 0.001

    sorted_wc = sorted([r["wall_clock_s"] for r in runs])
    # 20 rows: mean of 10th and 11th (1-based index 10 and 11 => index 9 and 10)
    expected_median_wc = (sorted_wc[9] + sorted_wc[10]) / 2.0
    assert abs(data.get("median_wall_clock_s", 0) - expected_median_wc) <= 0.001

    # p90: rank ceil(0.90 * n) = 18th value => index 17
    rank_p90 = math.ceil(0.90 * n)
    expected_p90_wc = sorted_wc[rank_p90 - 1]
    assert abs(data.get("p90_wall_clock_s", 0) - expected_p90_wc) <= 0.001

    sorted_boot = sorted([r["boot_to_ready_s"] for r in runs])
    expected_median_boot = (sorted_boot[9] + sorted_boot[10]) / 2.0
    assert abs(data.get("median_boot_to_ready_s", 0) - expected_median_boot) <= 0.001

    expected_cost = sum(r["cost_usd"] for r in runs)
    assert abs(data.get("total_cost_usd", 0) - expected_cost) <= 0.01

    # Postmortem check
    pm_path = REPO_ROOT / data.get("postmortem_path", "")
    assert pm_path.exists(), "postmortem_path must exist"
    pm_text = pm_path.read_text(encoding="utf-8")
    assert len(pm_text) >= 200, "postmortem.md must be at least 200 characters"


def test_contract_8_containment_proof():
    """Requirement 8: reports/containment.json attack enum and untouched host."""
    cont_path = REPO_ROOT / "reports/containment.json"
    assert cont_path.exists(), "reports/containment.json must exist"

    data = json.loads(cont_path.read_text(encoding="utf-8"))
    assert data.get("attack") in ("prompt_injection_exfil", "destructive_command", "suspicious_package")
    assert data.get("blocked") is True
    assert data.get("host_untouched") is True

    ev_paths = data.get("evidence_paths", [])
    assert len(ev_paths) >= 1, "Must have at least one evidence path"
    for p in ev_paths:
        assert (REPO_ROOT / p).exists(), f"Evidence path does not exist: {p}"


def test_contract_9_failure_policy_and_trace():
    """Requirement 9: reports/failure_policy.json failed_step=7, total=10, and matching policy trace."""
    fp_path = REPO_ROOT / "reports/failure_policy.json"
    assert fp_path.exists(), "reports/failure_policy.json must exist"

    data = json.loads(fp_path.read_text(encoding="utf-8"))
    assert data.get("failed_step") == 7, "failed_step must be 7"
    assert data.get("total_steps") == 10, "total_steps must be 10"
    policy = data.get("policy")
    assert policy in ("resume", "rollback", "fresh"), f"Invalid policy: {policy}"
    assert len(data.get("rationale", "")) >= 200, "rationale must be at least 200 chars"

    trace_path = REPO_ROOT / data.get("trace_path", "")
    assert trace_path.exists(), "trace_path must exist"

    trace_lines = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    found_policy_event = any(entry.get("event") == "policy_applied" and entry.get("policy") == policy for entry in trace_lines)
    assert found_policy_event, f"trace must contain policy_applied event with policy '{policy}'"


def test_contract_10_concurrency():
    """Requirement 10: reports/concurrency.json >= 5 unique jobs and breakage_notes >= 40 chars."""
    conc_path = REPO_ROOT / "reports/concurrency.json"
    assert conc_path.exists(), "reports/concurrency.json must exist"

    data = json.loads(conc_path.read_text(encoding="utf-8"))
    jobs = data.get("jobs", [])
    assert len(jobs) >= 5, "Must have at least 5 jobs"

    names = [j.get("sandbox_name", "") for j in jobs]
    assert len(names) == len(set(names)), "Jobs sandbox names must be unique"
    for j in jobs:
        assert re.match(r"^sbx-[a-z0-9]{8,}$", j.get("sandbox_name", ""))
        assert j.get("started_at"), "started_at must be non-empty"

    assert len(data.get("breakage_notes", "")) >= 40, "breakage_notes must be at least 40 chars"


def test_contract_11_api_endpoints():
    """Requirement 11: FastAPI app endpoints /health, /api/runs (GET & POST)."""
    from fastapi.testclient import TestClient
    from spacev.control_plane.main import app

    client = TestClient(app)

    # GET /health
    r_health = client.get("/health")
    assert r_health.status_code == 200
    assert r_health.json() == {"status": "ok"}

    # GET /api/runs includes sbx-seeddemo1
    r_runs = client.get("/api/runs")
    assert r_runs.status_code == 200
    runs = r_runs.json()
    assert any(r.get("sandbox_name") == "sbx-seeddemo1" for r in runs), "Must include sbx-seeddemo1"

    # POST valid run -> 201
    valid_payload = {
        "run_id": "run-test-valid-01",
        "sandbox_name": "sbx-testval01",
        "problem_id": "prob-detonator",
        "state": "running",
        "execution_target": "celesto_sandbox"
    }
    r_post_valid = client.post("/api/runs", json=valid_payload)
    assert r_post_valid.status_code == 201
    assert r_post_valid.json().get("sandbox_name") == "sbx-testval01"

    # POST invalid execution_target -> 400
    bad_target_payload = dict(valid_payload, execution_target="host", sandbox_name="sbx-testval02")
    r_bad_target = client.post("/api/runs", json=bad_target_payload)
    assert r_bad_target.status_code == 400, "Invalid execution_target must return 400"

    # POST bad sandbox_name -> 400
    bad_name_payload = dict(valid_payload, sandbox_name="invalid_name")
    r_bad_name = client.post("/api/runs", json=bad_name_payload)
    assert r_bad_name.status_code == 400, "Invalid sandbox_name must return 400"

    # POST unknown state -> 400
    bad_state_payload = dict(valid_payload, state="unknown_state", sandbox_name="sbx-testval03")
    r_bad_state = client.post("/api/runs", json=bad_state_payload)
    assert r_bad_state.status_code == 400, "Unknown state must return 400"


def test_contract_12_readme_mandatory_phrases():
    """Requirement 12: README contains the 6 required verbatim phrases."""
    readme_path = REPO_ROOT / "README.md"
    assert readme_path.exists(), "README.md must exist at repository root"

    text = readme_path.read_text(encoding="utf-8")
    required_phrases = [
        "Problem statement",
        "How I used Celesto",
        "Eval report",
        "Containment test",
        "State and failure design",
        "Setup"
    ]
    for phrase in required_phrases:
        assert phrase in text, f"README.md must contain mandatory phrase '{phrase}'"
