"""
Configuration settings for SpaceV Cybernetic Desktop AI Agent.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
# 1. Load .env if present (never breaks if .env is missing)
load_dotenv(BASE_DIR / ".env")

# 1.1 Load structured provider configuration from config/providers.yaml if present
_yaml_config_path = BASE_DIR / os.getenv("CONFIG_PATH", "config/providers.yaml")
_yaml_data = {}
if _yaml_config_path.exists():
    try:
        import yaml

        with open(_yaml_config_path, "r", encoding="utf-8") as _yf:
            _yaml_data = yaml.safe_load(_yf) or {}
    except Exception:
        pass
_yaml_providers = _yaml_data.get("providers", {})
_yaml_roles = _yaml_data.get("roles", {})
_yaml_ollama = _yaml_data.get("ollama", {})

# 2. LLM configuration. Blank provider means the configured endpoint speaks the
# OpenAI-compatible chat-completions protocol (for example, a local proxy).
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
_configured_llm_provider = os.getenv("LLM_PROVIDER", "").strip().lower()
if _configured_llm_provider in ("", "auto"):
    # With credentials configured, a blank provider selects the common proxy/API
    # protocol. With no credentials, retain the safe local Ollama default.
    LLM_PROVIDER = "openai_compatible" if LLM_API_KEY else "ollama"
elif _configured_llm_provider in ("openai-compatible", "compatible", "proxy"):
    LLM_PROVIDER = "openai_compatible"
elif _configured_llm_provider == "google":
    LLM_PROVIDER = "gemini"
elif _configured_llm_provider == "claude":
    LLM_PROVIDER = "anthropic"
else:
    LLM_PROVIDER = _configured_llm_provider

_default_llm_base_urls = {
    "ollama": "https://openrouter.ai/api/v1",
    "openai_compatible": "http://127.0.0.1:8000/v1",
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "anthropic": "https://api.anthropic.com/v1",
}
LLM_BASE_URL = (
    os.getenv("LLM_BASE_URL", "").strip()
    or _default_llm_base_urls.get(LLM_PROVIDER, "https://openrouter.ai/api/v1")
).rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()

# Multi-Cloud Frontier Providers (100% Free Tiers - Zero Card Required)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", LLM_API_KEY)
GROQ_API_KEY_2 = os.getenv("GROQ_API_KEY_2", "")
GROQ_API_KEY_3 = os.getenv("GROQ_API_KEY_3", "")
GROQ_API_KEY_4 = os.getenv("GROQ_API_KEY_4", "")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_FAST_MODEL = os.getenv("GROQ_FAST_MODEL", "openai/gpt-oss-20b")

# Parse multi-account key pools (comma-separated or distinct env vars)
_raw_groq_keys = os.getenv("GROQ_API_KEYS", "")
GROQ_API_KEYS = [k.strip() for k in _raw_groq_keys.split(",") if k.strip()] if _raw_groq_keys else []
for _k in [GROQ_API_KEY, GROQ_API_KEY_2, GROQ_API_KEY_3, GROQ_API_KEY_4]:
    if _k and _k not in GROQ_API_KEYS:
        GROQ_API_KEYS.append(_k)
# Supplement from config/providers.yaml if present
for _k in _yaml_providers.get("groq", {}).get("keys", []):
    if _k and str(_k).strip() and str(_k).strip() not in GROQ_API_KEYS:
        GROQ_API_KEYS.append(str(_k).strip())

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_API_KEY_2 = os.getenv("GEMINI_API_KEY_2", "")
GEMINI_API_KEY_3 = os.getenv("GEMINI_API_KEY_3", "")
GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai").rstrip("/")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

_raw_gemini_keys = os.getenv("GEMINI_API_KEYS", "")
GEMINI_API_KEYS = [k.strip() for k in _raw_gemini_keys.split(",") if k.strip()] if _raw_gemini_keys else []
for _k in [GEMINI_API_KEY, GEMINI_API_KEY_2, GEMINI_API_KEY_3]:
    if _k and _k not in GEMINI_API_KEYS:
        GEMINI_API_KEYS.append(_k)
for _k in _yaml_providers.get("gemini", {}).get("keys", []):
    if _k and str(_k).strip() and str(_k).strip() not in GEMINI_API_KEYS:
        GEMINI_API_KEYS.append(str(_k).strip())

SAMBANOVA_API_KEY = os.getenv("SAMBANOVA_API_KEY", "")
SAMBANOVA_BASE_URL = os.getenv("SAMBANOVA_BASE_URL", "https://api.sambanova.ai/v1").rstrip("/")
SAMBANOVA_MODEL = os.getenv("SAMBANOVA_MODEL", "DeepSeek-V3.1")
if not SAMBANOVA_API_KEY and _yaml_providers.get("sambanova", {}).get("keys"):
    SAMBANOVA_API_KEY = str(_yaml_providers["sambanova"]["keys"][0]).strip()

CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY", "")
CEREBRAS_API_KEY_2 = os.getenv("CEREBRAS_API_KEY_2", "")
CEREBRAS_BASE_URL = os.getenv("CEREBRAS_BASE_URL", "https://api.cerebras.ai/v1").rstrip("/")
CEREBRAS_MODEL = os.getenv("CEREBRAS_MODEL", "llama3.1-70b")
CEREBRAS_FAST_MODEL = os.getenv("CEREBRAS_FAST_MODEL", "llama3.1-8b")

_raw_cerebras_keys = os.getenv("CEREBRAS_API_KEYS", "")
CEREBRAS_API_KEYS = [k.strip() for k in _raw_cerebras_keys.split(",") if k.strip()] if _raw_cerebras_keys else []
for _k in [CEREBRAS_API_KEY, CEREBRAS_API_KEY_2]:
    if _k and _k not in CEREBRAS_API_KEYS:
        CEREBRAS_API_KEYS.append(_k)
for _k in _yaml_providers.get("cerebras", {}).get("keys", []):
    if _k and str(_k).strip() and not str(_k).startswith("csk-your-") and str(_k).strip() not in CEREBRAS_API_KEYS:
        CEREBRAS_API_KEYS.append(str(_k).strip())

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
MISTRAL_API_KEY_2 = os.getenv("MISTRAL_API_KEY_2", "")
MISTRAL_BASE_URL = os.getenv("MISTRAL_BASE_URL", "https://api.mistral.ai/v1").rstrip("/")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "codestral-latest")
MISTRAL_SMALL_MODEL = os.getenv("MISTRAL_SMALL_MODEL", "mistral-small-latest")

_raw_mistral_keys = os.getenv("MISTRAL_API_KEYS", "")
MISTRAL_API_KEYS = [k.strip() for k in _raw_mistral_keys.split(",") if k.strip()] if _raw_mistral_keys else []
for _k in [MISTRAL_API_KEY, MISTRAL_API_KEY_2]:
    if _k and _k not in MISTRAL_API_KEYS:
        MISTRAL_API_KEYS.append(_k)
for _k in _yaml_providers.get("mistral", {}).get("keys", []):
    if _k and str(_k).strip() and str(_k).strip() not in MISTRAL_API_KEYS:
        MISTRAL_API_KEYS.append(str(_k).strip())

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_API_KEY_2 = os.getenv("OPENROUTER_API_KEY_2", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "z-ai/glm-5.3-flash")

_raw_openrouter_keys = os.getenv("OPENROUTER_API_KEYS", "")
OPENROUTER_API_KEYS = [k.strip() for k in _raw_openrouter_keys.split(",") if k.strip()] if _raw_openrouter_keys else []
for _k in [OPENROUTER_API_KEY, OPENROUTER_API_KEY_2]:
    if _k and _k not in OPENROUTER_API_KEYS:
        OPENROUTER_API_KEYS.append(_k)

ZAI_API_KEY = os.getenv("ZAI_API_KEY", "")
ZAI_BASE_URL = os.getenv("ZAI_BASE_URL", "https://api.z.ai/api/coding/paas/v4").rstrip("/")
ZAI_MODEL = os.getenv("ZAI_MODEL", "glm-5.3-flash")

# Local Multi-Model Tiers (Ollama)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", str(_yaml_ollama.get("base_url", "http://localhost:11434")))
FAST_CHAT_MODEL = os.getenv("FAST_CHAT_MODEL", str(_yaml_roles.get("fast_chat", "qwen2.5:3b")))
PRIMARY_MODEL = os.getenv("PRIMARY_MODEL", "qwen2.5:3b")
CODER_MODEL = os.getenv("CODER_MODEL", str(_yaml_roles.get("coder", "qwen2.5-coder:7b")))
VISION_MODEL = os.getenv("VISION_MODEL", str(_yaml_roles.get("vision", "moondream:latest")))
UI_TARS_MODEL = os.getenv("UI_TARS_MODEL", str(_yaml_roles.get("ui_tars", "ui-tars:7b")))
UI_TARS_MODEL_2B = os.getenv("UI_TARS_MODEL_2B", "ui-tars:2b")
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "qwen2.5:7b-instruct-q5_0")
# 3. Settings
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
LOW_RAM_MODE = os.getenv("LOW_RAM_MODE", "true").lower() in ("true", "1", "yes")

USER_DESKTOP_DIR = Path(os.path.expanduser("~")) / "Desktop"
MEMORY_FILE = BASE_DIR / "spacev_memory.json"


# Neural Voice Configuration
USE_NEURAL_TTS = True  # Uses high-fidelity realistic Azure Neural Voice with offline SAPI5 fallback
TTS_NEURAL_VOICE = "en-US-AriaNeural"  # High-fidelity natural lady AI voice (warm, conversational, Gemini/Siri style)


# Tool Virtualization & Code Mode (Cloudflare MCP Pattern: 81% token reduction)
ENABLE_CODE_MODE = os.getenv("SPACEV_CODE_MODE", "true").lower() == "true"

# UI & Agent Configuration
APP_NAME = "SpaceV"
WAKE_WORDS = ["hey spacev", "spacev", "space v", "hey space v", "hey space"]
BUBBLE_SIZE = 64  # Size in pixels of the floating Arc Reactor bubble
CHAT_WIDTH = 500
CHAT_HEIGHT = 620
DEFAULT_CURSOR_SPEED = "1.0x"  # Relative desktop input speed options are 0.1x, 0.3x, 0.5x, 0.8x, and 1.0x

# Proactive Companion Settings (Continuous Interaction & Check-Ins)
COMPANION_MODE_DEFAULT = True
COMPANION_CHECKIN_INTERVAL_SEC = 240  # 4 minutes idle before gentle check-in
AUTO_LISTEN_FOLLOWUP = True  # Auto-listen after SpaceV asks questions or checks in
WAKE_WORD_ENABLED_BY_DEFAULT = True  # Hands-free 'Hey SpaceV' active by default

# Visual Styling / Theme (Cosmic Cybernetic Glassmorphism)
THEME = {
    "primary_glow": "#00f0ff",  # Cyan neon glow
    "secondary_glow": "#8b5cf6",  # Electric violet accent
    "bg_dark": "#0a0e17",  # Deep rich dark background
    "bg_card": "#121824",  # Sleek elevated card surface
    "bg_glass": "rgba(18, 24, 36, 0.95)",  # Glassmorphic panel
    "text_primary": "#f8fafc",  # Crisp high-contrast white text
    "text_secondary": "#94a3b8",  # Muted secondary text
    "bubble_user": "#0284c7",  # Refined cyber blue for user
    "bubble_agent": "#141c2b",  # Deep sleek card bubble for agent
    "border_color": "#1f2a3e",  # Subtle dark slate border
    "accent_green": "#10b981",  # Emerald active indicator
}
