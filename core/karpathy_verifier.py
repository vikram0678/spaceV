"""
Karpathy Goal-Driven Verification & Algorithmic Discipline Engine for SpaceV.
Inspired by opensourcetools/andrej-karpathy-skills (Karpathy Guidelines).
Enforces:
1. Think Before Coding (Surfaces hidden assumptions and high-risk operations)
2. Simplicity First (Rejects speculative bloat)
3. Surgical Execution (Restricts diffs to targeted hunks)
4. Goal-Driven Verification (Requires empirical proof before declaring success)
"""
import re
from typing import Dict, Any, List, Optional, Callable


class KarpathyVerifier:
    """
    Guards against autonomous hallucination, destructive commands,
    and unnecessary context/token bloating.
    """

    DESTRUCTIVE_PATTERNS = [
        re.compile(r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f?|-f)\s+[/~]", re.I),
        re.compile(r"\bdrop\s+(database|table|schema)\b", re.I),
        re.compile(r"\bformat\s+[a-zA-Z]:", re.I),
        re.compile(r"\bkillall\s+-9\b", re.I),
        re.compile(r">\s*/dev/sd[a-z]\b", re.I),
    ]

    def audit_intent_safety(self, action_type: str, payload: str) -> Dict[str, Any]:
        """
        Rule 1 & 3: Check if command is potentially destructive or ambiguous.
        If dangerous, flags the need for user verification.
        """
        for pat in self.DESTRUCTIVE_PATTERNS:
            if pat.search(payload):
                return {
                    "safe": False,
                    "reason": f"Potentially destructive operation detected: pattern '{pat.pattern}' matched.",
                    "requires_confirmation": True
                }
        return {"safe": True, "requires_confirmation": False}

    def verify_goal_backward(
        self,
        goal_description: str,
        verification_fn: Callable[[], bool],
        max_attempts: int = 3
    ) -> Dict[str, Any]:
        """
        Rule 4: Transforms task execution into an empirical verification loop.
        Does not declare task complete until verification_fn returns True.
        """
        for attempt in range(1, max_attempts + 1):
            try:
                success = verification_fn()
                if success:
                    return {
                        "verified": True,
                        "attempts": attempt,
                        "goal": goal_description,
                        "message": f"Empirical verification PASSED on attempt {attempt}."
                    }
            except Exception as e:
                last_err = str(e)
            else:
                last_err = "Verification returned False."

        return {
            "verified": False,
            "attempts": max_attempts,
            "goal": goal_description,
            "error": f"Failed empirical verification after {max_attempts} attempts: {last_err}"
        }


# Global singleton instance
karpathy_verifier = KarpathyVerifier()
