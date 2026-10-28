"""
SpaceV DAG Node & Edge Contract Schemas (Volume IV §29).
Defines structural constraints, node types, edge semantics, and graph validation:
  - Node Types: action, condition, approval, merge, terminal
  - Edge Types: dependency, conditional, error
  - Topological cycle detection and reference validation
"""
from __future__ import annotations

from typing import Any

DAG_NODE_TYPES: dict[str, dict[str, list[str]]] = {
    "action": {
        "required_fields": ["node_id", "name", "agent", "action"],
        "optional_fields": ["action_args", "max_retries", "timeout_sec"],
    },
    "condition": {
        "required_fields": ["node_id", "name", "condition"],
        "optional_fields": ["true_branch", "false_branch"],
    },
    "approval": {
        "required_fields": ["node_id", "name", "description"],
        "optional_fields": ["auto_approve_after_sec"],
    },
    "merge": {
        "required_fields": ["node_id", "name", "depends_on"],
        "optional_fields": ["merge_strategy"],  # "all" | "any" | "majority"
    },
    "terminal": {
        "required_fields": ["node_id", "name"],
        "optional_fields": ["status_message"],
    },
}

DAG_EDGE_TYPES: dict[str, str] = {
    "dependency": "Normal dependency — target waits for source to complete",
    "conditional": "Target runs only if source result matches condition",
    "error": "Target runs only if source fails (error handling branch)",
}


def validate_node_schema(arg1: Any, arg2: dict[str, Any] | None = None) -> tuple[bool, str]:
    """
    Validates that a node dictionary contains all required fields for its node type.
    Supports either validate_node_schema(node_dict) or validate_node_schema(node_type, node_dict).
    """
    if isinstance(arg1, str) and isinstance(arg2, dict):
        node_type = arg1
        node = dict(arg2)
        node["type"] = node_type
    elif isinstance(arg1, dict):
        node = arg1
        node_type = node.get("type", "action")
    else:
        return False, "Invalid arguments to validate_node_schema"

    if node_type not in DAG_NODE_TYPES:
        return False, f"Invalid node type '{node_type}'. Supported: {list(DAG_NODE_TYPES.keys())}"

    spec = DAG_NODE_TYPES[node_type]
    for req in spec["required_fields"]:
        if req not in node or node[req] is None or (isinstance(node[req], str) and not node[req].strip()):
            return False, f"Missing required field '{req}' for node type '{node_type}'"

    return True, ""


def validate_edge_schema(edge_type: str) -> tuple[bool, str]:
    """
    Validates that an edge type is recognized by the DAG schema.
    """
    if edge_type not in DAG_EDGE_TYPES:
        return False, f"Unknown edge type '{edge_type}'. Supported: {list(DAG_EDGE_TYPES.keys())}"
    return True, ""


def validate_dag_graph(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]] | None = None,
) -> tuple[bool, str]:
    """
    Validates a complete workflow DAG:
    1. All node IDs are unique
    2. All depends_on targets and edge targets exist
    3. No circular dependencies (topological sort verification via Kahn's algorithm)
    """
    if not nodes:
        return False, "DAG must contain at least one node"

    node_ids: set[str] = set()
    adj: dict[str, list[str]] = {}
    in_degree: dict[str, int] = {}

    for n in nodes:
        nid = n.get("node_id")
        if not nid:
            return False, "All nodes must have a non-empty 'node_id'"
        if nid in node_ids:
            return False, f"Duplicate node_id '{nid}' found in DAG"
        node_ids.add(nid)
        adj[nid] = []
        in_degree[nid] = 0

    # Process node-embedded dependencies
    for n in nodes:
        nid = n["node_id"]
        deps = n.get("depends_on", [])
        for dep in deps:
            if dep not in node_ids:
                return False, f"Node '{nid}' depends on non-existent node '{dep}'"
            adj[dep].append(nid)
            in_degree[nid] += 1

    # Process explicit edges if provided
    if edges:
        for e in edges:
            src = e.get("source")
            tgt = e.get("target")
            etype = e.get("type", "dependency")
            if not src or not tgt:
                return False, "Edges must specify non-empty 'source' and 'target'"
            if src not in node_ids:
                return False, f"Edge references non-existent source node '{src}'"
            if tgt not in node_ids:
                return False, f"Edge references non-existent target node '{tgt}'"

            ok, err = validate_edge_schema(etype)
            if not ok:
                return False, err

            adj[src].append(tgt)
            in_degree[tgt] += 1

    # Kahn's algorithm for topological sorting and cycle detection
    queue = [nid for nid in node_ids if in_degree[nid] == 0]
    visited_count = 0

    while queue:
        curr = queue.pop(0)
        visited_count += 1
        for neighbor in adj[curr]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if visited_count != len(node_ids):
        return False, "Cycle detected in DAG: circular dependencies are forbidden"

    return True, ""
