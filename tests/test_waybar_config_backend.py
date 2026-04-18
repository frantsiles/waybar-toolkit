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


def test_load_multibar_config_and_switch_active_bar(tmp_path: Path) -> None:
    config = tmp_path / "config.jsonc"
    config.write_text(
        """[
  {"name": "primary", "layer": "top"},
  {"name": "secondary", "layer": "bottom"}
]
""",
        encoding="utf-8",
    )
    manager = WaybarConfigManager(config_path=config, backup_dir=tmp_path / "b")

    first = manager.load()
    assert first["name"] == "primary"
    assert manager.bar_count == 2
    assert manager.active_bar_index == 0

    manager.set_active_bar_index(1)
    second = manager.get_active_bar_data()
    assert second["name"] == "secondary"
    assert manager.active_bar_index == 1


def test_save_updates_only_selected_bar_in_multibar_config(tmp_path: Path) -> None:
    config = tmp_path / "config.jsonc"
    config.write_text(
        """[
  {"name": "primary", "modules-right": ["clock"]},
  {"name": "secondary", "modules-right": ["cpu"]}
]
""",
        encoding="utf-8",
    )
    manager = WaybarConfigManager(config_path=config, backup_dir=tmp_path / "b")
    manager.load()
    manager.set_active_bar_index(1)
    manager.set_node_value("modules-right", ["cpu", "memory"])
    manager.save()

    reloaded = WaybarConfigManager(config_path=config, backup_dir=tmp_path / "b")
    bar_zero = reloaded.load()
    assert bar_zero["modules-right"] == ["clock"]
    reloaded.set_active_bar_index(1)
    bar_one = reloaded.get_active_bar_data()
    assert bar_one["modules-right"] == ["cpu", "memory"]

def test_delete_node_removes_key_from_saved_config(tmp_path: Path) -> None:
    config = tmp_path / "config.jsonc"
    config.write_text(
        """{
  "layer": "top",
  "modules-right": ["clock"],
  "position": "top"
}
""",
        encoding="utf-8",
    )
    manager = WaybarConfigManager(config_path=config, backup_dir=tmp_path / "bk")
    manager.load()

    manager.delete_node("modules-right")
    manager.save()

    reloaded = WaybarConfigManager(config_path=config, backup_dir=tmp_path / "bk")
    data = reloaded.load()
    assert "modules-right" not in data
    assert data["layer"] == "top"


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


def test_save_rewrites_json_without_comments(tmp_path: Path) -> None:
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
    assert "// global comment" not in saved
    assert "/* keep block */" not in saved
    assert "// keep-inline" not in saved
    assert '"layer": "top"' in saved
    assert '"on-click": "waybar-toolkit --waybar"' in saved

    reloaded = WaybarConfigManager(config_path=config, backup_dir=tmp_path / "b")
    data = reloaded.load()
    assert data["custom/toolkit"]["format"] == "🧩"
    assert data["custom/toolkit"]["on-click"] == "waybar-toolkit --waybar"

def test_save_removes_comments_between_value_and_comma(tmp_path: Path) -> None:
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
    assert "/* keep-this-comment */" not in saved


def test_save_allows_new_top_level_keys(tmp_path: Path) -> None:
    config = tmp_path / "config.jsonc"
    config.write_text(
        """{
    // initial comment
    "layer": "top"
}
""",
        encoding="utf-8",
    )
    manager = WaybarConfigManager(config_path=config, backup_dir=tmp_path / "b")
    manager.load()

    manager.set_node_value("modules-right", ["clock", "cpu"])
    manager.save()

    reloaded = WaybarConfigManager(config_path=config, backup_dir=tmp_path / "b")
    data = reloaded.load()
    assert data["layer"] == "top"
    assert data["modules-right"] == ["clock", "cpu"]


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
