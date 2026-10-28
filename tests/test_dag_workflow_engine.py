"""
SpaceV DAG Workflow Engine & State Machine Verification Suite.
Validates:
  - Parallel fan-out execution via asyncio.gather
  - Dependency resolution and topological ordering
  - Conditional branch skipping based on parent results
  - LoopGuard iteration and wall-time ceilings
  - Human-in-the-loop ApprovalStore pausing and resumption
  - Bounded retries with backoff on node failures
  - Token budget tracking and enforcement per workflow
  - Atomic on-disk persistence and crash recovery in .spacev/workflows/
  - Brain orchestrator complexity heuristics and workflow construction
"""
from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
import time
import pytest

from core.brain_orchestrator import HybridBrainAgent
from core.workflow_engine import (
    ApprovalStore,
    LoopGuard,
    SpaceVWorkflowEngine,
)
from core.workflow_state import (
    DAGNode,
    NodeStatus,
    Workflow,
    WorkflowStateManager,
    WorkflowStatus,
)


@pytest.fixture
def temp_workflow_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.mark.asyncio
async def test_dag_parallel_fanout_execution(temp_workflow_dir):
    """
    Empirical proof of parallel fan-out:
    Two independent nodes each sleeping for 0.1s execute concurrently via asyncio.gather.
    Total elapsed time must be significantly less than serial execution (0.2s).
    """
    state_mgr = WorkflowStateManager(state_dir=temp_workflow_dir / "workflows")
    execution_order = []

    async def custom_executor(node: DAGNode, wf: Workflow):
        execution_order.append(f"start_{node.node_id}")
        await asyncio.sleep(0.1)
        execution_order.append(f"end_{node.node_id}")
        return {"status": "ok", "node": node.node_id}

    engine = SpaceVWorkflowEngine(state_manager=state_mgr, node_executor=custom_executor)

    node1 = DAGNode(node_id="n1", name="Parallel Worker 1")
    node2 = DAGNode(node_id="n2", name="Parallel Worker 2")
    node3 = DAGNode(node_id="n3", name="Aggregator", depends_on=["n1", "n2"])

    wf = Workflow(
        name="Parallel Test",
        nodes=[node1, node2, node3]
    )

    t0 = time.time()
    completed_wf = await engine.execute_workflow(wf)
    elapsed = time.time() - t0

    assert completed_wf.status == WorkflowStatus.COMPLETED
    assert node1.status == NodeStatus.COMPLETED
    assert node2.status == NodeStatus.COMPLETED
    assert node3.status == NodeStatus.COMPLETED

    # Both n1 and n2 started before either finished (concurrency evidence)
    assert execution_order.index("start_n1") < execution_order.index("end_n2")
    assert execution_order.index("start_n2") < execution_order.index("end_n1")

    # Aggregator n3 must start strictly AFTER n1 and n2 completed
    assert execution_order.index("start_n3") > execution_order.index("end_n1")
    assert execution_order.index("start_n3") > execution_order.index("end_n2")

    # Time check: parallel wave (0.1s) + aggregator (0.1s) ~ 0.2s (serial would be 0.3s)
    assert elapsed < 0.28


@pytest.mark.asyncio
async def test_dag_conditional_execution_skip(temp_workflow_dir):
    """
    Verifies conditional branches: a node is skipped if its parent condition evaluates to False.
    """
    state_mgr = WorkflowStateManager(state_dir=temp_workflow_dir / "workflows")

    async def custom_executor(node: DAGNode, wf: Workflow):
        if node.node_id == "check_auth":
            return {"authenticated": False}
        return {"action": "performed"}

    engine = SpaceVWorkflowEngine(state_manager=state_mgr, node_executor=custom_executor)

    check_node = DAGNode(node_id="check_auth", name="Check Auth")
    # Condition: only run if parent check_auth returned authenticated == True
    admin_node = DAGNode(
        node_id="admin_task",
        name="Admin Task",
        depends_on=["check_auth"],
        condition="parent_results['check_auth']['result']['authenticated'] == True"
    )

    wf = Workflow(name="Conditional Test", nodes=[check_node, admin_node])
    completed_wf = await engine.execute_workflow(wf)

    assert completed_wf.status == WorkflowStatus.COMPLETED
    assert check_node.status == NodeStatus.COMPLETED
    assert admin_node.status == NodeStatus.SKIPPED


@pytest.mark.asyncio
async def test_approval_store_gate_and_resume(temp_workflow_dir):
    """
    Verifies that a sensitive node marked requires_approval=True pauses the workflow
    in PAUSED status until human approval is recorded, and resume_workflow completes it.
    """
    state_mgr = WorkflowStateManager(state_dir=temp_workflow_dir / "workflows")
    approval_store = ApprovalStore(state_dir=temp_workflow_dir / "approvals")

    async def custom_executor(node: DAGNode, wf: Workflow):
        return {"result": f"Executed {node.name}"}

    engine = SpaceVWorkflowEngine(
        state_manager=state_mgr,
        approval_store=approval_store,
        node_executor=custom_executor
    )

    safe_node = DAGNode(node_id="read_spec", name="Read Spec")
    sensitive_node = DAGNode(
        node_id="deploy_prod",
        name="Deploy to Production",
        depends_on=["read_spec"],
        requires_approval=True
    )

    wf = Workflow(name="Approval Test", nodes=[safe_node, sensitive_node])

    # 1. Execute initial run -> should pause at sensitive_node
    paused_wf = await engine.execute_workflow(wf)
    assert paused_wf.status == WorkflowStatus.PAUSED
    assert safe_node.status == NodeStatus.COMPLETED
    assert sensitive_node.status == NodeStatus.WAITING_APPROVAL

    # Verify approval record was created on disk
    pending = approval_store.get_pending_approvals()
    assert len(pending) == 1
    req_id = pending[0]["request_id"]
    assert pending[0]["node_id"] == "deploy_prod"

    # 2. Grant approval
    approved = approval_store.approve(req_id)
    assert approved is True
    assert approval_store.is_approved(req_id) is True

    # 3. Resume workflow -> should finish sensitive_node
    resumed_wf = await engine.resume_workflow(wf.workflow_id)
    assert resumed_wf is not None
    assert resumed_wf.status == WorkflowStatus.COMPLETED
    assert resumed_wf.get_node("deploy_prod").status == NodeStatus.COMPLETED


@pytest.mark.asyncio
async def test_node_retry_with_exponential_backoff(temp_workflow_dir):
    """
    Verifies that failing nodes retry up to max_retries before marking failure.
    """
    state_mgr = WorkflowStateManager(state_dir=temp_workflow_dir / "workflows")
    attempts = {"count": 0}

    async def flakey_executor(node: DAGNode, wf: Workflow):
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise RuntimeError("Transient connection reset")
        return {"status": "recovered"}

    engine = SpaceVWorkflowEngine(state_manager=state_mgr, node_executor=flakey_executor)

    node = DAGNode(node_id="net_op", name="Network Operation", max_retries=2)
    wf = Workflow(name="Retry Test", nodes=[node])

    completed_wf = await engine.execute_workflow(wf)
    assert completed_wf.status == WorkflowStatus.COMPLETED
    assert node.status == NodeStatus.COMPLETED
    assert node.retry_count == 1
    assert attempts["count"] == 2


@pytest.mark.asyncio
async def test_token_budget_enforcement(temp_workflow_dir):
    """
    Verifies that total token usage is accumulated across nodes and triggers FAILED status
    if the workflow token ceiling is exceeded.
    """
    state_mgr = WorkflowStateManager(state_dir=temp_workflow_dir / "workflows")

    async def heavy_token_executor(node: DAGNode, wf: Workflow):
        return {"status": "done", "token_usage": 3000}

    engine = SpaceVWorkflowEngine(state_manager=state_mgr, node_executor=heavy_token_executor)

    node1 = DAGNode(node_id="step1", name="Step 1")
    node2 = DAGNode(node_id="step2", name="Step 2", depends_on=["step1"])
    node3 = DAGNode(node_id="step3", name="Step 3", depends_on=["step2"])

    # Cap total tokens at 5000 (after step 1 & 2 = 6000, step 3 should not run)
    wf = Workflow(name="Budget Test", nodes=[node1, node2, node3], max_total_tokens=5000)

    failed_wf = await engine.execute_workflow(wf)
    assert failed_wf.status == WorkflowStatus.FAILED
    assert failed_wf.total_token_usage >= 5000


def test_loop_guard_limits():
    """
    Validates LoopGuard halts runaway iterations and elapsed wall time.
    """
    guard = LoopGuard(max_iterations=5, max_wall_sec=0.5)

    # 1. Test iteration cap
    for _ in range(5):
        ok, reason = guard.check()
        assert ok is True

    # 6th iteration exceeds max_iterations=5
    ok, reason = guard.check()
    assert ok is False
    assert "Max iterations exceeded" in reason

    # 2. Test wall-time limit
    time_guard = LoopGuard(max_iterations=1000, max_wall_sec=0.05)
    time.sleep(0.06)
    ok, reason = time_guard.check()
    assert ok is False
    assert "Wall time exceeded" in reason


def test_workflow_state_persistence_and_recovery(temp_workflow_dir):
    """
    Verifies atomic disk writes and discovery/recovery of interrupted workflows.
    """
    state_mgr = WorkflowStateManager(state_dir=temp_workflow_dir / "workflows")

    node1 = DAGNode(node_id="a", name="Node A", status=NodeStatus.COMPLETED)
    node2 = DAGNode(node_id="b", name="Node B", status=NodeStatus.RUNNING)
    wf = Workflow(workflow_id="wf_audit_1", name="Audit Workflow", nodes=[node1, node2], status=WorkflowStatus.RUNNING)

    # 1. Save workflow atomically
    target_path = state_mgr.save_workflow(wf)
    assert target_path.exists()

    # 2. Load workflow from disk
    loaded = state_mgr.load_workflow("wf_audit_1")
    assert loaded is not None
    assert loaded.name == "Audit Workflow"
    assert len(loaded.nodes) == 2
    assert loaded.nodes[0].name == "Node A"

    # 3. List workflows
    listing = state_mgr.list_workflows()
    assert len(listing) == 1
    assert listing[0]["workflow_id"] == "wf_audit_1"

    # 4. Recover active/interrupted workflows
    recovered = state_mgr.recover_active_workflows()
    assert len(recovered) == 1
    # Status should have been safely converted from RUNNING to PAUSED
    assert recovered[0].status == WorkflowStatus.PAUSED
    assert recovered[0].get_node("b").status == NodeStatus.PENDING


def test_brain_orchestrator_workflow_routing():
    """
    Verifies HybridBrainAgent complexity heuristics and DAG workflow generation.
    """
    agent = HybridBrainAgent()

    # 1. Simple queries should not trigger workflow
    assert agent.is_complex_workflow("what is the weather today?") is False
    assert agent.is_complex_workflow("read file main.py") is False

    # 2. Multi-step / parallel queries should trigger workflow
    assert agent.is_complex_workflow("execute this in parallel across tests") is True
    assert agent.is_complex_workflow("create a workflow to build and test the app") is True
    assert agent.is_complex_workflow("first inspect the code, then run tests, finally deploy") is True

    # 3. Create workflow from planned steps
    planned_steps = [
        {"id": "s1", "name": "Compile code", "action": "compile"},
        {"id": "s2", "name": "Run unit tests", "action": "test", "depends_on": ["s1"]},
        {"id": "s3", "name": "Publish report", "action": "report", "depends_on": ["s2"], "requires_approval": True},
    ]

    wf = agent.create_workflow_from_plan(
        goal="Compile and test project",
        steps=planned_steps,
        workflow_name="CI Pipeline"
    )

    assert wf.name == "CI Pipeline"
    assert len(wf.nodes) == 3
    assert wf.get_node("s2").depends_on == ["s1"]
    assert wf.get_node("s3").requires_approval is True
    assert wf.status == WorkflowStatus.CREATED
