"""Tests for the new WaybarConfig backend."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from waybar_toolkit.waybar.config_backend import WaybarConfig, WaybarConfigError


# ------------------------------------------------------------------
# Parsing
# ------------------------------------------------------------------


def test_load_jsonc_strips_comments_and_trailing_commas(tmp_path: Path) -> None:
    config = tmp_path / "config.jsonc"
    config.write_text(
        """
        {
          // modules
          "modules-right": ["clock", "cpu",],
          "custom/toolkit": {
            "format": "🔧", /* icon */
          },
        }
        """,
        encoding="utf-8",
    )
    cfg = WaybarConfig(config)
    assert cfg.get_modules("modules-right") == ["clock", "cpu"]


def test_load_multibar_config(tmp_path: Path) -> None:
    config = tmp_path / "config.jsonc"
    config.write_text(
        '[{"name": "primary"}, {"name": "secondary"}]',
        encoding="utf-8",
    )
    cfg = WaybarConfig(config)
    assert cfg.bar_count == 2
    assert cfg.bar_names == ["primary", "secondary"]


def test_select_bar_switches_active(tmp_path: Path) -> None:
    config = tmp_path / "config.jsonc"
    config.write_text(
        '[{"modules-left": ["a"]}, {"modules-left": ["b"]}]',
        encoding="utf-8",
    )
    cfg = WaybarConfig(config)
    assert cfg.get_modules("modules-left") == ["a"]
    cfg.select_bar(1)
    assert cfg.get_modules("modules-left") == ["b"]


def test_load_raises_on_bad_json(tmp_path: Path) -> None:
    config = tmp_path / "config.jsonc"
    config.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(WaybarConfigError):
        WaybarConfig(config)


def test_load_raises_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(WaybarConfigError):
        WaybarConfig(tmp_path / "nonexistent.jsonc")


# ------------------------------------------------------------------
# Module operations
# ------------------------------------------------------------------


def test_get_modules_returns_list_for_string_value(tmp_path: Path) -> None:
    config = tmp_path / "config.jsonc"
    config.write_text('{"modules-left": "clock"}', encoding="utf-8")
    cfg = WaybarConfig(config)
    assert cfg.get_modules("modules-left") == ["clock"]


def test_get_modules_returns_empty_for_missing_key(tmp_path: Path) -> None:
    config = tmp_path / "config.jsonc"
    config.write_text("{}", encoding="utf-8")
    cfg = WaybarConfig(config)
    assert cfg.get_modules("modules-left") == []


def test_set_modules_updates_in_memory(tmp_path: Path) -> None:
    config = tmp_path / "config.jsonc"
    config.write_text('{"modules-left": ["clock"]}', encoding="utf-8")
    cfg = WaybarConfig(config)
    cfg.set_modules("modules-left", ["clock", "memory"])
    assert cfg.get_modules("modules-left") == ["clock", "memory"]


# ------------------------------------------------------------------
# Save / backup / restore
# ------------------------------------------------------------------


def test_save_writes_correct_json(tmp_path: Path) -> None:
    config = tmp_path / "config.jsonc"
    config.write_text('{"modules-left": ["clock"]}', encoding="utf-8")
    cfg = WaybarConfig(config)
    cfg.set_modules("modules-left", ["clock", "cpu"])
    cfg.save()

    data = json.loads(config.read_text(encoding="utf-8"))
    assert data["modules-left"] == ["clock", "cpu"]


def test_save_creates_backup(tmp_path: Path) -> None:
    config = tmp_path / "config.jsonc"
    config.write_text('{"modules-left": []}', encoding="utf-8")
    cfg = WaybarConfig(config)
    backup = cfg.save()
    assert backup.exists()
    assert backup.parent.name == "backups"


def test_save_is_atomic_on_error(tmp_path: Path) -> None:
    """No tmp file should remain if write fails."""
    config = tmp_path / "config.jsonc"
    config.write_text("{}", encoding="utf-8")
    cfg = WaybarConfig(config)
    # Make parent read-only to force failure
    config.parent.chmod(0o555)
    try:
        with pytest.raises(Exception):
            cfg.save()
        tmps = list(tmp_path.glob("*.tmp"))
        assert tmps == [], f"Leaked tmp files: {tmps}"
    finally:
        config.parent.chmod(0o755)


def test_save_preserves_other_keys(tmp_path: Path) -> None:
    config = tmp_path / "config.jsonc"
    config.write_text(
        '{"layer": "top", "modules-left": ["clock"]}', encoding="utf-8"
    )
    cfg = WaybarConfig(config)
    cfg.set_modules("modules-left", ["cpu"])
    cfg.save()

    data = json.loads(config.read_text(encoding="utf-8"))
    assert data["layer"] == "top"
    assert data["modules-left"] == ["cpu"]


def test_save_multibar_only_modifies_selected_bar(tmp_path: Path) -> None:
    config = tmp_path / "config.jsonc"
    config.write_text(
        '[{"modules-left": ["clock"]}, {"modules-left": ["cpu"]}]',
        encoding="utf-8",
    )
    cfg = WaybarConfig(config)
    cfg.select_bar(1)
    cfg.set_modules("modules-left", ["cpu", "memory"])
    cfg.save()

    data = json.loads(config.read_text(encoding="utf-8"))
    assert data[0]["modules-left"] == ["clock"]
    assert data[1]["modules-left"] == ["cpu", "memory"]


def test_restore_backup(tmp_path: Path) -> None:
    config = tmp_path / "config.jsonc"
    config.write_text('{"modules-left": ["clock"]}', encoding="utf-8")
    cfg = WaybarConfig(config)
    backup = cfg.save()

    # Corrupt the config
    config.write_text('{"modules-left": ["BROKEN"]}', encoding="utf-8")

    cfg.restore_backup(backup)
    data = json.loads(config.read_text(encoding="utf-8"))
    assert data["modules-left"] == ["clock"]


def test_list_backups_sorted_newest_first(tmp_path: Path) -> None:
    config = tmp_path / "config.jsonc"
    config.write_text("{}", encoding="utf-8")
    cfg = WaybarConfig(config)
    b1 = cfg.save()
    b2 = cfg.save()
    backups = cfg.list_backups()
    assert backups[0] == b2
    assert backups[1] == b1
