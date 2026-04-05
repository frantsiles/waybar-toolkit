"""Waybar stats output — prints JSON with CPU/RAM for Waybar custom module.

Usage in Waybar config:
    "custom/stats": {
        "exec": "waybar-toolkit-stats",
        "return-type": "json",
        "interval": 2
    }
"""

from __future__ import annotations

import json
import sys

from waybar_toolkit.processes.backend import ProcessBackend


def main() -> None:
    """Print a single JSON line with system stats for Waybar."""
    backend = ProcessBackend()

    # First call seeds the CPU jiffies baseline
    backend.get_system_stats()

    # Small delay to get a meaningful CPU delta
    import time
    time.sleep(1)

    stats = backend.get_system_stats()

    cpu = stats.cpu_percent_total
    mem_used_gb = stats.mem_used_kb / (1024 * 1024)
    mem_total_gb = stats.mem_total_kb / (1024 * 1024)
    mem_pct = (
        (stats.mem_used_kb / stats.mem_total_kb * 100)
        if stats.mem_total_kb > 0
        else 0
    )

    # Determine CSS class for styling
    if cpu >= 80 or mem_pct >= 90:
        css_class = "critical"
    elif cpu >= 50 or mem_pct >= 70:
        css_class = "warning"
    else:
        css_class = "normal"

    uptime = backend.format_uptime(stats.uptime_seconds)
    load = ", ".join(f"{l:.2f}" for l in stats.load_avg)

    output = {
        "text": f"CPU {cpu:.0f}% | RAM {mem_used_gb:.1f}G",
        "tooltip": (
            f"CPU: {cpu:.1f}%\n"
            f"RAM: {mem_used_gb:.1f}/{mem_total_gb:.1f} GB ({mem_pct:.0f}%)\n"
            f"Processes: {stats.process_count}\n"
            f"Load: {load}\n"
            f"Uptime: {uptime}"
        ),
        "class": css_class,
    }

    json.dump(output, sys.stdout)
    print()  # Newline for Waybar


if __name__ == "__main__":
    main()
