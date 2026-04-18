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


def _mask_jsonc_comments(text: str) -> str:
    """Mask JSONC comments with spaces while preserving text length."""
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
                out.append("\n")
            else:
                out.append(" ")
            i += 1
            continue

        if in_multi_comment:
            if ch == "*" and nxt == "/":
                out.append(" ")
                out.append(" ")
                in_multi_comment = False
                i += 2
            else:
                out.append("\n" if ch == "\n" else " ")
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

        if ch == "/" and nxt == "/":
            out.append(" ")
            out.append(" ")
            in_single_comment = True
            i += 2
            continue

        if ch == "/" and nxt == "*":
            out.append(" ")
            out.append(" ")
            in_multi_comment = True
            i += 2
            continue

        out.append(ch)
        if ch == '"':
            in_string = True
        i += 1

    return "".join(out)


def _skip_ws(text: str, index: int) -> int:
    while index < len(text) and text[index] in " \t\r\n":
        index += 1
    return index


def _parse_string_end(text: str, index: int) -> int:
    if index >= len(text) or text[index] != '"':
        raise WaybarConfigParseError("Expected string token")
    i = index + 1
    escaped = False
    while i < len(text):
        ch = text[i]
        if escaped:
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == '"':
            return i + 1
        i += 1
    raise WaybarConfigParseError("Unterminated string token")


def _parse_compound_end(text: str, index: int) -> int:
    stack = [text[index]]
    i = index + 1
    in_string = False
    escaped = False
    while i < len(text):
        ch = text[i]
        if in_string:
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
            i += 1
            continue

        if ch in "{[":
            stack.append(ch)
            i += 1
            continue

        if ch in "}]":
            top = stack[-1]
            expected = "}" if top == "{" else "]"
            if ch != expected:
                raise WaybarConfigParseError("Mismatched closing token")
            stack.pop()
            i += 1
            if not stack:
                return i
            continue

        i += 1

    raise WaybarConfigParseError("Unterminated compound value")


def _parse_number_end(text: str, index: int) -> int:
    match = re.match(
        r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+\-]?\d+)?",
        text[index:],
    )
    if not match:
        raise WaybarConfigParseError("Invalid number token")
    return index + len(match.group(0))


def _parse_json_value_end(text: str, index: int) -> int:
    i = _skip_ws(text, index)
    if i >= len(text):
        raise WaybarConfigParseError("Missing value")
    ch = text[i]
    if ch == '"':
        return _parse_string_end(text, i)
    if ch in "{[":
        return _parse_compound_end(text, i)
    if text.startswith("true", i):
        return i + 4
    if text.startswith("false", i):
        return i + 5
    if text.startswith("null", i):
        return i + 4
    if ch == "-" or ch.isdigit():
        return _parse_number_end(text, i)
    raise WaybarConfigParseError("Unsupported value token")


def _line_indent_before(text: str, index: int) -> str:
    line_start = text.rfind("\n", 0, index) + 1
    i = line_start
    while i < len(text) and text[i] in " \t":
        i += 1
    return text[line_start:i]


def _find_top_level_value_span(
    original_text: str,
    key: str,
) -> tuple[int, int, int, str] | None:
    """Return (key_start, value_start, value_end, key_indent) for a top-level key."""
    masked = _mask_jsonc_comments(original_text)
    i = _skip_ws(masked, 0)
    if i >= len(masked) or masked[i] != "{":
        raise WaybarConfigParseError("Config root must start with '{'")
    i += 1

    while i < len(masked):
        i = _skip_ws(masked, i)
        if i >= len(masked):
            break
        if masked[i] == "}":
            return None

        key_start = i
        key_end = _parse_string_end(masked, i)
        try:
            current_key = json.loads(masked[key_start:key_end])
        except json.JSONDecodeError as exc:
            raise WaybarConfigParseError(
                "Invalid key token in top-level object"
            ) from exc

        i = _skip_ws(masked, key_end)
        if i >= len(masked) or masked[i] != ":":
            raise WaybarConfigParseError("Expected ':' after key")
        i += 1
        i = _skip_ws(masked, i)

        value_start = i
        value_end = _parse_json_value_end(masked, value_start)

        if current_key == key:
            key_indent = _line_indent_before(original_text, key_start)
            return (key_start, value_start, value_end, key_indent)

        i = _skip_ws(masked, value_end)
        if i < len(masked) and masked[i] == ",":
            i += 1
            continue
        if i < len(masked) and masked[i] == "}":
            return None
        raise WaybarConfigParseError("Expected ',' or '}' after top-level value")

    return None


def _find_top_level_entry_span(
    original_text: str,
    key: str,
) -> tuple[int, int] | None:
    """Return full top-level key entry span suitable for deletion."""
    value_span = _find_top_level_value_span(original_text, key)
    if value_span is None:
        return None

    key_start, _value_start, value_end, _key_indent = value_span
    masked = _mask_jsonc_comments(original_text)

    after_value = _skip_ws(masked, value_end)
    if after_value < len(masked) and masked[after_value] == ",":
        return key_start, after_value + 1

    # Last item in object: remove preceding comma if present.
    before_key = key_start - 1
    while before_key >= 0 and masked[before_key] in " \t\r\n":
        before_key -= 1
    if before_key >= 0 and masked[before_key] == ",":
        return before_key, value_end
    return key_start, value_end


def _detect_indent_unit(text: str) -> str:
    """Detect indentation style from top-level keys; fallback to 4 spaces."""
    indents = [
        match.group(1)
        for match in re.finditer(r'(?m)^([ \t]+)"[^"]+"\s*:', text)
    ]
    if not indents:
        return "    "
    if any("\t" in indent for indent in indents):
        return "\t"
    min_len = min(len(indent) for indent in indents)
    return " " * min_len if min_len > 0 else "    "


def _serialize_value_for_jsonc(
    value: Any,
    *,
    key_indent: str,
    indent_unit: str,
) -> str:
    if isinstance(value, (dict, list)):
        dumped = json.dumps(
            value,
            ensure_ascii=False,
            indent=indent_unit,
        )
        lines = dumped.splitlines()
        if len(lines) == 1:
            return dumped
        return lines[0] + "".join(f"\n{key_indent}{line}" for line in lines[1:])
    return json.dumps(value, ensure_ascii=False)


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
        self._original_text: str | None = None
        self._dirty_keys: list[str] = []
        self._deleted_keys: list[str] = []

    @property
    def config_path(self) -> Path:
        return self._config_path

    def set_config_path(self, path: Path) -> None:
        """Switch active config path and clear in-memory state."""
        self._config_path = path.expanduser()
        self._data = None
        self._original_text = None
        self._dirty_keys = []
        self._deleted_keys = []

    def create_new_config(self, path: Path | None = None) -> Path:
        """Create a new config file and set it as active path."""
        target = (path or self._config_path).expanduser()
        if target.exists():
            raise WaybarConfigError(f"Config file already exists: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{\n}\n", encoding="utf-8")
        self.set_config_path(target)
        return target

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
        self._original_text = raw
        self._dirty_keys = []
        self._deleted_keys = []
        return parsed

    def save(self) -> None:
        """Write edited nodes while preserving surrounding JSONC/comments."""
        if self._data is None:
            self.load()
        assert self._data is not None
        assert self._original_text is not None
        if not self._dirty_keys and not self._deleted_keys:
            return

        text = self._original_text
        for key in list(self._deleted_keys):
            entry_span = _find_top_level_entry_span(text, key)
            if entry_span is None:
                continue
            start, end = entry_span
            text = text[:start] + text[end:]
        indent_unit = _detect_indent_unit(text)
        for key in self._dirty_keys:
            span = _find_top_level_value_span(text, key)
            if span is None:
                raise WaybarConfigError(
                    "Could not preserve formatting while saving. "
                    f"Top-level node not found in source text: {key}"
                )
            _, value_start, value_end, key_indent = span
            replacement = _serialize_value_for_jsonc(
                self._data[key],
                key_indent=key_indent,
                indent_unit=indent_unit,
            )
            text = text[:value_start] + replacement + text[value_end:]

        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text(text, encoding="utf-8")
        self._original_text = text
        self._dirty_keys = []
        self._deleted_keys = []

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
        if key in self._deleted_keys:
            self._deleted_keys.remove(key)
        if key not in self._dirty_keys:
            self._dirty_keys.append(key)

    def delete_node(self, key: str) -> None:
        """Delete a top-level node from the config."""
        data = self._data if self._data is not None else self.load()
        if key in data:
            del data[key]
            self._data = data
            if key in self._dirty_keys:
                self._dirty_keys.remove(key)
            if key not in self._deleted_keys:
                self._deleted_keys.append(key)

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
        self._original_text = None
        self._dirty_keys = []
        self._deleted_keys = []
        return self._config_path
