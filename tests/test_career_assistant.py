from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json

import pytest

from core.career_assistant import CareerAssistantStore
from tools.career_tools import create_career_goal, create_career_reminder, delete_career_assistant_data
from tools.registry import OLLAMA_TOOLS_SCHEMA, execute_tool_normalized, get_scoped_tools


def _goal(store: CareerAssistantStore):
    due = (date.today() + timedelta(days=20)).isoformat()
    result = store.create_goal(
        goal="Find a software engineering role",
        target_roles=["Software Engineer"],
        location="Bengaluru or remote",
        deadline=due,
        available_hours=2,
        plan_items=[
            {"title": "Review resume against target roles", "due_date": date.today().isoformat(), "estimated_minutes": 45, "category": "resume"},
            {"title": "Apply to suitable verified listings", "due_date": due, "estimated_minutes": 60, "category": "applications"},
        ],
    )
    assert result["status"] == "draft"
    assert store.activate_goal(result["goal_id"])
    return result


def test_goal_and_plan_are_persisted_and_task_updates_record_confirmed_activity(tmp_path):
    db = tmp_path / "career.sqlite3"
    store = CareerAssistantStore(db)
    created = _goal(store)

    reloaded = CareerAssistantStore(db).get_active_goal()
    assert reloaded is not None
    assert reloaded["goal_id"] == created["goal_id"]
    assert len(reloaded["plan_items"]) == 2

    first = reloaded["plan_items"][0]
    assert CareerAssistantStore(db).update_plan_task(first["task_id"], title="Review my resume", status="completed")
    review = CareerAssistantStore(db).daily_review()
    assert all(item["task_id"] != first["task_id"] for item in review["overdue_or_due_tasks"])
    assert len(review["confirmed_activities_today"]) == 1


def test_draft_plan_can_be_edited_before_user_activates_it(tmp_path):
    store = CareerAssistantStore(tmp_path / "career.sqlite3")
    created = store.create_goal(
        goal="Find a role", target_roles=["Engineer"], location="Remote",
        deadline=(date.today() + timedelta(days=10)).isoformat(), available_hours=2,
        plan_items=[{"title": "Study", "due_date": date.today().isoformat()}],
    )
    task_id = created["plan_items"][0]["task_id"]
    assert store.update_plan_task(task_id, title="Practice interview questions")
    assert store.get_active_goal()["plan_items"][0]["title"] == "Practice interview questions"
    assert store.daily_review()["has_goal"] is False
    assert store.activate_goal(created["goal_id"])
    assert store.daily_review()["has_goal"] is True


def test_goal_validation_rejects_plan_after_deadline_without_partial_write(tmp_path):
    store = CareerAssistantStore(tmp_path / "career.sqlite3")
    deadline = date.today() + timedelta(days=2)
    with pytest.raises(ValueError, match="after the goal deadline"):
        store.create_goal(
            goal="Find a job", target_roles=["Engineer"], location="Remote",
            deadline=deadline.isoformat(), available_hours=1,
            plan_items=[{"title": "Late task", "due_date": (deadline + timedelta(days=1)).isoformat()}],
        )
    assert store.get_active_goal() is None


def test_goal_accepts_relative_deadline_without_model_guessing_calendar_date(tmp_path):
    store = CareerAssistantStore(tmp_path / "career.sqlite3")
    result = store.create_goal(
        "Find a job", ["Engineer"], "Remote", available_hours=1, duration_days=20,
        plan_items=[{"title": "Review resume", "due_date": date.today().isoformat()}],
    )
    assert result["deadline"] == (date.today() + timedelta(days=20)).isoformat()


def test_activity_requires_active_goal_and_records_user_confirmed_source(tmp_path):
    store = CareerAssistantStore(tmp_path / "career.sqlite3")
    with pytest.raises(ValueError, match="no active career goal"):
        store.record_activity("Practiced interview questions")
    _goal(store)
    store.record_activity("Practiced interview questions", minutes=30)
    review = store.daily_review()
    assert review["confirmed_activities_today"][0]["activity"] == "Practiced interview questions"


def test_reminders_survive_restart_fire_once_and_support_snooze(tmp_path):
    db = tmp_path / "career.sqlite3"
    now = datetime.now(timezone.utc)
    due = now + timedelta(minutes=3)
    store = CareerAssistantStore(db)
    reminder = store.create_reminder("Apply to shortlisted role", due.isoformat())

    restarted = CareerAssistantStore(db)
    assert restarted.list_reminders()[0]["reminder_id"] == reminder["reminder_id"]
    assert restarted.snooze_reminder(reminder["reminder_id"], (due + timedelta(hours=1)).isoformat())
    snoozed = restarted.list_reminders()[0]
    assert datetime.fromisoformat(snoozed["due_at_local"]) == due + timedelta(hours=1)

    result = restarted.poll_due_reminders(now=due + timedelta(hours=2))
    assert len(result) == 1
    assert result[0]["title"] == "Apply to shortlisted role"
    assert restarted.poll_due_reminders(now=due + timedelta(hours=2)) == []
    assert restarted.list_reminders(include_completed=True)[0]["status"] == "completed"


def test_recurring_reminder_advances_to_next_future_occurrence(tmp_path):
    store = CareerAssistantStore(tmp_path / "career.sqlite3")
    due = datetime.now(timezone.utc) + timedelta(minutes=2)
    store.create_reminder("Daily career review", due.isoformat(), repeat_rule="daily", timezone_name="UTC")

    fired = store.poll_due_reminders(now=due + timedelta(minutes=1))
    assert len(fired) == 1
    next_item = store.list_reminders()[0]
    assert next_item["repeat_rule"] == "daily"
    assert datetime.fromisoformat(next_item["due_at_local"]) > due


def test_recurring_reminder_uses_iana_timezone_across_dst(tmp_path):
    store = CareerAssistantStore(tmp_path / "career.sqlite3")
    store.create_reminder(
        "Morning review", "2027-11-06T09:00:00", repeat_rule="daily",
        timezone_name="America/New_York",
    )
    first_due = datetime.fromisoformat(store.list_reminders()[0]["due_at_local"])
    store.poll_due_reminders(now=first_due.astimezone(timezone.utc) + timedelta(minutes=1))
    next_due = datetime.fromisoformat(store.list_reminders()[0]["due_at_local"])
    assert first_due.utcoffset() == timedelta(hours=-4)
    assert next_due.utcoffset() == timedelta(hours=-5)
    assert next_due.hour == first_due.hour == 9


def test_opportunity_queue_deduplicates_and_updates_latest_source_check(tmp_path):
    store = CareerAssistantStore(tmp_path / "career.sqlite3")
    url = "https://jobs.example/role/123"
    store.save_opportunities([{"title": "Engineer", "company": "A", "url": url, "platform": "feed-a"}])
    store.save_opportunities([{"title": "Senior Engineer", "company": "A", "url": url, "platform": "feed-b"}])
    items = store.list_opportunities()
    assert len(items) == 1
    assert items[0]["title"] == "Senior Engineer"
    assert items[0]["source"] == "feed-b"
    assert items[0]["status"] == "new"


def test_tool_layer_clarifies_missing_goal_data_and_scopes_goal_tools():
    assert create_career_goal().startswith("SPACEV_NEEDS_USER_INPUT:")
    names = {
        item["function"]["name"]
        for item in get_scoped_tools("Set a goal to find a job and remind me to apply", OLLAMA_TOOLS_SCHEMA)
    }
    assert {"create_career_goal", "get_career_daily_review", "create_career_reminder"}.issubset(names)


def test_tool_registry_normalizes_and_persists_career_reminder(tmp_path, monkeypatch):
    from core import career_assistant

    monkeypatch.setattr(career_assistant, "career_assistant_store", CareerAssistantStore(tmp_path / "registry.sqlite3"))
    due = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    result = execute_tool_normalized("create_career_reminder", {"title": "Apply to role", "due_at": due})
    assert result.status == "success"
    saved = career_assistant.career_assistant_store.list_reminders()
    assert len(saved) == 1
    assert "Reminder saved locally" in result.data
    assert saved[0]["title"] == "Apply to role"


def test_career_reminder_requires_timezone_instead_of_guessing():
    assert create_career_reminder("Apply", "2026-11-05T10:00:00").startswith("SPACEV_NEEDS_USER_INPUT:")


def test_repeating_reminder_requires_iana_timezone(tmp_path):
    store = CareerAssistantStore(tmp_path / "career.sqlite3")
    due = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    with pytest.raises(ValueError, match="IANA timezone"):
        store.create_reminder("Daily check-in", due, repeat_rule="daily")


def test_data_deletion_requires_explicit_confirmation(tmp_path, monkeypatch):
    from core import career_assistant

    store = CareerAssistantStore(tmp_path / "career.sqlite3")
    monkeypatch.setattr(career_assistant, "career_assistant_store", store)
    _goal(store)
    assert delete_career_assistant_data().startswith("SPACEV_NEEDS_USER_INPUT:")
    assert store.get_active_goal() is not None
    assert "Deleted" in delete_career_assistant_data(confirm=True)
    assert store.get_active_goal() is None
