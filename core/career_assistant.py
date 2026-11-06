"""Persistent, local-first career goal, progress, opportunity, and reminder store."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import logging
import math
from pathlib import Path
import sqlite3
import uuid
from typing import Any, Iterator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger("SpaceV.CareerAssistant")
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = REPO_ROOT / ".spacev" / "career_assistant.sqlite3"
REMINDER_REPEAT = {"none", "daily", "weekdays", "weekly"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_aware_datetime(value: str, timezone_name: str = "") -> datetime:
    try:
        result = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Use an ISO date and time with a timezone offset, for example 2026-11-04T18:30:00+05:30.") from exc
    if timezone_name:
        try:
            zone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown IANA timezone '{timezone_name}'. Use a name such as Asia/Kolkata or America/New_York.") from exc
        result = result.replace(tzinfo=zone) if result.tzinfo is None else result.astimezone(zone)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("The date and time needs a timezone offset so the reminder fires at the right local time.")
    return result


class CareerAssistantStore:
    """SQLite-backed source of truth for a user's career plan and follow-through."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 10000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self._connection() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS career_goals (
                    goal_id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    target_roles TEXT NOT NULL,
                    location TEXT NOT NULL,
                    deadline TEXT NOT NULL,
                    available_hours REAL NOT NULL,
                    resume_path TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS career_plan_tasks (
                    task_id TEXT PRIMARY KEY,
                    goal_id TEXT NOT NULL REFERENCES career_goals(goal_id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    due_date TEXT NOT NULL,
                    estimated_minutes INTEGER NOT NULL DEFAULT 0,
                    category TEXT NOT NULL DEFAULT 'career',
                    status TEXT NOT NULL DEFAULT 'planned',
                    completed_at TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(goal_id, title, due_date)
                );
                CREATE TABLE IF NOT EXISTS career_activity (
                    activity_id TEXT PRIMARY KEY,
                    goal_id TEXT NOT NULL REFERENCES career_goals(goal_id) ON DELETE CASCADE,
                    task_id TEXT REFERENCES career_plan_tasks(task_id) ON DELETE SET NULL,
                    activity TEXT NOT NULL,
                    minutes INTEGER NOT NULL DEFAULT 0,
                    happened_at TEXT NOT NULL,
                    evidence_source TEXT NOT NULL DEFAULT 'user_confirmed',
                    notes TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS career_reminders (
                    reminder_id TEXT PRIMARY KEY,
                    goal_id TEXT REFERENCES career_goals(goal_id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    due_at_utc REAL NOT NULL,
                    due_at_local TEXT NOT NULL,
                    timezone_name TEXT NOT NULL DEFAULT '',
                    repeat_rule TEXT NOT NULL DEFAULT 'none',
                    purpose TEXT NOT NULL DEFAULT 'notification',
                    status TEXT NOT NULL DEFAULT 'active',
                    last_fired_at REAL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_career_reminders_due ON career_reminders(status, due_at_utc);
                CREATE TABLE IF NOT EXISTS career_opportunities (
                    opportunity_id TEXT PRIMARY KEY,
                    opportunity_type TEXT NOT NULL DEFAULT 'job',
                    title TEXT NOT NULL,
                    company TEXT NOT NULL DEFAULT '',
                    location TEXT NOT NULL DEFAULT '',
                    url TEXT NOT NULL UNIQUE,
                    source TEXT NOT NULL DEFAULT '',
                    first_seen_at TEXT NOT NULL,
                    last_checked_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'new',
                    notes TEXT NOT NULL DEFAULT ''
                );
                """
            )
            reminder_columns = {row[1] for row in conn.execute("PRAGMA table_info(career_reminders)")}
            if "purpose" not in reminder_columns:
                conn.execute("ALTER TABLE career_reminders ADD COLUMN purpose TEXT NOT NULL DEFAULT 'notification'")
            if "timezone_name" not in reminder_columns:
                conn.execute("ALTER TABLE career_reminders ADD COLUMN timezone_name TEXT NOT NULL DEFAULT ''")
            opportunity_columns = {row[1] for row in conn.execute("PRAGMA table_info(career_opportunities)")}
            if "last_checked_at" not in opportunity_columns and "last_verified_at" in opportunity_columns:
                conn.execute("ALTER TABLE career_opportunities RENAME COLUMN last_verified_at TO last_checked_at")

    def create_goal(
        self,
        goal: str,
        target_roles: list[str],
        location: str,
        available_hours: float,
        plan_items: list[dict[str, Any]],
        deadline: str = "",
        resume_path: str = "",
        duration_days: int = 0,
    ) -> dict[str, Any]:
        clean_goal = goal.strip()
        if isinstance(target_roles, str):
            raise ValueError("target_roles must be a list of roles, not one unstructured string.")
        clean_roles = [str(role).strip() for role in target_roles if str(role).strip()]
        clean_location = location.strip()
        if duration_days < 0 or duration_days > 3650:
            raise ValueError("duration_days must be between 1 and 3650 when provided.")
        if not deadline.strip() and duration_days > 0:
            due_date = date.today() + timedelta(days=duration_days)
        else:
            try:
                due_date = date.fromisoformat(deadline.strip())
            except (TypeError, ValueError) as exc:
                raise ValueError("deadline must be a date in YYYY-MM-DD format, or provide duration_days.") from exc
        if not clean_goal:
            raise ValueError("Tell me what result you want to reach.")
        if not clean_roles:
            raise ValueError("Provide at least one target role so the plan can be relevant.")
        if not clean_location:
            raise ValueError("Provide your target location or work mode; I won't assume remote.")
        if not math.isfinite(available_hours) or available_hours <= 0 or available_hours > 16:
            raise ValueError("available_hours must be greater than 0 and at most 16 per day.")
        if due_date < date.today():
            raise ValueError("The deadline is in the past. Provide a future date or revise the goal.")
        if not plan_items:
            raise ValueError("I need a proposed plan to save with this goal. Draft specific tasks from the user's goal and available time, then ask them to review it.")
        if len(plan_items) > 365:
            raise ValueError("A career goal can contain at most 365 dated plan tasks.")

        now = _utc_now().isoformat()
        goal_id = f"goal_{uuid.uuid4().hex[:12]}"
        inserted_tasks: list[dict[str, Any]] = []
        with self._connection() as conn:
            conn.execute(
                """INSERT INTO career_goals
                   (goal_id, goal, target_roles, location, deadline, available_hours, resume_path, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)""",
                (goal_id, clean_goal, json.dumps(clean_roles), clean_location, due_date.isoformat(), float(available_hours), resume_path.strip(), now, now),
            )
            for item in plan_items:
                if not isinstance(item, dict):
                    raise ValueError("Each plan item must be an object with title, due_date, and optional estimate/category.")
                title = str(item.get("title", "")).strip()
                if not title:
                    raise ValueError("Every plan item needs a title.")
                item_date = date.fromisoformat(str(item.get("due_date", "")))
                if item_date < date.today():
                    raise ValueError(f"Plan item '{title}' is dated before this goal starts.")
                if item_date > due_date:
                    raise ValueError(f"Plan item '{title}' is after the goal deadline.")
                if len(title) > 300:
                    raise ValueError("Plan task titles must be 300 characters or fewer.")
                estimate = int(item.get("estimated_minutes", 0))
                if estimate < 0 or estimate > 24 * 60:
                    raise ValueError("estimated_minutes must be between 0 and 1440.")
                task_id = f"plan_{uuid.uuid4().hex[:12]}"
                category = str(item.get("category", "career")).strip()[:40] or "career"
                conn.execute(
                    """INSERT INTO career_plan_tasks
                       (task_id, goal_id, title, due_date, estimated_minutes, category, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (task_id, goal_id, title, item_date.isoformat(), estimate, category, now),
                )
                inserted_tasks.append({"task_id": task_id, "title": title, "due_date": item_date.isoformat(), "estimated_minutes": estimate, "category": category, "status": "planned"})
        return {"goal_id": goal_id, "goal": clean_goal, "target_roles": clean_roles, "location": clean_location, "deadline": due_date.isoformat(), "available_hours": float(available_hours), "resume_path": resume_path.strip(), "status": "draft", "plan_items": inserted_tasks}

    def activate_goal(self, goal_id: str) -> bool:
        """Activate a proposed goal only after the user has reviewed it."""
        now = _utc_now().isoformat()
        with self._connection() as conn:
            target = conn.execute("SELECT status FROM career_goals WHERE goal_id = ?", (goal_id,)).fetchone()
            if not target or target["status"] not in {"draft", "paused", "active"}:
                return False
            conn.execute("UPDATE career_goals SET status = 'paused', updated_at = ? WHERE status = 'active' AND goal_id != ?", (now, goal_id))
            conn.execute("UPDATE career_goals SET status = 'active', updated_at = ? WHERE goal_id = ?", (now, goal_id))
            return True

    def get_active_goal(self) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM career_goals WHERE status IN ('active', 'draft') ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, created_at DESC LIMIT 1").fetchone()
            if not row:
                return None
            goal = dict(row)
            goal["target_roles"] = json.loads(goal["target_roles"])
            goal["plan_items"] = [dict(item) for item in conn.execute(
                "SELECT task_id, title, due_date, estimated_minutes, category, status, completed_at FROM career_plan_tasks WHERE goal_id = ? ORDER BY due_date, created_at", (goal["goal_id"],)
            )]
            return goal

    def record_activity(self, activity: str, minutes: int = 0, task_id: str = "", notes: str = "") -> str:
        clean_activity = activity.strip()
        if not clean_activity:
            raise ValueError("Describe what you completed.")
        if minutes < 0 or minutes > 24 * 60:
            raise ValueError("minutes must be between 0 and 1440.")
        now = _utc_now().isoformat()
        with self._connection() as conn:
            goal = conn.execute("SELECT goal_id FROM career_goals WHERE status = 'active' ORDER BY created_at DESC LIMIT 1").fetchone()
            if not goal:
                raise ValueError("There is no active career goal yet. Create one first.")
            linked_task = None
            if task_id:
                linked_task = conn.execute("SELECT task_id, goal_id, status FROM career_plan_tasks WHERE task_id = ?", (task_id,)).fetchone()
                if not linked_task or linked_task["goal_id"] != goal["goal_id"]:
                    raise ValueError("That plan task does not belong to the active goal.")
            activity_id = f"activity_{uuid.uuid4().hex[:12]}"
            conn.execute(
                "INSERT INTO career_activity (activity_id, goal_id, task_id, activity, minutes, happened_at, evidence_source, notes) VALUES (?, ?, ?, ?, ?, ?, 'user_confirmed', ?)",
                (activity_id, goal["goal_id"], task_id or None, clean_activity, minutes, now, notes.strip()),
            )
            if linked_task:
                conn.execute("UPDATE career_plan_tasks SET status = 'completed', completed_at = ? WHERE task_id = ?", (now, task_id))
        return activity_id

    def update_plan_task(
        self,
        task_id: str,
        title: str = "",
        due_date: str = "",
        estimated_minutes: int | None = None,
        status: str = "",
    ) -> bool:
        allowed_status = {"planned", "completed", "paused", "cancelled"}
        if status and status not in allowed_status:
            raise ValueError(f"status must be one of: {', '.join(sorted(allowed_status))}.")
        clean_title = title.strip()
        clean_date = ""
        if due_date.strip():
            clean_date = date.fromisoformat(due_date.strip()).isoformat()
        if estimated_minutes is not None and not (0 <= estimated_minutes <= 24 * 60):
            raise ValueError("estimated_minutes must be between 0 and 1440.")
        assignments: list[str] = []
        params: list[Any] = []
        if clean_title:
            assignments.append("title = ?")
            params.append(clean_title)
        if clean_date:
            assignments.append("due_date = ?")
            params.append(clean_date)
        if estimated_minutes is not None:
            assignments.append("estimated_minutes = ?")
            params.append(estimated_minutes)
        if status:
            assignments.append("status = ?")
            params.append(status)
            assignments.append("completed_at = ?")
            params.append(_utc_now().isoformat() if status == "completed" else None)
        if not assignments:
            raise ValueError("Provide at least one plan field to update.")
        with self._connection() as conn:
            target = conn.execute(
                "SELECT t.title, t.status, t.goal_id, g.deadline, g.status AS goal_status FROM career_plan_tasks t JOIN career_goals g ON g.goal_id = t.goal_id WHERE t.task_id = ?",
                (task_id,),
            ).fetchone()
            if not target or target["goal_status"] not in {"draft", "active"}:
                return False
            if clean_date and clean_date > target["deadline"]:
                raise ValueError("A task cannot be scheduled after the active goal deadline.")
            params.append(task_id)
            params.append(target["goal_id"])
            cur = conn.execute(f"UPDATE career_plan_tasks SET {', '.join(assignments)} WHERE task_id = ? AND goal_id = ?", params)
            if cur.rowcount and status == "completed" and target["status"] != "completed":
                conn.execute(
                    "INSERT INTO career_activity (activity_id, goal_id, task_id, activity, minutes, happened_at, evidence_source) VALUES (?, ?, ?, ?, 0, ?, 'user_confirmed')",
                    (f"activity_{uuid.uuid4().hex[:12]}", target["goal_id"], task_id, f"User confirmed completion: {title.strip() or target['title']}", _utc_now().isoformat()),
                )
            return cur.rowcount > 0

    def daily_review(self, day: date | None = None) -> dict[str, Any]:
        target_day = day or date.today()
        with self._connection() as conn:
            goal_row = conn.execute("SELECT * FROM career_goals WHERE status = 'active' ORDER BY created_at DESC LIMIT 1").fetchone()
            if not goal_row:
                draft = conn.execute("SELECT goal_id FROM career_goals WHERE status = 'draft' ORDER BY created_at DESC LIMIT 1").fetchone()
                message = "A career goal plan is saved as a draft. Review it and confirm before I start tracking progress." if draft else "You have no active career goal yet. Tell me the role, location, deadline, and time you can spend each day, and I'll help draft one."
                return {"has_goal": False, "message": message}
            goal = dict(goal_row)
            tasks = [dict(row) for row in conn.execute(
                "SELECT * FROM career_plan_tasks WHERE goal_id = ? AND due_date <= ? AND status != 'completed' ORDER BY due_date, created_at",
                (goal["goal_id"], target_day.isoformat()),
            )]
            done_today = [dict(row) for row in conn.execute(
                "SELECT activity, minutes, happened_at, task_id FROM career_activity WHERE goal_id = ? AND date(happened_at, 'localtime') = ? ORDER BY happened_at",
                (goal["goal_id"], target_day.isoformat()),
            )]
            upcoming = [dict(row) for row in conn.execute(
                "SELECT task_id, title, due_date, estimated_minutes, category FROM career_plan_tasks WHERE goal_id = ? AND due_date > ? AND status = 'planned' ORDER BY due_date LIMIT 5",
                (goal["goal_id"], target_day.isoformat()),
            )]
        return {
            "has_goal": True,
            "goal_id": goal["goal_id"],
            "goal": goal["goal"],
            "target_roles": json.loads(goal["target_roles"]),
            "location": goal["location"],
            "deadline": goal["deadline"],
            "review_date": target_day.isoformat(),
            "overdue_or_due_tasks": tasks,
            "confirmed_activities_today": done_today,
            "upcoming_tasks": upcoming,
            "evidence_note": "Progress includes only activities you explicitly recorded; SpaceV does not infer completion from screen or app activity.",
        }

    def create_reminder(self, title: str, due_at: str, repeat_rule: str = "none", goal_id: str = "", purpose: str = "notification", timezone_name: str = "") -> dict[str, Any]:
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("Reminder title is required.")
        if repeat_rule not in REMINDER_REPEAT:
            raise ValueError(f"repeat_rule must be one of: {', '.join(sorted(REMINDER_REPEAT))}.")
        if purpose not in {"notification", "daily_review"}:
            raise ValueError("purpose must be 'notification' or 'daily_review'.")
        if repeat_rule != "none" and not timezone_name:
            raise ValueError("Repeating reminders need an IANA timezone name to stay correct across daylight-saving changes.")
        local_dt = _parse_aware_datetime(due_at, timezone_name)
        now_utc = _utc_now().timestamp()
        if local_dt.timestamp() <= now_utc:
            raise ValueError("Reminder time must be in the future.")
        with self._connection() as conn:
            if goal_id and not conn.execute("SELECT 1 FROM career_goals WHERE goal_id = ?", (goal_id,)).fetchone():
                raise ValueError("No career goal found with that goal_id.")
            reminder_id = f"rem_{uuid.uuid4().hex[:12]}"
            conn.execute(
                "INSERT INTO career_reminders (reminder_id, goal_id, title, due_at_utc, due_at_local, timezone_name, repeat_rule, purpose, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)",
                (reminder_id, goal_id or None, clean_title, local_dt.timestamp(), local_dt.isoformat(), timezone_name, repeat_rule, purpose, _utc_now().isoformat()),
            )
        return {"reminder_id": reminder_id, "title": clean_title, "due_at": local_dt.isoformat(), "repeat_rule": repeat_rule, "timezone_name": timezone_name, "purpose": purpose, "status": "active"}

    def list_reminders(self, include_completed: bool = False) -> list[dict[str, Any]]:
        query = "SELECT * FROM career_reminders" + ("" if include_completed else " WHERE status = 'active'") + " ORDER BY due_at_utc"
        with self._connection() as conn:
            return [dict(row) for row in conn.execute(query)]

    def cancel_reminder(self, reminder_id: str) -> bool:
        with self._connection() as conn:
            cur = conn.execute("UPDATE career_reminders SET status = 'cancelled' WHERE reminder_id = ? AND status = 'active'", (reminder_id,))
            return cur.rowcount > 0

    def snooze_reminder(self, reminder_id: str, due_at: str) -> bool:
        local_dt = _parse_aware_datetime(due_at)
        if local_dt.timestamp() <= _utc_now().timestamp():
            raise ValueError("Snooze time must be in the future.")
        with self._connection() as conn:
            cur = conn.execute("UPDATE career_reminders SET due_at_utc = ?, due_at_local = ? WHERE reminder_id = ? AND status = 'active'", (local_dt.timestamp(), local_dt.isoformat(), reminder_id))
            return cur.rowcount > 0

    def poll_due_reminders(self, now: datetime | None = None, catch_up_hours: int = 24) -> list[dict[str, Any]]:
        current = now or _utc_now()
        if current.tzinfo is None:
            raise ValueError("now must be timezone-aware.")
        current_ts = current.timestamp()
        due: list[dict[str, Any]] = []
        with self._connection() as conn:
            rows = conn.execute("SELECT * FROM career_reminders WHERE status = 'active' AND due_at_utc <= ? ORDER BY due_at_utc", (current_ts,)).fetchall()
            for row in rows:
                item = dict(row)
                scheduled_ts = float(item["due_at_utc"])
                item["overdue"] = current_ts - scheduled_ts > 60
                item["due_at"] = item["due_at_local"]
                if current_ts - scheduled_ts <= catch_up_hours * 3600:
                    due.append(item)
                repeat_rule = item["repeat_rule"]
                if repeat_rule == "none":
                    conn.execute("UPDATE career_reminders SET status = 'completed', last_fired_at = ? WHERE reminder_id = ?", (current_ts, item["reminder_id"]))
                else:
                    next_dt = datetime.fromisoformat(item["due_at_local"])
                    if item.get("timezone_name"):
                        next_dt = next_dt.astimezone(ZoneInfo(item["timezone_name"]))
                    while next_dt.timestamp() <= current_ts:
                        if repeat_rule == "daily":
                            next_dt += timedelta(days=1)
                        elif repeat_rule == "weekly":
                            next_dt += timedelta(days=7)
                        else:
                            next_dt += timedelta(days=1)
                            while next_dt.weekday() >= 5:
                                next_dt += timedelta(days=1)
                    conn.execute("UPDATE career_reminders SET due_at_utc = ?, due_at_local = ?, last_fired_at = ? WHERE reminder_id = ?", (next_dt.timestamp(), next_dt.isoformat(), current_ts, item["reminder_id"]))
        return due

    def save_opportunities(self, items: list[dict[str, Any]], opportunity_type: str = "job") -> int:
        if opportunity_type not in {"job", "internship", "hackathon"}:
            raise ValueError("opportunity_type must be job, internship, or hackathon.")
        now = _utc_now().isoformat()
        saved = 0
        with self._connection() as conn:
            for item in items:
                url = str(item.get("url") or item.get("apply_url") or "").strip()
                title = str(item.get("title") or "").strip()
                if not url or not title:
                    continue
                if not url.casefold().startswith(("https://", "http://")):
                    raise ValueError("Opportunity links must use http or https.")
                digest = hashlib.sha256(url.casefold().encode("utf-8")).hexdigest()[:24]
                conn.execute(
                    """INSERT INTO career_opportunities
                       (opportunity_id, opportunity_type, title, company, location, url, source, first_seen_at, last_checked_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(url) DO UPDATE SET title=excluded.title, company=excluded.company,
                         location=excluded.location, source=excluded.source, last_checked_at=excluded.last_checked_at""",
                    (f"opp_{digest}", opportunity_type, title, str(item.get("company") or ""), str(item.get("location") or ""), url, str(item.get("platform") or item.get("source") or ""), now, now),
                )
                saved += 1
        return saved

    def list_opportunities(self, status: str = "new", limit: int = 25, opportunity_type: str = "") -> list[dict[str, Any]]:
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100.")
        query = "SELECT * FROM career_opportunities"
        params: list[Any] = []
        filters: list[str] = []
        if status:
            filters.append("status = ?")
            params.append(status)
        if opportunity_type:
            if opportunity_type not in {"job", "internship", "hackathon"}:
                raise ValueError("opportunity_type must be job, internship, or hackathon.")
            filters.append("opportunity_type = ?")
            params.append(opportunity_type)
        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY last_checked_at DESC LIMIT ?"
        params.append(limit)
        with self._connection() as conn:
            return [dict(row) for row in conn.execute(query, params)]

    def update_opportunity_status(self, url: str, status: str, notes: str = "") -> bool:
        allowed = {"new", "wishlist", "shortlisted", "preparing", "applied", "interview", "offer", "rejected", "closed"}
        if status not in allowed:
            raise ValueError(f"status must be one of: {', '.join(sorted(allowed))}.")
        with self._connection() as conn:
            cur = conn.execute("UPDATE career_opportunities SET status = ?, notes = ? WHERE url = ?", (status, notes.strip(), url.strip()))
            return cur.rowcount > 0

    def delete_all_career_data(self) -> None:
        """Delete locally stored career goals, tasks, activity, reminders, and leads."""
        with self._connection() as conn:
            conn.execute("DELETE FROM career_reminders")
            conn.execute("DELETE FROM career_activity")
            conn.execute("DELETE FROM career_plan_tasks")
            conn.execute("DELETE FROM career_opportunities")
            conn.execute("DELETE FROM career_goals")


def format_daily_review(review: dict[str, Any]) -> str:
    """Render a clear, evidence-labeled career check-in for the desktop UI."""
    if not review.get("has_goal"):
        return str(review.get("message", "No active career goal is saved."))
    lines = [
        f"Career check-in — {review['review_date']}",
        f"Goal: {review['goal']} (deadline {review['deadline']})",
    ]
    activities = review.get("confirmed_activities_today", [])
    if activities:
        lines.append("You confirmed:")
        lines.extend(f"• {item['activity']} ({item['minutes']} min)" for item in activities)
    else:
        lines.append("No progress was logged today; that means I don't have an update, not that you did nothing.")
    due = review.get("overdue_or_due_tasks", [])
    if due:
        lines.append("Due or overdue plan tasks:")
        lines.extend(f"• {item['due_date']}: {item['title']}" for item in due)
    upcoming = review.get("upcoming_tasks", [])
    if upcoming:
        lines.append("Coming next:")
        lines.extend(f"• {item['due_date']}: {item['title']}" for item in upcoming[:3])
    lines.append("Tell me what changed and I can adjust the plan with you.")
    return "\n".join(lines)


career_assistant_store = CareerAssistantStore()
