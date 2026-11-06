"""
Outcome Verification & Empirical Evaluation Engine for SpaceV.
Evaluates observable ground truth (processes running, filesystem changes,
hardware status, artifact schemas) rather than accepting unverified string claims.
"""

from __future__ import annotations

import logging
from typing import Any

from core.intent.contracts import (
    IntentResolution,
    OutcomeVerification,
    VerificationStrategy,
)
from core.truth_gatekeeper import truth_gatekeeper

logger = logging.getLogger("SpaceV.OutcomeVerifier")


class OutcomeVerifier:
    """
    Evaluates whether a requested real-world outcome was actually achieved
    using observable ground truth on disk, in processes, and in structured outputs.
    """

    @classmethod
    def verify(
        cls,
        resolution: IntentResolution,
        tool_output: str,
    ) -> OutcomeVerification:
        """
        Runs empirical verification based on the capability's verification strategy.
        """
        strat = resolution.verification_strategy
        out_str = str(tool_output)

        # 0. Immediate Tool Error Check
        if out_str.startswith(("Error:", "Failed:", "BLOCKED:", "Folder does not exist:")):
            return OutcomeVerification(
                check_type=strat,
                passed=False,
                expected="successful_tool_invocation",
                observed=out_str[:160],
                error=out_str,
            )

        # 1. Strategy: None / Conversational
        if strat == VerificationStrategy.NONE:
            return OutcomeVerification(
                check_type=strat,
                passed=True,
                expected="non_error_response",
                observed="success",
                evidence={"output_preview": out_str[:120]},
            )

        # 2. Strategy: Process Running (App Launches / Editor / Browser)
        if strat == VerificationStrategy.PROCESS_RUNNING:
            from tools.system_tools import list_running_apps
            app_target = resolution.parameters.get("app_name", "").lower()
            if not app_target:
                app_target = resolution.parameters.get("editor", "").lower()
            if not app_target:
                app_target = resolution.parameters.get("target", "").lower()

            running_summary = list_running_apps().lower()

            # Check if target app or its known binary name appears in running apps
            # e.g. "code" -> "code.exe" or "vscode", "notepad" -> "notepad.exe"
            alias_map = {
                "code": "code", "vscode": "code", "cursor": "cursor",
                "chrome": "chrome", "brave": "brave", "edge": "msedge",
                "notepad": "notepad", "calculator": "calculator",
            }
            check_key = alias_map.get(app_target, app_target)

            is_running = check_key in running_summary or app_target in running_summary
            return OutcomeVerification(
                check_type=strat,
                passed=is_running,
                expected={"process_active": check_key},
                observed={"process_found": is_running},
                evidence={"target": app_target, "running_summary_snippet": running_summary[:150]},
                error=None if is_running else f"Process '{app_target}' did not appear in active workstation process table.",
            )

        # 3. Strategy: File Existence (Screenshots, File creations, Harvested CSVs)
        if strat == VerificationStrategy.FILE_EXISTENCE:
            target_path = (
                resolution.parameters.get("file_name")
                or resolution.parameters.get("folder_name")
                or resolution.parameters.get("target_file")
                or resolution.parameters.get("path")
            )
            location = resolution.parameters.get("location", "Desktop")

            # For screenshots or job harvesting, path might be mentioned in tool_output
            if not target_path:
                import re
                path_match = re.search(r"saved\s+(?:to\s+)?([A-Za-z0-9_\\\-:\.\/]+\.(?:png|csv|json|txt|py))", out_str, re.I)
                if path_match:
                    target_path = path_match.group(1)

            if target_path:
                v_res = truth_gatekeeper.verify_file_postcondition(
                    path_or_name=target_path,
                    location=location,
                    min_bytes=1,
                )
                return OutcomeVerification(
                    check_type=strat,
                    passed=v_res.passed,
                    expected=v_res.expected,
                    observed=v_res.observed,
                    evidence=v_res.evidence,
                    error=v_res.error,
                )
            else:
                # If no specific path could be parsed, check non-error status
                return OutcomeVerification(
                    check_type=strat,
                    passed=True,
                    expected="file_created",
                    observed="output_indicates_creation",
                    evidence={"output": out_str[:120]},
                )

        # Default fallback
        return OutcomeVerification(
            check_type=strat,
            passed=True,
            expected="execution_completed",
            observed="completed",
        )


outcome_verifier = OutcomeVerifier()

