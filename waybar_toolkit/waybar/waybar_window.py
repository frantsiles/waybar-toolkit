"""Waybar config visual editor window."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import gi

from waybar_toolkit.waybar.config_backend import (
    WaybarBackupError,
    WaybarConfigError,
    WaybarConfigManager,
    WaybarConfigParseError,
)
from waybar_toolkit.waybar.structured import (
    ALIGN_KEYS,
    LAYOUT_BOOLEAN_KEYS,
    MODULE_CATEGORY_LABELS,
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
    normalize_module_buckets,
    validate_layout_payload,
)

gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GObject, Gtk, Pango  # noqa: E402

CSS = """
.waybar-window {
    background-color: @window_bg_color;
    color: @window_fg_color;
}
.section-title {
    font-size: 13px;
    font-weight: bold;
    color: @window_fg_color;
}
.info-label {
    font-size: 12px;
    color: alpha(@window_fg_color, 0.55);
}
.action-button {
    padding: 6px 16px;
    border-radius: 6px;
    font-size: 12px;
}
.toolbar-button {
    background-color: @card_bg_color;
    color: @window_fg_color;
}
.toolbar-button:hover {
    background-color: lighter(@card_bg_color);
}
.status-bar {
    background-color: @headerbar_bg_color;
    padding: 4px 12px;
    font-size: 11px;
    color: alpha(@window_fg_color, 0.55);
}
.node-card {
    min-width: 220px;
    min-height: 100px;
    border-radius: 10px;
    background-color: @card_bg_color;
    padding: 10px;
}
.node-card:hover {
    background-color: lighter(@card_bg_color);
}
.node-key {
    font-size: 12px;
    font-weight: bold;
    color: @window_fg_color;
}
.node-summary {
    font-size: 11px;
    color: alpha(@window_fg_color, 0.65);
}
.structured-wrap {
    margin: 10px 12px 8px 12px;
    padding: 10px;
    border-radius: 8px;
    background-color: @card_bg_color;
}
.structured-title {
    font-size: 13px;
    font-weight: bold;
    color: @window_fg_color;
}
.module-column {
    background-color: alpha(@window_fg_color, 0.05);
    border-radius: 8px;
    padding: 8px;
}
.module-column-drop-target {
    background-color: alpha(@accent_bg_color, 0.18);
}
.module-pill {
    background-color: alpha(@accent_bg_color, 0.2);
    border-radius: 12px;
    padding: 4px 8px;
    color: @window_fg_color;
}
.module-pill-selected {
    background-color: alpha(@accent_bg_color, 0.4);
}
.module-row-selected {
    background-color: alpha(@accent_bg_color, 0.15);
    border-radius: 8px;
}
.module-trash-zone {
    background-color: alpha(#c0392b, 0.15);
    border-radius: 8px;
    padding: 6px 10px;
}
.module-trash-zone-drop-target {
    background-color: alpha(#c0392b, 0.35);
}
.module-trash-zone:hover {
    background-color: alpha(#c0392b, 0.25);
}
.inspector-wrap {
    margin-top: 8px;
}
.diff-summary-add {
    color: #2ecc71;
}
.diff-summary-update {
    color: #f1c40f;
}
.diff-summary-remove {
    color: #e74c3c;
}
.mini-button {
    min-width: 24px;
    padding: 2px 6px;
}
"""

logger = logging.getLogger(__name__)


class WaybarConfigWindow(Gtk.Window):
    """Visual editor for top-level Waybar config nodes."""

    def __init__(self, app: Gtk.Application) -> None:
        super().__init__(application=app, title="Waybar Config Manager")
        self.set_default_size(860, 620)
        self.add_css_class("waybar-window")

        self._manager = WaybarConfigManager()
        self._missing_config_prompt_open = False
        self._config_data: dict[str, Any] = {}
        self._bar_dropdown_updating = False
        self._bar_dropdown: Gtk.DropDown | None = None
        self._layout_widgets: dict[str, Any] = {}
        self._module_buckets: dict[str, list[str]] = {
            key: [] for key in ALIGN_KEYS
        }
        self._module_boxes: dict[str, Gtk.Box] = {}
        self._module_columns: dict[str, Gtk.Box] = {}
        self._module_catalog_all: list[str] = []
        self._module_category_dropdown: Gtk.DropDown | None = None
        self._module_search_entry: Gtk.Entry | None = None
        self._module_new_entry: Gtk.Entry | None = None
        self._module_catalog_dropdown: Gtk.DropDown | None = None
        self._module_target_dropdown: Gtk.DropDown | None = None
        self._module_selected_name: str | None = None
        self._module_selected_align: str | None = None
        self._module_selected_index: int = -1
        self._module_overrides: dict[str, dict[str, Any]] = {}
        self._module_inspector_widgets: dict[str, Gtk.Widget] = {}
        self._module_inspector_title: Gtk.Label | None = None
        self._network_profile_dropdown: Gtk.DropDown | None = None
        self._module_trash_zone: Gtk.Box | None = None
        self._drag_source_align: str | None = None
        self._drag_source_index: int = -1

        css_provider = Gtk.CssProvider()
        css_provider.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_child(main_box)

        toolbar = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
            margin_start=12,
            margin_end=12,
            margin_top=8,
            margin_bottom=8,
        )
        main_box.append(toolbar)

        title = Gtk.Label(label="Waybar config nodes")
        title.add_css_class("section-title")
        toolbar.append(title)

        self._path_label = Gtk.Label(label=str(self._manager.config_path))
        self._path_label.add_css_class("info-label")
        self._path_label.set_xalign(0)
        self._path_label.set_hexpand(True)
        self._path_label.set_ellipsize(Pango.EllipsizeMode.END)
        toolbar.append(self._path_label)

        bar_label = Gtk.Label(label="Bar")
        bar_label.add_css_class("info-label")
        toolbar.append(bar_label)
        self._bar_dropdown = Gtk.DropDown.new_from_strings(["bar[0]"])
        self._bar_dropdown.connect("notify::selected", self._on_bar_changed)
        toolbar.append(self._bar_dropdown)

        open_btn = Gtk.Button(label="📄 Open config")
        open_btn.add_css_class("action-button")
        open_btn.add_css_class("toolbar-button")
        open_btn.connect("clicked", self._on_open_config)
        toolbar.append(open_btn)

        new_btn = Gtk.Button(label="🆕 New config")
        new_btn.add_css_class("action-button")
        new_btn.add_css_class("toolbar-button")
        new_btn.connect("clicked", self._on_new_config)
        toolbar.append(new_btn)

        backup_btn = Gtk.Button(label="💾 Backup")
        backup_btn.add_css_class("action-button")
        backup_btn.add_css_class("toolbar-button")
        backup_btn.connect("clicked", self._on_backup)
        toolbar.append(backup_btn)

        self._backup_dropdown = Gtk.DropDown.new_from_strings(["(none)"])
        self._backup_dropdown.set_size_request(210, -1)
        toolbar.append(self._backup_dropdown)

        restore_btn = Gtk.Button(label="📂 Load backup")
        restore_btn.add_css_class("action-button")
        restore_btn.add_css_class("toolbar-button")
        restore_btn.connect("clicked", self._on_restore_backup)
        toolbar.append(restore_btn)

        refresh_btn = Gtk.Button(label="↻ Refresh")
        refresh_btn.add_css_class("action-button")
        refresh_btn.add_css_class("toolbar-button")
        refresh_btn.connect("clicked", lambda *_: self._reload_nodes())
        toolbar.append(refresh_btn)

        apply_structured_btn = Gtk.Button(label="✔ Apply structured")
        apply_structured_btn.add_css_class("action-button")
        apply_structured_btn.add_css_class("toolbar-button")
        apply_structured_btn.connect("clicked", self._on_apply_structured)
        toolbar.append(apply_structured_btn)

        main_box.append(Gtk.Separator())

        content_scroll = Gtk.ScrolledWindow()
        content_scroll.set_policy(
            Gtk.PolicyType.AUTOMATIC,
            Gtk.PolicyType.AUTOMATIC,
        )
        content_scroll.set_vexpand(True)
        main_box.append(content_scroll)

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        content_scroll.set_child(content_box)

        self._build_structured_editor(content_box)
        content_box.append(Gtk.Separator())

        advanced_label = Gtk.Label(label="Advanced node editor")
        advanced_label.add_css_class("info-label")
        advanced_label.set_margin_start(12)
        advanced_label.set_margin_top(8)
        advanced_label.set_halign(Gtk.Align.START)
        content_box.append(advanced_label)

        self._nodes_flow = Gtk.FlowBox()
        self._nodes_flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self._nodes_flow.set_max_children_per_line(3)
        self._nodes_flow.set_min_children_per_line(1)
        self._nodes_flow.set_row_spacing(10)
        self._nodes_flow.set_column_spacing(10)
        self._nodes_flow.set_margin_start(12)
        self._nodes_flow.set_margin_end(12)
        self._nodes_flow.set_margin_top(12)
        self._nodes_flow.set_margin_bottom(12)
        self._nodes_flow.set_halign(Gtk.Align.FILL)
        self._nodes_flow.set_hexpand(True)
        content_box.append(self._nodes_flow)

        main_box.append(Gtk.Separator())
        self._status = Gtk.Label(label="Ready")
        self._status.add_css_class("status-bar")
        self._status.set_halign(Gtk.Align.START)
        self._status.set_hexpand(True)
        main_box.append(self._status)

        self._refresh_backups()
        self._reload_nodes()

        key_controller = Gtk.EventControllerKey.new()
        key_controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_controller)

    def _reload_nodes(self) -> None:
        self._clear_flow()
        if not self._manager.config_path.exists():
            self._config_data = {}
            self._module_overrides = {}
            self._module_selected_name = None
            if self._bar_dropdown:
                self._bar_dropdown_updating = True
                self._bar_dropdown.set_model(Gtk.StringList.new(["bar[0]"]))
                self._bar_dropdown.set_selected(0)
                self._bar_dropdown.set_sensitive(False)
                self._bar_dropdown_updating = False
            self._clear_structured_editor()
            self._set_status(
                "Waybar config not found. Open an existing file or create a new one."
            )
            self._refresh_path_label()
            self._refresh_backups()
            if not self._missing_config_prompt_open:
                self._show_missing_config_prompt()
            return
        self._missing_config_prompt_open = False
        try:
            data = self._manager.load()
            self._config_data = data
            self._module_overrides = {}
            self._module_selected_name = None
            self._refresh_bar_selector()
            self._load_structured_editor(data)
            for key, value in data.items():
                self._nodes_flow.append(self._make_node_card(key, value))
            self._refresh_path_label()
            bar_msg = (
                f"bar[{self._manager.active_bar_index}]"
                if self._manager.bar_count > 1
                else "single bar"
            )
            self._set_status(f"{len(data)} node(s) loaded ({bar_msg})")
        except WaybarConfigError as exc:
            self._set_status(str(exc))
        except Exception:
            logger.exception("Unexpected error loading Waybar config")
            self._set_status("Unexpected error loading Waybar config")

    def _refresh_bar_selector(self) -> None:
        if not self._bar_dropdown:
            return
        count = max(1, self._manager.bar_count)
        labels = [f"bar[{idx}]" for idx in range(count)]
        self._bar_dropdown_updating = True
        self._bar_dropdown.set_model(Gtk.StringList.new(labels))
        selected = min(self._manager.active_bar_index, count - 1)
        self._bar_dropdown.set_selected(selected)
        self._bar_dropdown.set_sensitive(count > 1)
        self._bar_dropdown_updating = False

    def _on_bar_changed(self, dropdown: Gtk.DropDown, *_args) -> None:
        if self._bar_dropdown_updating:
            return
        idx = dropdown.get_selected()
        if idx == self._manager.active_bar_index:
            return
        try:
            self._manager.set_active_bar_index(idx)
            self._reload_nodes()
        except WaybarConfigError as exc:
            self._set_status(str(exc))

    def _on_key_pressed(
        self,
        _controller: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        state: Gdk.ModifierType,
    ) -> bool:
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        alt = bool(state & Gdk.ModifierType.ALT_MASK)
        if ctrl and keyval in (Gdk.KEY_s, Gdk.KEY_S):
            self._on_apply_structured()
            return True
        if ctrl and keyval in (Gdk.KEY_r, Gdk.KEY_R):
            self._reload_nodes()
            return True
        if keyval in (Gdk.KEY_Delete, Gdk.KEY_KP_Delete):
            return self._remove_selected_module()
        if alt and keyval == Gdk.KEY_Left:
            return self._move_selected_module("left")
        if alt and keyval == Gdk.KEY_Right:
            return self._move_selected_module("right")
        if alt and keyval == Gdk.KEY_Up:
            return self._move_selected_module("up")
        if alt and keyval == Gdk.KEY_Down:
            return self._move_selected_module("down")
        return False

    def _remove_selected_module(self) -> bool:
        align = self._module_selected_align
        idx = self._module_selected_index
        if align is None or idx < 0:
            return False
        items = self._module_buckets.get(align, [])
        if not (0 <= idx < len(items)):
            return False
        removed = items.pop(idx)
        self._set_selected_module(None, None, -1)
        self._render_module_columns()
        self._set_status(f"Removed module '{removed}'")
        return True

    def _move_selected_module(self, direction: str) -> bool:
        align = self._module_selected_align
        idx = self._module_selected_index
        if align is None or idx < 0:
            return False
        items = self._module_buckets.get(align, [])
        if not (0 <= idx < len(items)):
            return False
        module_name = items.pop(idx)
        align_order = list(ALIGN_KEYS)
        target_align = align
        target_idx = idx
        if direction == "up":
            target_idx = max(0, idx - 1)
        elif direction == "down":
            target_idx = min(len(items), idx + 1)
        elif direction == "left":
            target_align = align_order[max(0, align_order.index(align) - 1)]
            target_items = self._module_buckets[target_align]
            target_idx = min(idx, len(target_items))
        elif direction == "right":
            target_align = align_order[
                min(len(align_order) - 1, align_order.index(align) + 1)
            ]
            target_items = self._module_buckets[target_align]
            target_idx = min(idx, len(target_items))
        else:
            items.insert(idx, module_name)
            return False

        destination = self._module_buckets[target_align]
        destination.insert(target_idx, module_name)
        self._set_selected_module(target_align, module_name, target_idx)
        self._render_module_columns()
        return True

    def _on_module_filter_changed(self, *_args) -> None:
        self._refresh_module_catalog(self._config_data)

    def _get_selected_module_category(self) -> str:
        if not self._module_category_dropdown:
            return "All"
        idx = self._module_category_dropdown.get_selected()
        if idx < 0 or idx >= len(MODULE_CATEGORY_LABELS):
            return "All"
        return MODULE_CATEGORY_LABELS[idx]

    @staticmethod
    def _module_name_from_catalog_option(option: str) -> str:
        if " — " in option:
            return option.split(" — ", 1)[0].strip()
        return option.strip()

    def _read_module_config(self, module_name: str) -> dict[str, Any]:
        if module_name in self._module_overrides:
            return dict(self._module_overrides[module_name])
        value = self._config_data.get(module_name)
        if isinstance(value, dict):
            return dict(value)
        return {}

    def _on_apply_module_template(self, *_args) -> None:
        module_name = self._module_selected_name or ""
        if not module_name and self._module_new_entry:
            module_name = self._module_new_entry.get_text().strip()
        if not module_name and self._module_catalog_dropdown:
            selected = self._get_dropdown_value(self._module_catalog_dropdown)
            module_name = self._module_name_from_catalog_option(selected)
        if not module_name:
            self._set_status("Select or type a module first")
            return
        template = get_module_template(module_name)
        if not template:
            self._set_status(f"No template available for '{module_name}'")
            return
        current = self._read_module_config(module_name)
        merged = merge_module_config_with_template(current, template)
        self._module_overrides[module_name] = merged
        if self._module_selected_name == module_name:
            self._populate_module_inspector(module_name)
        self._set_status(f"Template applied to '{module_name}'")

    def _on_apply_network_profile(self, *_args) -> None:
        module_name = self._module_selected_name
        if not module_name:
            self._set_status("Select a module first")
            return
        if module_name != "network":
            self._set_status(
                "Network profiles only apply to 'network' module"
            )
            return
        if not self._network_profile_dropdown:
            return
        selected = self._get_dropdown_value(self._network_profile_dropdown)
        profile = selected.strip().lower()
        if profile.startswith("("):
            self._set_status("Select a network profile first")
            return
        template = get_network_profile_template(profile)
        if not template:
            self._set_status(f"Unknown network profile: {selected}")
            return
        current = self._read_module_config(module_name)
        merged = merge_module_config_with_template(current, template)
        self._module_overrides[module_name] = merged
        self._populate_module_inspector(module_name)
        self._set_status(
            f"Network profile '{profile}' applied to '{module_name}'"
        )

    def _collect_module_inspector_values(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for key, widget in self._module_inspector_widgets.items():
            if isinstance(widget, Gtk.Entry):
                values[key] = widget.get_text()
            elif isinstance(widget, Gtk.DropDown):
                values[key] = self._get_dropdown_value(widget)
        return values

    def _on_apply_module_inspector(self, *_args) -> None:
        module_name = self._module_selected_name
        if not module_name:
            self._set_status("Select a module first")
            return
        raw_values = self._collect_module_inspector_values()
        payload = build_module_inspector_payload(raw_values)
        self._module_overrides[module_name] = payload
        self._set_status(f"Inspector updated for '{module_name}'")

    def _set_selected_module(
        self,
        align: str | None,
        module_name: str | None,
        index: int,
    ) -> None:
        self._module_selected_align = align
        self._module_selected_name = module_name
        self._module_selected_index = index
        self._populate_module_inspector(module_name)

    def _populate_module_inspector(self, module_name: str | None) -> None:
        if self._module_inspector_title is None:
            return
        if not module_name:
            self._module_inspector_title.set_text(
                "Select a module to inspect"
            )
            for widget in self._module_inspector_widgets.values():
                if isinstance(widget, Gtk.Entry):
                    widget.set_text("")
                elif isinstance(widget, Gtk.DropDown):
                    widget.set_selected(0)
            return
        self._module_inspector_title.set_text(
            f"Inspecting: {module_name} ({get_module_category(module_name)})"
        )
        payload = self._read_module_config(module_name)
        for key, widget in self._module_inspector_widgets.items():
            value = payload.get(key)
            if isinstance(widget, Gtk.Entry):
                widget.set_text("" if value is None else str(value))
            elif isinstance(widget, Gtk.DropDown):
                if value is True:
                    self._set_dropdown_value(widget, "true")
                elif value is False:
                    self._set_dropdown_value(widget, "false")
                else:
                    self._set_dropdown_value(widget, "")

    def _on_module_row_pressed(
        self,
        _gesture: Gtk.GestureClick,
        _n_press: int,
        _x: float,
        _y: float,
        align: str,
        index: int,
        module_name: str,
    ) -> None:
        self._set_selected_module(align, module_name, index)
        self._render_module_columns()

    def _on_drop_target_enter(
        self,
        _target: Gtk.DropTarget,
        _x: float,
        _y: float,
        widget: Gtk.Widget,
        css_class: str,
    ) -> Gdk.DragAction:
        widget.add_css_class(css_class)
        return Gdk.DragAction.MOVE

    def _on_drop_target_leave(
        self,
        _target: Gtk.DropTarget,
        widget: Gtk.Widget,
        css_class: str,
    ) -> None:
        widget.remove_css_class(css_class)

    def _build_structured_editor(self, parent: Gtk.Box) -> None:
        wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        wrap.add_css_class("structured-wrap")
        parent.append(wrap)

        title = Gtk.Label(label="Structured editor")
        title.add_css_class("structured-title")
        title.set_halign(Gtk.Align.START)
        wrap.append(title)

        hint = Gtk.Label(
            label=(
                "Edit common Waybar options with forms and module pills. "
                "Empty fields are removed when saving."
            )
        )
        hint.add_css_class("info-label")
        hint.set_halign(Gtk.Align.START)
        hint.set_xalign(0)
        hint.set_wrap(True)
        hint.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        wrap.append(hint)

        layout_frame = Gtk.Frame(label="Layout")
        wrap.append(layout_frame)

        layout_grid = Gtk.Grid(
            column_spacing=12,
            row_spacing=8,
            margin_start=10,
            margin_end=10,
            margin_top=10,
            margin_bottom=10,
        )
        layout_frame.set_child(layout_grid)

        row = 0
        for _key, label_text, widget in self._build_layout_widgets():
            label = Gtk.Label(label=label_text)
            label.add_css_class("info-label")
            label.set_halign(Gtk.Align.END)
            layout_grid.attach(label, 0, row, 1, 1)
            layout_grid.attach(widget, 1, row, 1, 1)
            row += 1

        modules_frame = Gtk.Frame(label="Modules")
        wrap.append(modules_frame)

        modules_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8,
            margin_start=10,
            margin_end=10,
            margin_top=10,
            margin_bottom=10,
        )
        modules_frame.set_child(modules_box)

        modules_hint = Gtk.Label(
            label=(
                "Drag and drop module pills to reorder or move between left/center/right."
            )
        )
        modules_hint.add_css_class("info-label")
        modules_hint.set_halign(Gtk.Align.START)
        modules_hint.set_xalign(0)
        modules_hint.set_wrap(True)
        modules_hint.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        modules_box.append(modules_hint)

        filter_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        modules_box.append(filter_row)

        self._module_category_dropdown = Gtk.DropDown.new_from_strings(
            list(MODULE_CATEGORY_LABELS)
        )
        self._module_category_dropdown.connect(
            "notify::selected",
            self._on_module_filter_changed,
        )
        filter_row.append(self._module_category_dropdown)

        self._module_search_entry = Gtk.Entry()
        self._module_search_entry.set_hexpand(True)
        self._module_search_entry.set_placeholder_text(
            "Search modules..."
        )
        self._module_search_entry.connect(
            "changed",
            self._on_module_filter_changed,
        )
        filter_row.append(self._module_search_entry)

        trash_zone = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        trash_zone.add_css_class("module-trash-zone")
        trash_zone.set_halign(Gtk.Align.FILL)
        trash_zone.set_hexpand(True)
        self._module_trash_zone = trash_zone
        trash_label = Gtk.Label(label="🗑 Drop here to remove module")
        trash_label.add_css_class("section-title")
        trash_label.set_halign(Gtk.Align.CENTER)
        trash_label.set_hexpand(True)
        trash_zone.append(trash_label)
        trash_target = Gtk.DropTarget.new(
            GObject.TYPE_STRING,
            Gdk.DragAction.MOVE,
        )
        trash_target.connect(
            "enter",
            self._on_drop_target_enter,
            trash_zone,
            "module-trash-zone-drop-target",
        )
        trash_target.connect(
            "leave",
            self._on_drop_target_leave,
            trash_zone,
            "module-trash-zone-drop-target",
        )
        trash_target.connect("drop", self._on_module_drop_on_trash)
        trash_zone.add_controller(trash_target)
        modules_box.append(trash_zone)

        add_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        modules_box.append(add_row)

        self._module_catalog_dropdown = Gtk.DropDown.new_from_strings(
            ["(existing module)"]
        )
        self._module_catalog_dropdown.set_hexpand(True)
        add_row.append(self._module_catalog_dropdown)

        self._module_new_entry = Gtk.Entry()
        self._module_new_entry.set_hexpand(True)
        self._module_new_entry.set_placeholder_text(
            "or custom module (e.g. custom/stats)"
        )
        self._module_new_entry.connect("activate", self._on_add_module)
        add_row.append(self._module_new_entry)

        self._module_target_dropdown = Gtk.DropDown.new_from_strings(
            list(ALIGN_KEYS)
        )
        add_row.append(self._module_target_dropdown)

        add_btn = Gtk.Button(label="Add")
        add_btn.add_css_class("toolbar-button")
        add_btn.connect("clicked", self._on_add_module)
        add_row.append(add_btn)

        template_btn = Gtk.Button(label="Apply template")
        template_btn.add_css_class("toolbar-button")
        template_btn.connect("clicked", self._on_apply_module_template)
        add_row.append(template_btn)

        columns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        modules_box.append(columns)

        for align in ALIGN_KEYS:
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            col.set_hexpand(True)
            col.add_css_class("module-column")

            col_title = Gtk.Label(label=align)
            col_title.add_css_class("section-title")
            col_title.set_halign(Gtk.Align.START)
            col.append(col_title)

            rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            drop_target = Gtk.DropTarget.new(
                GObject.TYPE_STRING,
                Gdk.DragAction.MOVE,
            )
            drop_target.connect(
                "enter",
                self._on_drop_target_enter,
                col,
                "module-column-drop-target",
            )
            drop_target.connect(
                "leave",
                self._on_drop_target_leave,
                col,
                "module-column-drop-target",
            )
            drop_target.connect(
                "drop",
                self._on_module_drop_on_column,
                align,
            )
            rows.add_controller(drop_target)
            col.append(rows)
            columns.append(col)
            self._module_boxes[align] = rows
            self._module_columns[align] = col

        inspector = Gtk.Frame(label="Module inspector")
        inspector.add_css_class("inspector-wrap")
        modules_box.append(inspector)

        inspector_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8,
            margin_start=8,
            margin_end=8,
            margin_top=8,
            margin_bottom=8,
        )
        inspector.set_child(inspector_box)

        self._module_inspector_title = Gtk.Label(
            label="Select a module to inspect"
        )
        self._module_inspector_title.add_css_class("info-label")
        self._module_inspector_title.set_halign(Gtk.Align.START)
        inspector_box.append(self._module_inspector_title)

        grid = Gtk.Grid(column_spacing=10, row_spacing=6)
        inspector_box.append(grid)

        def add_inspector_entry(
            key: str,
            label_text: str,
            row: int,
        ) -> None:
            label = Gtk.Label(label=label_text)
            label.add_css_class("info-label")
            label.set_halign(Gtk.Align.END)
            entry = Gtk.Entry()
            entry.set_hexpand(True)
            grid.attach(label, 0, row, 1, 1)
            grid.attach(entry, 1, row, 1, 1)
            self._module_inspector_widgets[key] = entry

        def add_inspector_dropdown(
            key: str,
            label_text: str,
            row: int,
            options: list[str],
        ) -> None:
            label = Gtk.Label(label=label_text)
            label.add_css_class("info-label")
            label.set_halign(Gtk.Align.END)
            dropdown = Gtk.DropDown.new_from_strings(options)
            dropdown.set_hexpand(True)
            grid.attach(label, 0, row, 1, 1)
            grid.attach(dropdown, 1, row, 1, 1)
            self._module_inspector_widgets[key] = dropdown

        add_inspector_entry("format", "Format", 0)
        add_inspector_dropdown("tooltip", "Tooltip", 1, ["", "true", "false"])
        add_inspector_entry("interval", "Interval", 2)
        add_inspector_entry("tooltip-format", "Tooltip Format", 3)
        add_inspector_entry("on-click", "On Click", 4)
        add_inspector_entry("on-click-right", "On Right Click", 5)

        inspector_actions = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
            halign=Gtk.Align.END,
        )
        inspector_box.append(inspector_actions)
        self._network_profile_dropdown = Gtk.DropDown.new_from_strings(
            ["(network profile)", "compact", "detailed", "minimal"]
        )
        inspector_actions.append(self._network_profile_dropdown)

        network_profile_btn = Gtk.Button(label="Apply network profile")
        network_profile_btn.add_css_class("toolbar-button")
        network_profile_btn.connect("clicked", self._on_apply_network_profile)
        inspector_actions.append(network_profile_btn)

        inspector_apply = Gtk.Button(label="Apply inspector")
        inspector_apply.add_css_class("toolbar-button")
        inspector_apply.connect("clicked", self._on_apply_module_inspector)
        inspector_actions.append(inspector_apply)

    def _build_layout_widgets(
        self,
    ) -> list[tuple[str, str, Gtk.Widget]]:
        fields: list[tuple[str, str, Gtk.Widget]] = []

        def add_entry(key: str, label: str) -> None:
            entry = Gtk.Entry()
            entry.set_hexpand(True)
            self._layout_widgets[key] = entry
            fields.append((key, label, entry))

        def add_dropdown(
            key: str,
            label: str,
            options: list[str],
        ) -> None:
            dropdown = Gtk.DropDown.new_from_strings(options)
            dropdown.set_hexpand(True)
            self._layout_widgets[key] = dropdown
            fields.append((key, label, dropdown))

        add_entry("name", "Name")
        add_dropdown("layer", "Layer", ["", "top", "bottom", "overlay"])
        add_dropdown(
            "position",
            "Position",
            ["", "top", "bottom", "left", "right"],
        )
        add_dropdown(
            "mode",
            "Mode",
            ["", "dock", "hide", "invisible", "overlay"],
        )
        add_entry("output", "Output(s)")
        add_entry("height", "Height")
        add_entry("spacing", "Spacing")
        add_entry("margin-top", "Margin Top")
        add_entry("margin-right", "Margin Right")
        add_entry("margin-bottom", "Margin Bottom")
        add_entry("margin-left", "Margin Left")

        for key in sorted(LAYOUT_BOOLEAN_KEYS):
            label = key.replace("-", " ").title()
            add_dropdown(key, label, ["", "true", "false"])

        return fields

    def _load_structured_editor(self, data: dict[str, Any]) -> None:
        for key, widget in self._layout_widgets.items():
            value = data.get(key)
            if isinstance(widget, Gtk.Entry):
                if key == "output" and isinstance(value, list):
                    widget.set_text(", ".join(str(v) for v in value))
                elif value is None:
                    widget.set_text("")
                else:
                    widget.set_text(str(value))
            elif isinstance(widget, Gtk.DropDown):
                if key in LAYOUT_BOOLEAN_KEYS:
                    if value is True:
                        self._set_dropdown_value(widget, "true")
                    elif value is False:
                        self._set_dropdown_value(widget, "false")
                    else:
                        self._set_dropdown_value(widget, "")
                else:
                    self._set_dropdown_value(
                        widget,
                        "" if value is None else str(value),
                    )

        self._module_buckets = extract_module_buckets(data)
        self._refresh_module_catalog(data)
        self._render_module_columns()
        self._set_selected_module(None, None, -1)

    def _clear_structured_editor(self) -> None:
        for widget in self._layout_widgets.values():
            if isinstance(widget, Gtk.Entry):
                widget.set_text("")
            elif isinstance(widget, Gtk.DropDown):
                widget.set_selected(0)
        self._module_buckets = {key: [] for key in ALIGN_KEYS}
        self._module_overrides = {}
        self._set_selected_module(None, None, -1)
        if self._module_search_entry:
            self._module_search_entry.set_text("")
        if self._module_category_dropdown:
            self._module_category_dropdown.set_selected(0)
        self._refresh_module_catalog({})
        self._render_module_columns()

    def _collect_layout_values(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for key, widget in self._layout_widgets.items():
            if isinstance(widget, Gtk.Entry):
                values[key] = widget.get_text()
            elif isinstance(widget, Gtk.DropDown):
                values[key] = self._get_dropdown_value(widget)
        return values

    def _on_apply_structured(self, *_args) -> None:
        if not self._manager.config_path.exists():
            self._set_status(
                "Cannot apply structured changes: config file not found."
            )
            return
        layout_values = self._collect_layout_values()
        errors = validate_layout_payload(layout_values)
        if errors:
            _StructuredValidationDialog(self, errors).present()
            self._set_status("Structured validation failed")
            return

        layout_payload = build_layout_payload(layout_values)
        layout_payload, layout_cleanup_keys = normalize_layout_aliases(
            self._config_data,
            layout_payload,
        )
        normalized_buckets = normalize_module_buckets(self._module_buckets)
        to_set, to_delete, target_values = compute_structured_changes(
            self._config_data,
            layout_payload,
            normalized_buckets,
        )
        for key in sorted(layout_cleanup_keys):
            if key in self._config_data and key not in to_delete:
                to_delete.append(key)
        module_config_set: dict[str, dict[str, Any]] = {}
        module_config_delete: list[str] = []
        preview_target = dict(target_values)
        for key in layout_cleanup_keys:
            preview_target.pop(key, None)
        for module_name, payload in self._module_overrides.items():
            if payload:
                preview_target[module_name] = payload
                if self._config_data.get(module_name) != payload:
                    module_config_set[module_name] = payload
            else:
                preview_target.pop(module_name, None)
                if module_name in self._config_data:
                    module_config_delete.append(module_name)
        if (
            not to_set
            and not to_delete
            and not module_config_set
            and not module_config_delete
        ):
            self._set_status("No structured changes detected")
            return
        preview_extra_keys = set(self._module_overrides.keys()) | set(
            layout_cleanup_keys
        )
        friendly_summary = build_structured_change_summary(
            self._config_data,
            preview_target,
            extra_keys=preview_extra_keys,
        )
        diff_text = build_structured_diff_preview(
            self._config_data,
            preview_target,
            extra_keys=preview_extra_keys,
        )
        dialog = _StructuredDiffDialog(
            self,
            friendly_summary,
            diff_text,
            len(to_set) + len(module_config_set),
            len(to_delete) + len(module_config_delete),
        )
        dialog.connect(
            "response",
            self._on_apply_structured_response,
            to_set,
            to_delete,
            module_config_set,
            module_config_delete,
        )
        dialog.present()

    def _on_apply_structured_response(
        self,
        dialog: _StructuredDiffDialog,
        response_id: str,
        to_set: dict[str, Any],
        to_delete: list[str],
        module_config_set: dict[str, dict[str, Any]],
        module_config_delete: list[str],
    ) -> None:
        if response_id != "ok":
            dialog.close()
            self._set_status("Structured changes canceled")
            return
        dialog.close()
        try:
            for key, value in to_set.items():
                self._manager.set_node_value(key, value)
            for key in to_delete:
                self._manager.delete_node(key)
            for module_name, payload in module_config_set.items():
                self._manager.set_node_value(module_name, payload)
            for module_name in module_config_delete:
                self._manager.delete_node(module_name)
            self._manager.save()
            self._reload_nodes()
            self._set_status("Structured changes applied")
        except WaybarConfigError as exc:
            self._set_status(str(exc))

    def _on_add_module(self, *_args) -> None:
        if (
            not self._module_new_entry
            or not self._module_target_dropdown
            or not self._module_catalog_dropdown
        ):
            return
        name = self._module_new_entry.get_text().strip()
        if not name:
            selected = self._get_dropdown_value(
                self._module_catalog_dropdown
            ).strip()
            name = self._module_name_from_catalog_option(selected)
        if name.startswith("(") and name.endswith(")"):
            name = ""
        if not name:
            self._set_status("Select or type a module name first")
            return
        selected = self._module_target_dropdown.get_selected()
        align = (
            ALIGN_KEYS[selected]
            if 0 <= selected < len(ALIGN_KEYS)
            else ALIGN_KEYS[0]
        )
        self._module_buckets[align].append(name)
        self._module_new_entry.set_text("")
        self._module_catalog_dropdown.set_selected(0)
        self._module_overrides.setdefault(name, self._read_module_config(name))
        self._refresh_module_catalog(self._config_data)
        self._render_module_columns()
        self._set_selected_module(
            align,
            name,
            len(self._module_buckets[align]) - 1,
        )
        self._set_status(f"Added module '{name}' to {align}")

    def _refresh_module_catalog(self, data: dict[str, Any]) -> None:
        if not self._module_catalog_dropdown:
            return
        data_for_catalog = dict(data)
        for align in ALIGN_KEYS:
            data_for_catalog[align] = list(
                self._module_buckets.get(align, [])
            )
        self._module_catalog_all = build_module_catalog(data_for_catalog)
        category = self._get_selected_module_category()
        query = (
            self._module_search_entry.get_text()
            if self._module_search_entry
            else ""
        )
        filtered = filter_module_catalog(
            self._module_catalog_all,
            query=query,
            category=category,
        )
        options = ["(existing module)"] + [
            f"{module} — {get_module_category(module)}"
            for module in filtered
        ]
        self._module_catalog_dropdown.set_model(Gtk.StringList.new(options))
        self._module_catalog_dropdown.set_selected(0)

    def _render_module_columns(self) -> None:
        if self._module_selected_align is not None:
            items = self._module_buckets.get(self._module_selected_align, [])
            idx = self._module_selected_index
            if (
                idx < 0
                or idx >= len(items)
                or items[idx] != self._module_selected_name
            ):
                self._set_selected_module(None, None, -1)
        for align in ALIGN_KEYS:
            box = self._module_boxes.get(align)
            if not box:
                continue
            self._clear_box(box)
            items = self._module_buckets.get(align, [])
            if not items:
                empty = Gtk.Label(label="(empty)")
                empty.add_css_class("info-label")
                empty.set_halign(Gtk.Align.START)
                box.append(empty)
                continue

            for idx, module_name in enumerate(items):
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
                row.set_hexpand(True)
                row.set_focusable(True)
                if (
                    self._module_selected_align == align
                    and self._module_selected_index == idx
                    and self._module_selected_name == module_name
                ):
                    row.add_css_class("module-row-selected")
                drag_handle = Gtk.Label(label="⠿")
                drag_handle.add_css_class("info-label")
                row.append(drag_handle)

                pill = Gtk.Label(label=module_name)
                pill.add_css_class("module-pill")
                if (
                    self._module_selected_align == align
                    and self._module_selected_index == idx
                    and self._module_selected_name == module_name
                ):
                    pill.add_css_class("module-pill-selected")
                pill.set_halign(Gtk.Align.START)
                pill.set_xalign(0)
                pill.set_hexpand(True)
                row.append(pill)

                click = Gtk.GestureClick.new()
                click.connect(
                    "pressed",
                    self._on_module_row_pressed,
                    align,
                    idx,
                    module_name,
                )
                row.add_controller(click)

                drag_source = Gtk.DragSource.new()
                drag_source.set_actions(Gdk.DragAction.MOVE)
                drag_source.connect(
                    "prepare",
                    self._on_module_drag_prepare,
                    align,
                    idx,
                    module_name,
                )
                row.add_controller(drag_source)

                drop_target = Gtk.DropTarget.new(
                    GObject.TYPE_STRING,
                    Gdk.DragAction.MOVE,
                )
                drop_target.connect(
                    "drop",
                    self._on_module_drop_on_row,
                    align,
                    idx,
                )
                row.add_controller(drop_target)

                box.append(row)

    def _on_module_drag_prepare(
        self,
        _source: Gtk.DragSource,
        _x: float,
        _y: float,
        align: str,
        index: int,
        module_name: str,
    ) -> Gdk.ContentProvider:
        self._drag_source_align = align
        self._drag_source_index = index
        token = f"{align}:{index}:{module_name}"
        return Gdk.ContentProvider.new_for_value(token)

    def _on_module_drop_on_row(
        self,
        _target: Gtk.DropTarget,
        _value: str,
        _x: float,
        _y: float,
        target_align: str,
        target_index: int,
    ) -> bool:
        col = self._module_columns.get(target_align)
        if col:
            col.remove_css_class("module-column-drop-target")
        return self._apply_drag_move(target_align, target_index)

    def _on_module_drop_on_column(
        self,
        _target: Gtk.DropTarget,
        _value: str,
        _x: float,
        _y: float,
        target_align: str,
    ) -> bool:
        col = self._module_columns.get(target_align)
        if col:
            col.remove_css_class("module-column-drop-target")
        return self._apply_drag_move(target_align, None)

    def _on_module_drop_on_trash(
        self,
        _target: Gtk.DropTarget,
        _value: str,
        _x: float,
        _y: float,
    ) -> bool:
        if self._module_trash_zone:
            self._module_trash_zone.remove_css_class(
                "module-trash-zone-drop-target"
            )
        source_align = self._drag_source_align
        source_index = self._drag_source_index
        if source_align is None or source_index < 0:
            return False
        source_items = self._module_buckets.get(source_align, [])
        if not (0 <= source_index < len(source_items)):
            return False
        removed = source_items.pop(source_index)
        if (
            self._module_selected_align == source_align
            and self._module_selected_index == source_index
        ):
            self._set_selected_module(None, None, -1)
        self._drag_source_align = None
        self._drag_source_index = -1
        self._render_module_columns()
        self._set_status(f"Removed module '{removed}'")
        return True

    def _apply_drag_move(
        self,
        target_align: str,
        target_index: int | None,
    ) -> bool:
        source_align = self._drag_source_align
        source_index = self._drag_source_index
        if source_align is None or source_index < 0:
            return False

        source_items = self._module_buckets.get(source_align, [])
        if not (0 <= source_index < len(source_items)):
            return False
        module = source_items.pop(source_index)

        if source_align == target_align:
            insert_at = len(source_items) if target_index is None else target_index
            if insert_at > source_index:
                insert_at -= 1
            insert_at = max(0, min(insert_at, len(source_items)))
            source_items.insert(insert_at, module)
            final_align = source_align
            final_index = insert_at
        else:
            target_items = self._module_buckets.get(target_align, [])
            insert_at = len(target_items) if target_index is None else target_index
            insert_at = max(0, min(insert_at, len(target_items)))
            target_items.insert(insert_at, module)
            final_align = target_align
            final_index = insert_at

        self._drag_source_align = None
        self._drag_source_index = -1
        self._set_selected_module(final_align, module, final_index)
        self._render_module_columns()
        return True

    @staticmethod
    def _set_dropdown_value(dropdown: Gtk.DropDown, value: str) -> None:
        model = dropdown.get_model()
        if not model:
            return
        for idx in range(model.get_n_items()):
            if model.get_string(idx) == value:
                dropdown.set_selected(idx)
                return
        dropdown.set_selected(0)

    @staticmethod
    def _get_dropdown_value(dropdown: Gtk.DropDown) -> str:
        model = dropdown.get_model()
        idx = dropdown.get_selected()
        if model and 0 <= idx < model.get_n_items():
            return model.get_string(idx)
        return ""

    @staticmethod
    def _clear_box(box: Gtk.Box) -> None:
        child = box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            box.remove(child)
            child = nxt

    def _make_node_card(self, key: str, value: Any) -> Gtk.Button:
        btn = Gtk.Button()
        btn.add_css_class("node-card")
        btn.connect("clicked", self._on_edit_node, key)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_halign(Gtk.Align.START)
        box.set_valign(Gtk.Align.CENTER)
        box.set_hexpand(True)
        box.set_vexpand(True)

        key_lbl = Gtk.Label(label=key)
        key_lbl.add_css_class("node-key")
        key_lbl.set_halign(Gtk.Align.START)
        key_lbl.set_xalign(0)
        key_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        box.append(key_lbl)

        summary_lbl = Gtk.Label(label=self._summarize_value(value))
        summary_lbl.add_css_class("node-summary")
        summary_lbl.set_halign(Gtk.Align.START)
        summary_lbl.set_xalign(0)
        summary_lbl.set_wrap(True)
        summary_lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        summary_lbl.set_max_width_chars(44)
        box.append(summary_lbl)

        btn.set_child(box)
        return btn

    def _on_edit_node(self, _btn: Gtk.Button, key: str) -> None:
        try:
            value = self._manager.get_node_value(key)
        except WaybarConfigError as exc:
            self._set_status(str(exc))
            return

        editor = _NodeEditorDialog(self, key, value)
        editor.connect("response", self._on_edit_node_response, key)
        editor.present()

    def _on_edit_node_response(
        self,
        dialog: _NodeEditorDialog,
        response_id: str,
        key: str,
    ) -> None:
        if response_id != "ok":
            dialog.close()
            return
        should_close = False
        try:
            value = dialog.get_json_value()
            self._manager.set_node_value(key, value)
            self._manager.save()
            self._reload_nodes()
            self._set_status(f"Node '{key}' updated")
            should_close = True
        except (WaybarConfigParseError, WaybarConfigError) as exc:
            dialog.show_error(str(exc))
            return
        finally:
            if should_close:
                dialog.close()

    def _on_backup(self, *_args) -> None:
        try:
            created = self._manager.backup_now()
            self._refresh_backups()
            self._set_status(f"Backup created: {created.name}")
        except WaybarBackupError as exc:
            self._set_status(str(exc))

    def _on_restore_backup(self, *_args) -> None:
        model = self._backup_dropdown.get_model()
        selected = self._backup_dropdown.get_selected()
        if not model or selected >= model.get_n_items():
            self._set_status("No backup selected")
            return
        name = model.get_string(selected)
        if not name or name == "(none)":
            self._set_status("No backup selected")
            return
        try:
            self._manager.restore_backup(name)
            self._reload_nodes()
            self._set_status(f"Backup restored: {name}")
        except WaybarBackupError as exc:
            self._set_status(str(exc))

    def _on_open_config(self, *_args) -> None:
        chooser = Gtk.FileChooserNative(
            title="Open Waybar config",
            transient_for=self,
            action=Gtk.FileChooserAction.OPEN,
            accept_label="Open",
            cancel_label="Cancel",
        )
        chooser.connect("response", self._on_open_config_response)
        chooser.show()

    def _on_open_config_response(
        self,
        chooser: Gtk.FileChooserNative,
        response_id: int,
    ) -> None:
        if response_id == Gtk.ResponseType.ACCEPT:
            selected = chooser.get_file()
            if selected and selected.get_path():
                self._manager.set_config_path(Path(selected.get_path()))
                self._refresh_path_label()
                self._reload_nodes()
        chooser.destroy()

    def _on_new_config(self, *_args) -> None:
        chooser = Gtk.FileChooserNative(
            title="Create Waybar config",
            transient_for=self,
            action=Gtk.FileChooserAction.SAVE,
            accept_label="Create",
            cancel_label="Cancel",
        )
        chooser.set_current_name("config.jsonc")
        chooser.set_do_overwrite_confirmation(False)
        chooser.connect("response", self._on_new_config_response)
        chooser.show()

    def _on_new_config_response(
        self,
        chooser: Gtk.FileChooserNative,
        response_id: int,
    ) -> None:
        if response_id == Gtk.ResponseType.ACCEPT:
            selected = chooser.get_file()
            if selected and selected.get_path():
                path = Path(selected.get_path())
                try:
                    self._manager.create_new_config(path)
                    self._refresh_path_label()
                    self._reload_nodes()
                    self._set_status(f"Created config: {path}")
                except WaybarConfigError as exc:
                    self._set_status(str(exc))
        chooser.destroy()

    def _show_missing_config_prompt(self) -> None:
        self._missing_config_prompt_open = True
        prompt = _MissingConfigDialog(self, str(self._manager.config_path))
        prompt.connect("response", self._on_missing_config_prompt_response)
        prompt.present()

    def _on_missing_config_prompt_response(
        self,
        dialog: _MissingConfigDialog,
        response_id: str,
    ) -> None:
        self._missing_config_prompt_open = False
        if response_id == "open":
            self._on_open_config()
        elif response_id == "create":
            self._on_new_config()
        dialog.close()

    def _refresh_backups(self) -> None:
        names = [p.name for p in self._manager.list_backups()]
        if not names:
            names = ["(none)"]
        self._backup_dropdown.set_model(Gtk.StringList.new(names))

    def _refresh_path_label(self) -> None:
        self._path_label.set_text(str(self._manager.config_path))

    def _clear_flow(self) -> None:
        child = self._nodes_flow.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._nodes_flow.remove(child)
            child = nxt

    def _set_status(self, text: str) -> None:
        self._status.set_text(text)

    @staticmethod
    def _summarize_value(value: Any) -> str:
        if isinstance(value, dict):
            preview_keys = list(value.keys())[:3]
            suffix = "…" if len(value) > 3 else ""
            return f"Object ({len(value)} keys): {', '.join(preview_keys)}{suffix}"
        if isinstance(value, list):
            return f"Array ({len(value)} items)"
        return repr(value)[:100]


class _NodeEditorDialog(Gtk.Window):
    """Popup editor for one top-level node."""

    def __init__(self, parent: Gtk.Window, key: str, value: Any) -> None:
        super().__init__(
            title=f"Edit node: {key}",
            transient_for=parent,
            modal=True,
            default_width=640,
            default_height=460,
        )
        self._response_callback = None

        main = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8,
            margin_start=12,
            margin_end=12,
            margin_top=12,
            margin_bottom=12,
        )
        self.set_child(main)

        hint = Gtk.Label(
            label="Edit JSON value for this node (object, array, string, number, bool or null)"
        )
        hint.add_css_class("info-label")
        hint.set_halign(Gtk.Align.START)
        main.append(hint)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        main.append(scroll)

        self._text = Gtk.TextView()
        self._text.set_monospace(True)
        self._text.set_wrap_mode(Gtk.WrapMode.NONE)
        self._text.get_buffer().set_text(
            json.dumps(value, indent=4, ensure_ascii=False)
        )
        scroll.set_child(self._text)

        self._error_label = Gtk.Label(label="")
        self._error_label.add_css_class("info-label")
        self._error_label.set_halign(Gtk.Align.START)
        main.append(self._error_label)

        actions = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
            halign=Gtk.Align.END,
        )
        main.append(actions)

        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", self._on_cancel)
        actions.append(cancel)

        save = Gtk.Button(label="Save")
        save.add_css_class("toolbar-button")
        save.connect("clicked", self._on_save)
        actions.append(save)

    def connect(self, signal: str, callback, *user_data):
        if signal == "response":
            self._response_callback = (callback, user_data)
        return self

    def _emit_response(self, response_id: str) -> None:
        if self._response_callback:
            callback, user_data = self._response_callback
            callback(self, response_id, *user_data)

    def _on_cancel(self, *_args) -> None:
        self._emit_response("cancel")

    def _on_save(self, *_args) -> None:
        self._emit_response("ok")

    def get_json_value(self) -> Any:
        buf = self._text.get_buffer()
        start = buf.get_start_iter()
        end = buf.get_end_iter()
        text = buf.get_text(start, end, False).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise WaybarConfigParseError(f"Invalid JSON: {exc}") from exc

    def show_error(self, message: str) -> None:
        self._error_label.set_text(message)

class _StructuredValidationDialog(Gtk.Window):
    """Dialog showing structured validation errors."""

    def __init__(self, parent: Gtk.Window, errors: list[str]) -> None:
        super().__init__(
            title="Structured validation errors",
            transient_for=parent,
            modal=True,
            default_width=520,
            default_height=260,
        )

        main = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8,
            margin_start=12,
            margin_end=12,
            margin_top=12,
            margin_bottom=12,
        )
        self.set_child(main)

        title = Gtk.Label(label="Fix these issues before saving:")
        title.add_css_class("section-title")
        title.set_halign(Gtk.Align.START)
        main.append(title)

        lines = "\n".join(f"• {error}" for error in errors)
        details = Gtk.Label(label=lines)
        details.add_css_class("info-label")
        details.set_halign(Gtk.Align.START)
        details.set_xalign(0)
        details.set_wrap(True)
        details.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        main.append(details)

        actions = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
            halign=Gtk.Align.END,
        )
        main.append(actions)

        close_btn = Gtk.Button(label="Close")
        close_btn.add_css_class("toolbar-button")
        close_btn.connect("clicked", lambda *_: self.close())
        actions.append(close_btn)


class _StructuredDiffDialog(Gtk.Window):
    """Dialog showing structured diff preview and confirmation action."""

    def __init__(
        self,
        parent: Gtk.Window,
        friendly_summary: str,
        diff_text: str,
        set_count: int,
        delete_count: int,
    ) -> None:
        super().__init__(
            title="Confirm structured changes",
            transient_for=parent,
            modal=True,
            default_width=720,
            default_height=520,
        )
        self._response_callback = None

        main = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8,
            margin_start=12,
            margin_end=12,
            margin_top=12,
            margin_bottom=12,
        )
        self.set_child(main)

        summary = Gtk.Label(
            label=(
                f"Review changes before saving "
                f"({set_count} update(s), {delete_count} removal(s))."
            )
        )
        summary.add_css_class("info-label")
        summary.set_halign(Gtk.Align.START)
        summary.set_xalign(0)
        main.append(summary)
        summary_label = Gtk.Label(label="Friendly summary by key")
        summary_label.add_css_class("section-title")
        summary_label.set_halign(Gtk.Align.START)
        main.append(summary_label)

        summary_scroll = Gtk.ScrolledWindow()
        summary_scroll.set_min_content_height(140)
        main.append(summary_scroll)
        summary_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=4,
            margin_start=6,
            margin_end=6,
            margin_top=6,
            margin_bottom=6,
        )
        summary_scroll.set_child(summary_box)
        lines = [
            line for line in friendly_summary.splitlines() if line.strip()
        ]
        if not lines:
            lines = ["(No friendly summary available)"]
        for line in lines:
            entry = Gtk.Label(label=line)
            entry.add_css_class("info-label")
            entry.set_halign(Gtk.Align.START)
            entry.set_xalign(0)
            entry.set_wrap(True)
            entry.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            stripped = line.strip()
            if stripped.startswith("• Add "):
                entry.add_css_class("diff-summary-add")
            elif stripped.startswith("• Update "):
                entry.add_css_class("diff-summary-update")
            elif stripped.startswith("• Remove "):
                entry.add_css_class("diff-summary-remove")
            summary_box.append(entry)

        diff_label = Gtk.Label(label="Unified diff")
        diff_label.add_css_class("section-title")
        diff_label.set_halign(Gtk.Align.START)
        main.append(diff_label)

        diff_scroll = Gtk.ScrolledWindow()
        diff_scroll.set_vexpand(True)
        main.append(diff_scroll)

        diff_view = Gtk.TextView()
        diff_view.set_monospace(True)
        diff_view.set_editable(False)
        diff_view.set_cursor_visible(False)
        diff_view.set_wrap_mode(Gtk.WrapMode.NONE)
        diff_view.get_buffer().set_text(diff_text or "(No textual diff)")
        diff_scroll.set_child(diff_view)

        actions = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
            halign=Gtk.Align.END,
        )
        main.append(actions)

        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", self._on_cancel)
        actions.append(cancel)

        apply_btn = Gtk.Button(label="Apply")
        apply_btn.add_css_class("toolbar-button")
        apply_btn.connect("clicked", self._on_apply)
        actions.append(apply_btn)

    def connect(self, signal: str, callback, *user_data):
        if signal == "response":
            self._response_callback = (callback, user_data)
        return self

    def _emit_response(self, response_id: str) -> None:
        if self._response_callback:
            callback, user_data = self._response_callback
            callback(self, response_id, *user_data)

    def _on_cancel(self, *_args) -> None:
        self._emit_response("cancel")

    def _on_apply(self, *_args) -> None:
        self._emit_response("ok")


class _MissingConfigDialog(Gtk.Window):
    """Prompt shown when default Waybar config path does not exist."""

    def __init__(self, parent: Gtk.Window, missing_path: str) -> None:
        super().__init__(
            title="Waybar config not found",
            transient_for=parent,
            modal=True,
            default_width=520,
            default_height=170,
        )
        self._response_callback = None

        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
            margin_start=14,
            margin_end=14,
            margin_top=14,
            margin_bottom=14,
        )
        self.set_child(box)

        title = Gtk.Label(label="Default Waybar config was not found.")
        title.add_css_class("section-title")
        title.set_halign(Gtk.Align.START)
        box.append(title)

        path_label = Gtk.Label(label=missing_path)
        path_label.add_css_class("info-label")
        path_label.set_halign(Gtk.Align.START)
        path_label.set_xalign(0)
        path_label.set_ellipsize(Pango.EllipsizeMode.END)
        box.append(path_label)

        hint = Gtk.Label(
            label="Choose one option: open an existing config file or create a new file at a path you select."
        )
        hint.add_css_class("info-label")
        hint.set_halign(Gtk.Align.START)
        hint.set_wrap(True)
        hint.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        hint.set_xalign(0)
        box.append(hint)

        actions = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
            halign=Gtk.Align.END,
        )
        box.append(actions)

        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda *_: self._emit_response("cancel"))
        actions.append(cancel)

        open_btn = Gtk.Button(label="Open file…")
        open_btn.add_css_class("toolbar-button")
        open_btn.connect("clicked", lambda *_: self._emit_response("open"))
        actions.append(open_btn)

        create_btn = Gtk.Button(label="Create new…")
        create_btn.add_css_class("toolbar-button")
        create_btn.connect("clicked", lambda *_: self._emit_response("create"))
        actions.append(create_btn)

    def connect(self, signal: str, callback, *user_data):
        if signal == "response":
            self._response_callback = (callback, user_data)
        return self

    def _emit_response(self, response_id: str) -> None:
        if self._response_callback:
            callback, user_data = self._response_callback
            callback(self, response_id, *user_data)

