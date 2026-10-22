"""
Phase 6 Tests: Host Containment & Adversarial Prompt-Injection Defense.
Validates that malicious commands (credential theft, host file breakout,
and trojan payloads) detonated inside guest Celesto microVMs are 100% contained,
leaving host integrity cryptographically pristine.
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.sandbox_tools import (
    HostIntegrityMonitor,
    PromptInjectionContainmentHarness,
    audit_sandbox_containment,
    generate_containment_contract_report,
)


def test_credential_theft_containment():
    """Verify credential exfiltration payloads are blocked and never leak host tokens."""
    harness = PromptInjectionContainmentHarness()
    res = harness.test_attack_containment("prompt_injection_exfil")

    assert res["attack"] == "prompt_injection_exfil"
    assert res["blocked"] is True
    assert res["host_untouched"] is True
    assert res["guest_contained"] is True


def test_destructive_command_containment():
    """Verify destructive host filesystem breakout commands are intercepted and isolated."""
    harness = PromptInjectionContainmentHarness()
    res = harness.test_attack_containment("destructive_command")

    assert res["attack"] == "destructive_command"
    assert res["blocked"] is True
    assert res["host_untouched"] is True


def test_suspicious_package_containment():
    """Verify untrusted package installation attacks remain contained inside guest."""
    harness = PromptInjectionContainmentHarness()
    res = harness.test_attack_containment("suspicious_package")

    assert res["attack"] == "suspicious_package"
    assert res["host_untouched"] is True


def test_host_integrity_monitor_cryptographic_parity():
    """Verify SHA-256 host integrity monitor passes on intact codebase and detects canary tampering."""
    monitor = HostIntegrityMonitor(monitored_files=["config.py", "requirements.txt"])
    status = monitor.verify_host_integrity()

    assert status["intact"] is True
    assert status["host_compromised"] is False
    assert len(status["mismatches"]) == 0

    # Simulate canary tampering
    monitor.baseline_hashes["config.py"] = "0000000000000000000000000000000000000000000000000000000000000000"
    tampered_status = monitor.verify_host_integrity()
    assert tampered_status["intact"] is False
    assert tampered_status["host_compromised"] is True
    assert len(tampered_status["mismatches"]) == 1


def test_contract_8_report_generation():
    """Verify Contract 8 reports/containment.json is generated with valid schema and evidence."""
    report_file = generate_containment_contract_report("prompt_injection_exfil")
    assert report_file.exists()

    data = json.loads(report_file.read_text(encoding="utf-8"))
    assert data["attack"] in ("prompt_injection_exfil", "destructive_command", "suspicious_package")
    assert data["blocked"] is True
    assert data["host_untouched"] is True
    assert len(data["evidence_paths"]) >= 1

    for ev_rel in data["evidence_paths"]:
        ev_full = REPO_ROOT / ev_rel
        assert ev_full.exists(), f"Evidence path must exist: {ev_rel}"


def test_spacev_audit_tool():
    """Verify SpaceV audit_sandbox_containment tool returns human-readable audit status."""
    msg = audit_sandbox_containment("prompt_injection_exfil")
    assert "Celesto Containment Audit Passed" in msg
    assert "Attack Blocked in Guest: `True`" in msg
    assert "Host OS Untouched: `True`" in msg
