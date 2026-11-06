"""
SpaceV Capability Registry.
Structured catalog of all agent capabilities exposing semantic descriptions,
supported outcomes, typed parameter requirements, risk levels, and empirical
verification strategies.
"""

from __future__ import annotations

from typing import Any, Optional

from core.intent.contracts import (
    Capability,
    ParameterRequirement,
    RiskLevel,
    VerificationStrategy,
)


class CapabilityRegistry:
    """
    Central authoritative catalog of SpaceV capabilities.
    Provides structured discovery for semantic retrieval, parameter binding,
    risk governance, and outcome verification.
    """

    def __init__(self):
        self._capabilities: dict[str, Capability] = {}
        self._register_default_capabilities()

    def register(self, capability: Capability) -> None:
        """Registers a capability into the catalog."""
        self._capabilities[capability.name] = capability

    def get(self, name: str) -> Optional[Capability]:
        """Retrieves a capability by unique name."""
        return self._capabilities.get(name)

    def list_all(self) -> list[Capability]:
        """Returns all registered capabilities."""
        return list(self._capabilities.values())

    def _register_default_capabilities(self) -> None:
        """Initializes the standard suite of SpaceV desktop and agent capabilities."""

        # ---------------------------------------------------------------------
        # 1. Operating System Primitives & Diagnostics
        # ---------------------------------------------------------------------
        self.register(Capability(
            name="os.get_time",
            description="Reports the current local time, date, day of the week, and clock status.",
            supported_outcomes=[
                "check the current time",
                "what time is it right now",
                "what is today's date",
                "current clock and calendar status",
                "tell me the time and date",
            ],
            tool_name="get_current_time",
            risk_level=RiskLevel.SAFE,
            verification_strategy=VerificationStrategy.NONE,
            default_response="At your service, Sir. {result}",
        ))

        self.register(Capability(
            name="os.get_system_stats",
            description="Inspects workstation hardware health, CPU load, RAM utilization, battery status, and operating system diagnostics.",
            supported_outcomes=[
                "inspect system performance and hardware stats",
                "check cpu usage and memory consumption",
                "how is my computer performing right now",
                "diagnose workstation resources and battery",
                "what is hogging my system hardware",
            ],
            tool_name="get_system_stats",
            risk_level=RiskLevel.SAFE,
            verification_strategy=VerificationStrategy.NONE,
            default_response="System diagnostics at your disposal, Sir:\n\n{result}",
        ))

        self.register(Capability(
            name="os.optimize_memory",
            description="Flushes workstation RAM cache, clears unneeded standby memory pages, and optimizes system responsiveness.",
            supported_outcomes=[
                "free up workstation memory and clean ram",
                "flush memory cache to boost performance",
                "clear standby ram and optimize resources",
                "my pc is lagging, optimize memory",
            ],
            tool_name="optimize_system_memory",
            risk_level=RiskLevel.LOW,
            verification_strategy=VerificationStrategy.NONE,
            default_response="Memory optimization complete, Sir. {result}",
        ))

        self.register(Capability(
            name="os.get_network_info",
            description="Inspects active network interfaces, IP address configuration, WiFi connection status, and internet reachability.",
            supported_outcomes=[
                "check internet connection and wifi status",
                "what is my ip address and network configuration",
                "is my internet working properly",
                "diagnose network connectivity",
            ],
            tool_name="get_network_info",
            risk_level=RiskLevel.SAFE,
            verification_strategy=VerificationStrategy.NONE,
            default_response="Network diagnostics ready, Sir:\n\n{result}",
        ))

        self.register(Capability(
            name="os.lock_workstation",
            description="Immediately locks the Windows workstation screen to protect user privacy and secure the session.",
            supported_outcomes=[
                "lock the computer screen immediately",
                "secure my workstation desktop",
                "lock pc right now",
            ],
            tool_name="lock_workstation",
            risk_level=RiskLevel.LOW,
            verification_strategy=VerificationStrategy.NONE,
            default_response="Workstation locked and secured for you, Sir.",
        ))

        self.register(Capability(
            name="os.empty_recycle_bin",
            description="Permanently empties deleted files and junk from the Windows Recycle Bin to free disk space.",
            supported_outcomes=[
                "empty the recycle bin and clear trash",
                "purge deleted files from the recycle bin",
                "clean out computer trash bin",
            ],
            tool_name="empty_recycle_bin",
            risk_level=RiskLevel.HIGH,
            verification_strategy=VerificationStrategy.NONE,
            default_response="Recycle bin successfully purged, Sir.",
        ))

        self.register(Capability(
            name="os.take_screenshot",
            description="Captures a full-resolution screen snapshot of the active desktop monitor and saves it for inspection.",
            supported_outcomes=[
                "take a screenshot of my screen",
                "capture desktop display snapshot",
                "grab an image of what is on monitor",
                "snap the current screen view",
            ],
            tool_name="take_screen_snapshot",
            risk_level=RiskLevel.SAFE,
            verification_strategy=VerificationStrategy.FILE_EXISTENCE,
            default_response="Screen snapshot captured and saved, Sir:\n{result}",
        ))

        self.register(Capability(
            name="os.get_active_window",
            description="Inspects the currently focused application window title, executable name, and screen geometry.",
            supported_outcomes=[
                "what window is currently active",
                "what application am i currently looking at",
                "which program has focus right now",
                "inspect the foreground window title",
            ],
            tool_name="get_active_window_info",
            risk_level=RiskLevel.SAFE,
            verification_strategy=VerificationStrategy.NONE,
            default_response="Focused application details, Sir:\n\n{result}",
        ))

        self.register(Capability(
            name="os.read_clipboard",
            description="Reads and inspects whatever text is currently stored on the system clipboard.",
            supported_outcomes=[
                "what is on my clipboard right now",
                "read the copied clipboard text",
                "show me what i just copied",
                "check clipboard contents",
            ],
            tool_name="read_clipboard_text",
            risk_level=RiskLevel.SAFE,
            verification_strategy=VerificationStrategy.NONE,
            default_response="Inspecting your clipboard buffer, Sir:\n\n{result}",
        ))

        self.register(Capability(
            name="os.write_clipboard",
            description="Writes specific text or code directly onto the system clipboard for immediate pasting.",
            supported_outcomes=[
                "copy this text to my clipboard",
                "put this snippet onto the clipboard",
                "copy text to clipboard buffer",
            ],
            tool_name="write_clipboard_text",
            parameters=[
                ParameterRequirement(name="text", param_type="str", required=True, description="Text to copy to clipboard")
            ],
            risk_level=RiskLevel.LOW,
            verification_strategy=VerificationStrategy.NONE,
            default_response="Copied text to your clipboard, Sir.",
        ))

        self.register(Capability(
            name="os.media_control",
            description="Controls hardware media playback: toggle play/pause, adjust volume up or down, mute/unmute audio, or skip tracks.",
            supported_outcomes=[
                "pause music or resume playback",
                "mute audio or silence the sound",
                "turn up volume or make it louder",
                "turn down volume or make it quieter",
                "skip to the next track or song",
                "go back to the previous track",
                "hush the audio or silence playback",
                "crank the sound or boost volume",
            ],
            tool_name="media_control",
            parameters=[
                ParameterRequirement(name="action", param_type="str", required=True, description="Action: play_pause, mute, volume_up, volume_down, next, previous")
            ],
            risk_level=RiskLevel.LOW,
            verification_strategy=VerificationStrategy.AUDIO_STATE,
            default_response="Executed media control ({parameters.get('action')}) for you, Sir.",
        ))

        self.register(Capability(
            name="os.set_brightness",
            description="Controls display backlight brightness percentage or dims/boosts screen illumination.",
            supported_outcomes=[
                "change screen brightness to 50 percent",
                "dim the display brightness",
                "brighten the screen or increase backlight",
                "set monitor brightness level",
                "make the screen darker or lighter",
            ],
            tool_name="set_system_brightness",
            parameters=[
                ParameterRequirement(name="level", param_type="int", required=True, description="Brightness percentage 0-100")
            ],
            risk_level=RiskLevel.LOW,
            verification_strategy=VerificationStrategy.BRIGHTNESS_LEVEL,
            default_response="Adjusted display brightness to {parameters.get('level')}%, Sir.",
        ))

        self.register(Capability(
            name="os.set_timer",
            description="Sets a countdown alert timer for a specified duration in minutes with an optional label.",
            supported_outcomes=[
                "set a timer for 5 minutes",
                "create a countdown timer for 10 mins",
                "remind me in 15 minutes",
                "timer 3 minutes named break",
            ],
            tool_name="set_timer",
            parameters=[
                ParameterRequirement(name="minutes", param_type="float", required=True, description="Duration in minutes"),
                ParameterRequirement(name="label", param_type="str", required=False, default="Timer", description="Timer description"),
            ],
            risk_level=RiskLevel.SAFE,
            verification_strategy=VerificationStrategy.NONE,
            default_response="Timer initialized, Sir. {result}",
        ))

        self.register(Capability(
            name="os.list_timers",
            description="Lists all currently active countdown timers and their remaining time.",
            supported_outcomes=[
                "show active countdown timers",
                "how much time is left on my timer",
                "check active timers",
            ],
            tool_name="list_active_timers",
            risk_level=RiskLevel.SAFE,
            verification_strategy=VerificationStrategy.NONE,
            default_response="Here are your active timers, Sir:\n\n{result}",
        ))

        self.register(Capability(
            name="os.list_running_apps",
            description="Scans and lists active workstation processes, open applications, and running programs.",
            supported_outcomes=[
                "what apps are running on my pc",
                "list active desktop processes and programs",
                "show open software and applications",
                "check what is running on my computer",
            ],
            tool_name="list_running_apps",
            risk_level=RiskLevel.SAFE,
            verification_strategy=VerificationStrategy.NONE,
            default_response="Scanning your active desktop workspace, Sir:\n\n{result}",
        ))

        self.register(Capability(
            name="os.switch_browser_profile",
            description="Switches or sets preferred browser automation profile (e.g. switch profile to gaming, use profile 1).",
            supported_outcomes=[
                "switch browser profile to gaming",
                "use chrome profile 1",
                "set preferred browser profile",
                "select default profile",
                "change browser profile",
            ],
            tool_name="set_chrome_profile",
            parameters=[
                ParameterRequirement(name="profile_target", param_type="str", required=True, description="Profile name or index")
            ],
            risk_level=RiskLevel.LOW,
            verification_strategy=VerificationStrategy.NONE,
            default_response="Right away, Sir. Preferred browser profile updated in persistent memory.",
        ))

        self.register(Capability(
            name="os.launch_app",
            description="Launches an installed desktop application, browser, editor, or tool verified through the system application catalog.",
            supported_outcomes=[
                "launch or open an application on my pc",
                "start visual studio code or cursor",
                "open notepad or calculator",
                "open brave or chrome browser",
                "launch discord, spotify, or obsidian",
            ],
            tool_name="open_application",
            parameters=[
                ParameterRequirement(name="app_name", param_type="app_name", required=True, description="Name or alias of the application to open")
            ],
            risk_level=RiskLevel.LOW,
            verification_strategy=VerificationStrategy.PROCESS_RUNNING,
            default_response="Right away, Sir. Initializing **{parameters.get('app_name')}** from your workstation applications.",
        ))

        self.register(Capability(
            name="os.kill_process",
            description="Terminates a running process or unresponsive application by name.",
            supported_outcomes=[
                "force close an application",
                "kill process by name",
                "terminate frozen program",
            ],
            tool_name="kill_process_by_name",
            parameters=[
                ParameterRequirement(name="process_name", param_type="str", required=True, description="Executable name to terminate")
            ],
            risk_level=RiskLevel.HIGH,
            verification_strategy=VerificationStrategy.NONE,
            default_response="Process termination result, Sir: {result}",
        ))

        # ---------------------------------------------------------------------
        # 2. Filesystem & Development Capabilities
        # ---------------------------------------------------------------------
        self.register(Capability(
            name="fs.list_desktop_files",
            description="Lists all files, folders, and documents located directly on the user's Desktop directory.",
            supported_outcomes=[
                "what files are on my desktop",
                "list documents and items on desktop",
                "show desktop directory contents",
            ],
            tool_name="list_desktop_files",
            risk_level=RiskLevel.SAFE,
            verification_strategy=VerificationStrategy.NONE,
            default_response="Here are the items on your Desktop, Sir:\n\n{result}",
        ))

        self.register(Capability(
            name="fs.list_workspace_files",
            description="Lists project code files and directories within the current active repository workspace.",
            supported_outcomes=[
                "what files are in this project",
                "list repository workspace files",
                "inspect codebase folder structure",
            ],
            tool_name="list_workspace_files",
            risk_level=RiskLevel.SAFE,
            verification_strategy=VerificationStrategy.NONE,
            default_response="Workspace files discovered, Sir:\n\n{result}",
        ))

        self.register(Capability(
            name="fs.create_folder",
            description="Creates a new folder or directory at a specified location on disk.",
            supported_outcomes=[
                "create a new directory or folder",
                "make a folder on desktop or workspace",
            ],
            tool_name="create_folder",
            parameters=[
                ParameterRequirement(name="folder_name", param_type="str", required=True, description="Name of the folder"),
                ParameterRequirement(name="location", param_type="str", required=False, default="Desktop", description="Location: Desktop or Workspace"),
            ],
            risk_level=RiskLevel.MEDIUM,
            verification_strategy=VerificationStrategy.FILE_EXISTENCE,
            default_response="Folder created successfully, Sir: {result}",
        ))

        self.register(Capability(
            name="fs.create_file",
            description="Creates a new text or code file on disk with the specified content.",
            supported_outcomes=[
                "create a new file on disk",
                "write a code script and save it",
                "save text content to a file",
            ],
            tool_name="create_file",
            parameters=[
                ParameterRequirement(name="file_name", param_type="str", required=True, description="Filename to create"),
                ParameterRequirement(name="content", param_type="str", required=True, description="File contents"),
                ParameterRequirement(name="location", param_type="str", required=False, default="Desktop", description="Location: Desktop or Workspace"),
            ],
            risk_level=RiskLevel.MEDIUM,
            verification_strategy=VerificationStrategy.FILE_EXISTENCE,
            default_response="File created and saved, Sir: {result}",
        ))

        self.register(Capability(
            name="fs.read_file",
            description="Reads the text content of an existing file on disk.",
            supported_outcomes=[
                "read the contents of a file",
                "inspect what is written in this document",
                "view text inside a script or file",
            ],
            tool_name="read_file_content",
            parameters=[
                ParameterRequirement(name="file_name_or_path", param_type="path", required=True, description="File to read"),
                ParameterRequirement(name="location", param_type="str", required=False, default="Desktop", description="Location: Desktop or Workspace"),
            ],
            risk_level=RiskLevel.SAFE,
            verification_strategy=VerificationStrategy.NONE,
            default_response="File content retrieved, Sir:\n\n{result}",
        ))

        self.register(Capability(
            name="fs.open_editor",
            description="Opens a code file or empty editor in the user's preferred code editor (VS Code, Cursor, Notepad).",
            supported_outcomes=[
                "open code in editor or vscode",
                "launch text editor to write code",
                "open file in notepad or cursor",
            ],
            tool_name="open_text_editor",
            parameters=[
                ParameterRequirement(name="file_name", param_type="str", required=False, default="", description="File to open"),
                ParameterRequirement(name="editor", param_type="str", required=False, default="auto", description="Editor choice"),
            ],
            risk_level=RiskLevel.LOW,
            verification_strategy=VerificationStrategy.PROCESS_RUNNING,
            default_response="Opening editor for you, Sir: {result}",
        ))

        # ---------------------------------------------------------------------
        # 3. Web & Media Intelligence
        # ---------------------------------------------------------------------
        self.register(Capability(
            name="web.search_google",
            description="Performs an intelligent web search on Google or the user's default browser.",
            supported_outcomes=[
                "search the web for information",
                "google a query or look up a topic online",
                "find articles or documentation on the web",
            ],
            tool_name="search_google",
            parameters=[
                ParameterRequirement(name="query", param_type="str", required=True, description="Search keywords")
            ],
            risk_level=RiskLevel.LOW,
            verification_strategy=VerificationStrategy.NONE,
            default_response="Searched the web for you, Sir:\n\n{result}",
        ))

        self.register(Capability(
            name="web.play_media",
            description="Opens YouTube or web media playback in the browser for a requested song, video, or topic.",
            supported_outcomes=[
                "play a song or video on youtube",
                "watch music video in browser",
                "put on some study beats or music",
                "play interstellar theme or podcast",
            ],
            tool_name="play_youtube",
            parameters=[
                ParameterRequirement(name="query", param_type="str", required=True, description="Video or song search query")
            ],
            risk_level=RiskLevel.LOW,
            verification_strategy=VerificationStrategy.PROCESS_RUNNING,
            default_response="Opening media playback for '{parameters.get('query')}', Sir.",
        ))

        self.register(Capability(
            name="web.open_url",
            description="Navigates to a specific website or URL directly in the user's default browser.",
            supported_outcomes=[
                "open a website or link",
                "navigate to a web url in browser",
                "go to this webpage",
            ],
            tool_name="open_url",
            parameters=[
                ParameterRequirement(name="url", param_type="url", required=True, description="Website URL to open")
            ],
            risk_level=RiskLevel.LOW,
            verification_strategy=VerificationStrategy.PROCESS_RUNNING,
            default_response="Navigating to URL in your browser, Sir: {parameters.get('url')}",
        ))

        self.register(Capability(
            name="web.gui_search",
            description="Performs an interactive human-like web search in browser and opens or clicks the top organic result.",
            supported_outcomes=[
                "search google and click the first result",
                "search the web and click top result",
                "open browser search and click first link",
                "search google like a human and open first link",
                "navigate to website and click the top organic result",
            ],
            tool_name="gui_human_search_and_open",
            parameters=[
                ParameterRequirement(name="query", param_type="str", required=True, description="Search query to execute and click")
            ],
            risk_level=RiskLevel.LOW,
            verification_strategy=VerificationStrategy.PROCESS_RUNNING,
            default_response="Navigating to top result for '{parameters.get('query')}', Sir.",
        ))

        # ---------------------------------------------------------------------
        # 4. Career Intelligence & Workforce Tools
        # ---------------------------------------------------------------------
        self.register(Capability(
            name="career.search_jobs",
            description="Scrapes, harvests, deduplicates, and saves verified job and internship openings matching a role and location.",
            supported_outcomes=[
                "search and harvest job openings",
                "find machine learning or ai internships",
                "scrape software engineer vacancies and save to desktop",
                "search for jobs in a city or location and save to desktop",
            ],
            tool_name="search_and_harvest_jobs",
            parameters=[
                ParameterRequirement(name="role", param_type="str", required=True, description="Job title or keywords"),
                ParameterRequirement(name="location", param_type="str", required=False, default="remote", description="Job location"),
            ],
            risk_level=RiskLevel.LOW,
            verification_strategy=VerificationStrategy.FILE_EXISTENCE,
            default_response="Harvested and exported verified career opportunities, Sir:\n\n{result}",
        ))

        # ---------------------------------------------------------------------
        # 5. Conversational & Social Primitives
        # ---------------------------------------------------------------------
        self.register(Capability(
            name="general.greeting",
            description="Responds warmly to user greetings, casual hellos, and arrival check-ins.",
            supported_outcomes=[
                "say hello or greet the assistant",
                "good morning or good afternoon",
                "what's up or how are you",
            ],
            tool_name="greeting",
            risk_level=RiskLevel.SAFE,
            verification_strategy=VerificationStrategy.NONE,
            default_response="SpaceV online and operational, Sir. All cybernetic systems green. How may I assist your workflow today?",
        ))

        self.register(Capability(
            name="general.gratitude",
            description="Acknowledges user expressions of gratitude, appreciation, and compliments.",
            supported_outcomes=[
                "thank you or thanks a lot",
                "appreciate it or great work",
                "well done or awesome job",
            ],
            tool_name="gratitude",
            risk_level=RiskLevel.SAFE,
            verification_strategy=VerificationStrategy.NONE,
            default_response="My absolute pleasure, Sir. Always at your service. Let me know what you'd like to tackle next!",
        ))

        self.register(Capability(
            name="general.farewell",
            description="Acknowledges user sign-off, farewells, and puts the assistant into standby.",
            supported_outcomes=[
                "goodbye or see you later",
                "signing off or bye for now",
                "have a good day or take care",
            ],
            tool_name="farewell",
            risk_level=RiskLevel.SAFE,
            verification_strategy=VerificationStrategy.NONE,
            default_response="Standing by in low-power standby mode, Sir. Call upon me whenever you need assistance.",
        ))

        self.register(Capability(
            name="general.identity",
            description="Explains SpaceV identity, architecture, version, and core capabilities.",
            supported_outcomes=[
                "who are you or what is your name",
                "identify yourself or who created you",
                "what can you do or what are your capabilities",
                "show help or available commands",
            ],
            tool_name="identity",
            risk_level=RiskLevel.SAFE,
            verification_strategy=VerificationStrategy.NONE,
            default_response=(
                "I am **SpaceV** (*System Protocol Autonomous Cybernetic Engine Version V*), "
                "your intelligent desktop companion and autonomous workstation copilot, Sir.\n\n"
                "• 🖥️ **Workstation Control**: Launch apps, inspect windows, capture screen snapshots, manage desktop files.\n"
                "• ⚡ **Cybernetic Automation**: Execute bash tasks, manage timers, optimize memory, detonate sandboxed workflows.\n"
                "• 🌐 **Web Intelligence**: Search the web, play media, distill web pages to Markdown with Crawl4AI.\n"
                "• 🎙️ **Full-Duplex Voice**: Hands-free conversation, speech dictation, audio effects.\n"
                "• 🛡️ **Container Isolation**: Run code in Celesto MicroVMs with strict action authority."
            ),
        ))

        self.register(Capability(
            name="general.presence",
            description="Confirms system presence, operational status, and responsiveness to ping.",
            supported_outcomes=[
                "are you there or are you alive",
                "status check or ping",
                "are you ready or are you listening",
                "are you awake or online",
            ],
            tool_name="status_ping",
            risk_level=RiskLevel.SAFE,
            verification_strategy=VerificationStrategy.NONE,
            default_response="SpaceV systems fully operational, primed, and awaiting your command, Sir.",
        ))


capability_registry = CapabilityRegistry()
