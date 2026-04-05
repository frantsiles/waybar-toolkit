"""Backend for querying and configuring monitors.

Primary backend: hyprctl (Hyprland)
Fallback: wlr-randr (generic wlroots compositors)
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field

from waybar_toolkit.utils.compositor import Compositor, detect_compositor, has_command


@dataclass
class MonitorMode:
    """A display mode (resolution + refresh rate)."""

    width: int
    height: int
    refresh: float

    @property
    def label(self) -> str:
        return f"{self.width}x{self.height}@{self.refresh:.0f}Hz"

    def __str__(self) -> str:
        return self.label


@dataclass
class Monitor:
    """Represents a connected monitor."""

    name: str
    description: str
    make: str
    model: str
    serial: str
    width: int
    height: int
    physical_width: int
    physical_height: int
    refresh_rate: float
    x: int
    y: int
    scale: float
    transform: int
    enabled: bool
    modes: list[MonitorMode] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        """Friendly name like 'MSI MAG241C (HDMI-A-1)'."""
        if self.model and self.model != self.name:
            return f"{self.model} ({self.name})"
        return self.name

    @property
    def scaled_width(self) -> int:
        """Effective width after scale is applied."""
        return int(self.width / self.scale)

    @property
    def scaled_height(self) -> int:
        """Effective height after scale is applied."""
        return int(self.height / self.scale)

    @property
    def current_mode(self) -> MonitorMode:
        return MonitorMode(self.width, self.height, self.refresh_rate)

    @property
    def transform_label(self) -> str:
        labels = {
            0: "Normal",
            1: "90°",
            2: "180°",
            3: "270°",
            4: "Flipped",
            5: "Flipped 90°",
            6: "Flipped 180°",
            7: "Flipped 270°",
        }
        return labels.get(self.transform, "Normal")


# ---------------------------------------------------------------------------
# Hyprland backend
# ---------------------------------------------------------------------------


def _run(cmd: list[str], timeout: int = 5) -> str:
    """Run a command and return stdout."""
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    result.check_returncode()
    return result.stdout


def _parse_hyprland_monitors(data: list[dict]) -> list[Monitor]:
    monitors: list[Monitor] = []
    for m in data:
        modes: list[MonitorMode] = []
        for mode_str in m.get("availableModes", []):
            # format: "1920x1080@60.00Hz"
            try:
                res, hz = mode_str.replace("Hz", "").split("@")
                w, h = res.split("x")
                modes.append(MonitorMode(int(w), int(h), float(hz)))
            except (ValueError, IndexError):
                continue

        monitors.append(
            Monitor(
                name=m["name"],
                description=m.get("description", ""),
                make=m.get("make", ""),
                model=m.get("model", ""),
                serial=m.get("serial", ""),
                width=m["width"],
                height=m["height"],
                physical_width=m.get("physicalWidth", 0),
                physical_height=m.get("physicalHeight", 0),
                refresh_rate=m.get("refreshRate", 60.0),
                x=m.get("x", 0),
                y=m.get("y", 0),
                scale=m.get("scale", 1.0),
                transform=m.get("transform", 0),
                enabled=not m.get("disabled", False),
                modes=modes,
            )
        )
    return monitors


def get_monitors_hyprland() -> list[Monitor]:
    """Query monitors via hyprctl."""
    raw = _run(["hyprctl", "monitors", "-j"])
    data = json.loads(raw)
    return _parse_hyprland_monitors(data)


def _hyprctl_monitor_arg(mon: Monitor) -> str:
    """Build the monitor config string for hyprctl."""
    mode = f"{mon.width}x{mon.height}@{mon.refresh_rate:.0f}"
    pos = f"{mon.x}x{mon.y}"
    return f"{mon.name},{mode},{pos},{mon.scale},transform,{mon.transform}"


def apply_monitor_hyprland(mon: Monitor) -> None:
    """Apply monitor configuration via hyprctl keyword."""
    cmd = ["hyprctl", "keyword", "monitor", _hyprctl_monitor_arg(mon)]
    _run(cmd)


def apply_all_hyprland(monitors: list[Monitor]) -> None:
    """Apply all monitor configs atomically via hyprctl --batch."""
    batch_cmds = [
        f"keyword monitor {_hyprctl_monitor_arg(mon)}" for mon in monitors
    ]
    cmd = ["hyprctl", "--batch", ";".join(batch_cmds)]
    _run(cmd)


# ---------------------------------------------------------------------------
# wlr-randr fallback
# ---------------------------------------------------------------------------


def _parse_wlr_randr_output(output: str) -> list[Monitor]:
    """Parse wlr-randr text output into Monitor objects."""
    monitors: list[Monitor] = []
    current: dict | None = None
    modes: list[MonitorMode] = []

    for line in output.splitlines():
        stripped = line.strip()

        # New monitor block — not indented
        if not line.startswith(" ") and not line.startswith("\t") and stripped:
            if current is not None:
                current["modes"] = modes
                monitors.append(Monitor(**current))
                modes = []

            # e.g.: 'eDP-1 "Chimei Innolux Corporation 0x150D (eDP-1)"'
            parts = stripped.split('"', 1)
            name = parts[0].strip()
            desc = parts[1].rstrip('"') if len(parts) > 1 else ""

            current = dict(
                name=name,
                description=desc,
                make="",
                model="",
                serial="",
                width=0,
                height=0,
                physical_width=0,
                physical_height=0,
                refresh_rate=60.0,
                x=0,
                y=0,
                scale=1.0,
                transform=0,
                enabled=True,
            )
        elif current is None:
            continue
        elif stripped.startswith("Make:"):
            current["make"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("Model:"):
            current["model"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("Serial:"):
            current["serial"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("Physical size:"):
            try:
                size = stripped.split(":", 1)[1].strip().replace("mm", "").strip()
                w, h = size.split("x")
                current["physical_width"] = int(w)
                current["physical_height"] = int(h)
            except (ValueError, IndexError):
                pass
        elif stripped.startswith("Position:"):
            try:
                pos = stripped.split(":", 1)[1].strip()
                x, y = pos.split(",")
                current["x"] = int(x)
                current["y"] = int(y)
            except (ValueError, IndexError):
                pass
        elif stripped.startswith("Scale:"):
            try:
                current["scale"] = float(stripped.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif stripped.startswith("Enabled:"):
            current["enabled"] = "yes" in stripped.lower()
        elif stripped.startswith("Transform:"):
            transform_map = {
                "normal": 0,
                "90": 1,
                "180": 2,
                "270": 3,
                "flipped": 4,
                "flipped-90": 5,
                "flipped-180": 6,
                "flipped-270": 7,
            }
            val = stripped.split(":", 1)[1].strip().lower()
            current["transform"] = transform_map.get(val, 0)
        elif "px," in stripped and "Hz" in stripped:
            # Mode line: "1920x1080 px, 60.007999 Hz (preferred, current)"
            try:
                parts = stripped.split("px,")
                res = parts[0].strip()
                hz_part = parts[1].strip().split("Hz")[0].strip()
                w, h = res.split("x")
                mode = MonitorMode(int(w), int(h), float(hz_part))
                modes.append(mode)
                if "current" in stripped:
                    current["width"] = mode.width
                    current["height"] = mode.height
                    current["refresh_rate"] = mode.refresh
            except (ValueError, IndexError):
                pass

    if current is not None:
        current["modes"] = modes
        monitors.append(Monitor(**current))

    return monitors


def get_monitors_wlr() -> list[Monitor]:
    """Query monitors via wlr-randr."""
    raw = _run(["wlr-randr"])
    return _parse_wlr_randr_output(raw)


def apply_monitor_wlr(mon: Monitor) -> None:
    """Apply monitor configuration via wlr-randr."""
    cmd = [
        "wlr-randr",
        "--output",
        mon.name,
        "--pos",
        f"{mon.x},{mon.y}",
        "--scale",
        str(mon.scale),
        "--mode",
        f"{mon.width}x{mon.height}@{mon.refresh_rate:.3f}Hz",
    ]
    transform_map = {
        0: "normal",
        1: "90",
        2: "180",
        3: "270",
        4: "flipped",
        5: "flipped-90",
        6: "flipped-180",
        7: "flipped-270",
    }
    cmd.extend(["--transform", transform_map.get(mon.transform, "normal")])
    _run(cmd)


# ---------------------------------------------------------------------------
# Public API — auto-selects backend
# ---------------------------------------------------------------------------


class MonitorBackend:
    """Unified monitor backend that auto-selects the right tool."""

    def __init__(self) -> None:
        self.compositor = detect_compositor()

    def get_monitors(self) -> list[Monitor]:
        """Get list of connected monitors."""
        if self.compositor == Compositor.HYPRLAND and has_command("hyprctl"):
            return get_monitors_hyprland()
        if has_command("wlr-randr"):
            return get_monitors_wlr()
        raise RuntimeError(
            "No supported monitor backend found. "
            "Install hyprctl (Hyprland) or wlr-randr."
        )

    def apply(self, monitor: Monitor) -> None:
        """Apply configuration for a single monitor."""
        if self.compositor == Compositor.HYPRLAND and has_command("hyprctl"):
            apply_monitor_hyprland(monitor)
        elif has_command("wlr-randr"):
            apply_monitor_wlr(monitor)
        else:
            raise RuntimeError("No supported backend to apply monitor config.")

    def apply_all(self, monitors: list[Monitor]) -> None:
        """Apply configuration for all monitors atomically."""
        if self.compositor == Compositor.HYPRLAND and has_command("hyprctl"):
            apply_all_hyprland(monitors)
        else:
            for mon in monitors:
                self.apply(mon)

    def swap_positions(
        self, monitors: list[Monitor], idx_a: int, idx_b: int
    ) -> list[Monitor]:
        """Swap the positions of two monitors and recalculate X coords.

        Returns the updated list sorted by X position.
        """
        a, b = monitors[idx_a], monitors[idx_b]

        # Swap X positions: place them side by side in swapped order
        # Sort all monitors by X, find which is left/right, then swap
        sorted_mons = sorted(monitors, key=lambda m: m.x)

        # Recalculate positions left to right
        pos_a, pos_b = a.x, b.x
        a.x, b.x = pos_b, pos_a

        # If they were adjacent, recalc to avoid overlap
        sorted_mons = sorted(monitors, key=lambda m: m.x)
        x_cursor = 0
        for mon in sorted_mons:
            mon.x = x_cursor
            x_cursor += mon.scaled_width

        return sorted_mons
