"""
Colibrì On-Device MoE Inference Engine Client for SpaceV.
Bridges SpaceV directly to the local Colibrì engine (D:/agentSpace/eto/colibri),
enabling NVMe streaming and CPU execution of large MoE models with zero cloud API token cost.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger("spacev.colibri")

COLIBRI_DIR = Path("D:/agentSpace/eto/colibri")
COLIBRI_CMD = COLIBRI_DIR / "c" / "coli.cmd"
COLIBRI_CLI = COLIBRI_DIR / "c" / "coli"
DEFAULT_BASE_URL = "http://127.0.0.1:8080/v1"


class ColibriClient:
    """
    OpenAI-compatible client bridge for the on-device Colibrì streaming MoE engine.
    Allows zero-token offline reasoning using asynchronously prefetched expert weights.
    """

    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def is_installed(self) -> bool:
        """Verifies if Colibrì repository and core binaries exist locally."""
        if not COLIBRI_DIR.exists():
            return False
        return (
            (COLIBRI_DIR / "c" / "coli.cmd").exists()
            or (COLIBRI_DIR / "c" / "coli").exists()
            or (COLIBRI_DIR / "c" / "colibri.c").exists()
        )

    def is_server_running(self, base_url: str | None = None) -> bool:
        """Probes the Colibrì local server for readiness (0.5s timeout)."""
        target_url = (base_url or self.base_url).rstrip("/")
        try:
            res = requests.get(f"{target_url}/models", timeout=0.5)
            return res.status_code == 200
        except Exception:
            try:
                res = requests.get(f"{target_url}/health", timeout=0.5)
                return res.status_code == 200
            except Exception:
                return False

    def get_available_models(self, base_url: str | None = None) -> list[str]:
        """Returns detected models from running Colibrì instance or known default profiles."""
        target_url = (base_url or self.base_url).rstrip("/")
        try:
            res = requests.get(f"{target_url}/models", timeout=1.0)
            if res.status_code == 200:
                data = res.json()
                models = data.get("data", [])
                names = [m.get("id", "") for m in models if isinstance(m, dict) and "id" in m]
                if names:
                    return names
        except Exception:
            pass

        return ["colibri-moe-744b", "colibri-qwen3-coder-30b"]

    def chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        base_url: str | None = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        """
        Executes a standard OpenAI-compatible chat completion on the local Colibrì daemon.
        """
        target_url = (base_url or self.base_url).rstrip("/")
        selected_model = model or "colibri-moe-744b"

        payload: dict[str, Any] = {
            "model": selected_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if tools:
            payload["tools"] = tools

        try:
            res = requests.post(
                f"{target_url}/chat/completions",
                json=payload,
                timeout=self.timeout,
            )
            if res.status_code == 200:
                return res.json()
            else:
                logger.warning(
                    f"[COLIBRI] Server returned status {res.status_code}: {res.text[:200]}"
                )
                return {
                    "error": {
                        "message": f"Colibri returned HTTP {res.status_code}",
                        "code": res.status_code,
                    }
                }
        except Exception as e:
            logger.debug(f"[COLIBRI] Request error: {e}")
            return {
                "error": {
                    "message": f"Colibri connection failed: {e}",
                    "code": "connection_error",
                }
            }


# Singleton instance
colibri_client = ColibriClient()

