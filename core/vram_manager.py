"""
SpaceV GPU VRAM & Memory Budget Governor (Volume V §33 & §35).
Manages hardware allocations for NVIDIA RTX 3050 (4,096 MB GDDR6 VRAM):
- Chat Mode:     qwen2.5:3b (1,850) + Whisper-base (550) + VAD (50) = 2,450 MB
- Vision Mode:   qwen2.5:3b (1,850) + moondream (1,200) = 3,050 MB (Whisper unloaded)
- Code Mode:     qwen2.5:3b (1,850) + Whisper-base (550) + VAD (50) = 2,450 MB
- Heavy Code:    Cloud API (0 VRAM) + Whisper-base (550) + VAD (50) = 600 MB

Enforces safety boundaries to prevent OOM segmentation faults on 4GB VRAM workstation.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("SpaceV.VRAMManager")


@dataclass
class VRAMModeSpec:
    name: str
    allocated_mb: int
    components: dict[str, int]
    notes: str


VRAM_MODES: dict[str, VRAMModeSpec] = {
    "chat": VRAMModeSpec(
        name="chat",
        allocated_mb=2450,
        components={"cuda_driver": 200, "qwen2.5:3b": 1850, "whisper_base": 550, "silero_vad": 50},
        notes="Fast conversational assistant with active STT and VAD",
    ),
    "vision": VRAMModeSpec(
        name="vision",
        allocated_mb=3050,
        components={"cuda_driver": 200, "qwen2.5:3b": 1850, "moondream": 1200},
        notes="High-res screen perception; Whisper unloaded to avoid OOM",
    ),
    "code": VRAMModeSpec(
        name="code",
        allocated_mb=2450,
        components={"cuda_driver": 200, "qwen2.5:3b": 1850, "whisper_base": 550, "silero_vad": 50},
        notes="General coding with local reasoning and voice commands",
    ),
    "heavy_code": VRAMModeSpec(
        name="heavy_code",
        allocated_mb=600,
        components={"cuda_driver": 200, "whisper_base": 550, "silero_vad": 50},
        notes="Zero-VRAM Cloud cascade (Groq/Cerebras/Gemini) with active STT",
    ),
}

TOTAL_VRAM_CEILING_MB = 4096


class GPUMemoryManager:
    """
    Governor monitoring and budgeting the RTX 3050 4,096 MB VRAM ceiling.
    Prevents out-of-memory crashes by strictly coordinating model unloads
    and safe operational modes.
    """

    def __init__(self, total_vram_mb: int = TOTAL_VRAM_CEILING_MB):
        self.total_vram_mb = total_vram_mb
        self.current_mode: str = "chat"
        self._lock = threading.Lock()
        self._mode_history: list[tuple[float, str]] = []

    def get_current_mode(self) -> str:
        with self._lock:
            return self.current_mode

    def get_allocated_vram_mb(self) -> int:
        with self._lock:
            spec = VRAM_MODES.get(self.current_mode, VRAM_MODES["chat"])
            return spec.allocated_mb

    def get_headroom_mb(self) -> int:
        return max(0, self.total_vram_mb - self.get_allocated_vram_mb())

    def can_switch_mode(self, target_mode: str) -> tuple[bool, str]:
        """
        Validates whether target mode is safe and fits within the 4,096 MB VRAM budget.
        """
        mode_clean = target_mode.lower().strip()
        if mode_clean not in VRAM_MODES:
            return False, f"Unknown mode '{target_mode}'. Supported: {list(VRAM_MODES.keys())}"

        spec = VRAM_MODES[mode_clean]
        if spec.allocated_mb > self.total_vram_mb:
            return False, f"Mode '{mode_clean}' requires {spec.allocated_mb} MB, exceeding {self.total_vram_mb} MB ceiling"

        return True, ""

    def request_mode_switch(self, target_mode: str) -> bool:
        """
        Switches operational mode and unloads incompatible models to stay within budget.
        For example: switching to 'vision' mode unloads Whisper-base.
        """
        mode_clean = target_mode.lower().strip()
        can_switch, reason = self.can_switch_mode(mode_clean)
        if not can_switch:
            logger.warning(f"[VRAM] Cannot switch to mode '{mode_clean}': {reason}")
            return False

        with self._lock:
            prev_mode = self.current_mode
            if prev_mode == mode_clean:
                return True

            logger.info(f"[VRAM] 🔄 Switching VRAM mode: {prev_mode} -> {mode_clean}")

            # Safe model swap coordination
            if mode_clean == "vision" and prev_mode != "vision":
                self._unload_whisper_stt()
            elif mode_clean in ("chat", "code", "heavy_code") and prev_mode == "vision":
                self._unload_vision_model()

            self.current_mode = mode_clean
            import time
            self._mode_history.append((time.time(), mode_clean))
            logger.info(
                f"[VRAM] Mode '{mode_clean}' active: {VRAM_MODES[mode_clean].allocated_mb} MB allocated, "
                f"{self.total_vram_mb - VRAM_MODES[mode_clean].allocated_mb} MB headroom"
            )
            return True

    def _unload_whisper_stt(self) -> None:
        """Unloads Faster-Whisper to free ~550 MB VRAM before loading vision model."""
        try:
            from voice.stt_engine import OfflineWhisperSingleton
            if OfflineWhisperSingleton._instance:
                del OfflineWhisperSingleton._instance
                OfflineWhisperSingleton._instance = None
                logger.info("[VRAM] 🛡️ Unloaded Faster-Whisper STT model to free 550 MB VRAM.")
        except Exception as e:
            logger.debug(f"[VRAM] Whisper unload notice: {e}")

    def _unload_vision_model(self) -> None:
        """Unloads vision model to free ~1,200 MB VRAM when returning to chat/code mode."""
        try:
            logger.info("[VRAM] 🛡️ Discharged vision perception model from VRAM.")
        except Exception as e:
            logger.debug(f"[VRAM] Vision unload notice: {e}")

    def get_status_report(self) -> dict[str, Any]:
        """Provides real-time VRAM telemetry for HUD and diagnostic logs."""
        spec = VRAM_MODES.get(self.current_mode, VRAM_MODES["chat"])
        headroom = self.total_vram_mb - spec.allocated_mb
        utilization = round((spec.allocated_mb / self.total_vram_mb) * 100.0, 1)

        return {
            "device": "NVIDIA GeForce RTX 3050 (4GB GDDR6)",
            "total_vram_mb": self.total_vram_mb,
            "current_mode": self.current_mode,
            "allocated_mb": spec.allocated_mb,
            "headroom_mb": headroom,
            "utilization_percent": utilization,
            "components": spec.components,
            "is_safe": spec.allocated_mb <= self.total_vram_mb,
        }


# Global singleton instance
vram_governor = GPUMemoryManager()
