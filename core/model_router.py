"""
Low-RAM Multi-LLM Dynamic Routing Engine for SpaceV.
Automatically classifies user intent and routes tasks to the lightest,
most capable specialized model available while enforcing RAM/VRAM auto-unloading.
"""

import requests

from config import (
    CODER_MODEL,
    FALLBACK_MODEL,
    FAST_CHAT_MODEL,
    LOW_RAM_MODE,
    OLLAMA_BASE_URL,
    OLLAMA_KEEP_ALIVE,
    PRIMARY_MODEL,
    UI_TARS_MODEL,
    UI_TARS_MODEL_2B,
    VISION_MODEL,
)

# Role Constants
ROLE_FAST_CHAT = "chat"          # Lightweight fast conversational brain (3B)
ROLE_CODER_TOOLS = "coder_tools" # Deep reasoning, tool calling, code generation (7B)
ROLE_VISION = "vision"           # Screen perception & visual OCR
ROLE_GUI_NAVIGATOR = "gui_navigation" # UI-TARS OSWorld SOTA computer control & mouse navigation (2B/7B)
ROLE_PRIMARY = "primary"         # Generalist orchestrator


class MultiModelRouter:
    """
    Intelligent Multi-LLM Router that selects optimal models per query
    to maximize reasoning capability while preserving workstation RAM.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.installed_models: list[str] = []
            cls._instance.refresh_installed_models()
        return cls._instance

    def refresh_installed_models(self) -> list[str]:
        """Probes the local Ollama API to detect which models are installed."""
        try:
            res = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
            if res.status_code == 200:
                self.installed_models = [m.get("name", "") for m in res.json().get("models", [])]
        except Exception:
            self.installed_models = []
        return self.installed_models

    def is_model_installed(self, model_tag: str) -> str | None:
        """Checks if a model tag or prefix exists in local Ollama installation."""
        if not self.installed_models:
            return None
        # Exact match
        if model_tag in self.installed_models:
            return model_tag
        # Prefix match (e.g. 'qwen2.5:7b' matches 'qwen2.5:7b-instruct-q5_0')
        prefix = model_tag.split(":")[0]
        for m in self.installed_models:
            if prefix in m:
                return m
        return None

    def needs_tools(self, prompt: str) -> bool:
        """
        Determines if the query requires tool calling schemas attached.
        Pure chit-chat greetings stay fast; all actionable, computational, or system queries
        are empowered with the full tool calling schema.
        """
        text = prompt.lower().strip()
        pure_chat_greetings = {
            "hi", "hello", "hey", "yo", "sup", "good morning", "good evening",
            "good afternoon", "how are you", "who are you", "what is your name",
            "thank you", "thanks", "bye", "goodbye", "how are you doing"
        }
        if text in pure_chat_greetings:
            return False

        return True

    def classify_intent(self, prompt: str, has_tools: bool = False, has_images: bool = False) -> str:
        """
        Classifies user prompt into the most cost-effective specialized role.
        """
        if has_images:
            return ROLE_VISION

        text = prompt.lower().strip()

        # 1. Vision & Screen reading intents
        if any(k in text for k in ["look at my screen", "read my screen", "what is on screen", "ocr", "read image", "see what is going in the desktop", "see what is on the desktop"]):
            return ROLE_VISION

        # 1.5 UI-TARS Autonomous Computer Control & Mouse Navigation
        if any(k in text for k in ["navigate and click", "click on the icon", "ui-tars", "mouse navigation", "computer control", "gui action", "click button at"]):
            return ROLE_GUI_NAVIGATOR

        # 2. Coding, Scripting & Complex Tool Execution
        if has_tools or self.needs_tools(prompt):
            return ROLE_CODER_TOOLS

        # 3. Fast Conversational, Summarization, Greetings, Q&A
        return ROLE_FAST_CHAT

    def select_model(self, prompt: str, requires_tools: bool = False, requires_vision: bool = False) -> tuple[str, str]:
        """
        Resolves the optimal local model and role tag for the request.
        Returns: (model_name, role_name)
        """
        role = self.classify_intent(prompt, has_tools=requires_tools, has_images=requires_vision)

        # 1. Try resolving preferred role model
        target_candidate = None
        if role == ROLE_GUI_NAVIGATOR:
            target_candidate = self.is_model_installed(UI_TARS_MODEL) or self.is_model_installed(UI_TARS_MODEL_2B) or self.is_model_installed(VISION_MODEL)
        elif role == ROLE_VISION:
            target_candidate = self.is_model_installed(VISION_MODEL)
        elif role == ROLE_CODER_TOOLS:
            target_candidate = self.is_model_installed(CODER_MODEL) or self.is_model_installed(PRIMARY_MODEL)
        elif role == ROLE_FAST_CHAT and LOW_RAM_MODE:
            target_candidate = self.is_model_installed(FAST_CHAT_MODEL)

        if target_candidate:
            return target_candidate, role


        # 2. Fallback to Primary Model
        primary_match = self.is_model_installed(PRIMARY_MODEL)
        if primary_match:
            return primary_match, ROLE_PRIMARY

        # 3. Fallback to Fallback Model
        fallback_match = self.is_model_installed(FALLBACK_MODEL)
        if fallback_match:
            return fallback_match, "fallback"

        # 4. Fallback to any installed model
        if self.installed_models:
            return self.installed_models[0], "installed_default"

        # 5. Default string if Ollama is not yet started
        return PRIMARY_MODEL, "default"

    @staticmethod
    def get_cloud_provider_fallback_chain() -> list[str]:
        """Returns the priority cloud provider fallback chain."""
        from core.provider_failover import DEFAULT_FAILOVER_CASCADE
        return list(DEFAULT_FAILOVER_CASCADE)

    def select_healthy_cloud_provider(self, preferred: str = "groq") -> str:
        """Selects the first cloud provider in the fallback chain that is currently under rate limits."""
        from core.rate_limiter import rate_limiter
        chain = self.get_cloud_provider_fallback_chain()
        if preferred in chain and rate_limiter.is_available(preferred):
            return preferred
        for provider in chain:
            if rate_limiter.is_available(provider):
                return provider
        return "ollama"

# Global singleton router
model_router = MultiModelRouter()
