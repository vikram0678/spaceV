import os
import sys
from unittest.mock import MagicMock, patch
import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Mock audio stream to prevent contention with running agent
mock_stream = MagicMock()
mock_stream.is_running = False
mock_stream.read_chunk.return_value = b"\x00" * 1024
sys.modules["voice.audio_stream"] = MagicMock(audio_stream=mock_stream)

from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QApplication

@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["pytest", "-platform", "offscreen"])
    return app

def test_qt_platform_initialization(qapp):
    """Verify that QApplication initializes a valid platform plugin."""
    assert qapp.platformName() in ("wayland", "offscreen", "xcb")

def test_floating_icon_bottom_right_positioning(qapp):
    """Verify that FloatingIcon positions in the bottom-right corner of available screen."""
    from ui.floating_icon import FloatingIcon
    icon = FloatingIcon()
    icon.init_position()

    pos = icon.pos()
    assert pos.x() > 500, f"Icon x ({pos.x()}) should be towards the right"
    assert pos.y() > 300, f"Icon y ({pos.y()}) should be towards the bottom"
    icon.deleteLater()

def test_chat_window_dock_near_directly_above(qapp):
    """Verify that ChatWindow.dock_near docks directly above the floating icon."""
    with patch("core.proactive_companion.companion_engine.start"):
        from ui.chat_window import ChatWindow
        agent_mock = MagicMock()
        agent_mock.model = "qwen2.5:3b"
        chat = ChatWindow(agent_mock)

        screen = qapp.primaryScreen().availableGeometry()
        icon_pos = QPoint(screen.width() - 100, screen.height() - 100)
        chat.dock_near(icon_pos)

        chat_pos = chat.pos()
        # The chat window must be positioned strictly above the floating icon
        assert chat_pos.y() < icon_pos.y(), "Chat window must be positioned ABOVE the floating icon"
        assert chat_pos.y() + chat.height() <= icon_pos.y(), "Chat window bottom must not overlap or go below the icon"
        # In any screen resolution, it must clamp to the right edge (within 20px margin)
        expected_right_x = screen.x() + screen.width() - chat.width() - 20
        assert chat_pos.x() == expected_right_x, f"Chat window ({chat_pos.x()}) should be at right clamp {expected_right_x}"
        chat.deleteLater()

def test_toggle_chat_visibility_minimize_maximize(qapp):
    """Verify that clicking toggle hides when visible, and docks & restores when hidden."""
    with patch("core.proactive_companion.companion_engine.start"):
        from ui.chat_window import ChatWindow
        from ui.floating_icon import FloatingIcon

        agent_mock = MagicMock()
        agent_mock.model = "qwen2.5:3b"
        chat = ChatWindow(agent_mock)
        icon = FloatingIcon()

        def toggle():
            if chat.isVisible():
                chat.hide()
            else:
                chat.dock_near(icon.pos())
                chat.show()

        # Initially hidden
        assert not chat.isVisible()

        # Click 1: Show / Maximize
        toggle()
        assert chat.isVisible()

        # Click 2: Hide / Minimize
        toggle()
        assert not chat.isVisible()

        # Click 3: Re-show / Restore
        toggle()
        assert chat.isVisible()

        chat.deleteLater()
        icon.deleteLater()
