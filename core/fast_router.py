"""
Fast-Path Intent Dispatcher for Zero-Latency Instant Responses (0ms).
Bypasses LLM inference for trivial system commands with authentic SpaceV personality.
"""
import re

from tools.file_tools import list_desktop_files
from tools.system_tools import (
    activate_workspace_mode,
    empty_recycle_bin,
    get_current_time,
    get_network_info,
    get_system_stats,
    list_running_apps,
    lock_workstation,
    media_control,
    open_application,
    optimize_system_memory,
)
from tools.vision_tools import get_active_window_info, read_clipboard_text, take_screen_snapshot


class FastRouter:
    @staticmethod
    def match(user_prompt: str) -> tuple[str, str, str] | None:
        """
        Attempts to match common trivial intents.
        Returns Tuple[tool_name, tool_result, reply_text] or None if LLM is required.
        """
        text = user_prompt.strip().lower()

        # 0. Instant Greetings, What's Up & Casual Chit-Chat (0ms)
        greeting_pattern = (
            r"^(?:hello|hi|hey|yo|sup|howdy|good\s+(?:morning|afternoon|evening|night))"
            r"(?:\s+(?:spacev|space\s+v|buddy|bro|there|friend))?"
            r"(?:(?:,\s*|\s+)(?:what(?:'s|\s+is)\s+up|how(?:'s|\s+is)\s+it\s+going|how\s+are\s+you(?:\s+doing)?|what(?:'s|\s+is)\s+new|what(?:'s|\s+is)\s+happening))?$"
            r"|"
            r"^(?:what(?:'s|\s+is)\s+up|whats\s+up|sup|how\s+are\s+you(?:\s+doing)?|how(?:'s|\s+is)\s+it\s+going|how\s+are\s+things)(?:\s+(?:spacev|space\s+v|buddy|bro|there))?$"
        )
        if re.search(greeting_pattern, text):
            greetings = (
                "SpaceV online and operational, Sir. All cybernetic systems green. "
                "How may I assist your workflow today?"
            )
            return ("greeting", "SpaceV Systems Online", greetings)

        # 0.0 Universal Gatekeeper Disambiguation Continuation (0ms)
        from core.memory import memory
        suspended = memory.get_suspended_disambiguation()
        if suspended and suspended.get("options"):
            matched_opt = None
            clean_text = text.lower().strip()
            for label, opt_val in suspended["options"]:
                clean_label = re.sub(r"[^a-zA-Z0-9\s]", "", label).strip().lower()
                clean_val = opt_val.lower().strip()
                if clean_text in [clean_val, clean_label] or clean_val in clean_text or clean_label in clean_text:
                    matched_opt = (label, opt_val)
                    break

            if matched_opt:
                label, opt_val = matched_opt
                domain = suspended.get("domain", "system")
                prop_key = suspended.get("property_key", "choice")
                suspended_task = suspended.get("suspended_task")

                # Persist to dynamic hierarchical memory
                memory.set_preference(domain, prop_key, opt_val)
                memory.clear_suspended_disambiguation()

                # Resume suspended task if present
                if suspended_task:
                    if domain == "chrome" and prop_key == "profile":
                        from tools.web_tools import play_youtube
                        res = play_youtube(suspended_task)
                        return ("resolve_disambiguation", opt_val, f"Understood, Sir. Saved **'{label}'** for {domain.capitalize()} in memory.\n\nResuming your request for **'{suspended_task}'** now:\n{res}")
                    else:
                        return ("resolve_disambiguation", opt_val, f"Understood, Sir. Saved **'{label}'** for {domain.capitalize()} in memory.\n\nResuming your suspended request: **'{suspended_task}'**...")

                return ("resolve_disambiguation", opt_val, f"Understood, Sir. Saved preference **'{label}'** for {domain.capitalize()}. I will automatically remember this choice.")

        # 0.1 Gratitude & Politeness (0ms)
        if re.search(r"^(?:thank\s+you|thanks(?:\s+a\s+lot)?|appreciate\s+it|good\s+job|great\s+job|nice\s+work|awesome|well\s+done)(?:\s+(?:spacev|space\s+v|buddy|bro))?$", text):
            gratitude_reply = "My absolute pleasure, Sir. Always at your service. Let me know what you'd like to tackle next!"
            return ("gratitude", "SpaceV Acknowledged", gratitude_reply)

        # 0.2 Farewells & Standby (0ms)
        if re.search(r"^(?:bye|goodbye|see\s+you|see\s+ya|take\s+care|talk\s+to\s+you\s+later|have\s+a\s+good\s+day)$", text):
            farewell_reply = "Standing by in low-power standby mode, Sir. Call upon me whenever you need assistance."
            return ("farewell", "SpaceV Standby", farewell_reply)

        # 0.3 Readiness & Presence Check (0ms)
        if re.search(r"^(?:are\s+you\s+there|are\s+you\s+ready|you\s+alive|status\s+check|ping|ready\?*)$", text):
            status_reply = "SpaceV systems fully operational, primed, and awaiting your command, Sir."
            return ("status_ping", "SpaceV Primed", status_reply)

        if re.search(r"^(who are you|what is your name|identify yourself|who made you|who created you)$", text):
            id_text = (
                "I am **SpaceV** (*System Protocol Autonomous Cybernetic Engine Version V*), "
                "your intelligent desktop companion and autonomous automation assistant, Sir."
            )
            return ("identity", "SpaceV Identity", id_text)

        # 0.5 Countdown Timers ("set a timer for 5 minutes", "timer 10 minutes")
        timer_match = re.match(r"^(?:set\s+a\s+)?timer\s+(?:for\s+)?(\d+(?:\.\d+)?)\s*(?:m|min|mins|minute|minutes)(?:\s+(?:for|to|named)\s+(.+))?$", text)
        if timer_match:
            mins = float(timer_match.group(1))
            label = timer_match.group(2) or "Timer"
            from tools.system_tools import set_timer
            res = set_timer(mins, label=label.strip())
            return ("set_timer", res, res)

        # 1. Time & Date queries
        if re.search(r"^(what time is it|what is the time|current time|tell me the time|time now|what date is it|what is the date)$", text):
            time_str = get_current_time()
            return ("get_current_time", time_str, f"At your service, Sir. {time_str}")

        # 2. System status / Battery / CPU
        if re.search(r"^(system stats|system status|cpu usage|battery status|pc status|check cpu|diagnostics)$", text):
            stats_str = get_system_stats()
            return ("get_system_stats", stats_str, f"System diagnostics at your disposal, Sir:\n\n{stats_str}")

        # 3. Simple Desktop Files & Folder Inspection
        if re.search(r"^(?:list\s+desktop(?:\s+files|\s+items)?|show\s+desktop(?:\s+files|\s+items)?|what(?:'s|\s+is|\s+do\s+i\s+have|\s+files\s+are)\s+on\s+(?:the|my)?\s*desktop(?:\s+files|\s+folder|\s+items)?(?:\s+right\s+now)?)$", text):
            items_str = list_desktop_files()
            return ("list_desktop_files", items_str, f"Inspecting your desktop directory, Sir:\n\n{items_str}")

        # 4. Clipboard Reading
        if re.search(r"^(read clipboard|check clipboard|what is on my clipboard|clipboard content|show clipboard)$", text):
            clip = read_clipboard_text()
            return ("read_clipboard_text", clip, f"Retrieved your clipboard contents, Sir:\n\n{clip}")

        # 5. Active Window Inspection
        if re.search(r"^(what window is active|what am i looking at|active window|current window)$", text):
            win_info = get_active_window_info()
            return ("get_active_window_info", win_info, f"Perceiving your active display, Sir:\n\n{win_info}")

        # 6. Take Screenshot
        if re.search(r"^(take screenshot|screenshot|take a screenshot|capture screen)$", text):
            snap = take_screen_snapshot()
            return ("take_screen_snapshot", snap, "Captured full screen snapshot for you, Sir. Saved safely to your Desktop.")

        # 7. Media & Volume Controls (Instant Physical Keys)
        if re.search(r"^(pause|pause music|resume|resume music|play music|play pause|toggle music)$", text):
            res = media_control("play_pause")
            return ("media_control", res, "Toggled media playback for you, Sir.")

        if re.search(r"^(next song|next track|skip song|skip track)$", text):
            res = media_control("next")
            return ("media_control", res, "Skipped to the next track, Sir.")

        if re.search(r"^(prev song|previous song|previous track|back song)$", text):
            res = media_control("previous")
            return ("media_control", res, "Returned to the previous track, Sir.")

        if re.search(r"^(mute|unmute|mute audio|mute sound|mute volume)$", text):
            res = media_control("mute")
            return ("media_control", res, "Toggled system audio mute, Sir.")

        if re.search(r"^(volume up|vol up|increase volume|louder|turn up sound|turn up volume)$", text):
            res = media_control("volume_up")
            return ("media_control", res, "Increased volume level, Sir.")

        if re.search(r"^(volume down|vol down|decrease volume|quieter|lower volume|turn down volume)$", text):
            res = media_control("volume_down")
            return ("media_control", res, "Decreased volume level, Sir.")

        # 8. Lock Workstation
        if re.search(r"^(lock screen|lock pc|lock workstation|lock computer|lock windows)$", text):
            res = lock_workstation()
            return ("lock_workstation", res, "Securing workstation and locking display immediately, Sir.")

        # 9. Empty Recycle Bin
        if re.search(r"^(empty recycle bin|clean recycle bin|clear recycle bin|empty trash|clear trash)$", text):
            res = empty_recycle_bin()
            return ("empty_recycle_bin", res, "Recycle Bin has been completely purged and cleaned, Sir.")

        # 10. Network Diagnostics
        if re.search(r"^(network info|network status|check wifi|wifi status|my ip|ip address|internet status|ping)$", text):
            res = get_network_info()
            return ("get_network_info", res, res)

        # 11. Memory Optimization
        if re.search(r"^(optimize memory|clean ram|free ram|flush ram|free memory|optimize ram)$", text):
            res = optimize_system_memory()
            return ("optimize_system_memory", res, res)

        # 12. Workspace Modes ("activate coding mode", "focus mode")
        mode_match = re.match(r"^(activate\s+)?(coding|research|focus)\s+mode$", text)
        if mode_match:
            mode_name = mode_match.group(2)
            res = activate_workspace_mode(mode_name)
            return ("activate_workspace_mode", res, res)

        # 13. Quick App Launches ("open calc", "open notepad", "open chrome")
        app_match = re.match(r"^(open|launch)\s+(calculator|calc|notepad|chrome|paint|task manager|taskmgr|vs code|vscode|settings)$", text)
        if app_match:
            app_name = app_match.group(2)
            res = open_application(app_name)
            return ("open_application", res, f"Right away, Sir. Initializing {app_name} for you now.")

        # 14. Autonomous Cursor Drawing in MS Paint ("draw a house in paint", "draw a smiling face", "draw a star")
        draw_match = re.match(r"^(?:please\s+)?draw(?:\s+(?:a|an|the|me\s+a|me\s+an))?\s+(.+?)(?:\s+in\s+paint|\s+in\s+mspaint|\s+with\s+cursor|\s+on\s+canvas)?$", text)
        if draw_match:
            raw_shape = draw_match.group(1).strip()
            # Exclude code/programming requests like "draw a table in sql" or "draw a flowchart in python"
            if not any(k in raw_shape for k in ["table", "sql", "chart in excel", "python", "code"]):
                from tools.gui_tools import gui_draw_in_paint
                res = gui_draw_in_paint(raw_shape)
                return ("gui_draw_in_paint", res, res)

        # 15. Quick Web Searches & Job/Internship Scraping ("open browser and search for ai intern", "search google for python")
        search_match = re.match(
            r"^(?:hey\s+|please\s+)?(?:open\s+(?:browser|browswer|chrome|web\s+browser)\s+and\s+)?(?:search\s+(?:for\s+|google\s+(?:for\s+)?)?|google\s+)(.+?)(?:\s+and\s+(?:make\s+(?:a\s+|the\s+)?list.*|list\s+them.*|show\s+them.*))?$",
            text
        )
        if search_match:
            query = search_match.group(1).strip()
            if any(k in query.lower() for k in ["job", "jobs", "intern", "internship", "internships", "vacancies", "openings"]):
                from tools.scraper_tools import scrape_jobs
                from tools.web_tools import search_google
                search_google(f"{query} internships")
                scrape_role = re.sub(r"\b(?:or\s+related|or\s+similar|jobs?|internships?)\b", "", query, flags=re.IGNORECASE).strip()
                res = scrape_jobs(role=scrape_role or query, location="remote", save_to_desktop=True)
                return ("scrape_jobs", res, f"Opened your browser and retrieved active tech opportunities for '{query}', Sir:\n\n{res}")
            else:
                from tools.web_tools import search_google
                res = search_google(query)
                return ("search_google", res, f"Right away, Sir. {res}")

        # 16. YouTube Video & Music Playback ("open chrome open youtube play...", "play ... on youtube", "search youtube for...")
        yt_query = None
        m_yt1 = re.match(r"^(?:please\s+)?(?:open\s+(?:chrome|browser|web\s+browser)\s+)?open\s+youtube\s+(?:and\s+)?(?:play\s+|search\s+for\s+)?(.+)$", text)
        if m_yt1:
            yt_query = m_yt1.group(1).strip()
        else:
            m_yt2 = re.match(r"^(?:please\s+)?play\s+(.+?)(?:\s+(?:on|in)\s+youtube|\s+video|\s+song)?$", text)
            if m_yt2:
                candidate = m_yt2.group(1).strip()
                if candidate not in ["music", "song", "audio", "pause", ""]:
                    yt_query = candidate
            else:
                m_yt3 = re.match(r"^(?:please\s+)?(?:search\s+youtube\s+for|youtube\s+(?:play|search))\s+(.+)$", text)
                if m_yt3:
                    yt_query = m_yt3.group(1).strip()

        if yt_query:
            from tools.web_tools import play_youtube
            res = play_youtube(yt_query)
            return ("play_youtube", res, f"Right away, Sir. Opening YouTube to play '{yt_query}'.")

        # 17. Desktop Dictation Mode ("dictation mode", "start dictation", "dictate text")
        if re.search(r"^(?:activate\s+|start\s+|toggle\s+)?dictat(?:e|ion)(?:\s+mode)?$", text):
            msg = "🎙️ **Desktop Dictation Activated**. Speak clearly—your words will be typed directly into your focused application."
            return ("dictation_mode", "Dictation Activated", msg)

        # 18. Active Desktop Processes & Running Apps
        if re.search(
            r"^(?:(?:what(?:'s|\s+is|\s+are)?|which|list|show|check|tell\s+me)\s+(?:all\s+)?(?:the\s+)?"
            r"(?:(?:currently\s+)?(?:running|open|active)\s+(?:apps?|applications?|programs?|processes?|windows?)?"
            r"|(?:apps?|applications?|programs?|processes?|windows?)\s+(?:that\s+are\s+)?(?:is|are)?\s*(?:currently\s+)?(?:running|open|opened|active).*"
            r"|(?:is|are)\s+(?:currently\s+)?(?:running|open|active)(?:\s+(?:on|in)\s+(?:the|my)?\s*(?:desktop|laptop|pc|system|computer))?.*)"
            r"|^what\s+is\s+going\s+(?:on\s+in|in)\s+(?:the|my)?\s*(?:desktop|laptop|pc|system).*"
            r"|^(?:running|open|active)\s+(?:apps|processes|applications|programs|windows)$)",
            text
        ):
            res = list_running_apps()
            return ("list_running_apps", res, f"Scanning your active desktop workspace, Sir:\n\n{res}")

        # 19. Chrome Profile Preferences ("use chrome profile vicky", "set chrome profile to vikram", "use vikram", "switch to vicky")
        profile_set_match = re.search(r"^(?:use|set|switch\s+to|select)?\s*(?:chrome\s+profile\s+(?:to\s+)?|(?:the\s+)?(?:profile\s+)?)?(vikram|vicky|vicky\s+space|n\.\s*vikram)(?:\s+profile)?$", text)
        if profile_set_match:
            from core.memory import memory
            raw_prof = profile_set_match.group(1).strip()
            prof_val = "vicky" if "vicky" in raw_prof else "vikram"
            prof_label = "Vicky Space" if prof_val == "vicky" else "n. vikram"
            memory.set("preferred_chrome_profile", prof_val)

            pending_task = memory.get("pending_resume_task")
            if pending_task:
                memory.set("pending_resume_task", None)
                from tools.web_tools import play_youtube
                res = play_youtube(pending_task)
                return ("set_chrome_profile", prof_val, f"Understood, Sir. Preferred Chrome profile updated to **'{prof_label}'** in memory.\n\nResuming your request for **'{pending_task}'** now:\n{res}")

            return ("set_chrome_profile", prof_val, f"Right away, Sir. Preferred Chrome profile updated to **'{prof_label}'** in persistent memory. I will automatically use it for browser automation.")

        if re.search(r"^(?:which|what)\s+chrome\s+profile(?:\s+am\s+i\s+using|\s+is\s+set|\s+is\s+active|\s+is\s+default)?$", text):
            from core.memory import memory
            current = memory.get("preferred_chrome_profile", "vikram")
            label = "Vicky Space" if current == "vicky" else "n. vikram"
            return ("get_chrome_profile", current, f"Your current preferred Chrome automation profile is set to **'{label}'**, Sir.")

        # 20. Ghost Mode Background Automation ("activate ghost mode", "turn off ghost mode", "ghost mode status")
        if re.search(r"^(?:activate|enable|turn\s+on|start)\s+ghost\s+mode$", text):
            from core.ghost_mode import ghost_manager
            msg = ghost_manager.enable()
            return ("toggle_ghost_mode", "enabled", msg)

        if re.search(r"^(?:deactivate|disable|turn\s+off|stop)\s+ghost\s+mode$", text):
            from core.ghost_mode import ghost_manager
            msg = ghost_manager.disable()
            return ("toggle_ghost_mode", "disabled", msg)

        if re.search(r"^(?:what\s+is\s+)?ghost\s+mode\s+status|is\s+ghost\s+mode\s+(?:on|active)$", text):
            from core.ghost_mode import ghost_manager
            status = ghost_manager.get_status()
            return ("get_ghost_mode_status", status, status)

        # 21. Temporal Timeline & Clipboard History ("clipboard history", "what did i copy earlier")
        if re.search(r"^(?:show|get|what\s+did\s+i\s+copy|recent)?\s*(?:clipboard\s+history|copied\s+items|clipboard\s+items)$", text):
            from core.temporal_memory import temporal_memory
            clips = temporal_memory.get_recent_clipboard(limit=3)
            if not clips:
                return ("get_clipboard_history", "Empty", "Your clipboard history is currently clear, Sir.")
            res = "Recent Clipboard History, Sir:\n"
            for c in clips:
                res += f"• [{c['time']}] {c['content'][:120]}\n"
            return ("get_clipboard_history", res, res)

        # 21.5. SpaceV Deterministic Reflex Engine (Needle-Personalized <0.2ms Tool Router)
        try:
            from spacev.core.reflex import reflex_engine
            reflex_res = reflex_engine.match_and_execute(user_prompt)
            if reflex_res:
                return reflex_res
        except Exception:
            pass

        # 22. Aurelio Semantic-Router Fuzzy Natural Language Fast-Path (<4ms)
        # Bypasses LLM for natural phrasing of system, media, clipboard, and desktop intents
        try:
            from core.semantic_router_engine import semantic_router_engine
            semantic_match = semantic_router_engine.route(user_prompt)
            if semantic_match:
                intent_name, confidence, latency_ms = semantic_match
                dispatched = semantic_router_engine.dispatch(intent_name)
                if dispatched:
                    return dispatched
        except Exception:
            pass

        # Not matched -> Send to Ollama Brain
        return None

    @staticmethod
    def match_semantic(user_prompt: str) -> tuple[str, float, float] | None:
        """Direct access to Aurelio semantic-router intent matching."""
        try:
            from core.semantic_router_engine import semantic_router_engine
            return semantic_router_engine.route(user_prompt)
        except Exception:
            return None



