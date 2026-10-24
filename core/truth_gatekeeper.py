"""
SpaceV Karpathy Truth Gatekeeper & Deterministic Verification Engine.
Provides empirical postcondition verification, artifact inspection,
syntax validation, and anti-hallucination protection.

Ensures SpaceV never reports false-positive success when tools fail,
files are missing, or outputs violate required schemas.
"""

from __future__ import annotations

import ast
import csv
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("SpaceV.TruthGatekeeper")


@dataclass
class VerificationResult:
    check_id: str
    check_type: str  # 'file_existence', 'file_content', 'json_schema', 'csv_structure', 'python_syntax', 'command_exit'
    status: str      # 'PASS', 'FAIL', 'INCONCLUSIVE', 'NOT_RUN', 'BLOCKED'
    expected: Any
    observed: Any
    evidence: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def passed(self) -> bool:
        return self.status == "PASS"


class TruthGatekeeper:
    """
    Independent Deterministic Verification Engine.
    Evaluates observable ground truth on disk, in processes, and in structured outputs.
    """

    @staticmethod
    def compute_sha256(path: Union[str, Path]) -> Optional[str]:
        """Computes cryptographic SHA-256 digest of a file for tamper-evident provenance."""
        try:
            p = Path(path)
            if not p.is_file():
                return None
            hasher = hashlib.sha256()
            with open(p, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as e:
            logger.error(f"Failed to hash {path}: {e}")
            return None

    @classmethod
    def verify_file_postcondition(
        cls,
        path_or_name: Union[str, Path],
        expected_content: Optional[str] = None,
        min_bytes: int = 1,
        location: str = "Desktop"
    ) -> VerificationResult:
        """
        Deterministically verifies that a file exists on disk, has non-zero size,
        and optionally matches expected content.
        """
        from tools.file_tools import resolve_path
        check_id = f"file_check_{int(datetime.now().timestamp() * 1000)}"

        target_path: Path
        p = Path(path_or_name)
        if p.is_absolute():
            target_path = p
        else:
            base_dir = resolve_path(location)
            target_path = base_dir / p

        if not target_path.exists():
            return VerificationResult(
                check_id=check_id,
                check_type="file_existence",
                status="FAIL",
                expected={"exists": True, "path": str(target_path)},
                observed={"exists": False},
                error=f"File does not exist on disk: {target_path}"
            )

        if not target_path.is_file():
            return VerificationResult(
                check_id=check_id,
                check_type="file_existence",
                status="FAIL",
                expected={"is_file": True},
                observed={"is_file": False, "is_dir": target_path.is_dir()},
                error=f"Path is a directory, not a file: {target_path}"
            )

        stat = target_path.stat()
        file_size = stat.st_size

        if file_size < min_bytes:
            return VerificationResult(
                check_id=check_id,
                check_type="file_content",
                status="FAIL",
                expected={"min_bytes": min_bytes},
                observed={"file_size": file_size},
                evidence={"path": str(target_path)},
                error=f"File size ({file_size} bytes) is less than required minimum ({min_bytes} bytes)."
            )

        file_hash = cls.compute_sha256(target_path)
        evidence = {
            "path": str(target_path.resolve()),
            "file_size": file_size,
            "sha256": file_hash,
            "mtime": stat.st_mtime
        }

        if expected_content is not None:
            try:
                with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                    actual_content = f.read()

                if expected_content.strip() not in actual_content:
                    return VerificationResult(
                        check_id=check_id,
                        check_type="file_content",
                        status="FAIL",
                        expected={"expected_snippet": expected_content[:120]},
                        observed={"actual_snippet": actual_content[:120]},
                        evidence=evidence,
                        error="File content does not contain expected snippet."
                    )
            except Exception as e:
                return VerificationResult(
                    check_id=check_id,
                    check_type="file_content",
                    status="FAIL",
                    expected="readable_text",
                    observed=f"read_error: {e}",
                    evidence=evidence,
                    error=f"Failed to read back file content: {e}"
                )

        return VerificationResult(
            check_id=check_id,
            check_type="file_existence",
            status="PASS",
            expected={"exists": True, "min_bytes": min_bytes},
            observed={"exists": True, "file_size": file_size},
            evidence=evidence
        )

    @staticmethod
    def verify_json_postcondition(
        path_or_content: Union[str, Path, dict],
        required_keys: Optional[List[str]] = None
    ) -> VerificationResult:
        """
        Parses JSON artifact or string and validates required schema keys.
        """
        check_id = f"json_check_{int(datetime.now().timestamp() * 1000)}"
        data: Any = None

        if isinstance(path_or_content, dict):
            data = path_or_content
        else:
            raw_str = str(path_or_content).strip()
            p = Path(raw_str)
            if p.is_file():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception as e:
                    return VerificationResult(
                        check_id=check_id,
                        check_type="json_schema",
                        status="FAIL",
                        expected="valid_json_file",
                        observed=f"json_parse_error: {e}",
                        error=f"Failed to parse JSON file {p}: {e}"
                    )
            else:
                try:
                    data = json.loads(raw_str)
                except Exception as e:
                    return VerificationResult(
                        check_id=check_id,
                        check_type="json_schema",
                        status="FAIL",
                        expected="valid_json_string",
                        observed=f"json_parse_error: {e}",
                        error=f"String is not valid JSON: {e}"
                    )

        if not isinstance(data, dict):
            return VerificationResult(
                check_id=check_id,
                check_type="json_schema",
                status="FAIL",
                expected={"type": "dict"},
                observed={"type": type(data).__name__},
                error=f"JSON root must be an object/dict, got {type(data).__name__}"
            )

        if required_keys:
            missing = [k for k in required_keys if k not in data]
            if missing:
                return VerificationResult(
                    check_id=check_id,
                    check_type="json_schema",
                    status="FAIL",
                    expected={"required_keys": required_keys},
                    observed={"missing_keys": missing, "present_keys": list(data.keys())},
                    error=f"JSON object is missing required keys: {missing}"
                )

        return VerificationResult(
            check_id=check_id,
            check_type="json_schema",
            status="PASS",
            expected={"valid_json": True, "required_keys": required_keys or []},
            observed={"key_count": len(data), "keys": list(data.keys())[:10]}
        )

    @staticmethod
    def verify_csv_postcondition(
        path_or_name: Union[str, Path],
        min_rows: int = 1,
        required_columns: Optional[List[str]] = None,
        location: str = "Desktop"
    ) -> VerificationResult:
        """
        Parses CSV artifact using csv.reader, validating row count and header columns.
        """
        from tools.file_tools import resolve_path
        check_id = f"csv_check_{int(datetime.now().timestamp() * 1000)}"

        target_path: Path
        p = Path(path_or_name)
        if p.is_absolute():
            target_path = p
        else:
            base_dir = resolve_path(location)
            target_path = base_dir / p

        if not target_path.exists():
            return VerificationResult(
                check_id=check_id,
                check_type="csv_structure",
                status="FAIL",
                expected={"exists": True},
                observed={"exists": False},
                error=f"CSV file does not exist: {target_path}"
            )

        try:
            with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.reader(f)
                rows = list(reader)

            if not rows:
                return VerificationResult(
                    check_id=check_id,
                    check_type="csv_structure",
                    status="FAIL",
                    expected={"min_rows": min_rows},
                    observed={"row_count": 0},
                    error=f"CSV file is empty (0 rows): {target_path}"
                )

            headers = [h.strip() for h in rows[0]]
            data_rows = rows[1:]

            if len(data_rows) < min_rows:
                return VerificationResult(
                    check_id=check_id,
                    check_type="csv_structure",
                    status="FAIL",
                    expected={"min_data_rows": min_rows},
                    observed={"data_rows": len(data_rows), "header": headers},
                    error=f"CSV contains {len(data_rows)} data rows, but expected at least {min_rows}."
                )

            if required_columns:
                missing_cols = [c for c in required_columns if c not in headers]
                if missing_cols:
                    return VerificationResult(
                        check_id=check_id,
                        check_type="csv_structure",
                        status="FAIL",
                        expected={"required_columns": required_columns},
                        observed={"missing_columns": missing_cols, "actual_columns": headers},
                        error=f"CSV header is missing required columns: {missing_cols}"
                    )

            return VerificationResult(
                check_id=check_id,
                check_type="csv_structure",
                status="PASS",
                expected={"min_rows": min_rows, "columns": required_columns or []},
                observed={"row_count": len(rows), "data_row_count": len(data_rows), "columns": headers},
                evidence={"path": str(target_path.resolve()), "row_count": len(rows)}
            )
        except Exception as e:
            return VerificationResult(
                check_id=check_id,
                check_type="csv_structure",
                status="FAIL",
                expected="valid_csv",
                observed=f"parse_error: {e}",
                error=f"Failed to parse CSV file: {e}"
            )

    @staticmethod
    def verify_python_syntax(path_or_code: Union[str, Path]) -> VerificationResult:
        """
        Parses Python code using ast.parse() to guarantee 100% syntactically valid code.
        """
        check_id = f"ast_check_{int(datetime.now().timestamp() * 1000)}"
        code_str: str

        p = Path(path_or_code) if isinstance(path_or_code, str) and len(path_or_code) < 300 else None
        if p and p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    code_str = f.read()
            except Exception as e:
                return VerificationResult(
                    check_id=check_id,
                    check_type="python_syntax",
                    status="FAIL",
                    expected="readable_python_file",
                    observed=f"read_error: {e}",
                    error=f"Failed to read python file: {e}"
                )
        else:
            code_str = str(path_or_code)

        try:
            tree = ast.parse(code_str)
            node_count = len(list(ast.walk(tree)))
            return VerificationResult(
                check_id=check_id,
                check_type="python_syntax",
                status="PASS",
                expected="valid_ast",
                observed={"node_count": node_count, "syntax_valid": True}
            )
        except SyntaxError as se:
            return VerificationResult(
                check_id=check_id,
                check_type="python_syntax",
                status="FAIL",
                expected="valid_syntax",
                observed={"line": se.lineno, "offset": se.offset, "msg": se.msg},
                error=f"Python SyntaxError at line {se.lineno}: {se.msg}"
            )
        except Exception as e:
            return VerificationResult(
                check_id=check_id,
                check_type="python_syntax",
                status="FAIL",
                expected="valid_ast",
                observed=str(e),
                error=f"AST parse error: {e}"
            )

    @classmethod
    def audit_and_enforce_truth(
        cls,
        candidate_response: str,
        tool_results: List[Dict[str, Any]],
        user_prompt: str = ""
    ) -> str:
        """
        Truth Enforcement Shield:
        Examines tool results and verification outcomes.
        If tools failed or postconditions failed, NEVER allows the model to state
        'Action completed successfully' or claim that an action succeeded.
        """
        has_tool_failure = any(
            t.get("status") in ("failed", "blocked") or
            str(t.get("result", "")).startswith(("Failed:", "Error:", "BLOCKED:", "Failed to "))
            for t in tool_results
        ) if tool_results else False

        if not has_tool_failure:
            return candidate_response

        # Find the specific failure
        failed_tools = [
            t for t in tool_results
            if t.get("status") in ("failed", "blocked") or
            str(t.get("result", "")).startswith(("Failed:", "Error:", "BLOCKED:", "Failed to "))
        ]
        fail_summary = []
        for ft in failed_tools[:2]:
            t_name = ft.get("name", "operation")
            t_err = str(ft.get("result", ""))[:120]
            fail_summary.append(f"{t_name} ({t_err})")

        error_details = "; ".join(fail_summary) if fail_summary else "An underlying tool error occurred."

        lower_resp = (candidate_response or "").lower()
        phantom_success_phrases = [
            "completed successfully", "i have created", "successfully created",
            "has been executed", "workspace is updated", "all done",
            "i have saved", "i have compiled", "i have written"
        ]

        if any(phrase in lower_resp for phrase in phantom_success_phrases) or not candidate_response.strip():
            return (
                f"Sir, I must report that the requested operation encountered a roadblock and could not be completed: "
                f"{error_details}. Please guide me on how you would like to proceed."
            )

        return (
            f"[Execution Alert: Operation encountered an issue: {error_details}]\n\n{candidate_response}"
        )

    def get_impacted_tests(
        self,
        modified_files_or_symbols: list[str],
        root_dir: Union[str, Path, None] = None
    ) -> list[str]:
        """
        Calculates the blast radius of modified files or symbols using the CodeGraphEngine.
        Returns the exact list of impacted test files that need to be executed for verification.
        """
        from core.code_graph_engine import code_graph_engine
        if not code_graph_engine.nodes or root_dir:
            code_graph_engine.index_directory(root_dir)

        impacted_tests: set[str] = set()
        for seed in modified_files_or_symbols:
            blast = code_graph_engine.compute_blast_radius(seed, depth=2)
            for t_file in blast.get("impacted_tests", []):
                impacted_tests.add(t_file)

        return sorted(impacted_tests)

    def verify_code_modification_impact(
        self,
        modified_files_or_symbols: list[str],
        root_dir: Union[str, Path, None] = None
    ) -> VerificationResult:
        """
        Audits code changes, computes downstream blast radius, and establishes the required test plan.
        """
        from core.code_graph_engine import code_graph_engine
        if not code_graph_engine.nodes or root_dir:
            code_graph_engine.index_directory(root_dir)

        all_impacted_symbols: set[str] = set()
        all_impacted_files: set[str] = set()
        all_impacted_tests: set[str] = set()
        total_hits = 0

        for seed in modified_files_or_symbols:
            blast = code_graph_engine.compute_blast_radius(seed, depth=2)
            total_hits += blast.get("total_affected", 0)
            all_impacted_symbols.update(blast.get("impacted_symbols", []))
            all_impacted_files.update(blast.get("impacted_files", []))
            all_impacted_tests.update(blast.get("impacted_tests", []))

        evidence = {
            "seeds": modified_files_or_symbols,
            "total_affected_nodes": total_hits,
            "impacted_symbols": sorted(all_impacted_symbols),
            "impacted_files": sorted(all_impacted_files),
            "impacted_tests": sorted(all_impacted_tests),
        }

        return VerificationResult(
            check_id=f"blast_radius_{hashlib.md5(str(modified_files_or_symbols).encode()).hexdigest()[:8]}",
            check_type="blast_radius_impact",
            status="PASS",
            expected="Bounded and identified downstream blast radius",
            observed=f"{total_hits} nodes affected across {len(all_impacted_files)} files ({len(all_impacted_tests)} test suites)",
            evidence=evidence
        )


truth_gatekeeper = TruthGatekeeper()
