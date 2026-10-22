"""
SpaceV Telemetry HUD Diagnostic Monitor (Upgrade #49).
Cybernetic, translucent glassmorphism widget displaying real-time system metrics,
reflex routing latencies (<0.5ms), active model role, and perception state.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

try:
    import psutil
except Exception:
    psutil = None


class TelemetryHUD(QWidget):
    """
    Real-time Cybernetic Diagnostics HUD Widget.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(280)

        self._reflex_latency_ms: float = 0.18
        self._active_model_role: str = "FastRouter (C++ Needle)"
        self._companion_state: str = "IDLE (Cosmic Cyan)"

        self._init_ui()

        # Update timer: 1000ms polling for hardware metrics
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_metrics)
        self.timer.start(1000)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        # Glassmorphism container frame
        self.frame = QFrame(self)
        self.frame.setStyleSheet("""
            QFrame {
                background: rgba(13, 17, 23, 0.88);
                border: 1px solid rgba(0, 240, 255, 0.45);
                border-radius: 12px;
            }
        """)
        frame_layout = QVBoxLayout(self.frame)
        frame_layout.setContentsMargins(12, 10, 12, 10)
        frame_layout.setSpacing(6)

        # Header Title
        title_label = QLabel("⚡ SPACEV TELEMETRY HUD")
        title_label.setStyleSheet("color: #00F0FF; font-weight: bold; font-size: 11px; letter-spacing: 1px; border: none;")
        frame_layout.addWidget(title_label)

        # Metric Labels
        self.lbl_state = QLabel(f"STATE: {self._companion_state}")
        self.lbl_state.setStyleSheet("color: #E2E8F0; font-size: 10px; border: none;")
        frame_layout.addWidget(self.lbl_state)

        self.lbl_reflex = QLabel(f"REFLEX LATENCY: {self._reflex_latency_ms:.2f} ms")
        self.lbl_reflex.setStyleSheet("color: #FFB300; font-size: 10px; font-weight: bold; border: none;")
        frame_layout.addWidget(self.lbl_reflex)

        self.lbl_cpu = QLabel("CPU USAGE: 0.0 %")
        self.lbl_cpu.setStyleSheet("color: #A0AEC0; font-size: 10px; border: none;")
        frame_layout.addWidget(self.lbl_cpu)

        self.lbl_ram = QLabel("RAM USAGE: 0.0 %")
        self.lbl_ram.setStyleSheet("color: #A0AEC0; font-size: 10px; border: none;")
        frame_layout.addWidget(self.lbl_ram)

        self.lbl_model = QLabel(f"ROUTER: {self._active_model_role}")
        self.lbl_model.setStyleSheet("color: #A855F7; font-size: 10px; border: none;")
        frame_layout.addWidget(self.lbl_model)

        layout.addWidget(self.frame)

    def set_reflex_latency(self, latency_ms: float):
        self._reflex_latency_ms = latency_ms
        self.lbl_reflex.setText(f"REFLEX LATENCY: {self._reflex_latency_ms:.2f} ms")

    def set_companion_state(self, state: str):
        self._companion_state = state
        self.lbl_state.setText(f"STATE: {self._companion_state}")

    def refresh_metrics(self):
        try:
            if psutil:
                cpu = psutil.cpu_percent()
                ram = psutil.virtual_memory().percent
                self.lbl_cpu.setText(f"CPU USAGE: {cpu:.1f} %")
                self.lbl_ram.setText(f"RAM USAGE: {ram:.1f} %")
        except Exception:
            pass
