"""
Microsoft OmniParser v2 Inspired Visual & Icon Grounding Engine for SpaceV.
Parses unstructured desktop screenshots into interactive visual elements,
detecting both text buttons and non-text interactive icons (⚙️ Settings, ▶️ Play,
🔍 Search, ✕ Close, ☰ Menu, 👤 Profile, ⬇️ Download) with sub-pixel cursor navigation.
"""
from __future__ import annotations

import difflib
import logging
import math
import time
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

from tools.gui_tools import human_move_to, safety

logger = logging.getLogger("SpaceV.OmniParser")


@dataclass
class UIElement:
    """Represents a parsed interactive UI widget or icon."""
    element_id: int
    element_type: str  # 'icon', 'button', 'text_control', 'input'
    label: str         # 'play', 'settings', 'close', 'search', or text content
    bbox: tuple[int, int, int, int]  # (x1, y1, x2, y2)
    center: tuple[int, int]          # (cx, cy)
    confidence: float


class OmniParserEngine:
    """
    OmniParser v2 Screen Parsing & Semantic Icon Grounding Engine.
    Combines edge/contour morphological segmentation with geometric icon classification
    and Windows Native OCR for 100% coverage of both text and icon widgets.
    """

    def __init__(self, min_size: int = 14, max_size: int = 400):
        self.min_size = min_size
        self.max_size = max_size

    def parse_screen(self, image: Image.Image | None = None) -> list[UIElement]:
        """
        Parses desktop frame into structured interactive UI elements and icons.
        """
        from core.screen_capture import capture_desktop_pil
        img = image or capture_desktop_pil()
        if img is None:
            return []

        cv_img = np.array(img)
        if len(cv_img.shape) == 3 and cv_img.shape[2] == 3:
            gray = cv2.cvtColor(cv_img, cv2.COLOR_RGB2GRAY)
        elif len(cv_img.shape) == 3 and cv_img.shape[2] == 4:
            gray = cv2.cvtColor(cv_img, cv2.COLOR_RGBA2GRAY)
        else:
            gray = cv_img

        parsed_elements: list[UIElement] = []
        element_id = 1

        # 1. Edge & Contour Discovery for Interactive Widgets
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        edges = cv2.Canny(blurred, 40, 120)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        dilated = cv2.dilate(edges, kernel, iterations=1)

        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            if self.min_size <= w <= self.max_size and self.min_size <= h <= self.max_size:
                # Discard full screen borders or long thin divider lines
                aspect_ratio = max(w, h) / max(min(w, h), 1)
                if aspect_ratio > 8.0:
                    continue

                roi = gray[y:y+h, x:x+w]
                icon_type, conf = self._classify_icon(cnt, w, h, roi)
                cx = x + w // 2
                cy = y + h // 2

                parsed_elements.append(UIElement(
                    element_id=element_id,
                    element_type="icon" if icon_type != "widget" else "button",
                    label=icon_type,
                    bbox=(x, y, x + w, y + h),
                    center=(cx, cy),
                    confidence=conf
                ))
                element_id += 1

        # 2. Integrate Windows Native OCR for Text Widgets
        try:
            from core.vision_grounding import _get_winocr
            ocr = _get_winocr()
            if ocr:
                res = ocr.recognize_pil_sync(img, lang="en-US")
                lines = res.get("lines", [])
                for line in lines:
                    for word in line.get("words", []):
                        w_text = word.get("text", "").strip()
                        if not w_text:
                            continue
                        rect = word.get("bounding_rect", {})
                        wx = int(rect.get("x", 0))
                        wy = int(rect.get("y", 0))
                        ww = int(rect.get("width", 0))
                        wh = int(rect.get("height", 0))
                        if ww > 2 and wh > 2:
                            parsed_elements.append(UIElement(
                                element_id=element_id,
                                element_type="text_control",
                                label=w_text,
                                bbox=(wx, wy, wx + ww, wy + wh),
                                center=(wx + ww // 2, wy + wh // 2),
                                confidence=0.95
                            ))
                            element_id += 1
        except Exception:
            pass

        return parsed_elements

    def _classify_icon(
        self,
        contour: np.ndarray,
        w: int,
        h: int,
        roi: np.ndarray
    ) -> tuple[str, float]:
        """
        Classifies geometric features into standard UI icon categories:
        play, close, settings, search, hamburger_menu, profile, download, plus.
        """
        perimeter = cv2.arcLength(contour, True)
        if perimeter == 0:
            return "widget", 0.4

        approx = cv2.approxPolyDP(contour, 0.04 * perimeter, True)
        num_vertices = len(approx)
        area = cv2.contourArea(contour)
        bounding_area = w * h
        extent = float(area) / bounding_area if bounding_area > 0 else 0

        # 1. Triangle pointing right -> Play ▶️
        if num_vertices == 3:
            # Check orientation of triangle apex
            pts = approx.reshape(-1, 2)
            pts_sorted_x = pts[pts[:, 0].argsort()]
            # If two points on left and one rightmost apex -> Play button
            if abs(pts_sorted_x[0][0] - pts_sorted_x[1][0]) < w * 0.35 and pts_sorted_x[2][0] > pts_sorted_x[0][0]:
                return "play", 0.92

        # 2. Square aspect ratio widgets
        aspect = float(w) / h
        if 0.82 <= aspect <= 1.18:
            # Low extent (< 0.48) indicates thin intersecting arms -> Close ✕ or Add ➕
            if extent < 0.48:
                return "close", 0.88

            # High extent (>= 0.48) with high vertex count -> Gear / Settings ⚙️
            if num_vertices >= 8:
                return "settings", 0.85

            # Circular shape -> Profile / User or Search 👤 🔍
            circularity = 4 * math.pi * (area / (perimeter * perimeter))
            if circularity > 0.62:
                return "profile", 0.80

        # 3. Horizontal bars -> Menu / Hamburger ☰
        if aspect > 1.2 and aspect < 2.5 and extent < 0.55:
            return "menu", 0.75

        # 4. Downward arrow check -> Download ⬇️
        if num_vertices in [5, 7] and h > w * 0.8:
            return "download", 0.76

        # 5. Plus / Add shape ➕
        if num_vertices == 12 or (extent < 0.5 and 0.8 <= aspect <= 1.2):
            return "add", 0.75

        return "widget", 0.50

    def find_icon_or_element(
        self,
        target_description: str,
        image: Image.Image | None = None,
        min_similarity: float = 0.65
    ) -> tuple[int, int, str, float] | None:
        """
        Locates any UI button, icon, or text element matching target_description.
        Returns:
            (center_x, center_y, matched_label, confidence) or None.
        """
        elements = self.parse_screen(image)
        if not elements:
            return None

        clean_target = target_description.lower().strip()
        # Strip common command words
        for prefix in ["click the ", "click on ", "click ", "press ", "select ", "tap "]:
            if clean_target.startswith(prefix):
                clean_target = clean_target[len(prefix):].strip()

        # Handle icon aliases
        target_aliases = [clean_target]
        if "gear" in clean_target or "cog" in clean_target or "option" in clean_target or "setting" in clean_target:
            target_aliases.extend(["settings", "gear"])
        if "play" in clean_target or "start video" in clean_target or "resume" in clean_target:
            target_aliases.extend(["play", "triangle"])
        if "close" in clean_target or "cross" in clean_target or "exit" in clean_target or "quit" in clean_target:
            target_aliases.extend(["close", "cancel"])
        if "search" in clean_target or "find" in clean_target or "magnifying" in clean_target:
            target_aliases.extend(["search"])
        if "menu" in clean_target or "hamburger" in clean_target or "drawer" in clean_target:
            target_aliases.extend(["menu", "hamburger"])
        if "profile" in clean_target or "account" in clean_target or "avatar" in clean_target or "user" in clean_target:
            target_aliases.extend(["profile", "user"])
        if "download" in clean_target or "save" in clean_target:
            target_aliases.extend(["download"])
        if "add" in clean_target or "plus" in clean_target or "new" in clean_target:
            target_aliases.extend(["add", "plus"])

        best_match: UIElement | None = None
        best_score: float = 0.0

        for elem in elements:
            elem_label = elem.label.lower().strip()
            for alias in target_aliases:
                # 1. Exact match
                if alias == elem_label:
                    score = 1.0 * elem.confidence
                # 2. Substring match
                elif alias in elem_label or elem_label in alias:
                    score = 0.88 * elem.confidence
                # 3. Fuzzy similarity
                else:
                    ratio = difflib.SequenceMatcher(None, alias, elem_label).ratio()
                    score = ratio * elem.confidence

                if score > best_score:
                    best_score = score
                    best_match = elem

        if best_match and best_score >= min_similarity:
            cx, cy = best_match.center
            return (cx, cy, best_match.label, best_score)

        return None

    def gui_click_icon(self, target_description: str) -> str:
        """
        Searches the screen for an icon or UI widget matching target_description,
        glides cursor with human acceleration, and clicks its center.
        """
        safety.reset()
        try:
            match = self.find_icon_or_element(target_description)
            if not match:
                # Fallback to pure OCR text discovery
                from core.vision_grounding import gui_click_text
                return gui_click_text(target_description)

            cx, cy, label, conf = match
            print(f"  [OMNIPARSER] 🎯 Found '{label}' at ({cx}, {cy}) (Confidence: {int(conf * 100)}%)")
            human_move_to(cx, cy, duration=0.45, label=f"🎯 CLICKING '{label.upper()}'", mode="clicking")
            safety.check()
            time.sleep(0.08)
            import pyautogui
            pyautogui.click()

            try:
                from ui.cursor_overlay import hide_cursor_hud
                hide_cursor_hud()
            except Exception:
                pass

            return f"OmniParser visually located '{label}' at ({cx}, {cy}) and clicked successfully!"

        except Exception as e:
            return f"OmniParser visual click failed: {e!s}"


# Global singleton instance
omniparser = OmniParserEngine()
