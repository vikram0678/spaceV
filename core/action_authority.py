"""
Cryptographic Action Authority & Region Validation Engine for SpaceV.
Inspired by cua/libs/cua-driver (OmniParser & CUA Action Authority Contract).
Generates and enforces single-use ephemeral `capture_id` tokens to ensure
autonomous GUI actions (click, type, drag) only execute against verified, active screen states.
"""
import time
import uuid
import hashlib
from typing import Dict, Any, List, Optional


class ActionAuthority:
    """
    Guarantees state parity between what the model perceived and what the OS executes.
    Prevents window drift, phantom clicks, and runaway hallucinated loops.
    """

    def __init__(self, validity_window_sec: float = 12.0):
        self.validity_window_sec = validity_window_sec
        self._active_capture: Optional[Dict[str, Any]] = None
        self._consumed_tokens: set = set()

    def register_observation(
        self,
        window_title: str,
        elements: List[Dict[str, Any]],
        screen_hash: Optional[str] = None
    ) -> str:
        """
        Creates a new ephemeral capture token for the perceived state.
        Invalidates any previously unused capture tokens.
        """
        token = f"cap_{uuid.uuid4().hex[:12]}"
        now = time.time()

        if not screen_hash:
            # Deterministic fingerprint from window and interactive elements
            summary = f"{window_title}:" + ",".join([f"{e.get('id')}:{e.get('name')}" for e in elements])
            screen_hash = hashlib.sha256(summary.encode("utf-8")).hexdigest()[:16]

        self._active_capture = {
            "capture_id": token,
            "created_at": now,
            "window_title": window_title,
            "elements": {e.get("id"): e for e in elements if "id" in e},
            "screen_hash": screen_hash,
        }
        return token

    def authorize_action(
        self,
        capture_id: str,
        element_id: Optional[int] = None,
        expected_window: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validates whether an action is authorized against the current observation.
        Consumes the token upon successful authorization to enforce single-use.
        """
        now = time.time()

        if not capture_id:
            return {
                "authorized": False,
                "error": "Missing required capture_id. Actions must carry a valid observation token."
            }

        if capture_id in self._consumed_tokens:
            return {
                "authorized": False,
                "error": f"Token {capture_id} has already been consumed. Re-observe the desktop to act."
            }

        if not self._active_capture or self._active_capture["capture_id"] != capture_id:
            return {
                "authorized": False,
                "error": f"Stale or unknown capture_id '{capture_id}'. The desktop state has changed."
            }

        elapsed = now - self._active_capture["created_at"]
        if elapsed > self.validity_window_sec:
            return {
                "authorized": False,
                "error": f"Observation timed out ({elapsed:.1f}s > {self.validity_window_sec}s). State is expired."
            }

        if expected_window and expected_window.lower() not in self._active_capture["window_title"].lower():
            return {
                "authorized": False,
                "error": f"Target window mismatch: expected '{expected_window}', but active window is '{self._active_capture['window_title']}'."
            }

        matched_element = None
        if element_id is not None:
            elements_map = self._active_capture.get("elements", {})
            if element_id not in elements_map:
                return {
                    "authorized": False,
                    "error": f"Element ID [{element_id}] was not found in the verified observation state."
                }
            matched_element = elements_map[element_id]

        # Authorize and consume
        self._consumed_tokens.add(capture_id)
        return {
            "authorized": True,
            "element": matched_element,
            "capture_id": capture_id,
            "window": self._active_capture["window_title"]
        }


# Global singleton instance
action_authority = ActionAuthority()
