"""
SpaceV Code Graph Engine & AST Intelligence Adapter.
Adapted from Graphify (v0.9.95) for deterministic, zero-token repository comprehension,
AST structural extraction, reverse-walk blast radius analysis, and MCP query tools.

Operates with 100% Python standard library (ast, json, pathlib, collections).
Optionally reads Graphify's full graph.json format if generated.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("SpaceV.CodeGraphEngine")

# Standard Graphify reverse-walk relations for blast-radius calculation
DEFAULT_AFFECTED_RELATIONS = frozenset({
    "calls",
    "indirect_call",
    "references",
    "imports",
    "imports_from",
    "dynamic_import",
    "re_exports",
    "inherits",
    "extends",
    "implements",
    "uses",
    "mixes_in",
    "embeds",
    "defines",
    "requires",
})

_SUPERTYPE_RELATIONS = frozenset({"inherits", "extends", "implements"})


@dataclass
class CodeNode:
    id: str
    label: str
    source_file: str
    source_location: str = "L1"
    node_type: str = "symbol"  # 'function', 'class', 'module', 'file', 'symbol'
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class CodeEdge:
    source: str
    target: str
    relation: str  # 'calls', 'imports', 'defines', 'inherits', 'references'
    confidence: str = "EXTRACTED"  # 'EXTRACTED', 'INFERRED', 'AMBIGUOUS'
    properties: dict[str, Any] = field(default_factory=dict)


class CodeGraphEngine:
    """
    Deterministic AST Knowledge Graph Engine for SpaceV.
    Builds, indexes, traverses, and queries code structural relationships.
    """

    def __init__(self, root_dir: Path | str | None = None):
        self.root_dir = Path(root_dir).resolve() if root_dir else Path.cwd().resolve()
        self.nodes: dict[str, CodeNode] = {}
        self.edges: list[CodeEdge] = []
        self.adj_out: dict[str, list[CodeEdge]] = {}
        self.adj_in: dict[str, list[CodeEdge]] = {}
        self._symbol_to_id: dict[str, str] = {}
        self._file_to_id: dict[str, str] = {}

    def clear(self) -> None:
        self.nodes.clear()
        self.edges.clear()
        self.adj_out.clear()
        self.adj_in.clear()
        self._symbol_to_id.clear()
        self._file_to_id.clear()

    def add_node(self, node: CodeNode) -> None:
        self.nodes[node.id] = node
        self.adj_out.setdefault(node.id, [])
        self.adj_in.setdefault(node.id, [])
        self._symbol_to_id[node.label] = node.id
        self._symbol_to_id[node.label.lower()] = node.id
        if node.node_type == "file":
            self._file_to_id[node.source_file] = node.id

    def add_edge(self, edge: CodeEdge) -> None:
        self.edges.append(edge)
        self.adj_out.setdefault(edge.source, []).append(edge)
        self.adj_in.setdefault(edge.target, []).append(edge)

    def load_graphify_json(self, json_path: Path | str) -> bool:
        """Loads a pre-generated Graphify graph.json file."""
        p = Path(json_path)
        if not p.is_file():
            return False
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            self.clear()
            raw_nodes = data.get("nodes", [])
            for n in raw_nodes:
                node = CodeNode(
                    id=str(n.get("id", "")),
                    label=str(n.get("label", n.get("id", ""))),
                    source_file=str(n.get("source_file", "")),
                    source_location=str(n.get("source_location", "L1")),
                    node_type=str(n.get("type", n.get("node_type", "symbol"))),
                    properties=n,
                )
                self.add_node(node)

            raw_edges = data.get("links", data.get("edges", []))
            for e in raw_edges:
                edge = CodeEdge(
                    source=str(e.get("source", "")),
                    target=str(e.get("target", "")),
                    relation=str(e.get("relation", "references")),
                    confidence=str(e.get("confidence", "EXTRACTED")),
                    properties=e,
                )
                self.add_edge(edge)
            return True
        except Exception as e:
            logger.warning("Failed to load Graphify JSON %s: %s", json_path, e)
            return False

    def save_graphify_json(self, json_path: Path | str) -> bool:
        """Serializes current graph to Graphify canonical graph.json format."""
        try:
            p = Path(json_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "directed": False,  # Canonical Graphify convention (arc order is direction)
                "multigraph": False,
                "nodes": [
                    {
                        "id": n.id,
                        "label": n.label,
                        "source_file": n.source_file,
                        "source_location": n.source_location,
                        "type": n.node_type,
                    }
                    for n in self.nodes.values()
                ],
                "links": [
                    {
                        "source": e.source,
                        "target": e.target,
                        "relation": e.relation,
                        "confidence": e.confidence,
                    }
                    for e in self.edges
                ],
            }
            p.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return True
        except Exception as e:
            logger.error("Failed to save Graphify JSON %s: %s", json_path, e)
            return False

    def index_directory(self, target_dir: Path | str | None = None, max_files: int = 500) -> int:
        """
        Parses all Python source files in the target directory using pure AST.
        Extracts modules, classes, functions, calls, imports, and inheritance.
        Zero token usage, runs in milliseconds.
        """
        scan_dir = Path(target_dir).resolve() if target_dir else self.root_dir
        self.clear()
        indexed_count = 0

        # Pass 1: Local AST extraction per file
        for root, dirs, files in os.walk(scan_dir):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("venv", ".venv", "__pycache__", "site-packages", "node_modules")]
            for f in files:
                if f.endswith(".py") and not f.startswith("."):
                    file_path = Path(root) / f
                    rel_path = str(file_path.relative_to(scan_dir))
                    self._extract_python_file(file_path, rel_path)
                    indexed_count += 1
                    if indexed_count >= max_files:
                        break
            if indexed_count >= max_files:
                break

        # Pass 2: Cross-File Call & Import Binding
        self._resolve_cross_file_calls()
        return indexed_count

    def _extract_python_file(self, file_path: Path, rel_path: str) -> None:
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content, filename=str(file_path))
        except Exception:
            return

        file_node_id = f"file::{rel_path}"
        self.add_node(CodeNode(
            id=file_node_id,
            label=rel_path,
            source_file=rel_path,
            source_location="L1",
            node_type="file"
        ))

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                self._extract_class(node, file_node_id, rel_path)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._extract_function(node, file_node_id, rel_path)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    mod_name = alias.name
                    target_id = f"mod::{mod_name}"
                    self.add_node(CodeNode(id=target_id, label=mod_name, source_file=mod_name, node_type="module"))
                    self.add_edge(CodeEdge(source=file_node_id, target=target_id, relation="imports", confidence="EXTRACTED"))
            elif isinstance(node, ast.ImportFrom):
                mod_name = node.module or ""
                for alias in node.names:
                    sym_name = f"{mod_name}.{alias.name}" if mod_name else alias.name
                    target_id = f"sym::{sym_name}"
                    self.add_node(CodeNode(id=target_id, label=alias.name, source_file=mod_name, node_type="symbol"))
                    self.add_edge(CodeEdge(source=file_node_id, target=target_id, relation="imports_from", confidence="EXTRACTED"))

    def _extract_class(self, node: ast.ClassDef, parent_id: str, rel_path: str) -> None:
        class_id = f"class::{rel_path}::{node.name}"
        self.add_node(CodeNode(
            id=class_id,
            label=node.name,
            source_file=rel_path,
            source_location=f"L{node.lineno}",
            node_type="class"
        ))
        self.add_edge(CodeEdge(source=parent_id, target=class_id, relation="defines", confidence="EXTRACTED"))

        # Inheritance
        for base in node.bases:
            base_name = getattr(base, "id", None) or getattr(base, "attr", None)
            if base_name:
                target_id = f"sym::{base_name}"
                self.add_node(CodeNode(id=target_id, label=str(base_name), source_file=rel_path, node_type="class"))
                self.add_edge(CodeEdge(source=class_id, target=target_id, relation="inherits", confidence="EXTRACTED"))

        # Methods
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._extract_function(item, class_id, rel_path)

    def _extract_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, parent_id: str, rel_path: str) -> None:
        func_id = f"func::{rel_path}::{node.name}"
        self.add_node(CodeNode(
            id=func_id,
            label=node.name,
            source_file=rel_path,
            source_location=f"L{node.lineno}",
            node_type="function"
        ))
        self.add_edge(CodeEdge(source=parent_id, target=func_id, relation="defines", confidence="EXTRACTED"))

        # Calls inside function
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                call_name = ""
                if isinstance(sub.func, ast.Name):
                    call_name = sub.func.id
                elif isinstance(sub.func, ast.Attribute):
                    call_name = sub.func.attr
                if call_name:
                    target_id = f"sym::{call_name}"
                    self.add_node(CodeNode(id=target_id, label=call_name, source_file=rel_path, node_type="symbol"))
                    self.add_edge(CodeEdge(source=func_id, target=target_id, relation="calls", confidence="INFERRED"))

    def _resolve_cross_file_calls(self) -> None:
        """Binds inferred calls, module imports, and symbol imports to concrete function/class/file nodes."""
        defined_symbols: dict[str, str] = {}
        for nid, node in self.nodes.items():
            if node.node_type in ("function", "class") and not nid.startswith("sym::"):
                defined_symbols[node.label] = nid

        for edge in list(self.edges):
            # 1. Resolve sym:: targets (imports_from, calls, inherits)
            if edge.target.startswith("sym::"):
                symbol_label = self.nodes.get(edge.target, CodeNode("", "", "")).label
                if symbol_label in defined_symbols and defined_symbols[symbol_label] != edge.source:
                    resolved_target = defined_symbols[symbol_label]
                    rel = "imports" if edge.relation == "imports_from" else edge.relation
                    conf = "EXTRACTED" if edge.relation == "imports_from" else "INFERRED"
                    self.add_edge(CodeEdge(
                        source=edge.source,
                        target=resolved_target,
                        relation=rel,
                        confidence=conf
                    ))

            # 2. Resolve mod:: imports to file nodes
            elif edge.target.startswith("mod::") and edge.relation == "imports":
                mod_name = self.nodes.get(edge.target, CodeNode("", "", "")).label
                candidate_rel = mod_name.replace(".", "/") + ".py"
                candidate_id = f"file::{candidate_rel}"
                if candidate_id in self.nodes and candidate_id != edge.source:
                    self.add_edge(CodeEdge(
                        source=edge.source,
                        target=candidate_id,
                        relation="imports",
                        confidence="EXTRACTED"
                    ))

    def resolve_seed(self, seed: str) -> str | None:
        """Resolves a human query/label/path to a concrete node_id."""
        if seed in self.nodes:
            return seed
        if seed in self._symbol_to_id:
            return self._symbol_to_id[seed]
        seed_lower = seed.lower()
        if seed_lower in self._symbol_to_id:
            return self._symbol_to_id[seed_lower]
        # Match stripped 'func()' -> 'func'
        if seed.endswith("()"):
            bare = seed[:-2].lower()
            if bare in self._symbol_to_id:
                return self._symbol_to_id[bare]
        # Match filename
        if seed in self._file_to_id:
            return self._file_to_id[seed]
        for fpath, fid in self._file_to_id.items():
            if seed in fpath or fpath.endswith(seed):
                return fid
        return None

    def compute_blast_radius(
        self,
        seed: str,
        depth: int = 2,
        relations: frozenset[str] = DEFAULT_AFFECTED_RELATIONS
    ) -> dict[str, Any]:
        """
        Reverse topological walk tracing incoming dependency paths.
        Computes downstream impacted functions, classes, files, and test suites.
        """
        seed_id = self.resolve_seed(seed)
        if not seed_id:
            return {
                "seed": seed,
                "found": False,
                "error": f"Seed symbol or file '{seed}' not found in code graph.",
                "impacted_symbols": [],
                "impacted_files": [],
                "impacted_tests": [],
                "total_affected": 0,
            }

        visited: set[str] = {seed_id}
        queue: deque[tuple[str, int]] = deque([(seed_id, 0)])
        hits: list[dict[str, Any]] = []

        while queue:
            curr_id, curr_depth = queue.popleft()
            if curr_depth >= depth:
                continue

            for edge in self.adj_in.get(curr_id, []):
                if edge.relation in relations:
                    src_id = edge.source
                    if src_id not in visited:
                        visited.add(src_id)
                        queue.append((src_id, curr_depth + 1))
                        src_node = self.nodes.get(src_id)
                        if src_node:
                            hits.append({
                                "node_id": src_id,
                                "label": src_node.label,
                                "type": src_node.node_type,
                                "source_file": src_node.source_file,
                                "source_location": src_node.source_location,
                                "depth": curr_depth + 1,
                                "via_relation": edge.relation,
                            })

        # Categorize
        impacted_symbols = [h["label"] for h in hits if h["type"] in ("function", "class", "symbol")]
        impacted_files = sorted({h["source_file"] for h in hits if h["source_file"]})
        impacted_tests = sorted({f for f in impacted_files if "test" in f.lower()})

        return {
            "seed": seed,
            "seed_id": seed_id,
            "found": True,
            "depth": depth,
            "total_affected": len(hits),
            "impacted_symbols": impacted_symbols,
            "impacted_files": impacted_files,
            "impacted_tests": impacted_tests,
            "hits": hits,
        }

    def query_graph(self, question: str, depth: int = 2, token_budget: int = 2000) -> str:
        """
        Graphify MCP query_graph tool equivalent.
        Matches question terms, extracts bounded BFS subgraph, and formats dense ASCII summary.
        """
        q_tokens = [w.lower() for w in re.findall(r"\w+", question) if len(w) > 2]
        scored_seeds: list[tuple[int, str]] = []

        for nid, node in self.nodes.items():
            score = 0
            label_lower = node.label.lower()
            file_lower = node.source_file.lower()
            for t in q_tokens:
                if t == label_lower:
                    score += 10
                elif t in label_lower:
                    score += 4
                if t in file_lower:
                    score += 2
            if score > 0:
                scored_seeds.append((score, nid))

        scored_seeds.sort(reverse=True, key=lambda x: x[0])
        seeds = [nid for _, nid in scored_seeds[:3]]
        if not seeds:
            return f"No code graph symbols matched question: '{question}'."

        # Bounded BFS
        visited: set[str] = set(seeds)
        edges_collected: list[CodeEdge] = []
        queue = deque([(s, 0) for s in seeds])

        while queue:
            curr, d = queue.popleft()
            if d >= depth:
                continue
            for e in self.adj_out.get(curr, []):
                edges_collected.append(e)
                if e.target not in visited and e.target in self.nodes:
                    visited.add(e.target)
                    queue.append((e.target, d + 1))

        # Format dense text representation
        lines = [f"=== Code Graph Result for: '{question}' ==="]
        lines.append(f"Seeds matched: {', '.join(self.nodes[s].label for s in seeds)}")
        lines.append("\nNodes:")
        for nid in sorted(visited):
            n = self.nodes.get(nid)
            if n:
                lines.append(f"  [{n.node_type.upper()}] {n.label} ({n.source_file}:{n.source_location})")

        lines.append("\nRelationships:")
        for e in edges_collected:
            src_lbl = self.nodes.get(e.source, CodeNode(e.source, e.source, "")).label
            tgt_lbl = self.nodes.get(e.target, CodeNode(e.target, e.target, "")).label
            lines.append(f"  {src_lbl} --({e.relation})--> {tgt_lbl}")

        output = "\n".join(lines)
        if len(output) > token_budget * 4:
            output = output[:token_budget * 4] + "\n... [truncated to token budget]"
        return output

    def get_node(self, label_or_id: str) -> dict[str, Any]:
        """Inspects exact details of a node."""
        nid = self.resolve_seed(label_or_id)
        if not nid or nid not in self.nodes:
            return {"error": f"Node '{label_or_id}' not found"}
        node = self.nodes[nid]
        in_deg = len(self.adj_in.get(nid, []))
        out_deg = len(self.adj_out.get(nid, []))
        return {
            "id": node.id,
            "label": node.label,
            "type": node.node_type,
            "source_file": node.source_file,
            "source_location": node.source_location,
            "in_degree": in_deg,
            "out_degree": out_deg,
        }

    def get_neighbors(self, label_or_id: str, direction: str = "both") -> dict[str, Any]:
        """Inspects incoming and outgoing structural relationships."""
        nid = self.resolve_seed(label_or_id)
        if not nid or nid not in self.nodes:
            return {"error": f"Node '{label_or_id}' not found"}

        incoming = []
        if direction in ("in", "both"):
            for e in self.adj_in.get(nid, []):
                src_node = self.nodes.get(e.source)
                incoming.append({
                    "source": src_node.label if src_node else e.source,
                    "relation": e.relation,
                    "confidence": e.confidence,
                })

        outgoing = []
        if direction in ("out", "both"):
            for e in self.adj_out.get(nid, []):
                tgt_node = self.nodes.get(e.target)
                outgoing.append({
                    "target": tgt_node.label if tgt_node else e.target,
                    "relation": e.relation,
                    "confidence": e.confidence,
                })

        return {
            "node": self.nodes[nid].label,
            "incoming": incoming,
            "outgoing": outgoing,
        }

    def get_god_nodes(self, top_n: int = 10) -> list[dict[str, Any]]:
        """Identifies architectural bottlenecks (highest total connectivity)."""
        scored = []
        for nid, node in self.nodes.items():
            if node.node_type == "file":
                continue
            deg = len(self.adj_in.get(nid, [])) + len(self.adj_out.get(nid, []))
            scored.append((deg, node))
        scored.sort(reverse=True, key=lambda x: x[0])
        return [
            {
                "label": n.label,
                "type": n.node_type,
                "source_file": n.source_file,
                "connectivity": deg,
            }
            for deg, n in scored[:top_n]
        ]


# Singleton engine instance anchored to SpaceV workspace root
code_graph_engine = CodeGraphEngine(Path(__file__).resolve().parent.parent)
