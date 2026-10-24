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
        import re

        # Determine default locus across categories
        locus = (
            args.get("url")
            or args.get("target_url")
            or args.get("filename")
            or args.get("folder_name")
            or args.get("app_name")
            or args.get("target_text")
            or args.get("command")
            or tool_name
        )

        # 1. Dependency or command missing errors
        if any(w in err_lower for w in ["modulenotfounderror", "no module named", "command not found", "not recognized as an internal or external command", "executable file not found in $path", "exit code 127"]):
            pkg_match = ""
            m = re.search(r"no module named ['\"]?([a-zA-Z0-9_\-]+)['\"]?", error_str, re.IGNORECASE)
            if m:
                pkg_match = m.group(1)
            else:
                m_cmd = re.search(r"['\"]?([a-zA-Z0-9_\-]+)['\"]?:\s*command not found", error_str, re.IGNORECASE)
                if m_cmd:
                    pkg_match = m_cmd.group(1)

            dep_locus = pkg_match or args.get("command") or tool_name
            return {
                "category": "DEPENDENCY_MISSING",
                "tool": tool_name,
                "args": args,
                "locus": dep_locus,
                "original_error": error_str,
                "strategy": "install_and_retry",
                "explanation": f"Required module or executable '{dep_locus}' is not installed in the environment.",
                "remediation_options": [
                    {
                        "index": 1,
                        "name": "Auto-Install / Upgrade",
                        "action_type": "command",
                        "action": f"pip install {pkg_match}" if pkg_match else f"sudo apt-get install -y {dep_locus}",
                        "description": f"Install '{dep_locus}' automatically in your python/system environment and retry."
                    },
                    {
                        "index": 2,
                        "name": "Alternative Approach",
                        "action_type": "fallback_tool",
                        "tool": "execute_terminal_command",
                        "args": {"command": f"which {dep_locus} || find / -name {dep_locus} 2>/dev/null"},
                        "description": f"Scan system paths to verify if an alternative binary for '{dep_locus}' exists."
                    },
                    {
                        "index": 3,
                        "name": "Manual Takeover",
                        "action_type": "manual",
                        "description": f"Install '{dep_locus}' manually in your terminal, then reply 'continue'."
                    }
                ]
            }

        # 2. Resource lock / Permission errors
        if any(w in err_lower for w in ["permissionerror", "winerror 32", "used by another process", "access is denied", "file locked"]):
            return {
                "category": "RESOURCE_LOCKED",
                "tool": tool_name,
                "args": args,
                "locus": locus,
                "original_error": error_str,
                "strategy": "retry_with_backoff",
                "explanation": "Target resource is temporarily locked by another process.",
                "remediation_options": [
                    {
                        "index": 1,
                        "name": "Exponential Backoff & Flush",
                        "action_type": "retry",
                        "description": "Wait for resource handles to unlock and retry automatically."
                    },
                    {
                        "index": 2,
                        "name": "Alternative Temp Path",
                        "action_type": "fallback_tool",
                        "tool": "create_file",
                        "args": {"filename": f"/tmp/spacev_fallback_{int(time.time())}.txt"},
                        "description": "Redirect output to an isolated temporary scratchpad file."
                    },
                    {
                        "index": 3,
                        "name": "Manual Process Release",
                        "action_type": "manual",
                        "description": "Close the software locking the file, then reply 'continue'."
                    }
                ]
            }

        # 3. UI Grounding / Element discovery errors
        if any(w in err_lower for w in ["could not visually locate", "not in accessibility tree", "failed to find", "failsafe"]):
            return {
                "category": "UI_ELEMENT_NOT_FOUND",
                "tool": tool_name,
                "args": args,
                "locus": locus,
                "original_error": error_str,
                "strategy": "switch_grounding_tier",
                "explanation": "UI element was not discovered with default coordinates or OCR parameters.",
                "remediation_options": [
                    {
                        "index": 1,
                        "name": "Elevate to OmniParser v2",
                        "action_type": "switch_engine",
                        "description": "Switch grounding engine to deep icon detection & bounding box model."
                    },
                    {
                        "index": 2,
                        "name": "Keyboard Shortcut Navigation",
                        "action_type": "fallback_tool",
                        "tool": "press_hotkey",
                        "args": {"hotkey": "enter"},
                        "description": "Use keyboard accelerator / hotkey instead of visual coordinate clicking."
                    },
                    {
                        "index": 3,
                        "name": "Bring Window to Foreground",
                        "action_type": "manual",
                        "description": "Bring the target application into clear view and reply 'continue'."
                    }
                ]
            }

        # 4. Path resolution or missing file errors
        if any(w in err_lower for w in ["filenotfounderror", "does not exist", "path not found", "cannot find", "not found", "no such file", "can't open file", "cannot open file"]):
            return {
                "category": "PATH_NOT_FOUND",
                "tool": tool_name,
                "args": args,
                "locus": locus,
                "original_error": error_str,
                "strategy": "fuzzy_path_resolution",
                "explanation": "Target file or path was not found in the exact specified directory.",
                "remediation_options": [
                    {
                        "index": 1,
                        "name": "Fuzzy Desktop / Workspace Search",
                        "action_type": "fuzzy_search",
                        "description": "Locate matching filenames across Desktop and workspace automatically."
                    },
                    {
                        "index": 2,
                        "name": "List Directory Contents",
                        "action_type": "fallback_tool",
                        "tool": "list_directory_contents",
                        "args": {"path": "."},
                        "description": "List current workspace files to identify the intended target path."
                    },
                    {
                        "index": 3,
                        "name": "Specify Target Path",
                        "action_type": "manual",
                        "description": "Provide the exact path or create the file, then reply 'continue'."
                    }
                ]
            }

        # 5. Process or Application not running
        if any(w in err_lower for w in ["process not running", "no process found", "not active"]):
            return {
                "category": "PROCESS_NOT_FOUND",
                "tool": tool_name,
                "args": args,
                "locus": locus,
                "original_error": error_str,
                "strategy": "launch_and_attach",
                "explanation": "Target application is not currently active in foreground.",
                "remediation_options": [
                    {
                        "index": 1,
                        "name": "Spawn Application via Shell",
                        "action_type": "fallback_tool",
                        "tool": "open_application",
                        "args": {"app_name": str(locus)},
                        "description": f"Launch '{locus}' via system shell before executing."
                    },
                    {
                        "index": 2,
                        "name": "Direct Command-Line Execution",
                        "action_type": "fallback_tool",
                        "tool": "execute_terminal_command",
                        "args": {"command": str(locus)},
                        "description": f"Run '{locus}' headless inside a terminal session."
                    },
                    {
                        "index": 3,
                        "name": "Launch Manually",
                        "action_type": "manual",
                        "description": f"Launch '{locus}' on your desktop, then reply 'continue'."
                    }
                ]
            }

        # 6. Browser Runtime or Interactive Navigation Failure
        if (
            tool_name in ("browse_interactive_dom", "browse_website_stealth", "click_dom_element", "type_dom_element")
            or any(w in err_lower for w in ["has no attribute 'goto'", "nonetype", "target page, context or browser has been closed", "stealth navigation failed", "playwright", "browser offline"])
        ):
            target_url = args.get("url") or args.get("target_url") or "web portal"
            return {
                "category": "BROWSER_RUNTIME_FAILURE",
                "tool": tool_name,
                "args": args,
                "locus": target_url,
                "original_error": error_str,
                "strategy": "fallback_to_semantic_reader",
                "explanation": "Interactive browser engine encountered a runtime failure or missing Playwright browser binary.",
                "remediation_options": [
                    {
                        "index": 1,
                        "name": "Auto-Install Browser Binaries",
                        "action_type": "command",
                        "action": "playwright install chromium",
                        "description": "Install headless Chromium browser binaries in background and retry."
                    },
                    {
                        "index": 2,
                        "name": "Semantic HTTP Content Extractor",
                        "action_type": "fallback_tool",
                        "tool": "read_web_page",
                        "args": {"url": target_url},
                        "description": f"Degrade to Crawl4AI lightweight HTTP markdown reader for '{target_url}'."
                    },
                    {
                        "index": 3,
                        "name": "Manual Review",
                        "action_type": "manual",
                        "description": "Inspect browser network/dependencies in terminal and reply 'continue'."
                    }
                ]
            }

        # Default fallback
        return {
            "category": "GENERIC_ERROR",
            "tool": tool_name,
            "args": args,
            "locus": locus,
            "original_error": error_str,
            "strategy": "standard_retry",
            "explanation": "Tool returned an unexpected failure state.",
            "remediation_options": [
                {
                    "index": 1,
                    "name": "Retry with Sanitized Parameters",
                    "action_type": "retry",
                    "description": "Sanitize execution inputs and re-attempt tool call."
                },
                {
                    "index": 2,
                    "name": "Execute via Terminal CLI",
                    "action_type": "fallback_tool",
                    "tool": "execute_terminal_command",
                    "args": {"command": f"echo 'Running diagnostic for {tool_name}'"},
                    "description": "Run diagnostic check via terminal command execution."
                },
                {
                    "index": 3,
                    "name": "Live Guidance",
                    "action_type": "manual",
                    "description": "Provide explicit live guidance or new parameters for this step."
                }
            ]
        }

    @classmethod
    def format_clarification_card(cls, diagnosis: dict[str, Any]) -> str:
        """
        Formats a structured, Crawl4AI/Karpathy-style live clarification card
        for display in chat and real-time interaction without stopping the agent.
        """
        tool = diagnosis.get("tool", "system_tool")
        locus = diagnosis.get("locus", "workstation environment")
        category = diagnosis.get("category", "EXECUTION_ROADBLOCK")
        explanation = diagnosis.get("explanation", "An unexpected failure state occurred.")
        options = diagnosis.get("remediation_options", [])

        lines = [
            "⏸️ **SpaceV Live Clarification & Remediation Protocol**",
            f"I encountered an issue executing `{tool}` on `{locus}`.",
            f"**Diagnosis**: {explanation} `[{category}]`\n",
            "Sir, how would you prefer me to proceed?"
        ]
        for opt in options:
            idx = opt.get("index", 1)
            name = opt.get("name", "")
            desc = opt.get("description", "")
            lines.append(f"- **[{idx}] {name}**: {desc}")

        lines.append("\n*(You can reply with 1, 2, 3, or simply tell me what to do live)*")
        return "\n".join(lines)

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

        # Strategy 2: UI element not found -> 3-Step Fail-Safe Reflex (Hotkey -> UIA -> OmniParser -> Clarification)
        if category == "UI_ELEMENT_NOT_FOUND":
            target = args.get("target_text") or args.get("target_name") or args.get("target_description") or ""
            target_clean = str(target).lower().strip()

            # 2.1 Deterministic Hotkey Accelerator Table
            HOTKEY_EQUIVALENTS: dict[str, list[str]] = {
                "close": ["alt", "f4"],
                "exit": ["alt", "f4"],
                "quit": ["alt", "f4"],
                "save": ["ctrl", "s"],
                "search": ["ctrl", "f"],
                "find": ["ctrl", "f"],
                "settings": ["win", "i"],
                "copy": ["ctrl", "c"],
                "paste": ["ctrl", "v"],
                "cut": ["ctrl", "x"],
                "new tab": ["ctrl", "t"],
                "new window": ["ctrl", "n"],
                "refresh": ["f5"],
                "reload": ["ctrl", "r"],
                "address bar": ["ctrl", "l"],
            }
            if target_clean in HOTKEY_EQUIVALENTS and attempt_number == 0:
                hotkey_keys = HOTKEY_EQUIVALENTS[target_clean]
                return True, "gui_press_hotkey", {"keys": hotkey_keys}, f"Switched to deterministic OS hotkey {'+'.join(hotkey_keys)} for action '{target}'."

            if attempt_number == 0:
                if tool == "gui_click_text":
                    return True, "gui_click_control", {"target_name": target}, f"Switched grounding from OCR to Native UIA for '{target}'."
                else:
                    return True, "gui_click_text", {"target_text": target}, f"Switched grounding to Native OCR for '{target}'."
            else:
                return True, "gui_click_icon", {"target_description": target}, f"Promoting to Microsoft OmniParser v2 icon detector for '{target}'."

        # Strategy 3: Path not found -> Fuzzy Desktop/User/Temp directory search
        if category == "PATH_NOT_FOUND":
            filename = (
                args.get("filename")
                or args.get("file_name_or_path")
                or args.get("file_name")
                or args.get("file_path")
                or args.get("folder_name")
                or ""
            )
            if filename:
                from config import USER_DESKTOP_DIR
                p = Path(filename)

                # Check /tmp and /tmp/test candidates first
                tmp_candidates = [
                    Path("/tmp") / p.name,
                    Path("/tmp/test") / p.name,
                    Path("/tmp/spacev_test") / p.name,
                    USER_DESKTOP_DIR / p.name,
                    Path.cwd() / p.name
                ]
                resolved_match = None
                for c in tmp_candidates:
                    if c.exists():
                        resolved_match = c
                        break

                if resolved_match:
                    new_args = dict(args)
                    for k in ("file_name_or_path", "filename", "file_name", "file_path"):
                        if k in new_args:
                            new_args[k] = str(resolved_match)
                    return True, tool, new_args, f"Remapped unresolved path to existing location: '{resolved_match}'."
                else:
                    potential_match = USER_DESKTOP_DIR / p.name
                    new_args = dict(args)
                    new_args["location"] = "Desktop"
                    return True, tool, new_args, f"Remapped unresolved path to user Desktop location: '{potential_match}'."

        # Strategy 4: Application not found -> Launch via Windows shell
        if category == "PROCESS_NOT_FOUND":
            app_name = args.get("app_name") or args.get("process_name") or ""
            return True, "open_application", {"app_name": app_name}, f"Spawning '{app_name}' via Windows shell before re-attempting."

        # Strategy 5: Browser Runtime Failure -> Failover to Crawl4AI Semantic Web Reader
        if category == "BROWSER_RUNTIME_FAILURE" or (tool in ("browse_interactive_dom", "browse_website_stealth")):
            url = args.get("url") or args.get("target_url") or ""
            if url:
                return True, "read_web_page", {"url": url}, f"Interactive browser unavailable ({diagnosis.get('explanation', '')}). Degraded to Crawl4AI semantic reader for '{url}'."

        # Strategy 6: Dependency missing -> pip install if single module
        if category == "DEPENDENCY_MISSING":
            pkg = diagnosis.get("locus", "")
            if pkg and attempt_number == 0:
                return True, "execute_terminal_command", {"command": f"pip install {pkg}"}, f"Executing automated environment installation for '{pkg}'."

        return False, None, None, f"No automated remediation strategy available for category: {category}."


self_healing_engine = SelfHealingEngine()
