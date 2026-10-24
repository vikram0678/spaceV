"""
Configuration settings for SpaceV Cybernetic Desktop AI Agent.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
# 1. Load .env if present (never breaks if .env is missing)

load_dotenv(BASE_DIR / ".env")
# 2. Dual-Brain Provider & Multi-LLM Configuration with Safe Defaults
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")

# Universal Brain Routing Mode
# Options:
#   "hybrid"    -> Try paid primary model first; if 429/402, automatically fall over to Free Mesh
#   "direct"    -> Directly use single configured LLM_API_KEY / provider (BYOK Paid Mode)
#   "free_mesh" -> Multiplex across 15 free tiers with round-robin multi-account rotation
#   "local"     -> 100% offline Local Ollama only
ROUTING_MODE = os.getenv("ROUTING_MODE", "hybrid").lower()

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

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_API_KEY_2 = os.getenv("GEMINI_API_KEY_2", "")
GEMINI_API_KEY_3 = os.getenv("GEMINI_API_KEY_3", "")
GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai").rstrip("/")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

_raw_gemini_keys = os.getenv("GEMINI_API_KEYS", "")
GEMINI_API_KEYS = [k.strip() for k in _raw_gemini_keys.split(",") if k.strip()] if _raw_gemini_keys else []
for _k in [GEMINI_API_KEY, GEMINI_API_KEY_2, GEMINI_API_KEY_3]:
    if _k and _k not in GEMINI_API_KEYS:
        GEMINI_API_KEYS.append(_k)

SAMBANOVA_API_KEY = os.getenv("SAMBANOVA_API_KEY", "")
SAMBANOVA_BASE_URL = os.getenv("SAMBANOVA_BASE_URL", "https://api.sambanova.ai/v1").rstrip("/")
SAMBANOVA_MODEL = os.getenv("SAMBANOVA_MODEL", "DeepSeek-V3.1")

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

# Frontier Cloud Model Roles
AUTONOMOUS_AGENT_MODEL = os.getenv("AUTONOMOUS_AGENT_MODEL", LLM_MODEL)
CODING_ENGINEER_MODEL = os.getenv("CODING_ENGINEER_MODEL", LLM_MODEL)
FAST_CHAT_CLOUD_MODEL = os.getenv("FAST_CHAT_CLOUD_MODEL", LLM_MODEL)

# Local Multi-Model Tiers (Ollama)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
FAST_CHAT_MODEL = os.getenv("FAST_CHAT_MODEL", "qwen2.5:3b")
PRIMARY_MODEL = os.getenv("PRIMARY_MODEL", "qwen2.5:3b")
CODER_MODEL = os.getenv("CODER_MODEL", "qwen2.5-coder:7b")
VISION_MODEL = os.getenv("VISION_MODEL", "moondream:latest")
UI_TARS_MODEL = os.getenv("UI_TARS_MODEL", "ui-tars:7b")
UI_TARS_MODEL_2B = os.getenv("UI_TARS_MODEL_2B", "ui-tars:2b")
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "qwen2.5:7b-instruct-q5_0")
# 3. Settings
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
LOW_RAM_MODE = os.getenv("LOW_RAM_MODE", "true").lower() in ("true", "1", "yes")

USER_DESKTOP_DIR = Path(os.path.expanduser("~")) / "Desktop"
MEMORY_FILE = BASE_DIR / "spacev_memory.json"


# Neural Voice Configuration
USE_NEURAL_TTS = True                      # Uses high-fidelity realistic Azure Neural Voice with offline SAPI5 fallback
TTS_NEURAL_VOICE = "en-US-AriaNeural"      # High-fidelity natural lady AI voice (warm, conversational, Gemini/Siri style)


# UI & Agent Configuration
APP_NAME = "SpaceV"
WAKE_WORDS = ["hey spacev", "spacev", "space v", "hey space v", "hey space"]
BUBBLE_SIZE = 64  # Size in pixels of the floating Arc Reactor bubble
CHAT_WIDTH = 500
CHAT_HEIGHT = 620
DEFAULT_CURSOR_SPEED = "Normal"  # Options: Hyper, Fast, Normal, Steady, Precision

# Proactive Companion Settings (Continuous Interaction & Check-Ins)
COMPANION_MODE_DEFAULT = True
COMPANION_CHECKIN_INTERVAL_SEC = 240  # 4 minutes idle before gentle check-in
AUTO_LISTEN_FOLLOWUP = True           # Auto-listen after SpaceV asks questions or checks in
WAKE_WORD_ENABLED_BY_DEFAULT = True   # Hands-free 'Hey SpaceV' active by default

# Visual Styling / Theme (Cosmic Cybernetic Glassmorphism)
THEME = {
    "primary_glow": "#00f0ff",      # Cyan neon glow
    "secondary_glow": "#8b5cf6",    # Electric violet accent
    "bg_dark": "#0a0e17",           # Deep rich dark background
    "bg_card": "#121824",           # Sleek elevated card surface
    "bg_glass": "rgba(18, 24, 36, 0.95)", # Glassmorphic panel
    "text_primary": "#f8fafc",      # Crisp high-contrast white text
    "text_secondary": "#94a3b8",    # Muted secondary text
    "bubble_user": "#0284c7",       # Refined cyber blue for user
    "bubble_agent": "#141c2b",      # Deep sleek card bubble for agent
    "border_color": "#1f2a3e",      # Subtle dark slate border
    "accent_green": "#10b981",      # Emerald active indicator
}



