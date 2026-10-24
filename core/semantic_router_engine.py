"""
Aurelio Semantic Router Fast-Path Engine for SpaceV.
Performs fuzzy natural language intent classification and tool dispatching in <4ms
without consuming LLM tokens, cloud APIs, or GPU inference compute.
"""
import logging
import math
import re
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("SpaceV.SemanticRouter")

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False

try:
    from semantic_router import IndexedRouter, Route as ExternalRoute
    from semantic_router.encoders.base import DenseEncoder
    _HAS_SEMANTIC_ROUTER = True
except ImportError:
    _HAS_SEMANTIC_ROUTER = False
    logger.info("[SemanticRouter] 'semantic-router' package not found; using SpaceV native ultra-low-latency (<0.1ms) pure-Python semantic vector engine.")


@dataclass
class NativeRoute:
    name: str
    utterances: list[str]


Route = ExternalRoute if _HAS_SEMANTIC_ROUTER else NativeRoute


def _fnv1a(s: str) -> int:
    h = 2166136261
    for b in s.encode("utf-8"):
        h = (h ^ b) * 16777619
        h &= 0xFFFFFFFF
    return h

DOMAIN_KEYWORD_WEIGHTS = {
    "ram": 9.0, "cpu": 9.0, "memory": 8.0, "hardware": 7.0, "diagnostics": 7.0, "stats": 7.0,
    "time": 8.0, "clock": 8.0, "date": 7.0,
    "mute": 9.0, "volume": 8.0, "louder": 7.0, "quieter": 7.0, "music": 7.0,
    "screenshot": 8.0, "clipboard": 8.0, "recycle": 8.0, "trash": 8.0, "ghost": 8.0,
    "clean": 7.0, "flush": 7.0, "lock": 8.0, "wifi": 8.0, "network": 8.0,
    "youtube": 9.0, "video": 8.0, "play": 7.0, "watch": 7.0,
    "editor": 9.0, "notepad": 9.0, "vscode": 8.0, "code": 5.0, "write": 1.0,
    "google": 9.0, "search": 8.0, "browse": 7.0,
    "capabilities": 8.0, "features": 7.0, "help": 8.0
}


def encode_sparse_text(text: str, dim: int = 4096) -> dict[int, float]:
    """Pure-Python sub-millisecond sparse semantic encoder (FNV-1a + n-grams + L2 norm)."""
    text = text.lower().strip()
    vec: dict[int, float] = {}
    words = text.split()
    for w in words:
        h = _fnv1a(w) % dim
        weight = DOMAIN_KEYWORD_WEIGHTS.get(w, 1.0 + min(len(w) * 0.15, 1.5))
        vec[h] = vec.get(h, 0.0) + weight
    for i in range(max(0, len(text) - 2)):
        h3 = _fnv1a(text[i:i+3]) % dim
        vec[h3] = vec.get(h3, 0.0) + 0.35
    for i in range(max(0, len(text) - 3)):
        h4 = _fnv1a(text[i:i+4]) % dim
        vec[h4] = vec.get(h4, 0.0) + 0.20

    norm = math.sqrt(sum(v * v for v in vec.values()))
    if norm > 0:
        for k in vec:
            vec[k] /= norm
    return vec


if _HAS_SEMANTIC_ROUTER and _HAS_NUMPY:
    class SemanticFastEncoder(DenseEncoder):
        """
        Sub-millisecond dense semantic encoder for Aurelio Semantic Router.
        """
        name: str = "spacev-semantic-fast-4096"
        type: str = "dense"

        def __call__(self, docs: list[Any]) -> list[list[float]]:
            dim = 4096
            results = []
            for d in docs:
                sparse = encode_sparse_text(str(d), dim=dim)
                vec = np.zeros(dim, dtype=np.float32)
                for idx, val in sparse.items():
                    vec[idx] = val
                results.append(vec.tolist())
            return results

        async def acall(self, docs: list[Any]) -> list[list[float]]:
            return self(docs)
else:
    class SemanticFastEncoder:  # type: ignore
        pass


class SemanticRouterEngine:
    """
    High-Performance Fast-Path Intent Dispatcher powered by Aurelio semantic-router.
    Resolves natural language queries directly to SpaceV operating tools in <2ms.
    """
    DEFAULT_CONFIDENCE_THRESHOLD = 0.65

    def __init__(self, confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD):
        self.confidence_threshold = confidence_threshold
        self.router: Any | None = None
        self.native_routes: list[tuple[str, dict[int, float]]] = []
        self._init_routes()

    def _init_routes(self):
        """Compiles SpaceV semantic routes into IndexedRouter or native sparse vectors."""
        routes = [
            Route(name="greeting", utterances=[
                "hello", "hi spacev", "hey spacev", "good morning", "good afternoon",
                "good evening", "how are you doing", "what is up", "sup bro", "hello there spacev",
                "greetings spacev", "hey buddy"
            ]),
            Route(name="gratitude", utterances=[
                "thank you", "thanks a lot", "appreciate it", "great work", "good job spacev",
                "awesome job", "well done buddy", "thanks for the help", "much appreciated"
            ]),
            Route(name="farewell", utterances=[
                "goodbye", "see you later", "bye spacev", "catch you soon", "talk to you later",
                "have a good day", "signing off", "take care spacev"
            ]),
            Route(name="status_ping", utterances=[
                "are you there", "are you alive", "ping spacev", "status check", "are you ready",
                "system check", "ready for command", "spacev ping", "are you listening"
            ]),
            Route(name="identity", utterances=[
                "who are you", "what is your name", "identify yourself", "tell me who you are",
                "who made you", "introduce yourself", "what are you called"
            ]),
            Route(name="get_current_time", utterances=[
                "what time is it", "what is the time", "tell me current time", "what date is today",
                "current time now", "what is today's date", "tell me the time please", "what time is it right now"
            ]),
            Route(name="get_system_stats", utterances=[
                "system stats", "system status", "check cpu usage", "check ram memory",
                "computer hardware status", "pc performance diagnostics", "how much ram is being used",
                "check battery and cpu", "diagnostics", "check hardware stats", "how is my pc performing"
            ]),
            Route(name="optimize_system_memory", utterances=[
                "optimize memory", "clean ram", "free up memory", "flush ram cache",
                "clear system memory", "free up ram on pc", "clean up computer memory", "free ram now"
            ]),
            Route(name="get_network_info", utterances=[
                "network info", "network status", "check wifi connection", "what is my ip address",
                "internet connection diagnostics", "ping internet", "wifi status check", "is internet working"
            ]),
            Route(name="lock_workstation", utterances=[
                "lock screen", "lock workstation", "secure computer immediately", "lock windows desktop",
                "lock my pc", "lock the screen", "secure desktop right now"
            ]),
            Route(name="empty_recycle_bin", utterances=[
                "empty recycle bin", "clean trash bin", "purge deleted files", "clear recycle bin",
                "empty computer trash", "purge recycle bin"
            ]),
            Route(name="take_screen_snapshot", utterances=[
                "take screenshot", "capture screen", "snap display", "screenshot my monitor",
                "capture current screen", "take a screenshot of this screen"
            ]),
            Route(name="get_active_window_info", utterances=[
                "what window is active", "what am i looking at", "current active application",
                "which program is focused", "focused window info", "active screen window"
            ]),
            Route(name="read_clipboard_text", utterances=[
                "read clipboard", "check clipboard", "what is on my clipboard", "show clipboard content",
                "inspect clipboard text", "what text did i copy"
            ]),
            Route(name="media_play_pause", utterances=[
                "pause music", "resume music", "toggle media playback", "play music", "stop audio playback",
                "pause track", "resume playback"
            ]),
            Route(name="media_next", utterances=[
                "next song", "next track", "skip to next track", "skip song", "play next song"
            ]),
            Route(name="media_previous", utterances=[
                "previous song", "previous track", "back to previous song", "play previous track", "go back a song"
            ]),
            Route(name="media_mute", utterances=[
                "mute audio", "unmute sound", "silence system volume", "mute sound", "toggle audio mute",
                "silence volume immediately", "mute computer"
            ]),
            Route(name="media_volume_up", utterances=[
                "volume up", "increase sound level", "louder volume", "turn up volume", "raise sound volume",
                "make it louder"
            ]),
            Route(name="media_volume_down", utterances=[
                "volume down", "decrease sound level", "quieter volume", "turn down volume", "lower sound volume",
                "make it quieter"
            ]),
            Route(name="list_desktop_files", utterances=[
                "list desktop files", "what files are on my desktop", "show desktop items", "check files on desktop",
                "inspect desktop directory", "what items are on the desktop"
            ]),
            Route(name="list_running_apps", utterances=[
                "what apps are running", "list running processes", "show open applications",
                "active desktop programs", "which applications are open", "what programs are running"
            ]),
            Route(name="toggle_ghost_mode", utterances=[
                "activate ghost mode", "enable ghost mode", "turn on ghost mode", "background automation mode",
                "start ghost mode"
            ]),
            Route(name="get_clipboard_history", utterances=[
                "show clipboard history", "recent clipboard items", "what did i copy earlier",
                "clipboard history timeline", "past clipboard entries"
            ]),
            Route(name="media_play_youtube", utterances=[
                "open youtube and play top video",
                "hey open youtube and uma telugu traveller latest video play also",
                "open youtube and play video",
                "play interstellar on youtube",
                "put on some lofi on youtube",
                "play song on youtube",
                "play video on youtube",
                "search youtube and play",
                "watch video on youtube",
                "play on youtube",
                "open youtube video",
                "play youtube music",
                "youtube play video",
                "play latest video on youtube"
            ]),
            Route(name="open_text_editor", utterances=[
                "open editor and write the code",
                "can you open editor and write the code",
                "open editor and write code",
                "open editor",
                "launch code editor",
                "open text editor",
                "open notepad",
                "launch notepad",
                "open vscode",
                "launch vscode",
                "launch editor"
            ]),
            Route(name="search_google", utterances=[
                "search google for python tutorial",
                "google search latest news",
                "search the web for weather",
                "search google",
                "google search",
                "search on google",
                "lookup on google"
            ]),
            Route(name="capabilities", utterances=[
                "what can you do",
                "what are your capabilities",
                "show capabilities",
                "what can you done",
                "commands",
                "what tools do you have",
                "help"
            ]),
        ]

        if _HAS_SEMANTIC_ROUTER and _HAS_NUMPY:
            try:
                self.router = IndexedRouter(
                    encoder=SemanticFastEncoder(),
                    routes=routes,
                    top_k=3
                )
                self.router("warmup")
                logger.info("[SemanticRouter] Aurelio semantic-router initialized with 24 native SpaceV intent routes.")
            except Exception as e:
                logger.error(f"[SemanticRouter] Initialization failure: {e}")
                self.router = None

        # Always prepare high-speed pure-Python sparse vectors for instant fallback (<0.1ms)
        self.native_routes: list[tuple[str, dict[int, float]]] = []
        for r in routes:
            for u in r.utterances:
                self.native_routes.append((r.name, encode_sparse_text(u)))
        logger.info(f"[SemanticRouter] Native pure-Python sparse engine initialized with {len(self.native_routes)} intent vectors.")

    def route(self, user_prompt: str) -> tuple[str, float, float] | None:
        """
        Classifies intent using Aurelio semantic-router or native pure-Python sparse cosine matching (<0.1ms).
        Returns Tuple[intent_name, confidence, latency_ms] or None if confidence is below threshold.
        """
        if not user_prompt or not user_prompt.strip():
            return None

        # Check Cognitive Reflex Gatekeeper (Kahneman System 1 vs System 2 Separation)
        from core.reflex_gatekeeper import ReflexGatekeeper
        if ReflexGatekeeper.should_bypass_fast_router(user_prompt):
            return None

        # Ignore long prompts that clearly require deep reasoning or coding
        words = user_prompt.strip().split()
        if len(words) > 25:
            return None

        t0 = time.perf_counter()

        def _is_safe_route(route_name: str) -> bool:
            lower_p = user_prompt.lower()
            if route_name == "open_text_editor":
                exec_terms = {"run", "execute", "exec", "terminal", "test", "compile"}
                p_words = set(re.findall(r"\b[a-z0-9_+#]+\b", lower_p))
                if bool(p_words & exec_terms):
                    return False
            if route_name == "media_play_youtube":
                if re.search(r"\b(?:don't|dont|do\s+not|not|never|without)\s+(?:play|watch|want\s+to\s+play)\b", lower_p) or re.search(r"\b(?:dont|don't|do\s+not)\s+want\s+to\b", lower_p):
                    return False
            if route_name in ("media_previous", "media_next", "media_play_pause"):
                if re.search(r"\b(?:sing|joke|story|poem|riddle)\b", lower_p):
                    return False
            if route_name == "get_network_info" and "settings" in lower_p:
                return False
            if route_name == "capabilities":
                clean_p = lower_p.strip(" .!?,")
                if clean_p in {"no", "nope", "nah", "nevermind", "cancel", "dont", "don't"}:
                    return False
            return True

        # Tier 1: External Aurelio Semantic Router if available
        if self.router:
            try:
                choice = self.router(user_prompt)
                dt_ms = (time.perf_counter() - t0) * 1000
                if choice and choice.name and choice.confidence is not None:
                    if choice.confidence >= self.confidence_threshold and _is_safe_route(choice.name):
                        return (choice.name, float(choice.confidence), round(dt_ms, 2))
            except Exception as e:
                logger.debug(f"[SemanticRouter] External router exception: {e}")

        # Tier 2: SpaceV Native Pure-Python Sparse Cosine Matcher (<0.1ms)
        if self.native_routes:
            q_vec = encode_sparse_text(user_prompt)
            best_name: str | None = None
            best_score = 0.0

            for route_name, u_vec in self.native_routes:
                sim = sum(q_vec.get(k, 0.0) * val for k, val in u_vec.items())
                if sim > best_score:
                    best_score = sim
                    best_name = route_name

            dt_ms = (time.perf_counter() - t0) * 1000
            if best_name and best_score >= self.confidence_threshold and _is_safe_route(best_name):
                return (best_name, round(best_score, 3), round(dt_ms, 2))

        return None

    @staticmethod
    def _extract_youtube_query(user_prompt: str) -> str:
        text = (user_prompt or "").strip()
        clean = re.sub(r"^(?:hey\s+|hi\s+|spacev\s+|can\s+you\s+(?:please\s+)?|please\s+)", "", text, flags=re.I).strip()
        clean = re.sub(r"\b(?:also|too|please)\b$", "", clean, flags=re.I).strip()

        if re.search(r"\b(?:dont|don't|do\s+not|not|never|without)\s+play\b", clean, flags=re.I) or re.search(r"\b(?:just|only)\s+open\b", clean, flags=re.I):
            return "homepage"

        m1 = re.search(r"(?:play|watch)\s+(.+?)\s+on\s+youtube", clean, flags=re.I)
        if m1 and m1.group(1).strip():
            return m1.group(1).strip()

        m2 = re.search(r"open\s+youtube\s+(?:and\s+)?play\s+(.+)", clean, flags=re.I)
        if m2 and m2.group(1).strip():
            target = re.sub(r"\b(?:also|video\s+play)\b", "", m2.group(1), flags=re.I).strip()
            if target:
                return target

        m3 = re.search(r"open\s+youtube\s+(?:and\s+)?(.+?)\s+play", clean, flags=re.I)
        if m3 and m3.group(1).strip():
            return m3.group(1).strip()

        residual = re.sub(r"\b(?:open\s+youtube(?:\s+and)?|on\s+youtube|play|watch|youtube)\b", " ", clean, flags=re.I)
        residual = " ".join(residual.split()).strip()
        if residual and len(residual) > 2:
            return residual
        return "trending"

    @staticmethod
    def _extract_search_query(user_prompt: str) -> str:
        text = (user_prompt or "").strip()
        clean = re.sub(r"^(?:hey\s+|hi\s+|spacev\s+|can\s+you\s+(?:please\s+)?|please\s+)", "", text, flags=re.I).strip()
        clean = re.sub(r"^(?:search\s+google\s+for|google\s+search\s+for|search\s+for|search\s+google|google\s+search|lookup\s+on\s+google|search\s+the\s+web\s+for|search\s+online\s+for|search)\s+", "", clean, flags=re.I).strip()
        clean = re.sub(r"\s+on\s+google$", "", clean, flags=re.I).strip()
        return clean or "Google"

    def dispatch(self, intent_name: str, user_prompt: str = "") -> tuple[str, str, str] | None:
        """
        Executes the mapped SpaceV tool for the recognized semantic intent
        and formats an authentic, Jarvis-style response.
        Returns Tuple[tool_name, tool_result, reply_text] or None.
        """
        from tools.file_tools import list_desktop_files, open_text_editor
        from tools.system_tools import (
            empty_recycle_bin,
            get_current_time,
            get_network_info,
            get_system_stats,
            list_running_apps,
            lock_workstation,
            media_control,
            optimize_system_memory,
        )
        from tools.vision_tools import get_active_window_info, read_clipboard_text, take_screen_snapshot

        if intent_name == "greeting":
            msg = "SpaceV online and operational, Sir. All cybernetic systems green. How may I assist your workflow today?"
            return ("greeting", "SpaceV Systems Online", msg)

        elif intent_name == "gratitude":
            msg = "My absolute pleasure, Sir. Always at your service. Let me know what you'd like to tackle next!"
            return ("gratitude", "SpaceV Acknowledged", msg)

        elif intent_name == "farewell":
            msg = "Standing by in low-power standby mode, Sir. Call upon me whenever you need assistance."
            return ("farewell", "SpaceV Standby", msg)

        elif intent_name == "status_ping":
            msg = "SpaceV systems fully operational, primed, and awaiting your command, Sir."
            return ("status_ping", "SpaceV Primed", msg)

        elif intent_name == "identity":
            id_text = (
                "I am **SpaceV** (*System Protocol Autonomous Cybernetic Engine Version V*), "
                "your intelligent desktop companion and autonomous automation assistant, Sir."
            )
            return ("identity", "SpaceV Identity", id_text)

        elif intent_name == "get_current_time":
            time_str = get_current_time()
            return ("get_current_time", time_str, f"At your service, Sir. {time_str}")

        elif intent_name == "get_system_stats":
            stats_str = get_system_stats()
            return ("get_system_stats", stats_str, f"System diagnostics at your disposal, Sir:\n\n{stats_str}")

        elif intent_name == "optimize_system_memory":
            res = optimize_system_memory()
            return ("optimize_system_memory", res, res)

        elif intent_name == "get_network_info":
            res = get_network_info()
            return ("get_network_info", res, res)

        elif intent_name == "lock_workstation":
            res = lock_workstation()
            return ("lock_workstation", res, "Securing workstation and locking display immediately, Sir.")

        elif intent_name == "empty_recycle_bin":
            res = empty_recycle_bin()
            return ("empty_recycle_bin", res, "Recycle Bin has been completely purged and cleaned, Sir.")

        elif intent_name == "take_screen_snapshot":
            snap = take_screen_snapshot()
            return ("take_screen_snapshot", snap, "Captured full screen snapshot for you, Sir. Saved safely to your Desktop.")

        elif intent_name == "get_active_window_info":
            win_info = get_active_window_info()
            return ("get_active_window_info", win_info, f"Perceiving your active display, Sir:\n\n{win_info}")

        elif intent_name == "read_clipboard_text":
            clip = read_clipboard_text()
            return ("read_clipboard_text", clip, f"Retrieved your clipboard contents, Sir:\n\n{clip}")

        elif intent_name == "media_play_pause":
            res = media_control("play_pause")
            return ("media_control", res, "Toggled media playback for you, Sir.")

        elif intent_name == "media_next":
            res = media_control("next")
            return ("media_control", res, "Skipped to the next track, Sir.")

        elif intent_name == "media_previous":
            res = media_control("previous")
            return ("media_control", res, "Returned to the previous track, Sir.")

        elif intent_name == "media_mute":
            res = media_control("mute")
            return ("media_control", res, "Toggled system audio mute, Sir.")

        elif intent_name == "media_volume_up":
            res = media_control("volume_up")
            return ("media_control", res, "Increased volume level, Sir.")

        elif intent_name == "media_volume_down":
            res = media_control("volume_down")
            return ("media_control", res, "Decreased volume level, Sir.")

        elif intent_name == "list_desktop_files":
            items_str = list_desktop_files()
            return ("list_desktop_files", items_str, f"Inspecting your desktop directory, Sir:\n\n{items_str}")

        elif intent_name == "list_running_apps":
            res = list_running_apps()
            return ("list_running_apps", res, f"Scanning your active desktop workspace, Sir:\n\n{res}")

        elif intent_name == "toggle_ghost_mode":
            from core.ghost_mode import ghost_manager
            msg = ghost_manager.enable()
            return ("toggle_ghost_mode", "enabled", msg)

        elif intent_name == "get_clipboard_history":
            from core.temporal_memory import temporal_memory
            clips = temporal_memory.get_recent_clipboard(limit=3)
            if not clips:
                return ("get_clipboard_history", "Empty", "Your clipboard history is currently clear, Sir.")
            res = "Recent Clipboard History, Sir:\n"
            for c in clips:
                res += f"• [{c['time']}] {c['content'][:120]}\n"
            return ("get_clipboard_history", res, res)

        elif intent_name == "media_play_youtube":
            from tools.web_tools import open_url, play_youtube
            query = self._extract_youtube_query(user_prompt)
            if query in ("homepage", "home", "trending", "") and any(w in user_prompt.lower() for w in ["just open", "dont play", "don't play", "only open"]):
                res = open_url("https://www.youtube.com")
                return ("open_url", res, f"Opening YouTube homepage for you, Sir: {res}")
            res = play_youtube(query)
            return ("play_youtube", res, f"Playing '{query}' on YouTube for you, Sir: {res}")

        elif intent_name == "open_text_editor":
            editor_target = "code" if ("vscode" in user_prompt.lower() or "code" in user_prompt.lower()) else "notepad"
            res = open_text_editor(file_name="script.py", content="", editor=editor_target)
            return ("open_text_editor", res, f"Launching text editor for you, Sir: {res}")

        elif intent_name == "search_google":
            from tools.web_tools import open_url
            query = self._extract_search_query(user_prompt)
            encoded = urllib.parse.quote_plus(query)
            res = open_url(f"https://www.google.com/search?q={encoded}")
            return ("search_google", res, f"Searching Google for '{query}', Sir: {res}")

        elif intent_name == "capabilities":
            id_text = (
                "I am **SpaceV** (*System Protocol Autonomous Cybernetic Engine Version V*), "
                "your intelligent desktop companion and autonomous workstation copilot, Sir.\n\n"
                "Here are my core capabilities:\n"
                "• **Natural Language Desktop Control**: Autonomous application launching, file editing, window perception.\n"
                "• **Web Perception & Autoplay**: Instant YouTube video resolution, Google search, stealth DOM indexer.\n"
                "• **System Telemetry**: CPU, RAM, battery diagnostics, memory optimization, network analysis.\n"
                "• **Ghost Mode & Background Automation**: Dual-plane non-intrusive task execution.\n"
                "• **Multi-Modal Vision & OCR**: Screen inspection, UI control recognition, active window tracking.\n"
                "• **Cloudflare Code Mode**: Token-efficient sandbox Python orchestration."
            )
            return ("capabilities", "SpaceV Capabilities", id_text)

        return None


semantic_router_engine = SemanticRouterEngine()
