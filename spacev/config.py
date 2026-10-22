"""
SpaceV Central Configuration Module.
Loads environment settings with strict fallback defaults for production and evaluation.
"""
from __future__ import annotations

import os
from pathlib import Path
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent

class SpaceVConfig(BaseModel):
    # Celesto settings
    celesto_provider: str = os.getenv("CELESTO_PROVIDER", "local")
    celesto_api_key: str = os.getenv("CELESTO_API_KEY", "placeholder_key")
    celesto_backend: str = os.getenv("CELESTO_BACKEND", "firecracker")

    # AI Brain & LLM Inference
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://example-llm-host/v1")
    llm_api_key: str = os.getenv("LLM_API_KEY", "placeholder_llm_key")
    llm_model: str = os.getenv("LLM_MODEL", "spacev-reflex-qwen")

    # Ledger Database
    database_url: str = os.getenv(
        "DATABASE_URL", 
        "postgresql://ledger:ledger@localhost:5432/ledger"
    )

    # API Server
    api_port: int = int(os.getenv("API_PORT", "8080"))

    # Logging paths
    command_audit_log: Path = BASE_DIR / os.getenv("COMMAND_AUDIT_LOG", "logs/commands.jsonl")
    failure_trace_log: Path = BASE_DIR / os.getenv("FAILURE_TRACE_LOG", "reports/failure_trace.jsonl")
    reports_dir: Path = BASE_DIR / "reports"

    # Runtime mode
    environment: str = os.getenv("ENVIRONMENT", "production")


settings = SpaceVConfig()
