"""
Hybrid Autonomous Stealth Browser Agent for SpaceV.
Integrates Cua Sandboxes, Camoufox/Playwright Anti-Detect,
Local Faster-Whisper CAPTCHA Solving, and LangGraph Cyclical Reasoning.
"""
from hybrid_agent.state import HybridAgentState, DOMElement, BrowserAction
from hybrid_agent.graph import HybridBrowserAgent
from hybrid_agent.captcha_solver import LocalAudioCaptchaSolver, local_captcha_solver
from hybrid_agent.stealth_browser import StealthBrowserController
from hybrid_agent.dom_extractor import DOMExtractor
from hybrid_agent.cua_bridge import CuaSandboxBridge, cua_bridge

__all__ = [
    "HybridAgentState",
    "DOMElement",
    "BrowserAction",
    "HybridBrowserAgent",
    "LocalAudioCaptchaSolver",
    "local_captcha_solver",
    "StealthBrowserController",
    "DOMExtractor",
    "CuaSandboxBridge",
    "cua_bridge",
]
