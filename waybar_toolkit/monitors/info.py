"""Monitor information panel — EDID static data + DDC/CI VCP queries."""
from __future__ import annotations

import math
import threading
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from waybar_toolkit.monitors.backend import Monitor

if TYPE_CHECKING:
    from waybar_toolkit.monitors.brightness import BrightnessBackend

_VCP_POWER_STATE = 0xD6
_VCP_INPUT_SOURCE = 0x60

_POWER_LABELS: dict[int, str] = {
    1: "On",
    2: "Standby",
    3: "Suspend",
    4: "Off (hard)",
    5: "On (hardwired)",
}

_INPUT_LABELS: dict[int, str] = {
    1: "VGA-1",
    2: "VGA-2",
    3: "DVI-1",
    4: "DVI-2",
    15: "DisplayPort-1",
    16: "DisplayPort-2",
    17: "HDMI-1",
    18: "HDMI-2",
}


def _diagonal_inches(w_mm: int, h_mm: int) -> str:
    if w_mm <= 0 or h_mm <= 0:
        return "Unknown"
    return f'{math.sqrt(w_mm**2 + h_mm**2) / 25.4:.1f}"'


def _lbl(text: str) -> Gtk.Label:
    w = Gtk.Label(label=text)
    w.add_css_class("dim-label")
    w.set_halign(Gtk.Align.END)
    return w


def _val(text: str, selectable: bool = False) -> Gtk.Label:
    w = Gtk.Label(label=text)
    w.set_halign(Gtk.Align.START)
    if selectable:
        w.set_selectable(True)
    return w


class MonitorInfoPanel(Gtk.Expander):
    """Collapsible panel with EDID static info and DDC/CI VCP data when available."""

    def __init__(self, monitor: Monitor, brightness: BrightnessBackend) -> None:
        super().__init__(label="ℹ Monitor Info")
        self.set_margin_top(8)
        self._monitor = monitor
        self._brightness = brightness

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        outer.set_margin_top(8)
        self.set_child(outer)

        outer.append(self._build_static_grid())

        self._ddc_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        outer.append(self._ddc_box)

        if brightness.is_ddc_available(monitor.name, model=monitor.model):
            self._load_ddc_async()
        else:
            note = _val("DDC/CI not available on this display")
            note.add_css_class("dim-label")
            self._ddc_box.append(note)

    def _build_static_grid(self) -> Gtk.Grid:
        mon = self._monitor
        grid = Gtk.Grid(column_spacing=16, row_spacing=4)

        size_str = (
            f"{mon.physical_width}×{mon.physical_height} mm"
            f"  ({_diagonal_inches(mon.physical_width, mon.physical_height)})"
        )
        rows = [
            ("Make", mon.make or "—"),
            ("Model", mon.model or "—"),
            ("Serial", mon.serial or "—"),
            ("Size", size_str),
            ("Modes", str(len(mon.modes))),
        ]
        for i, (label, value) in enumerate(rows):
            grid.attach(_lbl(label), 0, i, 1, 1)
            grid.attach(_val(value, selectable=True), 1, i, 1, 1)

        return grid

    def _load_ddc_async(self) -> None:
        sep = Gtk.Separator()
        sep.set_margin_top(4)
        sep.set_margin_bottom(4)
        self._ddc_box.append(sep)

        spinner_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        spinner = Gtk.Spinner()
        spinner.start()
        note = _val("Loading DDC/CI data…")
        note.add_css_class("dim-label")
        spinner_row.append(spinner)
        spinner_row.append(note)
        self._ddc_box.append(spinner_row)

        def _fetch() -> None:
            results: dict[str, int] = {}
            for code, key in [
                (_VCP_POWER_STATE, "power"),
                (_VCP_INPUT_SOURCE, "input"),
            ]:
                val = self._brightness.query_vcp(
                    self._monitor.name, code, model=self._monitor.model
                )
                if val is not None:
                    results[key] = val[0]
            GLib.idle_add(self._update_ddc_ui, spinner_row, results)

        threading.Thread(target=_fetch, daemon=True).start()

    def _update_ddc_ui(
        self, spinner_row: Gtk.Box, results: dict[str, int]
    ) -> bool:
        self._ddc_box.remove(spinner_row)

        title = _val("DDC/CI")
        title.add_css_class("dim-label")
        self._ddc_box.append(title)

        if not results:
            note = _val("No readable VCP codes on this display")
            note.add_css_class("dim-label")
            self._ddc_box.append(note)
            return GLib.SOURCE_REMOVE

        grid = Gtk.Grid(column_spacing=16, row_spacing=4)
        row = 0

        if "power" in results:
            power_str = _POWER_LABELS.get(results["power"], f"Code {results['power']}")
            grid.attach(_lbl("Power state"), 0, row, 1, 1)
            grid.attach(_val(power_str), 1, row, 1, 1)
            row += 1

        if "input" in results:
            input_str = _INPUT_LABELS.get(results["input"], f"Source {results['input']}")
            grid.attach(_lbl("Input source"), 0, row, 1, 1)
            grid.attach(_val(input_str), 1, row, 1, 1)

        self._ddc_box.append(grid)
        return GLib.SOURCE_REMOVE
