"""
Unit and Integration Tests for SpaceV Career & Job Intelligence Engine.
Tests:
  - Multi-source job search and harvesting with deduplication
  - SHA-1 canonical deduplication key generation
  - Local ATS Kanban tracking (.spacev/career_applications.jsonl)
  - Tailored job application draft preparation
  - Two-tiered approval gate classification (TRIVIAL vs HIGH_RISK)
  - Tool scoping for career intents
  - Registry execution via execute_tool_normalized
"""

import json
from pathlib import Path
import pytest
import tools.career_tools as career_tools

from core.containment_gatekeeper import ContainmentGatekeeper
from tools.career_tools import (
    CAREER_APPLICATIONS_FILE,
    list_career_applications,
    make_dedup_key,
    prepare_job_application,
    search_and_harvest_jobs,
    track_career_application,
)
from tools.registry import execute_tool_normalized, get_scoped_tools


@pytest.fixture(autouse=True)
def cleanup_career_test_data(tmp_path, monkeypatch):
    """Isolate career applications file during tests."""
    test_file = tmp_path / "test_career_apps.jsonl"
    monkeypatch.setattr("tools.career_tools.CAREER_APPLICATIONS_FILE", test_file)
    monkeypatch.setattr("tools.career_tools.CAREER_STORE_DIR", tmp_path)
    yield
    if test_file.exists():
        test_file.unlink()


def test_make_dedup_key_deterministic():
    key1 = make_dedup_key("Google", "Senior AI Engineer", "https://careers.google.com/jobs/123")
    key2 = make_dedup_key("Google", "Senior AI Engineer", "https://careers.google.com/jobs/123")
    key3 = make_dedup_key("Meta", "Senior AI Engineer", "https://careers.google.com/jobs/123")

    assert key1 == key2
    assert key1 != key3
    assert "google" in key1
    assert "senior-ai-engineer" in key1


def test_search_and_harvest_jobs_asks_for_missing_location():
    res = search_and_harvest_jobs(role="engineer", limit=3, save_to_desktop=False)
    assert res.startswith("SPACEV_NEEDS_USER_INPUT:")
    assert "target location" in res


def test_search_and_harvest_jobs_does_not_return_unmatched_listings(monkeypatch):
    monkeypatch.setattr(career_tools, "_harvest_simplify_jobs", lambda *args, **kwargs: [])
    monkeypatch.setattr(career_tools, "_harvest_jobspy_live", lambda *args, **kwargs: [])
    monkeypatch.setattr(career_tools, "_load_local_zjob_data", lambda: [])
    monkeypatch.setattr(career_tools, "_fetch_live_remoteok", lambda *args, **kwargs: [])

    res = search_and_harvest_jobs(role="data scientist", location="Bengaluru", save_to_desktop=False)
    assert res.startswith("SPACEV_NEEDS_USER_INPUT:")
    assert "data scientist" in res
    assert "Bengaluru" in res


def test_track_career_application_lifecycle():
    # 1. Track wishlist application
    res1 = track_career_application(
        job_title="AI Systems Architect",
        company="Anthropic",
        job_url="https://anthropic.com/jobs/ai-arch",
        status="Wishlist",
        notes="Referred by colleague",
    )
    assert "AI Systems Architect" in res1
    assert "Anthropic" in res1
    assert "[Wishlist]" in res1

    # 2. Track applied application
    res2 = track_career_application(
        job_title="Lead ML Engineer",
        company="OpenAI",
        job_url="https://openai.com/careers/lead-ml",
        status="Applied",
        notes="Applied through portal",
    )
    assert "Lead ML Engineer" in res2
    assert "[Applied]" in res2

    # 3. List Kanban view
    kanban = list_career_applications()
    assert "Wishlist (1)" in kanban
    assert "Applied (1)" in kanban
    assert "AI Systems Architect" in kanban
    assert "Lead ML Engineer" in kanban

    # 4. Filter by status
    applied_only = list_career_applications(status_filter="Applied")
    assert "Applied (1)" in applied_only
    assert "Lead ML Engineer" in applied_only


def test_prepare_job_application_pitch():
    draft = prepare_job_application(
        job_title="Autonomous Agent Researcher",
        company="DeepMind",
        candidate_name="Vikram",
        skills="LangGraph, Multi-Brain Routing, Celesto Sandboxes",
    )
    assert "DeepMind" in draft
    assert "Autonomous Agent Researcher" in draft
    assert "Vikram" in draft
    assert "LangGraph" in draft


def test_containment_gate_two_tier_classification():
    # TRIVIAL tools should be autonomous
    status, reason = ContainmentGatekeeper.classify_tool_call("search_and_harvest_jobs", {"role": "python"})
    assert status == "TRIVIAL"

    status, reason = ContainmentGatekeeper.classify_tool_call("list_desktop_files", {})
    assert status == "TRIVIAL"

    status, reason = ContainmentGatekeeper.classify_tool_call("track_career_application", {"job_title": "ML Engineer", "company": "Tesla"})
    assert status == "TRIVIAL"

    # HIGH_RISK tools require gatekeeper / approval
    status, reason = ContainmentGatekeeper.classify_tool_call("empty_recycle_bin", {})
    assert status == "HIGH_RISK"

    status, reason = ContainmentGatekeeper.classify_tool_call("kill_process_by_name", {"process_name": "chrome"})
    assert status == "HIGH_RISK"

    status, reason = ContainmentGatekeeper.classify_tool_call(
        "execute_terminal_command", {"command": "git clone https://malicious.repo.com/pwn"}
    )
    assert status == "HIGH_RISK"


def test_registry_scoping_includes_career_tools_on_job_intent():
    scoped = get_scoped_tools("Can you apply for a python ai engineer job for me?")
    tool_names = {t["function"]["name"] for t in scoped}

    assert "search_and_harvest_jobs" in tool_names
    assert "track_career_application" in tool_names
    assert "list_career_applications" in tool_names
    assert "prepare_job_application" in tool_names


def test_execute_tool_normalized_career_tools():
    # Test normalized execution of search_and_harvest_jobs
    res = execute_tool_normalized(
        "search_and_harvest_jobs",
        {"role": "data", "limit": 2, "save_to_desktop": False},
    )
    assert res.success is False
    assert res.status == "needs_input"
    assert str(res.data).startswith("SPACEV_NEEDS_USER_INPUT:")

    # Test normalized execution of track_career_application
    track_res = execute_tool_normalized(
        "track_career_application",
        {
            "job_title": "Full Stack AI Developer",
            "company": "Cursor AI",
            "job_url": "https://cursor.com/jobs/1",
            "status": "Wishlist",
        },
    )
    assert track_res.success is True
    assert "Cursor AI" in str(track_res.data)


def test_detect_ats_vendor_and_skill_extraction():
    from core.career_copilot import detect_ats_vendor, extract_skills_from_text, extract_yoe

    # ATS Vendor tests
    assert detect_ats_vendor("https://boards.greenhouse.io/anthropic/jobs/123") == "greenhouse"
    assert detect_ats_vendor("https://jobs.lever.co/openai/456") == "lever"
    assert detect_ats_vendor("https://nvidia.wd5.myworkdayjobs.com/careers/789") == "workday"
    assert detect_ats_vendor("https://jobs.ashbyhq.com/replicate/abc") == "ashby"

    # Skill extraction tests
    sample_jd = (
        "We are looking for an AI Engineer with strong Python and PyTorch experience. "
        "Familiarity with LangChain, FastAPI, Docker, and Vector Databases is required. "
        "Freshers or candidates with 0-1 years of experience are welcome."
    )
    skills = extract_skills_from_text(sample_jd)
    assert "Python" in skills
    assert "PyTorch" in skills
    assert "LangChain" in skills
    assert "FastAPI" in skills
    assert "Docker" in skills
    assert "Vector Databases" in skills

    assert extract_yoe(sample_jd) == 0


def test_analyze_job_description_compares_only_real_resume_evidence(tmp_path, monkeypatch):
    from core.career_copilot import career_copilot
    from tools.career_tools import analyze_job_description

    resume = tmp_path / "resume.txt"
    resume.write_text("Built backend services using Python and FastAPI across production projects. " * 4, encoding="utf-8")
    monkeypatch.setattr(career_copilot, "extract_job_description", lambda _: {
        "title": "Backend Engineer",
        "company": "Example Co",
        "ats_vendor": "greenhouse",
        "required_skills": ["Python", "Docker"],
        "min_exp": None,
        "details_source": "provided_text",
        "full_description": "Backend role requiring Python and Docker experience." * 8,
    })

    result = analyze_job_description("pasted job description", resume_path=str(resume), compare_resume=True)
    assert "Detected in resume: Python" in result
    assert "Not detected in resume: Docker" in result
    assert "does not mean you lack a skill" in result
    assert "Candidate Match Score" not in result


def test_analyze_job_description_asks_for_resume_when_comparison_requested(monkeypatch):
    from core.career_copilot import career_copilot
    from tools.career_tools import analyze_job_description

    monkeypatch.setattr(career_copilot, "extract_job_description", lambda _: {
        "required_skills": ["Python"], "title": "Engineer", "company": "Example",
        "full_description": "A sufficiently long job description. " * 8,
    })
    result = analyze_job_description("pasted description", compare_resume=True)
    assert result.startswith("SPACEV_NEEDS_USER_INPUT:")
    assert "resume" in result.lower()


def test_brain_tool_result_requires_user_input_without_resynthesis():
    from core.brain_orchestrator import HybridBrainAgent

    question = HybridBrainAgent._clarification_from_tool_result(
        "SPACEV_NEEDS_USER_INPUT: Which location should I search?"
    )
    assert question == "Which location should I search?"
    assert HybridBrainAgent._clarification_from_tool_result("Found three matching jobs") is None


def test_tool_summary_surfaces_input_question_instead_of_success():
    from core.graph_engine import generate_tool_summary

    summary = generate_tool_summary([{
        "name": "search_and_harvest_jobs",
        "status": "needs_input",
        "result": "SPACEV_NEEDS_USER_INPUT: Which location should I search?",
    }])
    assert summary == "Which location should I search?"


def test_mission_pauses_and_resumes_at_tool_needing_input(monkeypatch):
    from core.mission_commander import MissionCommander
    from tools.schemas import ToolResult
    import tools.registry as registry

    calls = []

    def fake_execute(tool_name, arguments):
        calls.append((tool_name, dict(arguments)))
        if tool_name == "search_and_harvest_jobs" and not arguments.get("location"):
            return ToolResult(
                success=False,
                status="needs_input",
                data="SPACEV_NEEDS_USER_INPUT: What location should I search?",
            )
        return ToolResult(success=True, status="success", data="completed")

    monkeypatch.setattr(registry, "execute_tool_normalized", fake_execute)
    commander = MissionCommander(objective="Search jobs then summarize")
    commander.plan_mission([
        {"task_id": "context", "name": "Collect context", "payload": {
            "tool_name": "get_weather", "arguments": {"city": "London"},
        }},
        {"task_id": "job_search", "name": "Find jobs", "payload": {
            "tool_name": "search_and_harvest_jobs",
            "arguments": {"role": "data scientist"},
        }},
        {"task_id": "summarize", "name": "Summarize results", "dependencies": ["context", "job_search"], "payload": {
            "tool_name": "get_weather", "arguments": {"city": "London"},
        }},
    ])

    paused = commander.execute_mission()
    assert paused["status"] == "WAITING_INPUT"
    assert paused["completed_tasks"] == 1
    assert paused["clarification_question"] == "What location should I search?"
    assert calls == [
        ("get_weather", {"city": "London"}),
        ("search_and_harvest_jobs", {"role": "data scientist"}),
    ]
    assert commander.tasks["summarize"].status == "PENDING"

    commander.resume_with_user_input("job_search", {"location": "remote"})
    finished = commander.execute_mission()
    assert finished["status"] == "COMPLETED"
    assert finished["completed_tasks"] == 3
    assert len(calls) == 4
    assert calls[2] == ("search_and_harvest_jobs", {"role": "data scientist", "location": "remote"})


def test_dag_workflow_classifies_tool_input_requests():
    from core.workflow_engine import SpaceVWorkflowEngine

    assert SpaceVWorkflowEngine._clarification_from_result(
        "SPACEV_NEEDS_USER_INPUT: Select a location."
    ) == "Select a location."
    assert SpaceVWorkflowEngine._clarification_from_result({
        "status": "needs_input", "question": "Provide a resume path."
    }) == "Provide a resume path."
    assert SpaceVWorkflowEngine._clarification_from_result({"status": "success", "output": "done"}) is None


def test_fast_router_never_claims_an_application_was_submitted_without_integration(monkeypatch):
    from core.fast_router import FastRouter
    from core.memory import memory

    calls = {}

    def review_only(job_url, resume_path="", auto_submit=False):
        calls.update(job_url=job_url, resume_path=resume_path, auto_submit=auto_submit)
        return "Review prepared; no form was submitted."

    monkeypatch.setattr(career_tools, "apply_to_job", review_only)

    memory.set_suspended_disambiguation({
        "domain": "career_application",
        "property_key": "submit_decision",
        "question": "Confirm?",
        "options": [
            ("1. Submit Application", "submit_confirmed"),
            ("2. Inspect Manually", "inspect_manually"),
            ("3. Cancel", "cancel")
        ],
        "payload": {
            "job_url": "https://boards.greenhouse.io/scaleai/jobs/999",
            "resume_file": "Vikram_Resume.pdf"
        }
    })

    # User replies "1" to confirm
    match = FastRouter.match("1")
    assert match is not None
    action, status, reply = match
    assert action == "apply_to_job"
    assert "not been marked as applied" in reply
    assert "no form was submitted" in reply
    assert calls["auto_submit"] is False
    assert memory.get_suspended_disambiguation() is None


def test_application_confirmation_gate_fails_closed_until_form_integration_exists():
    from core.career_copilot import CareerCopilot

    copilot = CareerCopilot()
    payload = copilot.prepare_application_form(
        "https://boards.greenhouse.io/example/jobs/123",
        "resume.pdf",
        candidate_data={"name": "Test User", "email": "test@example.com"},
    )
    can_submit, message, _ = copilot.verify_and_gate_submission(payload, auto_submit=True)
    assert can_submit is False
    assert "no form was filled" in message.lower()
    assert "nothing was marked applied" in message.lower()


def test_containment_gatekeeper_classifies_apply_to_job_as_high_risk():
    from core.containment_gatekeeper import ContainmentGatekeeper

    # Without auto_submit=True, it must be classified HIGH_RISK
    status, reason = ContainmentGatekeeper.classify_tool_call("apply_to_job", {"job_url": "https://example.com/job"})
    assert status == "HIGH_RISK"
    assert "confirmation" in reason.lower()


