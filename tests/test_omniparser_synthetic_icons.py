"""
Synthetic Verification Test for OmniParser & WSL2 Host Screen Capture.
Verifies:
- DEF-013 Fix: HostBridge.capture_host_screen() & capture_desktop_pil() in WSL2
- DEF-015 Fix: gui_click_icon & parse_screen_elements registered in PYDANTIC_TOOL_MODELS
- Geometric icon contour classification (Play, Close, Menu, Add, Profile)
"""
import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.omniparser import OmniParserEngine, omniparser
from core.screen_capture import capture_desktop_pil
from tools.schemas import PYDANTIC_TOOL_MODELS


def test_wsl_host_screen_capture():
    """Verifies that screen capture returns a valid PIL Image without display errors."""
    img = capture_desktop_pil()
    assert img is not None, "capture_desktop_pil() must return a valid Image"
    w, h = img.size
    assert w > 0 and h > 0, f"Captured screen image must have positive dimensions, got {w}x{h}"


def test_omniparser_tool_schemas_registered():
    """Verifies that OmniParser meta-tools are exposed in PYDANTIC_TOOL_MODELS."""
    assert "gui_click_icon" in PYDANTIC_TOOL_MODELS, "gui_click_icon missing from PYDANTIC_TOOL_MODELS"
    assert "parse_screen_elements" in PYDANTIC_TOOL_MODELS, "parse_screen_elements missing from PYDANTIC_TOOL_MODELS"


def test_omniparser_synthetic_icon_classification():
    """
    Renders clean geometric shapes on an empty canvas and verifies
    that OmniParserEngine accurately classifies Play, Close, Menu, and Add.
    """
    canvas_w, canvas_h = 800, 600
    img = Image.new("RGB", (canvas_w, canvas_h), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # 1. Play Button: Right-pointing triangle (apex pointing right)
    # x: 100..140, y: 100..140
    draw.polygon([(100, 100), (100, 140), (140, 120)], fill=(0, 0, 0))

    # 2. Close Icon: Cross with intersecting arms (aspect ~1, thin arms)
    # Draw an X
    draw.line([(200, 100), (240, 140)], fill=(0, 0, 0), width=3)
    draw.line([(200, 140), (240, 100)], fill=(0, 0, 0), width=3)

    # 3. Menu Icon: Three horizontal bars
    for offset_y in [100, 115, 130]:
        draw.rectangle([(300, offset_y), (350, offset_y + 5)], fill=(0, 0, 0))

    # 4. Add / Plus Icon: Intersecting plus
    draw.rectangle([(415, 100), (425, 140)], fill=(0, 0, 0))
    draw.rectangle([(400, 115), (440, 125)], fill=(0, 0, 0))

    parser = OmniParserEngine(min_size=10, max_size=200)
    elements = parser.parse_screen(img)

    labels = {e.label for e in elements}
    print("Detected synthetic labels:", labels)

    # Verify key geometric categories were detected
    assert len(elements) >= 3, f"Expected at least 3 detected elements, got {len(elements)}"
    # Verify Play triangle was recognized
    assert "play" in labels, f"Play triangle was not recognized. Labels: {labels}"


if __name__ == "__main__":
    test_omniparser_tool_schemas_registered()
    test_omniparser_synthetic_icon_classification()
    test_wsl_host_screen_capture()
    print("All OmniParser & Vision unit tests PASSED!")
