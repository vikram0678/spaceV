"""
SpaceV Mission Commander & Autonomous Workforce Coordinator.
Orchestrates topological task decomposition, worker delegation,
state machine transitions, and empirical postcondition verification.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from core.durable_ledger import durable_ledger
from core.task_state_machine import TaskStateMachine
from core.truth_gatekeeper import truth_gatekeeper, VerificationResult

logger = logging.getLogger("SpaceV.MissionCommander")


@dataclass
class WorkforceTaskNode:
    task_id: str
    name: str
    worker_role: str  # "ResearchWorker", "SandboxExecutor", "CUADesktop", "TruthGatekeeper"
    dependencies: List[str] = field(default_factory=list)
    action_type: str = "tool"  # "tool", "sandbox_command", "verification"
    payload: Dict[str, Any] = field(default_factory=dict)
    postcondition_check: Optional[str] = None  # "file_exists", "json_valid", "csv_valid", "syntax_valid"
    postcondition_args: Dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 300
    status: str = "PENDING"
    result: Optional[Any] = None
    verification: Optional[VerificationResult] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None


class MissionCommander:
    """
    Coordinates multi-step autonomous workforce missions.
    Decomposes goals, delegates to specialized workers, tracks state in the durable ledger,
    and independently verifies postconditions before reporting completion.
    """

    def __init__(self, mission_id: Optional[str] = None, objective: str = ""):
        self.mission_id = mission_id or f"msn_{uuid.uuid4().hex[:8]}"
        self.objective = objective
        self.state_machine = TaskStateMachine(task_id=self.mission_id, objective=objective)
        self.tasks: Dict[str, WorkforceTaskNode] = {}
        self.execution_order: List[str] = []
        durable_ledger.record_mission(self.mission_id, objective, status="CREATED")

    def plan_mission(self, task_specs: List[Dict[str, Any]]) -> List[str]:
        """
        Decomposes mission into structured tasks with dependencies and postcondition rules.
        """
        self.state_machine.transition_to("PLANNED", f"Decomposed into {len(task_specs)} tasks")
        durable_ledger.update_mission_status(self.mission_id, "PLANNED")

        for spec in task_specs:
            t_id = spec.get("task_id") or f"task_{uuid.uuid4().hex[:6]}"
            node = WorkforceTaskNode(
                task_id=t_id,
                name=spec.get("name", "Unnamed task"),
                worker_role=spec.get("worker_role", "ResearchWorker"),
                dependencies=spec.get("dependencies", []),
                action_type=spec.get("action_type", "tool"),
                payload=spec.get("payload", {}),
                postcondition_check=spec.get("postcondition_check"),
                postcondition_args=spec.get("postcondition_args", {}),
                timeout_seconds=spec.get("timeout_seconds", 300)
            )
            self.tasks[t_id] = node
            self.execution_order.append(t_id)
            durable_ledger.record_task_node(
                task_id=t_id,
                mission_id=self.mission_id,
                name=node.name,
                worker_role=node.worker_role,
                status="PLANNED"
            )

        self.state_machine.transition_to("READY", "All tasks ready for execution")
        durable_ledger.update_mission_status(self.mission_id, "READY")
        return self.execution_order

    def execute_mission(self) -> Dict[str, Any]:
        """
        Executes all planned tasks in dependency order with empirical postcondition verification.
        """
        self.state_machine.transition_to("RUNNING", "Workforce execution started")
        durable_ledger.update_mission_status(self.mission_id, "RUNNING")
        t0 = time.perf_counter()

        from tools.registry import execute_tool_normalized

        completed_task_ids = set()
        failed_tasks = []

        for task_id in self.execution_order:
            node = self.tasks[task_id]

            # Check dependencies
            unmet = [dep for dep in node.dependencies if dep not in completed_task_ids]
            if unmet:
                node.status = "BLOCKED"
                node.error = f"Unmet dependencies: {unmet}"
                durable_ledger.update_task_node(task_id, "BLOCKED", error_summary=node.error)
                failed_tasks.append(task_id)
                continue

            node.status = "RUNNING"
            node.started_at = datetime.now(timezone.utc).isoformat()
            durable_ledger.update_task_node(task_id, "RUNNING")
            durable_ledger.record_event(task_id, "TASK_START", {"name": node.name, "worker": node.worker_role})

            # Execute action based on worker role
            t_exec_start = time.perf_counter()
            exec_res = None
            try:
                if node.worker_role == "SandboxExecutor":
                    from tools.sandbox_tools import CelestoSandboxRunner
                    runner = CelestoSandboxRunner(default_sandbox_id=f"sbx-{task_id[:8]}")
                    cmd = node.payload.get("command", "echo 'no command'")
                    raw_sbx_res = runner.run_in_sandbox(cmd)
                    exec_res = {
                        "success": raw_sbx_res.exit_code == 0 and not raw_sbx_res.blocked,
                        "data": raw_sbx_res.stdout,
                        "error": raw_sbx_res.stderr if raw_sbx_res.exit_code != 0 else None,
                        "metadata": {"environment": "celesto_microvm", "exit_code": raw_sbx_res.exit_code}
                    }
                else:
                    tool_name = node.payload.get("tool_name", "")
                    tool_args = node.payload.get("arguments", {})
                    raw_tool_res = execute_tool_normalized(tool_name, tool_args)
                    exec_res = {
                        "success": raw_tool_res.success,
                        "data": raw_tool_res.data,
                        "error": raw_tool_res.error,
                        "metadata": raw_tool_res.metadata
                    }

                node.result = exec_res.get("data")
                duration_s = time.perf_counter() - t_exec_start

                if not exec_res.get("success"):
                    node.status = "FAILED"
                    node.error = exec_res.get("error") or "Execution failed"
                    durable_ledger.update_task_node(task_id, "FAILED", error_summary=node.error, duration_s=duration_s)
                    failed_tasks.append(task_id)
                    continue

                # Run Deterministic Postcondition Verification
                if node.postcondition_check:
                    durable_ledger.record_event(task_id, "VERIFY_START", {"check": node.postcondition_check})
                    v_res: Optional[VerificationResult] = None
                    chk_type = node.postcondition_check
                    p_args = node.postcondition_args

                    if chk_type == "file_exists":
                        fname = p_args.get("file_name") or node.payload.get("arguments", {}).get("file_name", "")
                        loc = p_args.get("location") or node.payload.get("arguments", {}).get("location", "Desktop")
                        v_res = truth_gatekeeper.verify_file_postcondition(fname, location=loc)
                    elif chk_type == "json_valid":
                        target_content = node.result or p_args.get("content")
                        req_keys = p_args.get("required_keys")
                        v_res = truth_gatekeeper.verify_json_postcondition(target_content, required_keys=req_keys)
                    elif chk_type == "csv_valid":
                        target_path = p_args.get("file_name") or node.payload.get("arguments", {}).get("file_name", "")
                        min_rows = p_args.get("min_rows", 1)
                        req_cols = p_args.get("required_columns")
                        v_res = truth_gatekeeper.verify_csv_postcondition(target_path, min_rows=min_rows, required_columns=req_cols)
                    elif chk_type == "syntax_valid":
                        code_str = p_args.get("code") or node.payload.get("arguments", {}).get("code", "")
                        v_res = truth_gatekeeper.verify_python_syntax(code_str)

                    node.verification = v_res

                    if v_res and not v_res.passed:
                        node.status = "FAILED"
                        node.error = f"Verification check failed: {v_res.error}"
                        durable_ledger.record_verification(
                            task_id=task_id,
                            check_type=chk_type,
                            status="FAIL",
                            expected=v_res.expected,
                            observed=v_res.observed,
                            evidence=v_res.evidence,
                            error=v_res.error
                        )
                        durable_ledger.update_task_node(task_id, "FAILED", error_summary=node.error, duration_s=duration_s)
                        failed_tasks.append(task_id)
                        continue
                    elif v_res and v_res.passed:
                        durable_ledger.record_verification(
                            task_id=task_id,
                            check_type=chk_type,
                            status="PASS",
                            expected=v_res.expected,
                            observed=v_res.observed,
                            evidence=v_res.evidence
                        )

                node.status = "COMPLETED"
                node.finished_at = datetime.now(timezone.utc).isoformat()
                completed_task_ids.add(task_id)
                durable_ledger.update_task_node(task_id, "COMPLETED", duration_s=duration_s)
                durable_ledger.record_event(task_id, "TASK_COMPLETE", {"result_preview": str(node.result)[:100]})

            except Exception as e:
                node.status = "FAILED"
                node.error = str(e)
                durable_ledger.update_task_node(task_id, "FAILED", error_summary=str(e))
                failed_tasks.append(task_id)

        total_duration = time.perf_counter() - t0
        final_status = "COMPLETED" if not failed_tasks and len(completed_task_ids) == len(self.execution_order) else (
            "PARTIAL" if completed_task_ids else "FAILED"
        )

        # Invariant: Must transition through VERIFYING phase before reaching COMPLETED
        self.state_machine.transition_to("VERIFYING", "Verifying mission deliverables and postconditions")

        self.state_machine.transition_to(
            "COMPLETED" if final_status == "COMPLETED" else "FAILED",
            f"Execution finished: {len(completed_task_ids)}/{len(self.execution_order)} tasks succeeded"
        )
        durable_ledger.update_mission_status(self.mission_id, final_status, error_summary="; ".join([self.tasks[f].error or "" for f in failed_tasks]))

        return {
            "mission_id": self.mission_id,
            "status": final_status,
            "total_tasks": len(self.execution_order),
            "completed_tasks": len(completed_task_ids),
            "failed_tasks": len(failed_tasks),
            "total_duration_s": total_duration,
            "evidence": {t_id: {"status": self.tasks[t_id].status, "result": self.tasks[t_id].result, "error": self.tasks[t_id].error} for t_id in self.execution_order}
        }
