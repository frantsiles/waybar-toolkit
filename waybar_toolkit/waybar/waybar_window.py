"""Waybar Manager — reorder modules, add/remove, backup, and reload."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Pango  # noqa: E402

from waybar_toolkit.waybar.config_backend import (
    ALIGN_KEYS,
    WaybarConfig,
    WaybarConfigError,
    find_config,
)

logger = logging.getLogger(__name__)

_ALIGN_LABELS = {
    "modules-left": "Left",
    "modules-center": "Center",
    "modules-right": "Right",
}

CSS = """
.col-header {
    font-weight: bold;
    font-size: 13px;
    padding: 10px 0 6px 0;
}
.mod-label {
    font-size: 13px;
}
.status-bar {
    font-size: 11px;
    color: alpha(@window_fg_color, 0.6);
}
"""


class WaybarConfigWindow(Gtk.Window):
    """Focused Waybar module manager: reorder, add, remove, backup, reload."""

    def __init__(self, app: Gtk.Application) -> None:
        super().__init__(application=app, title="Waybar Manager")
        self.set_default_size(860, 520)

        provider = Gtk.CssProvider()
        provider.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self._config: Optional[WaybarConfig] = None

        self._build_ui()
        self._load_config()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_child(root)

        root.append(self._build_header())
        root.append(Gtk.Separator())

        # Three columns fill remaining space
        columns_scroll = Gtk.ScrolledWindow()
        columns_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        columns_scroll.set_vexpand(True)

        self._columns_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=1
        )
        self._columns_box.set_homogeneous(True)
        columns_scroll.set_child(self._columns_box)
        root.append(columns_scroll)

        root.append(Gtk.Separator())
        root.append(self._build_footer())

    def _build_header(self) -> Gtk.Box:
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.set_margin_start(12)
        bar.set_margin_end(12)
        bar.set_margin_top(8)
        bar.set_margin_bottom(8)

        self._path_label = Gtk.Label(label="No config loaded")
        self._path_label.set_halign(Gtk.Align.START)
        self._path_label.set_hexpand(True)
        self._path_label.add_css_class("dim-label")
        self._path_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        bar.append(self._path_label)

        self._bar_selector = Gtk.DropDown()
        self._bar_selector.set_visible(False)
        self._bar_selector.connect("notify::selected", self._on_bar_selected)
        bar.append(self._bar_selector)

        for label, callback in [
            ("Open in Editor", self._on_open_editor),
            ("↺ Reload Waybar", self._on_reload_waybar),
            ("⟳ Refresh", lambda _: self._load_config()),
        ]:
            btn = Gtk.Button(label=label)
            btn.connect("clicked", callback)
            bar.append(btn)

        return bar

    def _build_footer(self) -> Gtk.Box:
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.set_margin_start(12)
        bar.set_margin_end(12)
        bar.set_margin_top(8)
        bar.set_margin_bottom(8)

        self._status_label = Gtk.Label(label="")
        self._status_label.set_halign(Gtk.Align.START)
        self._status_label.set_hexpand(True)
        self._status_label.add_css_class("status-bar")
        bar.append(self._status_label)

        save_btn = Gtk.Button(label="💾 Save & Reload Waybar")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self._on_save)
        bar.append(save_btn)

        return bar

    # ------------------------------------------------------------------
    # Config loading
    # ------------------------------------------------------------------

    def _load_config(self) -> None:
        path = find_config()
        if path is None:
            self._set_status("No Waybar config found in ~/.config/waybar/")
            return
        try:
            self._config = WaybarConfig(path)
            self._path_label.set_text(str(path))
            self._update_bar_selector()
            self._rebuild_columns()
            self._set_status(f"Loaded — {path}")
        except WaybarConfigError as e:
            self._set_status(f"Error loading config: {e}")
            logger.exception("Failed to load Waybar config")

    def _update_bar_selector(self) -> None:
        if self._config is None:
            return
        if self._config.bar_count > 1:
            self._bar_selector.set_model(
                Gtk.StringList.new(self._config.bar_names)
            )
            self._bar_selector.set_visible(True)
        else:
            self._bar_selector.set_visible(False)

    def _on_bar_selected(self, dropdown: Gtk.DropDown, _param) -> None:
        if self._config is None:
            return
        self._config.select_bar(dropdown.get_selected())
        self._rebuild_columns()

    # ------------------------------------------------------------------
    # Column UI
    # ------------------------------------------------------------------

    def _rebuild_columns(self) -> None:
        child = self._columns_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._columns_box.remove(child)
            child = nxt

        if self._config is None:
            return

        for i, align in enumerate(ALIGN_KEYS):
            col = self._build_column(align, i)
            self._columns_box.append(col)
            if i < len(ALIGN_KEYS) - 1:
                self._columns_box.append(Gtk.Separator(
                    orientation=Gtk.Orientation.VERTICAL
                ))

    def _build_column(self, align: str, col_idx: int) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        header = Gtk.Label(label=_ALIGN_LABELS[align])
        header.add_css_class("col-header")
        header.set_halign(Gtk.Align.CENTER)
        box.append(header)
        box.append(Gtk.Separator())

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        listbox.set_margin_top(4)
        listbox.set_margin_bottom(4)
        listbox.set_margin_start(4)
        listbox.set_margin_end(4)
        scroll.set_child(listbox)
        box.append(scroll)

        modules = self._config.get_modules(align)  # type: ignore[union-attr]
        for i, mod in enumerate(modules):
            listbox.append(
                self._build_module_row(mod, align, col_idx, i, len(modules))
            )

        box.append(Gtk.Separator())
        box.append(self._build_add_row(align))

        return box

    def _build_module_row(
        self,
        mod: str,
        align: str,
        col_idx: int,
        index: int,
        total: int,
    ) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.set_activatable(False)

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        hbox.set_margin_start(6)
        hbox.set_margin_end(4)
        hbox.set_margin_top(3)
        hbox.set_margin_bottom(3)

        # Reorder within column
        up = Gtk.Button(label="↑")
        up.add_css_class("flat")
        up.set_sensitive(index > 0)
        up.connect("clicked", self._on_move_up, align, index)

        down = Gtk.Button(label="↓")
        down.add_css_class("flat")
        down.set_sensitive(index < total - 1)
        down.connect("clicked", self._on_move_down, align, index)

        hbox.append(up)
        hbox.append(down)

        label = Gtk.Label(label=mod)
        label.add_css_class("mod-label")
        label.set_halign(Gtk.Align.START)
        label.set_hexpand(True)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        hbox.append(label)

        # Move to adjacent column
        if col_idx > 0:
            ml = Gtk.Button(label="←")
            ml.add_css_class("flat")
            ml.connect(
                "clicked", self._on_move_to_col, align, index,
                ALIGN_KEYS[col_idx - 1],
            )
            hbox.append(ml)

        if col_idx < len(ALIGN_KEYS) - 1:
            mr = Gtk.Button(label="→")
            mr.add_css_class("flat")
            mr.connect(
                "clicked", self._on_move_to_col, align, index,
                ALIGN_KEYS[col_idx + 1],
            )
            hbox.append(mr)

        rm = Gtk.Button(label="✕")
        rm.add_css_class("flat")
        rm.connect("clicked", self._on_remove, align, index)
        hbox.append(rm)

        row.set_child(hbox)
        return row

    def _build_add_row(self, align: str) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        row.set_margin_start(6)
        row.set_margin_end(6)
        row.set_margin_top(6)
        row.set_margin_bottom(6)

        entry = Gtk.Entry()
        entry.set_placeholder_text("module name…")
        entry.set_hexpand(True)

        add_btn = Gtk.Button(label="+")
        add_btn.connect("clicked", self._on_add, align, entry)
        entry.connect("activate", self._on_add, align, entry)

        row.append(entry)
        row.append(add_btn)
        return row

    # ------------------------------------------------------------------
    # Module operations — all rebuild the column UI after mutating state
    # ------------------------------------------------------------------

    def _on_move_up(self, _btn, align: str, index: int) -> None:
        if self._config is None or index == 0:
            return
        mods = self._config.get_modules(align)
        mods[index], mods[index - 1] = mods[index - 1], mods[index]
        self._config.set_modules(align, mods)
        self._rebuild_columns()

    def _on_move_down(self, _btn, align: str, index: int) -> None:
        if self._config is None:
            return
        mods = self._config.get_modules(align)
        if index >= len(mods) - 1:
            return
        mods[index], mods[index + 1] = mods[index + 1], mods[index]
        self._config.set_modules(align, mods)
        self._rebuild_columns()

    def _on_move_to_col(
        self, _btn, src_align: str, index: int, dst_align: str
    ) -> None:
        if self._config is None:
            return
        src = self._config.get_modules(src_align)
        dst = self._config.get_modules(dst_align)
        mod = src.pop(index)
        dst.append(mod)
        self._config.set_modules(src_align, src)
        self._config.set_modules(dst_align, dst)
        self._rebuild_columns()
        self._set_status(
            f"Moved '{mod}' → {_ALIGN_LABELS[dst_align]}"
        )

    def _on_remove(self, _btn, align: str, index: int) -> None:
        if self._config is None:
            return
        mods = self._config.get_modules(align)
        removed = mods.pop(index)
        self._config.set_modules(align, mods)
        self._rebuild_columns()
        self._set_status(f"Removed '{removed}'")

    def _on_add(self, _widget, align: str, entry: Gtk.Entry) -> None:
        if self._config is None:
            return
        name = entry.get_text().strip()
        if not name:
            return
        mods = self._config.get_modules(align)
        mods.append(name)
        self._config.set_modules(align, mods)
        entry.set_text("")
        self._rebuild_columns()
        self._set_status(
            f"Added '{name}' to {_ALIGN_LABELS[align]}"
        )

    # ------------------------------------------------------------------
    # Header actions
    # ------------------------------------------------------------------

    def _on_open_editor(self, _btn) -> None:
        if self._config is None:
            return
        import os
        editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "xdg-open"
        try:
            subprocess.Popen([editor, str(self._config.path)])
            self._set_status(f"Opened in {editor}")
        except FileNotFoundError:
            subprocess.Popen(["xdg-open", str(self._config.path)])

    def _on_reload_waybar(self, _btn) -> None:
        result = subprocess.run(
            ["pkill", "-SIGUSR2", "waybar"], capture_output=True
        )
        if result.returncode == 0:
            self._set_status("Waybar reloaded")
        else:
            self._set_status("Waybar not running (config saved, reload manually)")

    def _on_save(self, _btn) -> None:
        if self._config is None:
            return
        try:
            backup = self._config.save()
            self._set_status(f"Saved — backup: {backup.name}")
            self._on_reload_waybar(None)
        except Exception as e:
            self._set_status(f"Save failed: {e}")
            logger.exception("Save failed")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_status(self, msg: str) -> None:
        self._status_label.set_text(msg)
