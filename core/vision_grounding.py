"""
Visual Grounding & Text-Anchored Navigation Engine for SpaceV.
Powered by Windows Native OCR (Windows.Media.Ocr / winocr) with high-res bounding-box discovery
and sub-pixel human-like cursor gliding to any on-screen text, button, or link.
"""
import time
import difflib
from typing import Optional, Tuple, Dict, Any, List
from PIL import Image

def _get_winocr():
    """
    Lazy import of winocr to prevent premature WinRT/COM runtime initialization
    from interfering with ONNX Runtime C++ pybind state.
    """
    try:
        import winocr
        return winocr
    except Exception:
        return None

try:
    import pyautogui
except Exception:
    from tools.gui_tools import pyautogui
from tools.gui_tools import human_move_to, safety


def capture_screen_pil() -> Optional[Image.Image]:
    """
    Captures the interactive desktop display using hardware-accelerated DXGI (via bettercam)
    with automatic fallback to Windows GDI host capture.
    """
    from core.screen_capture import capture_desktop_pil
    return capture_desktop_pil()


def find_text_coordinates(
    target_text: str,
    image: Optional[Image.Image] = None,
    min_similarity: float = 0.72
) -> Optional[Tuple[int, int, str, float]]:
    """
    Locates specified text anywhere on screen using Windows Native OCR.
    Returns (center_x, center_y, matched_text, confidence_score) or None if not found.
    """
    ocr_engine = _get_winocr()
    if ocr_engine is None:
        return None

    img = image or capture_screen_pil()
    if img is None:
        return None

    try:
        res = ocr_engine.recognize_pil_sync(img, lang="en-US")
    except Exception:
        try:
            res = ocr_engine.recognize_pil_sync(img)
        except Exception:
            return None

    target_clean = target_text.lower().strip()
    best_match = None
    best_score = 0.0

    lines = res.get("lines", [])
    for line in lines:
        line_text = line.get("text", "").lower().strip()

        # Check full line match
        line_sim = difflib.SequenceMatcher(None, target_clean, line_text).ratio()
        if target_clean in line_text:
            line_sim = max(line_sim, 0.90)

        # Check word-by-word matches
        for word in line.get("words", []):
            w_text = word.get("text", "").lower().strip()
            if not w_text:
                continue

            sim = difflib.SequenceMatcher(None, target_clean, w_text).ratio()
            if target_clean == w_text:
                sim = 1.0
            elif target_clean in w_text or w_text in target_clean:
                sim = max(sim, 0.85)

            if sim > best_score:
                best_score = sim
                rect = word.get("bounding_rect", {})
                cx = int(rect.get("x", 0) + rect.get("width", 0) / 2)
                cy = int(rect.get("y", 0) + rect.get("height", 0) / 2)
                best_match = (cx, cy, word.get("text", target_text), sim)

    if best_match and best_score >= min_similarity:
        return best_match

    return None


def read_screen_text(image: Optional[Image.Image] = None) -> str:
    """
    Performs full-screen OCR transcription, returning all visible on-screen text.
    """
    ocr_engine = _get_winocr()
    if ocr_engine is None:
        return "Windows OCR engine is not initialized."

    img = image or capture_screen_pil()
    if img is None:
        return "Unable to capture desktop screen for OCR."

    try:
        res = ocr_engine.recognize_pil_sync(img, lang="en-US")
        text = res.get("text", "").strip()
        return text if text else "No legible text detected on screen."
    except Exception as e:
        return f"OCR inspection failed: {str(e)}"


def gui_click_text(target_text: str) -> str:
    """
    Autonomously searches the current display for specified text, button, or link,
    glides the virtual cursor to its pixel center, and clicks it.
    """
    safety.reset()
    try:
        match = find_text_coordinates(target_text)
        if not match:
            return f"Could not visually locate '{target_text}' on your screen."

        cx, cy, matched_word, score = match
        print(f"  [VISION OCR] 🎯 Found '{matched_word}' at ({cx}, {cy}) (Confidence: {int(score * 100)}%)")

        # Glide cursor smoothly to text center
        human_move_to(cx, cy, duration=0.45, label=f"🎯 CLICKING '{matched_word}'", mode="clicking")
        safety.check()
        time.sleep(0.1)
        pyautogui.click()

        try:
            from ui.cursor_overlay import hide_cursor_hud
            hide_cursor_hud()
        except Exception:
            pass

        return f"Autonomously located '{matched_word}' at ({cx}, {cy}) and clicked successfully!"

    except pyautogui.FailSafeException:
        safety.abort()
        return "⚠️ EMERGENCY STOP: PyAutoGUI Fail-Safe triggered."
    except InterruptedError as e:
        return f"⚠️ EMERGENCY STOP: {str(e)}"
    except Exception as e:
        return f"Visual click failed: {str(e)}"


# ============================================================================
# SET-OF-MARK (SoM) COORDINATE NORMALIZATION & VISUAL GROUNDING (Upgrade #15)
# ============================================================================

def normalize_coordinates(x: int, y: int, screen_w: int, screen_h: int) -> Tuple[int, int]:
    """
    Normalizes physical screen pixel coordinates onto standard [0, 1000] scale.
    """
    w = max(screen_w, 1)
    h = max(screen_h, 1)
    norm_x = int(round((x / w) * 1000))
    norm_y = int(round((y / h) * 1000))
    return (max(0, min(1000, norm_x)), max(0, min(1000, norm_y)))


def denormalize_coordinates(norm_x: int, norm_y: int, screen_w: int, screen_h: int) -> Tuple[int, int]:
    """
    De-normalizes [0, 1000] model coordinate space into physical screen pixels.
    """
    x = int(round((norm_x / 1000.0) * screen_w))
    y = int(round((norm_y / 1000.0) * screen_h))
    return (max(0, min(screen_w - 1, x)), max(0, min(screen_h - 1, y)))


_CACHED_SOM_ELEMENTS: List[Dict[str, Any]] = []


def generate_set_of_marks(image: Optional[Image.Image] = None) -> Tuple[Optional[Image.Image], List[Dict[str, Any]]]:
    """
    Discovers interactive desktop elements using OmniParser and renders
    Set-of-Mark (SoM) labeled bounding boxes with numeric badges [1], [2], [3].
    Returns (annotated_som_image, elements_metadata).
    """
    global _CACHED_SOM_ELEMENTS
    from PIL import ImageDraw, ImageFont
    from core.omniparser import OmniParserEngine

    img = image or capture_screen_pil()
    if img is None:
        return None, []

    screen_w, screen_h = img.size
    parser = OmniParserEngine()
    ui_elements = parser.parse_screen(img)

    annotated = img.copy()
    draw = ImageDraw.Draw(annotated, "RGBA")
    elements_metadata: List[Dict[str, Any]] = []

    # Palette for SoM bounding boxes
    colors = [
        (0, 240, 255, 180),    # Cyan
        (255, 179, 0, 180),    # Amber
        (168, 85, 247, 180),   # Purple
        (0, 230, 118, 180),    # Neon Green
        (255, 42, 109, 180),   # Crimson
    ]

    for idx, el in enumerate(ui_elements, 1):
        x1, y1, x2, y2 = el.bbox
        cx, cy = el.center
        norm_cx, norm_cy = normalize_coordinates(cx, cy, screen_w, screen_h)
        col = colors[(idx - 1) % len(colors)]

        # 1. Draw element boundary box
        draw.rectangle([x1, y1, x2, y2], outline=col[:3] + (220,), width=2)

        # 2. Draw integer badge overlay [idx]
        badge_w, badge_h = 24, 18
        bx1 = max(0, x1)
        by1 = max(0, y1 - badge_h)
        draw.rectangle([bx1, by1, bx1 + badge_w, by1 + badge_h], fill=col[:3] + (240,))
        draw.text((bx1 + 4, by1 + 2), str(idx), fill=(0, 0, 0, 255))

        elements_metadata.append({
            "index": idx,
            "label": el.label,
            "type": el.element_type,
            "bbox": (x1, y1, x2, y2),
            "center": (cx, cy),
            "norm_center": (norm_cx, norm_cy),
            "confidence": el.confidence
        })

    _CACHED_SOM_ELEMENTS = elements_metadata
    return annotated, elements_metadata


def gui_click_som_index(element_index: int, som_elements: Optional[List[Dict[str, Any]]] = None) -> str:
    """
    Clicks the on-screen element corresponding to Set-of-Mark integer index [element_index].
    """
    global _CACHED_SOM_ELEMENTS
    safety.reset()
    elements = som_elements or _CACHED_SOM_ELEMENTS

    if not elements:
        # Generate fresh marks if not cached
        _, elements = generate_set_of_marks()

    target = next((e for e in elements if e["index"] == element_index), None)
    if not target:
        return f"Element index [{element_index}] not found among {len(elements)} detected UI marks."

    cx, cy = target["center"]
    label = target.get("label", "element")
    try:
        human_move_to(cx, cy, duration=0.35, label=f"🎯 CLICKING [{element_index}] {label}", mode="clicking")
        safety.check()
        time.sleep(0.08)
        pyautogui.click()
        return f"Autonomously clicked Set-of-Mark [{element_index}] ('{label}') at ({cx}, {cy})."
    except Exception as e:
        return f"Failed clicking mark [{element_index}]: {str(e)}"
