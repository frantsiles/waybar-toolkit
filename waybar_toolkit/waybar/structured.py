"""Helpers for structured Waybar config editing UI."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

ALIGN_KEYS = ("modules-left", "modules-center", "modules-right")

LAYOUT_NUMERIC_KEYS = {
    "height",
    "spacing",
    "margin-top",
    "margin-right",
    "margin-bottom",
    "margin-left",
}
LAYOUT_BOOLEAN_KEYS = {
    "passthrough",
    "exclusive",
    "fixed-center",
    "ipc",
    "gtk-layer-shell",
    "reload_style_on_change",
}
LAYOUT_TEXT_KEYS = {
    "layer",
    "position",
    "mode",
    "name",
    "output",
}
LAYOUT_SUPPORTED_KEYS = (
    LAYOUT_NUMERIC_KEYS | LAYOUT_BOOLEAN_KEYS | LAYOUT_TEXT_KEYS
)


def _parse_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "yes", "1", "on"):
            return True
        if lowered in ("false", "no", "0", "off"):
            return False
    return None


def _parse_number(value: Any) -> int | float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if re.fullmatch(r"[+-]?\d+", stripped):
        return int(stripped)
    if re.fullmatch(r"[+-]?\d+\.\d+", stripped):
        return float(stripped)
    return None


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) == 0
    return False


def compact_object(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deep-compacted dict removing empty values recursively."""
    out: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            compacted = compact_object(value)
            if _is_empty(compacted):
                continue
            out[key] = compacted
            continue
        if isinstance(value, list):
            items = []
            for item in value:
                if isinstance(item, dict):
                    compacted_item = compact_object(item)
                    if not _is_empty(compacted_item):
                        items.append(compacted_item)
                elif not _is_empty(item):
                    items.append(item)
            if items:
                out[key] = items
            continue
        if not _is_empty(value):
            out[key] = value
    return out


def build_layout_payload(raw_values: Mapping[str, Any]) -> dict[str, Any]:
    """Build compact top-level layout payload from raw form values."""
    payload: dict[str, Any] = {}
    for key in LAYOUT_SUPPORTED_KEYS:
        raw = raw_values.get(key)
        if raw is None:
            continue

        if key in LAYOUT_NUMERIC_KEYS:
            parsed = _parse_number(raw)
            if parsed is not None:
                payload[key] = parsed
            continue

        if key in LAYOUT_BOOLEAN_KEYS:
            parsed = _parse_bool(raw)
            if parsed is not None:
                payload[key] = parsed
            continue

        if key == "output":
            if isinstance(raw, list):
                values = [str(v).strip() for v in raw if str(v).strip()]
            else:
                values = [
                    token.strip()
                    for token in str(raw).split(",")
                    if token.strip()
                ]
            if len(values) == 1:
                payload[key] = values[0]
            elif len(values) > 1:
                payload[key] = values
            continue

        if isinstance(raw, str):
            stripped = raw.strip()
            if stripped:
                payload[key] = stripped
        elif not _is_empty(raw):
            payload[key] = raw

    return compact_object(payload)


def extract_module_buckets(data: Mapping[str, Any]) -> dict[str, list[str]]:
    """Return module arrays grouped by alignment keys."""
    buckets: dict[str, list[str]] = {key: [] for key in ALIGN_KEYS}
    for key in ALIGN_KEYS:
        raw = data.get(key, [])
        if isinstance(raw, list):
            buckets[key] = [str(item).strip() for item in raw if str(item).strip()]
        elif isinstance(raw, str):
            stripped = raw.strip()
            if stripped:
                buckets[key] = [stripped]
    return buckets
