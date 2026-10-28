"""
SpaceV DAG Workflow Execution Engine (Volume I §7 & Volume III §22).
Implements:
  - Directed Acyclic Graph (DAG) topological resolution with parallel fan-out (asyncio.gather)
  - LoopGuard: bounded iterations and wall-clock safety (OpenJarvis pattern)
  - ApprovalStore: Human-In-The-Loop gate with durable approval records (.spacev/approvals/)
  - Conditional branch evaluation based on parent node outcomes
  - Bounded retries with exponential backoff
  - Token budget tracking per node and per workflow
  - Automatic durable disk persistence via WorkflowStateManager
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
import json
import logging
import os
from pathlib import Path
import tempfile
import time
from typing import Any
import uuid

from core.workflow_state import (
    DAGNode,
    NodeStatus,
    Workflow,
    WorkflowStatus,
    workflow_state_manager,
)
from tools.registry import execute_tool

logger = logging.getLogger("SpaceV.WorkflowEngine")


class LoopGuard:
    """
    Prevents infinite execution loops in DAG workflows.
    Inspired by the OpenJarvis LoopGuard pattern.
    """

    def __init__(self, max_iterations: int = 50, max_wall_sec: float = 600.0):
        self.max_iterations = max_iterations
        self.max_wall_sec = max_wall_sec
        self._iteration_count = 0
        self._start_time = time.time()

    def check(self) -> tuple[bool, str]:
        """Check if execution should continue. Returns (ok, reason)."""
        self._iteration_count += 1

        if self._iteration_count > self.max_iterations:
            return False, f"Max iterations exceeded ({self.max_iterations})"

        elapsed = time.time() - self._start_time
        if elapsed > self.max_wall_sec:
            return False, f"Wall time exceeded ({self.max_wall_sec:.1f}s)"

        return True, "ok"

    @property
    def iterations(self) -> int:
        return self._iteration_count

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self._start_time


class ApprovalStore:
    """
    Human-in-the-loop approval gate for sensitive workflow operations.
    Stores and manages approval tokens in .spacev/approvals/.
    """

    def __init__(self, state_dir: Path | str = ".spacev/approvals"):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._pending: dict[str, dict[str, Any]] = {}
        self._load_existing_approvals()

    def _load_existing_approvals(self):
        for f in self.state_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                req_id = data.get("request_id") or f.stem
                self._pending[req_id] = data
            except Exception:
                continue

    def request_approval(self, node_id: str, description: str, workflow_id: str = "") -> str:
        """Requests human approval. Returns a unique request ID."""
        request_id = uuid.uuid4().hex[:8]
        entry = {
            "request_id": request_id,
            "node_id": node_id,
            "description": description,
            "workflow_id": workflow_id,
            "requested_at": time.time(),
            "status": "pending",
        }
        self._pending[request_id] = entry
        self._persist_request(request_id)
        logger.info(f"[APPROVAL] Requested approval for node '{node_id}' ({request_id}): {description}")
        return request_id

    def is_approved(self, request_id: str) -> bool:
        """Checks if a request has been explicitly approved."""
        entry = self._pending.get(request_id)
        if not entry:
            self._load_existing_approvals()
            entry = self._pending.get(request_id)
        return entry is not None and entry.get("status") == "approved"

    def approve(self, request_id: str) -> bool:
        """Grants human approval for a pending request."""
        if request_id in self._pending:
            self._pending[request_id]["status"] = "approved"
            self._pending[request_id]["decided_at"] = time.time()
            self._persist_request(request_id)
            logger.info(f"[APPROVAL] Granted approval for request {request_id}")
            return True
        return False

    def deny(self, request_id: str) -> bool:
        """Denies human approval."""
        if request_id in self._pending:
            self._pending[request_id]["status"] = "denied"
            self._pending[request_id]["decided_at"] = time.time()
            self._persist_request(request_id)
            logger.info(f"[APPROVAL] Denied approval for request {request_id}")
            return True
        return False

    def get_pending_approvals(self) -> list[dict[str, Any]]:
        return [item for item in self._pending.values() if item.get("status") == "pending"]

    def _persist_request(self, request_id: str):
        target_path = self.state_dir / f"{request_id}.json"
        data_json = json.dumps(self._pending[request_id], indent=2)
        target_path.write_text(data_json, encoding="utf-8")


class SpaceVWorkflowEngine:
    """
    DAG-based workflow execution engine for SpaceV.
    Executes tasks in topological stages with parallel fan-out, retry loops,
    conditional gates, and durable state persistence.
    """

    def __init__(
        self,
        state_manager=None,
        approval_store: ApprovalStore | None = None,
        event_bus: Any | None = None,
        node_executor: Callable[[DAGNode, Workflow], Any] | None = None,
    ):
        self.state_manager = state_manager or workflow_state_manager
        self.approval_store = approval_store or ApprovalStore()
        self.event_bus = event_bus
        self.node_executor = node_executor or self._default_tool_node_executor
        self._active_workflows: dict[str, Workflow] = {}
        self._node_approval_requests: dict[str, str] = {}  # node_id -> request_id

    async def execute_workflow(self, workflow: Workflow) -> Workflow:
        """
        Executes a workflow DAG to completion or pause.
        """
        workflow.status = WorkflowStatus.RUNNING
        workflow.started_at = time.time()
        self._active_workflows[workflow.workflow_id] = workflow
        self.state_manager.save_workflow(workflow)

        loop_guard = LoopGuard(
            max_iterations=max(20, len(workflow.nodes) * 4),
            max_wall_sec=workflow.max_wall_time_sec,
        )

        logger.info(f"[WORKFLOW] Starting workflow '{workflow.name}' ({workflow.workflow_id}) with {len(workflow.nodes)} nodes")
        self._emit_event("workflow.started", {"workflow_id": workflow.workflow_id, "name": workflow.name})

        try:
            while True:
                # 1. Loop guard checks
                ok, reason = loop_guard.check()
                if not ok:
                    logger.warning(f"[WORKFLOW] LoopGuard stopped workflow {workflow.workflow_id}: {reason}")
                    workflow.status = WorkflowStatus.FAILED
                    break

                # 2. Token budget check
                if workflow.total_token_usage >= workflow.max_total_tokens:
                    logger.warning(f"[WORKFLOW] Workflow {workflow.workflow_id} exceeded token budget: {workflow.total_token_usage}/{workflow.max_total_tokens}")
                    workflow.status = WorkflowStatus.FAILED
                    break

                # 3. Find ready nodes whose dependencies are satisfied
                ready_nodes = workflow.get_ready_nodes()

                if not ready_nodes:
                    # Check terminal state
                    all_finished = all(
                        n.status in (NodeStatus.COMPLETED, NodeStatus.SKIPPED, NodeStatus.CANCELLED)
                        for n in workflow.nodes
                    )
                    if all_finished:
                        workflow.status = WorkflowStatus.COMPLETED
                    else:
                        has_waiting = any(n.status == NodeStatus.WAITING_APPROVAL for n in workflow.nodes)
                        has_failures = any(n.status == NodeStatus.FAILED for n in workflow.nodes)
                        if has_waiting:
                            workflow.status = WorkflowStatus.PAUSED
                        elif has_failures:
                            workflow.status = WorkflowStatus.FAILED
                        else:
                            # Dependency deadlock or unknown stall
                            workflow.status = WorkflowStatus.FAILED
                    break

                # 4. Filter ready nodes for human approval gates
                runnable_nodes: list[DAGNode] = []
                for node in ready_nodes:
                    if node.requires_approval:
                        req_id = self._node_approval_requests.get(node.node_id)
                        if not req_id:
                            req_id = self.approval_store.request_approval(
                                node_id=node.node_id,
                                description=f"Approve execution of '{node.name}': {node.description or node.action}",
                                workflow_id=workflow.workflow_id
                            )
                            self._node_approval_requests[node.node_id] = req_id

                        if not self.approval_store.is_approved(req_id):
                            node.status = NodeStatus.WAITING_APPROVAL
                            self._emit_event("workflow.approval_needed", {
                                "workflow_id": workflow.workflow_id,
                                "node_id": node.node_id,
                                "request_id": req_id,
                                "description": node.description,
                            })
                            continue
                        else:
                            # Approved!
                            node.requires_approval = False

                    runnable_nodes.append(node)

                if not runnable_nodes:
                    # If all ready nodes are waiting for approval, pause workflow
                    if any(n.status == NodeStatus.WAITING_APPROVAL for n in ready_nodes):
                        workflow.status = WorkflowStatus.PAUSED
                    break

                # 5. Parallel fan-out execution via asyncio.gather
                tasks = [self._execute_node(workflow, node) for node in runnable_nodes]
                await asyncio.gather(*tasks, return_exceptions=True)

                # 6. Checkpoint state to disk after each wave
                self.state_manager.save_workflow(workflow)

        except Exception as e:
            logger.error(f"[WORKFLOW] Execution failure in workflow {workflow.workflow_id}: {e}", exc_info=True)
            workflow.status = WorkflowStatus.FAILED

        workflow.completed_at = time.time()
        self.state_manager.save_workflow(workflow)

        event_name = "workflow.completed" if workflow.status == WorkflowStatus.COMPLETED else "workflow.failed"
        self._emit_event(event_name, workflow.to_dict())

        logger.info(f"[WORKFLOW] Workflow '{workflow.name}' finished with status '{workflow.status.value}' "
                    f"in {workflow.completed_at - workflow.started_at:.2f}s (tokens: {workflow.total_token_usage})")
        return workflow

    async def _execute_node(self, workflow: Workflow, node: DAGNode):
        """Executes an individual node with conditional evaluation, retries, and timeout."""
        # 1. Evaluate condition if present
        if node.condition:
            parent_results = {
                dep_id: {
                    "status": workflow.get_node(dep_id).status.value if workflow.get_node(dep_id) else "unknown",
                    "result": workflow.get_node(dep_id).result if workflow.get_node(dep_id) else None,
                }
                for dep_id in node.depends_on
            }
            try:
                # Safe eval with parent_results in scope
                should_run = eval(node.condition, {"__builtins__": {}}, {"parent_results": parent_results})
                if not should_run:
                    node.status = NodeStatus.SKIPPED
                    node.completed_at = time.time()
                    logger.info(f"[WORKFLOW] Node '{node.name}' skipped (condition not met)")
                    return
            except Exception as cond_err:
                logger.warning(f"[WORKFLOW] Condition evaluation failed for '{node.name}': {cond_err}")

        node.status = NodeStatus.RUNNING
        node.started_at = time.time()
        self._emit_event("workflow.node_started", {"workflow_id": workflow.workflow_id, "node_id": node.node_id})

        for attempt in range(node.max_retries + 1):
            try:
                result = await asyncio.wait_for(
                    self._invoke_executor(node, workflow),
                    timeout=node.timeout_sec
                )
                node.result = result
                node.status = NodeStatus.COMPLETED
                node.completed_at = time.time()

                # Extract token usage if reported
                if isinstance(result, dict) and "token_usage" in result:
                    node.token_usage = int(result["token_usage"])
                    workflow.total_token_usage += node.token_usage

                self._emit_event("workflow.node_done", {
                    "workflow_id": workflow.workflow_id,
                    "node_id": node.node_id,
                    "status": "completed",
                    "result": str(result)[:200],
                })
                logger.info(f"[WORKFLOW] Node '{node.name}' completed (attempt {attempt + 1})")
                return

            except asyncio.TimeoutError:
                node.retry_count = attempt + 1
                node.error = f"Node timed out after {node.timeout_sec}s"
                logger.warning(f"[WORKFLOW] Node '{node.name}' timed out on attempt {attempt + 1}")
            except Exception as e:
                node.retry_count = attempt + 1
                node.error = str(e)
                logger.warning(f"[WORKFLOW] Node '{node.name}' failed on attempt {attempt + 1}: {e}")

            if attempt < node.max_retries:
                # Exponential backoff: 0.1s, 0.2s, 0.4s (capped for speed in local systems)
                backoff = min(2.0, 0.1 * (2 ** attempt))
                await asyncio.sleep(backoff)

        # Retries exhausted
        node.status = NodeStatus.FAILED
        node.completed_at = time.time()
        self._emit_event("workflow.node_done", {
            "workflow_id": workflow.workflow_id,
            "node_id": node.node_id,
            "status": "failed",
            "error": node.error,
        })

    async def _invoke_executor(self, node: DAGNode, workflow: Workflow) -> Any:
        """Calls node executor, awaiting it if coroutine or calling in thread if synchronous."""
        if asyncio.iscoroutinefunction(self.node_executor):
            return await self.node_executor(node, workflow)
        return await asyncio.to_thread(self.node_executor, node, workflow)

    async def _default_tool_node_executor(self, node: DAGNode, workflow: Workflow) -> Any:
        """Default executor invoking registered SpaceV tools by action name."""
        if not node.action:
            return {"status": "success", "note": "noop"}
        try:
            res = execute_tool(node.action, **node.action_args)
            return {"status": "success", "output": res}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def resume_workflow(self, workflow_id: str) -> Workflow | None:
        """
        Resumes a paused workflow (e.g. after approval is granted or human intervention).
        """
        wf = self.state_manager.load_workflow(workflow_id)
        if not wf:
            logger.error(f"[WORKFLOW] Cannot resume: workflow {workflow_id} not found on disk")
            return None

        # Reset paused/waiting nodes that now have approval
        for node in wf.nodes:
            if node.status == NodeStatus.WAITING_APPROVAL:
                req_id = self._node_approval_requests.get(node.node_id)
                if req_id and self.approval_store.is_approved(req_id):
                    node.status = NodeStatus.PENDING
                    node.requires_approval = False

        return await self.execute_workflow(wf)

    def cancel_workflow(self, workflow_id: str) -> bool:
        """Cancels an active or paused workflow."""
        wf = self._active_workflows.get(workflow_id) or self.state_manager.load_workflow(workflow_id)
        if not wf:
            return False

        wf.status = WorkflowStatus.CANCELLED
        wf.completed_at = time.time()
        for node in wf.nodes:
            if node.status in (NodeStatus.PENDING, NodeStatus.RUNNING, NodeStatus.WAITING_APPROVAL):
                node.status = NodeStatus.CANCELLED
        self.state_manager.save_workflow(wf)
        self._emit_event("workflow.cancelled", {"workflow_id": workflow_id})
        logger.info(f"[WORKFLOW] Cancelled workflow {workflow_id}")
        return True

    def _emit_event(self, event_type: str, data: dict[str, Any]):
        if self.event_bus:
            try:
                if hasattr(self.event_bus, "publish"):
                    self.event_bus.publish(event_type, data)
                elif callable(self.event_bus):
                    self.event_bus(event_type, data)
            except Exception as e:
                logger.debug(f"[WORKFLOW] Event emit failed for {event_type}: {e}")


# Global default instance
workflow_engine = SpaceVWorkflowEngine()
