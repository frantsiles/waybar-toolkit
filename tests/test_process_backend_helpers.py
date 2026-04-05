from __future__ import annotations

from waybar_toolkit.processes.backend import ProcessBackend


def test_calc_cpu_percent_returns_zero_for_invalid_snapshots() -> None:
    assert ProcessBackend._calc_cpu_percent((), ()) == 0.0
    assert ProcessBackend._calc_cpu_percent((1, 2, 3), (2, 3, 4)) == 0.0


def test_calc_cpu_percent_computes_expected_value() -> None:
    prev = (100, 0, 50, 800, 50)
    curr = (200, 0, 100, 900, 60)

    # total_delta = 260, idle_delta = 110 => usage ~57.7%
    assert ProcessBackend._calc_cpu_percent(prev, curr) == 57.7


def test_format_uptime_outputs_readable_units() -> None:
    assert ProcessBackend.format_uptime(1800) == "30m"
    assert ProcessBackend.format_uptime(5 * 3600 + 20 * 60) == "5h 20m"
    assert ProcessBackend.format_uptime(2 * 86400 + 3 * 3600 + 10 * 60) == "2d 3h 10m"
