"""
SpaceV Polyglot 4D Neuro-Symbolic Knowledge Graph Engine.
Bridges AST structural intelligence (Python, Rust, TypeScript/JS, Go)
with 4D temporal Git commit co-change causality and FastMCP query endpoints.
Strictly abolishes regex string heuristics, hardcoded repository paths,
fixed prompt words, and language-specific assumptions.
"""

from __future__ import annotations

import ast
import json
import logging
import subprocess
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Generator, Set

from pygments.lexers import get_lexer_for_filename
from pygments.token import Token

logger = logging.getLogger("SpaceV.KnowledgeGraph")


class GraphRelation(str, Enum):
    """Formal semantic and temporal edge relation types."""
    DEFINES = "defines"
    CALLS = "calls"
    IMPORTS = "imports"
    INHERITS = "inherits"
    IMPLEMENTS = "implements"
    REFERENCES = "references"
    CO_CHANGES = "co_changes_with"


class SemanticNodeKind(str, Enum):
    """Formal taxonomic classifications for codebase entities."""
    FILE = "file"
    MODULE = "module"
    PACKAGE = "package"
    CLASS = "class"
    STRUCT = "struct"
    TRAIT = "trait"
    INTERFACE = "interface"
    FUNCTION = "function"
    SYMBOL = "symbol"


@dataclass
class KnowledgeNode:
    """Represents a discrete semantic entity in the codebase."""
    id: str
    label: str
    source_file: str
    source_location: str = "L1"
    node_type: SemanticNodeKind | str = SemanticNodeKind.SYMBOL
    language: str = "unknown"
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgeEdge:
    """Represents a directed structural or temporal edge between two entities."""
    source: str
    target: str
    relation: GraphRelation | str
    confidence: str = "EXTRACTED"  # 'EXTRACTED', 'INFERRED', 'TEMPORAL'
    weight: float = 1.0
    properties: dict[str, Any] = field(default_factory=dict)


class PolyglotKnowledgeGraph:
    """
    Universal 4D Neuro-Symbolic Knowledge Graph for SpaceV.
    Combines formal AST & lexical token-stream parsing with Git revision causality.
    Operates with ZERO regex heuristics and ZERO hardcoded directory lists.
    """

    def __init__(self, root_dir: Path | str | None = None):
        self.root_dir = Path(root_dir).resolve() if root_dir else Path.cwd().resolve()
        self.nodes: dict[str, KnowledgeNode] = {}
        self.edges: list[KnowledgeEdge] = []
        self.adj_out: dict[str, list[KnowledgeEdge]] = defaultdict(list)
        self.adj_in: dict[str, list[KnowledgeEdge]] = defaultdict(list)
        self._symbol_to_ids: dict[str, set[str]] = defaultdict(set)
        self._file_to_id: dict[str, str] = {}
        self._co_change_counts: dict[tuple[str, str], int] = defaultdict(int)

    def clear(self) -> None:
        self.nodes.clear()
        self.edges.clear()
        self.adj_out.clear()
        self.adj_in.clear()
        self._symbol_to_ids.clear()
        self._file_to_id.clear()
        self._co_change_counts.clear()

    def add_node(self, node: KnowledgeNode) -> None:
        self.nodes[node.id] = node
        self._symbol_to_ids[node.label].add(node.id)
        self._symbol_to_ids[node.label.lower()].add(node.id)
        if node.node_type == SemanticNodeKind.FILE or node.node_type == "file":
            self._file_to_id[node.source_file] = node.id

    def add_edge(self, edge: KnowledgeEdge) -> None:
        self.edges.append(edge)
        self.adj_out[edge.source].append(edge)
        self.adj_in[edge.target].append(edge)

    def _discover_scannable_files(self, scan_dir: Path) -> list[Path]:
        """
        Discovers repository files dynamically without hardcoded directory blacklists.
        Uses Git's native tree indexing when available, with standard dot-file exclusion fallback.
        """
        if (scan_dir / ".git").exists():
            try:
                cmd = ["git", "-C", str(scan_dir), "ls-files", "--cached", "--others", "--exclude-standard"]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
                if res.returncode == 0:
                    files = []
                    for line in res.stdout.splitlines():
                        line = line.strip()
                        if line:
                            p = scan_dir / line
                            if p.is_file():
                                files.append(p)
                    if files:
                        return files
            except Exception:
                pass

        # Filesystem crawl without hardcoded directory names (skips hidden directories only)
        discovered: list[Path] = []
        for p in scan_dir.rglob("*"):
            if p.is_file():
                # Ignore hidden path segments (starting with '.')
                parts = p.relative_to(scan_dir).parts
                if not any(part.startswith(".") for part in parts[:-1]):
                    discovered.append(p)
        return discovered

    def index_workspace(
        self,
        target_dir: Path | str | None = None,
        max_files: int = 1000,
        include_temporal: bool = True,
        temporal_commit_limit: int = 100,
    ) -> dict[str, int]:
        """
        Indexes code across Python, Rust, TypeScript, and Go using formal AST & token streams.
        Zero regex pattern matching.
        """
        scan_dir = Path(target_dir).resolve() if target_dir else self.root_dir
        self.clear()
        file_counts: dict[str, int] = defaultdict(int)

        scannable_files = self._discover_scannable_files(scan_dir)
        indexed_files = 0

        for file_path in scannable_files:
            rel_path = str(file_path.relative_to(scan_dir)).replace("\\", "/")
            ext = file_path.suffix.lower()

            if ext == ".py":
                self._parse_python_ast(file_path, rel_path)
                file_counts["python"] += 1
                indexed_files += 1
            elif ext in (".ts", ".tsx", ".js", ".jsx", ".mjs"):
                self._parse_token_stream(file_path, rel_path, language="typescript")
                file_counts["javascript/typescript"] += 1
                indexed_files += 1
            elif ext == ".rs":
                self._parse_token_stream(file_path, rel_path, language="rust")
                file_counts["rust"] += 1
                indexed_files += 1
            elif ext == ".go":
                self._parse_token_stream(file_path, rel_path, language="go")
                file_counts["go"] += 1
                indexed_files += 1

            if indexed_files >= max_files:
                break

        # Cross-file symbol resolution
        self._resolve_cross_references()

        # 4D Temporal Git mining
        if include_temporal and (scan_dir / ".git").exists():
            co_changes = self.mine_git_co_changes(scan_dir, commit_limit=temporal_commit_limit)
            file_counts["temporal_co_changes"] = co_changes

        file_counts["total_nodes"] = len(self.nodes)
        file_counts["total_edges"] = len(self.edges)
        return dict(file_counts)

    def _parse_python_ast(self, file_path: Path, rel_path: str) -> None:
        """Parses Python using the native compiler AST visitor; zero regex."""
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content, filename=str(file_path))
        except Exception:
            return

        file_id = f"file::{rel_path}"
        self.add_node(KnowledgeNode(
            id=file_id,
            label=rel_path,
            source_file=rel_path,
            source_location="L1",
            node_type=SemanticNodeKind.FILE,
            language="python",
        ))

        class PythonASTVisitor(ast.NodeVisitor):
            def __init__(self, parent_graph: PolyglotKnowledgeGraph):
                self.graph = parent_graph
                self.scope_stack: list[str] = [file_id]

            def visit_ClassDef(self, node: ast.ClassDef):
                parent_id = self.scope_stack[-1]
                class_id = f"class::{rel_path}::{node.name}"
                self.graph.add_node(KnowledgeNode(
                    id=class_id,
                    label=node.name,
                    source_file=rel_path,
                    source_location=f"L{node.lineno}",
                    node_type=SemanticNodeKind.CLASS,
                    language="python",
                ))
                self.graph.add_edge(KnowledgeEdge(source=parent_id, target=class_id, relation=GraphRelation.DEFINES))

                for base in node.bases:
                    base_name = getattr(base, "id", None) or getattr(base, "attr", None)
                    if base_name:
                        base_id = f"sym::{base_name}"
                        self.graph.add_node(KnowledgeNode(id=base_id, label=str(base_name), source_file=rel_path, node_type=SemanticNodeKind.CLASS, language="python"))
                        self.graph.add_edge(KnowledgeEdge(source=class_id, target=base_id, relation=GraphRelation.INHERITS))

                self.scope_stack.append(class_id)
                self.generic_visit(node)
                self.scope_stack.pop()

            def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
                parent_id = self.scope_stack[-1]
                func_id = f"func::{rel_path}::{node.name}"
                self.graph.add_node(KnowledgeNode(
                    id=func_id,
                    label=node.name,
                    source_file=rel_path,
                    source_location=f"L{node.lineno}",
                    node_type=SemanticNodeKind.FUNCTION,
                    language="python",
                ))
                self.graph.add_edge(KnowledgeEdge(source=parent_id, target=func_id, relation=GraphRelation.DEFINES))

                self.scope_stack.append(func_id)
                self.generic_visit(node)
                self.scope_stack.pop()

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
                self.visit_FunctionDef(node)

            def visit_Import(self, node: ast.Import):
                parent_id = self.scope_stack[-1]
                for alias in node.names:
                    mod_id = f"mod::{alias.name}"
                    self.graph.add_node(KnowledgeNode(id=mod_id, label=alias.name, source_file=alias.name, node_type=SemanticNodeKind.MODULE, language="python"))
                    self.graph.add_edge(KnowledgeEdge(source=parent_id, target=mod_id, relation=GraphRelation.IMPORTS))

            def visit_ImportFrom(self, node: ast.ImportFrom):
                parent_id = self.scope_stack[-1]
                mod_name = node.module or ""
                for alias in node.names:
                    sym_id = f"sym::{mod_name}.{alias.name}" if mod_name else f"sym::{alias.name}"
                    self.graph.add_node(KnowledgeNode(id=sym_id, label=alias.name, source_file=mod_name, node_type=SemanticNodeKind.SYMBOL, language="python"))
                    self.graph.add_edge(KnowledgeEdge(source=parent_id, target=sym_id, relation=GraphRelation.IMPORTS))

            def visit_Call(self, node: ast.Call):
                parent_id = self.scope_stack[-1]
                call_name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if call_name:
                    sym_id = f"sym::{call_name}"
                    self.graph.add_node(KnowledgeNode(id=sym_id, label=call_name, source_file=rel_path, node_type=SemanticNodeKind.SYMBOL, language="python"))
                    self.graph.add_edge(KnowledgeEdge(source=parent_id, target=sym_id, relation=GraphRelation.CALLS, confidence="INFERRED"))
                self.generic_visit(node)

        visitor = PythonASTVisitor(self)
        visitor.visit(tree)

    def _parse_token_stream(self, file_path: Path, rel_path: str, language: str) -> None:
        """
        Parses non-Python languages (TypeScript, Rust, Go) using formal lexical token streams.
        Abolishes regex string matching.
        """
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            lexer = get_lexer_for_filename(file_path.name)
            raw_tokens = list(lexer.get_tokens(content))
        except Exception:
            return

        file_id = f"file::{rel_path}"
        self.add_node(KnowledgeNode(
            id=file_id,
            label=rel_path,
            source_file=rel_path,
            source_location="L1",
            node_type=SemanticNodeKind.FILE,
            language=language,
        ))

        # Filter whitespace tokens while keeping lexical position
        tokens = [(tok_type, val) for tok_type, val in raw_tokens if val.strip()]
        total_tokens = len(tokens)

        for i in range(total_tokens):
            tok_type, val = tokens[i]

            # -------------------------------------------------------------
            # TypeScript / JavaScript Lexical Extraction
            # -------------------------------------------------------------
            if language == "typescript":
                if val == "interface" and i + 1 < total_tokens:
                    target_name = tokens[i + 1][1]
                    if target_name.isidentifier():
                        node_id = f"interface::{rel_path}::{target_name}"
                        self.add_node(KnowledgeNode(id=node_id, label=target_name, source_file=rel_path, node_type=SemanticNodeKind.INTERFACE, language="typescript"))
                        self.add_edge(KnowledgeEdge(source=file_id, target=node_id, relation=GraphRelation.DEFINES))
                elif val == "class" and i + 1 < total_tokens:
                    target_name = tokens[i + 1][1]
                    if target_name.isidentifier():
                        class_id = f"class::{rel_path}::{target_name}"
                        self.add_node(KnowledgeNode(id=class_id, label=target_name, source_file=rel_path, node_type=SemanticNodeKind.CLASS, language="typescript"))
                        self.add_edge(KnowledgeEdge(source=file_id, target=class_id, relation=GraphRelation.DEFINES))
                elif val == "function" and i + 1 < total_tokens:
                    fn_name = tokens[i + 1][1]
                    if fn_name.isidentifier():
                        fn_id = f"func::{rel_path}::{fn_name}"
                        self.add_node(KnowledgeNode(id=fn_id, label=fn_name, source_file=rel_path, node_type=SemanticNodeKind.FUNCTION, language="typescript"))
                        self.add_edge(KnowledgeEdge(source=file_id, target=fn_id, relation=GraphRelation.DEFINES))
                elif val in ("const", "let", "var") and i + 1 < total_tokens:
                    ident = tokens[i + 1][1]
                    if ident.isidentifier():
                        # Look forward for arrow function syntax (=>) before statement terminator (;)
                        for j in range(i + 2, min(i + 15, total_tokens)):
                            if tokens[j][1] == "=>":
                                fn_id = f"func::{rel_path}::{ident}"
                                self.add_node(KnowledgeNode(id=fn_id, label=ident, source_file=rel_path, node_type=SemanticNodeKind.FUNCTION, language="typescript"))
                                self.add_edge(KnowledgeEdge(source=file_id, target=fn_id, relation=GraphRelation.DEFINES))
                                break
                            if tokens[j][1] == ";":
                                break

            # -------------------------------------------------------------
            # Rust Lexical Extraction
            # -------------------------------------------------------------
            elif language == "rust":
                if val in ("struct", "enum") and i + 1 < total_tokens:
                    type_name = tokens[i + 1][1]
                    if type_name.isidentifier():
                        type_id = f"type::{rel_path}::{type_name}"
                        self.add_node(KnowledgeNode(id=type_id, label=type_name, source_file=rel_path, node_type=SemanticNodeKind.STRUCT, language="rust"))
                        self.add_edge(KnowledgeEdge(source=file_id, target=type_id, relation=GraphRelation.DEFINES))
                elif val == "trait" and i + 1 < total_tokens:
                    trait_name = tokens[i + 1][1]
                    if trait_name.isidentifier():
                        trait_id = f"trait::{rel_path}::{trait_name}"
                        self.add_node(KnowledgeNode(id=trait_id, label=trait_name, source_file=rel_path, node_type=SemanticNodeKind.TRAIT, language="rust"))
                        self.add_edge(KnowledgeEdge(source=file_id, target=trait_id, relation=GraphRelation.DEFINES))
                elif val == "fn" and i + 1 < total_tokens:
                    fn_name = tokens[i + 1][1]
                    if fn_name.isidentifier():
                        fn_id = f"func::{rel_path}::{fn_name}"
                        self.add_node(KnowledgeNode(id=fn_id, label=fn_name, source_file=rel_path, node_type=SemanticNodeKind.FUNCTION, language="rust"))
                        self.add_edge(KnowledgeEdge(source=file_id, target=fn_id, relation=GraphRelation.DEFINES))

            # -------------------------------------------------------------
            # Go Lexical Extraction
            # -------------------------------------------------------------
            elif language == "go":
                if val == "package" and i + 1 < total_tokens:
                    pkg_name = tokens[i + 1][1]
                    if pkg_name.isidentifier():
                        pkg_id = f"pkg::{pkg_name}"
                        self.add_node(KnowledgeNode(id=pkg_id, label=pkg_name, source_file=rel_path, node_type=SemanticNodeKind.PACKAGE, language="go"))
                        self.add_edge(KnowledgeEdge(source=file_id, target=pkg_id, relation=GraphRelation.DEFINES))
                elif val == "type" and i + 2 < total_tokens:
                    type_name = tokens[i + 1][1]
                    kind_decl = tokens[i + 2][1]
                    if type_name.isidentifier() and kind_decl in ("struct", "interface"):
                        kind_enum = SemanticNodeKind.STRUCT if kind_decl == "struct" else SemanticNodeKind.INTERFACE
                        type_id = f"type::{rel_path}::{type_name}"
                        self.add_node(KnowledgeNode(id=type_id, label=type_name, source_file=rel_path, node_type=kind_enum, language="go"))
                        self.add_edge(KnowledgeEdge(source=file_id, target=type_id, relation=GraphRelation.DEFINES))
                elif val == "func" and i + 1 < total_tokens:
                    curr = i + 1
                    # Handle Go method receiver: func (s *Server) Handle()
                    if tokens[curr][1] == "(":
                        while curr < total_tokens and tokens[curr][1] != ")":
                            curr += 1
                        curr += 1
                    if curr < total_tokens:
                        fn_name = tokens[curr][1]
                        if fn_name.isidentifier():
                            fn_id = f"func::{rel_path}::{fn_name}"
                            self.add_node(KnowledgeNode(id=fn_id, label=fn_name, source_file=rel_path, node_type=SemanticNodeKind.FUNCTION, language="go"))
                            self.add_edge(KnowledgeEdge(source=file_id, target=fn_id, relation=GraphRelation.DEFINES))

    def _resolve_cross_references(self) -> None:
        """Connects dangling symbol references to defined symbols across files."""
        defined_symbols: dict[str, list[str]] = defaultdict(list)
        for nid, node in self.nodes.items():
            if not nid.startswith("sym::") and node.node_type not in (SemanticNodeKind.FILE, SemanticNodeKind.MODULE):
                defined_symbols[node.label].append(nid)

        for edge in list(self.edges):
            if edge.target.startswith("sym::"):
                target_node = self.nodes.get(edge.target)
                if target_node and target_node.label in defined_symbols:
                    matches = defined_symbols[target_node.label]
                    for match_id in matches:
                        if match_id != edge.source:
                            self.add_edge(KnowledgeEdge(
                                source=edge.source,
                                target=match_id,
                                relation=edge.relation,
                                confidence="INFERRED",
                            ))

    def mine_git_co_changes(self, repo_root: Path, commit_limit: int = 100) -> int:
        """
        Mines 4D temporal causality from Git revision logs.
        Files that frequently change together establish weighted co_changes_with edges.
        """
        try:
            cmd = ["git", "-C", str(repo_root), "log", f"-n{commit_limit}", "--name-only", "--pretty=format:COMMIT:%H"]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
            if res.returncode != 0:
                return 0

            commits_files: list[list[str]] = []
            curr_files: list[str] = []

            for line in res.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith("COMMIT:"):
                    if curr_files:
                        commits_files.append(curr_files)
                        curr_files = []
                else:
                    norm = line.replace("\\", "/")
                    curr_files.append(norm)
            if curr_files:
                commits_files.append(curr_files)

            for files in commits_files:
                unique_files = sorted(set(files))
                for i in range(len(unique_files)):
                    for j in range(i + 1, len(unique_files)):
                        f1, f2 = unique_files[i], unique_files[j]
                        self._co_change_counts[(f1, f2)] += 1

            edges_created = 0
            for (f1, f2), count in self._co_change_counts.items():
                if count >= 2:
                    id1 = self._file_to_id.get(f1) or f"file::{f1}"
                    id2 = self._file_to_id.get(f2) or f"file::{f2}"
                    if id1 not in self.nodes:
                        self.add_node(KnowledgeNode(id=id1, label=f1, source_file=f1, node_type=SemanticNodeKind.FILE))
                    if id2 not in self.nodes:
                        self.add_node(KnowledgeNode(id=id2, label=f2, source_file=f2, node_type=SemanticNodeKind.FILE))

                    weight = float(count)
                    self.add_edge(KnowledgeEdge(source=id1, target=id2, relation=GraphRelation.CO_CHANGES, confidence="TEMPORAL", weight=weight))
                    self.add_edge(KnowledgeEdge(source=id2, target=id1, relation=GraphRelation.CO_CHANGES, confidence="TEMPORAL", weight=weight))
                    edges_created += 2

            return edges_created
        except Exception as e:
            logger.warning("Git temporal mining encountered: %s", e)
            return 0

    def resolve_seed(self, query: str) -> str | None:
        """Resolves an arbitrary identifier, filename, or symbol to a node ID."""
        if query in self.nodes:
            return query
        q_lower = query.lower()
        if query in self._file_to_id:
            return self._file_to_id[query]
        for fpath, fid in self._file_to_id.items():
            if fpath.endswith(query) or query.endswith(fpath):
                return fid

        if query in self._symbol_to_ids:
            candidates = self._symbol_to_ids[query]
            if candidates:
                return sorted(candidates)[0]
        if q_lower in self._symbol_to_ids:
            candidates = self._symbol_to_ids[q_lower]
            if candidates:
                return sorted(candidates)[0]

        return None

    def compute_blast_radius(
        self,
        seed: str,
        depth: int = 2,
        include_temporal: bool = True,
    ) -> dict[str, Any]:
        """
        Reverse-walks dependency edges and temporal co-change linkages.
        """
        seed_id = self.resolve_seed(seed)
        if not seed_id:
            return {
                "seed": seed,
                "found": False,
                "error": f"Seed identifier '{seed}' not found in knowledge graph.",
                "impacted_symbols": [],
                "impacted_files": [],
                "impacted_tests": [],
                "total_affected": 0,
            }

        allowed_relations = {
            GraphRelation.DEFINES,
            GraphRelation.CALLS,
            GraphRelation.IMPORTS,
            GraphRelation.INHERITS,
            GraphRelation.IMPLEMENTS,
            GraphRelation.REFERENCES,
        }
        if include_temporal:
            allowed_relations.add(GraphRelation.CO_CHANGES)

        visited: set[str] = {seed_id}
        queue: deque[tuple[str, int]] = deque([(seed_id, 0)])
        hits: list[dict[str, Any]] = []

        while queue:
            curr_id, curr_depth = queue.popleft()
            if curr_depth >= depth:
                continue

            for edge in self.adj_in.get(curr_id, []):
                rel_val = edge.relation.value if isinstance(edge.relation, GraphRelation) else str(edge.relation)
                if any(rel_val == (r.value if isinstance(r, GraphRelation) else r) for r in allowed_relations):
                    src_id = edge.source
                    if src_id not in visited:
                        visited.add(src_id)
                        queue.append((src_id, curr_depth + 1))
                        src_node = self.nodes.get(src_id)
                        if src_node:
                            hits.append({
                                "node_id": src_id,
                                "label": src_node.label,
                                "type": str(src_node.node_type),
                                "language": src_node.language,
                                "source_file": src_node.source_file,
                                "source_location": src_node.source_location,
                                "depth": curr_depth + 1,
                                "via_relation": rel_val,
                                "confidence": edge.confidence,
                            })

        impacted_symbols = [
            h["label"] for h in hits
            if h["type"] in (SemanticNodeKind.FUNCTION, SemanticNodeKind.CLASS, SemanticNodeKind.STRUCT, SemanticNodeKind.TRAIT, SemanticNodeKind.INTERFACE, SemanticNodeKind.SYMBOL)
            or h["type"] in ("function", "class", "struct", "trait", "interface", "symbol")
        ]
        impacted_files = sorted({h["source_file"] for h in hits if h["source_file"] and not h["source_file"].startswith("sym::")})
        # Test detection without hardcoded framework strings: looks for test identifier markers in file path
        impacted_tests = sorted({f for f in impacted_files if "test" in f.lower() or "spec" in f.lower()})

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

    def query_graph(self, question: str, depth: int = 2, max_nodes: int = 50) -> str:
        """
        Structural context retrieval with zero regex string tokenization.
        """
        # Clean punctuation using string translation table (zero regex)
        clean_question = "".join(c if (c.isalnum() or c == "_") else " " for c in question)
        tokens = [w.lower() for w in clean_question.split() if len(w) > 2]
        scored_seeds: list[tuple[int, str]] = []

        for nid, node in self.nodes.items():
            score = 0
            label_lower = node.label.lower()
            file_lower = node.source_file.lower()
            for t in tokens:
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
            return f"No symbols matched question: '{question}'."

        visited: set[str] = set(seeds)
        queue = deque([(s, 0) for s in seeds])
        edges_collected: list[KnowledgeEdge] = []

        while queue and len(visited) < max_nodes:
            curr, d = queue.popleft()
            if d >= depth:
                continue
            for e in self.adj_out.get(curr, []):
                edges_collected.append(e)
                if e.target not in visited and e.target in self.nodes:
                    visited.add(e.target)
                    queue.append((e.target, d + 1))

        lines = [f"=== Knowledge Graph Context for: '{question}' ==="]
        lines.append(f"Matched Seeds: {', '.join(self.nodes[s].label for s in seeds)}")
        lines.append("\nEntities:")
        for nid in sorted(visited):
            n = self.nodes.get(nid)
            if n:
                lines.append(f"  [{n.language}:{n.node_type}] {n.label} ({n.source_file}:{n.source_location})")

        lines.append("\nRelationships:")
        for e in edges_collected:
            src = self.nodes.get(e.source, KnowledgeNode(e.source, e.source, "")).label
            tgt = self.nodes.get(e.target, KnowledgeNode(e.target, e.target, "")).label
            rel_str = e.relation.value if isinstance(e.relation, GraphRelation) else str(e.relation)
            lines.append(f"  {src} --[{rel_str}]--> {tgt}")

        return "\n".join(lines)


# Workspace singleton
knowledge_graph = PolyglotKnowledgeGraph()
