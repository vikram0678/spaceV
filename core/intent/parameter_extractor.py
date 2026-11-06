"""
Deterministic Parameter & Constraint Extractor for SpaceV.
Extracts structured typed values (numbers, units, app targets, URLs, file paths)
and evaluates negative constraints and preservation rules without brittle phrase templates.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from core.app_catalog import app_catalog


class ParameterExtractor:
    """
    Extracts typed arguments and constraints from natural language utterances
    based on the target capability's parameter requirements.
    """

    # Primary action negation ("don't do X", "never lock Y")
    PRIMARY_NEGATION_PATTERN = re.compile(
        r"\b(?:don't|dont|do\s+not|never|refrain\s+from|no\s+need\s+to)\b",
        re.IGNORECASE
    )

    # Secondary exclusion / negative constraints ("without muting", "except editor")
    EXCLUSION_PATTERN = re.compile(
        r"\b(?:without|except|excluding|other\s+than)\s+([a-zA-Z0-9_\-\s]+?)(?:\s+and|\s*$)",
        re.IGNORECASE
    )

    # Preservation patterns ("keep Z open", "without closing Y")
    PRESERVE_PATTERN = re.compile(
        r"\b(?:keep\s+(?:the\s+)?([a-zA-Z0-9_\-\s]+?)\s+open|without\s+(?:closing|stopping|quitting)\s+(?:the\s+)?([a-zA-Z0-9_\-\s]+))\b",
        re.IGNORECASE
    )

    @classmethod
    def extract_constraints(cls, text: str) -> dict[str, Any]:
        """
        Extracts negation flags, preservation rules, and execution constraints.
        """
        constraints: dict[str, Any] = {
            "negated": False,
            "negated_terms": [],
            "negative_constraints": [],
            "preserve": [],
        }

        # Check if the overall sentence has primary negative polarity directed at an action
        neg_matches = cls.PRIMARY_NEGATION_PATTERN.findall(text)
        if neg_matches:
            constraints["negated"] = True
            constraints["negated_terms"] = [m.lower() for m in neg_matches]

        # Extract exclusion constraints (e.g. "turn down volume without muting")
        for m in cls.EXCLUSION_PATTERN.finditer(text):
            ex_target = (m.group(1) or "").strip()
            if ex_target:
                constraints["negative_constraints"].append(ex_target)

        # Extract preservation constraints (e.g. "close all except editor")
        for m in cls.PRESERVE_PATTERN.finditer(text):
            preserved_target = (m.group(1) or m.group(2) or "").strip()
            if preserved_target:
                constraints["preserve"].append(preserved_target)

        return constraints

    @classmethod
    def extract_for_capability(
        cls,
        capability_name: str,
        user_prompt: str,
        context: Optional[dict[str, Any]] = None,
    ) -> tuple[dict[str, Any], list[str]]:
        """
        Extracts required and optional parameters for a specific capability.
        Returns (extracted_params, missing_required_params).
        """
        params: dict[str, Any] = {}
        missing: list[str] = []
        text = user_prompt.strip()
        lower = text.lower()

        # ---------------------------------------------------------------------
        # 1. Media Controls
        # ---------------------------------------------------------------------
        if capability_name == "os.media_control":
            # Classify specific media action
            if any(k in lower for k in ["mute", "silence", "unmute", "hush"]):
                params["action"] = "mute"
            elif any(k in lower for k in ["pause", "stop playback", "stop the music", "stop audio", "freeze"]):
                params["action"] = "play_pause"
            elif any(k in lower for k in ["resume", "play music", "play playback", "continue playing"]):
                params["action"] = "play_pause"
            elif any(k in lower for k in ["next", "skip", "next song", "next track"]):
                params["action"] = "next"
            elif any(k in lower for k in ["previous", "prev", "back a song", "last song", "prior track"]):
                params["action"] = "previous"
            elif any(k in lower for k in ["volume up", "louder", "crank", "boost sound", "increase volume", "turn up", "raise volume"]):
                params["action"] = "volume_up"
            elif any(k in lower for k in ["volume down", "quieter", "lower volume", "decrease volume", "turn down", "drop volume"]):
                params["action"] = "volume_down"
            else:
                params["action"] = "play_pause"

        # ---------------------------------------------------------------------
        # 2. Display Brightness
        # ---------------------------------------------------------------------
        elif capability_name == "os.set_brightness":
            # Look for explicit percentage or integer (0-100)
            num_match = re.search(r"\b(\d{1,3})\s*%?\b", text)
            if num_match:
                val = int(num_match.group(1))
                params["level"] = max(0, min(100, val))
            else:
                # Qualitative adjustment defaults
                if any(k in lower for k in ["dim", "lower", "darker", "decrease"]):
                    params["level"] = 30
                elif any(k in lower for k in ["boost", "brighten", "lighter", "increase", "max"]):
                    params["level"] = 90
                else:
                    missing.append("level")

        # ---------------------------------------------------------------------
        # 3. Timers
        # ---------------------------------------------------------------------
        elif capability_name == "os.set_timer":
            min_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:m|min|mins|minute|minutes)\b", text, re.I)
            sec_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:s|sec|secs|second|seconds)\b", text, re.I)

            mins = 0.0
            if min_match:
                mins = float(min_match.group(1))
            elif sec_match:
                mins = float(sec_match.group(1)) / 60.0
            else:
                # Standalone digit following "timer"
                digit_match = re.search(r"\btimer\s+(?:for\s+)?(\d+(?:\.\d+)?)\b", text, re.I)
                if digit_match:
                    mins = float(digit_match.group(1))

            if mins > 0:
                params["minutes"] = mins
            else:
                missing.append("minutes")

            # Extract label if specified ("named X", "called X", "for X")
            named_m = re.search(r"\b(?:named|called|titled)\s+([a-zA-Z0-9_\-\s]+)$", text, re.I)
            if named_m:
                params["label"] = named_m.group(1).strip()
            else:
                for_m = re.search(r"\b(?:for|to)\s+([a-zA-Z\s]+)$", text, re.I)
                if for_m and not any(k in for_m.group(1).lower() for k in ["min", "minute", "sec", "second"]):
                    params["label"] = for_m.group(1).strip()
                else:
                    params["label"] = "Timer"

        # 3.5 Browser Profile Switching
        elif capability_name == "os.switch_browser_profile":
            raw_t = re.sub(r"^(?:switch(?:\s+to)?|use|set|select)\s+(?:(?:browser|chrome|brave|edge)\s+)?(?:profile\s+(?:to\s+)?)?", "", text, flags=re.I).strip()
            raw_t = re.sub(r"\s+profile$", "", raw_t, flags=re.I).strip()
            params["profile_target"] = raw_t or "Default"

        # ---------------------------------------------------------------------
        # 4. Application Launches
        # ---------------------------------------------------------------------
        elif capability_name == "os.launch_app":
            # Extract target application candidate
            cleaned = re.sub(r"^(?:hey\s+|please\s+|can\s+you\s+|could\s+you\s+)?(?:open|launch|start|run|bring\s+up)\s+", "", text, flags=re.I).strip()
            cleaned = re.sub(r"\b(?:app|application|program|software|window)\b", "", cleaned, flags=re.I).strip()
            cleaned = re.sub(r"\b(?:for\s+me|please|now)\b", "", cleaned, flags=re.I).strip()

            target_candidate = cleaned
            matched_app = app_catalog.find_app(target_candidate)
            if matched_app:
                params["app_name"] = matched_app.name
                params["display_name"] = matched_app.display_name
                params["app_path"] = getattr(matched_app, "target", "")
            else:
                params["app_name"] = target_candidate
                params["display_name"] = target_candidate.title()
                # Note: If target is not installed, the catalog marks it
                if not app_catalog.find_app(target_candidate):
                    params["uninstalled"] = True

        # ---------------------------------------------------------------------
        # 5. Process Termination
        # ---------------------------------------------------------------------
        elif capability_name == "os.kill_process":
            proc_target = re.sub(r"^(?:force\s+)?(?:kill|terminate|close|end|stop)\s+(?:process\s+|task\s+|app\s+)?", "", text, flags=re.I).strip()
            proc_target = re.sub(r"\b(?:process|app|program)\b", "", proc_target, flags=re.I).strip()
            if proc_target:
                params["process_name"] = proc_target
            else:
                missing.append("process_name")

        # ---------------------------------------------------------------------
        # 6. Web Searches & GUI Automation
        # ---------------------------------------------------------------------
        elif capability_name == "web.search_google":
            from core.query_parser import parse_search_intent
            clean_q, _, _ = parse_search_intent(text)
            query = clean_q or re.sub(r"^(?:search\s+(?:google\s+(?:for\s+)?)?|google\s+(?:for\s+)?|look\s+up\s+)", "", text, flags=re.I).strip()
            params["query"] = query or "Google"

        elif capability_name == "web.gui_search":
            from core.query_parser import parse_search_intent
            clean_q, _, _ = parse_search_intent(text)
            if not clean_q:
                clean_q = re.sub(r"^(?:(?:hey|please)\s+)?(?:open\s+(?:browser|chrome|brave|edge)\s+and\s+)?(?:search\s+(?:google\s+(?:for\s+)?)?|google\s+)", "", text, flags=re.I).strip()
                clean_q = re.sub(r"\b(?:and\s+)?(?:click|open)\s+(?:the\s+)?(?:first|top)?\s*results?\b", "", clean_q, flags=re.I).strip()
                clean_q = re.sub(r"^(?:for\s+)", "", clean_q).strip()
            params["query"] = clean_q or "Google"

        # ---------------------------------------------------------------------
        # 7. Media Playback (YouTube / Web)
        # ---------------------------------------------------------------------
        elif capability_name == "web.play_media":
            raw_q = re.sub(r"^(?:(?:hey|hi|hello|please)\s+)?(?:open\s+(?:browser|chrome|brave|edge)\s+)?(?:open\s+)?(?:play|watch|listen\s+to|search\s+for)\s+", "", text, flags=re.I).strip()
            raw_q = re.sub(r"\s+(?:on\s+youtube|in\s+browser)\b", "", raw_q, flags=re.I).strip()
            raw_q = re.sub(r"\s+(?:video|song|track)\b", "", raw_q, flags=re.I).strip()
            raw_q = re.sub(r"\s+play(?:\s+also)?$", "", raw_q, flags=re.I).strip()
            params["query"] = raw_q or "music"

        # ---------------------------------------------------------------------
        # 8. Web URL Navigation
        # ---------------------------------------------------------------------
        elif capability_name == "web.open_url":
            url_match = re.search(r"https?://[^\s]+|www\.[^\s]+", text, re.I)
            if url_match:
                params["url"] = url_match.group(0)
            else:
                # Direct domain navigation (e.g. "go to github.com")
                domain_match = re.search(r"\b([a-zA-Z0-9\-]+\.(?:com|org|io|net|edu|dev|ai|app))\b", text, re.I)
                if domain_match:
                    params["url"] = f"https://{domain_match.group(1)}"
                else:
                    missing.append("url")

        # ---------------------------------------------------------------------
        # 9. Career Job Searches
        # ---------------------------------------------------------------------
        elif capability_name == "career.search_jobs":
            from core.memory import memory
            loc_m = re.search(r"\b(?:in|at|near|around)\s+([a-zA-Z\s]+?)(?:\s+and\s+save|\s+and|\s*$)", text, re.I)
            user_loc = memory.get_preference("career", "target_location") or "remote"
            params["location"] = loc_m.group(1).strip() if loc_m else user_loc

            role_str = re.sub(r"\b(?:in|at|near|around)\s+([a-zA-Z\s]+)", "", text, flags=re.I)
            role_clean = re.sub(r"\b(?:search|for|harvest|find|jobs?|internships?|openings?|vacancies|and\s+save\s+to\s+desktop|save\s+to\s+desktop)\b", "", role_str, flags=re.I).strip()
            user_role = memory.get_preference("career", "target_role") or "software engineer"
            params["role"] = role_clean or user_role
            params["save_to_desktop"] = "save to desktop" in text.lower() or "desktop" in text.lower()

        # ---------------------------------------------------------------------
        # 10. File Operations
        # ---------------------------------------------------------------------
        elif capability_name == "fs.create_folder":
            f_match = re.search(r"(?:folder|directory)\s+(?:named\s+|called\s+)?([a-zA-Z0-9_\-\.]+)", text, re.I)
            if f_match:
                params["folder_name"] = f_match.group(1).strip()
            else:
                missing.append("folder_name")
            params["location"] = "Workspace" if "workspace" in lower else "Desktop"

        elif capability_name == "fs.open_editor":
            params["file_name"] = ""
            params["editor"] = "auto"
            # Extract target file if named
            file_match = re.search(r"\b([a-zA-Z0-9_\-\.]+\.[a-zA-Z0-9]+)\b", text)
            if file_match:
                params["file_name"] = file_match.group(1)
            if "notepad" in lower:
                params["editor"] = "notepad"
            elif "vscode" in lower or "vs code" in lower or "code" in lower:
                params["editor"] = "code"
            elif "cursor" in lower:
                params["editor"] = "cursor"

        return params, missing
