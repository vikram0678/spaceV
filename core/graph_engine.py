"""
LangGraph Production Multi-Step Cyclic State Machine for SpaceV.
Coordinates Fast-Path dispatching, closed-loop Perception Guards, Ollama model reasoning,
Pydantic tool execution, roadblock clarification, and real-time streaming response synthesis.
"""
import datetime
import json
import uuid
from collections.abc import Callable
from typing import Any, TypedDict

import requests

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

                if current_state.get("is_complete") and current in ("fast_router", "clarification_node", "response_synthesizer"):
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
from config import OLLAMA_BASE_URL
from core.fast_router import FastRouter
from core.model_router import model_router
from core.ollama_client import SYSTEM_PROMPT, OllamaAgent, parse_fallback_tool_calls
from core.proactive_companion import ProactiveCompanion
from core.scratchpad import SpaceVScratchpad, active_scratchpad
from tools.registry import OLLAMA_TOOLS_SCHEMA, execute_tool
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
        workflow.add_node("fast_router", self._fast_router_node)
        workflow.add_node("perception_guard", self._perception_guard_node)
        workflow.add_node("model_reasoning", self._model_reasoning_node)
        workflow.add_node("tool_executor", self._tool_executor_node)
        workflow.add_node("self_healing", self._self_healing_node)
        workflow.add_node("clarification_node", self._clarification_node)
        workflow.add_node("response_synthesizer", self._response_synthesizer_node)

        # 2. Entry Point
        workflow.set_entry_point("fast_router")

        # 3. Conditional Edge: Fast-Router (0ms Instant Bypass)
        workflow.add_conditional_edges(
            "fast_router",
            self._route_after_fast_router,
            {
                "fast_complete": END,
                "needs_brain": "perception_guard"
            }
        )

        # 4. Conditional Edge: Perception Guard (Roadblock / Modal Check)
        workflow.add_conditional_edges(
            "perception_guard",
            self._route_after_perception,
            {
                "stuck": "clarification_node",
                "proceed": "model_reasoning"
            }
        )

        # 5. Conditional Edge: Model Reasoning (Tools vs Direct Chat)
        workflow.add_conditional_edges(
            "model_reasoning",
            self._route_after_reasoning,
            {
                "execute_tools": "tool_executor",
                "synthesize": "response_synthesizer"
            }
        )

        # 6. Conditional Edge: Tool Executor (Loop Chaining, Self-Healing, or Synthesize)
        workflow.add_conditional_edges(
            "tool_executor",
            self._route_after_tools,
            {
                "stuck": "clarification_node",
                "self_healing": "self_healing",
                "loop_reasoning": "model_reasoning",
                "synthesize": "response_synthesizer"
            }
        )

        # 7. Conditional Edge: Self-Healing Reflection Node
        workflow.add_conditional_edges(
            "self_healing",
            self._route_after_healing,
            {
                "retry_tool": "tool_executor",
                "escalate": "clarification_node"
            }
        )

        # 8. Terminal Edges
        workflow.add_edge("clarification_node", END)
        workflow.add_edge("response_synthesizer", END)

        return workflow

    # ==========================================
    # NODE IMPLEMENTATIONS
    # ==========================================

    def _fast_router_node(self, state: SpaceVState) -> dict[str, Any]:
        """
        Node 1: Evaluates deterministic FastRouter patterns in 0ms.
        Bypasses LLM inference entirely when safe, predictable shortcuts match.
        """
        prompt = state.get("user_prompt", "")

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
                "is_complete": True
            }

        prompt = assessment.sanitized_text
        match = FastRouter.match(prompt)

        if match:
            tool_name, tool_output, reply = match
            reply = ProactiveCompanion.generate_conversational_wrap(tool_name, reply)

            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] [FAST ROUTER MATCH]: {tool_name}")

            if self._current_tool_callback:
                self._current_tool_callback(tool_name, {}, tool_output)
            if self._current_token_callback:
                self._current_token_callback(reply)

            return {
                "fast_path_result": match,
                "final_response": reply,
                "is_complete": True
            }

        return {"fast_path_result": None, "is_complete": False}

    def _route_after_fast_router(self, state: SpaceVState) -> str:
        if state.get("fast_path_result"):
            return "fast_complete"
        return "needs_brain"

    def _perception_guard_node(self, state: SpaceVState) -> dict[str, Any]:
        """
        Node 2: Closed-Loop Perception Guard.
        Inspects active desktop window, detects roadblocks, and feeds perceptual context.
        """
        win_info = get_active_window_info()
        win_lower = win_info.lower()
        prompt_lower = state.get("user_prompt", "").lower()

        # Universal Gatekeeper Perception Check
        from core.memory import memory
        from core.modal_interceptor import modal_interceptor
        gatekeeper = modal_interceptor.detect()
        if gatekeeper and gatekeeper.is_active:
            pref = memory.get_preference(gatekeeper.domain, gatekeeper.property_key)
            if not pref:
                memory.set_suspended_disambiguation({
                    "domain": gatekeeper.domain,
                    "property_key": gatekeeper.property_key,
                    "question": gatekeeper.question,
                    "options": gatekeeper.options,
                    "suspended_task": state.get("user_prompt"),
                    "timestamp": datetime.datetime.now().timestamp()
                })
                return {
                    "active_window": win_info,
                    "stuck_detected": True,
                    "clarification_question": gatekeeper.question
                }

        # Reconstitute Scratchpad Working Memory
        scratchpad = SpaceVScratchpad.from_dict(state.get("scratchpad"))
        if not scratchpad.goal:
            scratchpad.set_goal(state.get("user_prompt", ""))

        # Auto-initialize plan checklist for multi-step prompts if not already set
        if not scratchpad.plan:
            import re
            parts = [p.strip() for p in re.split(r'\b(?:and then|and also|then|and|, then)\b', state.get("user_prompt", ""), flags=re.IGNORECASE) if p.strip()]
            if len(parts) > 1:
                scratchpad.create_plan(parts)

        scratchpad_context = scratchpad.format_prompt_context()

        # Inject perceptual awareness and scratchpad working memory into system message context
        messages = list(state.get("messages") or [])
        if not messages:
            sys_content = f"{SYSTEM_PROMPT}\n\n[Active Desktop Environment: {win_info}]"
            if scratchpad_context:
                sys_content += f"\n{scratchpad_context}"
            messages = [
                {"role": "system", "content": sys_content},
                {"role": "user", "content": state["user_prompt"]}
            ]
        else:
            update_content = f"[Perception Update: {win_info}]"
            if scratchpad_context:
                update_content += f"\n{scratchpad_context}"
            messages.append({"role": "system", "content": update_content})

        return {
            "active_window": win_info,
            "stuck_detected": False,
            "messages": messages,
            "scratchpad": scratchpad.to_dict()
        }

    def _route_after_perception(self, state: SpaceVState) -> str:
        if state.get("stuck_detected"):
            return "stuck"
        return "proceed"

    def _model_reasoning_node(self, state: SpaceVState) -> dict[str, Any]:
        """
        Node 3: LLM Model Reasoning.
        Sends prompt + tools to Ollama with smart low-RAM routing.
        """
        messages = state.get("messages", [])
        prompt = state.get("user_prompt", "")
        needs_tools = model_router.needs_tools(prompt)

        # Dual-Brain Branch: OpenRouter / Cloud API
        if getattr(self.agent, "provider", "ollama") in ("openai", "openrouter") and hasattr(self.agent, "cloud_client"):
            cloud_model = self.agent.cloud_client.select_cloud_model(prompt, requires_tools=needs_tools)
            self.agent.model = cloud_model
            self.agent.active_role = "cloud_agent"

            resp_dict = self.agent.cloud_client.chat(
                messages=messages,
                tools=OLLAMA_TOOLS_SCHEMA if needs_tools else None,
                model=cloud_model
            )
            content = resp_dict.get("content", "")
            tool_calls = resp_dict.get("tool_calls", [])

            if not tool_calls and content:
                extracted, clean = parse_fallback_tool_calls(content)
                if extracted:
                    tool_calls = extracted
                    content = clean

            msg = {"role": "assistant", "content": content}
            if tool_calls:
                msg["tool_calls"] = tool_calls
            messages.append(msg)

            return {
                "messages": messages,
                "tool_calls": tool_calls,
                "final_response": content,
                "iteration": state.get("iteration", 0) + 1
            }

        selected_model, role = model_router.select_model(prompt, requires_tools=needs_tools)
        self.agent.model = selected_model
        self.agent.active_role = role

        payload = {
            "model": self.agent.model,
            "messages": messages,
            "stream": False,
            "tools": OLLAMA_TOOLS_SCHEMA if needs_tools else [],
            "keep_alive": model_router.get_keep_alive(),
            "options": {"temperature": 0.3, "num_ctx": 2048}
        }

        try:
            res = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=60)
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

                messages.append(msg)
                return {
                    "messages": messages,
                    "tool_calls": tool_calls,
                    "final_response": msg.get("content", ""),
                    "iteration": state.get("iteration", 0) + 1
                }
            else:
                return {
                    "final_response": f"Ollama service error ({res.status_code}): {res.text}",
                    "tool_calls": [],
                    "is_complete": True
                }
        except Exception as e:
            return {
                "final_response": f"Reasoning engine exception: {e!s}",
                "tool_calls": [],
                "is_complete": True
            }

    def _route_after_reasoning(self, state: SpaceVState) -> str:
        tool_calls = state.get("tool_calls", [])
        if tool_calls:
            return "execute_tools"
        return "synthesize"

    def _tool_executor_node(self, state: SpaceVState) -> dict[str, Any]:
        """
        Node 4: Pydantic-Validated Tool Execution.
        Executes tools, notifies live UI callbacks, and checks for modal roadblocks.
        """
        tool_calls = state.get("tool_calls", [])
        messages = list(state.get("messages") or [])
        tool_results = list(state.get("tool_results") or [])
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")

        stuck_detected = False
        clarification_question = None

        import concurrent.futures

        is_gui_required = any(
            c.get("function", {}).get("name", "").startswith("gui_") or
            c.get("function", {}).get("name") in ["media_control", "lock_workstation"]
            for c in tool_calls
        )

        def _exec_single(call):
            func = call.get("function", {})
            t_name = func.get("name")
            t_args = func.get("arguments", {})
            call_id = call.get("id") or f"call_{uuid.uuid4().hex[:8]}"
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"[{ts}] [TOOL CALL]: {t_name}({t_args})")
            if self._current_tool_callback:
                self._current_tool_callback(t_name, t_args, "running")

            res = execute_tool(t_name, t_args)
            print(f"[{ts}] [OS RESULT]: {res}")
            if self._current_tool_callback:
                self._current_tool_callback(t_name, t_args, res)
            return t_name, t_args, res, call_id

        scratchpad = SpaceVScratchpad.from_dict(state.get("scratchpad"))

        # Parallel fan-out for independent I/O, scraping, and telemetry tools
        if len(tool_calls) > 1 and not is_gui_required:
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(tool_calls))) as executor:
                executed_items = list(executor.map(_exec_single, tool_calls))
            for t_name, t_args, res, call_id in executed_items:
                tool_results.append({"name": t_name, "args": t_args, "result": res})
                messages.append({"role": "tool", "tool_call_id": call_id, "content": str(res)})
                scratchpad.record_tool_action(t_name, t_args, str(res))
                if not t_name.startswith("scratchpad_"):
                    scratchpad.advance_step(result=str(res)[:120], success=True)
        else:
            # Deterministic sequential execution for GUI actions & single tools
            for call in tool_calls:
                t_name, t_args, res, call_id = _exec_single(call)
                tool_results.append({"name": t_name, "args": t_args, "result": res})
                messages.append({"role": "tool", "tool_call_id": call_id, "content": str(res)})
                scratchpad.record_tool_action(t_name, t_args, str(res))

                res_str = str(res)
                if "Modal Blocker" in res_str or "stuck at the" in res_str.lower() or "waiting at the" in res_str.lower():
                    from core.modal_interceptor import modal_interceptor
                    gatekeeper = modal_interceptor.detect()
                    stuck_detected = True
                    clarification_question = gatekeeper.question if gatekeeper else (
                        "Sir, I ran into an ambiguous desktop state and require your direction to proceed."
                    )

                if not t_name.startswith("scratchpad_"):
                    scratchpad.advance_step(result=res_str[:120], success=not stuck_detected)

        last_error = None
        for item in tool_results:
            res_str = str(item.get("result", ""))
            if any(err_key in res_str.lower() for err_key in [
                "failed", "error", "could not visually locate", "not in accessibility tree",
                "not found", "permission denied", "access is denied", "file locked"
            ]):
                if not stuck_detected:
                    last_error = res_str
                    break

        return {
            "messages": messages,
            "tool_results": tool_results,
            "tool_calls": [],
            "stuck_detected": stuck_detected,
            "clarification_question": clarification_question,
            "last_error": last_error,
            "scratchpad": scratchpad.to_dict()
        }

    def _route_after_tools(self, state: SpaceVState) -> str:
        if state.get("stuck_detected"):
            return "stuck"
        if state.get("last_error") and state.get("healing_attempts", 0) < 2:
            return "self_healing"

        scratchpad = SpaceVScratchpad.from_dict(state.get("scratchpad"))
        iteration = state.get("iteration", 0)

        # Autonomous multi-step tool chaining: if scratchpad has pending steps, loop up to 6 iterations
        if scratchpad.has_pending_steps() and iteration < 6:
            return "loop_reasoning"
        if iteration < 3 and state.get("tool_calls"):
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
                "last_error": None
            }
        else:
            return {
                "healing_attempts": attempts + 1,
                "stuck_detected": True,
                "clarification_question": f"Sir, I encountered an issue: {diag.get('explanation', last_err)}. How would you prefer to proceed?",
                "last_error": None
            }

    def _route_after_healing(self, state: SpaceVState) -> str:
        if state.get("tool_calls"):
            return "retry_tool"
        return "escalate"

    def _clarification_node(self, state: SpaceVState) -> dict[str, Any]:
        """
        Node 5: Self-Aware Clarification Inquirer.
        When stuck or confused, SpaceV asks the user for explicit guidance instead of hallucinating.
        """
        question = state.get("clarification_question") or (
            "Sir, I encountered an ambiguous state on your desktop and require your guidance to proceed safely."
        )
        if self._current_token_callback:
            self._current_token_callback(question)

        return {
            "final_response": question,
            "is_complete": True
        }

    def _response_synthesizer_node(self, state: SpaceVState) -> dict[str, Any]:
        """
        Node 6: Final Natural Language Response Synthesizer with Real-Time Streaming.
        """
        # If response already exists and no tools executed, stream it directly
        if state.get("final_response") and not state.get("tool_results"):
            content = state["final_response"]
            if self._current_token_callback:
                self._current_token_callback(content)
            return {"final_response": content, "is_complete": True}

        messages = state.get("messages", [])

        # Dual-Brain Branch: OpenRouter / Cloud API
        if getattr(self.agent, "provider", "ollama") in ("openai", "openrouter") and hasattr(self.agent, "cloud_client"):
            synth_dict = self.agent.cloud_client.chat(
                messages=messages,
                tools=None,
                model=self.agent.model,
                token_callback=self._current_token_callback
            )
            full_reply = synth_dict.get("content", "")
            messages.append({"role": "assistant", "content": full_reply})
            return {"final_response": full_reply, "is_complete": True}

        stream_payload = {
            "model": self.agent.model,
            "messages": messages,
            "stream": True,
            "keep_alive": model_router.get_keep_alive(),
            "options": {"temperature": 0.3, "num_ctx": 2048, "num_predict": 300}
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
                            tool_out = execute_tool(t_name, t_args)
                            if self._current_tool_callback:
                                self._current_tool_callback(t_name, t_args, tool_out)
                            full_reply = f"{clean}\n\n{tool_out}".strip() if clean else str(tool_out)

                return {"final_response": full_reply, "messages": messages, "is_complete": True}
            else:
                fallback = "Action completed successfully, Sir."
                if self._current_token_callback:
                    self._current_token_callback(fallback)
                return {"final_response": fallback, "is_complete": True}
        except Exception as e:
            fallback = f"Action completed, Sir. (Note: {e!s})"
            if self._current_token_callback:
                self._current_token_callback(fallback)
            return {"final_response": fallback, "is_complete": True}

    # ==========================================
    # PUBLIC EXECUTION INTERFACE
    # ==========================================

    def run(self, user_prompt: str, tool_callback: Callable | None = None, token_callback: Callable | None = None) -> str:
        """
        Executes the compiled LangGraph state machine with full deterministic node tracking,
        real-time UI callbacks, and closed-loop perception.
        """
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"\n{'='*65}")
        print(f"[{timestamp}] [USER]: {user_prompt}")
        print(f"[{timestamp}] [SPACEV GRAPH]: Executing state machine...")

        self._current_tool_callback = tool_callback
        self._current_token_callback = token_callback

        active_scratchpad.set_goal(user_prompt)
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
            "scratchpad": active_scratchpad.to_dict()
        }

        try:
            final_state = self.app.invoke(initial_state)
            response = final_state.get("final_response", "")
            print(f"[{timestamp}] [SPACEV]: {response}\n{'='*65}\n")
            return response
        finally:
            self._current_tool_callback = None
            self._current_token_callback = None


graph_engine = SpaceVGraphEngine()
