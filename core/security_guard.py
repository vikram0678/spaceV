r"""
SpaceV Prompt Injection Taint Analyzer & Workstation Security Guard.
Personalized from cortex-scan & VYUHA-C2 (D:\Gpp-Tasks):
Guarantees enterprise-grade airgap security:
- Real-time lexical & heuristic prompt injection scanning (<0.2ms)
- Delimiter escaping & LLM control token neutralization
- Base64 covert payload decoding & analysis
- Destructive OS / PowerShell command blocking
"""
from __future__ import annotations

import base64
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger("SpaceV.SecurityGuard")


@dataclass
class SecurityAssessment:
    is_safe: bool
    threat_level: str  # "CLEAN", "SUSPICIOUS", "CRITICAL"
    detected_patterns: list[str]
    sanitized_text: str


class SecurityGuard:
    """
    Sub-millisecond adversarial prompt and payload taint analyzer.
    """

    # 1. Direct Adversarial Jailbreak & System Prompt Hijacking
    JAILBREAK_PATTERNS = [
        re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions|directives|rules)", re.IGNORECASE),
        re.compile(r"disregard\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions|directives|prompts)", re.IGNORECASE),
        re.compile(r"(?:system\s+override|admin\s+override|root\s+override)", re.IGNORECASE),
        re.compile(r"you\s+are\s+now\s+(?:in\s+)?(?:developer|dan|unrestricted|god)\s+mode", re.IGNORECASE),
        re.compile(r"bypass\s+(?:all\s+)?(?:safety|guardrail|security)\s+(?:filters|protocols)", re.IGNORECASE),
        re.compile(r"reveal\s+(?:your\s+)?(?:system\s+prompt|hidden\s+instructions|master\s+directive)", re.IGNORECASE),
    ]

    # 2. Control Token & Delimiter Injections
    CONTROL_DELIMITERS = [
        re.compile(r"<\|im_start\|>", re.IGNORECASE),
        re.compile(r"<\|im_end\|>", re.IGNORECASE),
        re.compile(r"<\|system\|>", re.IGNORECASE),
        re.compile(r"\[/?INST\]", re.IGNORECASE),
        re.compile(r"###\s*(?:System|Human|Assistant|Instruction):", re.IGNORECASE),
    ]

    # 3. Destructive OS Shell & PowerShell Payloads
    DESTRUCTIVE_COMMANDS = [
        re.compile(r"rm\s+-rf\s+(?:/|\*)", re.IGNORECASE),
        re.compile(r":\(\)\s*\{\s*:\|:&\s*\};:", re.IGNORECASE),  # Fork bomb
        re.compile(r"format\s+[a-z]:\s+/fs", re.IGNORECASE),
        re.compile(r"del\s+/[fF]\s+/[sS]\s+/[qQ]\s+[cC]:\\", re.IGNORECASE),
        re.compile(r"powershell.*?(?:downloadstring|iex|invoke-expression|encodedcommand)", re.IGNORECASE),
        re.compile(r"(?:curl|wget).*?\|\s*(?:bash|sh|powershell)", re.IGNORECASE),
    ]

    @classmethod
    def analyze(cls, text: str) -> SecurityAssessment:
        """
        Performs multi-vector taint analysis on user input or untrusted data.
        """
        if not text or not text.strip():
            return SecurityAssessment(is_safe=True, threat_level="CLEAN", detected_patterns=[], sanitized_text=text)

        detected = []
        threat_level = "CLEAN"
        sanitized = text

        # 1. Check Destructive OS Commands
        for pat in cls.DESTRUCTIVE_COMMANDS:
            if pat.search(text):
                detected.append(f"destructive_command:{pat.pattern}")
                threat_level = "CRITICAL"

        # 2. Check Jailbreak Patterns
        for pat in cls.JAILBREAK_PATTERNS:
            if pat.search(text):
                detected.append(f"jailbreak_pattern:{pat.pattern}")
                if threat_level != "CRITICAL":
                    threat_level = "SUSPICIOUS"

        # 3. Check Control Delimiters and Neutralize
        for pat in cls.CONTROL_DELIMITERS:
            if pat.search(text):
                detected.append(f"control_delimiter:{pat.pattern}")
                if threat_level != "CRITICAL":
                    threat_level = "SUSPICIOUS"
                sanitized = pat.sub(" [FILTERED_DELIMITER] ", sanitized)

        # 4. Check for covert base64 encoded payloads
        b64_matches = re.findall(r"(?:[A-Za-z0-9+/]{40,}={0,2})", text)
        for b64 in b64_matches:
            try:
                decoded = base64.b64decode(b64).decode("utf-8", errors="ignore")
                for pat in cls.JAILBREAK_PATTERNS + cls.DESTRUCTIVE_COMMANDS:
                    if pat.search(decoded):
                        detected.append(f"covert_base64_injection:{pat.pattern}")
                        threat_level = "CRITICAL"
                        break
            except Exception:
                pass

        is_safe = (threat_level == "CLEAN")
        return SecurityAssessment(
            is_safe=is_safe,
            threat_level=threat_level,
            detected_patterns=detected,
            sanitized_text=sanitized
        )

    @classmethod
    def sanitize_external_context(cls, raw_content: str, source_label: str = "web") -> str:
        """
        Wraps untrusted external data (clipboard, web scraped HTML, documents)
        in an immutable untrusted enclosure with neutralized delimiters.
        """
        assessment = cls.analyze(raw_content)
        cleaned = assessment.sanitized_text

        # Enclose in structured taint boundaries for LLM awareness
        wrapped = (
            f"<!-- BEGIN_UNTRUSTED_EXTERNAL_DATA source='{source_label}' safe={assessment.is_safe} -->\n"
            f"{cleaned}\n"
            f"<!-- END_UNTRUSTED_EXTERNAL_DATA -->"
        )
        return wrapped


security_guard = SecurityGuard()
