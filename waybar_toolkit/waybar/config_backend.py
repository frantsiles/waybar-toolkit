"""Waybar config backend — minimal, safe read/write for module management.

Only modifies modules-left/center/right. All other keys are preserved
as-is. JSONC comments are stripped on write (unavoidable with JSON).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

WAYBAR_SEARCH_PATHS: list[Path] = [
    Path.home() / ".config/waybar/config",
    Path.home() / ".config/waybar/config.jsonc",
    Path.home() / ".config/waybar/config.json",
]

ALIGN_KEYS = ("modules-left", "modules-center", "modules-right")


def find_config() -> Optional[Path]:
    for p in WAYBAR_SEARCH_PATHS:
        if p.exists():
            return p
    return None


def _parse_jsonc(text: str) -> Any:
    text = re.sub(r"//[^\n]*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return json.loads(text)


class WaybarConfigError(Exception):
    pass


class WaybarConfig:
    """Read, modify module lists, and atomically write a Waybar config."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._bars: list[dict[str, Any]] = []
        self._is_multi = False
        self._active = 0
        self.load()

    # ------------------------------------------------------------------
    # Load / bar selection
    # ------------------------------------------------------------------

    def load(self) -> None:
        try:
            raw = self._path.read_text(encoding="utf-8")
            parsed = _parse_jsonc(raw)
        except OSError as e:
            raise WaybarConfigError(f"Cannot read config: {e}") from e
        except json.JSONDecodeError as e:
            raise WaybarConfigError(f"Invalid JSON: {e}") from e

        if isinstance(parsed, list):
            self._is_multi = True
            self._bars = parsed
        else:
            self._is_multi = False
            self._bars = [parsed]
        self._active = min(self._active, len(self._bars) - 1)

    def select_bar(self, index: int) -> None:
        if 0 <= index < len(self._bars):
            self._active = index

    @property
    def bar_count(self) -> int:
        return len(self._bars)

    @property
    def bar_names(self) -> list[str]:
        return [b.get("name", f"Bar {i + 1}") for i, b in enumerate(self._bars)]

    @property
    def path(self) -> Path:
        return self._path

    @property
    def _bar(self) -> dict[str, Any]:
        return self._bars[self._active]

    # ------------------------------------------------------------------
    # Module list operations
    # ------------------------------------------------------------------

    def get_modules(self, align: str) -> list[str]:
        val = self._bar.get(align, [])
        if isinstance(val, str):
            return [val]
        return [str(m) for m in val]

    def set_modules(self, align: str, modules: list[str]) -> None:
        self._bar[align] = list(modules)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def backup(self) -> Path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_dir = self._path.parent / "backups"
        backup_dir.mkdir(exist_ok=True)
        suffix = self._path.suffix or ".jsonc"
        dest = backup_dir / f"{self._path.stem}_{ts}{suffix}"
        shutil.copy2(self._path, dest)
        return dest

    def save(self) -> Path:
        """Backup then atomically write. Returns the backup path."""
        backup_path = self.backup()
        root = self._bars if self._is_multi else self._bars[0]
        text = json.dumps(root, ensure_ascii=False, indent=4) + "\n"
        fd, tmp = tempfile.mkstemp(dir=self._path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp, self._path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return backup_path

    def list_backups(self) -> list[Path]:
        backup_dir = self._path.parent / "backups"
        if not backup_dir.exists():
            return []
        return sorted(
            backup_dir.glob(f"{self._path.stem}_*"),
            reverse=True,
        )

    def restore_backup(self, backup: Path) -> None:
        fd, tmp = tempfile.mkstemp(dir=self._path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(backup.read_bytes())
            os.replace(tmp, self._path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        self.load()
