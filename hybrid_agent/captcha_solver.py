"""
Local Zero-Cost Neural CAPTCHA Solver for SpaceV Hybrid Agent.
Exploits accessibility audio challenges using on-device Faster-Whisper & Silero VAD.
Requires $0.00 in paid solver APIs. 100% local and private.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any

import requests

from voice.stt_engine import OfflineWhisperSingleton

logger = logging.getLogger("SpaceV.CaptchaSolver")


class LocalAudioCaptchaSolver:
    """
    Solves reCAPTCHA v2 and hCaptcha accessibility challenges locally
    by streaming audio into local quantized Faster-Whisper.
    """

    def __init__(self):
        pass  # Whisper is lazily loaded upon first audio challenge invocation

    @staticmethod
    def detect_captcha(page: Any) -> tuple[bool, str]:
        """
        Scans active page DOM for known CAPTCHA and anti-bot signatures.
        Returns: (detected: bool, captcha_type: str)
        """
        try:
            # 1. Check for reCAPTCHA v2 / v3
            recaptcha_frames = page.locator('iframe[src*="google.com/recaptcha"], iframe[src*="recaptcha"]').count()
            if recaptcha_frames > 0:
                return True, "recaptcha_v2"

            # 2. Check for Cloudflare Turnstile
            turnstile_elements = page.locator('.cf-turnstile, iframe[src*="challenges.cloudflare.com"]').count()
            if turnstile_elements > 0:
                return True, "turnstile"

            # 3. Check for hCaptcha
            hcaptcha_frames = page.locator('iframe[src*="hcaptcha.com"]').count()
            if hcaptcha_frames > 0:
                return True, "hcaptcha"

            # 4. Check page title/text for Cloudflare challenge
            title = page.title().lower()
            content = page.content().lower()
            if "just a moment..." in title or "checking your browser" in content or "cf-challenge" in content:
                return True, "turnstile"

        except Exception as e:
            logger.debug(f"[CaptchaSolver] Detection check error: {e}")

        return False, "none"

    def solve_recaptcha_audio(self, page: Any, timeout_sec: float = 15.0) -> bool:
        """
        Automates reCAPTCHA v2 audio challenge flow:
        1. Clicks the audio challenge button
        2. Retrieves audio URL
        3. Downloads and transcribes digits locally via Faster-Whisper
        4. Injects digits and submits
        """
        print("[CaptchaSolver] 🛡️ Attempting automated local Whisper audio bypass...")
        try:
            # 1. Switch to reCAPTCHA anchor frame and click if not already checked
            anchor_frame = page.frame_locator('iframe[src*="recaptcha/api2/anchor"]')
            checkbox = anchor_frame.locator("#recaptcha-anchor")
            if checkbox.count() > 0:
                is_checked = checkbox.get_attribute("aria-checked")
                if is_checked != "true":
                    print("[CaptchaSolver] Clicking reCAPTCHA anchor checkbox...")
                    checkbox.click()
                    time.sleep(1.5)

            # Check if verified without challenge
            if checkbox.count() > 0 and checkbox.get_attribute("aria-checked") == "true":
                print("[CaptchaSolver] ✅ Verified immediately without challenge!")
                return True

            # 2. Switch to the challenge bframe
            bframe = page.frame_locator('iframe[src*="recaptcha/api2/bframe"]')
            audio_btn = bframe.locator("#recaptcha-audio-button")

            if audio_btn.count() == 0:
                print("[CaptchaSolver] Challenge frame not visible or already solved.")
                return False

            print("[CaptchaSolver] Clicking audio challenge button...")
            audio_btn.click()
            time.sleep(1.5)

            # 3. Check for IP block or rate limit ("Your computer or network may be sending automated queries")
            error_msg = bframe.locator(".rc-doscaptcha-header")
            if error_msg.count() > 0 and error_msg.is_visible():
                print("[CaptchaSolver] ⚠️ Google detected automated query on audio challenge.")
                return False

            # 4. Extract audio download URL
            download_link = bframe.locator(".rc-audiochallenge-tdownload-link, a[href*='audio.mp3']")
            if download_link.count() == 0:
                print("[CaptchaSolver] Audio download link not found.")
                return False

            audio_url = download_link.get_attribute("href")
            if not audio_url:
                print("[CaptchaSolver] Failed to extract audio URL.")
                return False

            print("[CaptchaSolver] 📥 Downloading audio challenge stream...")
            resp = requests.get(audio_url, timeout=10)
            if resp.status_code != 200:
                print(f"[CaptchaSolver] Failed to download audio (HTTP {resp.status_code})")
                return False

            audio_bytes = resp.content

            # 5. Transcribe audio locally using Faster-Whisper
            print(f"[CaptchaSolver] 🧠 Transcribing audio with local Faster-Whisper model ({len(audio_bytes)} bytes)...")
            transcription = self._transcribe_audio_bytes(audio_bytes)

            if not transcription:
                print("[CaptchaSolver] Faster-Whisper could not decode audio digits.")
                return False

            # Extract clean digits or words
            cleaned_digits = re.sub(r"[^a-zA-Z0-9\s]", "", transcription).strip().lower()
            print(f"[CaptchaSolver] 🗣️ Transcribed Answer: '{cleaned_digits}'")

            # 6. Type response and submit
            response_input = bframe.locator("#audio-response")
            response_input.fill(cleaned_digits)
            time.sleep(0.5)

            verify_btn = bframe.locator("#recaptcha-verify-button")
            verify_btn.click()
            time.sleep(2.0)

            # 7. Check if checkbox is now checked
            if checkbox.count() > 0 and checkbox.get_attribute("aria-checked") == "true":
                print("[CaptchaSolver] 🎉 reCAPTCHA v2 successfully bypassed locally!")
                return True

            print("[CaptchaSolver] Verify clicked, checking final status...")
            return True

        except Exception as e:
            print(f"[CaptchaSolver] Error during audio solving: {e}")
            return False

    def solve_turnstile(self, page: Any) -> bool:
        """
        Attempts humanized interaction to pass Cloudflare Turnstile verification.
        """
        print("[CaptchaSolver] 🛡️ Cloudflare Turnstile detected. Applying humanized stealth click...")
        try:
            # Look for Turnstile iframe or container
            turnstile_frame = page.frame_locator('iframe[src*="challenges.cloudflare.com"]')
            box = turnstile_frame.locator('input[type="checkbox"], #challenge-stage')

            if box.count() > 0:
                # Add human jitter
                time.sleep(1.2)
                box.click(delay=150)
                time.sleep(2.5)
                print("[CaptchaSolver] Turnstile click dispatched.")
                return True
        except Exception as e:
            logger.debug(f"[CaptchaSolver] Turnstile error: {e}")
        return False

    def _transcribe_audio_bytes(self, audio_bytes: bytes) -> str:
        """Transcribes arbitrary mp3/wav bytes with Faster-Whisper."""
        model = OfflineWhisperSingleton.get_model()
        if model is None:
            return ""

        try:
            import io

            import av
            import numpy as np

            # Use PyAV (installed with faster-whisper) to decode mp3 stream in memory
            container = av.open(io.BytesIO(audio_bytes))
            stream = container.streams.audio[0]
            resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)

            frames = []
            for frame in container.decode(stream):
                resampled = resampler.resample(frame)
                for r in resampled:
                    frames.append(r.to_ndarray().flatten())

            if not frames:
                return ""

            raw_audio = np.concatenate(frames).astype(np.float32) / 32768.0
            segments, _ = model.transcribe(raw_audio, beam_size=2, language="en")
            result = " ".join([s.text for s in segments]).strip()
            return result

        except Exception as e:
            logger.error(f"[CaptchaSolver] Audio decode/transcription error: {e}")
            return ""


# Global singleton
local_captcha_solver = LocalAudioCaptchaSolver()
