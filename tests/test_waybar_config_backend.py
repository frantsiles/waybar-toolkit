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


def test_set_config_path_switches_active_file(tmp_path: Path) -> None:
    config_a = tmp_path / "a.jsonc"
    config_b = tmp_path / "b.jsonc"
    config_a.write_text('{"name": "a"}', encoding="utf-8")
    config_b.write_text('{"name": "b"}', encoding="utf-8")

    manager = WaybarConfigManager(config_path=config_a, backup_dir=tmp_path / "bk")
    data_a = manager.load()
    assert data_a["name"] == "a"

    manager.set_config_path(config_b)
    data_b = manager.load()
    assert data_b["name"] == "b"
    assert manager.config_path == config_b


def test_create_new_config_at_custom_path(tmp_path: Path) -> None:
    custom = tmp_path / "nested" / "my-waybar.jsonc"
    manager = WaybarConfigManager(
        config_path=tmp_path / "unused.jsonc",
        backup_dir=tmp_path / "bk",
    )

    created = manager.create_new_config(custom)

    assert created == custom
    assert created.exists()
    assert created.read_text(encoding="utf-8") == "{\n}\n"
    assert manager.config_path == custom

def test_save_preserves_comments_and_unedited_sections(tmp_path: Path) -> None:
    config = tmp_path / "config.jsonc"
    config.write_text(
        """{
    // global comment
    "modules-right": ["clock", "cpu"], // keep-inline
    "custom/toolkit": {
        "format": "🔧"
    },
    /* keep block */
    "layer": "top"
}
""",
        encoding="utf-8",
    )
    manager = WaybarConfigManager(config_path=config, backup_dir=tmp_path / "b")
    manager.load()

    manager.set_node_value(
        "custom/toolkit",
        {
            "format": "🧩",
            "on-click": "waybar-toolkit --waybar",
        },
    )
    manager.save()

    saved = config.read_text(encoding="utf-8")
    assert "// global comment" in saved
    assert '"modules-right": ["clock", "cpu"], // keep-inline' in saved
    assert "/* keep block */" in saved
    assert '"layer": "top"' in saved

    reloaded = WaybarConfigManager(config_path=config, backup_dir=tmp_path / "b")
    data = reloaded.load()
    assert data["custom/toolkit"]["format"] == "🧩"
    assert data["custom/toolkit"]["on-click"] == "waybar-toolkit --waybar"


def test_save_preserves_comment_between_value_and_comma(tmp_path: Path) -> None:
    config = tmp_path / "config.jsonc"
    config.write_text(
        """{
    "custom/toolkit": {"format": "🔧"} /* keep-this-comment */,
    "layer": "top"
}
""",
        encoding="utf-8",
    )
    manager = WaybarConfigManager(config_path=config, backup_dir=tmp_path / "b")
    manager.load()

    manager.set_node_value("custom/toolkit", {"format": "X"})
    manager.save()

    saved = config.read_text(encoding="utf-8")
    assert "/* keep-this-comment */" in saved


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
