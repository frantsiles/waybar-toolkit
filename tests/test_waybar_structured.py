from __future__ import annotations

from waybar_toolkit.waybar.structured import (
    ALIGN_KEYS,
    build_layout_payload,
    build_module_catalog,
    extract_module_buckets,
)


def test_build_layout_payload_drops_empty_values() -> None:
    payload = build_layout_payload(
        {
            "layer": "top",
            "position": "  ",
            "mode": "",
            "height": "30",
            "spacing": "",
            "margin-top": "5",
            "margin-right": "0",
            "margin-bottom": "",
            "margin-left": "",
            "fixed-center": "true",
            "reload_style_on_change": "",
            "output": "HDMI-A-1, DP-1",
            "name": "main",
        }
    )

    assert payload["layer"] == "top"
    assert payload["height"] == 30
    assert payload["margin-top"] == 5
    assert payload["margin-right"] == 0
    assert payload["fixed-center"] is True
    assert payload["output"] == ["HDMI-A-1", "DP-1"]
    assert "position" not in payload
    assert "mode" not in payload
    assert "spacing" not in payload
    assert "reload_style_on_change" not in payload


def test_extract_module_buckets_normalizes_string_and_list() -> None:
    buckets = extract_module_buckets(
        {
            "modules-left": ["workspaces", " "],
            "modules-center": "clock",
            "modules-right": ["pulseaudio", "network"],
        }
    )

    assert buckets["modules-left"] == ["workspaces"]
    assert buckets["modules-center"] == ["clock"]
    assert buckets["modules-right"] == ["pulseaudio", "network"]
    assert tuple(buckets.keys()) == ALIGN_KEYS


def test_build_module_catalog_includes_known_and_existing_custom_keys() -> None:
    catalog = build_module_catalog(
        {
            "modules-left": ["custom/stats", "clock"],
            "modules-center": ["window"],
            "custom/stats": {"exec": "foo"},
            "group/power": {},
        }
    )

    assert "clock" in catalog
    assert "window" in catalog
    assert "custom/stats" in catalog
    assert "group/power" in catalog
