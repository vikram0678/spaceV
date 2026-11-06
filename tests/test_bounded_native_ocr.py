import threading
import time
from unittest.mock import Mock

import core.vision_grounding as vision_grounding
from PIL import Image


def _reset_ocr_circuit_breaker():
    with vision_grounding._OCR_STATE_LOCK:
        vision_grounding._OCR_DISABLED_REASON = None
        vision_grounding._OCR_IN_FLIGHT = False


def test_native_ocr_timeout_returns_without_blocking_and_disables_retries(monkeypatch):
    _reset_ocr_circuit_breaker()
    monkeypatch.setattr(vision_grounding, "OCR_TIMEOUT_SECONDS", 0.03)
    release_worker = threading.Event()
    recognize = Mock(side_effect=lambda *_args, **_kwargs: (release_worker.wait(1), {"text": "late"})[1])
    engine = Mock(recognize_pil_sync=recognize)
    image = Image.new("RGB", (8, 8))

    started = time.monotonic()
    assert vision_grounding.recognize_screen_text_bounded(engine, image) is None
    assert time.monotonic() - started < 0.5
    assert vision_grounding._OCR_DISABLED_REASON
    assert vision_grounding.recognize_screen_text_bounded(engine, image) is None
    recognize.assert_called_once()

    release_worker.set()
    time.sleep(0.02)
    _reset_ocr_circuit_breaker()


def test_native_ocr_returns_successful_result():
    _reset_ocr_circuit_breaker()
    expected = {"text": "Settings", "lines": []}
    engine = Mock()
    engine.recognize_pil_sync.return_value = expected

    assert vision_grounding.recognize_screen_text_bounded(engine, Image.new("RGB", (8, 8))) == expected
    engine.recognize_pil_sync.assert_called_once()

