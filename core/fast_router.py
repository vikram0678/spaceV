"""
Fast-Path Intent Dispatcher for Zero-Latency Instant Responses (0ms).
Bypasses LLM inference for trivial system commands with authentic SpaceV personality.
"""
import re
import time

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

        # Cognitive Reflex Gatekeeper (Kahneman System 1 vs System 2 Separation)
        # Prevents generative programming, composite workflows, or deep research from false reflex hijacking
        from core.reflex_gatekeeper import ReflexGatekeeper
        if ReflexGatekeeper.should_bypass_fast_router(user_prompt):
            return None

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

            # Check 1: Did the user type a number ("1", "2", "3", "4", "5", etc.)?
            num_match = re.match(r"^(?:option\s+)?#?(\d+)$", clean_text)
            if num_match:
                idx = int(num_match.group(1)) - 1
                if 0 <= idx < len(suspended["options"]):
                    matched_opt = suspended["options"][idx]

            # Check 2: Match by profile name or keyword
            if not matched_opt:
                for label, opt_val in suspended["options"]:
                    clean_label = re.sub(r"[^a-zA-Z0-9\s]", "", label).strip().lower()
                    clean_val = opt_val.lower().strip()
                    tokens = [clean_val, clean_label] + [w for w in clean_label.split() if len(w) > 2]
                    if any(tok in clean_text for tok in tokens) or clean_text in clean_label:
                        matched_opt = (label, opt_val)
                        break

            if matched_opt:
                label, opt_val = matched_opt
                domain = suspended.get("domain", "system")
                prop_key = suspended.get("property_key", "choice")
                suspended_task = suspended.get("suspended_task")

                # Persist to dynamic hierarchical memory
                memory.set_preference(domain, prop_key, opt_val)
                if domain in ("chrome", "browser", "brave", "edge") and prop_key == "profile":
                    memory.set("preferred_chrome_profile", opt_val)
                    memory.set("preferred_browser_profile", opt_val)
                memory.clear_suspended_disambiguation()

                # Dismiss Holographic Visor attention & target overlay
                try:
                    from ui.holographic_visor import HolographicVisor
                    visor = HolographicVisor.get_instance()
                    if visor:
                        visor.clear_targets()
                        visor.clear_attention()
                except Exception:
                    pass

                from core.app_catalog import app_catalog
                def_browser, _ = app_catalog.get_default_browser()
                browser_title = (
                    domain.title()
                    if domain in ("chrome", "brave", "edge")
                    else def_browser.title()
                )

                # Career Application Human Confirmation Handler
                if domain == "career_application":
                    payload = suspended.get("payload", {})
                    job_url = payload.get("job_url", "")
                    resume_file = payload.get("resume_file", "")
                    if opt_val == "submit_confirmed":
                        from tools.career_tools import apply_to_job
                        res = apply_to_job(job_url, resume_path=resume_file, auto_submit=False)
                        return ("apply_to_job", res, f"I prepared the review, but this integration cannot submit the form. The application has not been marked as applied.\n\n{res}")
                    elif opt_val == "inspect_manually":
                        from tools.web_tools import open_url
                        open_url(job_url)
                        return ("open_url", job_url, f"Opening application form in {browser_title} for your manual review, Sir:\n{job_url}")
                    elif opt_val == "cancel":
                        return ("cancel_application", "Cancelled", "Application cancelled, Sir. No data was submitted.")

                # If the chosen option is a direct URL, open it in browser!
                if opt_val.startswith("http://") or opt_val.startswith("https://"):
                    from tools.web_tools import open_url
                    res = open_url(opt_val)
                    return ("open_url", opt_val, f"Right away, Sir. Opening **'{label}'** in your browser:\n{opt_val}")

                # Launch / switch browser to the selected profile
                if domain in ("chrome", "browser", "brave", "edge") and prop_key == "profile":
                    from core.platform_adapter import PlatformAdapter
                    target_b = domain if domain in ("chrome", "brave", "edge") else def_browser
                    PlatformAdapter.launch_app(target_b, profile_dir=opt_val)
                    time.sleep(1.2)

                # Resume suspended task if present
                if suspended_task:
                    st_lower = suspended_task.lower()
                    if any(k in st_lower for k in ["click", "first", "organic"]):
                        from tools.gui_tools import gui_human_search_and_open
                        clean_t = re.sub(r"^(?:search\s+(?:google\s+(?:for\s+)?)?|google\s+)", "", suspended_task, flags=re.IGNORECASE).strip()
                        clean_t = re.sub(r"(?:and\s+)?(?:click|open)\s+(?:the\s+)?(?:first|top)?\s*results?", "", clean_t, flags=re.IGNORECASE).strip()
                        clean_t = re.sub(r"^(?:for\s+)", "", clean_t).strip()
                        res = gui_human_search_and_open(clean_t, click_first_result=True)
                        return ("resolve_disambiguation", opt_val, f"Understood, Sir. Saved **'{label}'** for {browser_title}.\n\nOpening {browser_title} under **'{label}'** and completing your search:\n{res}")
                    elif any(k in st_lower for k in ["play", "youtube", "music", "song", "video"]):
                        from tools.web_tools import play_youtube
                        res = play_youtube(suspended_task)
                        return ("resolve_disambiguation", opt_val, f"Understood, Sir. Saved **'{label}'** for {browser_title}.\n\nOpening media for **'{suspended_task}'**:\n{res}")
                    elif any(k in st_lower for k in ["search", "google", "find", "lookup"]):
                        from tools.gui_tools import gui_search_google_browser
                        res = gui_search_google_browser(suspended_task)
                        return ("resolve_disambiguation", opt_val, f"Understood, Sir. Saved **'{label}'** for {browser_title}.\n\nSearching the web for **'{suspended_task}'**:\n{res}")
                    elif any(k in st_lower for k in ["open", "links", "tabs", "neatly", "one by one"]):
                        from tools.web_tools import open_browser_urls
                        res = open_browser_urls(suspended_task)
                        return ("resolve_disambiguation", opt_val, f"Understood, Sir. Saved **'{label}'** for {browser_title}.\n\nOpening links:\n{res}")
                    else:
                        return ("resolve_disambiguation", opt_val, f"Understood, Sir. Saved **'{label}'** for {domain.capitalize()} in memory.\n\nResuming your suspended request: **'{suspended_task}'**...")

                return ("resolve_disambiguation", opt_val, f"Understood, Sir. Saved preference **'{label}'** for {domain.capitalize()}. I will automatically remember this choice.")

        # Tier 1: Unified Intent Resolution Pipeline (Sub-millisecond Semantic + Grounded Execution)
        # Replaces brittle regex sprawl with semantic capability retrieval, typed parameter binding,
        # negation/constraint enforcement, ambiguity detection, and empirical outcome verification.
        try:
            from core.intent import unified_resolver, outcome_verifier, IntentType

            resolution = unified_resolver.resolve(user_prompt)

            # 1. Ambiguous or incomplete request -> Return clarification question
            if resolution.is_ambiguous or resolution.intent_type == IntentType.CLARIFICATION:
                if resolution.clarification_question:
                    return (
                        "clarification",
                        resolution.ambiguity_reason or "Ambiguous Request",
                        resolution.clarification_question,
                    )

            # 2. Negated action -> Acknowledge user constraint without executing
            if resolution.intent_type == IntentType.NEGATED:
                reply = resolution.clarification_question or f"Understood, Sir. I will NOT execute {resolution.capability_name} as requested."
                return (resolution.intent, "negated", reply)

            # 3. Composite task or deep generative cognitive task -> Defer to LangGraph / Planner
            if resolution.intent_type == IntentType.COMPOSITE_TASK or resolution.requires_planning:
                return None

            # 4. Simple Executable Action -> Dispatch and verify
            if resolution.is_executable and resolution.tool_name:
                t_name = resolution.tool_name
                params = resolution.parameters

                if t_name == "open_application":
                    app_name = params.get("app_name", "")
                    disp_name = params.get("display_name", app_name.title())
                    if params.get("uninstalled"):
                        return (
                            "app_not_found",
                            app_name,
                            f"Sir, I inspected your workstation applications and Start Menu, but **'{app_name}'** is not installed on this PC.",
                        )
                    res_out = open_application(app_name)
                    outcome_verifier.verify(resolution, res_out)
                    return (
                        "open_application",
                        res_out,
                        f"Right away, Sir. Initializing **{disp_name}** from your workstation applications.",
                    )

                elif t_name == "media_control":
                    act = params.get("action", "play_pause")
                    res_out = media_control(act)
                    outcome_verifier.verify(resolution, res_out)
                    action_msgs = {
                        "mute": "Toggled system audio mute, Sir.",
                        "volume_up": "Increased volume level, Sir.",
                        "volume_down": "Decreased volume level, Sir.",
                        "play_pause": "Toggled media playback for you, Sir.",
                        "next": "Skipped to the next track, Sir.",
                        "previous": "Returned to the previous track, Sir.",
                    }
                    reply = action_msgs.get(act, f"Executed media {act}, Sir.")
                    return ("media_control", res_out, reply)

                elif t_name == "set_system_brightness":
                    level = params.get("level", 50)
                    from tools.system_tools import set_system_brightness
                    res_out = set_system_brightness(level)
                    outcome_verifier.verify(resolution, res_out)
                    return ("set_system_brightness", res_out, res_out)

                elif t_name == "set_timer":
                    from tools.system_tools import set_timer
                    mins = params.get("minutes", 5.0)
                    lbl = params.get("label", "Timer")
                    res_out = set_timer(mins, label=lbl)
                    outcome_verifier.verify(resolution, res_out)
                    return ("set_timer", res_out, res_out)

                elif t_name == "get_current_time":
                    res_out = get_current_time()
                    return ("get_current_time", res_out, f"At your service, Sir. {res_out}")

                elif t_name == "get_system_stats":
                    res_out = get_system_stats()
                    return ("get_system_stats", res_out, f"System diagnostics at your disposal, Sir:\n\n{res_out}")

                elif t_name == "optimize_system_memory":
                    res_out = optimize_system_memory()
                    return ("optimize_system_memory", res_out, res_out)

                elif t_name == "get_network_info":
                    res_out = get_network_info()
                    return ("get_network_info", res_out, f"Network diagnostics ready, Sir:\n\n{res_out}")

                elif t_name == "lock_workstation":
                    res_out = lock_workstation()
                    return ("lock_workstation", res_out, "Workstation locked and secured for you, Sir.")

                elif t_name == "empty_recycle_bin":
                    res_out = empty_recycle_bin()
                    return ("empty_recycle_bin", res_out, "Recycle bin successfully purged, Sir.")

                elif t_name == "take_screen_snapshot":
                    res_out = take_screen_snapshot()
                    outcome_verifier.verify(resolution, res_out)
                    return ("take_screen_snapshot", res_out, f"Screen snapshot captured and saved, Sir:\n{res_out}")

                elif t_name == "get_active_window_info":
                    res_out = get_active_window_info()
                    return ("get_active_window_info", res_out, f"Focused application details, Sir:\n\n{res_out}")

                elif t_name == "read_clipboard_text":
                    res_out = read_clipboard_text()
                    return ("read_clipboard_text", res_out, f"Inspecting your clipboard buffer, Sir:\n\n{res_out}")

                elif t_name == "list_running_apps":
                    res_out = list_running_apps()
                    return ("list_running_apps", res_out, f"Scanning your active desktop workspace, Sir:\n\n{res_out}")

                elif t_name == "list_desktop_files":
                    res_out = list_desktop_files()
                    return ("list_desktop_files", res_out, f"Here are the items on your Desktop, Sir:\n\n{res_out}")

                elif t_name == "search_google":
                    from tools.web_tools import search_google
                    q = params.get("query", "Google")
                    res_out = search_google(q)
                    return ("search_google", res_out, f"Right away, Sir. {res_out}")

                elif t_name == "play_youtube":
                    from tools.web_tools import play_youtube
                    q = params.get("query", "music")
                    res_out = play_youtube(q)
                    return ("play_youtube", res_out, f"Right away, Sir. Opening media playback for '{q}'.")

                elif t_name in ("search_and_harvest_jobs", "scrape_jobs") or resolution.capability_name == "career.search_jobs":
                    from tools.career_tools import search_and_harvest_jobs
                    role = params.get("role", "")
                    loc = params.get("location", "")
                    save_desktop = params.get("save_to_desktop", False)
                    res_out = search_and_harvest_jobs(role=role, location=loc, save_to_desktop=save_desktop)
                    if str(res_out).startswith("SPACEV_NEEDS_USER_INPUT:"):
                        question = str(res_out).split("SPACEV_NEEDS_USER_INPUT:", 1)[1].strip()
                        return ("career_clarification", res_out, question)
                    return ("scrape_jobs", res_out, f"Job search results for **'{role}'** in **{loc}**:\n\n{res_out}")

                elif t_name == "gui_human_search_and_open" or resolution.capability_name == "web.gui_search":
                    from tools.gui_tools import gui_human_search_and_open
                    q = params.get("query", "Google")
                    res_out = gui_human_search_and_open(q, click_first_result=True)
                    if "modal blocker:" in str(res_out).lower():
                        modal_question = str(res_out).replace("⚠️ Modal Blocker:", "").strip()
                        return ("modal_disambiguation", modal_question, modal_question)
                    return ("gui_human_search_and_open", res_out, f"Right away, Sir. {res_out}")

                elif t_name == "greeting":
                    return ("greeting", "SpaceV Systems Online", "SpaceV online and operational, Sir. All cybernetic systems green. How may I assist your workflow today?")
                elif t_name == "gratitude":
                    return ("gratitude", "SpaceV Acknowledged", "My absolute pleasure, Sir. Always at your service. Let me know what you'd like to tackle next!")
                elif t_name == "farewell":
                    return ("farewell", "SpaceV Standby", "Standing by in low-power standby mode, Sir. Call upon me whenever you need assistance.")
                elif t_name == "status_ping":
                    return ("status_ping", "SpaceV Primed", "SpaceV systems fully operational, primed, and awaiting your command, Sir.")
                elif t_name == "identity":
                    from core.intent.capability_registry import capability_registry
                    id_cap = capability_registry.get("general.identity")
                    return ("identity", "SpaceV Identity & Capabilities", id_cap.default_response if id_cap else "SpaceV Autonomous Engine.")

        except Exception as e:
            pass

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

        if re.search(r"^(who are you|what is your name|identify yourself|who made you|who created you|what can you do|what can you done|what are your capabilities|help|commands)$", text):
            id_text = (
                "I am **SpaceV** (*System Protocol Autonomous Cybernetic Engine Version V*), "
                "your intelligent desktop companion and autonomous workstation copilot, Sir.\n\n"
                "Here are my core capabilities:\n"
                "• 🖥️ **Workstation Control**: Launch apps, inspect windows, capture screen snapshots, manage desktop files.\n"
                "• ⚡ **Cybernetic Automation**: Execute bash tasks, manage timers, optimize memory, detonate sandboxed workflows.\n"
                "• 🌐 **Web Intelligence**: Search Google, play YouTube, distill web pages to Markdown with Crawl4AI.\n"
                "• 🎙️ **Full-Duplex Voice**: Hands-free conversation, speech dictation, audio effects.\n"
                "• 🛡️ **Container Isolation**: Run code in Celesto MicroVMs with strict action authority.\n\n"
                "What would you like to tackle first, Sir?"
            )
            return ("identity", "SpaceV Identity & Capabilities", id_text)

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

                # 6.5 System Display Brightness Fast-Path (Deterministic WMI)
        bright_match = re.search(r"(?:brightness|display brightness).*?(\d{1,3})%?|(\d{1,3})%?.*?(?:brightness)", text)
        if bright_match and any(w in text for w in ["set", "decrease", "increase", "change", "to", "dim", "lower"]):
            val_str = bright_match.group(1) or bright_match.group(2)
            if val_str and val_str.isdigit():
                val = int(val_str)
                from tools.system_tools import set_system_brightness
                res = set_system_brightness(val)
                return ("set_system_brightness", res, f"Adjusted primary display brightness to {val}%, Sir.")

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

        # 7.5 Display Brightness Control ("decrease brightness to 50%", "open settings and decrease brightness to 50%", "set brightness 60")
        bright_match = re.search(
            r"^(?:(?:please|can\s+you|could\s+you|hey|spacev)\s+)?(?:open\s+settings\s+(?:and\s+)?|go\s+to\s+settings\s+(?:and\s+)?)?"
            r"(?:decrease|increase|set|change|lower|turn|dim|boost|adjust)?\s*(?:the\s+)?brightness\s*(?:to|at|by|=)?\s*(\d{1,3})?%?$",
            text
        )
        if bright_match:
            from tools.system_tools import set_system_brightness
            raw_val = bright_match.group(1)
            target_level = int(raw_val) if raw_val is not None else (
                30 if any(w in text for w in ["dim", "lower", "decrease"]) else 80
            )
            res = set_system_brightness(target_level)
            return ("set_system_brightness", res, res)

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

        # 13. Dynamic Application Launches Grounded in System App Catalog (Zero Hardcoded App Whitelist)
        app_match = re.match(
            r"^(?:please\s+|can\s+you\s+|hey\s+spacev\s+)?(?:open|launch)\s+([a-zA-Z0-9_\-\.\s]+?)(?:\s+(?:app|application|program))?$",
            text
        )
        if app_match and not any(k in text for k in [" and ", "youtube", "http", "folder", "search", "write", "brightness", "mode", "terminal"]):
            raw_target = app_match.group(1).strip()
            if raw_target not in ("coding", "focus", "research", "ghost"):
                from core.app_catalog import app_catalog
                matched = app_catalog.find_app(raw_target)
                if matched:
                    res = open_application(matched.name)
                    return ("open_application", res, f"Right away, Sir. Initializing **{matched.display_name}** from your workstation applications.")
                else:
                    return ("app_not_found", raw_target, f"Sir, I inspected your workstation applications and Start Menu, but **'{raw_target}'** is not installed on this PC.")

        # 14. Autonomous Cursor Drawing in MS Paint ("draw a house in paint", "draw a smiling face", "draw a star")
        draw_match = re.match(r"^(?:please\s+)?draw(?:\s+(?:a|an|the|me\s+a|me\s+an))?\s+(.+?)(?:\s+in\s+paint|\s+in\s+mspaint|\s+with\s+cursor|\s+on\s+canvas)?$", text)
        if draw_match:
            raw_shape = draw_match.group(1).strip()
            # Exclude code/programming requests like "draw a table in sql" or "draw a flowchart in python"
            if not any(k in raw_shape for k in ["table", "sql", "chart in excel", "python", "code"]):
                from tools.gui_tools import gui_draw_in_paint
                res = gui_draw_in_paint(raw_shape)
                return ("gui_draw_in_paint", res, res)

        # 14.5 Autonomous Human-like Web Search & Click ("search google for ... and click the first result")
        human_search_match = re.match(
            r"^(?:hey\s+|please\s+)?(?:open\s+(?:browser|web\s+browser|chrome|brave|edge)\s+and\s+)?(?:search\s+(?:google\s+(?:for\s+)?)?|search\s+(?:the\s+web\s+(?:for\s+)?)?|google\s+)(.+?)(?:\s+(?:and\s+)?(?:click|open)\s+(?:the\s+)?(?:first|top)?\s*results?|\s+like\s+(?:a\s+)?human)?$",
            text
        )
        if human_search_match and any(k in text.lower() for k in ["click", "first", "open", "like human", "like a human"]):
            target_q = human_search_match.group(1).strip()
            clean_q = re.sub(r"\b(?:and\s+)?(?:click|open)\s+(?:the\s+)?(?:first|top)?\s*results?\b", "", target_q, flags=re.IGNORECASE).strip()
            clean_q = re.sub(r"^(?:for\s+)", "", clean_q).strip()
            from tools.gui_tools import gui_human_search_and_open
            res = gui_human_search_and_open(clean_q or target_q, click_first_result=True)
            if "modal blocker:" in str(res).lower():
                modal_question = str(res).replace("⚠️ Modal Blocker:", "").strip()
                return ("modal_disambiguation", modal_question, modal_question)
            return ("gui_human_search_and_open", res, f"Right away, Sir. {res}")

        # 14.8 Direct Navigation / Website Launch ("take me to ... website", "takem to the smart india hackathon 2026 website and timeline")
        nav_match = re.match(
            r"^(?:hey\s+|please\s+)?(?:take\s*m[ye]\s+to|takem\s+to|navigate\s+to|go\s+to|bring\s+up)\s+(?:the\s+)?(.+)$",
            text,
            re.IGNORECASE,
        )
        if nav_match:
            from core.query_parser import parse_search_intent
            clean_q, _, _ = parse_search_intent(text)
            target_q = clean_q or nav_match.group(1).strip()
            from tools.gui_tools import gui_human_search_and_open
            res = gui_human_search_and_open(target_q, click_first_result=True)
            if "modal blocker:" in str(res).lower():
                modal_question = str(res).replace("⚠️ Modal Blocker:", "").strip()
                return ("modal_disambiguation", modal_question, modal_question)
            return ("gui_human_search_and_open", res, f"Right away, Sir! Navigating to **'{target_q}'**:\n\n{res}")

        # 15. Quick Web Searches & Job/Internship Scraping ("open browser and search for ai intern", "search google for python")
        search_match = re.match(
            r"^(?:hey\s+|please\s+)?(?:open\s+(?:browser|browswer|chrome|brave|edge|web\s+browser)\s+and\s+)?(?:search\s+(?:for\s+|the\s+web\s+for\s+|google\s+(?:for\s+)?)?|google\s+)(.+)$",
            text
        )
        if search_match:
            from core.query_parser import parse_search_intent, get_curated_learning_sources
            from core.app_catalog import app_catalog
            def_browser, _ = app_catalog.get_default_browser()
            browser_title = def_browser.title()

            clean_q, followup, meta = parse_search_intent(text)
            clean_q = clean_q or search_match.group(1).strip()

            if any(k in clean_q.lower() for k in ["job", "jobs", "intern", "internship", "internships", "vacancies", "openings"]) and not any(k in text.lower() for k in ["click", "first", "like human", "like a human"]):
                from tools.career_tools import search_and_harvest_jobs
                from core.memory import memory
                # Extract location if specified (e.g., 'in Bengaluru', 'in London', 'remote')
                loc_m = re.search(r"\b(?:in|at|near|around)\s+([a-zA-Z\s]+?)(?:\s+and\s+save|\s+and|\s*$)", clean_q, re.IGNORECASE)
                user_target_loc = memory.get_preference("career", "target_location") or memory.get("target_location") or ""
                explicitly_remote = bool(re.search(r"\bremote\b", clean_q, re.IGNORECASE))
                location = loc_m.group(1).strip() if loc_m else ("remote" if explicitly_remote else user_target_loc)

                role_str = re.sub(r"\b(?:in|at|near|around)\s+([a-zA-Z\s]+)", "", clean_q, flags=re.IGNORECASE)
                role_clean = re.sub(r"\b(?:remote|or\s+related|or\s+similar|jobs?|internships?|openings?|vacancies|and\s+save\s+to\s+desktop|save\s+to\s+desktop)\b", "", role_str, flags=re.IGNORECASE).strip()
                user_target_role = memory.get_preference("career", "target_role") or memory.get("target_role") or ""
                target_role = role_clean or user_target_role

                res = search_and_harvest_jobs(role=target_role, location=location, save_to_desktop=False)
                if str(res).startswith("SPACEV_NEEDS_USER_INPUT:"):
                    question = str(res).split("SPACEV_NEEDS_USER_INPUT:", 1)[1].strip()
                    return ("career_clarification", res, question)
                return ("scrape_jobs", res, f"Job search results for **'{target_role}'** in **{location}**:\n\n{res}")

            # Check if this is an interactive source evaluation / comparison request
            sources = get_curated_learning_sources(clean_q)
            if meta.get("has_comparison") and sources:
                from tools.web_tools import search_google
                search_res = search_google(clean_q)
                if "modal blocker:" in str(search_res).lower():
                    modal_question = str(search_res).replace("⚠️ Modal Blocker:", "").strip()
                    return ("modal_disambiguation", modal_question, modal_question)

                options = []
                lines = [
                    f"Sir, I have searched the web in {browser_title} for **'{clean_q}'**.\n",
                    "Here is my analysis of the top learning links and sources to help you choose the best fit:\n"
                ]
                for idx, (title, org, link, desc) in enumerate(sources, 1):
                    badge = "🏆" if idx == 1 else ("🧠" if idx == 2 else ("⚡" if idx == 3 else "🚀"))
                    lines.append(f"{idx}. {badge} **{title}** ({org})\n   • **Analysis**: {desc}\n   • **Link**: `{link}`\n")
                    options.append((f"{idx}. {title}", link))

                lines.append(f"Which link and source would you prefer me to open for you, Sir? (Reply with **1** to **{len(sources)}** or the name)")
                reply_text = "\n".join(lines)

                from core.memory import memory
                memory.set_suspended_disambiguation({
                    "domain": "web",
                    "property_key": "selected_source",
                    "question": reply_text,
                    "options": options,
                    "suspended_task": None,
                    "timestamp": time.time()
                })
                return ("search_and_recommend_sources", clean_q, reply_text)

            else:
                from tools.web_tools import search_google
                res = search_google(clean_q)
                if "modal blocker:" in str(res).lower():
                    modal_question = str(res).replace("⚠️ Modal Blocker:", "").strip()
                    return ("modal_disambiguation", modal_question, modal_question)
                return ("search_google", res, f"Right away, Sir. {res}")

        # 16. YouTube Video & Media Playback ("open browser play...", "play ... on youtube", "play some lofi music")
        yt_query = None
        m_yt1 = re.match(
            r"^(?:(?:hey|hi|hello|please)\s+)?(?:open\s+(?:chrome|brave|edge|browser|web\s+browser)\s+)?(?:open\s+)?youtube\s+(?:and\s+)?(?:play\s+|search\s+(?:for\s+)?)?(.+?)(?:\s+(?:play(?:\s+also)?|video|song))?$",
            text
        )
        if m_yt1:
            raw_q = m_yt1.group(1).strip()
            raw_q = re.sub(r"^(?:play|search\s+for|search)\s+", "", raw_q).strip()
            raw_q = re.sub(r"\s+(?:play(?:\s+also)?|video|song)$", "", raw_q).strip()
            if raw_q:
                yt_query = raw_q
        else:
            m_yt2 = re.match(r"^(?:(?:hey|hi|hello|please)\s+)?(?:play|listen\s+to|watch)\s+(.+?)(?:\s+(?:on|in)\s+(?:youtube|spotify|browser)|\s+video|\s+song)?$", text)
            if m_yt2:
                candidate = m_yt2.group(1).strip()
                if candidate not in ["music", "song", "audio", "pause", ""]:
                    yt_query = candidate
            else:
                m_yt3 = re.match(r"^(?:(?:hey|hi|hello|please)\s+)?(?:search\s+youtube\s+for|youtube\s+(?:play|search))\s+(.+)$", text)
                if m_yt3:
                    yt_query = m_yt3.group(1).strip()

        if yt_query:
            from tools.web_tools import play_youtube
            res = play_youtube(yt_query)
            if "modal blocker:" in str(res).lower():
                modal_question = str(res).replace("⚠️ Modal Blocker:", "").strip()
                return ("modal_disambiguation", modal_question, modal_question)
            return ("play_youtube", res, f"Right away, Sir. Opening media playback for '{yt_query}'.")

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

        # 19. Dynamic Browser Profile Preferences & Switching
        profile_set_match = re.search(
            r"^(?:use|set|switch(?:\s+to)?|select)\s+(?:(?:browser|chrome|brave|edge)\s+profile\s+(?:to\s+)?|(?:the\s+)?(?:profile\s+)?)?([a-zA-Z0-9_\-\.\s]+?)(?:\s+profile)?$",
            text,
            re.IGNORECASE,
        )
        if profile_set_match and ("profile" in text or any(k in text for k in ["chrome", "brave", "edge", "browser"])):
            from core.memory import memory
            from core.modal_interceptor import get_detected_chrome_profiles
            from core.platform_adapter import PlatformAdapter
            from core.app_catalog import app_catalog

            def_browser, _ = app_catalog.get_default_browser()
            browser_title = def_browser.title()

            raw_target = profile_set_match.group(1).strip()
            profs = get_detected_chrome_profiles()
            chosen_prof = None

            # 1. Match numeric index (1-based)
            if raw_target.isdigit():
                idx = int(raw_target) - 1
                if 0 <= idx < len(profs):
                    chosen_prof = profs[idx]

            # 2. Match profile ID, name, email, or display
            if not chosen_prof and profs:
                rt_lower = raw_target.lower()
                for p in profs:
                    if (
                        rt_lower == p["id"].lower()
                        or rt_lower in p["display"].lower()
                        or rt_lower in p["name"].lower()
                        or (p.get("email") and rt_lower in p["email"].lower())
                    ):
                        chosen_prof = p
                        break

            if chosen_prof:
                prof_val = chosen_prof["id"]
                prof_label = chosen_prof["display"]
            else:
                prof_val = raw_target
                prof_label = raw_target

            memory.set("preferred_browser_profile", prof_val)
            memory.set("preferred_chrome_profile", prof_val)
            memory.set_preference("browser", "profile", prof_val)
            memory.set_preference("chrome", "profile", prof_val)
            PlatformAdapter.launch_app(def_browser, profile_dir=prof_val)

            # Clear Holographic Visor targeting reticles and attention banner
            try:
                from ui.holographic_visor import HolographicVisor
                visor = HolographicVisor.get_instance()
                if visor:
                    visor.clear_targets()
                    visor.clear_attention()
            except Exception:
                pass

            pending_task = memory.get("pending_resume_task")
            if pending_task:
                memory.set("pending_resume_task", None)
                if any(k in pending_task.lower() for k in ["song", "play", "music", "video"]):
                    from tools.web_tools import play_youtube
                    res = play_youtube(pending_task)
                else:
                    from tools.web_tools import search_google
                    res = search_google(pending_task)
                return ("set_chrome_profile", prof_val, f"Understood, Sir. Preferred {browser_title} profile updated to **'{prof_label}'** in memory.\n\nResuming your request for **'{pending_task}'** now:\n{res}")

            return ("set_chrome_profile", prof_val, f"Right away, Sir. Preferred {browser_title} profile updated to **'{prof_label}'** in persistent memory. I will automatically use it for browser automation.")

        if re.search(r"^(?:which|what)\s+chrome\s+profile(?:\s+am\s+i\s+using|\s+is\s+set|\s+is\s+active|\s+is\s+default)?$", text):
            from core.memory import memory
            from core.modal_interceptor import get_detected_chrome_profiles
            from core.app_catalog import app_catalog

            def_browser, _ = app_catalog.get_default_browser()
            browser_title = def_browser.title()

            current = memory.get("preferred_browser_profile") or memory.get("preferred_chrome_profile") or memory.get_preference("chrome", "profile")
            profs = get_detected_chrome_profiles()
            label = current
            if profs and current:
                for p in profs:
                    if p["id"] == current or p["display"] == current:
                        label = p["display"]
                        break
            if not label:
                label = profs[0]["display"] if profs else "Default"
            return ("get_chrome_profile", current or "Default", f"Your current preferred {browser_title} automation profile is set to **'{label}'**, Sir.")

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

        # Not matched -> Send to Ollama Brain / LangGraph
        return None

    @staticmethod
    def match_semantic(user_prompt: str) -> tuple[str, float, float] | None:
        """Direct access to Aurelio semantic-router intent matching."""
        try:
            from core.semantic_router_engine import semantic_router_engine
            return semantic_router_engine.route(user_prompt)
        except Exception:
            return None



