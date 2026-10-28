"""
SpaceV Multi-Agent Swarm Configuration (Volume I §8 & Volume III §23).
Defines specialized roles, system prompts, token budgets, and tool access:
  - Planner: Goal decomposition, dependency analysis, workflow construction (800 token budget)
  - Coder: Focused code editing, tool execution, minimal responses (1200 token budget)
  - Auditor: Verification, test execution, pass/fail evidence analysis (600 token budget)
  - Conductor: Meta-orchestrator coordinating the swarm
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class AgentRole(str, Enum):
    PLANNER = "planner"
    CODER = "coder"
    AUDITOR = "auditor"
    CONDUCTOR = "conductor"


@dataclass
class AgentConfig:
    """Configuration contract for a specialized agent within the SpaceV swarm."""
    role: AgentRole
    name: str
    system_prompt: str

    # LLM Routing Configuration
    preferred_provider: str = "cloud"     # "cloud" | "local" | "auto"
    preferred_model: str = ""             # Specific model ID or empty for auto-select

    # Token Budgets (Strictly bounded to prevent TPM exhaustion)
    max_tokens_per_turn: int = 1500       # Max total tokens per turn
    max_input_tokens: int = 1200          # Max input tokens before compression
    max_tokens_per_task: int = 5000       # Max total tokens across task lifecycle
    max_output_tokens: int = 400          # Output token ceiling

    # Scoped Tools
    allowed_tools: list[str] = field(default_factory=list)

    # Execution Parameters
    temperature: float = 0.2
    max_retries: int = 2
    timeout_sec: float = 60.0


# ═══════════════════════════════════════════════════════════════════
# PRE-CONFIGURED AGENTS
# ═══════════════════════════════════════════════════════════════════

PLANNER_AGENT_CONFIG = AgentConfig(
    role=AgentRole.PLANNER,
    name="SpaceV Planner",
    system_prompt="""You are the SpaceV Planner Agent. Your role is to decompose complex user goals
into structured, executable task plans.

RULES:
1. Break goals into 3-7 atomic steps (never more than 7)
2. Identify which steps can run in parallel
3. Specify dependencies between steps
4. Estimate token cost for each step
5. Flag steps that need human approval (file deletion, destructive shell commands)
6. Output structured JSON with steps, dependencies, and agent assignments

OUTPUT FORMAT:
{
  "goal": "...",
  "steps": [
    {"id": "s1", "action": "...", "agent": "coder|auditor", "depends_on": [], "estimated_tokens": 800}
  ]
}

Keep your response under 300 tokens. Be precise, not verbose.""",
    preferred_provider="cloud",
    preferred_model="gemini-1.5-flash",
    max_tokens_per_turn=1000,
    max_input_tokens=800,
    max_output_tokens=300,
    temperature=0.2,
    allowed_tools=[],  # Planner designs plans without invoking tools directly
)

CODER_AGENT_CONFIG = AgentConfig(
    role=AgentRole.CODER,
    name="SpaceV Coder",
    system_prompt="""You are the SpaceV Coder Agent. You execute code modifications and tool calls.

RULES:
1. Execute exactly what the plan specifies
2. Use the minimum number of tool calls needed
3. Always verify tool results before proceeding
4. If a tool fails, report the error — do NOT retry blindly without instruction
5. Keep your responses under 200 tokens

You have access to: file operations, shell commands, code editing, and web search.""",
    preferred_provider="auto",
    preferred_model="",
    max_tokens_per_turn=1500,
    max_input_tokens=1200,
    max_output_tokens=400,
    temperature=0.1,
    allowed_tools=[
        "read_file", "write_file", "edit_file", "list_directory",
        "run_command", "search_web", "search_file_content", "create_file",
        "run_python_script", "execute_terminal_command"
    ],
)

AUDITOR_AGENT_CONFIG = AgentConfig(
    role=AgentRole.AUDITOR,
    name="SpaceV Auditor",
    system_prompt="""You are the SpaceV Auditor Agent. You verify that work was done correctly with empirical evidence.

RULES:
1. Check that the output matches the original goal
2. Run tests if available
3. Verify file changes are syntactically and structurally correct
4. Report PASS or FAIL with specific evidence
5. Keep your response under 150 tokens

Output format:
{"verdict": "PASS|FAIL", "evidence": "...", "issues": [...]}""",
    preferred_provider="local",
    preferred_model="qwen2.5:3b",
    max_tokens_per_turn=800,
    max_input_tokens=600,
    max_output_tokens=150,
    temperature=0.1,
    allowed_tools=["read_file", "run_command", "search_file_content", "read_file_content"],
)

AGENT_CONFIGS: dict[AgentRole, AgentConfig] = {
    AgentRole.PLANNER: PLANNER_AGENT_CONFIG,
    AgentRole.CODER: CODER_AGENT_CONFIG,
    AgentRole.AUDITOR: AUDITOR_AGENT_CONFIG,
}
