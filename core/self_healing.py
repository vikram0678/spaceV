"""
Autonomous Self-Healing & Reflection Node for SpaceV LangGraph State Machine.
Inspects tool errors, diagnoses OS/resource conflicts, applies dynamic remediation,
and automatically retries without troubling the user.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("SpaceV.SelfHealing")


class SelfHealingEngine:
    """
    Diagnoses tool and execution errors, computes remediation mutations,
    and coordinates recovery passes in LangGraph.
    """

    MAX_HEALING_ATTEMPTS = 2

    @staticmethod
    def diagnose_failure(tool_name: str, args: dict[str, Any], error_str: str) -> dict[str, Any]:
        """Categorizes failure modes based on OS return codes and traceback signatures."""
        err_lower = error_str.lower()

        # 1. Resource lock / Permission errors
        if any(w in err_lower for w in ["permissionerror", "winerror 32", "used by another process", "access is denied", "file locked"]):
            return {
                "category": "RESOURCE_LOCKED",
                "tool": tool_name,
                "args": args,
                "original_error": error_str,
                "strategy": "retry_with_backoff",
                "explanation": "Target resource is temporarily locked by another process."
            }

        # 2. UI Grounding / Element discovery errors
        if any(w in err_lower for w in ["could not visually locate", "not in accessibility tree", "failed to find", "failsafe"]):
            return {
                "category": "UI_ELEMENT_NOT_FOUND",
                "tool": tool_name,
                "args": args,
                "original_error": error_str,
                "strategy": "switch_grounding_tier",
                "explanation": "UI element was not discovered with default coordinates or OCR parameters."
            }

        # 3. Path resolution or missing file errors
        if any(w in err_lower for w in ["filenotfounderror", "does not exist", "path not found", "cannot find"]):
            return {
                "category": "PATH_NOT_FOUND",
                "tool": tool_name,
                "args": args,
                "original_error": error_str,
                "strategy": "fuzzy_path_resolution",
                "explanation": "Target file or path was not found in the exact specified directory."
            }

        # 4. Process or Application not running
        if any(w in err_lower for w in ["process not running", "no process found", "not active"]):
            return {
                "category": "PROCESS_NOT_FOUND",
                "tool": tool_name,
                "args": args,
                "original_error": error_str,
                "strategy": "launch_and_attach",
                "explanation": "Target application is not currently active in foreground."
            }

        # Default fallback
        return {
            "category": "GENERIC_ERROR",
            "tool": tool_name,
            "args": args,
            "original_error": error_str,
            "strategy": "standard_retry",
            "explanation": "Tool returned an unexpected failure state."
        }

    @classmethod
    def attempt_remediation(
        cls,
        diagnosis: dict[str, Any],
        attempt_number: int
    ) -> tuple[bool, str | None, dict[str, Any] | None, str]:
        """
        Calculates and applies the healing strategy.
        Returns:
            (can_heal: bool, new_tool_name: Optional[str], new_args: Optional[Dict], remedy_message: str)
        """
        if attempt_number >= cls.MAX_HEALING_ATTEMPTS:
            return False, None, None, f"Exhausted {cls.MAX_HEALING_ATTEMPTS} self-healing attempts."

        category = diagnosis.get("category")
        tool = diagnosis.get("tool")
        args = diagnosis.get("args", {})

        # Strategy 1: Resource locked -> Backoff sleep & flush
        if category == "RESOURCE_LOCKED":
            time.sleep(0.35 * (attempt_number + 1))
            return True, tool, args, f"Applied exponential backoff ({int(350 * (attempt_number + 1))}ms) for locked resource."

        # Strategy 2: UI element not found -> Switch between UIA, OCR, and OmniParser Icon Grounding
        if category == "UI_ELEMENT_NOT_FOUND":
            target = args.get("target_text") or args.get("target_name") or args.get("target_description") or ""
            if attempt_number == 0:
                if tool == "gui_click_text":
                    return True, "gui_click_control", {"target_name": target}, f"Switched grounding from OCR to Native UIA for '{target}'."
                else:
                    return True, "gui_click_text", {"target_text": target}, f"Switched grounding to Native OCR for '{target}'."
            else:
                return True, "gui_click_icon", {"target_description": target}, f"Promoting to Microsoft OmniParser v2 icon detector for '{target}'."

        # Strategy 3: Path not found -> Fuzzy Desktop/User directory search
        if category == "PATH_NOT_FOUND":
            filename = args.get("filename") or args.get("folder_name") or ""
            if filename:
                from config import USER_DESKTOP_DIR
                p = Path(filename)
                potential_match = USER_DESKTOP_DIR / p.name
                new_args = dict(args)
                new_args["location"] = "Desktop"
                return True, tool, new_args, f"Remapped unresolved path to user Desktop location: '{potential_match}'."

        # Strategy 4: Application not found -> Launch via Windows shell
        if category == "PROCESS_NOT_FOUND":
            app_name = args.get("app_name") or args.get("process_name") or ""
            return True, "open_application", {"app_name": app_name}, f"Spawning '{app_name}' via Windows shell before re-attempting."

        return False, None, None, f"No automated remediation strategy available for category: {category}."


self_healing_engine = SelfHealingEngine()
