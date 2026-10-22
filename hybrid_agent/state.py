"""
State Definition for the Hybrid Autonomous Stealth Browser Agent.
Built with LangGraph & LangChain typed state models.
"""
from __future__ import annotations

from typing import Any, TypedDict


class DOMElement(TypedDict, total=False):
    index: int
    tag: str
    text: str
    role: str
    selector: str
    xpath: str
    is_interactive: bool
    href: str | None
    placeholder: str | None
    input_type: str | None


class BrowserAction(TypedDict, total=False):
    action_type: str  # navigate | click | type | scroll | solve_captcha | extract | finish
    target_index: int | None
    selector: str | None
    value: str | None
    reasoning: str


class HybridAgentState(TypedDict):
    """
    Central state container passed across all LangGraph cyclic nodes.
    """
    task: str
    current_url: str
    page_title: str
    dom_elements: list[DOMElement]
    dom_summary: str
    screenshot_path: str | None
    captcha_detected: bool
    captcha_type: str  # 'recaptcha_v2' | 'hcaptcha' | 'turnstile' | 'none'
    captcha_solved: bool
    plan: list[str]
    actions_history: list[BrowserAction]
    last_action: BrowserAction | None
    extracted_data: dict[str, Any]
    step_count: int
    max_steps: int
    is_complete: bool
    final_result: str
    error: str | None
    cua_sandbox_active: bool
