from __future__ import annotations

from waybar_toolkit.processes.backend import ProcessInfo
from waybar_toolkit.processes.tree import (
    build_process_tree,
    flatten_tree,
    group_by_user,
)


def _proc(
    pid: int,
    ppid: int,
    name: str,
    user: str,
    cpu: float,
    mem: float,
) -> ProcessInfo:
    return ProcessInfo(
        pid=pid,
        ppid=ppid,
        name=name,
        user=user,
        state="S",
        cpu_percent=cpu,
        mem_percent=mem,
        mem_rss_kb=1024,
        threads=1,
        cmdline=name,
    )


def test_build_process_tree_sets_root_and_children() -> None:
    procs = [
        _proc(1, 0, "init", "root", 0.1, 0.2),
        _proc(10, 1, "child-a", "alice", 3.0, 1.0),
        _proc(11, 1, "child-b", "bob", 1.0, 0.5),
        _proc(20, 10, "grandchild", "alice", 0.5, 0.2),
    ]

    roots = build_process_tree(procs)

    assert [node.process.pid for node in roots] == [1]
    assert [child.process.pid for child in roots[0].children] == [10, 11]
    assert [child.process.pid for child in roots[0].children[0].children] == [20]


def test_flatten_tree_respects_collapsed_nodes() -> None:
    procs = [
        _proc(1, 0, "init", "root", 0.1, 0.2),
        _proc(10, 1, "child-a", "alice", 3.0, 1.0),
        _proc(20, 10, "grandchild", "alice", 0.5, 0.2),
    ]
    roots = build_process_tree(procs)

    rows = flatten_tree(roots, collapsed={10})
    pids = [row.process.pid for row in rows]
    depths = [row.depth for row in rows]

    assert pids == [1, 10]
    assert depths == [0, 1]
    assert rows[1].has_children is True
    assert rows[1].expanded is False


def test_group_by_user_sorts_by_total_cpu_desc() -> None:
    procs = [
        _proc(1, 0, "a", "alice", 10.0, 1.0),
        _proc(2, 0, "b", "bob", 4.0, 0.5),
        _proc(3, 0, "c", "alice", 2.0, 0.3),
        _proc(4, 0, "d", "carol", 7.0, 0.4),
    ]

    groups = group_by_user(procs)

    assert [group.user for group in groups] == ["alice", "carol", "bob"]
    assert groups[0].total_cpu == 12.0
    assert groups[0].count == 2
