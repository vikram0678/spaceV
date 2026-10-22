"""
Persistent Memory Manager for SpaceV Cybernetic Desktop AI Agent.
Stores user preferences, custom shortcuts, and long-term context in a local JSON file.
"""
import json
from typing import Any

from config import MEMORY_FILE


class MemoryManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.data = {}
            cls._instance.load()
        return cls._instance

    def load(self):
        """Loads persistent data from JSON file."""
        if MEMORY_FILE.exists():
            try:
                with open(MEMORY_FILE, encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {}
        else:
            self.data = {
                "user_name": "Sir",
                "voice_enabled": False,
                "cursor_mode_enabled": False,
                "custom_shortcuts": {},
                "notes": []
            }
            self.save()

    def save(self):
        """Saves persistent data to JSON file."""
        try:
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            print(f"[Memory] Failed to save memory: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        # Fallback mapping for hierarchical preferences
        if key == "preferred_chrome_profile":
            pref = self.get_preference("chrome", "profile")
            if pref is not None:
                return pref
        return self.data.get(key, default)

    def set(self, key: str, value: Any):
        self.data[key] = value
        if key == "preferred_chrome_profile":
            self.set_preference("chrome", "profile", value)
        else:
            self.save()

    def get_preference(self, domain: str, key: str, default: Any = None) -> Any:
        """Retrieves a preference from the hierarchical domain namespace (e.g. domain='chrome', key='profile')."""
        prefs = self.data.get("preferences", {})
        domain_prefs = prefs.get(domain, {})
        val = domain_prefs.get(key)
        if val is not None:
            return val
        # Backwards compatibility check for flat keys
        flat_key = f"preferred_{domain}_{key}"
        if flat_key in self.data:
            return self.data[flat_key]
        return default

    def set_preference(self, domain: str, key: str, value: Any):
        """Persists a preference into the hierarchical domain namespace."""
        if "preferences" not in self.data or not isinstance(self.data["preferences"], dict):
            self.data["preferences"] = {}
        if domain not in self.data["preferences"]:
            self.data["preferences"][domain] = {}
        self.data["preferences"][domain][key] = value
        self.save()

    def set_suspended_disambiguation(self, data: dict[str, Any]):
        """Stores a suspended interactive task awaiting user clarification."""
        self.data["suspended_disambiguation"] = data
        self.save()

    def get_suspended_disambiguation(self) -> dict[str, Any] | None:
        """Retrieves currently suspended task awaiting user input."""
        return self.data.get("suspended_disambiguation")

    def clear_suspended_disambiguation(self):
        """Clears suspended task upon user resolution."""
        if "suspended_disambiguation" in self.data:
            del self.data["suspended_disambiguation"]
            self.save()

    def add_note(self, note: str):
        notes = self.data.get("notes", [])
        notes.append(note)
        self.data["notes"] = notes
        self.save()

    def get_notes(self) -> list:
        return self.data.get("notes", [])

memory = MemoryManager()
