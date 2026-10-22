"""
Proactive Companion Engine for SpaceV.
Provides Gemini/Jarvis-style continuous conversational interactivity,
context-aware Next Best Action (NBA) suggestions, dynamic follow-up chips,
and proactive idle check-ins during working sessions.
"""
import time
import datetime
import random
from typing import List, Tuple, Optional, Dict, Any
from PyQt6.QtCore import QThread, pyqtSignal

from config import COMPANION_CHECKIN_INTERVAL_SEC, COMPANION_MODE_DEFAULT

# Context-Aware Next Best Action (NBA) mappings based on executed tools
TOOL_FOLLOWUP_MAP: Dict[str, List[Tuple[str, str]]] = {
    "activate_workspace_mode": [
        ("🎵 Focus Beats", "play lofi chill beats on youtube in chrome"),
        ("📄 New Script", "create a file named main.py with python boilerplate on Desktop"),
        ("⏱️ 25m Pomodoro", "set a timer for 25 minutes for Deep Focus"),
        ("🧹 Clean RAM", "clean ram"),
    ],
    "create_file": [
        ("📄 Read Content", "read file content"),
        ("📂 Open Desktop", "open folder Desktop"),
        ("⏱️ Set Work Timer", "set a timer for 30 minutes"),
    ],
    "create_folder": [
        ("📄 Create File", "create a notes.txt file on Desktop"),
        ("📂 Open Folder", "open folder Desktop"),
        ("💻 Coding Mode", "activate coding mode"),
    ],
    "gui_draw_in_paint": [
        ("🌟 Draw Star", "draw a star in paint"),
        ("🌳 Draw Tree", "draw a tree in paint"),
        ("☀️ Draw Sun", "draw a sun in paint"),
        ("🚀 Draw Rocket", "draw a rocket in paint"),
    ],
    "scrape_jobs": [
        ("📂 Open Desktop CSV", "open folder Desktop"),
        ("🔍 React Jobs", "scrape react remote jobs and save to desktop"),
        ("📰 Tech News", "fetch top technology news headlines"),
    ],
    "set_timer": [
        ("📋 Active Timers", "list active timers"),
        ("🔇 Mute Audio", "mute"),
        ("💻 Focus Mode", "activate focus mode"),
    ],
    "get_weather": [
        ("📰 Tech News", "fetch top technology news headlines"),
        ("🎵 Morning Music", "play acoustic morning songs on youtube"),
        ("⚡ Diagnostics", "system stats"),
    ],
    "optimize_system_memory": [
        ("⚡ System Stats", "system stats"),
        ("📊 Running Apps", "list running apps"),
        ("🔒 Lock Screen", "lock screen"),
    ],
    "get_system_stats": [
        ("🧹 Clean RAM", "clean ram"),
        ("📊 Running Apps", "list running apps"),
        ("🌐 Check Network", "check wifi"),
    ],
    "search_google": [
        ("📋 Copy Summary", "copy findings to clipboard"),
        ("📄 Save Notes", "create a file named research_notes.txt on Desktop"),
        ("🎥 YouTube Search", "play related video on youtube"),
    ],
    "get_wikipedia_summary": [
        ("📄 Save Notes", "create a file named wikipedia_notes.txt on Desktop"),
        ("🔍 Google Deeper", "search google for latest developments"),
    ],
    "media_control": [
        ("🎵 Next Song", "next song"),
        ("🔊 Vol Up", "volume up"),
        ("🔇 Mute", "mute"),
    ]
}

# Contextual Proactive Check-In Prompts
CHECK_IN_TEMPLATES = [
    (
        "Checking in with you, Sir. All background processes are running smoothly. "
        "Would you like me to optimize memory, queue up some focus music, or set a workflow timer?",
        [("🧹 Clean RAM", "clean ram"), ("🎵 Focus Music", "play lofi beats on youtube"), ("⏱️ 25m Timer", "set a timer for 25 minutes for Focus")]
    ),
    (
        "SpaceV standing by, Commander. Your system metrics are stable. "
        "Shall I fetch the latest tech headlines, check the weather, or assist with your current code?",
        [("📰 Tech News", "fetch top technology news headlines"), ("🌤️ Weather", "what is the weather?"), ("⚡ Diagnostics", "system stats")]
    ),
    (
        "How is your progress holding up, Sir? "
        "Remember to stay hydrated. Let me know if you need any files inspected, apps opened, or research pulled up.",
        [("⏱️ Hydrate Timer", "set a timer for 45 minutes for Drink Water"), ("💻 Coding Mode", "activate coding mode"), ("📂 Open Desktop", "open folder Desktop")]
    ),
    (
        "System diagnostics are green, Sir. Would you like me to scan your desktop directory, clear temporary cache, or draft a quick note for you?",
        [("🧹 Clean RAM", "clean ram"), ("📄 Create Note", "create a notes.txt file on Desktop"), ("⚡ Check WiFi", "check wifi")]
    ),
]


class ProactiveCompanion(QThread):
    """
    Background Companion Engine managing user idle monitoring,
    dynamic Follow-Up Action generation, and proactive session check-ins.
    """
    check_in_triggered = pyqtSignal(str, list)  # (message_text, follow_up_chips_list)

    def __init__(self, checkin_interval_sec: int = COMPANION_CHECKIN_INTERVAL_SEC):
        super().__init__()
        self.checkin_interval = checkin_interval_sec
        self.is_enabled = COMPANION_MODE_DEFAULT
        self.last_activity = time.time()
        self._running = True

    def record_activity(self):
        """Resets idle timer whenever the user or agent interacts."""
        self.last_activity = time.time()

    def set_enabled(self, enabled: bool):
        self.is_enabled = enabled
        if enabled:
            self.record_activity()

    def run(self):
        while self._running:
            time.sleep(10)
            if not self.is_enabled:
                continue

            from voice.tts_engine import tts
            if tts.is_speaking:
                self.record_activity()
                continue

            idle_duration = time.time() - self.last_activity
            if idle_duration >= self.checkin_interval:
                # Trigger a gentle proactive companion check-in
                prompt, chips = random.choice(CHECK_IN_TEMPLATES)
                self.check_in_triggered.emit(prompt, chips)
                self.record_activity()

    def stop(self):
        self._running = False

    @staticmethod
    def get_follow_up_chips(tool_name: str = "", reply_text: str = "") -> List[Tuple[str, str]]:
        """
        Dynamically derives 2-4 interactive follow-up action chips for any response.
        """
        # 1. Check if an active gatekeeper disambiguation is suspended in memory
        from core.memory import memory
        suspended = memory.get_suspended_disambiguation()
        if suspended and suspended.get("options"):
            return suspended["options"]

        if tool_name and tool_name in TOOL_FOLLOWUP_MAP:
            return TOOL_FOLLOWUP_MAP[tool_name]

        # Scan reply text for keywords
        text = reply_text.lower()
        if "who's using chrome" in text or "which profile" in text or "chrome profile" in text:
            return [
                ("👤 n. vikram", "use chrome profile vikram"),
                ("👤 Vicky Space", "use chrome profile vicky"),
            ]
        if "paint" in text or "draw" in text or "sketch" in text:
            return TOOL_FOLLOWUP_MAP["gui_draw_in_paint"]
        elif "job" in text or "career" in text or "resume" in text:
            return TOOL_FOLLOWUP_MAP["scrape_jobs"]
        elif "weather" in text or "temperature" in text:
            return TOOL_FOLLOWUP_MAP["get_weather"]
        elif "timer" in text or "countdown" in text:
            return TOOL_FOLLOWUP_MAP["set_timer"]
        elif "memory" in text or "ram" in text:
            return TOOL_FOLLOWUP_MAP["optimize_system_memory"]
        elif "music" in text or "song" in text or "youtube" in text:
            return TOOL_FOLLOWUP_MAP["media_control"]
        elif "code" in text or "python" in text or "workspace" in text:
            return TOOL_FOLLOWUP_MAP["activate_workspace_mode"]

        # Default intelligent companion actions
        return [
            ("⚡ Diagnostics", "system stats"),
            ("🧹 Clean RAM", "clean ram"),
            ("💻 Coding Mode", "activate coding mode"),
            ("⏱️ 15m Timer", "set a timer for 15 minutes"),
        ]

    @staticmethod
    def generate_conversational_wrap(tool_name: str, tool_result: str) -> str:
        """
        Adds authentic SpaceV companion follow-up phrasing to fast-path responses.
        """
        if tool_name == "activate_workspace_mode":
            return f"{tool_result}\n\nAll tools are primed, Sir. Would you like me to generate starter boilerplate code or queue focused ambient study beats?"
        elif tool_name == "set_timer":
            return f"{tool_result}\n\nI will monitor the clock continuously. Shall I activate Focus Mode or mute audio while you work?"
        elif tool_name == "optimize_system_memory":
            return f"{tool_result}\n\nYour workstation is operating at peak responsiveness. What task shall we conquer next, Sir?"
        elif tool_name == "gui_draw_in_paint":
            return f"{tool_result}\n\nYour canvas is ready. Would you like me to add more elements (such as a sun, tree, or star), or save the artwork?"
        elif tool_name == "get_network_info":
            return f"{tool_result}\n\nNetwork telemetry is verified, Sir. Shall I pull up live tech headlines or open any web portals for you?"
        elif tool_name == "lock_workstation":
            return f"{tool_result}\n\nWorkstation secured, Sir. SpaceV will guard the deck."
        elif tool_name == "take_screen_snapshot":
            return f"{tool_result}\n\nSnapshot saved to Desktop. Would you like me to inspect the file or transcribe its contents?"
        return tool_result

companion_engine = ProactiveCompanion()
