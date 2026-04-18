from __future__ import annotations

from waybar_toolkit.waybar.structured import (
    ALIGN_KEYS,
    build_layout_payload,
    build_module_catalog,
    build_module_inspector_payload,
    build_structured_change_summary,
    build_structured_diff_preview,
    compute_structured_changes,
    extract_module_buckets,
    filter_module_catalog,
    get_module_category,
    get_module_template,
    get_network_profile_template,
    merge_module_config_with_template,
    normalize_layout_aliases,
    validate_layout_payload,
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


def test_validate_layout_payload_reports_invalid_numeric_values() -> None:
    errors = validate_layout_payload(
        {
            "height": "abc",
            "spacing": "2px",
            "margin-top": "5",
        }
    )

    assert "'height' must be a number." in errors
    assert "'spacing' must be a number." in errors
    assert "'margin-top' must be a number." not in errors


def test_compute_structured_changes_builds_set_and_delete_lists() -> None:
    current = {
        "layer": "top",
        "height": 30,
        "modules-left": ["workspaces"],
        "modules-right": ["clock"],
    }
    layout_payload = {
        "layer": "bottom",
        "height": 32,
    }
    module_buckets = {
        "modules-left": ["workspaces", "window"],
        "modules-center": ["clock"],
        "modules-right": [],
    }

    to_set, to_delete, target_values = compute_structured_changes(
        current,
        layout_payload,
        module_buckets,
    )

    assert to_set["layer"] == "bottom"
    assert to_set["height"] == 32
    assert to_set["modules-left"] == ["workspaces", "window"]
    assert to_set["modules-center"] == ["clock"]
    assert "modules-right" in to_delete
    assert "modules-right" not in target_values


def test_normalize_layout_aliases_maps_legacy_mod_to_mode() -> None:
    payload, cleanup = normalize_layout_aliases(
        {"mod": "dock"},
        {},
    )

    assert payload["mode"] == "dock"
    assert cleanup == {"mod"}


def test_normalize_layout_aliases_prefers_existing_mode() -> None:
    payload, cleanup = normalize_layout_aliases(
        {"mod": "dock", "mode": "overlay"},
        {},
    )

    assert "mode" not in payload
    assert cleanup == {"mod"}

def test_normalize_layout_aliases_removes_invalid_legacy_mod_key() -> None:
    payload, cleanup = normalize_layout_aliases(
        {"mod": "invalid-value"},
        {},
    )

    assert payload == {}
    assert cleanup == {"mod"}


def test_build_structured_diff_preview_for_changed_fields() -> None:
    current = {
        "layer": "top",
        "height": 30,
        "modules-right": ["clock"],
    }
    target = {
        "layer": "bottom",
        "height": 30,
        "modules-center": ["clock"],
    }

    diff = build_structured_diff_preview(current, target)

    assert "--- current" in diff
    assert "+++ proposed" in diff
    assert '"layer": "top"' in diff
    assert '"layer": "bottom"' in diff
    assert '"modules-right": [' in diff
    assert '"modules-center": [' in diff


def test_build_structured_change_summary_for_non_technical_preview() -> None:
    current = {
        "layer": "top",
        "height": 30,
        "modules-right": ["clock"],
    }
    target = {
        "layer": "bottom",
        "height": 30,
        "modules-center": ["clock", "cpu"],
    }

    summary = build_structured_change_summary(current, target)

    assert "Update 'layer': top -> bottom" in summary
    assert "Remove 'modules-right'" in summary
    assert "Add 'modules-center': [clock, cpu]" in summary


def test_filter_module_catalog_by_category_and_query() -> None:
    catalog = ["clock", "cpu", "pulseaudio", "custom/stats"]

    filtered = filter_module_catalog(
        catalog,
        category="Audio",
        query="pulse",
    )

    assert filtered == ["pulseaudio"]


def test_get_module_category_and_template_for_custom_module() -> None:
    assert get_module_category("custom/stats") == "Custom"
    template = get_module_template("custom/stats")
    assert template is not None
    assert template["return-type"] == "json"


def test_get_network_profile_template() -> None:
    detailed = get_network_profile_template("detailed")
    assert detailed is not None
    assert "format-wifi" in detailed
    assert detailed["tooltip"] is True
    assert get_network_profile_template("unknown") is None


def test_build_module_inspector_payload_compacts_empty_fields() -> None:
    payload = build_module_inspector_payload(
        {
            "format": " {volume}% ",
            "tooltip": "true",
            "interval": "5",
            "tooltip-format": "",
            "on-click": "pavucontrol",
            "on-click-right": " ",
        }
    )

    assert payload["format"] == "{volume}%"
    assert payload["tooltip"] is True
    assert payload["interval"] == 5
    assert payload["on-click"] == "pavucontrol"
    assert "tooltip-format" not in payload
    assert "on-click-right" not in payload


def test_merge_module_config_with_template() -> None:
    merged = merge_module_config_with_template(
        {"tooltip": False, "format": "{value}"},
        {"tooltip": True, "interval": 5},
    )

    assert merged["format"] == "{value}"
    assert merged["tooltip"] is True
    assert merged["interval"] == 5


def test_diff_and_summary_include_extra_keys() -> None:
    current = {"layer": "top", "clock": {"format": "old"}}
    target = {"layer": "top", "clock": {"format": "new"}}

    diff = build_structured_diff_preview(
        current,
        target,
        extra_keys={"clock"},
    )
    summary = build_structured_change_summary(
        current,
        target,
        extra_keys={"clock"},
    )

    assert '"format": "old"' in diff
    assert '"format": "new"' in diff
    assert "Update 'clock'" in summary
