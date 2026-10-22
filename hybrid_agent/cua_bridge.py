"""
Cua Sandbox Bridge for SpaceV Hybrid Agent.
Connects to D:\\agentSpace\\cua and the in-guest `cua-spacesd` daemon (port 3211).
Enables the agent to target isolated VM sandboxes or fall back to local stealth execution.
"""
from __future__ import annotations

import logging
import socket
from typing import Optional, Dict, Any

import requests

logger = logging.getLogger("SpaceV.CuaBridge")

DEFAULT_CUA_SPACESD_URL = "http://localhost:3211"


class CuaSandboxBridge:
    """
    Manages communication with Cua Spaces and the local cua-spacesd daemon.
    """

    def __init__(self, endpoint: str = DEFAULT_CUA_SPACESD_URL):
        self.endpoint = endpoint
        self._is_available: Optional[bool] = None

    def check_availability(self) -> bool:
        """Checks if cua-spacesd is listening on port 3211."""
        try:
            with socket.create_connection(("localhost", 3211), timeout=0.8):
                self._is_available = True
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            self._is_available = False
            return False

    @property
    def is_connected(self) -> bool:
        if self._is_available is None:
            return self.check_availability()
        return self._is_available

    def get_status(self) -> Dict[str, Any]:
        """Queries health status of the Cua daemon."""
        if not self.check_availability():
            return {
                "connected": False,
                "message": "Cua sandbox daemon (cua-spacesd) not detected on port 3211. Using local stealth execution."
            }

        try:
            resp = requests.get(f"{self.endpoint}/health", timeout=1.5)
            return {
                "connected": True,
                "status_code": resp.status_code,
                "endpoint": self.endpoint,
                "mode": "Cua Sandbox (Isolated Micro-VM)"
            }
        except Exception as e:
            return {"connected": False, "error": str(e)}


# Global instance
cua_bridge = CuaSandboxBridge()
