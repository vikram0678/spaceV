"""
SpaceV Web Subsystem: Direct CDP Remote Debugging Port Bridge.
Engineered from Browser-Use architecture to control existing authenticated user browser sessions.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class BrowserTarget:
    target_id: str
    title: str
    url: str
    type: str
    ws_debugger_url: Optional[str] = None


class CDPBridge:
    """
    Connects to an existing Chrome/Edge instance launched with --remote-debugging-port=9222.
    Enables SpaceV to interact with the user's active, authenticated tabs.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 9222, timeout: float = 2.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.base_url = f"http://{host}:{port}"

    def is_browser_available(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.base_url}/json/version", method="GET")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status == 200
        except Exception:
            return False

    def get_version(self) -> Optional[Dict[str, Any]]:
        try:
            req = urllib.request.Request(f"{self.base_url}/json/version", method="GET")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None
        return None

    def list_targets(self) -> List[BrowserTarget]:
        try:
            req = urllib.request.Request(f"{self.base_url}/json/list", method="GET")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status == 200:
                    raw_targets = json.loads(resp.read().decode("utf-8"))
                    targets = []
                    for t in raw_targets:
                        targets.append(
                            BrowserTarget(
                                target_id=t.get("id", ""),
                                title=t.get("title", ""),
                                url=t.get("url", ""),
                                type=t.get("type", "page"),
                                ws_debugger_url=t.get("webSocketDebuggerUrl"),
                            )
                        )
                    return targets
        except Exception:
            return []
        return []

    def get_active_page(self) -> Optional[BrowserTarget]:
        targets = self.list_targets()
        for t in targets:
            if t.type == "page" and not t.url.startswith("chrome-extension://"):
                return t
        return targets[0] if targets else None
