"""Waybar config visual editor window."""

from __future__ import annotations

import json
import logging
from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gtk, Pango  # noqa: E402

from waybar_toolkit.waybar.config_backend import (
    WaybarBackupError,
    WaybarConfigError,
    WaybarConfigManager,
    WaybarConfigParseError,
)


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
"""

logger = logging.getLogger(__name__)


class WaybarConfigWindow(Gtk.Window):
    """Visual editor for top-level Waybar config nodes."""

    def __init__(self, app: Gtk.Application) -> None:
        super().__init__(application=app, title="Waybar Config Manager")
        self.set_default_size(860, 620)
        self.add_css_class("waybar-window")

        self._manager = WaybarConfigManager()

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

        path_lbl = Gtk.Label(label=str(self._manager.config_path))
        path_lbl.add_css_class("info-label")
        path_lbl.set_xalign(0)
        path_lbl.set_hexpand(True)
        path_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        toolbar.append(path_lbl)

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

        main_box.append(Gtk.Separator())

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        main_box.append(scroll)

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
        scroll.set_child(self._nodes_flow)

        main_box.append(Gtk.Separator())
        self._status = Gtk.Label(label="Ready")
        self._status.add_css_class("status-bar")
        self._status.set_halign(Gtk.Align.START)
        self._status.set_hexpand(True)
        main_box.append(self._status)

        self._refresh_backups()
        self._reload_nodes()

    def _reload_nodes(self) -> None:
        self._clear_flow()
        try:
            data = self._manager.load()
            for key, value in data.items():
                self._nodes_flow.append(self._make_node_card(key, value))
            self._set_status(f"{len(data)} node(s) loaded")
        except WaybarConfigError as exc:
            self._set_status(str(exc))
        except Exception:
            logger.exception("Unexpected error loading Waybar config")
            self._set_status("Unexpected error loading Waybar config")

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
        dialog: "_NodeEditorDialog",
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

    def _refresh_backups(self) -> None:
        names = [p.name for p in self._manager.list_backups()]
        if not names:
            names = ["(none)"]
        self._backup_dropdown.set_model(Gtk.StringList.new(names))

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

