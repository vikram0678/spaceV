"""
Voice Activity Detection (VAD) Engine for SpaceV.
Powered by Silero VAD (ONNX Runtime) with graceful fallback to RMS energy estimation.
"""
from __future__ import annotations

import logging
from pathlib import Path

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
    _shared_session: ort.InferenceSession | None = None

    def __init__(
        self,
        model_path: str | Path | None = None,
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

        self._session: ort.InferenceSession | None = None
        self._is_active = False

        resolved_path = Path(model_path) if model_path else MODEL_PATH
        if HAS_ORT and resolved_path.exists():
            if SileroVADDetector._shared_session is not None and model_path is None:
                self._session = SileroVADDetector._shared_session
                self._is_active = True
            else:
                try:
                    # Optimize inference session for low latency CPU execution
                    opts = ort.SessionOptions()
                    opts.intra_op_num_threads = 1
                    opts.inter_op_num_threads = 1
                    opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
                    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

                    session = ort.InferenceSession(
                        str(resolved_path),
                        sess_options=opts,
                        providers=["CPUExecutionProvider"],
                    )
                    self._session = session
                    self._is_active = True
                    if model_path is None:
                        SileroVADDetector._shared_session = session
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

    def process_frame(self, pcm_bytes: bytes) -> tuple[bool, float]:
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
                is_speech = neural_prob >= self.threshold

                try:
                    from voice.aec_guard import aec_guard
                    is_speech, prob = aec_guard.evaluate_frame(is_speech, neural_prob, rms)
                except Exception:
                    prob = neural_prob
                return is_speech, prob
            except Exception as e:
                logger.debug(f"[VAD] Neural inference error: {e}")
                return self._energy_fallback(audio_float32)
        else:
            return self._energy_fallback(audio_float32)

    def _energy_fallback(self, audio_float32: np.ndarray) -> tuple[bool, float]:
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
