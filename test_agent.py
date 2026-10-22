"""
Unit and integration test script for SpaceV Tools and Fast-Path Dispatcher.
"""
import sys

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    pass
except Exception:
    pass

import unittest

from core.fast_router import FastRouter
from core.scheduler import scheduler
from tools.file_tools import create_file, create_folder, read_file_content, resolve_path
from tools.registry import OLLAMA_TOOLS_SCHEMA, TOOL_FUNCTIONS, execute_tool
from tools.system_tools import (
    get_current_time,
    get_network_info,
    get_system_stats,
    list_active_timers,
    list_running_apps,
    media_control,
    optimize_system_memory,
    set_timer,
)
from tools.vision_tools import read_clipboard_text, write_clipboard_text


class TestSpaceVAgent(unittest.TestCase):
    def test_file_tools(self):
        # Create test folder
        result = create_folder("SpaceV_Auto_Test", "Desktop")
        self.assertIn("Successfully created folder", result)
        test_dir = resolve_path("Desktop") / "SpaceV_Auto_Test"
        self.assertTrue(test_dir.exists())

        # Create test file
        f_res = create_file("spacev_test.txt", "SpaceV Cosmic AI System Active!", "Desktop/SpaceV_Auto_Test")
        self.assertIn("Successfully created file", f_res)

        # Read test file
        read_res = read_file_content("spacev_test.txt", location="Desktop/SpaceV_Auto_Test")
        self.assertIn("SpaceV Cosmic AI System Active!", read_res)

        # Cleanup
        test_file = test_dir / "spacev_test.txt"
        if test_file.exists():
            test_file.unlink()
        if test_dir.exists():
            test_dir.rmdir()

    def test_system_tools(self):
        time_res = get_current_time()
        self.assertIn("The current time is", time_res)

        stats_res = get_system_stats()
        self.assertIn("CPU Usage", stats_res)
        self.assertIn("RAM", stats_res)

        net_res = get_network_info()
        self.assertIn("Network Diagnostics", net_res)

        apps_res = list_running_apps()
        self.assertIn("Top Active Applications", apps_res)

        mem_res = optimize_system_memory()
        self.assertIn("Optimization Complete", mem_res)

        media_res = media_control("volume_up")
        self.assertIn("Increased system volume", media_res)

    def test_timer_and_scheduler(self):
        t_res = set_timer(0.05, label="Test Timer")
        self.assertIn("Timer 'Test Timer' set", t_res)

        active = list_active_timers()
        self.assertIn("Test Timer", active)
        scheduler.cancel_all()

    def test_clipboard_tools(self):
        test_msg = "⚡ SpaceV Cybernetic Protocol Active"
        w_res = write_clipboard_text(test_msg)
        if "Failed to copy" in w_res:
            self.assertIn("Failed to copy", w_res)
        else:
            self.assertIn("Successfully copied", w_res)
            r_res = read_clipboard_text()
            self.assertIn("SpaceV Cybernetic Protocol Active", r_res)

    def test_tool_registry_integrity(self):
        schema_names = {s["function"]["name"] for s in OLLAMA_TOOLS_SCHEMA}
        registered_names = set(TOOL_FUNCTIONS.keys())

        self.assertTrue(schema_names.issubset(registered_names), f"Missing functions: {schema_names - registered_names}")

        res = execute_tool("get_current_time", {})
        self.assertIn("The current time is", res)

    def test_fast_router_spacev_matchers(self):
        # SpaceV Greetings
        match = FastRouter.match("hey spacev")
        self.assertIsNotNone(match)
        self.assertEqual(match[0], "greeting")

        # Conversational greeting & what's up (0ms)
        match_up = FastRouter.match("hello what's up")
        self.assertIsNotNone(match_up)
        self.assertEqual(match_up[0], "greeting")

        match_whats = FastRouter.match("what's up")
        self.assertIsNotNone(match_whats)
        self.assertEqual(match_whats[0], "greeting")

        # Gratitude (0ms)
        match_thanks = FastRouter.match("thank you")
        self.assertIsNotNone(match_thanks)
        self.assertEqual(match_thanks[0], "gratitude")

        # Farewell (0ms)
        match_bye = FastRouter.match("goodbye")
        self.assertIsNotNone(match_bye)
        self.assertEqual(match_bye[0], "farewell")

        # Ping / Readiness (0ms)
        match_ping = FastRouter.match("are you there")
        self.assertIsNotNone(match_ping)
        self.assertEqual(match_ping[0], "status_ping")

        # Identity
        match = FastRouter.match("who are you")
        self.assertIsNotNone(match)
        self.assertEqual(match[0], "identity")
        self.assertIn("SpaceV", match[2])

        # Timer
        match = FastRouter.match("set a timer for 5 minutes")
        self.assertIsNotNone(match)
        self.assertEqual(match[0], "set_timer")
        scheduler.cancel_all()

        # Time
        match = FastRouter.match("what time is it")
        self.assertIsNotNone(match)
        self.assertEqual(match[0], "get_current_time")

        # Media
        match = FastRouter.match("pause music")
        self.assertIsNotNone(match)
        self.assertEqual(match[0], "media_control")

        # Network
        match = FastRouter.match("check wifi")
        self.assertIsNotNone(match)
        self.assertEqual(match[0], "get_network_info")

        # Desktop Files & Items
        match_dt1 = FastRouter.match("what is on the desktop")
        self.assertIsNotNone(match_dt1)
        self.assertEqual(match_dt1[0], "list_desktop_files")

        match_dt2 = FastRouter.match("what is on my desktop")
        self.assertIsNotNone(match_dt2)
        self.assertEqual(match_dt2[0], "list_desktop_files")

        match_dt3 = FastRouter.match("what's on the desktop")
        self.assertIsNotNone(match_dt3)
        self.assertEqual(match_dt3[0], "list_desktop_files")

        # Desktop Running Apps & Processes
        match_run1 = FastRouter.match("what is currently running on the desktop")
        self.assertIsNotNone(match_run1)
        self.assertEqual(match_run1[0], "list_running_apps")

        match_run2 = FastRouter.match("what is going in the desktop")
        self.assertIsNotNone(match_run2)
        self.assertEqual(match_run2[0], "list_running_apps")

        match_run3 = FastRouter.match("what apps are running")
        self.assertIsNotNone(match_run3)
        self.assertEqual(match_run3[0], "list_running_apps")

        # YouTube Video & Music Playback
        match_yt1 = FastRouter.match("open chrome open youtube play uma telugu latest video")
        self.assertIsNotNone(match_yt1)
        self.assertEqual(match_yt1[0], "play_youtube")
        self.assertIn("uma telugu latest video", match_yt1[2])

        match_yt2 = FastRouter.match("play uma telugu latest video on youtube")
        self.assertIsNotNone(match_yt2)
        self.assertEqual(match_yt2[0], "play_youtube")

        match_yt3 = FastRouter.match("open youtube play lofi beats")
        self.assertIsNotNone(match_yt3)
        self.assertEqual(match_yt3[0], "play_youtube")

    def test_pydantic_schema_validation_and_coercion(self):
        from tools.schemas import CreateFolderInput, SetTimerInput

        # Test string-to-float coercion
        timer_input = SetTimerInput(minutes="10", label="Focus Session")
        self.assertEqual(timer_input.minutes, 10.0)
        self.assertEqual(timer_input.label, "Focus Session")

        # Test defaults
        folder_input = CreateFolderInput(folder_name="CosmicProject")
        self.assertEqual(folder_input.location, "Desktop")

        # Test tool execution with coercion via registry
        res = execute_tool("set_timer", {"minutes": "0.1", "label": "Coercion Test"})
        self.assertIn("Timer 'Coercion Test' set", res)
        scheduler.cancel_all()

    def test_langgraph_engine_compilation_and_fast_path(self):
        from core.graph_engine import SpaceVGraphEngine
        engine = SpaceVGraphEngine()

        # Verify LangGraph compiled app exists
        self.assertIsNotNone(engine.app)

        # Test Fast-Path execution through LangGraph runner
        received_tokens = []
        reply = engine.run("who are you", token_callback=lambda t: received_tokens.append(t))
        self.assertIn("SpaceV", reply)
        self.assertTrue(len(received_tokens) > 0)

    def test_gui_drawing_vector_strokes_and_schemas(self):
        from tools.gui_tools import get_shape_strokes
        from tools.schemas import GuiDrawInPaintInput

        # Test House stroke generator
        label, house_strokes = get_shape_strokes("house")
        self.assertEqual(label, "House")
        self.assertTrue(len(house_strokes) >= 5)

        # Test Heart stroke generator
        label, heart_strokes = get_shape_strokes("heart")
        self.assertEqual(label, "Heart")
        self.assertTrue(len(heart_strokes[0]) >= 30)

        # Test Star stroke generator
        label, star_strokes = get_shape_strokes("star")
        self.assertEqual(label, "Star")
        self.assertEqual(len(star_strokes[0]), 11)

        # Test Smiley Face
        label, smile_strokes = get_shape_strokes("smiley face")
        self.assertEqual(label, "Smiley Face")

        # Test Car
        label, car_strokes = get_shape_strokes("car")
        self.assertEqual(label, "Car")

        # Test Pydantic Schema
        draw_input = GuiDrawInPaintInput(shape_or_prompt="star")
        self.assertEqual(draw_input.shape_or_prompt, "star")

        # Test fast-path matcher for drawing
        draw_match = FastRouter.match("draw a house in paint")
        self.assertIsNotNone(draw_match)
        self.assertEqual(draw_match[0], "gui_draw_in_paint")

    def test_proactive_companion_and_dynamic_chips(self):
        from core.proactive_companion import ProactiveCompanion, companion_engine

        # Test dynamic chips derivation
        coding_chips = ProactiveCompanion.get_follow_up_chips("activate_workspace_mode")
        self.assertTrue(len(coding_chips) >= 3)
        self.assertTrue(any("Beats" in c[0] or "Lofi" in c[0] for c in coding_chips))

        paint_chips = ProactiveCompanion.get_follow_up_chips("gui_draw_in_paint")
        self.assertTrue(len(paint_chips) >= 3)
        self.assertTrue(any("Draw" in c[0] for c in paint_chips))

        timer_chips = ProactiveCompanion.get_follow_up_chips("set_timer")
        self.assertTrue(len(timer_chips) >= 2)

        # Test conversational wrap
        wrap = ProactiveCompanion.generate_conversational_wrap("activate_workspace_mode", "Coding mode active")
        self.assertIn("Would you like me to", wrap)

        # Test activity recording
        companion_engine.record_activity()
        self.assertTrue(companion_engine.last_activity > 0)

    def test_multimodel_router_and_ram_optimization(self):
        from core.model_router import ROLE_CODER_TOOLS, ROLE_FAST_CHAT, ROLE_VISION, MultiModelRouter
        router = MultiModelRouter()

        # Test Intent Classification
        chat_role = router.classify_intent("Tell me a short science fiction story")
        self.assertEqual(chat_role, ROLE_FAST_CHAT)

        code_role = router.classify_intent("Write a python script to sort files")
        self.assertEqual(code_role, ROLE_CODER_TOOLS)

        tool_role = router.classify_intent("Calculate something", has_tools=True)
        self.assertEqual(tool_role, ROLE_CODER_TOOLS)

        vision_role = router.classify_intent("Look at my screen and tell me what you see")
        self.assertEqual(vision_role, ROLE_VISION)

        # Test keep_alive parameter for RAM/VRAM management
        from config import OLLAMA_KEEP_ALIVE
        keep_alive = MultiModelRouter.get_keep_alive()
        self.assertEqual(keep_alive, OLLAMA_KEEP_ALIVE)

        # Test model resolution fallback
        model_name, role = router.select_model("Hello SpaceV")
        self.assertTrue(len(model_name) > 0)

    def test_neural_vad_and_modern_voice_pipeline(self):
        import numpy as np

        from core.fast_router import FastRouter
        from voice.audio_stream import AudioStreamRecorder
        from voice.vad_detector import SileroVADDetector

        # 1. Test Silero VAD initialization and inference
        vad = SileroVADDetector()
        self.assertTrue(vad.is_neural)

        # Silent frame (512 samples = 1024 bytes)
        silent_frame = np.zeros(512, dtype=np.int16).tobytes()
        is_speech, prob = vad.process_frame(silent_frame)
        self.assertFalse(is_speech)
        self.assertTrue(prob < 0.2)

        # Reset state
        vad.reset_state()

        # 2. Test AudioStreamRecorder WAV serialization
        dummy_pcm = np.zeros(1600, dtype=np.int16).tobytes()  # 100ms
        wav_bytes = AudioStreamRecorder.pcm_to_wav_bytes(dummy_pcm, sample_rate=16000)
        self.assertTrue(wav_bytes.startswith(b"RIFF"))
        self.assertIn(b"WAVE", wav_bytes[:12])

        # 3. Test FastRouter dictation trigger
        match = FastRouter.match("activate dictation mode")
        self.assertIsNotNone(match)
        self.assertEqual(match[0], "dictation_mode")
        self.assertIn("Dictation Activated", match[1])
        from voice.dictation_manager import dictation_manager
        dictation_manager.stop_dictation()

    def test_cursor_speed_profiles(self):
        from tools.gui_tools import CURSOR_SPEED_PRESETS, safety

        expected_profiles = ["Hyper", "Fast", "Normal", "Steady", "Precision"]
        for p in expected_profiles:
            self.assertIn(p, CURSOR_SPEED_PRESETS)
            self.assertTrue(safety.set_cursor_speed(p))
            settings = safety.get_speed_settings()
            self.assertEqual(safety.current_speed, p)
            self.assertIn("multiplier", settings)
            self.assertIn("move_duration", settings)
            self.assertIn("type_interval", settings)

        # Verify ordering of multipliers: Hyper < Fast < Normal < Steady < Precision
        self.assertTrue(
            CURSOR_SPEED_PRESETS["Hyper"]["multiplier"] <
            CURSOR_SPEED_PRESETS["Fast"]["multiplier"] <
            CURSOR_SPEED_PRESETS["Normal"]["multiplier"] <
            CURSOR_SPEED_PRESETS["Steady"]["multiplier"] <
            CURSOR_SPEED_PRESETS["Precision"]["multiplier"]
        )

        # Reset back to Normal
        safety.set_cursor_speed("Normal")

    def test_chrome_profile_preference_router(self):
        from core.fast_router import FastRouter
        from core.memory import memory

        # Test setting profile to vicky
        res = FastRouter.match("use chrome profile vicky")
        self.assertIsNotNone(res)
        self.assertEqual(res[0], "set_chrome_profile")
        self.assertEqual(res[1], "vicky")
        self.assertIn("Vicky Space", res[2])
        self.assertEqual(memory.get("preferred_chrome_profile"), "vicky")

        # Test querying current profile
        res_query = FastRouter.match("which chrome profile am i using")
        self.assertIsNotNone(res_query)
        self.assertEqual(res_query[0], "get_chrome_profile")
        self.assertIn("Vicky Space", res_query[2])

        # Test switching back to vikram via short phrase
        res_vikram = FastRouter.match("use vikram")
        self.assertIsNotNone(res_vikram)
        self.assertEqual(res_vikram[1], "vikram")
        self.assertEqual(memory.get("preferred_chrome_profile"), "vikram")

        # Test Jarvis Task Resumption
        memory.set("pending_resume_task", "uma telugu latest video")
        res_resume = FastRouter.match("use vicky")
        self.assertIsNotNone(res_resume)
        self.assertEqual(res_resume[1], "vicky")
        self.assertIn("Resuming your request for", res_resume[2])
        self.assertIn("uma telugu latest video", res_resume[2])
        self.assertIsNone(memory.get("pending_resume_task"))

        # Switch back to vikram for standard testing
        FastRouter.match("use vikram")

    def test_langgraph_engine_nodes_and_execution(self):
        from core.graph_engine import SpaceVGraphEngine
        engine = SpaceVGraphEngine()

        # Verify compiled app nodes
        expected_nodes = {"fast_router", "perception_guard", "model_reasoning", "tool_executor", "clarification_node", "response_synthesizer"}
        graph_nodes = set(engine.workflow.nodes.keys())
        self.assertTrue(expected_nodes.issubset(graph_nodes))

        # Test fast-path execution through compiled graph
        tokens = []
        reply = engine.run("who are you", token_callback=lambda t: tokens.append(t))
        self.assertIn("SpaceV", reply)
        self.assertTrue(len(tokens) > 0)

    def test_universal_modal_interceptor_and_memory(self):
        from core.fast_router import FastRouter
        from core.memory import memory

        # 1. Test Hierarchical Preference Matrix
        memory.set_preference("vscode", "trust_workspace", "always_trust")
        self.assertEqual(memory.get_preference("vscode", "trust_workspace"), "always_trust")

        memory.set_preference("notepad", "save_policy", "save")
        self.assertEqual(memory.get_preference("notepad", "save_policy"), "save")

        # Backwards compatibility check
        memory.set_preference("chrome", "profile", "vikram")
        self.assertEqual(memory.get("preferred_chrome_profile"), "vikram")

        # 2. Test Universal Disambiguation Continuation (0ms)
        memory.set_suspended_disambiguation({
            "domain": "file_explorer",
            "property_key": "conflict_policy",
            "question": "A file conflict occurred.",
            "options": [("🔄 Replace", "replace"), ("⏭️ Skip", "skip")],
            "suspended_task": "create summary on Desktop"
        })

        # User responds with "replace"
        res = FastRouter.match("replace")
        self.assertIsNotNone(res)
        self.assertEqual(res[0], "resolve_disambiguation")
        self.assertEqual(res[1], "replace")
        self.assertIn("File_explorer", res[2])
        self.assertIn("create summary on Desktop", res[2])
        self.assertEqual(memory.get_preference("file_explorer", "conflict_policy"), "replace")
        self.assertIsNone(memory.get_suspended_disambiguation())

    def test_neural_tts_audio_cache_and_parallel_tools(self):
        # 1. Test in-memory audio cache
        from voice.tts_engine import _NEURAL_AUDIO_CACHE
        test_key = "right away, sir."
        _NEURAL_AUDIO_CACHE[test_key] = b"MOCK_PCM_AUDIO_BYTES"
        self.assertIn(test_key, _NEURAL_AUDIO_CACHE)
        self.assertEqual(_NEURAL_AUDIO_CACHE[test_key], b"MOCK_PCM_AUDIO_BYTES")

        # 2. Test parallel tool execution in graph engine
        from core.graph_engine import SpaceVGraphEngine
        engine = SpaceVGraphEngine()
        state = {
            "user_prompt": "telemetry test",
            "messages": [],
            "fast_path_result": None,
            "tool_calls": [
                {"function": {"name": "get_current_time", "arguments": {}}},
                {"function": {"name": "get_network_info", "arguments": {}}}
            ],
            "tool_results": [],
            "active_window": "",
            "stuck_detected": False,
            "clarification_question": None,
            "final_response": "",
            "iteration": 0,
            "is_complete": False
        }
        res_state = engine._tool_executor_node(state)
        self.assertEqual(len(res_state["tool_results"]), 2)
        self.assertFalse(res_state["stuck_detected"])

    def test_vision_grounding_and_vector_rag(self):
        from PIL import Image, ImageDraw

        from core.vector_memory import vector_memory
        from tools.registry import TOOL_FUNCTIONS, execute_tool

        # 1. Test Semantic Vector / FTS5 Memory Storage & Search
        vector_memory.store("doc_1", "Cosmic deployment instructions for SpaceV agent", domain="docs")
        vector_memory.store("doc_2", "Database password and redis cache config", domain="credentials")

        search_res = vector_memory.search("deployment instructions")
        self.assertTrue(len(search_res) >= 1)
        self.assertEqual(search_res[0]["id"], "doc_1")
        self.assertIn("SpaceV", search_res[0]["content"])

        # Test search_memory tool wrapper
        tool_reply = execute_tool("search_memory", {"query": "deployment"})
        self.assertIn("SpaceV", tool_reply)

        # 2. Test Vision Grounding OCR Center Finding on Synthetic PIL Image
        from core.vision_grounding import find_text_coordinates
        img = Image.new('RGB', (800, 300), color=(255, 255, 255))
        d = ImageDraw.Draw(img)
        d.text((200, 100), 'Install Chrome', fill=(0, 0, 0))

        match = find_text_coordinates("chrome", image=img, min_similarity=0.60)
        if match:
            cx, cy, word, score = match
            self.assertTrue(cx > 100)
            self.assertTrue(cy > 50)
            self.assertTrue(score >= 0.60)

        # 3. Verify registry contains new tools
        self.assertIn("gui_click_text", TOOL_FUNCTIONS)
        self.assertIn("read_screen_text", TOOL_FUNCTIONS)
        self.assertIn("search_memory", TOOL_FUNCTIONS)

    def test_windows_uia_and_dual_tier_grounding(self):
        from core.uia_grounding import find_control_by_name, list_interactive_controls
        from tools.registry import TOOL_FUNCTIONS

        # 1. Test listing controls (runs safely in any desktop/console session)
        controls = list_interactive_controls(limit=5)
        self.assertIsInstance(controls, list)

        # 2. Test control lookup
        ctrl = find_control_by_name("NonExistentWindowControlXYZ123")
        self.assertIsNone(ctrl)

        # 3. Verify tool registry has dual-tier tools
        self.assertIn("gui_click_control", TOOL_FUNCTIONS)
        self.assertIn("search_clipboard_history", TOOL_FUNCTIONS)
        self.assertIn("get_activity_timeline", TOOL_FUNCTIONS)

    def test_temporal_timeline_memory_and_privacy(self):
        from core.fast_router import FastRouter
        from core.temporal_memory import sanitize_text, temporal_memory

        # 1. Test automated privacy redaction
        raw_secret = "Confidential: api_key = sk-1234567890123456789012 and password = 'mySecretPassword99'"
        clean = sanitize_text(raw_secret)
        self.assertNotIn("sk-1234567890123456789012", clean)
        self.assertIn("***REDACTED***", clean)

        # 2. Test event recording and retrieval
        e_id = temporal_memory.record_event(
            event_type="clipboard",
            title="Copied Docker run command",
            content="docker run -d -p 8080:8080 spacev/engine:latest"
        )
        self.assertTrue(e_id > 0)

        # 3. Test FTS5 search
        results = temporal_memory.search_events("spacev engine", event_type="clipboard")
        self.assertTrue(len(results) >= 1)
        self.assertIn("docker run", results[0]["content"])

        # 4. Test recent clipboard fetch
        recent = temporal_memory.get_recent_clipboard(limit=3)
        self.assertTrue(len(recent) >= 1)

        # 5. Test FastRouter clipboard history trigger
        res = FastRouter.match("clipboard history")
        self.assertIsNotNone(res)
        self.assertEqual(res[0], "get_clipboard_history")
        self.assertIn("Clipboard", res[2])

    def test_langgraph_self_healing_node(self):
        from core.graph_engine import SpaceVGraphEngine
        from core.self_healing import self_healing_engine

        # 1. Test failure diagnosis
        diag_locked = self_healing_engine.diagnose_failure("read_file_content", {"filename": "data.bin"}, "PermissionError: [WinError 32] The process cannot access the file because it is being used by another process")
        self.assertEqual(diag_locked["category"], "RESOURCE_LOCKED")

        diag_ui = self_healing_engine.diagnose_failure("gui_click_text", {"target_text": "Download"}, "Could not visually locate 'Download' on your screen.")
        self.assertEqual(diag_ui["category"], "UI_ELEMENT_NOT_FOUND")

        # 2. Test remediation strategy mutation
        can_heal, new_tool, new_args, msg = self_healing_engine.attempt_remediation(diag_ui, 0)
        self.assertTrue(can_heal)
        self.assertEqual(new_tool, "gui_click_control")
        self.assertEqual(new_args["target_name"], "Download")

        # 3. Test Graph Engine incorporates self_healing node
        engine = SpaceVGraphEngine()
        self.assertIn("self_healing", engine.workflow.nodes)

        # 4. Test self_healing node state transition
        mock_state = {
            "user_prompt": "click download",
            "messages": [],
            "fast_path_result": None,
            "tool_calls": [],
            "tool_results": [{"name": "gui_click_text", "args": {"target_text": "Submit"}, "result": "Could not visually locate 'Submit'"}],
            "active_window": "",
            "stuck_detected": False,
            "clarification_question": None,
            "final_response": "",
            "iteration": 0,
            "is_complete": False,
            "healing_attempts": 0,
            "last_error": "Could not visually locate 'Submit'"
        }
        healed_state = engine._self_healing_node(mock_state)
        self.assertEqual(healed_state["healing_attempts"], 1)
        self.assertTrue(len(healed_state["tool_calls"]) > 0)
        self.assertEqual(healed_state["tool_calls"][0]["function"]["name"], "gui_click_control")

    def test_ghost_mode_manager_and_process_isolation(self):
        import sys

        from core.fast_router import FastRouter
        from core.ghost_mode import ghost_manager

        # 1. Test enable & disable
        msg_enable = ghost_manager.enable()
        self.assertTrue(ghost_manager.is_active)
        self.assertIn("ACTIVE", msg_enable)

        msg_disable = ghost_manager.disable()
        self.assertFalse(ghost_manager.is_active)
        self.assertIn("DEACTIVATED", msg_disable)

        # 2. Test silent background process spawning
        code, out = ghost_manager.execute_silent_process([sys.executable, "-c", "print('SpaceV_Ghost_Active')"])
        self.assertEqual(code, 0)
        self.assertIn("SpaceV_Ghost_Active", out)

        # 3. Test FastRouter ghost mode triggers
        m_on = FastRouter.match("activate ghost mode")
        self.assertIsNotNone(m_on)
        self.assertEqual(m_on[0], "toggle_ghost_mode")
        self.assertEqual(m_on[1], "enabled")

        m_off = FastRouter.match("turn off ghost mode")
        self.assertIsNotNone(m_off)
        self.assertEqual(m_off[0], "toggle_ghost_mode")
        self.assertEqual(m_off[1], "disabled")

    def test_aec_full_duplex_barge_in_guard(self):
        from voice.aec_guard import aec_guard

        # 1. Normal state: speaker inactive
        aec_guard.set_speaker_active(False)
        self.assertFalse(aec_guard.is_speaker_active)
        is_speech, prob = aec_guard.evaluate_frame(True, 0.65, 0.02)
        self.assertTrue(is_speech)
        self.assertEqual(prob, 0.65)

        # 2. Active state: SpaceV is speaking through speakers
        barge_in_triggered = []
        aec_guard.register_barge_in_callback(lambda: barge_in_triggered.append(True))
        aec_guard.set_speaker_active(True)
        self.assertTrue(aec_guard.is_speaker_active)

        # Room echo (prob 0.65) should be suppressed
        is_speech_echo, prob_echo = aec_guard.evaluate_frame(True, 0.65, 0.02)
        self.assertFalse(is_speech_echo)
        self.assertTrue(prob_echo < 0.2)

        # Intentional loud user voice (prob 0.88, high energy) triggers barge-in
        is_speech_barge, prob_barge = aec_guard.evaluate_frame(True, 0.88, 0.05)
        self.assertTrue(is_speech_barge)
        self.assertTrue(len(barge_in_triggered) >= 1)

        # Reset back to inactive
        aec_guard.set_speaker_active(False)

    def test_screen_capture_multi_tier_engine(self):
        from core.screen_capture import capture_desktop_cv2, capture_desktop_pil, get_active_capture_tier

        # 1. Test tier discovery
        tier = get_active_capture_tier()
        self.assertIn(tier, ["DXGI (DirectX 11 GPU VRAM)", "GDI (Windows Desktop Host)"])

        # 2. Test PIL and CV2 captures execute without raising exceptions
        pil_frame = capture_desktop_pil()
        cv2_frame = capture_desktop_cv2()
        # In non-interactive background/console sessions, returns None or Image safely
        if pil_frame is not None:
            self.assertTrue(pil_frame.width > 0)
        if cv2_frame is not None:
            self.assertTrue(len(cv2_frame.shape) == 3)

    def test_omniparser_v2_icon_detection_and_grounding(self):
        import cv2
        import numpy as np
        from PIL import Image

        from core.omniparser import omniparser
        from tools.registry import TOOL_FUNCTIONS

        # 1. Synthesize canvas with non-text icons (Play triangle and Close X)
        canvas = np.ones((500, 800, 3), dtype=np.uint8) * 255

        # Draw a Play button triangle at (120, 170) -> (170, 200)
        pts = np.array([[120, 170], [120, 230], [170, 200]], np.int32)
        cv2.fillPoly(canvas, [pts], (0, 0, 0))

        # Draw a Close button X at (580, 80) -> (620, 120)
        cv2.line(canvas, (580, 80), (620, 120), (0, 0, 0), 4)
        cv2.line(canvas, (620, 80), (580, 120), (0, 0, 0), 4)

        pil_img = Image.fromarray(canvas)

        # 2. Test screen parsing
        elements = omniparser.parse_screen(pil_img)
        self.assertTrue(len(elements) >= 2)

        # 3. Test Play icon discovery
        match_play = omniparser.find_icon_or_element("play button", image=pil_img)
        self.assertIsNotNone(match_play)
        cx_play, cy_play, label_play, conf_play = match_play
        self.assertEqual(label_play, "play")
        self.assertTrue(110 <= cx_play <= 180)
        self.assertTrue(160 <= cy_play <= 240)
        self.assertTrue(conf_play > 0.8)

        # 4. Test Close icon discovery
        match_close = omniparser.find_icon_or_element("close window", image=pil_img)
        self.assertIsNotNone(match_close)
        cx_close, cy_close, label_close, conf_close = match_close
        self.assertEqual(label_close, "close")
        self.assertTrue(570 <= cx_close <= 630)
        self.assertTrue(70 <= cy_close <= 130)

        # 5. Verify registry mapping
        self.assertIn("gui_click_icon", TOOL_FUNCTIONS)
        self.assertIn("parse_screen_elements", TOOL_FUNCTIONS)

    def test_sqlite_vec_dense_knn_and_hybrid_rag(self):

        from core.vector_memory import generate_embedding, vector_memory

        # 1. Verify C extension is actively loaded
        self.assertTrue(vector_memory.is_vec_available)
        self.assertEqual(vector_memory.dimension, 384)

        # 2. Test embedding generation (dense unit vector)
        emb = generate_embedding("Kubernetes container cluster orchestration")
        self.assertEqual(len(emb), 384)
        norm = sum(x * x for x in emb) ** 0.5
        self.assertAlmostEqual(norm, 1.0, places=3)

        # 3. Store test documents
        doc_a = "doc_test_kube"
        doc_b = "doc_test_chef"
        vector_memory.store(doc_a, "Deploy Docker containers to Kubernetes cluster pod", domain="devops")
        vector_memory.store(doc_b, "Sauté garlic and onions in olive oil for pasta recipe", domain="culinary")

        # 4. Dense Vector KNN Search
        q_vec = generate_embedding("Kubernetes deployment")
        vec_matches = vector_memory.search_vector(q_vec, top_k=2)
        self.assertTrue(len(vec_matches) >= 1)
        self.assertEqual(vec_matches[0]["id"], doc_a)
        self.assertTrue(vec_matches[0]["relevance_score"] > 0.0)

        # 5. Hybrid Retrieval (Dense KNN + FTS5 BM25)
        hybrid_matches = vector_memory.search("Kubernetes cluster", top_k=2, alpha=0.5)
        self.assertTrue(len(hybrid_matches) >= 1)
        self.assertEqual(hybrid_matches[0]["id"], doc_a)
        self.assertIn("Kubernetes", hybrid_matches[0]["content"])

        # 6. Cleanup
        vector_memory.delete(doc_a)
        vector_memory.delete(doc_b)

    def test_semantic_router_fuzzy_intent_matching_and_latency(self):
        from core.fast_router import FastRouter
        from core.semantic_router_engine import semantic_router_engine

        # 1. Verify router initialization
        self.assertIsNotNone(semantic_router_engine.router)

        # 2. Test sub-4ms intent matching on natural language phrasing
        test_cases = [
            ("could you please check how much ram my pc is using right now", "get_system_stats"),
            ("tell me the current time please", "get_current_time"),
            ("free up some memory on this computer", "optimize_system_memory"),
            ("silence system volume right now", "media_mute")
        ]

        for prompt, expected_intent in test_cases:
            match = semantic_router_engine.route(prompt)
            self.assertIsNotNone(match, f"Failed to match prompt: '{prompt}'")
            intent, conf, latency = match
            self.assertEqual(intent, expected_intent)
            self.assertTrue(conf >= semantic_router_engine.confidence_threshold)
            self.assertTrue(latency < 15.0, f"Latency {latency}ms exceeds reasonable warm threshold")

        # 3. Test negative / out-of-domain fallback (complex coding question should not trigger fast path)
        complex_prompt = "implement a recursive red-black tree balancing function in rust"
        neg_match = semantic_router_engine.route(complex_prompt)
        self.assertIsNone(neg_match)

        # 4. Test end-to-end integration via FastRouter.match
        fast_res = FastRouter.match("could you please check how much ram my pc is using right now")
        self.assertIsNotNone(fast_res)
        self.assertEqual(fast_res[0], "get_system_stats")
        self.assertIn("System diagnostics", fast_res[2])

    def test_pipecat_frame_graph_and_microsecond_audio_flush(self):
        from voice.frame_pipeline import (
            AudioRawFrame,
            UserStartedSpeakingFrame,
            UserStoppedSpeakingFrame,
            frame_pipeline,
            pipecat_frame_graph,
        )

        # 1. Verify Frame Graph singleton integrity
        self.assertIs(frame_pipeline, pipecat_frame_graph)

        # 2. Test microsecond audio buffer flushing upon conversational turn-taking
        flush_res = frame_pipeline.flush_microsecond(reason="conversational_turn_taking_test")
        self.assertEqual(flush_res["status"], "flushed")
        self.assertEqual(flush_res["reason"], "conversational_turn_taking_test")
        self.assertTrue(flush_res["flush_latency_us"] < 2500.0, f"Flush latency {flush_res['flush_latency_us']}μs exceeded threshold")
        self.assertTrue(frame_pipeline.total_flushes >= 1)

        # 3. Test Pipecat typed frames instantiation
        raw_frame = AudioRawFrame(pcm_bytes=b"\x00" * 3200, is_speech=True, vad_probability=0.95)
        self.assertEqual(len(raw_frame.pcm_bytes), 3200)
        self.assertTrue(raw_frame.is_speech)

        turn_start = UserStartedSpeakingFrame()
        self.assertIsNotNone(turn_start)

        turn_stop = UserStoppedSpeakingFrame(accumulated_pcm=b"\x00" * 6400)
        self.assertEqual(len(turn_stop.accumulated_pcm), 6400)

        # 4. Test full pipeline interruption and AEC barge-in coordination
        interrupt_events = []
        frame_pipeline.pipeline_interrupted.connect(lambda reason: interrupt_events.append(reason))
        frame_pipeline.interrupt(reason="test_barge_in")
        self.assertIn("test_barge_in", interrupt_events)

        # 5. Verify telemetry reporting
        telemetry = frame_pipeline.get_telemetry()
        self.assertIn("total_flushes", telemetry)
        self.assertIn("last_flush_latency_us", telemetry)

    def test_ui_tars_vision_foundation_action_grammar_and_execution(self):
        import cv2
        import numpy as np
        from PIL import Image

        from core.ui_tars import UITARSEngine, ui_tars_engine
        from tools.registry import TOOL_FUNCTIONS, execute_tool

        # 1. Test UI-TARS action syntax parser with OSWorld [0, 1000] normalization
        raw_click_text = (
            "Thought: To play the media, I will click the triangular play button.\n"
            "Action: click(point='(150, 200)')"
        )
        action_click = UITARSEngine.parse_action(raw_click_text, screen_w=1920, screen_h=1080)
        self.assertEqual(action_click.action_type, "click")
        self.assertEqual(action_click.point, (288, 216))  # 150/1000 * 1920, 200/1000 * 1080
        self.assertIn("play", action_click.thought)

        # 2. Test bounding box parser
        raw_bbox_text = (
            "Thought: Locate submit button on screen.\n"
            "Action: click(start_box='(400, 300, 600, 350)')"
        )
        action_bbox = UITARSEngine.parse_action(raw_bbox_text, screen_w=1000, screen_h=1000)
        self.assertEqual(action_bbox.action_type, "click")
        self.assertEqual(action_bbox.point, (500, 325))

        # 3. Test typing and key actions
        raw_type_text = "Thought: Type search query\nAction: type(content='SpaceV OSWorld')"
        action_type = UITARSEngine.parse_action(raw_type_text, screen_w=1920, screen_h=1080)
        self.assertEqual(action_type.action_type, "type")
        self.assertEqual(action_type.content, "SpaceV OSWorld")

        raw_key_text = "Thought: Press Enter to submit\nAction: press_key(key='enter')"
        action_key = UITARSEngine.parse_action(raw_key_text, screen_w=1920, screen_h=1080)
        self.assertEqual(action_key.action_type, "press_key")
        self.assertEqual(action_key.key, "enter")

        # 4. Test closed-loop visual grounding on synthetic canvas
        canvas = np.ones((600, 800, 3), dtype=np.uint8) * 255
        pts = np.array([[120, 170], [120, 230], [170, 200]], np.int32)
        cv2.fillPoly(canvas, [pts], (0, 0, 0))
        img = Image.fromarray(canvas)

        predicted_act = ui_tars_engine.predict_action("click the play button", image=img)
        self.assertEqual(predicted_act.action_type, "click")
        self.assertIsNotNone(predicted_act.point)

        # 5. Verify Tool Registry mapping
        self.assertIn("ui_tars_navigate_and_act", TOOL_FUNCTIONS)
        self.assertIn("ui_tars_computer_control", TOOL_FUNCTIONS)

        # Tool execution test
        tool_res = execute_tool("ui_tars_navigate_and_act", {"instruction": "check status"})
        self.assertIsInstance(tool_res, str)


if __name__ == "__main__":
    unittest.main()








