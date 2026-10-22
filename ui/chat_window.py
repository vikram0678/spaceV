"""
Modern Glassmorphic Chat Popup Window with Word Streaming, Voice Support,
and Proactive Companion Engine with Dynamic Follow-up Action Chips.
"""
from PyQt6.QtCore import QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QKeyEvent, QTextDocument, QWheelEvent
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QMenu, QPushButton, QScrollArea, QTextEdit, QVBoxLayout, QWidget

from config import (
    APP_NAME,
    AUTO_LISTEN_FOLLOWUP,
    CHAT_HEIGHT,
    CHAT_WIDTH,
    DEFAULT_CURSOR_SPEED,
    WAKE_WORD_ENABLED_BY_DEFAULT,
)
from core.agent_worker import AgentWorker
from core.ollama_client import OllamaAgent
from core.proactive_companion import ProactiveCompanion, companion_engine
from core.scheduler import scheduler
from tools.gui_tools import CURSOR_SPEED_PRESETS, safety
from ui.audio_effects import play_action_sound, play_emergency_sound, play_listening_sound
from ui.styles import MAIN_WINDOW_STYLE, get_agent_bubble_style, get_tool_card_style, get_user_bubble_style
from voice.dictation_manager import dictation_manager
from voice.frame_pipeline import frame_pipeline
from voice.stt_engine import VoiceListener
from voice.tts_engine import tts
from voice.wake_word import WakeWordDetector


class HorizontalWheelScrollArea(QScrollArea):
    """Translates vertical mouse wheel rotation into smooth horizontal scrolling for chips."""
    def wheelEvent(self, event: QWheelEvent):
        if event.angleDelta().y() != 0:
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - event.angleDelta().y()
            )
            event.accept()
        else:
            super().wheelEvent(event)



class ChatBubble(QLabel):
    """
    Precision Cybernetic Chat Bubble.
    Guarantees crisp typography, zero markdown text clipping,
    and adaptive wrapping for both agent and user messages.
    """
    def __init__(self, text: str, is_user: bool = False, max_width: int = 400, parent=None):
        super().__init__(parent)
        self.is_user = is_user
        self.max_width = max_width
        self.setTextFormat(Qt.TextFormat.MarkdownText)
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        font = QFont("-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif")
        font.setPixelSize(13)
        self.setFont(font)

        if is_user:
            self.setStyleSheet(get_user_bubble_style())
        else:
            self.setStyleSheet(get_agent_bubble_style())

        self.setContentsMargins(14, 10, 14, 12)
        self.update_geometry_for_text(text)

    def update_geometry_for_text(self, text: str):
        self.setText(text)
        doc = QTextDocument()
        doc.setDefaultFont(self.font())
        doc.setMarkdown(text)

        content_w = self.max_width - 28
        doc.setTextWidth(content_w)

        ideal = doc.idealWidth()
        needed_w = max(60, min(self.max_width, int(ideal) + 36))
        doc.setTextWidth(needed_w - 28)
        needed_h = int(doc.size().height()) + 26

        self.setFixedSize(needed_w, needed_h)


class ChatInput(QTextEdit):
    send_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setObjectName("ChatInput")
        self.setPlaceholderText("Ask SpaceV anything...")
        self.setFixedHeight(44)
        self.setCursorWidth(2)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            if tts.is_speaking:
                frame_pipeline.interrupt(reason="escape_key")
                event.accept()
                return
        if event.key() == Qt.Key.Key_Return and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.send_requested.emit()
            event.accept()
        else:
            super().keyPressEvent(event)

class ChatWindow(QWidget):
    state_changed = pyqtSignal(str) # "IDLE", "THINKING", "LISTENING", "SPEAKING"

    def __init__(self, agent: OllamaAgent):
        super().__init__()
        self.agent = agent
        self.current_worker = None
        self.current_stream_label = None
        self.voice_listener = None
        self.wake_detector = None
        self.drag_position = QPoint()
        self.last_tool_executed = ""
        self._pending_auto_listen = False

        # Connect TTS speech states using thread-safe Qt signals
        tts.speech_started.connect(self.on_speech_started)
        tts.speech_finished.connect(self.on_speech_finished)

        # Connect Scheduler Timer events
        scheduler.on_timer_expired = self.on_scheduler_timer_expired

        # Initialize Proactive Companion Engine
        self.companion = companion_engine
        self.companion.check_in_triggered.connect(self.on_companion_check_in)
        self.companion.start()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(CHAT_WIDTH, CHAT_HEIGHT)
        self.setStyleSheet(MAIN_WINDOW_STYLE)

        self.init_ui()

    def init_ui(self):
        # Outer Central Widget (for rounded border and shadow look)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)

        self.central_widget = QWidget()
        self.central_widget.setObjectName("CentralWidget")
        central_layout = QVBoxLayout(self.central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        # 1. Header Bar
        header = QWidget()
        header.setObjectName("HeaderBar")
        header.setFixedHeight(44)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 0, 10, 0)

        title = QLabel(f"⚡ {APP_NAME}")
        title.setObjectName("AppTitle")

        # Model Badge
        model_name = self.agent.model.split(":")[0]
        self.badge = QLabel(model_name.upper())
        self.badge.setObjectName("ModelBadge")
        self.agent.on_model_switched = self.on_model_switched

        header_layout.addWidget(title)
        header_layout.addSpacing(6)
        header_layout.addWidget(self.badge)

        header_layout.addStretch()

        # Minimize & Close Buttons
        btn_minimize = QPushButton("—")
        btn_minimize.setObjectName("HeaderMinimizeButton")
        btn_minimize.setToolTip("Minimize to floating bubble")
        btn_minimize.setFixedSize(28, 28)
        btn_minimize.clicked.connect(self.hide)

        btn_close = QPushButton("✕")
        btn_close.setObjectName("HeaderCloseButton")
        btn_close.setToolTip("Close chat window")
        btn_close.setFixedSize(28, 28)
        btn_close.clicked.connect(self.hide)

        header_layout.addWidget(btn_minimize)
        header_layout.addSpacing(4)
        header_layout.addWidget(btn_close)
        central_layout.addWidget(header)

        # 1.5 Toolbar (Cursor, Voice, Wake, Companion & Emergency Stop)
        toolbar = QWidget()
        toolbar.setObjectName("Toolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(8, 4, 8, 4)
        toolbar_layout.setSpacing(6)

        # Split Cursor Control Pill: [🤖 Cursor | ▾]
        cursor_container = QWidget()
        cursor_container.setObjectName("CursorContainer")
        cursor_layout = QHBoxLayout(cursor_container)
        cursor_layout.setContentsMargins(0, 0, 0, 0)
        cursor_layout.setSpacing(0)

        self.btn_cursor_toggle = QPushButton("🤖 Cursor")
        self.btn_cursor_toggle.setObjectName("CursorToggleBtn")
        self.btn_cursor_toggle.setProperty("active", "false")
        self.btn_cursor_toggle.setToolTip("Toggle autonomous mouse & keyboard control")
        self.btn_cursor_toggle.clicked.connect(self.toggle_cursor_mode)

        self.btn_cursor_speed = QPushButton("▾")
        self.btn_cursor_speed.setObjectName("CursorSpeedArrowBtn")
        self.btn_cursor_speed.setProperty("active", "false")
        self.btn_cursor_speed.setToolTip(f"Adjust cursor motion speed (Current: {DEFAULT_CURSOR_SPEED})")
        self.btn_cursor_speed.clicked.connect(self.show_cursor_speed_menu)

        cursor_layout.addWidget(self.btn_cursor_toggle)
        cursor_layout.addWidget(self.btn_cursor_speed)

        self.btn_voice_toggle = QPushButton("🔊 Voice")
        self.btn_voice_toggle.setObjectName("VoiceToggleBtn")
        self.btn_voice_toggle.setProperty("active", "true")
        self.btn_voice_toggle.setToolTip("Toggle spoken voice responses (TTS)")
        self.btn_voice_toggle.clicked.connect(self.toggle_voice)

        self.btn_wake_toggle = QPushButton("🎙️ Wake")
        self.btn_wake_toggle.setObjectName("WakeToggleBtn")
        self.btn_wake_toggle.setProperty("active", "true" if WAKE_WORD_ENABLED_BY_DEFAULT else "false")
        self.btn_wake_toggle.setToolTip("Toggle continuous hands-free 'Hey SpaceV' wake-word detection")
        self.btn_wake_toggle.clicked.connect(self.toggle_wake_word)

        self.btn_companion_toggle = QPushButton("💬 Companion")
        self.btn_companion_toggle.setObjectName("CompanionToggleBtn")
        self.btn_companion_toggle.setProperty("active", "true")
        self.btn_companion_toggle.setToolTip("Toggle proactive companion check-ins & conversational follow-ups")
        self.btn_companion_toggle.clicked.connect(self.toggle_companion_mode)

        self.btn_emergency_stop = QPushButton("🛑 Stop")
        self.btn_emergency_stop.setObjectName("EmergencyStopBtn")
        self.btn_emergency_stop.setToolTip("Immediately stop autonomous action (or press ESC)")
        self.btn_emergency_stop.clicked.connect(self.emergency_stop)

        toolbar_layout.addWidget(cursor_container)
        toolbar_layout.addWidget(self.btn_voice_toggle)
        toolbar_layout.addWidget(self.btn_wake_toggle)
        toolbar_layout.addWidget(self.btn_companion_toggle)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.btn_emergency_stop)
        central_layout.addWidget(toolbar)

        # 2. Scrollable Messages Area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")

        self.messages_container = QWidget()
        self.messages_container.setObjectName("MessagesContainer")
        self.messages_container.setStyleSheet("background: transparent;")
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.setContentsMargins(14, 14, 14, 14)
        self.messages_layout.setSpacing(10)
        self.messages_layout.addStretch()

        self.scroll_area.setWidget(self.messages_container)
        central_layout.addWidget(self.scroll_area, 1)

        # 2.5 Quick Action Command Chips Bar
        chips_container = QWidget()
        chips_container.setObjectName("ChipsContainer")
        chips_container.setFixedHeight(38)
        chips_scroll = HorizontalWheelScrollArea()
        chips_scroll.setFixedHeight(38)
        chips_scroll.setWidgetResizable(True)
        chips_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        chips_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        chips_scroll.setStyleSheet("background: transparent; border: none;")

        chips_widget = QWidget()
        chips_widget.setStyleSheet("background: transparent;")
        chips_layout = QHBoxLayout(chips_widget)
        chips_layout.setContentsMargins(4, 0, 4, 0)
        chips_layout.setSpacing(6)

        quick_actions = [
            ("🎨 Draw in Paint", "draw a house in paint"),
            ("🎙️ Dictate Text", "activate dictation mode"),
            ("💻 Coding Mode", "activate coding mode"),
            ("🧹 Clean RAM", "clean ram"),
            ("⏱️ 5m Timer", "set a timer for 5 minutes"),
            ("🔒 Lock PC", "lock screen"),
            ("🌤️ Weather", "what is the weather?"),
            ("💼 Tech Jobs", "scrape python remote jobs and save to desktop"),
            ("⚡ Diagnostics", "system stats"),
            ("🎵 Next Song", "next song"),
        ]

        for label, cmd in quick_actions:
            btn = QPushButton(label)
            btn.setObjectName("QuickChipBtn")
            btn.clicked.connect(lambda _, c=cmd: self.send_quick_command(c))
            chips_layout.addWidget(btn)

        chips_scroll.setWidget(chips_widget)
        chips_layout_outer = QVBoxLayout(chips_container)
        chips_layout_outer.setContentsMargins(0, 0, 0, 0)
        chips_layout_outer.addWidget(chips_scroll)
        central_layout.addWidget(chips_container)

        # 3. Status Bar (Thinking / Action status indicator)
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #8b949e; font-size: 11px; padding: 2px 14px;")
        self.status_label.hide()
        central_layout.addWidget(self.status_label)

        # 4. Input Container Bar
        input_container = QWidget()
        input_container.setObjectName("InputContainer")
        input_container.setFixedHeight(60)
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(10, 8, 10, 8)
        input_layout.setSpacing(8)

        self.input_edit = ChatInput()
        self.input_edit.send_requested.connect(self.send_message)

        self.btn_mic = QPushButton("🎤")
        self.btn_mic.setObjectName("MicButton")
        self.btn_mic.setFixedHeight(44)
        self.btn_mic.setToolTip("Click to talk using your microphone")
        self.btn_mic.clicked.connect(self.toggle_mic_listening)

        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("SendButton")
        self.send_button.setFixedHeight(44)
        self.send_button.clicked.connect(self.send_message)

        input_layout.addWidget(self.input_edit)
        input_layout.addWidget(self.btn_mic)
        input_layout.addWidget(self.send_button)
        central_layout.addWidget(input_container)

        main_layout.addWidget(self.central_widget)

        # Hands-free wake-word detector is OFF by default; starts only if explicitly enabled
        self.wake_detector = None
        if WAKE_WORD_ENABLED_BY_DEFAULT:
            self.init_wake_detector()

    def play_initial_greeting(self):
        """Proactively speaks and displays a warm companion greeting upon startup."""
        greeting = "Hello Sir! This is SpaceV. How was your day? Is there anything I can assist you with today?"
        chips = [
            ("⚡ System Stats", "system stats"),
            ("🎵 Focus Beats", "play lofi beats on youtube"),
            ("📰 Tech News", "fetch top technology news headlines"),
        ]
        self.add_agent_message(
            f"⚡ **SpaceV Online**:\n\n{greeting}\n\n"
            "* Press `Ctrl + Space` or click `🎤` to speak\n"
            "* Say **'Hey SpaceV'** anytime for hands-free mode",
            custom_chips=chips
        )
        self._pending_auto_listen = True
        tts.speak(greeting)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def dock_near(self, point: QPoint):
        """Positions chat window nicely relative to the floating icon."""
        screen = self.screen().geometry()
        x = point.x() - self.width() + 40
        y = point.y() - self.height() - 10

        if x < 20:
            x = point.x() + 80
        if y < 20:
            y = 20
        self.move(x, y)

    def send_message(self):
        text = self.input_edit.toPlainText().strip()
        if not text:
            return

        # Instant speech barge-in via Pipecat Interruption Protocol
        frame_pipeline.interrupt(reason="new_message_barge_in")
        self.companion.record_activity()
        self.last_tool_executed = ""
        self._pending_auto_listen = False

        self.input_edit.clear()
        self.add_user_message(text)
        self.state_changed.emit("THINKING")

        # Reset streaming label
        self.current_stream_label = None

        # Disable input while processing
        self.send_button.setEnabled(False)
        self.status_label.setText("⚡ SpaceV is analyzing & executing...")
        self.status_label.show()

        # Run in background QThread
        self.current_worker = AgentWorker(self.agent, text)
        self.current_worker.token_received.connect(self.on_token_received)
        self.current_worker.tool_event.connect(self.on_tool_event)
        self.current_worker.response_ready.connect(self.on_response_ready)
        self.current_worker.error_occurred.connect(self.on_error)
        self.current_worker.start()

    def on_token_received(self, token: str):
        if self.current_stream_label is None:
            self.create_streaming_bubble()
        current_text = self.current_stream_label.text()
        new_text = current_text + token
        self.current_stream_label.update_geometry_for_text(new_text)
        self.scroll_to_bottom()

    def create_streaming_bubble(self):
        msg_wrapper = QHBoxLayout()
        msg_wrapper.setContentsMargins(0, 0, 0, 0)

        max_w = int(CHAT_WIDTH * 0.85)
        bubble = ChatBubble("", is_user=False, max_width=max_w)

        msg_wrapper.addWidget(bubble)
        msg_wrapper.addStretch()
        self.messages_layout.addWidget(self._wrap_layout(msg_wrapper))
        self.current_stream_label = bubble

    def on_tool_event(self, tool_name: str, status: str, details: str):
        if status == "running":
            self.status_label.setText(f"⚙️ Executing tool: {tool_name}...")
        else:
            self.last_tool_executed = tool_name
            play_action_sound()
            self.add_tool_card(tool_name, details)
            self.status_label.setText("⚡ Streaming response...")

    def on_response_ready(self, response_text: str):
        self.status_label.hide()
        self.send_button.setEnabled(True)
        self.companion.record_activity()

        executed_tool = self.last_tool_executed
        if self.current_stream_label is None:
            self.add_agent_message(response_text, tool_name=executed_tool)
        else:
            # Append dynamic follow-up chips below the finished streaming bubble
            chips = ProactiveCompanion.get_follow_up_chips(tool_name=executed_tool, reply_text=response_text)
            self._render_follow_up_chips(chips)

        self.current_stream_label = None
        self.last_tool_executed = ""
        self.input_edit.setFocus()

        if executed_tool == "dictation_mode":
            # Auto-activate desktop dictation after short delay
            QTimer.singleShot(600, self.start_desktop_dictation)

        # Check if SpaceV asked a follow-up question -> Prepare Auto-Listen
        if AUTO_LISTEN_FOLLOWUP and tts.is_enabled and self.companion.is_enabled:
            lower = response_text.lower()
            if "?" in response_text or "shall i" in lower or "would you like" in lower or "what" in lower:
                self._pending_auto_listen = True

        if not tts.is_speaking:
            self.state_changed.emit("IDLE")

    def on_speech_started(self):
        self.state_changed.emit("SPEAKING")
        # Keep wake_detector running with AEC so user speech can trigger conversational barge-in

    def on_speech_finished(self):
        self.state_changed.emit("IDLE")
        # Continuous Conversational Loop (Google Assistant / Siri Style)
        if AUTO_LISTEN_FOLLOWUP and self.wake_detector and self.wake_detector.isRunning():
            QTimer.singleShot(250, lambda: self.wake_detector.start_conversational_turn(timeout_sec=7.5))
        elif self._pending_auto_listen and self.companion.is_enabled:
            self._pending_auto_listen = False
            QTimer.singleShot(400, self.toggle_mic_listening)

    def on_error(self, error_message: str):
        self.status_label.hide()
        self.send_button.setEnabled(True)
        self.current_stream_label = None
        self.state_changed.emit("IDLE")
        self.add_agent_message(f"⚠️ Error: {error_message}")
        self.input_edit.setFocus()

    def add_user_message(self, text: str):
        msg_wrapper = QHBoxLayout()
        msg_wrapper.setContentsMargins(0, 0, 0, 0)
        msg_wrapper.addStretch()

        max_w = int(CHAT_WIDTH * 0.80)
        bubble = ChatBubble(text, is_user=True, max_width=max_w)

        msg_wrapper.addWidget(bubble)
        self.messages_layout.addWidget(self._wrap_layout(msg_wrapper))
        self.scroll_to_bottom()

    def add_agent_message(self, text: str, tool_name: str = "", custom_chips: list = None):
        msg_wrapper = QHBoxLayout()
        msg_wrapper.setContentsMargins(0, 0, 0, 0)

        max_w = int(CHAT_WIDTH * 0.85)
        bubble = ChatBubble(text, is_user=False, max_width=max_w)

        msg_wrapper.addWidget(bubble)
        msg_wrapper.addStretch()
        self.messages_layout.addWidget(self._wrap_layout(msg_wrapper))

        # Add dynamic interactive follow-up chips below message
        is_custom = custom_chips is not None
        chips = custom_chips if is_custom else ProactiveCompanion.get_follow_up_chips(tool_name=tool_name, reply_text=text)
        is_clarification = is_custom or any(k in text.lower() for k in ["who's using chrome", "which profile", "select a profile", "clarification"])
        self._render_follow_up_chips(chips, is_explicit=is_clarification)

        self.scroll_to_bottom()

    def _render_follow_up_chips(self, chips: list, is_explicit: bool = False):
        if not chips:
            return
        if not is_explicit and not self.companion.is_enabled:
            return

        chips_row = QHBoxLayout()
        chips_row.setContentsMargins(8, 2, 8, 4)
        chips_row.setSpacing(6)

        for chip_label, chip_cmd in chips[:3]:
            chip_btn = QPushButton(chip_label)
            chip_btn.setObjectName("DynamicFollowUpChip")
            chip_btn.setToolTip(f"Click to send: '{chip_cmd}'")
            chip_btn.clicked.connect(lambda _, c=chip_cmd: self.send_quick_command(c))
            chips_row.addWidget(chip_btn)

        chips_row.addStretch()
        self.messages_layout.addWidget(self._wrap_layout(chips_row))

    def add_tool_card(self, tool_name: str, result: str):
        card_wrapper = QHBoxLayout()
        card_wrapper.setContentsMargins(0, 0, 0, 0)

        card = QLabel(f"⚡ [Action: {tool_name}]\n{result}")
        card.setWordWrap(True)
        card.setMaximumWidth(int(CHAT_WIDTH * 0.85))
        card.setStyleSheet(get_tool_card_style())
        card.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        card_wrapper.addWidget(card)
        card_wrapper.addStretch()
        self.messages_layout.addWidget(self._wrap_layout(card_wrapper))
        self.scroll_to_bottom()

    def _wrap_layout(self, layout) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent; border: none;")
        w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        w.setLayout(layout)
        return w

    def toggle_cursor_mode(self):
        safety.autonomous_mode_enabled = not safety.autonomous_mode_enabled
        if safety.autonomous_mode_enabled:
            self.btn_cursor_toggle.setText("🤖 Cursor")
            self.btn_cursor_toggle.setProperty("active", "true")
            self.btn_cursor_speed.setProperty("active", "true")
            self.add_agent_message("🤖 **Autonomous Cursor Mode Enabled**!\nSpaceV will move the cursor and type like a human for UI commands.\n\n🛡️ **Emergency Stop**: Press `ESC` or shove cursor to top-left corner anytime to halt!")
        else:
            self.btn_cursor_toggle.setText("🤖 Cursor")
            self.btn_cursor_toggle.setProperty("active", "false")
            self.btn_cursor_speed.setProperty("active", "false")
            self.add_agent_message("🤖 Autonomous Cursor Mode Disabled. Reverted to standard background automation.")

        self.btn_cursor_toggle.style().unpolish(self.btn_cursor_toggle)
        self.btn_cursor_toggle.style().polish(self.btn_cursor_toggle)
        self.btn_cursor_speed.style().unpolish(self.btn_cursor_speed)
        self.btn_cursor_speed.style().polish(self.btn_cursor_speed)

    def show_cursor_speed_menu(self):
        menu = QMenu(self)
        menu.setObjectName("CursorSpeedMenu")
        for key, preset in CURSOR_SPEED_PRESETS.items():
            action = menu.addAction(preset["label"])
            action.setCheckable(True)
            if key == safety.current_speed:
                action.setChecked(True)
            action.triggered.connect(lambda checked, k=key: self.select_cursor_speed(k))

        btn_pos = self.btn_cursor_speed.mapToGlobal(QPoint(0, self.btn_cursor_speed.height() + 2))
        menu.exec(btn_pos)

    def select_cursor_speed(self, speed_key: str):
        if speed_key:
            safety.set_cursor_speed(speed_key)
            preset = CURSOR_SPEED_PRESETS.get(speed_key, {})
            label = preset.get("label", speed_key)
            self.btn_cursor_speed.setToolTip(f"Adjust cursor motion speed (Current: {speed_key})")
            play_action_sound()
            self.add_agent_message(f"⚡ **Cursor Speed Profile Updated**: `{label}` activated.")

    def toggle_voice(self):
        tts.is_enabled = not tts.is_enabled
        if tts.is_enabled:
            self.btn_voice_toggle.setText("🔊 Voice")
            self.btn_voice_toggle.setProperty("active", "true")
            tts.speak("Voice enabled. I am listening and ready to assist you.")
            self.add_agent_message("🔊 **Voice Mode Activated**! SpaceV will now speak responses aloud.")
        else:
            self.btn_voice_toggle.setText("🔇 Voice")
            self.btn_voice_toggle.setProperty("active", "false")
            tts.stop()
            self.add_agent_message("🔇 **Voice Mode Muted**.")

        self.btn_voice_toggle.style().unpolish(self.btn_voice_toggle)
        self.btn_voice_toggle.style().polish(self.btn_voice_toggle)

    def toggle_companion_mode(self):
        self.companion.set_enabled(not self.companion.is_enabled)
        if self.companion.is_enabled:
            self.btn_companion_toggle.setText("💬 Companion")
            self.btn_companion_toggle.setProperty("active", "true")
            self.add_agent_message("💬 **Proactive Companion Mode Activated**! SpaceV will actively suggest next steps, provide interactive action chips, and check in during your work.")
        else:
            self.btn_companion_toggle.setText("💬 Companion")
            self.btn_companion_toggle.setProperty("active", "false")
            self.add_agent_message("💬 **Companion Mode Muted** (Standard on-demand response mode).")

        self.btn_companion_toggle.style().unpolish(self.btn_companion_toggle)
        self.btn_companion_toggle.style().polish(self.btn_companion_toggle)

    def on_companion_check_in(self, prompt_text: str, chips: list):
        """Triggered by the background ProactiveCompanion during session idle."""
        self.show()
        self.raise_()
        play_action_sound()
        self.add_agent_message(f"💬 **SpaceV Check-In**:\n\n{prompt_text}", custom_chips=chips)
        tts.speak(prompt_text)

    def emergency_stop(self):
        play_emergency_sound()
        safety.abort()
        frame_pipeline.interrupt(reason="emergency_stop")
        self._pending_auto_listen = False
        self.state_changed.emit("IDLE")
        self.status_label.setText("🚨 EMERGENCY STOP TRIGGERED!")
        self.status_label.show()
        self.send_button.setEnabled(True)
        self.add_agent_message("🚨 **EMERGENCY STOP TRIGGERED**\nAll autonomous cursor and keyboard actions have been halted immediately.")

    def clear_conversation(self):
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.agent.reset_conversation()
        self.add_agent_message("Conversation cleared. Ready for your next command!")

    def toggle_mic_listening(self):
        # 1. Stop active audio via Pipecat Interruption Protocol
        frame_pipeline.interrupt(reason="mic_activated")
        self.companion.record_activity()

        # If conversational wake engine is running, start conversational turn directly
        if self.wake_detector and self.wake_detector.isRunning():
            self.wake_detector.start_conversational_turn(timeout_sec=8.5)
            return

        listener = getattr(self, "voice_listener", None)
        if listener is not None and listener.isRunning():
            listener.stop()
            self.on_listening_finished()
            return

        if self.wake_detector and hasattr(self.wake_detector, "pause"):
            self.wake_detector.pause()

        self.voice_listener = VoiceListener()
        self.voice_listener.listening_started.connect(self.on_listening_started)
        self.voice_listener.speech_recognized.connect(self.on_speech_recognized)
        self.voice_listener.listening_finished.connect(self.on_listening_finished)
        self.voice_listener.error_occurred.connect(self.on_mic_error)
        self.voice_listener.start()

    def start_desktop_dictation(self):
        """
        Activates desktop dictation mode:
        Captures speech via Silero VAD, transcribes via Faster-Whisper,
        and injects directly into the active focused window.
        """
        frame_pipeline.interrupt(reason="dictation_activated")
        self.companion.record_activity()
        if self.wake_detector and hasattr(self.wake_detector, "pause"):
            self.wake_detector.pause()

        play_listening_sound()
        self.state_changed.emit("LISTENING")
        self.btn_mic.setText("🎙️...")
        self.btn_mic.setProperty("listening", "true")
        self.btn_mic.style().unpolish(self.btn_mic)
        self.btn_mic.style().polish(self.btn_mic)
        self.status_label.setText("🎙️ Dictation Active... Speak clearly (will paste into focused app)")
        self.status_label.show()

        def _cleanup():
            self.btn_mic.setText("🎤")
            self.btn_mic.setProperty("listening", "false")
            self.btn_mic.style().unpolish(self.btn_mic)
            self.btn_mic.style().polish(self.btn_mic)
            if self.wake_detector and hasattr(self.wake_detector, "resume"):
                self.wake_detector.resume()
            self.state_changed.emit("IDLE")

        def _on_success(text: str):
            _cleanup()
            self.status_label.setText("⚡ Dictated text injected!")
            QTimer.singleShot(2500, self.status_label.hide)
            self.add_agent_message(
                f"🎙️ **Transcribed & Injected**:\n\n> \"{text}\"\n\n*Pasted directly into your focused application.*",
                tool_name="dictation_mode"
            )

        def _on_error(err: str):
            _cleanup()
            self.status_label.setText(f"🎙️ Dictation notice: {err}")
            QTimer.singleShot(3000, self.status_label.hide)

        # Disconnect any prior callbacks to prevent duplicate signal firings
        try:
            dictation_manager.dictation_finished.disconnect()
        except Exception:
            pass
        try:
            dictation_manager.dictation_error.disconnect()
        except Exception:
            pass

        dictation_manager.dictation_finished.connect(_on_success)
        dictation_manager.dictation_error.connect(_on_error)
        dictation_manager.start_dictation()

    def on_listening_started(self):
        play_listening_sound()
        self.state_changed.emit("LISTENING")
        self.btn_mic.setText("🎙️...")
        self.btn_mic.setProperty("listening", "true")
        self.btn_mic.style().unpolish(self.btn_mic)
        self.btn_mic.style().polish(self.btn_mic)
        self.status_label.setText("🎙️ Listening to your microphone... (Speak now)")
        self.status_label.show()

    def on_speech_recognized(self, text: str):
        self.input_edit.setText(text)
        self.send_message()

    def on_listening_finished(self):
        self.btn_mic.setText("🎤")
        self.btn_mic.setProperty("listening", "false")
        self.btn_mic.style().unpolish(self.btn_mic)
        self.btn_mic.style().polish(self.btn_mic)

        # Resume background wake-word listener
        if self.wake_detector and hasattr(self.wake_detector, "resume"):
            self.wake_detector.resume()

        self.companion.record_activity()
        worker = getattr(self, "current_worker", None)
        if not (worker and worker.isRunning()):
            self.status_label.hide()
            if not tts.is_speaking:
                self.state_changed.emit("IDLE")

    def on_mic_error(self, err_msg: str):
        if self.wake_detector and hasattr(self.wake_detector, "resume"):
            self.wake_detector.resume()
        self.status_label.hide()
        self.state_changed.emit("IDLE")
        self.add_agent_message(f"🎙️ *Microphone*: {err_msg}")

    def init_wake_detector(self):
        try:
            self.wake_detector = WakeWordDetector()
            self.wake_detector.wake_word_detected.connect(self.on_wake_word_triggered)
            self.wake_detector.command_detected.connect(self.on_wake_command_triggered)
            self.wake_detector.listening_state_changed.connect(self.on_conversational_state_changed)
            self.wake_detector.start()
        except Exception as e:
            print(f"[ChatWindow] Wake detector init notice: {e}")

    def on_conversational_state_changed(self, state: str):
        if state == "LISTENING":
            self.state_changed.emit("LISTENING")
            self.btn_mic.setText("🎙️...")
            self.btn_mic.setProperty("listening", "true")
            self.btn_mic.style().unpolish(self.btn_mic)
            self.btn_mic.style().polish(self.btn_mic)
            self.status_label.setText("🎙️ SpaceV is listening... (Speak naturally)")
            self.status_label.show()
        elif state == "STANDBY":
            self.btn_mic.setText("🎤")
            self.btn_mic.setProperty("listening", "false")
            self.btn_mic.style().unpolish(self.btn_mic)
            self.btn_mic.style().polish(self.btn_mic)
            worker = getattr(self, "current_worker", None)
            if not (worker and worker.isRunning()) and not tts.is_speaking:
                self.status_label.hide()
                self.state_changed.emit("IDLE")

    def toggle_wake_word(self):
        if self.wake_detector and self.wake_detector.isRunning():
            self.wake_detector.stop()
            self.wake_detector = None
            self.btn_wake_toggle.setText("🎙️ Wake")
            self.btn_wake_toggle.setProperty("active", "false")
            self.add_agent_message("🎙️ **Hands-Free Wake-Word Disabled**.")
        else:
            self.init_wake_detector()
            self.btn_wake_toggle.setText("🎙️ Wake")
            self.btn_wake_toggle.setProperty("active", "true")
            self.add_agent_message("🎙️ **Hands-Free Wake-Word Enabled**! Say **'Hey SpaceV'** anytime to speak.")

        self.btn_wake_toggle.style().unpolish(self.btn_wake_toggle)
        self.btn_wake_toggle.style().polish(self.btn_wake_toggle)

    def on_wake_word_triggered(self):
        self.show()
        self.raise_()
        self.activateWindow()
        self.toggle_mic_listening()

    def on_wake_command_triggered(self, cmd: str):
        self.show()
        self.raise_()
        self.activateWindow()

        clean = cmd.strip().lower()
        if clean in ["stop", "cancel", "shut up", "be quiet", "pause", "never mind", "halt"]:
            from voice.frame_pipeline import frame_pipeline
            frame_pipeline.interrupt(reason="user_stop_command")
            worker = getattr(self, "current_worker", None)
            if worker and worker.isRunning():
                worker.abort()
            tts.stop()
            self.state_changed.emit("IDLE")
            self.status_label.hide()
            self.add_agent_message("🛑 **Stopped**. Standing by, Sir.")
            tts.speak("Stopped, Sir.")
            return

        # Immediate Conversational Barge-In: if SpaceV is speaking or thinking, abort previous turn
        if tts.is_speaking or (getattr(self, "current_worker", None) and self.current_worker.isRunning()):
            from voice.frame_pipeline import frame_pipeline
            frame_pipeline.interrupt(reason="conversational_barge_in")
            worker = getattr(self, "current_worker", None)
            if worker and worker.isRunning():
                worker.abort()
            tts.stop()

        play_action_sound()
        self.input_edit.setText(cmd)
        self.send_message()

    def send_quick_command(self, cmd_text: str):
        if cmd_text == "activate dictation mode":
            self.add_user_message("activate dictation mode")
            self.add_agent_message(
                "🎙️ **Desktop Dictation Activated**. Speak clearly—your words will be typed directly into your focused application.",
                tool_name="dictation_mode"
            )
            self.start_desktop_dictation()
            return
        self.input_edit.setText(cmd_text)
        self.send_message()

    def on_scheduler_timer_expired(self, label: str, duration: float):
        play_action_sound()
        alert_text = f"⏰ **COUNTDOWN TIMER EXPIRED**\n\nYour timer for **'{label}'** ({int(duration)}s) has finished, Sir!"
        self.add_agent_message(alert_text, tool_name="set_timer")
        tts.speak(f"Sir, your timer for {label} has finished.")

    def on_model_switched(self, model_name: str, role: str):
        """Dynamically updates the active model badge in the window header."""
        display_name = model_name.split(":")[0].upper()
        if hasattr(self, 'badge'):
            self.badge.setText(display_name)

    def scroll_to_bottom(self):
        QTimer.singleShot(50, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        ))

    def cleanup(self):
        """Stops background threads and releases audio hardware before exit."""
        try:
            if self.wake_detector:
                self.wake_detector.stop()
            if self.voice_listener:
                self.voice_listener.stop()
            if self.companion:
                self.companion.stop()
            tts.shutdown()
        except Exception:
            pass


