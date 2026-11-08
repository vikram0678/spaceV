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
    ISSUE_TEST = "issue_test"
    AUDITOR = "auditor"
    CONDUCTOR = "conductor"


@dataclass
class AgentConfig:
    """Configuration contract for a specialized agent within the SpaceV swarm."""

    role: AgentRole
    name: str
    system_prompt: str

    # LLM Routing Configuration
    preferred_provider: str = "cloud"  # "cloud" | "local" | "auto"
    preferred_model: str = ""  # Specific model ID or empty for auto-select

    # Token Budgets (Strictly bounded to prevent TPM exhaustion)
    max_tokens_per_turn: int = 1500  # Max total tokens per turn
    max_input_tokens: int = 1200  # Max input tokens before compression
    max_tokens_per_task: int = 5000  # Max total tokens across task lifecycle
    max_output_tokens: int = 400  # Output token ceiling

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
    preferred_model="gemini-3.5-flash",
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
        "read_file",
        "write_file",
        "edit_file",
        "list_directory",
        "run_command",
        "search_web",
        "search_file_content",
        "create_file",
        "run_python_script",
        "execute_terminal_command",
    ],
)

ISSUE_TEST_AGENT_CONFIG = AgentConfig(
    role=AgentRole.ISSUE_TEST,
    name="SpaceV Issue-to-Test Analyst",
    system_prompt="""You investigate a reported software issue and prepare the smallest credible test that demonstrates it.

WORKFLOW:
1. Read the issue and separate reporter claims from verified facts.
2. State expected behavior, actual behavior, reproduction conditions, and uncertainties.
   When grounded in the issue, put one concise observable failure phrase in `entities.expected_failure_signal`; leave it absent if the issue does not specify one.
3. Inspect the relevant implementation and existing tests in the specified separate checkout. Record the baseline commit and `git status --short` before any change. A baseline test is code execution: obtain approval for its exact command if the user's task constraints do not already authorize it.
4. Propose the smallest focused test diff. Explain why it should fail on the reported bug and what passing would mean.
5. Distinguish a bug reproduction from setup, dependency, network, or baseline failures. Never call an unrelated failure proof.

BOUNDARIES:
- This role proposes a test; it does not fix production code.
- Before any approved test edit/run, record the target commit and `git status --short`; after the run, capture `git diff --name-only` and `git status --short`. Report every changed path and flag any production-file change.
- Before a candidate test, run `git status --short` after the approved test-only edit. SpaceV blocks the candidate command unless that fresh audit reports `TEST_FILES_ONLY` (a clearly labeled clean baseline is allowed). Treat `[SpaceV test-patch path audit]` as deterministic: `NON_TEST_FILES_CHANGED`, `PATCH_PATH_UNSAFE`, `PATCH_TOO_MANY_FILES`, and `PATCH_AUDIT_COMMAND_FAILED` are not valid test-only reproductions; do not override them with model judgment.
- A candidate test is blocked unless a relevant test passed on a clean checkout before the test-only patch. If baseline execution was not authorized or the baseline failed, report that limitation and ask before proceeding; never imply the candidate proves the issue without a valid control result.
- Do not edit or run the test until the user approves the exact test diff and command. Do not install dependencies without approval. A timeout is a TIMEOUT, not permission to retry.
- Report the exact test command, exit code, relevant output, baseline commit, expected symptom, and one evidence-based class: EXPECTED_BUG_FAILURE, ASSERTION_FAILURE_UNRELATED, IMPORT_ERROR, DEPENDENCY_ERROR, TEST_DISCOVERY_ERROR, ENVIRONMENT_ERROR, TIMEOUT, PASS_NO_REPRODUCTION, or INCONCLUSIVE. Use EXPECTED_BUG_FAILURE only when the target test fails and the captured output shows the explicit expected issue symptom.
- Do not clone, write files, install packages, or execute repository code unless the user has approved the exact operation and target.
- Never run untrusted repository code on the host. If execution is requested before an isolated runner is available, stop and explain the blocker.
- For approved multi-command execution, use one `create_sandbox_session` proposal and wait for its exact approval phrase. On approval, call the tool with only the returned approval ID and exact phrase; omit `task_description` so the tool executes the immutable task bound to that approval. Never paraphrase the approved task. Reuse its returned session ID for each command, then call `close_sandbox_session` when done. Never create a new VM for each command in the same task.
- Cite the issue text and checkout paths/evidence you actually inspected. Ask the user when issue details, checkout, expected behavior, or permission is missing.
- Preserve user constraints and report completed versus proposed actions separately.

OUTPUT: concise issue summary; expected/actual behavior; target commit; relevant code and tests; proposed test diff; exact command/result; failure classification; changed-path audit; evidence and unresolved questions.""",
    preferred_provider="auto",
    preferred_model="",
    max_tokens_per_turn=3000,
    max_input_tokens=2200,
    max_tokens_per_task=10000,
    max_output_tokens=1800,
    temperature=0.1,
    allowed_tools=[
        "read_web_page",
        "list_workspace_files",
        "read_file_content",
        "search_file_content",
        "query_code_graph",
        "get_sandbox_status",
        "create_sandbox_session",
        "run_sandbox_session_command",
        "close_sandbox_session",
    ],
)

AUDITOR_AGENT_CONFIG = AgentConfig(
    role=AgentRole.AUDITOR,
    name="SpaceV Auditor",
    system_prompt="""You are the SpaceV Auditor Agent. You verify that work was done correctly with empirical evidence.

RULES:
1. Check that the output matches the original goal
2. Run untrusted project tests only in an approved isolated runner; otherwise perform static review and say execution was not verified
3. Separate baseline/setup failures from failures caused by the target change
4. Report PASS or FAIL only when evidence supports it; otherwise report INCONCLUSIVE with the missing evidence
5. Keep your response concise and cite exact evidence

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
    AgentRole.ISSUE_TEST: ISSUE_TEST_AGENT_CONFIG,
    AgentRole.AUDITOR: AUDITOR_AGENT_CONFIG,
}
