"""
Hybrid Autonomous Stealth Browser Agent for SpaceV.
Integrates Cua Sandboxes, Camoufox/Playwright Anti-Detect,
Local Faster-Whisper CAPTCHA Solving, and LangGraph Cyclical Reasoning.
"""
from hybrid_agent.captcha_solver import LocalAudioCaptchaSolver, local_captcha_solver
from hybrid_agent.cua_bridge import CuaSandboxBridge, cua_bridge
from hybrid_agent.dom_extractor import DOMExtractor
from hybrid_agent.graph import HybridBrowserAgent
from hybrid_agent.state import BrowserAction, DOMElement, HybridAgentState
from hybrid_agent.stealth_browser import StealthBrowserController

__all__ = [
    "BrowserAction",
    "CuaSandboxBridge",
    "DOMElement",
    "DOMExtractor",
    "HybridAgentState",
    "HybridBrowserAgent",
    "LocalAudioCaptchaSolver",
    "StealthBrowserController",
    "cua_bridge",
    "local_captcha_solver",
]
