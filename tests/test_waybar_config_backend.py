from __future__ import annotations

from pathlib import Path

from waybar_toolkit.waybar.config_backend import WaybarConfigManager


def test_load_jsonc_with_comments_and_trailing_commas(tmp_path: Path) -> None:
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
    manager = WaybarConfigManager(config_path=config, backup_dir=tmp_path / "b")

    data = manager.load()

    assert data["modules-right"] == ["clock", "cpu"]
    assert data["custom/toolkit"]["format"] == "🔧"


def test_set_node_value_and_save(tmp_path: Path) -> None:
    config = tmp_path / "config.jsonc"
    config.write_text('{"a": 1}', encoding="utf-8")
    manager = WaybarConfigManager(config_path=config, backup_dir=tmp_path / "b")
    manager.load()

    manager.set_node_value("a", {"x": True, "n": 2})
    manager.save()

    reloaded = WaybarConfigManager(config_path=config, backup_dir=tmp_path / "b")
    data = reloaded.load()
    assert data["a"] == {"x": True, "n": 2}


def test_backup_and_restore(tmp_path: Path) -> None:
    config = tmp_path / "config.jsonc"
    backups = tmp_path / "backups"
    config.write_text('{"v": 1}', encoding="utf-8")
    manager = WaybarConfigManager(config_path=config, backup_dir=backups)

    backup = manager.backup_now()
    assert backup.exists()

    config.write_text('{"v": 99}', encoding="utf-8")
    manager.restore_backup(backup.name)

    assert config.read_text(encoding="utf-8") == '{"v": 1}'
