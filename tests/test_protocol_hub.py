"""Tests for Standardized Protocol Hub (FastMCP, A2A v1.0, CodeAct)."""

from __future__ import annotations

import pytest

from core.protocol_hub import (
    A2ATask,
    A2ATaskStatus,
    AgentCard,
    DynamicMCPTool,
    UniversalProtocolHub,
)


@pytest.mark.asyncio
async def test_fastmcp_dynamic_tool_registration_and_execution():
    hub = UniversalProtocolHub()

    # Define a normal Python function with type hints
    async def calculate_blast_radius(symbol: str, depth: int = 1) -> dict[str, Any]:
        """Calculates affected components for a given symbol."""
        return {"symbol": symbol, "depth": depth, "affected": [f"{symbol}_downstream"]}

    # Register dynamically - Pydantic model is auto-generated!
    tool = hub.register_tool(calculate_blast_radius)
    assert tool.name == "calculate_blast_radius"
    assert "Calculates affected components" in tool.description

    # Check MCP descriptor conforming to JSON-RPC standard
    descriptor = tool.to_mcp_descriptor()
    assert descriptor["name"] == "calculate_blast_radius"
    assert "properties" in descriptor["inputSchema"]
    assert "symbol" in descriptor["inputSchema"]["properties"]
    assert "depth" in descriptor["inputSchema"]["properties"]

    # Execute tool through protocol hub
    res = await hub.invoke_tool("calculate_blast_radius", symbol="core_engine", depth=2)
    assert res["symbol"] == "core_engine"
    assert res["depth"] == 2
    assert "core_engine_downstream" in res["affected"]


@pytest.mark.asyncio
async def test_fastmcp_rejects_invalid_arguments():
    hub = UniversalProtocolHub()

    def greet(name: str, count: int) -> str:
        return f"Hello {name} " * count

    hub.register_tool(greet)

    # Missing required argument 'count'
    with pytest.raises(Exception):
        await hub.invoke_tool("greet", name="Nandi")


@pytest.mark.asyncio
async def test_a2a_agent_card_registration_and_delegation():
    hub = UniversalProtocolHub()

    # Define an agent card for a specialized researcher agent
    researcher_card = AgentCard(
        agent_id="agent-researcher-01",
        name="Security Vulnerability Researcher",
        description="Scans codebases for CVE patterns and insecure dependencies.",
        capabilities=["cve-scan", "dependency-audit"],
    )

    # Define agent execution handler
    async def researcher_handler(task: A2ATask) -> dict[str, Any]:
        target = task.payload.get("target_path", ".")
        return {"findings": 0, "status": "SECURE", "scanned_path": target}

    # Register under A2A protocol
    hub.register_agent(researcher_card, researcher_handler)

    agents = hub.list_agents()
    assert len(agents) == 1
    assert agents[0].name == "Security Vulnerability Researcher"

    # Dispatch A2A task from Coordinator
    task = A2ATask(
        task_id="task-001",
        sender_agent_id="coordinator",
        target_agent_id="agent-researcher-01",
        action="cve-scan",
        payload={"target_path": "src/auth"},
    )

    completed_task = await hub.delegate_task(task)
    assert completed_task.status == A2ATaskStatus.COMPLETED
    assert completed_task.result["status"] == "SECURE"
    assert completed_task.result["scanned_path"] == "src/auth"


@pytest.mark.asyncio
async def test_a2a_rejects_unregistered_agent():
    hub = UniversalProtocolHub()
    task = A2ATask(
        task_id="task-002",
        sender_agent_id="coordinator",
        target_agent_id="unknown-agent",
        action="execute",
        payload={},
    )
    res = await hub.delegate_task(task)
    assert res.status == A2ATaskStatus.REJECTED
    assert "not registered in A2A roster" in res.error


def test_codeact_sandboxed_execution():
    hub = UniversalProtocolHub()
    script = """
import math
result = math.sqrt(144)
print(f"Calculated: {result}")
"""
    res = hub.execute_codeact(script)
    assert res["success"] is True
    assert "Calculated: 12.0" in res["stdout"]
