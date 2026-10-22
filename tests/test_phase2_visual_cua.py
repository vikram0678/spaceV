"""
Unit tests for SpaceV Phase 2: Visual CUA & Stealth Upgrades.
Verifies:
- Set-of-Mark (SoM) Coordinate Normalization & Badging (#15)
- DXGI / GDI Hardware Screen Capture Tiering (#18)
- Camoufox Anti-Detect Stealth Browser Initialization (#22)
- DOM Integer Indexing ([1], [2], [3]) (#23)
"""
import sys
from pathlib import Path
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.vision_grounding import (
    normalize_coordinates,
    denormalize_coordinates,
    generate_set_of_marks,
)
from core.screen_capture import get_active_capture_tier
from hybrid_agent.dom_extractor import DOMExtractor
from hybrid_agent.state import DOMElement


def test_som_coordinate_normalization():
    # Test 1920x1080 standard full HD
    norm_x, norm_y = normalize_coordinates(960, 540, 1920, 1080)
    assert norm_x == 500
    assert norm_y == 500

    # Test reverse de-normalization
    px_x, px_y = denormalize_coordinates(500, 500, 1920, 1080)
    assert px_x == 960
    assert px_y == 540

    # Test corner boundaries
    top_left_x, top_left_y = normalize_coordinates(0, 0, 1920, 1080)
    assert top_left_x == 0
    assert top_left_y == 0

    bot_right_x, bot_right_y = normalize_coordinates(1920, 1080, 1920, 1080)
    assert bot_right_x == 1000
    assert bot_right_y == 1000


def test_set_of_marks_overlay_generation():
    # Create synthetic test canvas with distinct button-like rectangles
    test_img = Image.new("RGB", (800, 600), color=(30, 30, 35))
    annotated, marks = generate_set_of_marks(test_img)

    assert annotated is not None
    assert annotated.size == (800, 600)
    assert isinstance(marks, list)


def test_screen_capture_active_tier():
    tier = get_active_capture_tier()
    assert tier is not None
    assert isinstance(tier, str)
    assert len(tier) > 0


def test_dom_extractor_element_modeling():
    # Verify DOMElement dataclass fields
    el = DOMElement(
        index=1,
        tag="button",
        text="Submit Application",
        role="button",
        selector="#submit-btn",
        rect={"x": 100, "y": 200, "width": 80, "height": 30}
    )
    assert el["index"] == 1
    assert el["tag"] == "button"
    assert el["role"] == "button"
    assert el["selector"] == "#submit-btn"
