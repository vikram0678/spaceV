"""
SpaceV Workflow State & Durable Persistence Engine (Volume I §7 & Volume III §22).
Provides:
  - NodeStatus and WorkflowStatus formal enumerations
  - DAGNode: Unit of atomic work in a Directed Acyclic Graph
  - Workflow: Graph structure with node dependency resolution and budget limits
  - WorkflowStateManager: Atomic on-disk persistence, recovery, and audit trails in .spacev/workflows/
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import json
import logging
import os
from pathlib import Path
import tempfile
import time
from typing import Any
import uuid

logger = logging.getLogger("SpaceV.WorkflowState")


class NodeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING_APPROVAL = "waiting_approval"
    CANCELLED = "cancelled"


class WorkflowStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"         # Waiting for human approval
    CANCELLED = "cancelled"


@dataclass
class DAGNode:
    """
    A single node in the workflow DAG.
    Represents one atomic unit of work (e.g. analysis, code generation, testing, verification).
    """
    node_id: str
    name: str
    description: str = ""
    agent: str = "default"                # "planner", "coder", "auditor", "system"
    action: str = ""                      # Tool function name or agent instruction
    action_args: dict[str, Any] = field(default_factory=dict)

    # DAG edges
    depends_on: list[str] = field(default_factory=list)

    # Execution config
    max_retries: int = 2
    timeout_sec: float = 120.0
    requires_approval: bool = False       # Human-in-the-loop gate

    # Conditional execution
    condition: str = ""                   # Python expression evaluated against parent results

    # Runtime state
    status: NodeStatus = NodeStatus.PENDING
    result: Any = None
    error: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0
    retry_count: int = 0
    token_usage: int = 0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DAGNode:
        data_copy = dict(data)
        data_copy["status"] = NodeStatus(data_copy.get("status", "pending"))
        return cls(**data_copy)


@dataclass
class Workflow:
    """
    A complete workflow DAG definition with concurrency and budget management.
    """
    workflow_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    description: str = ""
    goal: str = ""

    nodes: list[DAGNode] = field(default_factory=list)

    # State
    status: WorkflowStatus = WorkflowStatus.CREATED
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    completed_at: float = 0.0
    total_token_usage: int = 0

    # Budget constraints
    max_total_tokens: int = 10000
    max_wall_time_sec: float = 600.0

    def get_node(self, node_id: str) -> DAGNode | None:
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        return None

    def get_ready_nodes(self) -> list[DAGNode]:
        """Returns pending nodes whose parents have all succeeded or skipped."""
        ready: list[DAGNode] = []
        for node in self.nodes:
            if node.status != NodeStatus.PENDING:
                continue

            deps_satisfied = True
            for dep_id in node.depends_on:
                dep_node = self.get_node(dep_id)
                if dep_node is None or dep_node.status not in (NodeStatus.COMPLETED, NodeStatus.SKIPPED):
                    deps_satisfied = False
                    break

            if deps_satisfied:
                ready.append(node)

        return ready

    def has_active_nodes(self) -> bool:
        return any(n.status in (NodeStatus.RUNNING, NodeStatus.WAITING_APPROVAL) for n in self.nodes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "goal": self.goal,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "total_token_usage": self.total_token_usage,
            "max_total_tokens": self.max_total_tokens,
            "max_wall_time_sec": self.max_wall_time_sec,
            "nodes": [n.to_dict() for n in self.nodes],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Workflow:
        data_copy = dict(data)
        nodes_raw = data_copy.pop("nodes", [])
        nodes = [DAGNode.from_dict(n) for n in nodes_raw]
        data_copy["status"] = WorkflowStatus(data_copy.get("status", "created"))
        return cls(nodes=nodes, **data_copy)


class WorkflowStateManager:
    """
    Durable on-disk storage engine for SpaceV workflows.
    Guarantees atomic file writes and crash-recovery semantics in .spacev/workflows/.
    """

    def __init__(self, state_dir: Path | str = ".spacev/workflows"):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def save_workflow(self, workflow: Workflow) -> Path:
        """
        Atomically saves workflow state to .spacev/workflows/<workflow_id>.json.
        Uses temporary file + atomic rename to prevent corruption.
        """
        target_path = self.state_dir / f"{workflow.workflow_id}.json"
        data_json = json.dumps(workflow.to_dict(), indent=2)

        # Write to temporary file in the same directory for atomic rename
        temp_fd, temp_path_str = tempfile.mkstemp(
            prefix=f".{workflow.workflow_id}_",
            suffix=".tmp",
            dir=str(self.state_dir)
        )
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                f.write(data_json)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path_str, target_path)
            logger.debug(f"[WORKFLOW_STATE] Saved workflow {workflow.workflow_id} to {target_path}")
            return target_path
        except Exception as e:
            if os.path.exists(temp_path_str):
                try:
                    os.unlink(temp_path_str)
                except OSError:
                    pass
            logger.error(f"[WORKFLOW_STATE] Failed to save workflow {workflow.workflow_id}: {e}")
            raise

    def load_workflow(self, workflow_id: str) -> Workflow | None:
        """Loads a workflow definition and state from disk."""
        target_path = self.state_dir / f"{workflow_id}.json"
        if not target_path.exists():
            return None
        try:
            content = target_path.read_text(encoding="utf-8")
            data = json.loads(content)
            return Workflow.from_dict(data)
        except Exception as e:
            logger.error(f"[WORKFLOW_STATE] Failed to load workflow {workflow_id}: {e}")
            return None

    def list_workflows(self, status_filter: str | None = None) -> list[dict[str, Any]]:
        """Lists all persisted workflows, sorted by created_at descending."""
        results: list[dict[str, Any]] = []
        for path in self.state_dir.glob("*.json"):
            try:
                content = path.read_text(encoding="utf-8")
                data = json.loads(content)
                status = data.get("status")
                if status_filter and status != status_filter:
                    continue
                results.append({
                    "workflow_id": data.get("workflow_id"),
                    "name": data.get("name"),
                    "goal": data.get("goal"),
                    "status": status,
                    "created_at": data.get("created_at", 0.0),
                    "completed_at": data.get("completed_at", 0.0),
                    "total_token_usage": data.get("total_token_usage", 0),
                    "node_count": len(data.get("nodes", [])),
                })
            except Exception:
                continue
        return sorted(results, key=lambda x: x.get("created_at", 0.0), reverse=True)

    def recover_active_workflows(self) -> list[Workflow]:
        """
        Discovers any workflows that were interrupted mid-flight (e.g. power loss or process kill).
        Transitions RUNNING workflows to PAUSED so they can be inspected and resumed safely.
        """
        recovered: list[Workflow] = []
        for summary in self.list_workflows():
            w_id = summary["workflow_id"]
            wf = self.load_workflow(w_id)
            if not wf:
                continue
            if wf.status == WorkflowStatus.RUNNING:
                logger.warning(f"[WORKFLOW_STATE] Recovering interrupted workflow {wf.workflow_id} -> Marking as PAUSED")
                wf.status = WorkflowStatus.PAUSED
                # Also reset running nodes to pending or failed
                for node in wf.nodes:
                    if node.status == NodeStatus.RUNNING:
                        node.status = NodeStatus.PENDING
                self.save_workflow(wf)
                recovered.append(wf)
            elif wf.status == WorkflowStatus.PAUSED:
                recovered.append(wf)
        return recovered

    def delete_workflow(self, workflow_id: str) -> bool:
        """Deletes a workflow state file."""
        target_path = self.state_dir / f"{workflow_id}.json"
        if target_path.exists():
            try:
                target_path.unlink()
                return True
            except OSError as e:
                logger.error(f"[WORKFLOW_STATE] Failed to delete workflow {workflow_id}: {e}")
                return False
        return False


# Global default instance
workflow_state_manager = WorkflowStateManager()
