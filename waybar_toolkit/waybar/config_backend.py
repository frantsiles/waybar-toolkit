"""Backend for reading/editing Waybar JSONC config and handling backups."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from shutil import copy2
from typing import Any


DEFAULT_WAYBAR_CONFIG = Path.home() / ".config" / "waybar" / "config.jsonc"
DEFAULT_BACKUP_DIR = (
    Path.home() / ".config" / "waybar-toolkit" / "waybar-backups"
)


class WaybarConfigError(RuntimeError):
    """Base error for Waybar config operations."""


class WaybarConfigParseError(WaybarConfigError):
    """Raised when parsing config JSONC fails."""


class WaybarBackupError(WaybarConfigError):
    """Raised for backup/restore failures."""


def _strip_jsonc_comments(text: str) -> str:
    """Strip // and /* */ comments while preserving string literals."""
    out: list[str] = []
    in_string = False
    in_single_comment = False
    in_multi_comment = False
    escaped = False
    i = 0
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if in_single_comment:
            if ch == "\n":
                in_single_comment = False
                out.append(ch)
            i += 1
            continue

        if in_multi_comment:
            if ch == "*" and nxt == "/":
                in_multi_comment = False
                i += 2
            else:
                i += 1
            continue

        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue

        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue

        if ch == "/" and nxt == "/":
            in_single_comment = True
            i += 2
            continue

        if ch == "/" and nxt == "*":
            in_multi_comment = True
            i += 2
            continue

        out.append(ch)
        i += 1

    return "".join(out)


def _strip_trailing_commas(text: str) -> str:
    """Remove trailing commas before ] or }."""
    return re.sub(r",(\s*[}\]])", r"\1", text)


class WaybarConfigManager:
    """Read/edit/save Waybar config and manage backups."""

    def __init__(
        self,
        config_path: Path | None = None,
        backup_dir: Path | None = None,
    ) -> None:
        self._config_path = config_path or DEFAULT_WAYBAR_CONFIG
        self._backup_dir = backup_dir or DEFAULT_BACKUP_DIR
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, Any] | None = None

    @property
    def config_path(self) -> Path:
        return self._config_path

    def load(self) -> dict[str, Any]:
        """Load and parse the Waybar JSONC config."""
        if not self._config_path.exists():
            raise WaybarConfigError(
                f"Config file not found: {self._config_path}"
            )

        raw = self._config_path.read_text(encoding="utf-8")
        cleaned = _strip_trailing_commas(_strip_jsonc_comments(raw))
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise WaybarConfigParseError(
                f"Invalid Waybar JSONC config: {exc}"
            ) from exc

        if not isinstance(parsed, dict):
            raise WaybarConfigParseError(
                "Waybar config root must be a JSON object"
            )
        self._data = parsed
        return parsed

    def save(self) -> None:
        """Write current in-memory config as formatted JSON."""
        if self._data is None:
            self.load()
        assert self._data is not None
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text(
            json.dumps(self._data, indent=4, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def get_node_keys(self) -> list[str]:
        """Return top-level node keys in insertion order."""
        data = self._data if self._data is not None else self.load()
        return list(data.keys())

    def get_node_value(self, key: str) -> Any:
        """Get a top-level node value."""
        data = self._data if self._data is not None else self.load()
        if key not in data:
            raise WaybarConfigError(f"Node not found: {key}")
        return data[key]

    def set_node_value(self, key: str, value: Any) -> None:
        """Set/replace a top-level node value."""
        data = self._data if self._data is not None else self.load()
        data[key] = value
        self._data = data

    def backup_now(self) -> Path:
        """Create a timestamped backup copy of the current config."""
        if not self._config_path.exists():
            raise WaybarBackupError(
                f"Config file not found: {self._config_path}"
            )
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = self._backup_dir / f"waybar-config-{ts}.jsonc"
        copy2(self._config_path, dest)
        return dest

    def list_backups(self) -> list[Path]:
        """List backups newest first."""
        files = list(self._backup_dir.glob("waybar-config-*.jsonc"))
        return sorted(files, key=lambda p: p.name, reverse=True)

    def restore_backup(self, backup_name: str) -> Path:
        """Restore a backup by filename."""
        src = self._backup_dir / backup_name
        if not src.exists() or not src.is_file():
            raise WaybarBackupError(f"Backup not found: {backup_name}")
        copy2(src, self._config_path)
        self._data = None
        return self._config_path

