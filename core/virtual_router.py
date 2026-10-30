"""
SpaceV Virtual Model Router & Unified Provider Mesh Resolver.
Enables virtual aliases:
  - spacev/auto  -> Dynamically evaluates task intent and routes to best free provider
  - spacev/fast  -> Ultra-low latency streaming (< 300ms, Groq/Cerebras)
  - spacev/coder -> Code generation and debugging specialist (Codestral / Qwen-Coder)
  - spacev/smart -> Deep reasoning and 1M+ token context (Gemini / DeepSeek-V3 / SambaNova)
Loads structured configuration from config/providers.yaml with seamless .env fallback.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("SpaceV.VirtualRouter")

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config" / "providers.yaml"


class VirtualModelRouter:
    """
    Manages virtual model aliases, role mappings, and key pools from config/providers.yaml.
    """

    def __init__(self, config_path: Path | str | None = None):
        self.config_path = Path(config_path or os.getenv("CONFIG_PATH", DEFAULT_CONFIG_PATH))
        self.config: dict[str, Any] = self._load_yaml()

    def _load_yaml(self) -> dict[str, Any]:
        """Loads and parses the YAML configuration file safely."""
        if not self.config_path.exists():
            return {}
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning(f"[VIRTUAL_ROUTER] Failed to load {self.config_path}: {e}")
            return {}

    def reload(self) -> None:
        """Reloads the YAML configuration from disk."""
        self.config = self._load_yaml()

    def is_virtual_alias(self, model_name: str | None) -> bool:
        """Checks if a model string is a virtual alias."""
        if not model_name:
            return False
        clean = model_name.strip().lower()
        return clean.startswith("spacev/") or clean in ("auto", "fast", "smart", "coder")

    def resolve_alias(
        self,
        alias_or_model: str,
        prompt: str = "",
        tools: list[dict[str, Any]] | None = None,
    ) -> str:
        """
        Resolves a virtual alias (e.g. spacev/auto) into a concrete category alias
        ('spacev/fast', 'spacev/coder', 'spacev/smart') or leaves concrete model strings untouched.
        """
        if not self.is_virtual_alias(alias_or_model):
            return alias_or_model

        clean = alias_or_model.strip().lower()
        if clean in ("spacev/auto", "auto"):
            prompt_lower = (prompt or "").lower()
            # 1. Coding Task Detection
            code_keywords = [
                "def ", "class ", "import ", "python", "javascript", "typescript",
                "bash", "terminal", "compile", "bug", "traceback", "exception",
                "function", "refactor", "unit test", "pytest", "sql", "git "
            ]
            if any(k in prompt_lower for k in code_keywords):
                return "spacev/coder"

            # 2. Vision / Deep Reasoning Detection
            vision_keywords = ["screenshot", "screen", "look at", "see my desktop", "image", "vision", "window", "gui"]
            if any(k in prompt_lower for k in vision_keywords) or len(prompt) > 4000:
                return "spacev/smart"

            # 3. Default Fast Response
            return "spacev/fast"

        # Normalize shortcuts
        if clean in ("fast", "spacev/fast"):
            return "spacev/fast"
        if clean in ("coder", "spacev/coder"):
            return "spacev/coder"
        if clean in ("smart", "spacev/smart"):
            return "spacev/smart"

        return alias_or_model

    def get_preferred_providers(self, resolved_alias: str) -> list[str]:
        """
        Returns the preferred provider order for a resolved alias from config/providers.yaml.
        """
        aliases_cfg = self.config.get("aliases", {})
        if resolved_alias in aliases_cfg:
            return list(aliases_cfg[resolved_alias].get("preferred_providers", []))

        # Default fallbacks if YAML is missing alias section
        defaults = {
            "spacev/fast": ["cerebras", "groq", "ollama"],
            "spacev/coder": ["mistral", "groq", "ollama"],
            "spacev/smart": ["gemini", "sambanova", "groq", "ollama"],
        }
        return defaults.get(resolved_alias, ["groq", "cerebras", "gemini", "ollama"])

    def get_provider_keys(self, provider_name: str) -> list[str]:
        """Extracts list of API keys for a specific provider from config/providers.yaml."""
        prov = self.config.get("providers", {}).get(provider_name.lower(), {})
        keys = prov.get("keys", [])
        if isinstance(keys, list):
            return [str(k).strip() for k in keys if k and str(k).strip() and not str(k).startswith("csk-your-")]
        return []

    def get_provider_models(self, provider_name: str) -> dict[str, str]:
        """Returns configured models for a provider (e.g. fast_model, smart_model, coder_model)."""
        prov = self.config.get("providers", {}).get(provider_name.lower(), {})
        models = {}
        for key in ["fast_model", "smart_model", "coder_model"]:
            if key in prov:
                models[key] = str(prov[key])
        return models

    def get_role_model(self, role: str) -> str:
        """Returns the assigned model for a specific role (e.g., coder, vision, fast_chat)."""
        roles = self.config.get("roles", {})
        return str(roles.get(role, ""))


# Global singleton instance
virtual_router = VirtualModelRouter()

