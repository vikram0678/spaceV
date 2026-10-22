"""
Configuration settings for SpaceV Cybernetic Desktop AI Agent.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
# 1. Load .env if present (never breaks if .env is missing)

load_dotenv(BASE_DIR / ".env")
# 2. Multi-LLM Configuration with Defaults
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



