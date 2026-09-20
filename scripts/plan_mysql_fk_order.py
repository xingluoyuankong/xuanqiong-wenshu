#!/usr/bin/env python3
"""Read-only ORM foreign-key dependency planner for MySQL migration review."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List, Set


def tarjan(graph: Dict[str, Set[str]]) -> List[List[str]]:
    index = 0
    indices: Dict[str, int] = {}
    low: Dict[str, int] = {}
    stack: List[str] = []
    on_stack: Set[str] = set()
    components: List[List[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        low[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for child in graph.get(node, set()):
            if child not in indices:
                visit(child)
                low[node] = min(low[node], low[child])
            elif child in on_stack:
                low[node] = min(low[node], indices[child])
        if low[node] == indices[node]:
            component = []
            while True:
                child = stack.pop()
                on_stack.remove(child)
                component.append(child)
                if child == node:
                    break
            components.append(sorted(component))

    for node in sorted(graph):
        if node not in indices:
            visit(node)
    return components


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    from app.db.base import Base
    import app.models  # noqa: F401

    tables = set(Base.metadata.tables)
    graph: Dict[str, Set[str]] = {name: set() for name in tables}
    edges = []
    for table in Base.metadata.tables.values():
        for foreign_key in table.foreign_keys:
            target = foreign_key.target_fullname.split(".", 1)[0]
            if target in tables and target != table.name:
                graph[table.name].add(target)
                edges.append({"from": table.name, "to": target, "constraint": str(foreign_key.constraint.name or "unnamed")})
            elif target == table.name:
                graph[table.name].add(target)
                edges.append({"from": table.name, "to": target, "constraint": str(foreign_key.constraint.name or "unnamed")})

    indegree = {name: 0 for name in graph}
    reverse: Dict[str, Set[str]] = {name: set() for name in graph}
    for child, parents in graph.items():
        for parent in parents:
            if parent != child:
                indegree[child] += 1
                reverse[parent].add(child)
    ready = sorted(name for name, count in indegree.items() if count == 0)
    phases: List[List[str]] = []
    remaining = set(graph)
    while ready:
        phase = ready
        phases.append(phase)
        remaining -= set(phase)
        next_ready = []
        for parent in phase:
            for child in sorted(reverse[parent]):
                indegree[child] -= 1
                if indegree[child] == 0:
                    next_ready.append(child)
        ready = sorted(next_ready)

    components = [component for component in tarjan(graph) if len(component) > 1 or any(node in graph[node] for node in component)]
    result = {
        "audit_type": "readonly_mysql_fk_dependency_plan",
        "execute": False,
        "connected": False,
        "writes_performed": False,
        "table_count": len(tables),
        "edge_count": len(edges),
        "acyclic_phases": phases,
        "blocked_cycles": components,
        "cycle_edge_details": [edge for edge in edges if any(edge["from"] in component and edge["to"] in component for component in components)],
        "status": "READY_FOR_ORDER_REVIEW" if not components else "BLOCKED_BY_FK_CYCLES",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())