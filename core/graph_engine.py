"""
LangGraph Production Multi-Step Cyclic State Machine for SpaceV.
Coordinates Fast-Path dispatching, closed-loop Perception Guards, Ollama model reasoning,
Pydantic tool execution, roadblock clarification, and real-time streaming response synthesis.
"""

import datetime
import json
import logging
import re
import time
import uuid
from collections.abc import Callable
from typing import Any, TypedDict

import requests

logger = logging.getLogger("SpaceV.Graph")

END = "__end__"

try:
    from langgraph.graph import END, StateGraph

    _HAS_LANGGRAPH = True
except ImportError:
    _HAS_LANGGRAPH = False

    class CompiledNativeApp:
        """Native pure-Python state machine runtime that executes LangGraph topology identically."""

        def __init__(self, entry_point, nodes, conditional_edges, direct_edges):
            self.entry_point = entry_point
            self.nodes = nodes
            self.conditional_edges = conditional_edges
            self.direct_edges = direct_edges

        def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
            current = self.entry_point
            current_state = dict(state)
            step = 0
            while current and current != END and step < 30:
                step += 1
                node_fn = self.nodes.get(current)
                if not node_fn:
                    break
                update = node_fn(current_state)
                if isinstance(update, dict):
                    current_state.update(update)

                if current_state.get("is_complete") and current in (
                    "fast_router",
                    "clarification_node",
                    "response_synthesizer",
                ):
                    break

                if current in self.conditional_edges:
                    route_fn, mapping = self.conditional_edges[current]
                    decision = route_fn(current_state)
                    current = mapping.get(decision, END)
                elif current in self.direct_edges:
                    current = self.direct_edges[current]
                else:
                    break
            return current_state

    class StateGraph:
        """Lightweight native builder for LangGraph cyclic state machine topology."""

        def __init__(self, state_schema=None):
            self.state_schema = state_schema
            self.nodes = {}
            self.conditional_edges = {}
            self.direct_edges = {}
            self.entry_point = None

        def add_node(self, name: str, fn: Callable):
            self.nodes[name] = fn

        def set_entry_point(self, name: str):
            self.entry_point = name

        def add_conditional_edges(self, source: str, route_fn: Callable, mapping: dict[str, str]):
            self.conditional_edges[source] = (route_fn, mapping)

        def add_edge(self, source: str, target: str):
            self.direct_edges[source] = target

        def compile(self):
            return CompiledNativeApp(self.entry_point, self.nodes, self.conditional_edges, self.direct_edges)


from config import OLLAMA_BASE_URL, OLLAMA_NUM_CTX
from core.fast_router import FastRouter
from core.model_router import model_router
from core.ollama_client import SYSTEM_PROMPT, OllamaAgent, parse_fallback_tool_calls
from core.proactive_companion import ProactiveCompanion
from core.scratchpad import SpaceVScratchpad, active_scratchpad
from core.task_input import unresolved_template_marker
from core.telemetry import telemetry
from tools.registry import OLLAMA_TOOLS_SCHEMA, execute_tool, get_scoped_tools
from tools.vision_tools import get_active_window_info


class SpaceVState(TypedDict):
    user_prompt: str
    messages: list[dict[str, Any]]
    fast_path_result: tuple | None
    tool_calls: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    active_window: str
    stuck_detected: bool
    clarification_question: str | None
    final_response: str
    iteration: int
    is_complete: bool
    healing_attempts: int
    last_error: str | None
    scratchpad: dict[str, Any]
    goal_contract: dict[str, Any]
    goal_interpretation: str
    specialist_role: str
    environment_evidence: dict[str, Any]
    verification_evidence: dict[str, Any]
    verification_pending: bool
    sandbox_context: str
    task_evidence_context: str
    sandbox_control_call: bool


def determine_tool_status(t_name: str, res: Any) -> str:
    """
    Deterministically evaluates whether a tool execution succeeded, failed, or was blocked.
    Prevents the 'Substring Trap' where reading code containing 'error' or 'except' was falsely marked failed.
    Accurately detects dictionary error envelopes and literal JSON/dict strings.
    """
    if isinstance(res, dict):
        st = str(res.get("status", "")).lower()
        if st in ("error", "failed", "blocked", "invocation_error", "execution_error"):
            return "failed"
        if res.get("error") and not res.get("success", False):
            return "failed"

    res_str = str(res) if res is not None else ""
    if res_str.startswith("SPACEV_NEEDS_USER_INPUT:"):
        return "needs_input"

    # Detect dict-like string representations of error payloads (e.g. from execute_script or JSON)
    stripped = res_str.strip()
    if (stripped.startswith("{") and stripped.endswith("}")) or (stripped.startswith("[") and stripped.endswith("]")):
        try:
            import ast
            parsed = ast.literal_eval(stripped)
            if isinstance(parsed, dict):
                st = str(parsed.get("status", "")).lower()
                if st in ("error", "failed", "blocked", "invocation_error", "execution_error"):
                    return "failed"
                if parsed.get("error") and not parsed.get("success", False):
                    return "failed"
        except Exception:
            pass

    # Special-case read tools: reading code containing 'error', 'failed', 'except' etc. is SUCCESS
    if t_name in ("read_file_content", "view_file"):
        if res_str.startswith("Content of '"):
            return "success"
        if res_str.startswith("Failed") or "could not be found at" in res_str:
            return "failed"
        return "success"

    if t_name in ("list_desktop_files", "list_workspace_files"):
        if res_str.startswith("Failed"):
            return "failed"
        return "success"

    if res_str.startswith(("Failed:", "Error:", "BLOCKED:", "Failed to ", "Folder does not exist:")):
        return "failed"

    first_line = res_str.split("\n", 1)[0].lower() if res_str else ""
    if "permission denied" in first_line or "access is denied" in first_line or "file locked" in first_line:
        return "failed"
    if "could not visually locate" in res_str.lower() or "not in accessibility tree" in res_str.lower():
        return "failed"
    if "command failed with exit code" in res_str.lower():
        return "failed"
    if (
        "exit code:" in res_str.lower()
        and "exit code: 0" not in res_str.lower()
        and "exit code:0" not in res_str.lower()
    ):
        return "failed"
    if res_str.startswith("BLOCKED") or "modal blocker:" in res_str.lower():
        return "blocked"
    return "success"


def sandbox_context_payload(context: str) -> dict[str, Any]:
    """Read the payload from the bounded sandbox continuation record."""
    try:
        _, payload = str(context or "").split("\n", 1)
        decoded = json.loads(payload)
        return decoded if isinstance(decoded, dict) else {}
    except (ValueError, TypeError, json.JSONDecodeError):
        return {}


def sandbox_context_state(context: str) -> str | None:
    """Read the state tag from the persisted sandbox continuation record."""
    return sandbox_context_payload(context).get("state")


def generate_tool_summary(tool_results: list[dict[str, Any]]) -> str:
    """
    Generates a factual, non-hallucinatory summary of executed tools.
    Used during speech synthesis fallback to eliminate phantom successes.
    """
    if not tool_results:
        return ""
    summaries = []
    for t in tool_results:
        name = t.get("name", "")
        args = t.get("args", {})
        raw_res = t.get("result", "")
        res = str(raw_res)
        status = t.get("status", "success")

        if status == "needs_input" or res.startswith("SPACEV_NEEDS_USER_INPUT:"):
            question = res.split("SPACEV_NEEDS_USER_INPUT:", 1)[1].strip() if "SPACEV_NEEDS_USER_INPUT:" in res else res
            summaries.append(question or "I need more information before I can continue.")
            continue

        is_err = status in ("failed", "blocked", "error", "execution_error", "invocation_error")
        if isinstance(raw_res, dict) and (raw_res.get("status") in ("error", "failed", "blocked") or raw_res.get("error")):
            is_err = True
            res = str(raw_res.get("error") or raw_res)

        if "modal blocker:" in res.lower():
            summaries.append(res.replace("⚠️ Modal Blocker:", "").strip())
        elif is_err:
            summaries.append(f"Operation {name} encountered an issue: {res[:80]}")
        elif name == "read_file_content":
            fname = args.get("file_name_or_path") or args.get("file_path") or "file"
            first_line = res.split("\n", 1)[0]
            summaries.append(f"Read {fname} ({first_line})")
        elif name == "list_workspace_files":
            items = [line.strip("- ") for line in res.split("\n") if line.strip().startswith("-")]
            sample = ", ".join(items[:5])
            summaries.append(f"Inspected workspace ({len(items)} files, including {sample})")
        elif name == "list_desktop_files":
            summaries.append(res[:120])
        elif name in ("create_file", "create_folder"):
            target = args.get("file_name") or args.get("folder_name") or "item"
            summaries.append(f"Created {target}")
        elif name in ("execute_terminal_command", "run_python_script", "execute_code_block"):
            cmd = args.get("command") or args.get("file_name_or_path") or "script"
            summaries.append(f"Executed {cmd}")
        else:
            summaries.append(f"Executed {name}")
    summary_text = ". ".join(summaries).strip()
    return summary_text if not summary_text or summary_text.endswith((".", "!", "?")) else summary_text + "."


def sanitize_speech_output(
    text: str, has_error: bool = False, has_tools: bool | None = None, tool_summary: str = ""
) -> str:
    """
    Anti-Leak Shield: Scrubs leaked XML tool tags (<tool_call>, <tools>, <function>)
    and raw JSON payloads before speech synthesis, substituting natural conversational confirmations.
    Never reports false positive success if errors occurred.
    """
    if not text or not isinstance(text, str) or not text.strip():
        if has_error:
            return "Sir, I encountered a roadblock while executing this operation on your workstation. Would you like me to try another approach or guide me on what to do?"
        if has_tools is False:
            return "I understand, Sir. Please let me know what you would like to do next."
        if tool_summary:
            return f"Action completed. {tool_summary}"
        return "Action completed successfully, Sir."
    clean = re.sub(r"<(?:tool_call|tools)>.*?</(?:tool_call|tools)>", "", text, flags=re.DOTALL)
    clean = re.sub(r"<function=.*?>.*?</function>", "", clean, flags=re.DOTALL)
    clean = re.sub(r"</?(?:tool_call|function|parameter|tools)[^>]*>", "", clean).strip()
    if not clean or (clean.startswith("{") and clean.endswith("}")):
        if has_error:
            return "Sir, I encountered a roadblock while executing this operation on your workstation. Please let me know how you would like me to proceed."
        if has_tools is False:
            return "I understand, Sir. Please let me know what you would like to do next."
        if tool_summary:
            return f"Action completed. {tool_summary}"
        return "The requested task has been executed and your workspace is updated, Sir."
    return clean


def prune_conversation_trauma(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Sanitizes previous turn failure trauma and learned helplessness from rolling conversation history.
    Replaces apologies and defeatist error complaints with proactive operational readiness anchors.
    Inspired by Browser-Use and Artemis resilient execution architectures.
    """
    sanitized: list[dict[str, Any]] = []
    apology_triggers = [
        "apologize",
        "sincerely apologize",
        "sorry",
        "unexpected failure",
        "permission denied",
        "errno 13",
        "exit code 126",
        "unable to proceed",
        "failed to execute",
        "error executing",
    ]

    for msg in messages:
        if not isinstance(msg, dict):
            sanitized.append(msg)
            continue

        role = msg.get("role")
        content = msg.get("content")

        if role == "assistant" and isinstance(content, str):
            lower_c = content.lower()
            if any(trig in lower_c for trig in apology_triggers):
                clean_content = (
                    "[Previous Turn Execution Note: A transient execution hurdle occurred in the prior attempt. "
                    "All runtime environments, interpreters, and tools are now operational. "
                    "Proceed proactively to fulfill the user's intent using appropriate tools.]"
                )
                sanitized.append({**msg, "content": clean_content})
                continue

        sanitized.append(msg)

    return sanitized


class SpaceVGraphEngine:
    """
    Production StateGraph engine managing deterministic node execution, closed-loop perception,
    multi-step tool chaining (iteration < 3), and live UI/TTS streaming callbacks.
    """

    def __init__(self, agent: OllamaAgent | None = None):
        self.agent = agent or OllamaAgent()
        self._current_tool_callback: Callable | None = None
        self._current_token_callback: Callable | None = None
        self.workflow = self._build_graph()
        self.app = self.workflow.compile()

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(SpaceVState)

        # 1. Register Explicit Nodes
        workflow.add_node("goal_interpreter", self._goal_interpreter_node)
        workflow.add_node("fast_router", self._fast_router_node)
        workflow.add_node("perception_guard", self._perception_guard_node)
        workflow.add_node("model_reasoning", self._model_reasoning_node)
        workflow.add_node("tool_executor", self._tool_executor_node)
        workflow.add_node("self_healing", self._self_healing_node)
        workflow.add_node("clarification_node", self._clarification_node)
        workflow.add_node("response_synthesizer", self._response_synthesizer_node)

        # 2. Entry Point
        workflow.set_entry_point("goal_interpreter")

        # Model interpretation is the primary route. Deterministic fast routing is
        # retained only for turns the model identifies as conversational.
        workflow.add_conditional_edges(
            "goal_interpreter",
            self._route_after_goal,
            {
                "complete": END,
                "conversational": "fast_router",
                "action": "perception_guard",
                "sandbox_control": "tool_executor",
            },
        )

        # 3. Conditional Edge: Fast-Router (0ms Instant Bypass / Interactive Remediation Resume)
        workflow.add_conditional_edges(
            "fast_router",
            self._route_after_fast_router,
            {"fast_complete": END, "needs_brain": "perception_guard", "direct_tools": "tool_executor"},
        )

        # 4. Conditional Edge: Perception Guard (Roadblock / Modal Check)
        workflow.add_conditional_edges(
            "perception_guard",
            self._route_after_perception,
            {"stuck": "clarification_node", "proceed": "model_reasoning"},
        )

        # 5. Conditional Edge: Model Reasoning (Tools vs Direct Chat vs Anti-Hallucination Loop)
        workflow.add_conditional_edges(
            "model_reasoning",
            self._route_after_reasoning,
            {
                "execute_tools": "tool_executor",
                "loop_reasoning": "model_reasoning",
                "synthesize": "response_synthesizer",
            },
        )

        # 6. Conditional Edge: Tool Executor (Loop Chaining, Self-Healing, or Synthesize)
        workflow.add_conditional_edges(
            "tool_executor",
            self._route_after_tools,
            {
                "stuck": "clarification_node",
                "self_healing": "self_healing",
                "loop_reasoning": "model_reasoning",
                "synthesize": "response_synthesizer",
            },
        )

        # 7. Conditional Edge: Self-Healing Reflection Node
        workflow.add_conditional_edges(
            "self_healing",
            self._route_after_healing,
            {"retry_tool": "tool_executor", "loop_reasoning": "model_reasoning", "escalate": "clarification_node"},
        )

        # 8. Terminal Edges
        workflow.add_edge("clarification_node", END)
        workflow.add_edge("response_synthesizer", END)

        return workflow

    def _goal_interpreter_node(self, state: SpaceVState) -> dict[str, Any]:
        """Convert the user's request into a validated, model-produced goal contract."""
        from core.security_guard import security_guard

        prompt = state.get("user_prompt", "")
        assessment = security_guard.analyze(prompt)
        if not assessment.is_safe:
            blocked_reply = (
                "⚠️ SpaceV Security Protocol Alert: This request was blocked because it matched an unsafe "
                "instruction pattern: "
                f"{', '.join(assessment.detected_patterns)}."
            )
            if self._current_token_callback:
                self._current_token_callback(blocked_reply)
            return {"final_response": blocked_reply, "is_complete": True}

        # Reject unfinished prompt templates before goal interpretation or
        # tool routing. This applies to long requests too; otherwise a failed
        # JSON goal parse could fall through to the model and call status or
        # another unrelated tool while required task input is still missing.
        missing_input_marker = unresolved_template_marker(assessment.sanitized_text)
        if missing_input_marker:
            return {
                "user_prompt": assessment.sanitized_text,
                "goal_contract": {
                    "objective": "Ask the user to replace an unresolved request-template marker.",
                    "steps": [],
                    "success_criteria": ["The user supplies the missing concrete task input."],
                    "entities": {"unresolved_marker": missing_input_marker},
                    "constraints": ["Do not call tools or start a sandbox until the placeholder is replaced."],
                    "tool_domains": [],
                    "requires_action": False,
                    "confidence": 1.0,
                },
                "goal_interpretation": "missing_required_task_input",
                "final_response": (
                    f"I can’t start this task because {missing_input_marker!r} is still a placeholder. "
                    "Replace it with the actual issue text, or remove the no-fetch restriction and explicitly "
                    "allow a read-only fetch. I have not called tools or started a VM."
                ),
                "is_complete": True,
            }

        # Parse GitHub issue links before LLM goal extraction so numeric issue
        # IDs are canonical strings in the structured entity map, and reject
        # lookalike/private/PR URLs before any tool receives them.
        parsed_issue = None
        if re.search(r"\b(?:issue|bug report|issue-to-test|failing test)\b", assessment.sanitized_text, re.IGNORECASE):
            issue_links = re.findall(r"https?://github\.com/[^\s<>\"']+", assessment.sanitized_text, re.IGNORECASE)
            for issue_link in issue_links:
                candidate = issue_link.rstrip(".,;:!?)")
                if re.search(r"/(?:issues|pull)/", candidate, re.IGNORECASE):
                    from core.issue_test_workflow import parse_github_issue_url

                    try:
                        parsed_issue = parse_github_issue_url(candidate)
                    except ValueError as exc:
                        message = f"I did not route this issue link because it is not a supported public GitHub issue URL: {exc}"
                        return {"final_response": message, "is_complete": True}
                    break

        # An exact sandbox approval is a control-plane response, not a new
        # task for the model to reinterpret. Dispatch only the approval-gated
        # session tool; this prevents status/ledger calls from replacing the
        # user's explicit approval and avoids a cloud/model round trip.
        approval_match = re.fullmatch(
            r"approve sandbox task ([a-f0-9]{10})",
            assessment.sanitized_text.strip(),
            flags=re.IGNORECASE,
        )
        if approval_match:
            approval_id = approval_match.group(1).lower()
            approval_text = assessment.sanitized_text.strip()
            from tools.sandbox_tools import sandbox_session_manager

            sandbox_context = sandbox_session_manager.continuation_context(assessment.sanitized_text)
            call_id = f"call_sandbox_approval_{approval_id}"
            call_args = {"approval_id": approval_id, "approval_text": approval_text}
            assistant_call = {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": "create_sandbox_session",
                    "arguments": json.dumps(call_args),
                },
            }
            control_system_message = (
                "Resume the exact approved Celesto task. The tool call below validates and starts only the task "
                "bound to this approval ID. After it succeeds, continue that task using the active session and "
                "guest-command tool. Do not call status, ledger, or create another session."
            )
            if sandbox_context:
                control_system_message += "\n\n" + sandbox_context
            return {
                "user_prompt": assessment.sanitized_text,
                "goal_contract": {
                    "objective": "Resume the exact sandbox task approved by the user.",
                    "steps": [],
                    "success_criteria": ["The approval is validated and its bound task is resumed, or a clear rejection is returned."],
                    "entities": {"approval_id": approval_id},
                    "constraints": ["Use only the immutable task bound to this approval ID."],
                    "tool_domains": ["sandbox"],
                    "requires_action": True,
                    "confidence": 1.0,
                },
                "goal_interpretation": "exact_sandbox_approval",
                "sandbox_context": sandbox_context,
                "messages": [
                    {"role": "system", "content": control_system_message},
                    {"role": "user", "content": approval_text},
                    {"role": "assistant", "content": None, "tool_calls": [assistant_call]},
                ],
                "tool_calls": [
                    {
                        "id": call_id,
                        "function": {
                            "name": "create_sandbox_session",
                            "arguments": call_args,
                        }
                    }
                ],
                "sandbox_control_call": True,
            }

        # A clearly worded request to propose a disposable Celesto VM should
        # also be deterministic. The proposal tool itself only records the
        # task and asks for approval; it does not start a VM. This avoids the
        # model substituting status/ledger lookups for the requested proposal.
        proposal_text = assessment.sanitized_text.strip()
        proposal_lower = proposal_text.casefold()
        is_explicit_vm_proposal = (
            len(proposal_text) <= 800
            and re.search(r"\bpropose\b", proposal_lower)
            and re.search(r"\bcelesto\b", proposal_lower)
            and re.search(r"\b(vm|sandbox|microvm)\b", proposal_lower)
            and re.search(r"\b(clone|inspect|install|read-only|read only|run tests|run the tests)\b", proposal_lower)
        )
        if is_explicit_vm_proposal:
            placeholder = unresolved_template_marker(proposal_text)
            if placeholder:
                return {
                    "final_response": (
                        f"I did not propose or start a VM because the task still contains the unresolved "
                        f"placeholder {placeholder!r}. Replace it with the issue text, or explicitly allow "
                        "a read-only fetch of the public issue, then ask me to prepare the proposal again."
                    ),
                    "goal_interpretation": "missing_required_task_input",
                    "is_complete": True,
                }
        if is_explicit_vm_proposal:
            from tools.sandbox_tools import sandbox_session_manager

            sandbox_context = sandbox_session_manager.continuation_context(proposal_text)
            return {
                "user_prompt": proposal_text,
                "goal_contract": {
                    "objective": "Prepare an approval-gated disposable Celesto VM proposal for the requested task.",
                    "steps": [],
                    "success_criteria": ["A proposal is shown and the system waits for explicit user approval."],
                    "entities": {},
                    "constraints": ["Do not start the VM before approval."],
                    "tool_domains": ["sandbox"],
                    "requires_action": True,
                    "confidence": 1.0,
                },
                "goal_interpretation": "explicit_sandbox_proposal",
                "sandbox_context": sandbox_context,
                "tool_calls": [
                    {
                        "function": {
                            "name": "create_sandbox_session",
                            "arguments": {"task_description": proposal_text},
                        }
                    }
                ],
                "sandbox_control_call": True,
            }

        from core.grounded_agent import interpret_goal

        history = []
        if hasattr(self.agent, "messages") and self.agent.messages:
            history = prune_conversation_trauma(self.agent.messages[-8:])
        sandbox_context = ""
        try:
            from tools.sandbox_tools import sandbox_session_manager

            sandbox_context = sandbox_session_manager.continuation_context(assessment.sanitized_text)
            if sandbox_context:
                history.append({"role": "assistant", "content": sandbox_context})
        except Exception as exc:
            logger.debug("Sandbox continuation context unavailable: %s", exc)
        task_evidence_context = ""
        try:
            from core.task_evidence import task_evidence_store

            task_evidence_context = task_evidence_store.retrieve_context(
                assessment.sanitized_text, recent_history=history
            )
            if task_evidence_context:
                history.append({"role": "assistant", "content": task_evidence_context})
        except Exception as exc:
            logger.warning("Durable task evidence recall unavailable: %s", exc)
        goal, source = interpret_goal(
            assessment.sanitized_text,
            self.agent,
            OLLAMA_BASE_URL,
            OLLAMA_NUM_CTX,
            context_messages=history,
        )
        if parsed_issue:
            goal.entities.update({key: str(value) for key, value in parsed_issue.items()})
        return {
            "user_prompt": assessment.sanitized_text,
            "goal_contract": goal.model_dump(),
            "goal_interpretation": source,
            "sandbox_context": sandbox_context,
            "task_evidence_context": task_evidence_context,
        }

    @staticmethod
    def _route_after_goal(state: SpaceVState) -> str:
        if state.get("is_complete"):
            return "complete"
        if state.get("sandbox_control_call"):
            return "sandbox_control"
        goal = state.get("goal_contract") or {}
        if not goal.get("requires_action", True) and goal.get("confidence", 0.0) >= 0.65:
            return "conversational"
        return "action"

    # ==========================================
    # NODE IMPLEMENTATIONS
    # ==========================================

    def _fast_router_node(self, state: SpaceVState) -> dict[str, Any]:
        """
        Node 1: Evaluates deterministic FastRouter patterns in 0ms.
        Bypasses LLM inference entirely when safe, predictable shortcuts match.
        """
        prompt = state.get("user_prompt", "")
        t_router_start = time.perf_counter()

        # Security Guard Adversarial & Taint Scanner (Upgrade #41)
        from core.security_guard import security_guard

        assessment = security_guard.analyze(prompt)
        if not assessment.is_safe:
            blocked_reply = (
                "⚠️ SpaceV Security Protocol Alert, Sir: A critical adversarial prompt injection or destructive "
                f"system command was intercepted and neutralized ({', '.join(assessment.detected_patterns)})."
            )
            if self._current_token_callback:
                self._current_token_callback(blocked_reply)
            return {
                "fast_path_result": ("security_block", "blocked", blocked_reply),
                "final_response": blocked_reply,
                "is_complete": True,
            }

        prompt = assessment.sanitized_text

        # Interactive Remediation Protocol (IRP): Intercept response to active paused frame
        active_frame = getattr(self.agent, "active_paused_frame", None)
        if active_frame:
            prompt_clean = prompt.strip().lower()
            remediation_options = active_frame.get("remediation_options", [])

            opt1_triggers = ["1", "option 1", "auto", "repair", "auto-repair", "upgrade", "install", "auto-install"]
            opt2_triggers = ["2", "option 2", "alternative", "fallback", "degrade", "other tool", "secondary"]
            opt3_triggers = ["3", "option 3", "continue", "resume", "fixed", "done", "proceed", "retry", "i fixed it"]

            matched_option = None
            if any(prompt_clean == t or prompt_clean.startswith(f"{t} ") for t in opt1_triggers):
                matched_option = 1
            elif any(prompt_clean == t or prompt_clean.startswith(f"{t} ") for t in opt2_triggers):
                matched_option = 2
            elif any(prompt_clean == t or prompt_clean.startswith(f"{t} ") for t in opt3_triggers):
                matched_option = 3

            if matched_option:
                self.agent.active_paused_frame = None  # Consume frame
                t_name = active_frame.get("tool", "")
                t_args = dict(active_frame.get("args", {}))

                if matched_option == 1:
                    opt1 = remediation_options[0] if len(remediation_options) > 0 else {}
                    action_cmd = opt1.get("action", "")
                    if action_cmd:
                        msg = f"Executing auto-repair: `{action_cmd}` and resuming `{t_name}`..."
                        if self._current_token_callback:
                            self._current_token_callback(msg)
                        from tools.registry import execute_tool

                        exec_res = execute_tool("execute_terminal_command", {"command": action_cmd})
                        print(f"[REMEDIATION RESUME] Auto-repair output: {exec_res}")
                        return {
                            "messages": [
                                {"role": "user", "content": active_frame.get("user_prompt", prompt)},
                                {
                                    "role": "assistant",
                                    "content": None,
                                    "tool_calls": [
                                        {
                                            "id": "call_resume",
                                            "type": "function",
                                            "function": {"name": t_name, "arguments": json.dumps(t_args)},
                                        }
                                    ],
                                },
                            ],
                            "tool_calls": [{"function": {"name": t_name, "arguments": t_args}}],
                            "is_complete": False,
                        }
                    else:
                        msg = f"Re-evaluating parameters to resolve `{t_name}` issue..."
                        if self._current_token_callback:
                            self._current_token_callback(msg)
                        return {
                            "messages": [
                                {"role": "user", "content": active_frame.get("user_prompt", prompt)},
                                {
                                    "role": "system",
                                    "content": f"The user requested Option 1 (Retry with Sanitized Parameters) after '{t_name}' failed with args {t_args}. Re-evaluate parameters or use an alternative tool (such as execute_code_block or execute_terminal_command).",
                                },
                            ],
                            "tool_calls": [],
                            "is_complete": False,
                        }
                elif matched_option == 2:
                    opt2 = remediation_options[1] if len(remediation_options) > 1 else {}
                    alt_tool = opt2.get("tool", "read_web_page")
                    alt_args = opt2.get("args", t_args)
                    msg = f"Switching to alternative approach: `{alt_tool}`..."
                    if self._current_token_callback:
                        self._current_token_callback(msg)
                    return {
                        "messages": [
                            {"role": "user", "content": active_frame.get("user_prompt", prompt)},
                            {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_alt",
                                        "type": "function",
                                        "function": {"name": alt_tool, "arguments": json.dumps(alt_args)},
                                    }
                                ],
                            },
                        ],
                        "tool_calls": [{"function": {"name": alt_tool, "arguments": alt_args}}],
                        "is_complete": False,
                    }
                elif matched_option == 3:
                    msg = f"Manual intervention confirmed. Resuming `{t_name}`..."
                    if self._current_token_callback:
                        self._current_token_callback(msg)
                    return {
                        "messages": [
                            {"role": "user", "content": active_frame.get("user_prompt", prompt)},
                            {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_resume",
                                        "type": "function",
                                        "function": {"name": t_name, "arguments": json.dumps(t_args)},
                                    }
                                ],
                            },
                        ],
                        "tool_calls": [{"function": {"name": t_name, "arguments": t_args}}],
                        "is_complete": False,
                    }

        match = FastRouter.match(prompt)
        router_dur_ms = (time.perf_counter() - t_router_start) * 1000.0
        telemetry.record_stage_time("fast_router", router_dur_ms)

        if match:
            tool_name, tool_output, reply = match
            reply = ProactiveCompanion.generate_conversational_wrap(tool_name, reply)

            # Record fast-path tool execution in telemetry for 100% black box flight recorder parity
            status = (
                "failed"
                if any(err in str(tool_output).lower() for err in ["failed", "error", "blocked"])
                else "success"
            )
            telemetry.record_tool_execution(
                name=tool_name,
                args={"prompt": prompt},
                status=status,
                duration_ms=router_dur_ms,
                result_preview=str(tool_output)[:120],
                intercepted_from_xml=False,
            )

            telemetry.hud_badge("ROUTER", f"Match: {tool_name}", router_dur_ms)
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] [FAST ROUTER MATCH]: {tool_name}")

            if self._current_tool_callback:
                self._current_tool_callback(tool_name, {}, tool_output)
            if self._current_token_callback:
                self._current_token_callback(reply)

            # Persist fast-path turn to agent messages for multi-turn context
            if hasattr(self.agent, "messages"):
                self.agent.messages.append({"role": "user", "content": prompt})
                self.agent.messages.append({"role": "assistant", "content": reply})

            return {"fast_path_result": match, "final_response": reply, "is_complete": True}

        return {"fast_path_result": None, "is_complete": False}

    def _route_after_fast_router(self, state: SpaceVState) -> str:
        if state.get("fast_path_result"):
            return "fast_complete"
        if state.get("tool_calls"):
            return "direct_tools"
        return "needs_brain"

    def _perception_guard_node(self, state: SpaceVState) -> dict[str, Any]:
        """
        Node 2: Closed-Loop Perception Guard.
        Inspects active desktop window, detects roadblocks, and feeds perceptual context.
        """
        from core.grounded_agent import evidence_context, inspect_environment

        environment_evidence = inspect_environment()
        win_info = environment_evidence.get("active_window", "unavailable")

        # Universal Gatekeeper Perception Check
        from core.memory import memory
        from core.modal_interceptor import modal_interceptor

        gatekeeper = modal_interceptor.detect()
        if gatekeeper and gatekeeper.is_active:
            pref = memory.get_preference(gatekeeper.domain, gatekeeper.property_key)
            if not pref:
                memory.set_suspended_disambiguation(
                    {
                        "domain": gatekeeper.domain,
                        "property_key": gatekeeper.property_key,
                        "question": gatekeeper.question,
                        "options": gatekeeper.options,
                        "suspended_task": state.get("user_prompt"),
                        "timestamp": datetime.datetime.now().timestamp(),
                    }
                )
                return {
                    "active_window": win_info,
                    "stuck_detected": True,
                    "clarification_question": gatekeeper.question,
                }

        # Reconstitute Scratchpad Working Memory
        scratchpad = SpaceVScratchpad.from_dict(state.get("scratchpad"))
        if not scratchpad.goal:
            scratchpad.set_goal(state.get("user_prompt", ""))

        # Use the model-interpreted sub-goals instead of splitting on connector words.
        goal_contract = state.get("goal_contract") or {}
        if not scratchpad.plan and goal_contract.get("steps"):
            scratchpad.create_plan(goal_contract["steps"])

        scratchpad_context = scratchpad.format_prompt_context()

        # Select a task-specific coding workflow for GitHub issue reproduction.
        # This is prompt specialization only; it does not grant permissions or
        # execute repository code. Tool routing and approval gates remain active.
        specialist_guidance = ""
        specialist_role_name = ""
        try:
            from core.agent_configs import AgentRole
            from core.swarm_orchestrator import swarm_orchestrator

            specialist_role = swarm_orchestrator.classify_agent_role(
                f"{scratchpad.goal}\n{state.get('user_prompt', '')}"
            )
            specialist_role_name = specialist_role.value
            if specialist_role == AgentRole.ISSUE_TEST:
                specialist_guidance = swarm_orchestrator.agents[specialist_role].system_prompt
        except Exception as exc:
            logger.debug("Specialist workflow selection unavailable: %s", exc)

        # Inject perceptual awareness, rolling conversation history, and scratchpad working memory
        messages = list(state.get("messages") or [])
        if not messages:
            sys_content = (
                f"{SYSTEM_PROMPT}\n\n"
                f"[Structured Goal Contract]: {json.dumps(goal_contract, ensure_ascii=False, default=str)}\n\n"
                f"[Pre-action UI and system evidence]: {json.dumps(environment_evidence, ensure_ascii=False, default=str)}"
            )
            if specialist_guidance:
                sys_content += f"\n\n[Selected issue-to-test specialist workflow]\n{specialist_guidance}"
            if scratchpad_context:
                sys_content += f"\n{scratchpad_context}"
            if state.get("sandbox_context"):
                sys_content += f"\n\n{state['sandbox_context']}"
            if state.get("task_evidence_context"):
                sys_content += f"\n\n{state['task_evidence_context']}"

            # Compile rolling conversation history from self.agent.messages for multi-turn interlinking
            history = []
            if hasattr(self.agent, "messages") and self.agent.messages:
                for m in self.agent.messages:
                    if m.get("role") in ("user", "assistant"):
                        history.append(dict(m))
                # Keep last 8 messages (4 turns) for token-efficient cross-turn continuity
                history = history[-8:]
                history = prune_conversation_trauma(history)

            messages = [
                {"role": "system", "content": sys_content},
                *history,
                {"role": "user", "content": state["user_prompt"]},
            ]
        else:
            update_content = (
                f"[Structured Goal Contract]: {json.dumps(goal_contract, ensure_ascii=False, default=str)}\n"
                f"{evidence_context('Pre-action UI and system evidence', environment_evidence)}"
            )
            if specialist_guidance:
                update_content += f"\n\n[Selected issue-to-test specialist workflow]\n{specialist_guidance}"
            if scratchpad_context:
                update_content += f"\n{scratchpad_context}"
            if state.get("sandbox_context"):
                update_content += f"\n\n{state['sandbox_context']}"
            if state.get("task_evidence_context"):
                update_content += f"\n\n{state['task_evidence_context']}"
            messages.append({"role": "system", "content": update_content})

        return {
            "active_window": win_info,
            "environment_evidence": environment_evidence,
            "stuck_detected": False,
            "messages": messages,
            "scratchpad": scratchpad.to_dict(),
            "specialist_role": specialist_role_name,
        }

    def _route_after_perception(self, state: SpaceVState) -> str:
        if state.get("stuck_detected"):
            return "stuck"
        return "proceed"

    def _model_reasoning_node(self, state: SpaceVState) -> dict[str, Any]:
        """
        Node 3: LLM Model Reasoning.
        Sends the prompt and scoped tools to the configured cloud endpoint or Ollama.
        """
        messages = state.get("messages", [])
        prompt = state.get("user_prompt", "")
        goal_contract = state.get("goal_contract") or {}
        needs_tools = bool(goal_contract.get("requires_action", True)) or model_router.needs_tools(prompt)
        if goal_contract.get("requires_action", True):
            from core.grounded_agent import tools_for_goal

            available_tools = tools_for_goal(goal_contract, OLLAMA_TOOLS_SCHEMA)
        else:
            available_tools = get_scoped_tools(prompt, OLLAMA_TOOLS_SCHEMA)

        # Enforce the issue analyst's read-and-propose tool boundary in the
        # actual graph request, not just in its prompt. Test execution remains
        # out of this first-stage workflow until a sandbox runner is connected.
        if state.get("specialist_role") == "issue_test":
            from core.agent_configs import ISSUE_TEST_AGENT_CONFIG

            allowed = set(ISSUE_TEST_AGENT_CONFIG.allowed_tools)
            available_tools = [
                tool for tool in OLLAMA_TOOLS_SCHEMA
                if tool.get("function", {}).get("name") in allowed
            ]

        # Expose sandbox controls only for an explicitly sandbox-scoped goal
        # or a task-matched continuation. Exact approval replies are dispatched
        # deterministically by the goal interpreter, so unrelated web/file
        # requests must not inherit sandbox status/session tools.
        from tools.registry import SANDBOX_TOOL_NAMES

        sandbox_goal = (
            "sandbox" in (goal_contract.get("tool_domains") or [])
            or bool(state.get("sandbox_context"))
        )
        if sandbox_goal:
            if sandbox_context_state(state.get("sandbox_context", "")) == "active_approved_session":
                failed_guest_command = any(
                    item.get("name") == "run_sandbox_session_command"
                    and item.get("status") in ("failed", "blocked", "error")
                    for item in state.get("tool_results", [])
                )
                allowed_active_tools = (
                    {"close_sandbox_session"}
                    if failed_guest_command
                    else {"run_sandbox_session_command", "close_sandbox_session"}
                )
                available_tools = [
                    tool for tool in OLLAMA_TOOLS_SCHEMA
                    if tool.get("function", {}).get("name") in allowed_active_tools
                ]
            else:
                available_tools = [
                    tool for tool in OLLAMA_TOOLS_SCHEMA
                    if tool.get("function", {}).get("name") in SANDBOX_TOOL_NAMES
                ]
        cloud_client = getattr(self.agent, "cloud_client", None)
        use_cloud = getattr(self.agent, "provider", "ollama") != "ollama" and cloud_client is not None

        if use_cloud:
            cloud_model = cloud_client.select_cloud_model(prompt, requires_tools=needs_tools)
            self.agent.model = cloud_model
            self.agent.active_role = "cloud_agent"
            model_tag = cloud_model
        else:
            model_tag = getattr(self.agent, "model", "qwen2.5:3b")

        # Report the model selected for this request, not the agent's stale
        # local default from before cloud routing.
        telemetry.hud_badge("THINKING", f"Querying {model_tag}...")
        t_model_start = time.perf_counter()

        # Configured cloud endpoints (including OpenAI-compatible proxies) use
        # the cloud client; Ollama remains the explicit local-only route.
        if use_cloud:

            scoped_tools = available_tools if needs_tools else None
            from core.token_harness import token_harness, estimate_messages_tokens
            pre_tokens = estimate_messages_tokens(messages)
            opt_messages, opt_tools = token_harness.optimize(
                messages=messages,
                tools=scoped_tools,
                user_prompt=prompt,
            )
            explicit_tool_names = sorted({
                str(tool.get("function", {}).get("name", ""))
                for tool in (scoped_tools or [])
                if tool.get("function", {}).get("name")
                and re.search(
                    rf"(?<![a-z0-9_]){re.escape(str(tool['function']['name']).lower())}(?![a-z0-9_])",
                    prompt.lower(),
                )
            })
            print(
                f"[TOOL ROUTING] scoped={len(scoped_tools or [])}, "
                f"sent={len(opt_tools or [])}, explicitly_named={explicit_tool_names or 'none'}"
            )
            post_tokens = estimate_messages_tokens(opt_messages)
            resp_dict = self.agent.cloud_client.chat(
                messages=opt_messages,
                tools=opt_tools,
                model=cloud_model,
                pre_tokens=pre_tokens,
                post_tokens=post_tokens,
            )
            content = resp_dict.get("content", "")
            tool_calls = resp_dict.get("tool_calls", [])

            if not tool_calls and content:
                extracted, clean = parse_fallback_tool_calls(content)
                if extracted:
                    tool_calls = extracted
                    content = clean
                    for call in tool_calls:
                        fn = call.get("function", {}).get("name", "")
                        if call.get("intercepted_from_xml"):
                            telemetry.record_xml_healing(fn, content[:120])

            model_dur_ms = (time.perf_counter() - t_model_start) * 1000.0
            iter_num = state.get("iteration", 0) + 1
            telemetry.record_stage_time(f"llm_turn_{iter_num}_total", model_dur_ms)
            if iter_num == 1:
                telemetry.record_stage_time("llm_turn_1_ttft", min(model_dur_ms * 0.4, 1500.0))
            telemetry.hud_badge("MODEL", f"Turn {iter_num} finished ({len(tool_calls)} tools)", model_dur_ms)

            msg = {"role": "assistant", "content": content}
            if tool_calls:
                msg["tool_calls"] = tool_calls
            messages.append(msg)

            return {
                "messages": messages,
                "tool_calls": tool_calls,
                "final_response": content,
                "iteration": iter_num,
                "verification_pending": bool(state.get("verification_pending")) if tool_calls else False,
            }

        selected_model, role = model_router.select_model(prompt, requires_tools=needs_tools)
        self.agent.model = selected_model
        self.agent.active_role = role

        payload = {
            "model": self.agent.model,
            "messages": messages,
            "stream": False,
            "tools": available_tools if needs_tools else [],
            "keep_alive": model_router.get_keep_alive(),
            "options": {"temperature": 0.3, "num_ctx": OLLAMA_NUM_CTX},
        }

        try:
            res = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=60)
            model_dur_ms = (time.perf_counter() - t_model_start) * 1000.0
            iter_num = state.get("iteration", 0) + 1
            telemetry.record_stage_time(f"llm_turn_{iter_num}_total", model_dur_ms)
            if iter_num == 1:
                telemetry.record_stage_time("llm_turn_1_ttft", min(model_dur_ms * 0.4, 1500.0))

            if res.status_code == 200:
                data = res.json()
                msg = data.get("message", {})
                content = msg.get("content", "")
                tool_calls = msg.get("tool_calls", [])

                # Fallback parser for local models emitting <tool_call> tags in content
                if not tool_calls and content:
                    extracted, clean = parse_fallback_tool_calls(content)
                    if extracted:
                        tool_calls = extracted
                        msg["content"] = clean
                        for call in tool_calls:
                            fn = call.get("function", {}).get("name", "")
                            if call.get("intercepted_from_xml"):
                                telemetry.record_xml_healing(fn, content[:120])

                telemetry.hud_badge("MODEL", f"Turn {iter_num} finished ({len(tool_calls)} tools)", model_dur_ms)

                messages.append(msg)
                return {
                    "messages": messages,
                    "tool_calls": tool_calls,
                    "final_response": msg.get("content", ""),
                    "iteration": iter_num,
                    "verification_pending": bool(state.get("verification_pending")) if tool_calls else False,
                }
            else:
                return {
                    "final_response": f"Ollama service error ({res.status_code}): {res.text}",
                    "tool_calls": [],
                    "is_complete": True,
                }
        except Exception as e:
            return {"final_response": f"Reasoning engine exception: {e!s}", "tool_calls": [], "is_complete": True}

    def _route_after_reasoning(self, state: SpaceVState) -> str:
        tool_calls = state.get("tool_calls", [])
        if tool_calls:
            return "execute_tools"

        # Goal classification comes from the model-produced contract, not a verb list.
        goal_contract = state.get("goal_contract") or {}
        iteration = state.get("iteration", 0)

        if goal_contract.get("requires_action", True) and iteration < 2:
            msgs = list(state.get("messages") or [])
            msgs.append({
                "role": "system",
                "content": (
                    "The structured goal indicates that the user requested an action or inspection. "
                    "Use available tools when needed to establish the requested outcome. If the goal is "
                    "underspecified or unsafe, ask a focused question; do not claim an action occurred."
                ),
            })
            state["messages"] = msgs
            return "loop_reasoning"

        return "synthesize"

    def _tool_executor_node(self, state: SpaceVState) -> dict[str, Any]:
        """
        Node 4: Pydantic-Validated Tool Execution.
        Executes tools, notifies live UI callbacks, and checks for modal roadblocks.
        """
        tool_calls = state.get("tool_calls", [])
        messages = list(state.get("messages") or [])
        tool_results = list(state.get("tool_results") or [])

        stuck_detected = False
        clarification_question = None
        sandbox_scope_required = "sandbox" in (
            (state.get("goal_contract") or {}).get("tool_domains") or []
        ) or bool(state.get("sandbox_context"))
        active_sandbox_session = sandbox_context_state(state.get("sandbox_context", "")) == "active_approved_session"
        failed_guest_command = any(
            item.get("name") == "run_sandbox_session_command"
            and item.get("status") in ("failed", "blocked", "error")
            for item in state.get("tool_results", [])
        )
        from tools.registry import SANDBOX_TOOL_NAMES

        import concurrent.futures

        is_gui_required = any(
            c.get("function", {}).get("name", "").startswith("gui_")
            or c.get("function", {}).get("name") in ["media_control", "lock_workstation"]
            for c in tool_calls
        )

        def _exec_single(call):
            func = call.get("function", {})
            t_name = func.get("name")
            t_args = func.get("arguments", {})
            call_id = call.get("id") or f"call_{uuid.uuid4().hex[:8]}"
            is_from_xml = bool(call.get("intercepted_from_xml", False))
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"[{ts}] [TOOL CALL]: {t_name}({t_args})")
            t0 = time.perf_counter()
            if sandbox_scope_required and t_name not in SANDBOX_TOOL_NAMES:
                res = (
                    "BLOCKED: This task is scoped to its approved Celesto sandbox. "
                    "Host tools cannot be used for this task."
                )
                status = "blocked"
                dur_ms = (time.perf_counter() - t0) * 1000.0
                print(f"[{ts}] [OS RESULT]: {res}")
                telemetry.record_tool_execution(
                    name=t_name,
                    args=t_args,
                    status=status,
                    duration_ms=dur_ms,
                    result_preview=res[:120],
                    intercepted_from_xml=is_from_xml,
                )
                if self._current_tool_callback:
                    self._current_tool_callback(t_name, t_args, res)
                return t_name, t_args, res, call_id, status

            allowed_active_tools = (
                {"close_sandbox_session"}
                if failed_guest_command
                else {"run_sandbox_session_command", "close_sandbox_session"}
            )
            if active_sandbox_session and t_name not in allowed_active_tools:
                res = (
                    "BLOCKED: An approved Celesto session is already active. Use its guest-command tool or "
                    "close the session; status, ledger, and new-session calls are disabled during task execution."
                )
                status = "blocked"
                dur_ms = (time.perf_counter() - t0) * 1000.0
                print(f"[{ts}] [OS RESULT]: {res}")
                telemetry.record_tool_execution(
                    name=t_name,
                    args=t_args,
                    status=status,
                    duration_ms=dur_ms,
                    result_preview=res[:120],
                    intercepted_from_xml=is_from_xml,
                )
                if self._current_tool_callback:
                    self._current_tool_callback(t_name, t_args, res)
                return t_name, t_args, res, call_id, status

            if t_name == "run_sandbox_session_command" and isinstance(t_args, dict):
                gate_message = _issue_test_patch_gate(
                    str(t_args.get("command", "")), str(t_args.get("session_id", ""))
                )
                if gate_message:
                    res = gate_message
                    status = "needs_input"
                    dur_ms = (time.perf_counter() - t0) * 1000.0
                    print(f"[{ts}] [OS RESULT]: {res}")
                    telemetry.record_tool_execution(
                        name=t_name,
                        args=t_args,
                        status=status,
                        duration_ms=dur_ms,
                        result_preview=res[:120],
                        intercepted_from_xml=is_from_xml,
                    )
                    if self._current_tool_callback:
                        self._current_tool_callback(t_name, t_args, res)
                    return t_name, t_args, res, call_id, status

            if t_name == "create_sandbox_session":
                task_description = t_args.get("task_description", "") if isinstance(t_args, dict) else ""
                placeholder = unresolved_template_marker(str(task_description))
                if placeholder:
                    res = (
                        "BLOCKED: Sandbox proposal contains unresolved placeholder "
                        f"{placeholder!r}. No VM was started; supply the missing task input first."
                    )
                    status = "blocked"
                    dur_ms = (time.perf_counter() - t0) * 1000.0
                    print(f"[{ts}] [OS RESULT]: {res}")
                    telemetry.record_tool_execution(
                        name=t_name,
                        args=t_args,
                        status=status,
                        duration_ms=dur_ms,
                        result_preview=res[:120],
                        intercepted_from_xml=is_from_xml,
                    )
                    if self._current_tool_callback:
                        self._current_tool_callback(t_name, t_args, res)
                    return t_name, t_args, res, call_id, status

            # Karpathy Rule 1 & 3: Goal-Driven Safety Audit
            from core.karpathy_verifier import karpathy_verifier

            audit = karpathy_verifier.audit_intent_safety(t_name, str(t_args))
            if not audit.get("safe", True):
                res = f"BLOCKED by Karpathy Safety Shield: {audit.get('reason')}"
                status = "blocked"
            else:
                # Celesto Containment Gatekeeper (Contract #4 & #8)
                if t_name == "execute_terminal_command":
                    cmd_to_check = t_args.get("command") or t_args.get("cmd") or t_args.get("shell_command") or ""
                    from core.containment_gatekeeper import ContainmentGatekeeper

                    should_sandbox, reason = ContainmentGatekeeper.should_sandbox(cmd_to_check)
                    if should_sandbox:
                        print(f"[{ts}] [CONTAINMENT] 🛡️ Intercepted '{reason}': auto-redirecting to Celesto Sandbox.")
                        t_name = "detonate_in_sandbox"
                        t_args = {"command": cmd_to_check}

                res = execute_tool(t_name, t_args)
                status = determine_tool_status(t_name, res)

                # Truth Gatekeeper Empirical Postcondition Verification (Phase 3 & 5)
                from core.truth_gatekeeper import truth_gatekeeper

                if t_name in ("create_file", "write_file") and status == "success":
                    fname = t_args.get("file_name") or t_args.get("filename") or t_args.get("file_path") or ""
                    loc = t_args.get("location") or "Desktop"
                    f_check = truth_gatekeeper.verify_file_postcondition(fname, location=loc)
                    if not f_check.passed:
                        status = "failed"
                        res = f"Verification failed: {f_check.error}"
                elif t_name in ("execute_code_block", "run_python_script") and status == "success":
                    code_to_check = t_args.get("code") or ""
                    if code_to_check:
                        ast_check = truth_gatekeeper.verify_python_syntax(code_to_check)
                        if not ast_check.passed:
                            status = "failed"
                            res = f"Syntax verification failed: {ast_check.error}"
            dur_ms = (time.perf_counter() - t0) * 1000.0
            print(f"[{ts}] [OS RESULT]: {res}")
            telemetry.record_tool_execution(
                name=t_name,
                args=t_args,
                status=status,
                duration_ms=dur_ms,
                result_preview=str(res)[:120],
                intercepted_from_xml=is_from_xml,
            )
            telemetry.hud_badge("TOOL", f"{t_name} -> {status}", dur_ms)
            if self._current_tool_callback:
                self._current_tool_callback(t_name, t_args, res)
            return t_name, t_args, res, call_id, status

        def _record_evidence(t_name: str, t_args: Any, raw_result: Any, bounded_result: str, status: str) -> None:
            """Persist the same bounded output shown to the model, before token compression."""
            try:
                from core.task_evidence import task_evidence_store

                goal = state.get("goal_contract") or {}
                task_context = f"{state.get('user_prompt', '')}\n{goal.get('objective', '')}"
                raw_text = str(raw_result)
                task_evidence_store.record_tool(
                    task_context=task_context,
                    source_name=t_name,
                    args=t_args,
                    result=bounded_result,
                    status=status,
                    truncated=(len(raw_text) > 8000),
                )
            except Exception as exc:
                logger.warning("Could not persist tool evidence for %s: %s", t_name, exc)

        def _issue_test_note(t_name: str, t_args: Any, raw_result: Any) -> str:
            """Add conservative deterministic classifications to captured issue-task evidence."""
            if state.get("specialist_role") != "issue_test" or t_name != "run_sandbox_session_command":
                return ""
            command = str(t_args.get("command", "")) if isinstance(t_args, dict) else ""
            goal = state.get("goal_contract") or {}
            entities = goal.get("entities") if isinstance(goal.get("entities"), dict) else {}
            expected_signal = str(entities.get("expected_failure_signal", ""))
            from core.issue_test_workflow import (
                classify_git_status,
                classify_test_patch_paths,
                classify_test_execution,
                format_git_status_classification,
                format_test_patch_audit,
                format_test_classification,
                detect_guest_environment,
                format_guest_environment,
            )

            notes = []
            test_result = classify_test_execution(command, str(raw_result), expected_signal)
            if test_result:
                notes.append(format_test_classification(test_result))
            status_result = classify_git_status(command, str(raw_result))
            if status_result:
                notes.append(format_git_status_classification(status_result))
            patch_audit = classify_test_patch_paths(command, str(raw_result))
            if patch_audit:
                notes.append(format_test_patch_audit(patch_audit))
            if "cat /etc/os-release" in command:
                stdout_match = re.search(
                    r"STDOUT:\s*\n(.*?)(?:\nSTDERR:|\Z)", str(raw_result), re.IGNORECASE | re.DOTALL
                )
                output = stdout_match.group(1) if stdout_match else str(raw_result)
                python_match = re.search(r"Python\s+([0-9][^\s]*)", output, re.IGNORECASE)
                arch_match = re.search(r"\b(?:x86_64|aarch64|arm64|i686)\b", output, re.IGNORECASE)
                notes.append(format_guest_environment(detect_guest_environment(
                    output,
                    python_match.group(1) if python_match else "unknown",
                    arch_match.group(0) if arch_match else "unknown",
                )))
            return "\n\n".join(notes)

        def _issue_test_patch_gate(command: str, session_id: str = "") -> str | None:
            """Require same-session commit, clean baseline, and test-only edit evidence."""
            if state.get("specialist_role") != "issue_test":
                return None
            from core.issue_test_workflow import classify_test_execution, classify_test_patch_paths

            if classify_test_execution(command, "") is None:
                return None
            from core.task_evidence import task_evidence_store

            prior_records = task_evidence_store.session_tool_results(session_id) if session_id else []
            # Include current-turn receipts as a fallback for harnesses that do
            # not persist tool evidence, while keeping the session ID scoped.
            if not prior_records:
                prior_records = [
                    item for item in tool_results
                    if not session_id or str((item.get("args") or {}).get("session_id", "")) == session_id
                ]
            pinned_commit = None
            commit_unchanged = True
            post_patch_commit_verified = False
            initial_clean = False
            latest_audit = None
            baseline_passed = False
            patch_seen = False
            for prior in prior_records:
                if prior.get("name") != "run_sandbox_session_command":
                    continue
                prior_args = prior.get("args") if isinstance(prior.get("args"), dict) else {}
                prior_command = str(prior_args.get("command", ""))
                prior_result = str(prior.get("result", ""))
                exit_match = re.search(r"\bexit code:\s*(-?\d+)", prior_result, re.IGNORECASE)
                command_exit = int(exit_match.group(1)) if exit_match else None
                if re.search(r"\bgit\s+rev-parse\s+HEAD\b", prior_command, re.IGNORECASE):
                    stdout_match = re.search(
                        r"STDOUT:\s*\n(.*?)(?:\nSTDERR:|\Z)", prior_result, re.IGNORECASE | re.DOTALL
                    )
                    stdout = stdout_match.group(1).strip() if stdout_match else ""
                    observed_commit = (
                        stdout.casefold()
                        if command_exit == 0 and re.fullmatch(r"[0-9a-f]{40,64}", stdout, re.IGNORECASE)
                        else None
                    )
                    if observed_commit:
                        if pinned_commit is None:
                            pinned_commit = observed_commit
                        elif observed_commit != pinned_commit:
                            commit_unchanged = False
                        if patch_seen:
                            post_patch_commit_verified = observed_commit == pinned_commit and commit_unchanged

                path_audit = classify_test_patch_paths(prior_command, prior_result)
                if path_audit is not None:
                    latest_audit = path_audit
                    if path_audit["classification"] == "NO_CHANGED_PATHS" and not patch_seen:
                        initial_clean = (
                            path_audit.get("exit_code") == 0
                            and pinned_commit is not None
                            and commit_unchanged
                        )
                    elif path_audit["classification"] == "TEST_FILES_ONLY":
                        patch_seen = True
                    else:
                        initial_clean = False

                prior_test = classify_test_execution(prior_command, prior_result)
                if (
                    prior_test
                    and prior_test["classification"] == "PASS_NO_REPRODUCTION"
                    and initial_clean
                    and not patch_seen
                ):
                    baseline_passed = True

            if (
                latest_audit
                and latest_audit["classification"] == "TEST_FILES_ONLY"
                and baseline_passed
                and post_patch_commit_verified
            ):
                return None
            if (
                latest_audit
                and latest_audit["classification"] == "NO_CHANGED_PATHS"
                and "baseline" in str(state.get("user_prompt", "")).casefold()
                and latest_audit.get("exit_code") == 0
                and pinned_commit is not None
                and commit_unchanged
            ):
                return None
            latest = latest_audit["classification"] if latest_audit else "MISSING_AUDIT"
            baseline_state = "BASELINE_PASS" if baseline_passed else "BASELINE_NOT_VERIFIED"
            return (
                "SPACEV_NEEDS_USER_INPUT: Test execution is paused. Evidence must come from this same Celesto session: "
                "a successful `git rev-parse HEAD`, a clean initial `git status --short`, and an approved baseline test "
                "that passes before edits. After the separately approved test-only edit, a fresh `git status --short` "
                "must show TEST_FILES_ONLY, and `git rev-parse HEAD` must still match the pinned commit. "
                f"Current path audit={latest}; commit_pinned={pinned_commit is not None}; "
                f"commit_unchanged={commit_unchanged}; baseline={baseline_state}. "
                "No candidate test was run."
            )

        scratchpad = SpaceVScratchpad.from_dict(state.get("scratchpad"))

        MUTATING_TOOLS = {
            "create_folder",
            "create_file",
            "execute_code_block",
            "run_python_script",
            "execute_terminal_command",
            "open_text_editor",
            "delete_file",
            "write_file",
            "gui_open_and_search_app",
            # Guest commands must stay ordered so a fresh path audit cannot
            # race a candidate test command in the same model response.
            "run_sandbox_session_command",
        }
        has_mutating_tools = any(c.get("function", {}).get("name") in MUTATING_TOOLS for c in tool_calls)

        # Parallel fan-out ONLY for independent read-only inspection, scraping, and telemetry tools
        if len(tool_calls) > 1 and not is_gui_required and not has_mutating_tools:
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(tool_calls))) as executor:
                executed_items = list(executor.map(_exec_single, tool_calls))
            for t_name, t_args, res, call_id, status in executed_items:
                from tools.system_tools import sanitize_tool_output

                bounded_content = sanitize_tool_output(str(res))
                _record_evidence(t_name, t_args, res, bounded_content, status)
                from core.token_optimizer import token_optimizer
                model_content = bounded_content + _issue_test_note(t_name, t_args, res)
                compressed_content = token_optimizer.compress_tool_result(t_name, model_content, max_chars=1500)
                tool_results.append({"name": t_name, "args": t_args, "result": bounded_content, "status": status})
                messages.append({"role": "tool", "tool_call_id": call_id, "name": t_name, "content": compressed_content})
                scratchpad.record_tool_action(t_name, t_args, bounded_content)
                if not t_name.startswith("scratchpad_"):
                    scratchpad.advance_step(result=bounded_content[:120], success=(status == "success"))
        else:
            # Deterministic sequential execution for GUI actions & single tools
            for call in tool_calls:
                t_name, t_args, res, call_id, status = _exec_single(call)
                from tools.system_tools import sanitize_tool_output

                bounded_content = sanitize_tool_output(str(res))
                _record_evidence(t_name, t_args, res, bounded_content, status)
                from core.token_optimizer import token_optimizer
                model_content = bounded_content + _issue_test_note(t_name, t_args, res)
                compressed_content = token_optimizer.compress_tool_result(t_name, model_content, max_chars=1500)
                tool_results.append({"name": t_name, "args": t_args, "result": bounded_content, "status": status})
                messages.append({"role": "tool", "tool_call_id": call_id, "name": t_name, "content": compressed_content})
                scratchpad.record_tool_action(t_name, t_args, bounded_content)

                res_str = bounded_content
                if (
                    "Modal Blocker" in res_str
                    or "stuck at the" in res_str.lower()
                    or "waiting at the" in res_str.lower()
                ):
                    from core.modal_interceptor import modal_interceptor

                    gatekeeper = modal_interceptor.detect()
                    stuck_detected = True
                    clarification_question = (
                        gatekeeper.question
                        if gatekeeper
                        else ("Sir, I ran into an ambiguous desktop state and require your direction to proceed.")
                    )

                if not t_name.startswith("scratchpad_"):
                    scratchpad.advance_step(result=res_str[:120], success=(status == "success" and not stuck_detected))

        failed_guest_execution = next(
            (
                item for item in reversed(tool_results)
                if item.get("name") == "run_sandbox_session_command"
                and item.get("status") in ("failed", "blocked", "error")
            ),
            None,
        )
        if failed_guest_execution and active_sandbox_session:
            # A failed guest command is terminal for this approved task. Close
            # its disposable VM deterministically instead of asking the model
            # to retry, repair, or fall back to the host.
            session_id = sandbox_context_payload(state.get("sandbox_context", "")).get("session_id")
            if session_id:
                close_started = time.perf_counter()
                close_result = execute_tool("close_sandbox_session", {"session_id": session_id})
                close_duration_ms = (time.perf_counter() - close_started) * 1000.0
                close_status = determine_tool_status("close_sandbox_session", close_result)
                close_call_id = f"call_sandbox_failure_cleanup_{uuid.uuid4().hex[:8]}"
                from core.token_optimizer import token_optimizer
                from tools.system_tools import sanitize_tool_output

                close_content = sanitize_tool_output(str(close_result))
                _record_evidence(
                    "close_sandbox_session", {"session_id": session_id}, close_result, close_content, close_status
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": close_call_id,
                    "name": "close_sandbox_session",
                    "content": token_optimizer.compress_tool_result(
                        "close_sandbox_session", close_content, max_chars=800
                    ),
                })
                tool_results.append({
                    "name": "close_sandbox_session",
                    "args": {"session_id": session_id},
                    "result": close_content,
                    "status": close_status,
                })
                telemetry.record_tool_execution(
                    name="close_sandbox_session",
                    args={"session_id": session_id},
                    status=close_status,
                    duration_ms=close_duration_ms,
                    result_preview=close_content[:120],
                    intercepted_from_xml=False,
                )
                if self._current_tool_callback:
                    self._current_tool_callback(
                        "close_sandbox_session", {"session_id": session_id}, close_result
                    )

        last_error = None
        clarification_from_tool = next(
            (str(item.get("result", "")).split("SPACEV_NEEDS_USER_INPUT:", 1)[1].strip()
             for item in tool_results
             if item.get("status") == "needs_input" and "SPACEV_NEEDS_USER_INPUT:" in str(item.get("result", ""))),
            None,
        )
        if clarification_from_tool:
            stuck_detected = True
            clarification_question = clarification_from_tool
        for item in tool_results:
            if item.get("status") in ("failed", "blocked"):
                if not stuck_detected:
                    last_error = str(item.get("result", ""))
                    break

        action_results = [item for item in tool_results if not str(item.get("name", "")).startswith("scratchpad_")]
        verification_evidence: dict[str, Any] = {}
        # Sandbox task results are the evidence for guest execution; do not
        # inspect the host desktop after an action scoped to the VM.
        verification_pending = bool(action_results) and not sandbox_scope_required
        if verification_pending:
            from core.grounded_agent import evidence_context, inspect_environment

            verification_evidence = inspect_environment()
            goal = state.get("goal_contract") or {}
            messages.append({
                "role": "system",
                "content": (
                    f"{evidence_context('Post-action UI and system evidence', verification_evidence)}\n"
                    f"[Completion criteria]: {json.dumps(goal.get('success_criteria', []), ensure_ascii=False)}\n"
                    "Compare the observed state with the goal and tool results. This snapshot is evidence, not proof "
                    "of success by itself. If it does not establish completion, inspect further or report uncertainty."
                ),
            })

        updated_sandbox_context = state.get("sandbox_context", "")
        if sandbox_scope_required:
            try:
                from tools.sandbox_tools import sandbox_session_manager

                updated_sandbox_context = sandbox_session_manager.continuation_context(
                    state.get("user_prompt", "")
                )
                if updated_sandbox_context and updated_sandbox_context != state.get("sandbox_context", ""):
                    messages.append({"role": "system", "content": updated_sandbox_context})
            except Exception as exc:
                logger.debug("Sandbox continuation refresh unavailable: %s", exc)

        return {
            "messages": messages,
            "tool_results": tool_results,
            "tool_calls": [],
            "stuck_detected": stuck_detected,
            "clarification_question": clarification_question,
            "last_error": last_error,
            "scratchpad": scratchpad.to_dict(),
            "verification_evidence": verification_evidence,
            "verification_pending": verification_pending,
            "sandbox_context": updated_sandbox_context,
        }

    def _route_after_tools(self, state: SpaceVState) -> str:
        if state.get("stuck_detected"):
            return "stuck"
        if any(
            item.get("name") == "run_sandbox_session_command"
            and item.get("status") in ("failed", "blocked", "error")
            for item in state.get("tool_results", [])
        ):
            return "synthesize"
        if (
            sandbox_context_state(state.get("sandbox_context", "")) == "active_approved_session"
            and state.get("iteration", 0) < 4
        ):
            # Keep the approved task moving inside its existing guest. Any
            # failed guest command is restricted to close-only by the next
            # reasoning turn, preventing host-side self-healing or retries.
            return "loop_reasoning"
        if state.get("last_error"):
            if state.get("healing_attempts", 0) < 2:
                return "self_healing"
            else:
                # Self-healing exhausted! Escalate to interactive clarification/stuck instead of falsely synthesizing success
                tool_results = state.get("tool_results", [])
                failed_tool = tool_results[-1] if tool_results else {}
                from core.self_healing import self_healing_engine

                diag = self_healing_engine.diagnose_failure(
                    failed_tool.get("name", "tool"), failed_tool.get("args", {}), state.get("last_error", "")
                )
                card = self_healing_engine.format_clarification_card(diag)
                if hasattr(self.agent, "active_paused_frame"):
                    self.agent.active_paused_frame = {
                        "tool": failed_tool.get("name", ""),
                        "args": failed_tool.get("args", {}),
                        "diagnosis": diag,
                        "remediation_options": diag.get("remediation_options", []),
                        "user_prompt": state.get("user_prompt", ""),
                    }
                state["clarification_question"] = card
                state["stuck_detected"] = True
                return "stuck"

        scratchpad = SpaceVScratchpad.from_dict(state.get("scratchpad"))
        iteration = state.get("iteration", 0)

        # Karpathy Anti-Stall Guard: If the model is only reading or writing notes to scratchpad
        # without invoking real OS tools, break out to synthesize instead of looping endlessly
        tool_results = state.get("tool_results", [])
        recent_names = [t.get("name") for t in tool_results[-2:]]
        if recent_names and all(n in ("scratchpad_view", "scratchpad_note") for n in recent_names) and iteration >= 2:
            return "synthesize"

        # Autonomous multi-step tool chaining: if scratchpad has pending steps, loop up to 4 iterations
        if scratchpad.has_pending_steps() and iteration < 4:
            return "loop_reasoning"

        # Every completed tool batch gets one model pass against fresh environment
        # evidence before synthesis; the model can inspect further if evidence is weak.
        if state.get("verification_pending") and iteration < 4:
            return "loop_reasoning"

        user_p = (state.get("user_prompt") or "").lower()

        # Doubt-Driven Development Gate (skills/doubt-driven-development): Disprove phantom success.
        # If mutating tools encountered errors or explicit failure output, loop to allow self-healing / alternative tool
        recent_mutating_failures = [
            t
            for t in tool_results
            if t.get("name")
            in (
                "create_file",
                "create_folder",
                "write_file",
                "execute_code_block",
                "run_python_script",
                "execute_terminal_command",
            )
            and (
                t.get("status") in ("failed", "blocked", "error")
                or str(t.get("result", "")).startswith(("Failed:", "Error:", "BLOCKED:"))
            )
        ]
        if recent_mutating_failures and iteration < 3:
            return "loop_reasoning"

        return "synthesize"

    def _self_healing_node(self, state: SpaceVState) -> dict[str, Any]:
        """
        Self-Healing Reflection Node:
        Analyzes tool failures, computes dynamic OS remediations, and re-executes.
        """
        from core.self_healing import self_healing_engine

        attempts = state.get("healing_attempts", 0)
        last_err = state.get("last_error", "")
        tool_results = state.get("tool_results", [])
        failed_tool = tool_results[-1] if tool_results else {}
        t_name = failed_tool.get("name", "")
        t_args = failed_tool.get("args", {})

        diag = self_healing_engine.diagnose_failure(t_name, t_args, last_err)
        can_heal, new_tool, new_args, msg = self_healing_engine.attempt_remediation(diag, attempts)

        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [SELF-HEALING] 🩺 Attempt {attempts + 1}: {msg}")

        if can_heal and new_tool:
            return {
                "healing_attempts": attempts + 1,
                "tool_calls": [{"function": {"name": new_tool, "arguments": new_args or {}}}],
                "last_error": None,
            }
        elif diag.get("category") == "GENERIC_ERROR" and attempts == 0 and state.get("iteration", 0) < 3:
            msgs = list(state.get("messages") or [])
            msgs.append(
                {
                    "role": "system",
                    "content": (
                        f"[TOOL FAILURE DIAGNOSTIC]: Tool '{t_name}' failed with error:\n{last_err}\n"
                        "Do not repeat the identical failing command. Choose an alternative tool or execute via execute_code_block / execute_terminal_command."
                    ),
                }
            )
            return {"healing_attempts": attempts + 1, "messages": msgs, "tool_calls": [], "last_error": None}
        else:
            card = self_healing_engine.format_clarification_card(diag)
            if hasattr(self.agent, "active_paused_frame"):
                self.agent.active_paused_frame = {
                    "tool": t_name,
                    "args": t_args,
                    "diagnosis": diag,
                    "remediation_options": diag.get("remediation_options", []),
                    "user_prompt": state.get("user_prompt", ""),
                }
            return {
                "healing_attempts": attempts + 1,
                "stuck_detected": True,
                "clarification_question": card,
                "last_error": None,
            }

    def _route_after_healing(self, state: SpaceVState) -> str:
        if state.get("tool_calls"):
            return "retry_tool"
        if not state.get("stuck_detected") and state.get("healing_attempts", 0) <= 2:
            return "loop_reasoning"
        return "escalate"

    def _clarification_node(self, state: SpaceVState) -> dict[str, Any]:
        """
        Node 5: Self-Aware Clarification Inquirer.
        When stuck or confused, SpaceV asks the user for explicit guidance instead of hallucinating.
        """
        question = state.get("clarification_question") or (
            "Sir, I encountered an ambiguous state on your desktop and require your guidance to proceed safely."
        )
        try:
            from ui.holographic_visor import HolographicVisor
            visor = HolographicVisor.get_instance()
            if visor:
                visor.set_attention(question[:60])
        except Exception:
            pass

        if self._current_token_callback:
            self._current_token_callback(question)

        return {"final_response": question, "is_complete": True}

    def _response_synthesizer_node(self, state: SpaceVState) -> dict[str, Any]:
        """
        Node 6: Final Natural Language Response Synthesizer with Real-Time Streaming.
        """
        t_synth_start = time.perf_counter()

        # Backend readiness is already structured tool evidence. Summarize it
        # deterministically instead of asking a second model call that can
        # hallucinate a retry or leak provider-specific pseudo-tool markup.
        status_result = next(
            (
                item for item in state.get("tool_results", [])
                if item.get("name") == "get_sandbox_status" and item.get("status") == "success"
            ),
            None,
        )
        if status_result:
            try:
                status = json.loads(str(status_result.get("result", "")))
                blockers = status.get("blockers") or []
                ready = bool(status.get("real_celesto_backend_configured"))
                backend = status.get("execution_backend", "unknown")
                provider = status.get("celesto_provider", "unknown")
                py_version = status.get("python_version", "unknown")
                sdk_ready = bool(status.get("celesto_sdk_installed")) and bool(
                    status.get("celesto_python_version_supported")
                )
                if ready:
                    blocker_summary = "none"
                else:
                    blocker_summary = "; ".join(str(reason) for reason in blockers) or "configuration is incomplete"
                final_text = (
                    f"Celesto status: {'ready' if ready else 'not ready'}. "
                    f"Provider: {provider}; backend: {backend}. "
                    f"Python {py_version}; SDK available: {'yes' if sdk_ready else 'no'}. "
                    f"No VM was started by this status check. Blockers: {blocker_summary}."
                )
                messages = list(state.get("messages", []))
                messages.append({"role": "assistant", "content": final_text})
                if self._current_token_callback:
                    self._current_token_callback(final_text)
                telemetry.record_stage_time("tts_synthesis", (time.perf_counter() - t_synth_start) * 1000.0)
                telemetry.hud_badge("TTS", f"Response synthesized ({len(final_text)} chars)")
                return {"final_response": final_text, "messages": messages, "is_complete": True}
            except (TypeError, ValueError, json.JSONDecodeError):
                # If the registered diagnostic changes its output contract,
                # retain the normal synthesis path rather than guessing.
                pass

        # If response already exists and no tools executed, stream it directly
        if state.get("final_response") and not state.get("tool_results"):
            content = state["final_response"]
            if self._current_token_callback:
                self._current_token_callback(content)
            synth_dur_ms = (time.perf_counter() - t_synth_start) * 1000.0
            telemetry.record_stage_time("tts_synthesis", synth_dur_ms)
            return {"final_response": content, "is_complete": True}

        messages = state.get("messages", [])

        # Configured cloud endpoint branch.
        if getattr(self.agent, "provider", "ollama") in ("openai", "openrouter") and hasattr(
            self.agent, "cloud_client"
        ):
            from core.token_harness import token_harness, estimate_messages_tokens
            pre_tokens = estimate_messages_tokens(messages)
            opt_messages, _ = token_harness.optimize(
                messages=messages,
                tools=None,
                user_prompt=state.get("user_prompt", ""),
            )
            post_tokens = estimate_messages_tokens(opt_messages)
            synth_dict = self.agent.cloud_client.chat(
                messages=opt_messages,
                tools=None,
                model=self.agent.model,
                token_callback=self._current_token_callback,
                pre_tokens=pre_tokens,
                post_tokens=post_tokens,
            )
            raw_synth = synth_dict.get("content", "")
            tool_results = state.get("tool_results", [])
            has_tools = bool(tool_results)
            tool_summary = generate_tool_summary(tool_results)
            has_tool_failure = (
                any(
                    t.get("status") in ("failed", "blocked")
                    or str(t.get("result", "")).startswith(("Failed:", "Error:", "BLOCKED:"))
                    for t in tool_results
                )
                if tool_results
                else False
            )
            full_reply = sanitize_speech_output(
                raw_synth, has_error=has_tool_failure, has_tools=has_tools, tool_summary=tool_summary
            )
            from core.truth_gatekeeper import truth_gatekeeper

            full_reply = truth_gatekeeper.audit_and_enforce_truth(
                full_reply, tool_results, state.get("user_prompt", "")
            )
            messages.append({"role": "assistant", "content": full_reply})
            synth_dur_ms = (time.perf_counter() - t_synth_start) * 1000.0
            telemetry.record_stage_time("tts_synthesis", synth_dur_ms)
            telemetry.hud_badge("TTS", f"Response synthesized ({len(full_reply)} chars)", synth_dur_ms)
            return {"final_response": full_reply, "is_complete": True}

        stream_payload = {
            "model": self.agent.model,
            "messages": messages,
            "stream": True,
            "keep_alive": model_router.get_keep_alive(),
            "options": {"temperature": 0.3, "num_ctx": 2048, "num_predict": 300},
        }

        full_reply = ""
        try:
            res = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=stream_payload, stream=True, timeout=60)
            if res.status_code == 200:
                for line in res.iter_lines():
                    if line:
                        chunk = json.loads(line.decode("utf-8"))
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            full_reply += token
                            if self._current_token_callback:
                                self._current_token_callback(token)

                if not full_reply.strip():
                    tool_results = state.get("tool_results", [])
                    has_tools = bool(tool_results)
                    tool_summary = generate_tool_summary(tool_results)
                    has_tool_failure = (
                        any(
                            t.get("status") in ("failed", "blocked")
                            or str(t.get("result", "")).startswith(("Failed:", "Error:", "BLOCKED:"))
                            for t in tool_results
                        )
                        if tool_results
                        else False
                    )
                    full_reply = sanitize_speech_output(
                        "", has_error=has_tool_failure, has_tools=has_tools, tool_summary=tool_summary
                    )
                    if self._current_token_callback:
                        self._current_token_callback(full_reply)

                messages.append({"role": "assistant", "content": full_reply})

                # Pro ReAct Action Interceptor: Catch and execute any embedded tool calls
                extracted, clean = parse_fallback_tool_calls(full_reply)
                if extracted:
                    for call in extracted:
                        func = call.get("function", {})
                        t_name = func.get("name")
                        t_args = func.get("arguments", {})
                        if t_name:
                            ts = datetime.datetime.now().strftime("%H:%M:%S")
                            print(f"[{ts}] [REACT INTERCEPTOR]: Executing embedded tool '{t_name}'({t_args})")
                            if sandbox_scope_required and t_name not in SANDBOX_TOOL_NAMES:
                                blocked = (
                                    "BLOCKED: This task is scoped to its approved Celesto sandbox. "
                                    "Host tools cannot be used for this task."
                                )
                                tool_status = "blocked"
                                telemetry.record_tool_execution(
                                    name=t_name,
                                    args=t_args,
                                    status=tool_status,
                                    duration_ms=0.0,
                                    result_preview=blocked[:120],
                                    intercepted_from_xml=True,
                                )
                                full_reply = f"{clean}\n\n{blocked}".strip() if clean else blocked
                                continue
                            telemetry.record_xml_healing(t_name, full_reply[:120])
                            t0 = time.perf_counter()
                            tool_out = execute_tool(t_name, t_args)
                            dur_ms = (time.perf_counter() - t0) * 1000.0
                            tool_status = determine_tool_status(t_name, tool_out)
                            telemetry.record_tool_execution(
                                name=t_name,
                                args=t_args,
                                status=tool_status,
                                duration_ms=dur_ms,
                                result_preview=str(tool_out)[:120],
                                intercepted_from_xml=True,
                            )
                            telemetry.hud_badge("TOOL", f"{t_name} (intercepted) -> {tool_status}", dur_ms)
                            if self._current_tool_callback:
                                self._current_tool_callback(t_name, t_args, tool_out)
                            full_reply = f"{clean}\n\n{tool_out}".strip() if clean else str(tool_out)

                synth_dur_ms = (time.perf_counter() - t_synth_start) * 1000.0
                telemetry.record_stage_time("tts_synthesis", synth_dur_ms)
                telemetry.hud_badge("TTS", f"Response synthesized ({len(full_reply)} chars)", synth_dur_ms)
                return {"final_response": full_reply, "messages": messages, "is_complete": True}
            else:
                tool_results = state.get("tool_results", [])
                has_tools = bool(tool_results)
                tool_summary = generate_tool_summary(tool_results)
                has_tool_failure = (
                    any(
                        t.get("status") in ("failed", "blocked")
                        or str(t.get("result", "")).startswith(("Failed:", "Error:", "BLOCKED:"))
                        for t in tool_results
                    )
                    if tool_results
                    else False
                )
                if has_tool_failure:
                    fallback = "Sir, I encountered a roadblock while executing this operation on your workstation."
                elif not has_tools:
                    fallback = "I understand, Sir. Please let me know what you would like to do next."
                elif tool_summary:
                    fallback = f"Operation completed. {tool_summary}"
                else:
                    fallback = "Action completed successfully, Sir."
                if self._current_token_callback:
                    self._current_token_callback(fallback)
                synth_dur_ms = (time.perf_counter() - t_synth_start) * 1000.0
                telemetry.record_stage_time("tts_synthesis", synth_dur_ms)
                return {"final_response": fallback, "is_complete": True}
        except Exception as e:
            fallback = f"Operation stopped: {e!s}"
            if self._current_token_callback:
                self._current_token_callback(fallback)
            synth_dur_ms = (time.perf_counter() - t_synth_start) * 1000.0
            telemetry.record_stage_time("tts_synthesis", synth_dur_ms)
            return {"final_response": fallback, "is_complete": True}

    # ==========================================
    # PUBLIC EXECUTION INTERFACE
    # ==========================================

    def run(
        self, user_prompt: str, tool_callback: Callable | None = None, token_callback: Callable | None = None
    ) -> str:
        """
        Executes the compiled LangGraph state machine with full deterministic node tracking,
        real-time UI callbacks, closed-loop perception, and dual-sink telemetry auditing.
        """
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"\n{'=' * 65}")
        print(f"[{timestamp}] [USER]: {user_prompt}")
        print(f"[{timestamp}] [SPACEV GRAPH]: Executing state machine...")

        self._current_tool_callback = tool_callback
        self._current_token_callback = token_callback

        active_scratchpad.set_goal(user_prompt)
        telemetry.start_turn(user_prompt, channel="console")

        initial_state: SpaceVState = {
            "user_prompt": user_prompt,
            "messages": [],
            "fast_path_result": None,
            "tool_calls": [],
            "tool_results": [],
            "active_window": "",
            "stuck_detected": False,
            "clarification_question": None,
            "final_response": "",
            "iteration": 0,
            "is_complete": False,
            "healing_attempts": 0,
            "last_error": None,
            "scratchpad": active_scratchpad.to_dict(),
            "goal_contract": {},
            "goal_interpretation": "",
            "specialist_role": "",
            "environment_evidence": {},
            "verification_evidence": {},
            "verification_pending": False,
            "sandbox_context": "",
            "task_evidence_context": "",
            "sandbox_control_call": False,
        }

        try:
            final_state = self.app.invoke(initial_state)
            tool_results = final_state.get("tool_results", [])
            response = sanitize_speech_output(
                final_state.get("final_response", ""),
                has_error=bool(final_state.get("last_error")),
                has_tools=bool(tool_results),
            )

            # BugProof output is a first-class, bounded report artifact. Export
            # only this turn's captured tool receipts so repeated attempts for
            # the same issue cannot be silently mixed together.
            if final_state.get("specialist_role") == "issue_test" and tool_results:
                try:
                    from core.task_evidence import task_evidence_store

                    goal = final_state.get("goal_contract") or {}
                    report_context = (
                        f"{user_prompt}\n{goal.get('objective', '')}"
                    )
                    bundle = task_evidence_store.export_bundle(
                        report_context,
                        tool_results=tool_results,
                    )
                    if bundle.get("status") == "exported":
                        response += (
                            f"\nEvidence bundle saved: {bundle['path']} "
                            f"({bundle['record_count']} records; SHA-256 {bundle['sha256']})."
                        )
                except Exception as exc:
                    logger.warning("Could not export issue-test evidence bundle: %s", exc)

            print(f"[{timestamp}] [SPACEV]: {response}\n{'=' * 65}\n")
            outcome = "stuck" if final_state.get("stuck_detected") else "success"
            telemetry.end_turn(outcome_status=outcome, error=final_state.get("last_error"))

            # Persist completed turn to self.agent.messages for rolling multi-turn interlinking
            try:
                from core.task_evidence import task_evidence_store

                task_evidence_store.record_turn(user_prompt=user_prompt, assistant_response=response)
            except Exception as exc:
                logger.warning("Could not persist completed conversation turn: %s", exc)
            if hasattr(self.agent, "messages"):
                self.agent.messages.append({"role": "user", "content": user_prompt})
                self.agent.messages.append({"role": "assistant", "content": response})

            return response
        except Exception as e:
            telemetry.end_turn(outcome_status="failed", error=str(e))
            raise
        finally:
            self._current_tool_callback = None
            self._current_token_callback = None


graph_engine = SpaceVGraphEngine()
