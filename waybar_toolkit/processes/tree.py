"""Process tree utilities — build and flatten parent→child hierarchy."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from waybar_toolkit.processes.backend import ProcessInfo


# ---------------------------------------------------------------------------
# Tree node
# ---------------------------------------------------------------------------


@dataclass
class TreeNode:
    """A node in the process tree."""

    process: ProcessInfo
    children: list[TreeNode] = field(default_factory=list)
    depth: int = 0
    expanded: bool = True


# ---------------------------------------------------------------------------
# Build tree
# ---------------------------------------------------------------------------


def build_process_tree(processes: list[ProcessInfo]) -> list[TreeNode]:
    """Build a forest of TreeNodes from a flat process list.

    Returns the list of root nodes (processes whose parent is not in the list
    or whose parent is PID 0).
    """
    by_pid: dict[int, TreeNode] = {}
    for proc in processes:
        by_pid[proc.pid] = TreeNode(process=proc)

    roots: list[TreeNode] = []

    for node in by_pid.values():
        ppid = node.process.ppid
        parent = by_pid.get(ppid)
        if parent and parent is not node:
            parent.children.append(node)
        else:
            roots.append(node)

    # Sort children by PID at each level
    _sort_tree(roots)

    return roots


def _sort_tree(nodes: list[TreeNode]) -> None:
    """Recursively sort children by PID."""
    nodes.sort(key=lambda n: n.process.pid)
    for node in nodes:
        _sort_tree(node.children)


# ---------------------------------------------------------------------------
# Flatten tree for display
# ---------------------------------------------------------------------------


@dataclass
class FlatRow:
    """A single row in the flattened tree view."""

    process: ProcessInfo
    depth: int
    has_children: bool
    expanded: bool
    node: TreeNode  # Reference for toggle


def flatten_tree(
    roots: list[TreeNode],
    collapsed: Optional[set[int]] = None,
) -> list[FlatRow]:
    """Flatten the tree into a list of rows with depth info.

    Args:
        roots: Root TreeNode list.
        collapsed: Set of PIDs whose children should be hidden.

    Returns:
        Flat list of FlatRow suitable for rendering in a list widget.
    """
    if collapsed is None:
        collapsed = set()

    rows: list[FlatRow] = []
    _flatten_recursive(roots, 0, collapsed, rows)
    return rows


def _flatten_recursive(
    nodes: list[TreeNode],
    depth: int,
    collapsed: set[int],
    out: list[FlatRow],
) -> None:
    for node in nodes:
        node.depth = depth
        is_collapsed = node.process.pid in collapsed
        has_children = len(node.children) > 0

        out.append(
            FlatRow(
                process=node.process,
                depth=depth,
                has_children=has_children,
                expanded=not is_collapsed,
                node=node,
            )
        )

        if has_children and not is_collapsed:
            _flatten_recursive(node.children, depth + 1, collapsed, out)


# ---------------------------------------------------------------------------
# Group by user
# ---------------------------------------------------------------------------


@dataclass
class UserGroup:
    """A group of processes belonging to the same user."""

    user: str
    processes: list[ProcessInfo] = field(default_factory=list)
    expanded: bool = True

    @property
    def total_cpu(self) -> float:
        return round(sum(p.cpu_percent for p in self.processes), 1)

    @property
    def total_mem(self) -> float:
        return round(sum(p.mem_percent for p in self.processes), 1)

    @property
    def count(self) -> int:
        return len(self.processes)


def group_by_user(processes: list[ProcessInfo]) -> list[UserGroup]:
    """Group processes by user, sorted by total CPU descending."""
    groups: dict[str, UserGroup] = {}
    for proc in processes:
        if proc.user not in groups:
            groups[proc.user] = UserGroup(user=proc.user)
        groups[proc.user].processes.append(proc)

    # Sort each group's processes by CPU desc
    for group in groups.values():
        group.processes.sort(key=lambda p: p.cpu_percent, reverse=True)

    # Sort groups by total CPU desc
    return sorted(groups.values(), key=lambda g: g.total_cpu, reverse=True)
