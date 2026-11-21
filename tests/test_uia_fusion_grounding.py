"""
Unit tests for core/uia_grounding.py: Visual + UIA Fusion Grounding Engine ("SpaceV Eye").
Verifies hierarchical 3-tier discovery:
  Tier 1: Windows UI Automation Native Fast-Path (<2ms)
  Tier 2: Windows Native OCR On-Screen Text Grounding
  Tier 3: OmniParser Computer Vision Icon & Element Grounding
  Tier 4: Failure Graceful Fallback
Also verifies closed-loop motor execution and emergency halts.
Strictly zero regex and zero hardcoded paths.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from unittest.mock import MagicMock, Mock, patch

import pytest
from core.human_actuator import (
    ActuationAction,
    BoundingBox,
    EmergencyHaltSignal,
    HumanActuator,
    Point2D,
)
from core.uia_grounding import (
    GroundingMatch,
    GroundingTier,
    SpaceVEyeGrounder,
    find_control_box,
    find_control_by_name,
    gui_click_control,
    list_interactive_controls,
)


@dataclass
class MockRect:
    left: int
    top: int
    right: int
    bottom: int


class MockUIAElement:
    def __init__(
        self,
        name: str,
        rect: MockRect,
        ctrl_type: str = "Button",
        enabled: bool = True,
        offscreen: bool = False,
    ):
        self.CurrentName = name
        self.CurrentBoundingRectangle = rect
        self.CurrentLocalizedControlType = ctrl_type
        self.CurrentIsEnabled = enabled
        self.CurrentIsOffscreen = offscreen


class MockWalker:
    def __init__(self, hierarchy: dict[Any, list[Any]]):
        self.hierarchy = hierarchy

    def GetFirstChildElement(self, elem):
        children = self.hierarchy.get(elem, [])
        return children[0] if children else None

    def GetNextSiblingElement(self, elem):
        for parent, children in self.hierarchy.items():
            if elem in children:
                idx = children.index(elem)
                if idx + 1 < len(children):
                    return children[idx + 1]
        return None


def test_bounding_box_geometry_and_dispersion():
    box = BoundingBox(left=100.0, top=200.0, right=300.0, bottom=250.0)
    assert box.width == 200.0
    assert box.height == 50.0
    assert box.center == Point2D(200.0, 225.0)

    # Sample multiple human targets to verify Gaussian scatter within margins
    samples = [box.sample_human_target() for _ in range(25)]
    assert len(samples) == 25
    for s in samples:
        assert 100.0 <= s.x <= 300.0
        assert 200.0 <= s.y <= 250.0

    # Ensure not every click hits the exact identical coordinate (human dispersion)
    unique_x = {s.x for s in samples}
    assert len(unique_x) > 1, "Human click simulation must disperse naturally"


def test_find_control_box_and_find_control_by_name_tier1():
    root = MockUIAElement("MainWindow", MockRect(0, 0, 1920, 1080), "Window")
    btn_submit = MockUIAElement("Submit Order", MockRect(500, 400, 620, 440), "Button")
    input_email = MockUIAElement("Email Address", MockRect(500, 300, 800, 340), "Edit")

    mock_uia = Mock()
    mock_uia.GetRootElement.return_value = root
    mock_uia.ControlViewWalker = MockWalker({root: [input_email, btn_submit]})

    with patch("core.uia_grounding._get_uia_client", return_value=mock_uia):
        # Direct box lookup
        res = find_control_box("submit")
        assert res is not None
        box, matched_name, ctrl_type = res
        assert matched_name == "Submit Order"
        assert ctrl_type == "Button"
        assert box.left == 500.0
        assert box.top == 400.0
        assert box.right == 620.0
        assert box.bottom == 440.0

        # Backward-compatible center coordinate lookup
        center_res = find_control_by_name("email")
        assert center_res is not None
        cx, cy, name, c_type = center_res
        assert name == "Email Address"
        assert c_type == "Edit"
        assert cx == 650
        assert cy == 320

        # Not found lookup
        assert find_control_box("nonexistent_button_query") is None


def test_list_interactive_controls():
    root = MockUIAElement("AppWindow", MockRect(0, 0, 800, 600), "Window")
    btn1 = MockUIAElement("Save", MockRect(50, 50, 150, 90), "Button")
    btn2 = MockUIAElement("Cancel", MockRect(160, 50, 260, 90), "Button")

    mock_uia = Mock()
    mock_uia.GetRootElement.return_value = root
    mock_uia.ControlViewWalker = MockWalker({root: [btn1, btn2]})

    with patch("core.uia_grounding._get_uia_client", return_value=mock_uia):
        controls = list_interactive_controls(limit=10)
        assert len(controls) >= 2
        names = {c["name"] for c in controls}
        assert "Save" in names
        assert "Cancel" in names


def test_spacev_eye_hierarchical_fallback_tiers():
    # 1. Tier 1: UIA Native COM Fast-Path Match
    box1 = BoundingBox(10.0, 10.0, 50.0, 50.0)
    with patch("core.uia_grounding.find_control_box", return_value=(box1, "Settings Icon", "Button")):
        m1 = SpaceVEyeGrounder.ground_target("settings")
        assert m1.tier == GroundingTier.UIA_FASTPATH
        assert m1.matched_label == "Settings Icon"
        assert m1.confidence == 1.0
        assert m1.bounding_box == box1

    # 2. Tier 2: OCR Visual Match when Tier 1 fails
    with patch("core.uia_grounding.find_control_box", return_value=None):
        with patch("core.vision_grounding.find_text_coordinates", return_value=(450, 200, "Checkout", 0.95)):
            m2 = SpaceVEyeGrounder.ground_target("checkout")
            assert m2.tier == GroundingTier.OCR_VISUAL
            assert m2.matched_label == "Checkout"
            assert m2.confidence == 0.95
            assert m2.bounding_box is not None
            assert m2.bounding_box.center.x == 450.0
            assert m2.bounding_box.center.y == 200.0

    # 3. Tier 3: OmniParser Geometric Icon Match when Tiers 1 & 2 fail
    @dataclass
    class MockOmniElem:
        label: str
        element_type: str
        bounding_box: tuple[int, int, int, int]

    mock_omni_elem = MockOmniElem(label="Search", element_type="SearchIcon", bounding_box=(700, 15, 40, 40))

    with patch("core.uia_grounding.find_control_box", return_value=None):
        with patch("core.vision_grounding.find_text_coordinates", return_value=None):
            with patch("core.screen_capture.capture_desktop_pil", return_value=Mock()):
                with patch("core.omniparser.omniparser.parse_screen", return_value=[mock_omni_elem]):
                    m3 = SpaceVEyeGrounder.ground_target("search")
                    assert m3.tier == GroundingTier.ICON_GEOMETRIC
                    assert m3.matched_label == "Search"
                    assert m3.bounding_box == BoundingBox(700.0, 15.0, 740.0, 55.0)

    # 4. Tier 4: Total Failure Graceful Fallback
    with patch("core.uia_grounding.find_control_box", return_value=None):
        with patch("core.vision_grounding.find_text_coordinates", return_value=None):
            with patch("core.screen_capture.capture_desktop_pil", return_value=None):
                m4 = SpaceVEyeGrounder.ground_target("quantum_portal_button")
                assert m4.tier == GroundingTier.FAILED
                assert m4.bounding_box is None
                assert m4.confidence == 0.0


def test_gui_click_control_closed_loop_and_emergency():
    test_box = BoundingBox(200.0, 200.0, 300.0, 260.0)
    match = GroundingMatch(
        tier=GroundingTier.UIA_FASTPATH,
        target_query="Deploy",
        matched_label="Deploy",
        control_type="Button",
        bounding_box=test_box,
        confidence=1.0,
    )

    with patch("core.uia_grounding.safety.check"):
        with patch.object(SpaceVEyeGrounder, "ground_target", return_value=match):
            with patch("core.host_bridge.HostBridge.is_wsl", return_value=False):
                with patch("core.uia_grounding.pyautogui") as mock_pag:
                    mock_pag.position.return_value = (50, 50)
                    mock_pag.click = Mock()
                    mock_pag.moveTo = Mock()

                    # Successful execution
                    res = gui_click_control("Deploy")
                    assert "SpaceV Eye located 'Deploy'" in res
                    assert "via uia_fastpath" in res
                    assert "Organic actuation glided to" in res

        # Target not found scenario
        failed_match = GroundingMatch(
            tier=GroundingTier.FAILED,
            target_query="Ghost",
            matched_label="",
            control_type="",
            bounding_box=None,
            confidence=0.0,
        )
        with patch.object(SpaceVEyeGrounder, "ground_target", return_value=failed_match):
            res_fail = gui_click_control("Ghost")
            assert "Could not locate interactive control" in res_fail

        # Emergency halt scenario
        with patch.object(SpaceVEyeGrounder, "ground_target", return_value=match):
            with patch.object(HumanActuator, "glide_and_actuate", side_effect=EmergencyHaltSignal("User pressed Emergency Space")):
                res_halt = gui_click_control("Deploy")
                assert "EMERGENCY STOP" in res_halt
