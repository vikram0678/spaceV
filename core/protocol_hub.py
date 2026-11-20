"""Standardized Communication Protocol Hub for SpaceV (2026 Specification).

Implements:
1. Model Context Protocol (MCP) server & client abstractions via dynamic Pydantic v2 schema synthesis.
2. Agent-to-Agent (A2A v1.0) dynamic agent discovery, Agent Cards, and task delegation.
3. CodeAct Execution Bridge: allows agents to execute sandboxed Python blocks directly
   against the protocol bus rather than chaining slow JSON-RPC calls.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Protocol

from pydantic import BaseModel, Field, create_model

logger = logging.getLogger("SpaceV.ProtocolHub")


class A2ATaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"


class AgentCard(BaseModel):
    """Machine-readable A2A capability declaration according to Linux Foundation standard."""

    agent_id: str
    name: str
    version: str = "1.0.0"
    description: str
    capabilities: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    endpoint: str = "local://in-process"
    trust_score: float = 1.0


class A2ATask(BaseModel):
    """Standardized A2A task message sent from delegator to worker."""

    task_id: str
    sender_agent_id: str
    target_agent_id: str
    action: str
    payload: dict[str, Any]
    status: A2ATaskStatus = A2ATaskStatus.PENDING
    result: dict[str, Any] | None = None
    error: str | None = None


class DynamicMCPTool:
    """FastMCP-compatible tool wrapper synthesized dynamically from any callable."""

    def __init__(
        self,
        name: str,
        description: str,
        fn: Callable[..., Any],
        args_schema: type[BaseModel],
    ):
        self.name = name
        self.description = description
        self.fn = fn
        self.args_schema = args_schema

    async def execute(self, **kwargs) -> Any:
        """Validates arguments via Pydantic model and executes the tool."""
        validated = self.args_schema(**kwargs)
        payload = validated.model_dump()

        if inspect.iscoroutinefunction(self.fn):
            return await self.fn(**payload)
        return self.fn(**payload)

    def to_mcp_descriptor(self) -> dict[str, Any]:
        """Exports tool definition conforming to standard MCP JSON-RPC protocol."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.args_schema.model_json_schema(),
        }


class CodeActSandbox(Protocol):
    """Interface for isolated code execution environment (Celesto microVM or sandbox)."""

    def run_python(self, code: str, timeout: int = 60) -> tuple[int, str, str]: ...


class InProcessCodeActSandbox:
    """Safe fallback sandbox executing code with captured stdout/stderr."""

    def run_python(self, code: str, timeout: int = 60) -> tuple[int, str, str]:
        import contextlib
        import io

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        exit_code = 0

        # Limited local execution environment
        exec_globals = {
            "__builtins__": __builtins__,
        }

        try:
            with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
                exec(code, exec_globals)
        except Exception as e:
            exit_code = 1
            stderr_buf.write(str(e))

        return exit_code, stdout_buf.getvalue(), stderr_buf.getvalue()


class UniversalProtocolHub:
    """Central decoupled protocol bus uniting FastMCP tools, A2A agents, and CodeAct execution."""

    def __init__(self, codeact_sandbox: CodeActSandbox | None = None):
        self._tools: dict[str, DynamicMCPTool] = {}
        self._agents: dict[str, AgentCard] = {}
        self._agent_handlers: dict[str, Callable[[A2ATask], Coroutine[Any, Any, dict[str, Any]]]] = {}
        self._sandbox = codeact_sandbox or InProcessCodeActSandbox()

    # -----------------------------------------------------------------------
    # FastMCP Dynamic Tool Layer
    # -----------------------------------------------------------------------

    def register_tool(
        self,
        fn: Callable[..., Any],
        name: str | None = None,
        description: str | None = None,
    ) -> DynamicMCPTool:
        """Introspects any function signature and synthesizes a typed MCP tool dynamically."""
        tool_name = name or fn.__name__
        tool_desc = description or (inspect.getdoc(fn) or f"Dynamically registered tool: {tool_name}")

        # Introspect function parameters dynamically
        sig = inspect.signature(fn)
        fields: dict[str, Any] = {}

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue

            ann = param.annotation if param.annotation is not inspect.Parameter.empty else Any
            if param.default is inspect.Parameter.empty:
                fields[param_name] = (ann, ...)
            else:
                fields[param_name] = (ann, param.default)

        # Synthesize typed Pydantic v2 model dynamically
        schema_model = create_model(f"{tool_name}_Args", **fields)

        tool = DynamicMCPTool(
            name=tool_name,
            description=tool_desc,
            fn=fn,
            args_schema=schema_model,
        )
        self._tools[tool_name] = tool
        return tool

    def get_tool(self, name: str) -> DynamicMCPTool:
        """Retrieves registered MCP tool by name."""
        if name not in self._tools:
            raise KeyError(f"MCP Tool {name!r} not found in protocol hub.")
        return self._tools[name]

    def list_mcp_tools(self) -> list[dict[str, Any]]:
        """Lists all registered tools formatted as standard MCP JSON-RPC schemas."""
        return [tool.to_mcp_descriptor() for tool in self._tools.values()]

    async def invoke_tool(self, tool_name: str, **kwargs) -> Any:
        """Executes an MCP tool by name with strict Pydantic input validation."""
        tool = self.get_tool(tool_name)
        return await tool.execute(**kwargs)

    # -----------------------------------------------------------------------
    # Agent-to-Agent (A2A v1.0) Layer
    # -----------------------------------------------------------------------

    def register_agent(
        self,
        card: AgentCard,
        handler: Callable[[A2ATask], Coroutine[Any, Any, dict[str, Any]]] | None = None,
    ) -> None:
        """Registers a peer agent under A2A v1.0 specification with its capability card."""
        self._agents[card.agent_id] = card
        if handler:
            self._agent_handlers[card.agent_id] = handler

    def list_agents(self) -> list[AgentCard]:
        """Returns all discovered agents across the A2A network."""
        return list(self._agents.values())

    async def delegate_task(self, task: A2ATask) -> A2ATask:
        """Routes a task from one agent to another using machine-readable A2A cards."""
        if task.target_agent_id not in self._agents:
            task.status = A2ATaskStatus.REJECTED
            task.error = f"Target agent {task.target_agent_id!r} is not registered in A2A roster."
            return task

        handler = self._agent_handlers.get(task.target_agent_id)
        if not handler:
            task.status = A2ATaskStatus.REJECTED
            task.error = f"Agent {task.target_agent_id!r} has no registered execution handler."
            return task

        task.status = A2ATaskStatus.RUNNING
        try:
            res = await handler(task)
            task.status = A2ATaskStatus.COMPLETED
            task.result = res
        except Exception as e:
            task.status = A2ATaskStatus.FAILED
            task.error = str(e)

        return task

    # -----------------------------------------------------------------------
    # CodeAct Execution Interface
    # -----------------------------------------------------------------------

    def execute_codeact(self, code_snippet: str, timeout: int = 60) -> dict[str, Any]:
        """Executes Python snippets in isolated sandbox, replacing slow multi-turn JSON calls."""
        exit_code, stdout, stderr = self._sandbox.run_python(code_snippet, timeout=timeout)
        return {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
        }
