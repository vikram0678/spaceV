"""
SpaceV Safety Subsystem: 3-Tier Anti-Bot Heuristic Detector.
Engineered from Crawl4AI production methodologies for sub-5ms detection of WAF/bot walls.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class AntiBotResult:
    is_blocked: bool
    provider: str
    tier: int
    rule: str
    confidence: float
    action: str  # e.g., 'rotate_stealth_profile', 'solve_captcha', 'proceed'


# Tier 1: High-confidence structural markers (single match sufficient regardless of page length)
_TIER1_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # Akamai reference pattern
    (
        re.compile(r"Reference\s*#\s*[\d]+\.[0-9a-f]+\.\d+\.[0-9a-f]+", re.IGNORECASE),
        "Akamai",
        "Akamai Block Reference ID",
    ),
    (
        re.compile(r"Pardon\s+Our\s+Interruption", re.IGNORECASE),
        "Akamai",
        "Akamai Pardon Interruption Challenge",
    ),
    # Cloudflare challenge forms & tokens
    (
        re.compile(r"challenge-form.*?__cf_chl_f_tk=", re.IGNORECASE | re.DOTALL),
        "Cloudflare",
        "Cloudflare Challenge Form Token",
    ),
    (
        re.compile(r'<span\s+class="cf-error-code">\d{4}</span>', re.IGNORECASE),
        "Cloudflare",
        "Cloudflare WAF Error Code Block",
    ),
    (
        re.compile(r"/cdn-cgi/challenge-platform/\S+orchestrate", re.IGNORECASE),
        "Cloudflare",
        "Cloudflare Turnstile/IUAM Orchestrate Script",
    ),
    # PerimeterX / HUMAN
    (
        re.compile(r"window\._pxAppId\s*=", re.IGNORECASE),
        "PerimeterX",
        "PerimeterX AppId Hook",
    ),
    (
        re.compile(r"captcha\.px-cdn\.net", re.IGNORECASE),
        "PerimeterX",
        "PerimeterX CDN Captcha Asset",
    ),
    # DataDome
    (
        re.compile(r"captcha-delivery\.com", re.IGNORECASE),
        "DataDome",
        "DataDome Captcha Delivery Gateway",
    ),
    # Kasada
    (
        re.compile(r"KPSDK\.scriptStart\s*=\s*KPSDK\.now\(\)", re.IGNORECASE),
        "Kasada",
        "Kasada Challenge Script Initialization",
    ),
    # Imperva / Incapsula
    (
        re.compile(r"_Incapsula_Resource", re.IGNORECASE),
        "Imperva",
        "Imperva/Incapsula Resource Trap",
    ),
    (
        re.compile(r"Incapsula\s+incident\s+ID", re.IGNORECASE),
        "Imperva",
        "Incapsula Incident Block",
    ),
]

# Tier 2: Contextual markers (only trigger on short payloads < 12KB)
_TIER2_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"Checking\s+your\s+browser", re.IGNORECASE), "Cloudflare", "Browser Verification Notice"),
    (re.compile(r"Just\s+a\s+moment\.\.\.", re.IGNORECASE), "Cloudflare", "Cloudflare Waiting Room"),
    (re.compile(r"Access\s+Denied", re.IGNORECASE), "GenericWAF", "WAF Access Denied Page"),
    (re.compile(r"Security\s+check\s+to\s+access", re.IGNORECASE), "GenericWAF", "Security Check Prompt"),
]


class AntiBotDetector:
    """
    High-speed heuristic engine to trap anti-bot detection walls before LLM context ingestion.
    """

    @classmethod
    def analyze(cls, html_or_text: str, status_code: int = 200) -> AntiBotResult:
        if not html_or_text:
            return AntiBotResult(
                is_blocked=False,
                provider="None",
                tier=0,
                rule="Empty payload",
                confidence=0.0,
                action="proceed",
            )

        # Tier 1 Evaluation (Structural markers - checked first for exact attribution)
        for pattern, provider, rule in _TIER1_PATTERNS:
            if pattern.search(html_or_text):
                return AntiBotResult(
                    is_blocked=True,
                    provider=provider,
                    tier=1,
                    rule=rule,
                    confidence=0.99,
                    action="rotate_stealth_profile",
                )

        # HTTP error block shortcut (Tier 2)
        if status_code in (403, 503) and len(html_or_text) < 15000:
            for pattern, provider, rule in _TIER2_PATTERNS:
                if pattern.search(html_or_text):
                    return AntiBotResult(
                        is_blocked=True,
                        provider=provider,
                        tier=2,
                        rule=f"Status {status_code}: {rule}",
                        confidence=0.98,
                        action="rotate_stealth_profile",
                    )
            return AntiBotResult(
                is_blocked=True,
                provider="WAF_HTTP_Block",
                tier=2,
                rule=f"HTTP {status_code} with short error body",
                confidence=0.90,
                action="rotate_stealth_profile",
            )

        # Tier 2 Evaluation (Short payload heuristic)
        if len(html_or_text) < 12000:
            for pattern, provider, rule in _TIER2_PATTERNS:
                if pattern.search(html_or_text):
                    return AntiBotResult(
                        is_blocked=True,
                        provider=provider,
                        tier=2,
                        rule=rule,
                        confidence=0.88,
                        action="rotate_stealth_profile",
                    )

        # Tier 3 Evaluation (Empty SPA Shell Check)
        stripped = re.sub(r"<[^>]+>", "", html_or_text).strip()
        if len(html_or_text) > 1000 and len(stripped) < 40 and status_code == 200:
            return AntiBotResult(
                is_blocked=True,
                provider="Silent_Empty_Shell",
                tier=3,
                rule="Suspicious empty shell layout with <40 characters visible text",
                confidence=0.75,
                action="wait_and_retry",
            )

        return AntiBotResult(
            is_blocked=False,
            provider="None",
            tier=0,
            rule="Clear",
            confidence=0.0,
            action="proceed",
        )
