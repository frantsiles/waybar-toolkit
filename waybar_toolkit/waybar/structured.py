"""Helpers for structured Waybar config editing UI."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from difflib import unified_diff
from typing import Any

ALIGN_KEYS = ("modules-left", "modules-center", "modules-right")
MODULE_CATEGORY_LABELS = (
    "All",
    "Core",
    "System",
    "Connectivity",
    "Audio",
    "Custom",
    "Other",
)
KNOWN_WAYBAR_MODULES = (
    "workspaces",
    "window",
    "clock",
    "cpu",
    "memory",
    "temperature",
    "disk",
    "network",
    "pulseaudio",
    "wireplumber",
    "battery",
    "backlight",
    "bluetooth",
    "tray",
    "idle_inhibitor",
    "power-profiles-daemon",
    "keyboard-state",
    "language",
)

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
VALID_MODE_VALUES = {"dock", "hide", "invisible", "overlay"}
LAYOUT_SUPPORTED_KEYS = (
    LAYOUT_NUMERIC_KEYS | LAYOUT_BOOLEAN_KEYS | LAYOUT_TEXT_KEYS
)
STRUCTURED_EDIT_KEYS = tuple(sorted(LAYOUT_SUPPORTED_KEYS | set(ALIGN_KEYS)))
MODULE_CATEGORY_MAP = {
    "workspaces": "Core",
    "window": "Core",
    "clock": "Core",
    "tray": "Core",
    "idle_inhibitor": "Core",
    "cpu": "System",
    "memory": "System",
    "temperature": "System",
    "disk": "System",
    "battery": "System",
    "backlight": "System",
    "power-profiles-daemon": "System",
    "network": "Connectivity",
    "bluetooth": "Connectivity",
    "language": "Connectivity",
    "keyboard-state": "Connectivity",
    "pulseaudio": "Audio",
    "wireplumber": "Audio",
}
MODULE_TEMPLATES = {
    "clock": {
        "format": "{:%H:%M}",
        "tooltip-format": "{:%Y-%m-%d %H:%M}",
    },
    "network": {
        "format-wifi": "{essid} {signalStrength}%",
        "format-ethernet": "{ifname}",
        "tooltip": True,
    },
    "pulseaudio": {
        "format": "{volume}% {icon}",
        "format-muted": "muted",
        "tooltip": True,
    },
    "custom/*": {
        "exec": "echo '{\"text\":\"custom\"}'",
        "interval": 5,
        "return-type": "json",
        "tooltip": False,
    },
}


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


def normalize_layout_aliases(
    current_data: Mapping[str, Any],
    layout_payload: Mapping[str, Any],
) -> tuple[dict[str, Any], set[str]]:
    """Normalize known layout aliases and report keys that should be removed."""
    payload = dict(layout_payload)
    cleanup_keys: set[str] = set()
    current_mode = current_data.get("mode")
    has_valid_current_mode = (
        isinstance(current_mode, str)
        and current_mode.strip() in VALID_MODE_VALUES
    )
    payload_mode = payload.get("mode")
    has_valid_payload_mode = (
        isinstance(payload_mode, str)
        and payload_mode.strip() in VALID_MODE_VALUES
    )
    legacy_mode = current_data.get("mod")
    if "mod" in current_data:
        cleanup_keys.add("mod")
    if isinstance(legacy_mode, str):
        normalized_legacy = legacy_mode.strip()
        if normalized_legacy in VALID_MODE_VALUES:
            if not has_valid_payload_mode and not has_valid_current_mode:
                payload["mode"] = normalized_legacy

    return payload, cleanup_keys


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


def build_module_catalog(data: Mapping[str, Any]) -> list[str]:
    """Build module catalog from known modules plus those already present."""
    seen: set[str] = set()
    out: list[str] = []

    def add(name: str) -> None:
        module = name.strip()
        if module and module not in seen:
            seen.add(module)
            out.append(module)

    for name in KNOWN_WAYBAR_MODULES:
        add(name)

    buckets = extract_module_buckets(data)
    for key in ALIGN_KEYS:
        for name in buckets.get(key, []):
            add(name)

    for key in data.keys():
        if key in ALIGN_KEYS:
            continue
        if "/" in key:
            add(str(key))

    return out


def get_module_category(module_name: str) -> str:
    module = module_name.strip()
    if not module:
        return "Other"
    if module.startswith("custom/"):
        return "Custom"
    return MODULE_CATEGORY_MAP.get(module, "Other")


def filter_module_catalog(
    catalog: list[str],
    *,
    query: str = "",
    category: str = "All",
) -> list[str]:
    filtered: list[str] = []
    q = query.strip().lower()
    for module in catalog:
        if category != "All" and get_module_category(module) != category:
            continue
        if q and q not in module.lower():
            continue
        filtered.append(module)
    return filtered


NETWORK_PROFILE_TEMPLATES = {
    "compact": {
        "format-wifi": "{signalStrength}% {icon}",
        "format-ethernet": "{ifname}",
        "format-disconnected": "offline",
        "tooltip": False,
    },
    "detailed": {
        "format-wifi": "{essid} {signalStrength}% {icon}",
        "format-ethernet": "{ifname} {ipaddr}",
        "format-linked": "{ifname} (no IP)",
        "tooltip-format-wifi": "{essid}\\n{ipaddr}/{cidr}\\n{bandwidthUpBytes}↑ {bandwidthDownBytes}↓",
        "tooltip-format-ethernet": "{ifname}\\n{ipaddr}/{cidr}\\n{bandwidthUpBytes}↑ {bandwidthDownBytes}↓",
        "tooltip": True,
    },
    "minimal": {
        "format-wifi": "{icon}",
        "format-ethernet": "LAN",
        "format-disconnected": "×",
        "tooltip": True,
    },
}

def get_module_template(module_name: str) -> dict[str, Any] | None:
    module = module_name.strip()
    if not module:
        return None
    if module in MODULE_TEMPLATES:
        return dict(MODULE_TEMPLATES[module])
    if module.startswith("custom/"):
        return dict(MODULE_TEMPLATES["custom/*"])
    return None


def get_network_profile_template(
    profile_name: str,
) -> dict[str, Any] | None:
    profile = profile_name.strip().lower()
    template = NETWORK_PROFILE_TEMPLATES.get(profile)
    if template is None:
        return None
    return dict(template)


def normalize_module_buckets(
    buckets: Mapping[str, Any],
) -> dict[str, list[str]]:
    """Normalize module buckets into clean string lists per alignment key."""
    normalized: dict[str, list[str]] = {key: [] for key in ALIGN_KEYS}
    for align in ALIGN_KEYS:
        raw = buckets.get(align, [])
        values: list[str] = []
        if isinstance(raw, str):
            token = raw.strip()
            if token:
                values.append(token)
        elif isinstance(raw, list):
            for item in raw:
                token = str(item).strip()
                if token:
                    values.append(token)
        normalized[align] = values
    return normalized


def build_module_inspector_payload(
    raw_values: Mapping[str, Any],
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in ("format", "tooltip-format", "on-click", "on-click-right"):
        value = str(raw_values.get(key, "")).strip()
        if value:
            payload[key] = value
    tooltip = _parse_bool(raw_values.get("tooltip", ""))
    if tooltip is not None:
        payload["tooltip"] = tooltip
    interval = _parse_number(raw_values.get("interval", ""))
    if interval is not None:
        payload["interval"] = interval
    return compact_object(payload)


def merge_module_config_with_template(
    current: Mapping[str, Any] | None,
    template: Mapping[str, Any] | None,
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if current:
        merged.update(dict(current))
    if template:
        merged.update(dict(template))
    return compact_object(merged)


def validate_layout_payload(raw_values: Mapping[str, Any]) -> list[str]:
    """Return human-readable validation errors for layout form values."""
    errors: list[str] = []
    for key in sorted(LAYOUT_NUMERIC_KEYS):
        raw = raw_values.get(key, "")
        if isinstance(raw, str) and not raw.strip():
            continue
        if raw is None:
            continue
        if _parse_number(raw) is None:
            errors.append(f"'{key}' must be a number.")

    for key in sorted(LAYOUT_BOOLEAN_KEYS):
        raw = raw_values.get(key, "")
        if isinstance(raw, str) and not raw.strip():
            continue
        if raw is None:
            continue
        if _parse_bool(raw) is None:
            errors.append(f"'{key}' must be true or false.")
    return errors


def compute_structured_changes(
    current_data: Mapping[str, Any],
    layout_payload: Mapping[str, Any],
    module_buckets: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str], dict[str, Any]]:
    """Compute top-level set/delete operations and full target values."""
    target_values: dict[str, Any] = dict(layout_payload)
    normalized_buckets = normalize_module_buckets(module_buckets)
    for align in ALIGN_KEYS:
        items = normalized_buckets.get(align, [])
        if items:
            target_values[align] = items

    to_set: dict[str, Any] = {}
    to_delete: list[str] = []
    for key in STRUCTURED_EDIT_KEYS:
        has_current = key in current_data
        has_target = key in target_values
        if has_target:
            new_value = target_values[key]
            if not has_current or current_data[key] != new_value:
                to_set[key] = new_value
            continue
        if has_current:
            to_delete.append(key)

    return to_set, to_delete, target_values

def collect_change_keys(
    current_data: Mapping[str, Any],
    target_values: Mapping[str, Any],
    *,
    extra_keys: set[str] | None = None,
) -> list[str]:
    keys = set(STRUCTURED_EDIT_KEYS)
    if extra_keys:
        keys.update(extra_keys)
    return [
        key
        for key in sorted(keys)
        if (key in current_data) != (key in target_values)
        or (
            key in current_data
            and key in target_values
            and current_data[key] != target_values[key]
        )
    ]


def build_structured_diff_preview(
    current_data: Mapping[str, Any],
    target_values: Mapping[str, Any],
    *,
    extra_keys: set[str] | None = None,
) -> str:
    """Build unified diff for structured top-level keys."""
    changed_keys = collect_change_keys(
        current_data,
        target_values,
        extra_keys=extra_keys,
    )
    if not changed_keys:
        return ""

    before = {
        key: current_data[key] for key in changed_keys if key in current_data
    }
    after = {
        key: target_values[key] for key in changed_keys if key in target_values
    }
    before_text = json.dumps(before, ensure_ascii=False, indent=2, sort_keys=True)
    after_text = json.dumps(after, ensure_ascii=False, indent=2, sort_keys=True)
    return "\n".join(
        unified_diff(
            before_text.splitlines(),
            after_text.splitlines(),
            fromfile="current",
            tofile="proposed",
            lineterm="",
        )
    )


def _preview_change_value(value: Any) -> str:
    if isinstance(value, list):
        items = [str(item) for item in value]
        if not items:
            return "[]"
        if len(items) <= 4:
            return "[" + ", ".join(items) + "]"
        shown = ", ".join(items[:3])
        return f"[{shown}, … +{len(items) - 3} more]"
    if isinstance(value, dict):
        keys = list(value.keys())
        if not keys:
            return "{}"
        if len(keys) <= 3:
            return "{ " + ", ".join(str(key) for key in keys) + " }"
        return "{ " + ", ".join(str(key) for key in keys[:3]) + ", … }"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def build_structured_change_summary(
    current_data: Mapping[str, Any],
    target_values: Mapping[str, Any],
    *,
    extra_keys: set[str] | None = None,
) -> str:
    """Build a human-readable summary of structured key changes."""
    lines: list[str] = []
    changed_keys = collect_change_keys(
        current_data,
        target_values,
        extra_keys=extra_keys,
    )
    for key in changed_keys:
        has_current = key in current_data
        has_target = key in target_values
        if not has_current and not has_target:
            continue
        if has_current and not has_target:
            previous = _preview_change_value(current_data[key])
            lines.append(f"• Remove '{key}' (was: {previous})")
            continue
        if not has_current and has_target:
            new_value = _preview_change_value(target_values[key])
            lines.append(f"• Add '{key}': {new_value}")
            continue
        old_value = current_data[key]
        new_value = target_values[key]
        if old_value != new_value:
            old_preview = _preview_change_value(old_value)
            new_preview = _preview_change_value(new_value)
            lines.append(
                f"• Update '{key}': {old_preview} -> {new_preview}"
            )
    return "\n".join(lines)
