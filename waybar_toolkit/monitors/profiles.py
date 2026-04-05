"""Save and load monitor layout profiles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from waybar_toolkit.monitors.backend import Monitor

PROFILES_DIR = Path.home() / ".config" / "waybar-toolkit" / "profiles"


class ProfileManager:
    """Manages saved monitor profiles as JSON files."""

    def __init__(self, directory: Optional[Path] = None) -> None:
        self._dir = directory or PROFILES_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    def list_profiles(self) -> list[str]:
        """Return list of saved profile names."""
        return sorted(
            p.stem for p in self._dir.glob("*.json")
        )

    def save(self, name: str, monitors: list[Monitor]) -> None:
        """Save current monitor layout as a named profile."""
        data = []
        for mon in monitors:
            data.append({
                "name": mon.name,
                "width": mon.width,
                "height": mon.height,
                "refresh_rate": mon.refresh_rate,
                "x": mon.x,
                "y": mon.y,
                "scale": mon.scale,
                "transform": mon.transform,
            })

        path = self._dir / f"{name}.json"
        path.write_text(json.dumps(data, indent=2))

    def load(
        self, name: str, current_monitors: list[Monitor]
    ) -> Optional[list[Monitor]]:
        """Load a profile and apply its settings to current monitors.

        Only monitors whose name matches are updated. Returns None if
        the profile doesn't exist.
        """
        path = self._dir / f"{name}.json"
        if not path.exists():
            return None

        data = json.loads(path.read_text())
        by_name = {entry["name"]: entry for entry in data}

        for mon in current_monitors:
            if mon.name in by_name:
                entry = by_name[mon.name]
                mon.width = entry.get("width", mon.width)
                mon.height = entry.get("height", mon.height)
                mon.refresh_rate = entry.get("refresh_rate", mon.refresh_rate)
                mon.x = entry.get("x", mon.x)
                mon.y = entry.get("y", mon.y)
                mon.scale = entry.get("scale", mon.scale)
                mon.transform = entry.get("transform", mon.transform)

        return current_monitors

    def delete(self, name: str) -> bool:
        """Delete a saved profile."""
        path = self._dir / f"{name}.json"
        if path.exists():
            path.unlink()
            return True
        return False
