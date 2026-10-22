"""
LangGraph Multi-Step Cyclic State Machine for the Hybrid Autonomous Browser Agent.
Coordinates Ollama model reasoning, DOM extraction, local Faster-Whisper CAPTCHA solving,
and stealth browser automation.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Dict, Any, List, Optional

import requests
from langgraph.graph import StateGraph, END

from config import OLLAMA_BASE_URL, PRIMARY_MODEL
from hybrid_agent.state import HybridAgentState, BrowserAction, DOMElement
from hybrid_agent.stealth_browser import StealthBrowserController
from hybrid_agent.captcha_solver import local_captcha_solver
from hybrid_agent.cua_bridge import cua_bridge

logger = logging.getLogger("SpaceV.HybridAgentGraph")

SYSTEM_BROWSER_PROMPT = """You are an autonomous web-browsing agent.
Your objective is to accomplish the user's task on the web.
You will be provided with:
1. Current Page Title & URL
2. A list of indexed interactive elements on the page in format:
   [Index] <tag attributes> "Text/Value"
3. Previous actions taken

RULES:
1. Choose the next logical action to make progress toward the user's goal.
2. Output ONLY a valid JSON object matching this schema:
{
    "action": "click" | "type" | "navigate" | "scroll" | "finish",
    "index": <integer index of element, or null if navigating/scrolling>,
    "value": "<text to type or URL to navigate to, or 'down'/'up' for scroll>",
    "press_enter": true | false,
    "reasoning": "<brief explanation of why this action moves closer to the goal>",
    "extracted_answer": "<final answer for the user if action is finish>"
}
3. If the task is completed and you have found the requested information, set action to "finish" and include the extracted_answer.
"""


class HybridBrowserAgent:
    """
    Enterprise-grade autonomous browser agent orchestrating:
    - Camoufox / Playwright stealth execution
    - Local neural Faster-Whisper audio CAPTCHA solver
    - Cua sandbox micro-VM bridge
    - LangGraph multi-step cyclic execution loop
    """

    def __init__(self, headless: bool = False, max_steps: int = 15):
        self.headless = headless
        self.max_steps = max_steps
        self.browser = StealthBrowserController(headless=headless)
        self.workflow = self._compile_graph()

    def _compile_graph(self) -> Any:
        graph = StateGraph(HybridAgentState)

        # 1. Define Nodes
        graph.add_node("init_browser", self._init_browser_node)
        graph.add_node("inspect_page", self._inspect_page_node)
        graph.add_node("solve_captcha", self._solve_captcha_node)
        graph.add_node("reason_and_plan", self._reason_and_plan_node)
        graph.add_node("execute_action", self._execute_action_node)
        graph.add_node("verify_completion", self._verify_completion_node)

        # 2. Define Edges & Flow
        graph.set_entry_point("init_browser")
        graph.add_edge("init_browser", "inspect_page")

        # Routing after page inspection
        graph.add_conditional_edges(
            "inspect_page",
            self._route_after_inspection,
            {
                "solve_captcha": "solve_captcha",
                "reason_and_plan": "reason_and_plan"
            }
        )

        # Re-inspect after attempting CAPTCHA solve
        graph.add_edge("solve_captcha", "inspect_page")

        # Routing after reasoning
        graph.add_conditional_edges(
            "reason_and_plan",
            self._route_after_reasoning,
            {
                "execute_action": "execute_action",
                "finish": END
            }
        )

        graph.add_edge("execute_action", "verify_completion")

        # Routing after action verification (Loop cycle or finish)
        graph.add_conditional_edges(
            "verify_completion",
            self._route_after_verification,
            {
                "loop_next_step": "inspect_page",
                "finish": END
            }
        )

        return graph.compile()

    # --- Node Implementations ---

    def _init_browser_node(self, state: HybridAgentState) -> Dict[str, Any]:
        print(f"\n[HybridAgent] 🚀 Initializing stealth browser for task: '{state['task']}'")
        self.browser.start()

        # Check Cua sandbox status
        cua_active = cua_bridge.check_availability()
        if cua_active:
            print("[HybridAgent] 🛡️ Cua Spaces sandbox detected on port 3211. Running in isolated container.")
        else:
            print("[HybridAgent] 💻 Running with local anti-detect stealth profile.")

        # Determine starting URL
        task = state["task"].strip()
        url_match = re.search(r"https?://\S+", task)
        if url_match:
            start_url = url_match.group(0)
        elif "google" in task.lower():
            start_url = "https://www.google.com"
        else:
            # Default to DuckDuckGo/Google search for query
            query = re.sub(r"^(?:search|look\s+up|find|browse\s+to|navigate\s+to)\s+", "", task, flags=re.IGNORECASE)
            start_url = f"https://www.google.com/search?q={requests.utils.quote(query)}"

        url, title = self.browser.navigate(start_url)
        return {
            "current_url": url,
            "page_title": title,
            "cua_sandbox_active": cua_active,
            "step_count": 0,
            "is_complete": False,
            "actions_history": [],
            "extracted_data": {},
            "plan": []
        }

    def _inspect_page_node(self, state: HybridAgentState) -> Dict[str, Any]:
        page = self.browser.page
        url = page.url
        title = page.title()

        # 1. Check for CAPTCHA challenges
        has_captcha, captcha_type = local_captcha_solver.detect_captcha(page)

        # 2. Extract DOM interactive elements
        elements, summary = self.browser.get_dom_state()

        print(f"[HybridAgent] 👁️ Inspected page: '{title}' ({len(elements)} interactable nodes found)")
        if has_captcha:
            print(f"[HybridAgent] 🚨 Detected bot barrier: [{captcha_type.upper()}]")

        return {
            "current_url": url,
            "page_title": title,
            "dom_elements": elements,
            "dom_summary": summary,
            "captcha_detected": has_captcha,
            "captcha_type": captcha_type,
            "captcha_solved": False if has_captcha else True
        }

    def _route_after_inspection(self, state: HybridAgentState) -> str:
        if state.get("captcha_detected") and not state.get("captcha_solved"):
            return "solve_captcha"
        return "reason_and_plan"

    def _solve_captcha_node(self, state: HybridAgentState) -> Dict[str, Any]:
        c_type = state.get("captcha_type", "")
        page = self.browser.page
        print(f"[HybridAgent] ⚡ Launching automated zero-cost solver for {c_type}...")

        success = False
        if c_type == "recaptcha_v2":
            success = local_captcha_solver.solve_recaptcha_audio(page)
        elif c_type == "turnstile":
            success = local_captcha_solver.solve_turnstile(page)

        if success:
            print("[HybridAgent] ✅ CAPTCHA challenge cleared!")
            return {"captcha_detected": False, "captcha_solved": True}
        else:
            print("[HybridAgent] ⚠️ Automatic bypass incomplete. Resuming navigation.")
            return {"captcha_detected": False, "captcha_solved": False}

    def _reason_and_plan_node(self, state: HybridAgentState) -> Dict[str, Any]:
        prompt = (
            f"GOAL: {state['task']}\n\n"
            f"CURRENT PAGE: {state['page_title']} ({state['current_url']})\n\n"
            f"INTERACTABLE ELEMENTS:\n{state['dom_summary']}\n\n"
            f"PREVIOUS ACTIONS:\n{json.dumps(state.get('actions_history', [])[-3:])}\n\n"
            "What is the single next best action to achieve the goal? Respond strictly in JSON."
        )

        payload = {
            "model": PRIMARY_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_BROWSER_PROMPT},
                {"role": "user", "content": prompt}
            ],
            "stream": False,
            "options": {"temperature": 0.1}
        }

        try:
            resp = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=30)
            if resp.status_code == 200:
                raw_reply = resp.json().get("message", {}).get("content", "")
                
                # Parse JSON action
                clean_json = re.search(r"\{.*\}", raw_reply, re.DOTALL)
                if clean_json:
                    action_data = json.loads(clean_json.group(0))
                else:
                    action_data = {"action": "finish", "extracted_answer": raw_reply}
            else:
                action_data = {"action": "finish", "extracted_answer": "Model inference failed."}

        except Exception as e:
            logger.error(f"[HybridAgent] Reasoning error: {e}")
            action_data = {"action": "finish", "extracted_answer": f"Error: {e}"}

        action: BrowserAction = {
            "action_type": action_data.get("action", "finish"),
            "target_index": action_data.get("index"),
            "value": action_data.get("value"),
            "reasoning": action_data.get("reasoning", "")
        }

        print(f"[HybridAgent] 🧠 Next Action: [{action['action_type'].upper()}] - {action['reasoning']}")

        if action["action_type"] == "finish":
            return {
                "last_action": action,
                "is_complete": True,
                "final_result": action_data.get("extracted_answer", "Task complete.")
            }

        return {"last_action": action, "is_complete": False}

    def _route_after_reasoning(self, state: HybridAgentState) -> str:
        if state.get("is_complete") or (state.get("last_action", {}).get("action_type") == "finish"):
            return "finish"
        return "execute_action"

    def _execute_action_node(self, state: HybridAgentState) -> Dict[str, Any]:
        action = state.get("last_action", {})
        a_type = action.get("action_type")
        target_idx = action.get("target_index")
        val = action.get("value")

        if a_type == "click" and target_idx is not None:
            self.browser.click_element_by_index(target_idx)
        elif a_type == "type" and target_idx is not None:
            self.browser.type_element_by_index(target_idx, val or "", press_enter=True)
        elif a_type == "navigate" and val:
            self.browser.navigate(val)
        elif a_type == "scroll":
            self.browser.scroll(direction=val or "down")

        history = state.get("actions_history", [])
        history.append(action)

        step = state.get("step_count", 0) + 1
        return {"actions_history": history, "step_count": step}

    def _verify_completion_node(self, state: HybridAgentState) -> Dict[str, Any]:
        step = state.get("step_count", 0)
        if step >= self.max_steps:
            print(f"[HybridAgent] 🛑 Max step limit ({self.max_steps}) reached. Finalizing.")
            return {
                "is_complete": True,
                "final_result": f"Reached maximum allowed steps ({self.max_steps})."
            }
        return {"is_complete": False}

    def _route_after_verification(self, state: HybridAgentState) -> str:
        if state.get("is_complete"):
            return "finish"
        return "loop_next_step"

    def run(self, task: str) -> str:
        """Executes the full LangGraph loop on the given task."""
        initial_state: HybridAgentState = {
            "task": task,
            "current_url": "",
            "page_title": "",
            "dom_elements": [],
            "dom_summary": "",
            "screenshot_path": None,
            "captcha_detected": False,
            "captcha_type": "none",
            "captcha_solved": False,
            "plan": [],
            "actions_history": [],
            "last_action": None,
            "extracted_data": {},
            "step_count": 0,
            "max_steps": self.max_steps,
            "is_complete": False,
            "final_result": "",
            "error": None,
            "cua_sandbox_active": False
        }

        try:
            final_state = self.workflow.invoke(initial_state)
            return final_state.get("final_result", "Completed successfully.")
        finally:
            self.browser.close()
