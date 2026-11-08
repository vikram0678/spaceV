"""
Test Suite for SpaceV Universal Roadblock & Modal Disambiguation Engine.
Verifies:
1. Zero hardcoded developer names across the entire disambiguation engine.
2. Dynamic discovery of Chrome profiles on any machine.
3. Universal OS Gatekeeper handling:
   - Windows File Explorer file conflict (Replace/Skip/Keep Both)
   - VS Code Workspace Trust prompt (Trust/Deny)
   - Unsaved changes confirmation dialogs (Save/Don't Save/Cancel)
   - Generic Win32 (#32770) dialogs with dynamic child button enumeration
4. Holographic Visor (Amber/Yellow layer) visual targeting reticle & attention banner.
5. Strict "Ask ONLY when confused or blocked" principle: 100% silent when clear.
"""
from unittest.mock import MagicMock, patch
import pytest

from core.modal_interceptor import GatekeeperModal, UniversalModalInterceptor
from core.fast_router import FastRouter
from core.memory import memory


@pytest.fixture(autouse=True)
def clean_memory_state():
    """Ensure clean memory before and after each test."""
    memory.clear_suspended_disambiguation()
    yield
    memory.clear_suspended_disambiguation()


def test_zero_hardcoded_developer_identities_in_engine_code():
    """Verify core engine files contain zero personal developer names (vikram, vicky)."""
    target_files = [
        "core/modal_interceptor.py",
        "core/fast_router.py",
        "core/proactive_companion.py"
    ]
    for rel_path in target_files:
        with open(rel_path, "r", encoding="utf-8") as f:
            content = f.read().lower()
        # Verify no hardcoded strings for 'vikram' or 'vicky'
        assert "vikram" not in content, f"Hardcoded 'vikram' found in {rel_path}"
        assert "vicky" not in content, f"Hardcoded 'vicky' found in {rel_path}"


def test_silent_execution_when_desktop_is_clear():
    """Verify detect() returns None and asks ZERO questions for normal app windows."""
    interceptor = UniversalModalInterceptor()

    # Normal Google Chrome window (active web browsing)
    with patch.object(interceptor, "inspect_active_window", return_value=("Smart India Hackathon 2026 - Google Chrome", "chrome", "Chrome_WidgetWin_1")):
        modal = interceptor.detect()
        assert modal is None, "Normal browser window should not trigger a roadblock!"

    # Normal VS Code window
    with patch.object(interceptor, "inspect_active_window", return_value=("main.py - agentSpace - Visual Studio Code", "vscode", "Chrome_WidgetWin_1")):
        modal = interceptor.detect()
        assert modal is None, "Normal VS Code window should not trigger a roadblock!"

    # Normal Notepad window
    with patch.object(interceptor, "inspect_active_window", return_value=("Untitled - Notepad", "notepad", "Notepad")):
        modal = interceptor.detect()
        assert modal is None, "Normal Notepad window should not trigger a roadblock!"


def test_chrome_profile_picker_triggers_only_when_multiple_profiles_and_no_preference():
    """Verify profile disambiguation asks only when multiple profiles exist and no choice is stored."""
    interceptor = UniversalModalInterceptor()

    mock_profiles = [
        {"id": "Default", "display": "Work Account", "name": "Work", "email": "work@corp.com"},
        {"id": "Profile 2", "display": "Personal Account", "name": "Personal", "email": "me@home.com"}
    ]

    with patch.object(interceptor, "inspect_active_window", return_value=("Who's using Chrome?", "chrome", "Chrome_WidgetWin_1")), \
         patch("core.modal_interceptor.get_detected_chrome_profiles", return_value=mock_profiles), \
         patch("core.memory.memory.get", return_value=None), \
         patch("core.memory.memory.get_preference", return_value=None):
        modal = interceptor.detect()
        assert modal is not None
        assert modal.domain == "chrome"
        assert modal.property_key == "profile"
        assert "Who's using Chrome?" in modal.question
        assert len(modal.options) == 2
        assert "Work Account" in modal.options[0][0]
        assert "Personal Account" in modal.options[1][0]


def test_chrome_profile_picker_bypasses_silently_if_single_profile():
    """Verify if user has only 1 Chrome profile, SpaceV never interrupts."""
    interceptor = UniversalModalInterceptor()

    single_profile = [
        {"id": "Default", "display": "Alice Smith", "name": "Alice", "email": "alice@gmail.com"}
    ]

    with patch.object(interceptor, "inspect_active_window", return_value=("Who's using Chrome?", "chrome", "Chrome_WidgetWin_1")), \
         patch("core.modal_interceptor.get_detected_chrome_profiles", return_value=single_profile), \
         patch("core.memory.memory.get", return_value=None), \
         patch("core.memory.memory.get_preference", return_value=None):
        modal = interceptor.detect()
        assert modal is None, "Single profile user should never be interrupted with disambiguation!"


def test_file_explorer_conflict_modal_detection_and_resolution():
    """Verify File Explorer 'Replace or Skip Files' modal is detected with clean options."""
    interceptor = UniversalModalInterceptor()

    with patch.object(interceptor, "inspect_active_window", return_value=("Replace or Skip Files", "file_explorer", "#32770")):
        modal = interceptor.detect()
        assert modal is not None
        assert modal.domain == "file_explorer"
        assert modal.property_key == "conflict_policy"
        assert len(modal.options) == 3
        assert any("Replace" in opt[0] for opt in modal.options)
        assert any("Skip" in opt[0] for opt in modal.options)


def test_vs_code_workspace_trust_modal_detection():
    """Verify VS Code 'Do you trust the authors of the files in this folder?' is detected."""
    interceptor = UniversalModalInterceptor()

    with patch.object(interceptor, "inspect_active_window", return_value=("Do you trust the authors of the files in this folder?", "vscode", "Chrome_WidgetWin_1")):
        modal = interceptor.detect()
        assert modal is not None
        assert modal.domain == "vscode"
        assert modal.property_key == "trust_mode"
        assert any("Trust" in opt[0] for opt in modal.options)
        assert any("Deny" in opt[0] for opt in modal.options)


def test_unsaved_changes_dialog_detection():
    """Verify unsaved changes confirmation dialog (Notepad / Win32) is cleanly detected."""
    interceptor = UniversalModalInterceptor()

    with patch.object(interceptor, "inspect_active_window", return_value=("Do you want to save changes to Untitled?", "notepad", "#32770")):
        modal = interceptor.detect()
        assert modal is not None
        assert modal.property_key == "unsaved_action"
        assert len(modal.options) == 3
        assert any("Save" in opt[0] for opt in modal.options)
        assert any("Don't Save" in opt[0] for opt in modal.options)


def test_generic_win32_dialog_dynamic_button_enumeration():
    """Verify generic #32770 dialogs dynamically enumerate child buttons without static hardcoding."""
    interceptor = UniversalModalInterceptor()

    with patch.object(interceptor, "inspect_active_window", return_value=("Printer Connection Warning", "system", "#32770")), \
         patch.object(interceptor, "_get_dialog_text_and_buttons", return_value=("Network printer offline. Retry connection?", ["Retry", "Cancel"])):
        modal = interceptor.detect()
        assert modal is not None
        assert modal.domain == "system"
        assert modal.property_key == "dialog_response"
        assert len(modal.options) == 2
        assert modal.options[0] == ("🔘 Retry", "retry")
        assert modal.options[1] == ("🔘 Cancel", "cancel")
        assert "Printer Connection Warning" in modal.question
        assert "Retry connection?" in modal.question


def test_dynamic_chrome_profile_switching_via_fast_router():
    """Verify FastRouter dynamically switches to any profile name or number without hardcoded strings."""
    mock_profiles = [
        {"id": "Default", "display": "Company Work", "name": "Work", "email": "work@example.com"},
        {"id": "Profile 3", "display": "Personal Gaming", "name": "Personal", "email": "gaming@example.com"}
    ]

    with patch("core.modal_interceptor.get_detected_chrome_profiles", return_value=mock_profiles), \
         patch("core.platform_adapter.PlatformAdapter.launch_app"):

        # 1. By profile name keyword ("gaming")
        match = FastRouter.match("switch chrome profile to gaming")
        assert match is not None
        action, prof_val, reply = match
        assert action == "set_chrome_profile"
        assert prof_val == "Profile 3"
        assert "Personal Gaming" in reply
        assert memory.get_preference("chrome", "profile") == "Profile 3"

        # 2. By numeric index ("1")
        match = FastRouter.match("use chrome profile 1")
        assert match is not None
        action, prof_val, reply = match
        assert action == "set_chrome_profile"
        assert prof_val == "Default"
        assert "Company Work" in reply


def test_holographic_visor_target_and_attention_activation_on_roadblock():
    """Verify HolographicVisor triggers visual target box and attention banner when a roadblock halts."""
    interceptor = UniversalModalInterceptor()
    interceptor.last_hwnd = 12345
    interceptor.last_rect = (100, 200, 400, 300)

    mock_modal = GatekeeperModal(
        is_active=True,
        domain="file_explorer",
        dialog_title="Replace or Skip Files",
        property_key="conflict_policy",
        question="Which option?",
        options=[("🔄 Replace", "replace"), ("⏭️ Skip", "skip")],
        hwnd=12345,
        window_rect=(100, 200, 400, 300)
    )

    with patch.object(interceptor, "detect", return_value=mock_modal), \
         patch("core.memory.memory.get_preference", return_value=None), \
         patch("ui.holographic_visor.HolographicVisor.get_instance") as mock_get_visor:
        mock_visor = MagicMock()
        mock_get_visor.return_value = mock_visor

        resolved, gatekeeper, q = interceptor.resolve_or_intercept("copy files")
        assert resolved is False
        assert gatekeeper is not None

        # Verify Holographic Visor was called with options/geometry and attention
        assert mock_visor.highlight_modal_elements.called or mock_visor.highlight_target.called
        mock_visor.set_attention.assert_called_once()


def test_chrome_profile_picker_detects_roadblock_even_when_preference_in_memory():
    """Verify that detect() never silently ignores a physically stuck 'Who's using Chrome?' modal."""
    interceptor = UniversalModalInterceptor()

    mock_profiles = [
        {"id": "Default", "display": "Primary Work", "name": "Work", "email": "work@corp.com"},
        {"id": "Profile 2", "display": "Personal Gaming", "name": "Personal", "email": "me@home.com"}
    ]

    # Stored preference is in memory (e.g. "Default")
    with patch.object(interceptor, "inspect_active_window", return_value=("Who's using Chrome?", "chrome", "Chrome_WidgetWin_1")), \
         patch("core.modal_interceptor.get_detected_chrome_profiles", return_value=mock_profiles), \
         patch("core.memory.memory.get", return_value="Default"):
        modal = interceptor.detect()
        assert modal is not None, "detect() must return GatekeeperModal when 'Who's using Chrome?' is physically on screen!"
        assert modal.domain == "chrome"
        assert len(modal.options) == 2


def test_holographic_visor_multi_reticle_projection():
    """Verify HolographicVisor multi-element reticle projection (highlight_elements and highlight_modal_elements)."""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from ui.holographic_visor import HolographicVisor

    # Initialize HolographicVisor in Qt context
    visor = HolographicVisor()
    assert hasattr(visor, "highlight_elements")
    assert hasattr(visor, "highlight_modal_elements")

    # Test highlight_elements populates target reticles
    test_boxes = [
        {"rect": (100, 150, 160, 200), "label": "[1] N. Sunny"},
        {"rect": (300, 150, 160, 200), "label": "[2] n. vikram"},
        {"rect": (500, 150, 160, 200), "label": "[3] Vicky Space"}
    ]
    visor.highlight_elements(test_boxes, duration_ms=20000)
    assert len(visor._target_boxes) == 3
    assert visor._target_boxes[0]["label"] == "[1] N. Sunny"
    assert visor._target_boxes[1]["label"] == "[2] n. vikram"
    assert visor._target_boxes[2]["label"] == "[3] Vicky Space"

    # Test grid fallback in highlight_modal_elements
    visor.clear_targets()
    options = [("👤 Account Alpha", "alpha"), ("👤 Account Beta", "beta")]
    visor.highlight_modal_elements(options, window_rect=(0, 0, 800, 600))
    assert len(visor._target_boxes) == 2


def test_fast_router_job_query_extracts_role_and_location():
    """Verify job queries extract role and location and harvest without blind Start Menu launches."""
    with patch("tools.career_tools.search_and_harvest_jobs", return_value="Found 8 jobs") as mock_harvest:
        match = FastRouter.match("Search for entry-level AI Engineer jobs in Bengaluru and save to desktop")
        assert match is not None
        action, res, reply = match
        assert action == "scrape_jobs"
        mock_harvest.assert_called_once()
        _, kwargs = mock_harvest.call_args
        assert kwargs["location"].lower() == "bengaluru"
        assert "ai engineer" in kwargs["role"].lower()
        assert kwargs["save_to_desktop"] is True


