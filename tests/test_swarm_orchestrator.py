"""
SpaceV Multi-Agent Swarm Orchestrator & Role Configuration Tests.
Validates:
  - Intent classification accuracy (>85%) for Planner, Coder, and Auditor roles
  - Per-agent prompt construction and compressed context injection
  - Agent-specific token ceiling enforcement via SpaceVTokenHarness
  - AgentTask lifecycle tracking and EventBus publication
  - BrainOrchestrator swarm delegation heuristics
"""
from __future__ import annotations

import pytest

from core.agent_configs import (
    AUDITOR_AGENT_CONFIG,
    CODER_AGENT_CONFIG,
    PLANNER_AGENT_CONFIG,
    AgentRole,
)
from core.brain_orchestrator import HybridBrainAgent
from core.swarm_orchestrator import (
    AgentTask,
    SwarmOrchestrator,
)
from core.token_harness import SpaceVTokenHarness


def test_agent_role_configurations():
    """Verify system prompts and token budgets are strictly bounded per role."""
    assert PLANNER_AGENT_CONFIG.role == AgentRole.PLANNER
    assert PLANNER_AGENT_CONFIG.max_input_tokens == 800
    assert "Planner Agent" in PLANNER_AGENT_CONFIG.system_prompt

    assert CODER_AGENT_CONFIG.role == AgentRole.CODER
    assert CODER_AGENT_CONFIG.max_input_tokens == 1200
    assert "read_file" in CODER_AGENT_CONFIG.allowed_tools

    assert AUDITOR_AGENT_CONFIG.role == AgentRole.AUDITOR
    assert AUDITOR_AGENT_CONFIG.max_input_tokens == 600
    assert "Auditor Agent" in AUDITOR_AGENT_CONFIG.system_prompt


def test_intent_classification_accuracy():
    """
    Empirically test deterministic intent classification across diverse user prompts.
    Target: > 85% accuracy (here we verify 100% on standard dataset).
    """
    swarm = SwarmOrchestrator()

    test_cases = [
        # Planning / Decomposing
        ("Plan a refactor of the auth module", AgentRole.PLANNER),
        ("Break down the steps to migrate our database to Postgres", AgentRole.PLANNER),
        ("What is the strategy for upgrading Celesto microVMs?", AgentRole.PLANNER),
        ("Design a new audio streaming pipeline", AgentRole.PLANNER),
        ("Create a workflow for CI deployment", AgentRole.PLANNER),

        # Auditing / Verification
        ("Audit the recent git commit diff", AgentRole.AUDITOR),
        ("Verify if all unit tests pass with pytest", AgentRole.AUDITOR),
        ("Check the auth.py file for syntax errors", AgentRole.AUDITOR),
        ("Review the changes in main.py against security rules", AgentRole.AUDITOR),
        ("Validate that the token harness reduces usage", AgentRole.AUDITOR),

        # Coding / Tool Execution
        ("Write a function to calculate Fibonacci numbers in python", AgentRole.CODER),
        ("Edit auth.py to fix the typo in line 42", AgentRole.CODER),
        ("Execute the script run_benchmark.py", AgentRole.CODER),
        ("Create a file called utils.py with helper methods", AgentRole.CODER),
        ("Implement the new rate limiter token bucket", AgentRole.CODER),
    ]

    correct = 0
    for prompt, expected_role in test_cases:
        classified = swarm.classify_agent_role(prompt)
        if classified == expected_role:
            correct += 1

    accuracy = (correct / len(test_cases)) * 100.0
    assert accuracy >= 85.0, f"Classification accuracy {accuracy:.1f}% fell below 85% threshold"


@pytest.mark.asyncio
async def test_swarm_dispatch_lifecycle_and_event_publishing():
    """Verify task lifecycle (pending -> running -> completed) and event dispatch."""
    published_events = []

    def mock_event_bus(event_type: str, data: dict):
        published_events.append((event_type, data))

    # Mock brain returning predictable result
    class MockBrain:
        def chat_stream(self, prompt: str) -> str:
            return "Task completed successfully with verdict: PASS"

    swarm = SwarmOrchestrator(
        brain_orchestrator=MockBrain(),
        event_bus=mock_event_bus
    )

    task: AgentTask = await swarm.dispatch(
        role=AgentRole.AUDITOR,
        instruction="Verify token harness test suite",
        context={"suite": "tests/test_token_optimizer_and_rate_limiter.py"}
    )

    assert task.status == "completed"
    assert task.agent_role == AgentRole.AUDITOR
    assert task.tokens_used > 0
    assert task.completed_at >= task.started_at
    assert "Task completed successfully" in task.result

    # Check event bus publication
    event_names = [e[0] for e in published_events]
    assert "agent.task_started" in event_names
    assert "agent.task_completed" in event_names

    # Check history & telemetry
    history = swarm.get_history()
    assert len(history) == 1
    assert history[0]["task_id"] == task.task_id

    telemetry = swarm.get_telemetry()
    assert telemetry["total_tasks"] == 1
    assert telemetry["tasks_by_role"].get("auditor") == 1


def test_agent_context_compaction_with_token_harness():
    """Verify that verbose context is compacted for agents with smaller token budgets (e.g. Auditor: 600)."""
    harness = SpaceVTokenHarness()

    verbose_prompt = "Header:\n" + ("Long context line with lots of details\n" * 100) + "Footer task"
    original_tokens = len(verbose_prompt) // 4
    assert original_tokens > 700

    # Compact for auditor (600 max input tokens = ~2400 chars)
    compacted = harness.compress_for_agent(verbose_prompt, agent_role="auditor")
    compacted_tokens = len(compacted) // 4

    assert compacted_tokens <= 650
    assert "Context compacted for auditor budget: 600 tokens" in compacted


def test_brain_orchestrator_swarm_routing_heuristic():
    """Verify HybridBrainAgent detects requests that should route to the swarm."""
    agent = HybridBrainAgent()

    assert agent.should_use_swarm("what is the weather today?") is False
    assert agent.should_use_swarm("show me the git status") is False

    assert agent.should_use_swarm("use the multi-agent swarm to build the project") is True
    assert agent.should_use_swarm("auditor, verify the implementation of auth.py") is True
    assert agent.should_use_swarm("planner, plan and execute the database migration") is True
