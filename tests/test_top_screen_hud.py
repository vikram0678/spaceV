"""
Unit Tests for SpaceV Iron-Man Cybernetic Top-Screen HUD Ribbon.
Verifies positioning, phase styling, action card expansion, and signal dispatch.
"""
from PyQt6.QtWidgets import QApplication
import pytest

@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["pytest", "-platform", "offscreen"])
    return app


def test_top_screen_hud_geometry_and_docking(qapp):
    from ui.top_screen_hud import TopScreenHUD
    hud = TopScreenHUD()
    hud.init_position()

    screen = qapp.primaryScreen().availableGeometry()
    # Must be docked at the top center of screen
    assert hud.pos().y() <= 30
    center_x = hud.pos().x() + hud.width() // 2
    screen_center_x = screen.x() + screen.width() // 2
    assert abs(center_x - screen_center_x) < 25, f"HUD center ({center_x}) should match screen center ({screen_center_x})"
    hud.deleteLater()


def test_top_screen_hud_phase_and_action_card_expansion(qapp):
    from ui.top_screen_hud import TopScreenHUD
    hud = TopScreenHUD()
    hud.show()

    # Update phase to HARVESTING
    hud.update_phase("HARVESTING", "Harvesting top AI engineer listings")
    assert "[ HARVESTING ]" in hud.phase_pill.text()
    assert "Harvesting top AI engineer" in hud.status_label.text()

    # Expand action card
    test_urls = ["https://example.com/job1", "https://example.com/job2"]
    hud.show_action_card("Job Listings", "Found 2 matching roles", urls=test_urls)
    assert hud._is_expanded is True
    assert hud.card_frame.isVisible() is True
    assert hud.btn_primary_action.isVisible() is True

    # Dismiss card
    hud.hide_action_card()
    assert hud._is_expanded is False
    assert hud.card_frame.isHidden() is True
    hud.deleteLater()


def test_top_screen_hud_signals(qapp):
    from ui.top_screen_hud import TopScreenHUD
    hud = TopScreenHUD()

    chat_called = False
    def on_chat():
        nonlocal chat_called
        chat_called = True

    hud.chat_requested.connect(on_chat)
    hud.btn_chat.click()
    assert chat_called is True

    urls_received = []
    def on_urls(urls):
        nonlocal urls_received
        urls_received = urls

    hud.open_urls_requested.connect(on_urls)
    hud.show_action_card("Jobs", "Testing URLs", urls=["https://turing.com/1", "https://turing.com/2"])
    hud.btn_primary_action.click()
    assert urls_received == ["https://turing.com/1", "https://turing.com/2"]

    hud.deleteLater()
