"""Detect the running Wayland compositor."""

from __future__ import annotations

import os
import shutil
import subprocess


class Compositor:
    HYPRLAND = "hyprland"
    SWAY = "sway"
    GENERIC = "generic"  # wlroots-based, fallback to wlr-randr


def detect_compositor() -> str:
    """Return the compositor type currently running."""
    # Hyprland sets HYPRLAND_INSTANCE_SIGNATURE
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return Compositor.HYPRLAND

    # Sway sets SWAYSOCK
    if os.environ.get("SWAYSOCK"):
        return Compositor.SWAY

    # Try to detect via process name
    try:
        result = subprocess.run(
            ["pgrep", "-x", "Hyprland"],
            capture_output=True,
            timeout=2,
        )
        if result.returncode == 0:
            return Compositor.HYPRLAND
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return Compositor.GENERIC


def has_command(cmd: str) -> bool:
    """Check if a command is available in PATH."""
    return shutil.which(cmd) is not None
