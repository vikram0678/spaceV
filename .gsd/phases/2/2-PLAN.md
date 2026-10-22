---
phase: 2
plan: 1
wave: 1
---

# Plan 2.1: Host Containment & Prompt-Injection Defense

## Objective
Implement cryptographic host integrity monitoring and adversarial prompt-injection containment verification inside Celesto MicroVMs. Prove mathematically that malicious payload commands detonated inside the guest microVM cannot escape, modify host files, or exfiltrate host environment variables.

## Context
- .gsd/SPEC.md
- .gsd/ROADMAP.md
- tools/sandbox_tools.py
- reports/

## Tasks

<task type="auto">
  <name>Implement HostIntegrityMonitor and ContainmentHarness</name>
  <files>tools/sandbox_tools.py</files>
  <action>
    Add to `tools/sandbox_tools.py`:
    - `HostIntegrityMonitor`: Generates SHA-256 cryptographic baselines of canary files and host environment tokens prior to guest detonation, and validates 100% hash parity after detonation.
    - `PromptInjectionContainmentHarness`: Runs battery of adversarial prompt-injection payloads (credential theft, host file breakout, outbound exfiltration, and resource exhaustion) inside the guest sandbox.
    - Asserts that all adversarial effects are strictly contained within the guest filesystem (`guest_compromised: True`, `host_compromised: False`).
  </action>
  <verify>.venv/bin/python -c "from tools.sandbox_tools import HostIntegrityMonitor, PromptInjectionContainmentHarness; m = HostIntegrityMonitor(); assert hasattr(m, 'verify_host_integrity')"</verify>
  <done>HostIntegrityMonitor and PromptInjectionContainmentHarness are implemented and importable.</done>
</task>

<task type="auto">
  <name>Implement Contract 8 Containment Audit Generator</name>
  <files>tools/sandbox_tools.py, reports/contract_8_containment.json</files>
  <action>
    Create automated export function that runs the adversarial containment suite and writes `reports/contract_8_containment.json`:
    - Conforms to Hackathon Contract 8 schema: includes timestamp, sandbox_id, attack_vectors_tested, guest_status, host_status, and cryptographic proof of containment.
    - Expose `audit_sandbox_containment()` as an interactive tool in SpaceV's tool registry.
  </action>
  <verify>.venv/bin/python -c "from tools.sandbox_tools import generate_containment_contract_report; p = generate_containment_contract_report(); assert p.exists()"</verify>
  <done>reports/contract_8_containment.json is generated with valid structure and zero host compromise.</done>
</task>

<task type="auto">
  <name>Create Phase 2 Pytest Suite</name>
  <files>tests/test_phase6_containment.py</files>
  <action>
    Write comprehensive unit and integration tests:
    - Test 1: Verify credential exfiltration payloads (e.g. `cat /etc/shadow`, `printenv`) fail to read host secrets.
    - Test 2: Verify host file breakout attempts (`echo bad > /host_root/hacked.txt`) are dead-ended in guest.
    - Test 3: Verify SHA-256 host canary checksums remain identical before and after detonation.
    - Test 4: Verify Contract 8 JSON report schema validation.
  </action>
  <verify>.venv/bin/pytest tests/test_phase6_containment.py -v</verify>
  <done>All Phase 2 containment tests pass 100% green.</done>
</task>

## Success Criteria
- [ ] `HostIntegrityMonitor` and `PromptInjectionContainmentHarness` operational
- [ ] Adversarial prompt injections detonated with 0 bytes escaped to host
- [ ] `reports/contract_8_containment.json` produced and verified
- [ ] `pytest tests/test_phase6_containment.py` passes 100%
- [ ] Existing 46 SpaceV tests remain 100% green
