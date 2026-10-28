"""
SpaceV Agent Dashboard & Telemetry HUD Verification Suite.
Validates:
  - AgentDashboardWidget initialization in headless and GUI runtimes
  - Real-time swarm role status transitions
  - Workflow progress percentage and node ratio tracking
  - Token reduction and session budget updates
  - Perception sensor status management
"""
from __future__ import annotations

from ui.agent_dashboard import AgentDashboardWidget


def test_agent_dashboard_initialization_and_state():
    """Verify clean initialization and default telemetry states."""
    dashboard = AgentDashboardWidget()
    state = dashboard.get_state()

    assert state["swarm"]["planner"] == "IDLE"
    assert state["swarm"]["coder"] == "IDLE"
    assert state["swarm"]["auditor"] == "IDLE"

    assert state["workflow"]["name"] == "None"
    assert state["workflow"]["progress"] == (0, 0)

    assert state["tokens"]["session_total"] == 0
    assert state["perception"]["fs_watcher"] is True


def test_agent_dashboard_updates():
    """Verify dynamic updates to swarm, workflow, tokens, and perception."""
    dashboard = AgentDashboardWidget()

    # 1. Update Swarm Status
    dashboard.update_agent_status("planner", "running")
    dashboard.update_agent_status("coder", "completed")
    state = dashboard.get_state()
    assert state["swarm"]["planner"] == "RUNNING"
    assert state["swarm"]["coder"] == "COMPLETED"

    # 2. Update Workflow Progress
    dashboard.update_workflow_progress("CI Pipeline", completed_nodes=3, total_nodes=4)
    state = dashboard.get_state()
    assert state["workflow"]["name"] == "CI Pipeline"
    assert state["workflow"]["progress"] == (3, 4)

    # 3. Update Token Metrics
    dashboard.update_token_metrics(used_session=4200, reduction_percent=82.4)
    state = dashboard.get_state()
    assert state["tokens"]["session_total"] == 4200
    assert state["tokens"]["avg_reduction"] == "82.4%"

    # 4. Update Perception Status
    dashboard.update_perception_status(fs=True, term=False, screen=True)
    state = dashboard.get_state()
    assert state["perception"]["fs_watcher"] is True
    assert state["perception"]["terminal_monitor"] is False
    assert state["perception"]["screen_observer"] is True
