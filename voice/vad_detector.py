"""
Voice Activity Detection (VAD) Engine for SpaceV.
Powered by Silero VAD (ONNX Runtime) with graceful fallback to RMS energy estimation.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Tuple, Optional

import numpy as np

try:
    import onnxruntime as ort
    HAS_ORT = True
except ImportError:
    HAS_ORT = False

logger = logging.getLogger("SpaceV.VAD")

# Default model location
MODEL_PATH = Path(__file__).parent / "models" / "silero_vad.onnx"


class SileroVADDetector:
    """
    Enterprise-grade Neural Voice Activity Detector.
    Processes 512-sample (32ms at 16kHz) 16-bit PCM frames using Silero VAD ONNX.
    """

    def __init__(
        self,
        model_path: Optional[str | Path] = None,
        sample_rate: int = 16000,
        threshold: float = 0.5,
        neg_threshold: float = 0.35,
    ):
        self.sample_rate = sample_rate
        self.threshold = threshold
        self.neg_threshold = neg_threshold
        self.window_size_samples = 512 if sample_rate == 16000 else 256
        self.context_size = 64 if sample_rate == 16000 else 32
        self._sr_tensor = np.array(sample_rate, dtype=np.int64)
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, self.context_size), dtype=np.float32)

        self._session: Optional[ort.InferenceSession] = None
        self._is_active = False

        resolved_path = Path(model_path) if model_path else MODEL_PATH
        if HAS_ORT and resolved_path.exists():
            try:
                # Optimize inference session for low latency CPU execution
                opts = ort.SessionOptions()
                opts.intra_op_num_threads = 1
                opts.inter_op_num_threads = 1
                opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
                opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

                self._session = ort.InferenceSession(
                    str(resolved_path),
                    sess_options=opts,
                    providers=["CPUExecutionProvider"],
                )
                self._is_active = True
                logger.info("[VAD] 🧠 Silero VAD ONNX model initialized successfully.")
            except Exception as e:
                logger.warning(f"[VAD] Failed to load Silero VAD ONNX: {e}. Falling back to energy VAD.")
                self._session = None
        else:
            logger.info("[VAD] ONNX Runtime or model file not present; using energy-based fallback.")

    @property
    def is_neural(self) -> bool:
        """Returns True if the neural Silero VAD model is operational."""
        return self._session is not None

    def reset_state(self) -> None:
        """Resets the recurrent neural network hidden states and context."""
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, self.context_size), dtype=np.float32)

    def process_frame(self, pcm_bytes: bytes) -> Tuple[bool, float]:
        """
        Evaluates a raw PCM byte chunk (512 samples / 1024 bytes for 16-bit 16kHz).
        Prepends the required 64-sample context window for Silero VAD.
        Returns:
            (is_speech: bool, speech_probability: float)
        """
        if len(pcm_bytes) == 0:
            return False, 0.0

        # Convert 16-bit PCM bytes to float32 normalized array [-1.0, 1.0]
        try:
            audio_int16 = np.frombuffer(pcm_bytes, dtype=np.int16)
        except Exception:
            return False, 0.0

        if len(audio_int16) != self.window_size_samples:
            # Resample or pad/truncate to exact window size if necessary
            if len(audio_int16) < self.window_size_samples:
                audio_int16 = np.pad(audio_int16, (0, self.window_size_samples - len(audio_int16)))
            else:
                audio_int16 = audio_int16[: self.window_size_samples]

        audio_float32 = audio_int16.astype(np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(audio_float32 ** 2)))

        if self._session is not None:
            try:
                # Shape: [1, 512]
                input_tensor = audio_float32.reshape(1, -1)
                # Shape: [1, 64 + 512] = [1, 576]
                x = np.concatenate([self._context, input_tensor], axis=1)

                inputs = {
                    "input": x,
                    "state": self._state,
                    "sr": self._sr_tensor,
                }
                out, new_state = self._session.run(None, inputs)
                self._state = new_state
                self._context = x[:, -self.context_size:]

                neural_prob = float(out[0][0])
                energy_prob = min(1.0, rms * 20.0)

                # Combine neural probability with energy boost for low-gain laptop microphones
                prob = max(neural_prob, energy_prob if rms > 0.02 else neural_prob)
                is_speech = neural_prob >= self.threshold or (rms > 0.02 and neural_prob > 0.25)
                try:
                    from voice.aec_guard import aec_guard
                    is_speech, prob = aec_guard.evaluate_frame(is_speech, prob, rms)
                except Exception:
                    pass
                return is_speech, prob
            except Exception as e:
                logger.debug(f"[VAD] Neural inference error: {e}")
                return self._energy_fallback(audio_float32)
        else:
            return self._energy_fallback(audio_float32)

    def _energy_fallback(self, audio_float32: np.ndarray) -> Tuple[bool, float]:
        """Simple, fast Root Mean Square (RMS) energy estimation fallback."""
        rms = float(np.sqrt(np.mean(audio_float32 ** 2)))
        prob = min(1.0, rms * 15.0)
        is_speech = prob >= self.threshold
        try:
            from voice.aec_guard import aec_guard
            is_speech, prob = aec_guard.evaluate_frame(is_speech, prob, rms)
        except Exception:
            pass
        return is_speech, prob
