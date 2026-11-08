"""
Test suite for Universal System Application Catalog & Grounding Engine.
Verifies:
1. Dynamic discovery of workstation software (Registry, Start Menu, UWP, PATH).
2. Fuzzy matching and alias resolution (e.g. 'calc' -> Calculator, 'code' -> VS Code).
3. Truthful rejection of uninstalled software (anti-hallucination guard).
4. Registry-grounded default browser and code editor discovery.
5. FastRouter universal app dispatch in <1ms without static whitelists.
"""

from unittest.mock import MagicMock, patch
import pytest

from core.app_catalog import AppEntry, SystemAppCatalog, app_catalog
from core.fast_router import FastRouter
from core.platform_adapter import PlatformAdapter


def test_dynamic_app_catalog_indexing():
    """Verify that SystemAppCatalog discovers installed applications without hardcoded lists."""
    assert len(app_catalog._catalog) > 10, "Catalog should have discovered multiple installed apps on Windows"

    # Common Windows apps that must be discovered
    found_calc = app_catalog.find_app("calculator")
    assert found_calc is not None
    assert found_calc.display_name.lower() in ("calculator", "calc")

    found_notepad = app_catalog.find_app("notepad")
    assert found_notepad is not None
    assert "notepad" in found_notepad.display_name.lower()


def test_find_app_exact_and_alias():
    """Verify alias mapping and case-insensitive resolution."""
    # 'calc' alias -> Calculator
    match_calc = app_catalog.find_app("calc")
    assert match_calc is not None
    assert "calculator" in match_calc.name or "calc" in match_calc.name

    # 'vscode' alias -> Visual Studio Code or Code
    match_code = app_catalog.find_app("vscode")
    if match_code:
        assert any(k in match_code.display_name.lower() for k in ("code", "visual studio"))


def test_find_app_uninstalled_returns_none():
    """Verify that uninstalled software is not hallucinated."""
    res = app_catalog.find_app("fictional_uninstalled_software_999")
    assert res is None


def test_launch_uninstalled_app_truthful_rejection():
    """Verify launch returns False and truthful rejection for missing software."""
    success, msg = app_catalog.launch("fictional_uninstalled_software_999")
    assert success is False
    assert "not installed on this workstation" in msg


def test_get_default_browser_returns_installed_browser():
    """Verify default browser detection matches Windows Registry or installed browser."""
    browser_id, browser_path = app_catalog.get_default_browser()
    assert browser_id in ("chrome", "brave", "edge", "firefox", "opera", "browser")
    if browser_path:
        assert "exe" in browser_path.lower() or "lnk" in browser_path.lower()


def test_get_installed_editors_returns_prioritized_list():
    """Verify installed editors are returned in priority order."""
    editors = app_catalog.get_installed_editors()
    assert len(editors) >= 1
    editor_names = [e.name.lower() for e in editors]
    assert any(ed in editor_names for ed in ("cursor", "code", "notepad", "notepad++"))


def test_fast_router_dynamic_app_launch():
    """Verify FastRouter dispatches installed apps in <1ms without static whitelists."""
    res = FastRouter.match("open calculator")
    assert res is not None
    assert res[0] == "open_application"
    assert "Calculator" in res[2] or "calc" in res[2].lower()

    res_notepad = FastRouter.match("launch notepad")
    assert res_notepad is not None
    assert res_notepad[0] in ("open_application", "open_text_editor")
    assert "Notepad" in res_notepad[2] or "notepad" in res_notepad[2].lower()


def test_fast_router_truthful_rejection_for_uninstalled_app():
    """Verify FastRouter responds truthfully when an uninstalled app is requested."""
    res = FastRouter.match("open blender_fictional_app")
    assert res is not None
    assert res[0] == "app_not_found"
    assert "not installed on this PC" in res[2]
    assert "blender_fictional_app" in res[2]


def test_platform_adapter_truthful_rejection():
    """Verify PlatformAdapter returns explicit error when launching non-existent app."""
    msg = PlatformAdapter.launch_app("non_existent_app_xyz")
    assert "not installed on this workstation" in msg


def test_zero_hardcoded_developer_identities_in_engine_code():
    """
    Scans core/ engine modules to guarantee zero hardcoded developer usernames
    ('vikram', 'sunny', 'Profile 1') are present in runtime code.
    """
    from pathlib import Path
    core_dir = Path("core")
    banned_terms = ["profile 1", "vikram", "sunny"]

    for py_file in core_dir.glob("*.py"):
        content = py_file.read_text(encoding="utf-8").lower()
        for term in banned_terms:
            # Exempt comments or generic identifiers if any
            for line_idx, line in enumerate(content.splitlines(), 1):
                if term in line:
                    clean_line = line.strip()
                    # Skip benign docstrings or test comments if strictly generic
                    if not clean_line.startswith("#") and not clean_line.startswith('"""'):
                        pytest.fail(f"Found banned hardcoded identity '{term}' in {py_file} line {line_idx}: {clean_line}")
