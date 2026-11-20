"""
Unit tests for core/knowledge_graph.py: Polyglot 4D Neuro-Symbolic Knowledge Graph.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from core.knowledge_graph import PolyglotKnowledgeGraph, KnowledgeNode, KnowledgeEdge
from core.protocol_hub import UniversalProtocolHub
import pytest


def test_polyglot_ast_indexing(tmp_path: Path):
    # 1. Setup multi-language files
    # Python file
    py_file = tmp_path / "service.py"
    py_file.write_text(
        "import math\n\n"
        "class UserService:\n"
        "    def authenticate(self, user: str):\n"
        "        return calculate_hash(user)\n\n"
        "def calculate_hash(val: str):\n"
        "    return val\n",
        encoding="utf-8"
    )

    # TypeScript file
    ts_file = tmp_path / "client.ts"
    ts_file.write_text(
        "import { Config } from './config';\n\n"
        "export interface UserProfile {\n"
        "    id: string;\n"
        "}\n\n"
        "export class ApiClient {\n"
        "    async fetchUser(id: string) {}\n"
        "}\n\n"
        "export const initializeApp = () => {};\n",
        encoding="utf-8"
    )

    # Rust file
    rs_file = tmp_path / "engine.rs"
    rs_file.write_text(
        "use crate::config::Settings;\n\n"
        "pub trait Runner {\n"
        "    fn run(&self);\n"
        "}\n\n"
        "pub struct EngineCore {\n"
        "    workers: usize,\n"
        "}\n\n"
        "pub fn start_engine() {}\n",
        encoding="utf-8"
    )

    # Go file
    go_file = tmp_path / "handler.go"
    go_file.write_text(
        "package api\n\n"
        "import \"net/http\"\n\n"
        "type RequestHandler struct {}\n\n"
        "func ServeHTTP(w http.ResponseWriter, r *http.Request) {}\n",
        encoding="utf-8"
    )

    kg = PolyglotKnowledgeGraph(root_dir=tmp_path)
    counts = kg.index_workspace(tmp_path, include_temporal=False)

    assert counts["python"] == 1
    assert counts["javascript/typescript"] == 1
    assert counts["rust"] == 1
    assert counts["go"] == 1

    # Verify entities exist
    assert kg.resolve_seed("UserService") is not None
    assert kg.resolve_seed("calculate_hash") is not None
    assert kg.resolve_seed("ApiClient") is not None
    assert kg.resolve_seed("UserProfile") is not None
    assert kg.resolve_seed("EngineCore") is not None
    assert kg.resolve_seed("start_engine") is not None
    assert kg.resolve_seed("RequestHandler") is not None
    assert kg.resolve_seed("ServeHTTP") is not None


def test_blast_radius_reverse_walk(tmp_path: Path):
    src_file = tmp_path / "models.py"
    src_file.write_text(
        "class BaseModel:\n"
        "    pass\n\n"
        "class User(BaseModel):\n"
        "    pass\n",
        encoding="utf-8"
    )

    test_file = tmp_path / "test_models.py"
    test_file.write_text(
        "from models import User\n\n"
        "def test_user_creation():\n"
        "    u = User()\n",
        encoding="utf-8"
    )

    kg = PolyglotKnowledgeGraph(root_dir=tmp_path)
    kg.index_workspace(tmp_path, include_temporal=False)

    # Blast radius for User
    res = kg.compute_blast_radius("User", depth=3)
    assert res["found"] is True
    assert "test_models.py" in res["impacted_files"]
    assert "test_models.py" in res["impacted_tests"]


def test_4d_temporal_git_co_changes(tmp_path: Path):
    # Initialize a temporary git repo to test git commit log mining
    subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.email", "spacev@test.org"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.name", "SpaceV Tester"], cwd=str(tmp_path), check=True)

    f1 = tmp_path / "auth.py"
    f2 = tmp_path / "session.py"

    # Commit 1
    f1.write_text("def auth(): pass\n")
    f2.write_text("def session(): pass\n")
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "commit", "-m", "feat: initial auth and session"], cwd=str(tmp_path), check=True)

    # Commit 2 (both modified together again)
    f1.write_text("def auth(): return 1\n")
    f2.write_text("def session(): return 1\n")
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "commit", "-m", "fix: synchronize token logic"], cwd=str(tmp_path), check=True)

    kg = PolyglotKnowledgeGraph(root_dir=tmp_path)
    counts = kg.index_workspace(tmp_path, include_temporal=True)

    assert counts.get("temporal_co_changes", 0) > 0

    # Blast radius on auth.py should pull in session.py via temporal linkage
    blast = kg.compute_blast_radius("auth.py", depth=2, include_temporal=True)
    assert "session.py" in blast["impacted_files"]


@pytest.mark.asyncio
async def test_fastmcp_knowledge_graph_integration(tmp_path: Path):
    py_file = tmp_path / "calc.py"
    py_file.write_text(
        "def add(a, b):\n    return a + b\n\n"
        "def calculate_total(items):\n    return add(items[0], items[1])\n",
        encoding="utf-8"
    )

    kg = PolyglotKnowledgeGraph(root_dir=tmp_path)
    kg.index_workspace(tmp_path, include_temporal=False)

    hub = UniversalProtocolHub()

    def query_knowledge_graph(question: str) -> str:
        """Queries AST code knowledge graph"""
        return kg.query_graph(question)

    def get_blast_radius(seed: str) -> dict:
        """Computes symbol blast radius"""
        return kg.compute_blast_radius(seed)

    hub.register_tool(query_knowledge_graph)
    hub.register_tool(get_blast_radius)

    # Verify MCP schemas generated dynamically
    tools = hub.list_mcp_tools()
    tool_names = [t["name"] for t in tools]
    assert "query_knowledge_graph" in tool_names
    assert "get_blast_radius" in tool_names

    # Invoke tool via hub
    res_query = await hub.invoke_tool("query_knowledge_graph", question="calculate_total")
    assert "calculate_total" in res_query

    res_blast = await hub.invoke_tool("get_blast_radius", seed="add")
    assert res_blast["found"] is True
    assert "calc.py" in res_blast["impacted_files"]
