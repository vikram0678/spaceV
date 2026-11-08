"""
Verification Test Suite for Resource Integrations:
1. SimplifyJobs Direct ATS Feed Streamer (_harvest_simplify_jobs)
2. JobSpy Multi-Board Consumer Harvester (_harvest_jobspy_live)
3. Biological Overshoot & HumanCursor Trajectory in tools/human_motion.py
4. Deterministic Deduplication across mixed sources (make_dedup_key)
"""
from unittest.mock import MagicMock, patch
import pytest

from tools.career_tools import (
    _harvest_simplify_jobs,
    _harvest_jobspy_live,
    search_and_harvest_jobs,
    make_dedup_key
)
from tools.human_motion import human_move_to, generate_human_path
from tools.gui_tools import safety


def test_simplify_jobs_harvesting_normalizes_direct_ats_links():
    """Verify SimplifyJobs feed extracts active tech jobs with direct ATS links."""
    mock_feed = [
        {
            "active": True,
            "is_visible": True,
            "title": "AI Research Intern",
            "company_name": "DeepMind",
            "url": "https://jobs.lever.co/deepmind/12345",
            "locations": ["London", "Remote"],
            "category": "AI / ML",
            "date_posted": "2026-03-01"
        },
        {
            "active": False,  # Should be filtered out
            "is_visible": True,
            "title": "Old Expired Role",
            "company_name": "OldCo",
            "url": "https://oldco.com",
            "locations": ["Remote"]
        }
    ]

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        import json
        mock_resp.read.return_value = json.dumps(mock_feed).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        jobs = _harvest_simplify_jobs(role="ai", limit=5)
        assert len(jobs) == 1
        assert jobs[0]["title"] == "AI Research Intern"
        assert jobs[0]["company"] == "DeepMind"
        assert jobs[0]["url"] == "https://jobs.lever.co/deepmind/12345"
        assert jobs[0]["platform"] == "Simplify / Direct ATS"
        assert jobs[0]["work_type"] == "Remote"


def test_jobspy_live_bridge_returns_clean_job_dictionaries():
    """Verify JobSpy subprocess bridge extracts structured job listings."""
    mock_jobspy_output = "JSON_START" + '[{"title": "Python Developer", "company": "Stripe", "location": "Remote", "url": "https://stripe.com/jobs/99", "salary_raw": "$120k", "site": "Indeed", "date_posted": "2026-03-05"}]'

    with patch("pathlib.Path.exists", return_value=True), \
         patch("subprocess.run") as mock_run:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = mock_jobspy_output
        mock_run.return_value = mock_proc

        jobs = _harvest_jobspy_live(role="python", location="remote", limit=2)
        assert len(jobs) == 1
        assert jobs[0]["title"] == "Python Developer"
        assert jobs[0]["company"] == "Stripe"
        assert jobs[0]["url"] == "https://stripe.com/jobs/99"
        assert jobs[0]["platform"] == "Indeed"


def test_search_and_harvest_jobs_combines_and_deduplicates_feeds():
    """Verify search_and_harvest_jobs merges direct ATS and consumer boards with deduplication."""
    mock_ats = [
        {"title": "Software Engineer", "company": "Databricks", "url": "https://jobs.lever.co/databricks/1", "location": "Remote", "work_type": "Remote", "platform": "Simplify / Direct ATS", "salary": "$150k"}
    ]
    mock_jobspy = [
        # Duplicate of above (same company & title)
        {"title": "Software Engineer", "company": "Databricks", "url": "https://indeed.com/databricks", "location": "Remote", "work_type": "Remote", "platform": "JobSpy", "salary": "$150k"},
        # Unique role
        {"title": "ML Engineer", "company": "Snowflake", "url": "https://indeed.com/snowflake", "location": "Remote", "work_type": "Remote", "platform": "JobSpy", "salary": "$160k"}
    ]

    with patch("tools.career_tools._harvest_simplify_jobs", return_value=mock_ats), \
         patch("tools.career_tools._harvest_jobspy_live", return_value=mock_jobspy), \
         patch("tools.career_tools._load_local_zjob_data", return_value=[]), \
         patch("tools.career_tools._fetch_live_remoteok", return_value=[]):

        res = search_and_harvest_jobs(role="engineer", location="remote", limit=5, save_to_desktop=False)
        assert "Databricks" in res
        assert "Snowflake" in res
        # Databricks should appear only once due to deterministic deduplication
        assert res.count("@ **Databricks**") == 1
        assert res.count("@ **Snowflake**") == 1


def test_human_motion_trajectory_includes_overshoot_settling():
    """Verify human_move_to handles long distances with biological settling."""
    path = generate_human_path(start_x=100, start_y=100, target_x=800, target_y=600, steps=30)
    assert len(path) == 30
    assert path[0] == (100, 100)
    assert path[-1] == (800, 600)

    # Move with biological overshoot logic
    with patch("pyautogui.position") as mock_pos, \
         patch("pyautogui.moveTo") as mock_move, \
         patch("tools.human_motion.random.random", return_value=0.1):  # Trigger overshoot (< 0.40)
        mock_p = MagicMock()
        mock_p.x, mock_p.y = 100, 100
        mock_pos.return_value = mock_p

        previous_mode = safety.autonomous_mode_enabled
        safety.set_desktop_control(True)
        try:
            msg = human_move_to(target_x=900, target_y=700, speed="fast")
        finally:
            safety.set_desktop_control(previous_mode)
        assert "Moved smoothly" in msg
        assert mock_move.call_count >= 20
