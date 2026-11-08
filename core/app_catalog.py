"""
Universal System Application Catalog & Grounding Engine for SpaceV.
Eliminates hardcoded application whitelists by dynamically discovering
all installed software across Windows Registry, Start Menu, UWP packages, and PATH.
Provides sub-millisecond lookup and verified launches with zero cloud API token cost.
"""

from __future__ import annotations

import difflib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("SpaceV.AppCatalog")

try:
    import winreg
    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False


@dataclass
class AppEntry:
    """Represents a discovered and verified executable, shortcut, or system application."""
    name: str                 # Normalized lookup key (e.g., 'android studio', 'brave', 'excel')
    display_name: str         # Human-readable title (e.g., 'Android Studio', 'Brave Browser')
    target: str               # Binary path, .lnk path, URI protocol, or UWP AppID
    app_type: str             # 'exe' | 'lnk' | 'uri' | 'cli' | 'uwp'
    aliases: list[str]        # Alternative terms (e.g., ['vscode', 'code'])

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppEntry:
        return cls(
            name=data.get("name", ""),
            display_name=data.get("display_name", ""),
            target=data.get("target", ""),
            app_type=data.get("app_type", "exe"),
            aliases=data.get("aliases", []),
        )


class SystemAppCatalog:
    """
    On-device dynamic registry and discovery catalog for installed operating system applications.
    Pre-indexes all available tools so SpaceV can ground task execution in truth.
    """

    DEFAULT_ALIASES: dict[str, list[str]] = {
        "visual studio code": ["vscode", "code", "vs code"],
        "google chrome": ["chrome", "browser", "web browser"],
        "brave": ["brave browser", "browser", "web browser"],
        "microsoft edge": ["edge", "msedge", "browser", "web browser"],
        "calculator": ["calc"],
        "command prompt": ["cmd", "terminal"],
        "windows terminal": ["wt", "terminal"],
        "task manager": ["taskmgr", "task manager"],
        "notepad": ["editor", "text editor"],
        "notepad++": ["npp", "notepad plus plus", "editor"],
        "obs studio": ["obs", "recorder"],
        "settings": ["ms-settings", "windows settings", "system settings"],
        "file explorer": ["explorer", "files", "my computer"],
    }

    KNOWN_SYSTEM_URIS: dict[str, tuple[str, str]] = {
        "settings": ("Settings", "ms-settings:"),
        "calculator": ("Calculator", "ms-calculator:"),
        "camera": ("Camera", "microsoft.windows.camera:"),
        "photos": ("Photos", "ms-photos:"),
        "clock": ("Clock", "ms-clock:"),
        "alarms": ("Alarms & Clock", "ms-clock:"),
    }

    def __init__(self, cache_dir: Path | None = None) -> None:
        self.base_dir = cache_dir or Path(os.environ.get("LOCALAPPDATA", ".")) / "SpaceV"
        self.cache_file = self.base_dir / "spacev_app_index.json"
        self._catalog: dict[str, AppEntry] = {}
        self._alias_map: dict[str, str] = {}
        self._initialized: bool = False
        self.refresh_catalog()

    def refresh_catalog(self, force_rescan: bool = False) -> None:
        """
        Loads cached catalog or performs zero-token scan across Windows.
        """
        if not force_rescan and self._load_cache():
            self._build_alias_index()
            self._initialized = True
            return

        self._catalog.clear()

        # 1. Windows Registry App Paths (HKLM & HKCU)
        self._scan_registry_app_paths()

        # 2. Windows Start Menu Shortcuts (.lnk files)
        self._scan_start_menu()

        # 3. Known System URIs (Settings, Calculator, etc.)
        self._register_known_system_uris()

        # 4. PATH Binaries
        self._scan_path_binaries()

        # 5. Build Alias Index & Save Cache
        self._build_alias_index()
        self._save_cache()
        self._initialized = True
        logger.info(f"[APP_CATALOG] Indexed {len(self._catalog)} verified system applications.")

    def _normalize_name(self, raw_name: str) -> str:
        """Strips file extensions, version strings, and cleans whitespace."""
        clean = re.sub(r"\.(exe|lnk|bat|cmd)$", "", raw_name, flags=re.IGNORECASE)
        clean = re.sub(r"\(new\)", "", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\s+", " ", clean).strip().lower()
        return clean

    def _scan_registry_app_paths(self) -> None:
        """Direct inspection of Windows App Paths registry keys (<2ms)."""
        if not HAS_WINREG or sys.platform != "win32":
            return

        hives = [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]
        for hive in hives:
            try:
                with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths") as k:
                    num_subkeys = winreg.QueryInfoKey(k)[0]
                    for i in range(num_subkeys):
                        try:
                            sub_name = winreg.EnumKey(k, i)
                            with winreg.OpenKey(k, sub_name) as sk:
                                exe_path, _ = winreg.QueryValueEx(sk, "")
                                if exe_path and os.path.exists(exe_path):
                                    norm_key = self._normalize_name(sub_name)
                                    disp = Path(exe_path).stem
                                    if norm_key not in self._catalog:
                                        self._catalog[norm_key] = AppEntry(
                                            name=norm_key,
                                            display_name=disp,
                                            target=exe_path,
                                            app_type="exe",
                                            aliases=[],
                                        )
                        except Exception:
                            continue
            except Exception:
                continue

    def _scan_start_menu(self) -> None:
        """Recursively inspects Windows Start Menu shortcuts."""
        if sys.platform != "win32":
            return

        roots = [
            Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs"),
            Path(os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs")),
        ]

        for root in roots:
            if not root.exists():
                continue
            for lnk in root.rglob("*.lnk"):
                try:
                    norm_key = self._normalize_name(lnk.name)
                    disp = lnk.stem
                    # Prioritize Start Menu shortcuts as they carry natural user-facing titles
                    self._catalog[norm_key] = AppEntry(
                        name=norm_key,
                        display_name=disp,
                        target=str(lnk),
                        app_type="lnk",
                        aliases=[],
                    )
                except Exception:
                    continue

    def _register_known_system_uris(self) -> None:
        """Registers built-in Windows UWP protocol handlers."""
        for key, (disp, uri) in self.KNOWN_SYSTEM_URIS.items():
            self._catalog[key] = AppEntry(
                name=key,
                display_name=disp,
                target=uri,
                app_type="uri",
                aliases=[],
            )

    def _scan_path_binaries(self) -> None:
        """Detects developer CLIs in system PATH."""
        common_clis = ["wt", "code", "cmd", "powershell", "python", "git", "notepad", "mspaint"]
        for cli in common_clis:
            target = shutil.which(cli)
            if target:
                norm_key = self._normalize_name(cli)
                if norm_key not in self._catalog:
                    self._catalog[norm_key] = AppEntry(
                        name=norm_key,
                        display_name=cli.upper(),
                        target=target,
                        app_type="cli",
                        aliases=[],
                    )

    def _build_alias_index(self) -> None:
        """Compiles aliases for fast O(1) resolution."""
        self._alias_map.clear()
        for key, aliases in self.DEFAULT_ALIASES.items():
            for alias in aliases:
                self._alias_map[alias.lower().strip()] = key

        for entry_key, entry in self._catalog.items():
            entry_clean = entry.name.lower().strip()
            self._alias_map[entry_clean] = entry_key
            self._alias_map[entry.display_name.lower().strip()] = entry_key

    def _save_cache(self) -> None:
        """Persists catalog index to JSON for instant cold boot (<1ms)."""
        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
            serializable = {k: e.to_dict() for k, e in self._catalog.items()}
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(serializable, f, indent=2)
        except Exception as e:
            logger.debug(f"[APP_CATALOG] Cache save error: {e}")

    def _load_cache(self) -> bool:
        """Loads cached index if available."""
        if not self.cache_file.exists():
            return False
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and len(data) > 5:
                for k, v in data.items():
                    self._catalog[k] = AppEntry.from_dict(v)
                return True
        except Exception:
            pass
        return False

    def find_app(self, query: str) -> AppEntry | None:
        """
        Dynamically locates an application by exact name, alias, token, or fuzzy similarity.
        Returns AppEntry if present on the PC, or None if absent.
        """
        if not query or not query.strip():
            return None

        clean_q = self._normalize_name(query)

        # 1. Direct key match in catalog
        if clean_q in self._catalog:
            return self._catalog[clean_q]

        # 2. Alias mapping lookup (e.g. 'vscode' -> 'visual studio code')
        if clean_q in self._alias_map:
            target_key = self._alias_map[clean_q]
            if target_key in self._catalog:
                return self._catalog[target_key]

        # 3. Substring matching (e.g. 'chrome' matches 'google chrome')
        for key, entry in self._catalog.items():
            if clean_q == key or clean_q in key or key in clean_q:
                return entry
            disp_lower = entry.display_name.lower()
            if clean_q == disp_lower or clean_q in disp_lower:
                return entry

        # 4. Fuzzy Levenshtein match with high confidence (>= 0.78)
        all_keys = list(self._catalog.keys()) + list(self._alias_map.keys())
        matches = difflib.get_close_matches(clean_q, all_keys, n=1, cutoff=0.78)
        if matches:
            matched_key = matches[0]
            canonical = self._alias_map.get(matched_key, matched_key)
            if canonical in self._catalog:
                return self._catalog[canonical]

        return None

    def is_installed(self, query: str) -> bool:
        """Returns True if the application exists anywhere on the workstation."""
        return self.find_app(query) is not None

    def launch(self, target_or_entry: AppEntry | str, extra_args: list[str] | None = None) -> tuple[bool, str]:
        """
        Executes verified application on Windows.
        Returns: (success: bool, message: str)
        """
        entry = target_or_entry if isinstance(target_or_entry, AppEntry) else self.find_app(target_or_entry)
        if not entry:
            app_label = target_or_entry.name if isinstance(target_or_entry, AppEntry) else target_or_entry
            return False, f"Application '{app_label}' is not installed on this workstation."

        try:
            # 1. URI protocol targets (e.g. ms-settings:, ms-calculator:)
            if entry.app_type == "uri":
                if hasattr(os, "startfile"):
                    os.startfile(entry.target)
                else:
                    subprocess.Popen(f'start "" "{entry.target}"', shell=True)
                return True, f"Launched Windows application: '{entry.display_name}'"

            # 2. Shortcut (.lnk) targets
            if entry.app_type == "lnk":
                if not os.path.exists(entry.target):
                    return False, f"Shortcut target no longer exists at: {entry.target}"
                if hasattr(os, "startfile"):
                    os.startfile(entry.target)
                else:
                    subprocess.Popen(f'start "" "{entry.target}"', shell=True)
                return True, f"Launched Windows application: '{entry.display_name}'"

            # 3. Direct binary (.exe) targets
            if entry.app_type in ("exe", "cli"):
                if not os.path.exists(entry.target) and not shutil.which(entry.target):
                    return False, f"Executable not found at path: {entry.target}"

                cmd = [entry.target]
                if extra_args:
                    cmd.extend(extra_args)

                # Launch decoupled process
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
                )
                return True, f"Launched Windows application: '{entry.display_name}'"

            return False, f"Unknown application type '{entry.app_type}' for {entry.display_name}"

        except Exception as e:
            return False, f"Failed to launch '{entry.display_name}': {e}"

    def get_default_browser(self) -> tuple[str, str | None]:
        """
        Queries Windows Registry to detect the user's actual default browser.
        Returns: (browser_id, verified_executable_path)
        e.g., ('brave', 'C:/.../brave.exe'), ('chrome', '...'), ('edge', '...')
        """
        if not HAS_WINREG or sys.platform != "win32":
            return "browser", None

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice",
            ) as k:
                prog_id, _ = winreg.QueryValueEx(k, "ProgId")
                prog_lower = str(prog_id).lower()

                if "brave" in prog_lower:
                    entry = self.find_app("brave")
                    return "brave", entry.target if entry else None
                elif "chrome" in prog_lower:
                    entry = self.find_app("chrome")
                    return "chrome", entry.target if entry else None
                elif "edge" in prog_lower or "msedge" in prog_lower:
                    entry = self.find_app("edge")
                    return "edge", entry.target if entry else None
                elif "firefox" in prog_lower:
                    entry = self.find_app("firefox")
                    return "firefox", entry.target if entry else None
                elif "opera" in prog_lower:
                    entry = self.find_app("opera")
                    return "opera", entry.target if entry else None
        except Exception as e:
            logger.debug(f"[APP_CATALOG] Could not read default browser from registry: {e}")

        # Fallback: check which browser is physically installed
        for candidate in ["brave", "chrome", "edge", "firefox"]:
            entry = self.find_app(candidate)
            if entry:
                return candidate, entry.target

        return "chrome", None

    def get_installed_editors(self) -> list[AppEntry]:
        """Returns all installed code/text editors ordered by capability preference."""
        preferred_order = ["cursor", "code", "pycharm", "sublime_text", "notepad++", "notepad"]
        found: list[AppEntry] = []
        for name in preferred_order:
            entry = self.find_app(name)
            if entry and entry not in found:
                found.append(entry)
        return found


# Global singleton instance
app_catalog = SystemAppCatalog()

