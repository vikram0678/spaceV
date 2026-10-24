"""
Unit and integration tests for SpaceV Code Graph Engine, AST Extraction,
Reverse-Walk Blast Radius Analysis, and Truth Gatekeeper Test Selection.
"""

import json
from pathlib import Path
import pytest
from core.code_graph_engine import CodeGraphEngine, code_graph_engine
from core.truth_gatekeeper import truth_gatekeeper
from tools.registry import (
    CODE_TOOL_NAMES,
    execute_tool_normalized,
    get_scoped_tools,
)


@pytest.fixture
def temp_codebase(tmp_path: Path):
    """Creates a miniature multi-file Python project to test AST extraction & blast radius."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()

    # Base class
    (pkg / "base.py").write_text(
        "class BaseHandler:\n"
        "    def handle(self):\n"
        "        pass\n"
    )

    # Derived class & callers
    (pkg / "service.py").write_text(
        "from pkg.base import BaseHandler\n\n"
        "class OrderService(BaseHandler):\n"
        "    def process_order(self, order_id):\n"
        "        self.handle()\n"
        "        return order_id\n"
    )

    # Consumer
    (pkg / "controller.py").write_text(
        "from pkg.service import OrderService\n\n"
        "def checkout_endpoint():\n"
        "    svc = OrderService()\n"
        "    return svc.process_order(123)\n"
    )

    # Tests
    (tmp_path / "test_service.py").write_text(
        "from pkg.service import OrderService\n\n"
        "def test_process_order():\n"
        "    s = OrderService()\n"
        "    assert s.process_order(1) == 1\n"
    )

    return tmp_path


def test_code_graph_ast_indexing(temp_codebase: Path):
    """Verify zero-token AST extraction maps classes, functions, calls, and imports."""
    engine = CodeGraphEngine(temp_codebase)
    file_count = engine.index_directory(temp_codebase)

    assert file_count >= 4
    assert len(engine.nodes) >= 4
    assert len(engine.edges) >= 3

    # Check key symbols were extracted
    labels = {n.label for n in engine.nodes.values()}
    assert "BaseHandler" in labels
    assert "OrderService" in labels
    assert "process_order" in labels
    assert "checkout_endpoint" in labels


def test_blast_radius_reverse_walk(temp_codebase: Path):
    """Verify reverse topological walk accurately computes downstream callers and impacted tests."""
    engine = CodeGraphEngine(temp_codebase)
    engine.index_directory(temp_codebase)

    # Modify process_order -> should affect OrderService, checkout_endpoint, and test_service.py
    blast = engine.compute_blast_radius("process_order", depth=2)

    assert blast["found"] is True
    assert blast["total_affected"] >= 1
    assert any("service.py" in f for f in blast["impacted_files"])


def test_truth_gatekeeper_test_selection(temp_codebase: Path):
    """Verify TruthGatekeeper accurately identifies impacted test suites from modified symbols."""
    # Run truth gatekeeper impact audit
    impact_res = truth_gatekeeper.verify_code_modification_impact(["process_order"], root_dir=temp_codebase)

    assert impact_res.passed is True
    assert impact_res.check_type == "blast_radius_impact"
    assert "process_order" in impact_res.evidence["seeds"]


def test_code_graph_query_and_node_inspection(temp_codebase: Path):
    """Verify query_graph, get_node, and get_neighbors tools."""
    engine = CodeGraphEngine(temp_codebase)
    engine.index_directory(temp_codebase)

    # Natural language query
    q_res = engine.query_graph("process order service", depth=2)
    assert "OrderService" in q_res or "process_order" in q_res

    # Inspect node
    node_info = engine.get_node("OrderService")
    assert node_info.get("type") == "class"
    assert "service.py" in node_info.get("source_file", "")

    # Inspect neighbors
    neighbors = engine.get_neighbors("OrderService")
    assert neighbors.get("node") == "OrderService"


def test_graphify_canonical_json_serialization(temp_codebase: Path, tmp_path: Path):
    """Verify canonical Graphify graph.json format import and export."""
    engine = CodeGraphEngine(temp_codebase)
    engine.index_directory(temp_codebase)

    json_export_path = tmp_path / "exported_graph.json"
    saved = engine.save_graphify_json(json_export_path)
    assert saved is True
    assert json_export_path.exists()

    # Inspect JSON structure
    raw_json = json.loads(json_export_path.read_text(encoding="utf-8"))
    assert "nodes" in raw_json
    assert "links" in raw_json
    assert raw_json["directed"] is False  # Graphify canonical convention

    # Reload into new engine
    new_engine = CodeGraphEngine(temp_codebase)
    loaded = new_engine.load_graphify_json(json_export_path)
    assert loaded is True
    assert len(new_engine.nodes) == len(engine.nodes)
    assert len(new_engine.edges) == len(engine.edges)


def test_tool_registry_execution():
    """Verify registered tools execute properly through SpaceV execute_tool_normalized."""
    # Ensure current repo is indexed
    code_graph_engine.index_directory(Path(__file__).resolve().parent.parent / "core")

    res_node = execute_tool_normalized("get_code_node", {"label": "TruthGatekeeper"})
    assert res_node.success is True
    data = json.loads(res_node.data)
    assert data.get("type") == "class"

    res_blast = execute_tool_normalized("get_code_blast_radius", {"symbol_or_path": "TruthGatekeeper", "depth": 2})
    assert res_blast.success is True
    blast_data = json.loads(res_blast.data)
    assert blast_data.get("found") is True


def test_scoped_tools_includes_code_graph_on_keywords():
    """Verify get_scoped_tools routes CODE_TOOL_NAMES when code intelligence keywords match."""
    scoped = get_scoped_tools("find the blast radius and impacted callers of TruthGatekeeper")
    scoped_names = {t["function"]["name"] for t in scoped}

    assert "get_code_blast_radius" in scoped_names
    assert "query_code_graph" in scoped_names
