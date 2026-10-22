"""
State Definition for the Hybrid Autonomous Stealth Browser Agent.
Built with LangGraph & LangChain typed state models.
"""
from __future__ import annotations

from typing import TypedDict, List, Dict, Any, Optional


class DOMElement(TypedDict, total=False):
    index: int
    tag: str
    text: str
    role: str
    selector: str
    xpath: str
    is_interactive: bool
    href: Optional[str]
    placeholder: Optional[str]
    input_type: Optional[str]


class BrowserAction(TypedDict, total=False):
    action_type: str  # navigate | click | type | scroll | solve_captcha | extract | finish
    target_index: Optional[int]
    selector: Optional[str]
    value: Optional[str]
    reasoning: str


class HybridAgentState(TypedDict):
    """
    Central state container passed across all LangGraph cyclic nodes.
    """
    task: str
    current_url: str
    page_title: str
    dom_elements: List[DOMElement]
    dom_summary: str
    screenshot_path: Optional[str]
    captcha_detected: bool
    captcha_type: str  # 'recaptcha_v2' | 'hcaptcha' | 'turnstile' | 'none'
    captcha_solved: bool
    plan: List[str]
    actions_history: List[BrowserAction]
    last_action: Optional[BrowserAction]
    extracted_data: Dict[str, Any]
    step_count: int
    max_steps: int
    is_complete: bool
    final_result: str
    error: Optional[str]
    cua_sandbox_active: bool
