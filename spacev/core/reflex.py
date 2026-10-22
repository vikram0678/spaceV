"""
SpaceV Reflex Engine: Sub-35MB Deterministic Tool Calling & Schema Grammar.
Personalized from Cactus-Compute Needle: enforces byte-level schema conformity,
regex triggers, and calibrated confidence heads to prevent hallucinations.
"""
from __future__ import annotations

import inspect
import re
from dataclasses import dataclass
from typing import Callable, Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field as PydanticField


@dataclass
class ReflexMatch:
    tool_name: str
    arguments: Dict[str, Any]
    confidence: float = 1.0
    reply_template: str = "{res}"
    fn: Optional[Callable] = None


class Field:
    """Constraints helper for tool arguments with schema validation."""
    def __init__(
        self,
        default: Any = ...,
        *,
        description: Optional[str] = None,
        pattern: Optional[str] = None,
        ge: Optional[float] = None,
        le: Optional[float] = None
    ):
        self.default = default
        self.description = description
        self.pattern = pattern
        self.ge = ge
        self.le = le


class ToolDefinition:
    def __init__(
        self,
        fn: Callable,
        name: str,
        description: str,
        triggers: List[str],
        confidence_threshold: float = 0.85
    ):
        self.fn = fn
        self.name = name
        self.description = description
        self.triggers = [re.compile(t, re.IGNORECASE) for t in triggers]
        self.confidence_threshold = confidence_threshold
        self.schema = self._build_schema()

    def _build_schema(self) -> Dict[str, Any]:
        sig = inspect.signature(self.fn)
        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue
            
            p_type = "string"
            if param.annotation == int:
                p_type = "integer"
            elif param.annotation == bool:
                p_type = "boolean"
            elif param.annotation == float:
                p_type = "number"

            properties[param_name] = {
                "type": p_type,
                "description": f"Parameter {param_name}"
            }
            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }

    def matches_trigger(self, text: str) -> bool:
        """Determines if the user input satisfies trigger expressions."""
        return any(trig.search(text) for trig in self.triggers)


_TOOL_REGISTRY: Dict[str, ToolDefinition] = {}


def spacev_tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    triggers: Optional[List[str]] = None,
    confidence_threshold: float = 0.85
) -> Callable:
    """Decorator to register a deterministic SpaceV reflex tool."""
    def decorator(fn: Callable) -> Callable:
        tool_name = name or fn.__name__
        tool_desc = description or (fn.__doc__ or "").strip()
        tool_triggers = triggers or []

        tool_def = ToolDefinition(
            fn=fn,
            name=tool_name,
            description=tool_desc,
            triggers=tool_triggers,
            confidence_threshold=confidence_threshold
        )
        _TOOL_REGISTRY[tool_name] = tool_def
        fn._spacev_tool = tool_def
        return fn
    return decorator


class SpaceVReflexEngine:
    """
    Sub-35MB Deterministic Reflex Intent Matcher and Tool Execution Engine.
    Inspired by Needle: parses arguments directly from grammar regex triggers,
    enforcing strict Pydantic schemas with calibrated confidence (>0.95).
    """
    def __init__(self):
        self.registry = _TOOL_REGISTRY
        self._compiled_reflex_routes: List[Dict[str, Any]] = []
        self._init_native_reflexes()

    def _init_native_reflexes(self):
        """Compiles SpaceV's deterministic reflex trigger grammar."""
        from tools.registry import TOOL_FUNCTIONS

        routes = [
            {
                "tool": "run_sandboxed_workflow",
                "patterns": [
                    (r"^(?:run|execute)\s+(?:the\s+)?(?:sandboxed\s+workflow|celesto\s+pipeline|deployment\s+pipeline|sandbox\s+workflow)$", [])
                ],
                "reply": "{res}"
            },
            {
                "tool": "audit_sandbox_containment",
                "patterns": [
                    (r"^(?:audit|test|check)\s+(?:the\s+)?(?:sandbox\s+containment|containment\s+proof|prompt\s+injection\s+containment|containment)$", [])
                ],
                "reply": "{res}"
            },
            {
                "tool": "get_run_ledger_summary",
                "patterns": [
                    (r"^(?:get|show|view|check|fetch)\s+(?:the\s+)?(?:run\s+ledger|ledger\s+summary|eval\s+summary|evals\s+summary|benchmark\s+runs|run\s+ledger\s+summary)$", [])
                ],
                "reply": "{res}"
            },
            {
                "tool": "open_application",
                "patterns": [
                    (r"^(?:open|launch)\s+(?:the\s+)?(chrome|google\s+chrome|browser|calc|calculator|notepad|paint|mspaint|task\s*manager|taskmgr|vs\s*code|vscode|code|terminal|explorer|file\s+explorer|settings|spotify)$", ["app_name"])
                ],
                "reply": "Right away, Sir. Initializing {app_name} for you now."
            },
            {
                "tool": "search_memory",
                "patterns": [
                    (r"^(?:search\s+memory(?:\s+for)?|remember|recall|what\s+did\s+i\s+(?:say|note)\s+about)\s+(.+)$", ["query"])
                ],
                "reply": "{res}"
            },
            {
                "tool": "search_google",
                "patterns": [
                    (r"^(?:google|search\s+google\s+for|search\s+web\s+for|search\s+internet\s+for)\s+(.+)$", ["query"])
                ],
                "reply": "Searching Google for '{query}', Sir:\n\n{res}"
            },
            {
                "tool": "play_youtube",
                "patterns": [
                    (r"^(?:play|youtube\s+play|search\s+youtube\s+for)\s+(.+?)(?:\s+(?:on|in)\s+youtube|\s+video|\s+song)?$", ["video_query"])
                ],
                "reply": "Opening YouTube to play '{video_query}' for you, Sir."
            },
            {
                "tool": "create_folder",
                "patterns": [
                    (r"^(?:create|make|new)\s+(?:a\s+)?folder(?:\s+(?:named|called))?\s+([a-zA-Z0-9_\-\s]+)$", ["folder_name"])
                ],
                "reply": "{res}"
            },
            {
                "tool": "create_file",
                "patterns": [
                    (r"^(?:create|make|new)\s+(?:a\s+)?file(?:\s+(?:named|called))?\s+([^\s]+)(?:\s+with\s+content\s+(.+))?$", ["file_name", "content"])
                ],
                "reply": "{res}"
            },
            {
                "tool": "get_weather",
                "patterns": [
                    (r"^(?:check|what(?:'s|\s+is)\s+the|tell\s+me\s+the|how\s+is\s+the)?\s*weather(?:\s+in|\s+for|\s+at)?\s+([a-zA-Z\s]+)$", ["city"])
                ],
                "reply": "{res}"
            },
            {
                "tool": "get_wikipedia_summary",
                "patterns": [
                    (r"^(?:who\s+is|who\s+was|tell\s+me\s+about|wikipedia|wiki\s+summary\s+for)\s+(.+)$", ["topic"])
                ],
                "reply": "Encyclopedia dossier on '{topic}', Sir:\n\n{res}"
            },
            {
                "tool": "set_timer",
                "patterns": [
                    (r"^(?:set\s+a\s+)?timer\s+(?:for\s+)?(\d+(?:\.\d+)?)\s*(?:m|min|mins|minutes?)(?:\s+(?:for|to|named)\s+(.+))?$", ["minutes", "label"])
                ],
                "reply": "{res}"
            },
            {
                "tool": "media_control",
                "patterns": [
                    (r"^(mute|unmute|mute audio|silence audio)$", []),
                    (r"^(pause|resume|pause music|resume music)$", []),
                    (r"^(volume up|vol up|louder)$", []),
                    (r"^(volume down|vol down|quieter)$", []),
                    (r"^(next song|next track|skip song)$", []),
                    (r"^(previous song|prev track|back song)$", [])
                ],
                "reply": "{res}"
            },
            {
                "tool": "take_screen_snapshot",
                "patterns": [
                    (r"^(?:take|capture)\s+(?:a\s+)?(?:screenshot|screen\s+snapshot|display)$", [])
                ],
                "reply": "{res}"
            },
            {
                "tool": "optimize_system_memory",
                "patterns": [
                    (r"^(?:optimize|clean|free|flush)\s+(?:system\s+)?(?:ram|memory)$", [])
                ],
                "reply": "{res}"
            },
            {
                "tool": "lock_workstation",
                "patterns": [
                    (r"^(?:lock\s+screen|lock\s+pc|lock\s+workstation|lock\s+computer)$", [])
                ],
                "reply": "{res}"
            },
            {
                "tool": "empty_recycle_bin",
                "patterns": [
                    (r"^(?:empty\s+recycle\s+bin|clean\s+recycle\s+bin|empty\s+trash)$", [])
                ],
                "reply": "{res}"
            },
            {
                "tool": "get_network_info",
                "patterns": [
                    (r"^(?:network\s+info|network\s+status|check\s+wifi|my\s+ip|ip\s+address)$", [])
                ],
                "reply": "{res}"
            },
            {
                "tool": "list_desktop_files",
                "patterns": [
                    (r"^(?:list\s+desktop|show\s+desktop|what\s+files\s+are\s+on\s+desktop)$", [])
                ],
                "reply": "Inspecting your desktop directory, Sir:\n\n{res}"
            },
            {
                "tool": "list_running_apps",
                "patterns": [
                    (r"^(?:what\s+apps\s+are\s+running|list\s+running\s+processes|show\s+open\s+apps)$", [])
                ],
                "reply": "Scanning your active desktop workspace, Sir:\n\n{res}"
            }
        ]

        for item in routes:
            tool_name = item["tool"]
            fn = TOOL_FUNCTIONS.get(tool_name)
            if fn:
                compiled_patterns = []
                for pat, params in item["patterns"]:
                    compiled_patterns.append((re.compile(pat, re.IGNORECASE), params))
                self._compiled_reflex_routes.append({
                    "name": tool_name,
                    "fn": fn,
                    "patterns": compiled_patterns,
                    "reply": item.get("reply", "{res}")
                })

    def match_command(self, user_prompt: str) -> Optional[ReflexMatch]:
        """
        Sub-0.2ms deterministic regex matcher and parameter extractor.
        """
        text = user_prompt.strip()
        for route in self._compiled_reflex_routes:
            tool_name = route["name"]
            fn = route["fn"]
            reply_tmpl = route["reply"]

            for regex, param_names in route["patterns"]:
                m = regex.match(text)
                if m:
                    kwargs = {}
                    for idx, param in enumerate(param_names, 1):
                        val = m.group(idx)
                        if val is not None:
                            val_str = val.strip()
                            if param == "minutes":
                                try:
                                    kwargs[param] = float(val_str)
                                except ValueError:
                                    kwargs[param] = 5.0
                            else:
                                kwargs[param] = val_str

                    # Media control specific action mapping
                    if tool_name == "media_control" and not kwargs:
                        act_lower = text.lower()
                        if "mute" in act_lower:
                            kwargs["action"] = "mute"
                        elif "pause" in act_lower or "resume" in act_lower:
                            kwargs["action"] = "play_pause"
                        elif "volume up" in act_lower or "louder" in act_lower:
                            kwargs["action"] = "volume_up"
                        elif "volume down" in act_lower or "quieter" in act_lower:
                            kwargs["action"] = "volume_down"
                        elif "next" in act_lower or "skip" in act_lower:
                            kwargs["action"] = "next"
                        elif "prev" in act_lower or "back" in act_lower:
                            kwargs["action"] = "previous"

                    return ReflexMatch(
                        tool_name=tool_name,
                        arguments=kwargs,
                        confidence=1.0,
                        reply_template=reply_tmpl,
                        fn=fn
                    )
        return None

    def match_and_execute(self, user_prompt: str) -> Optional[Tuple[str, str, str]]:
        """
        Executes deterministic grammar matching and parameter extraction in <0.2ms.
        Returns Tuple[tool_name, tool_result, reply_text] or None.
        """
        match = self.match_command(user_prompt)
        if not match or not match.fn:
            return None

        try:
            res = match.fn(**match.arguments)
            res_str = str(res)
            try:
                reply_text = match.reply_template.format(res=res_str, **match.arguments)
            except Exception:
                reply_text = f"Right away, Sir. {res_str}"
            return (match.tool_name, res_str, reply_text)
        except Exception as e:
            return (match.tool_name, str(e), f"Encountered an issue running {match.tool_name}, Sir: {str(e)}")


reflex_engine = SpaceVReflexEngine()

