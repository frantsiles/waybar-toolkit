"""Identify monitors by showing a fullscreen overlay on each one."""

from __future__ import annotations

import subprocess
import math

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib  # noqa: E402

from waybar_toolkit.monitors.backend import Monitor  # noqa: E402
from waybar_toolkit.monitors.monitor_canvas import _lookup_color, _rgba  # noqa: E402

DISPLAY_SECONDS = 3


class IdentifyOverlay(Gtk.Window):
    """A fullscreen window that shows the monitor number and name."""

    def __init__(
        self, app: Gtk.Application, monitor: Monitor, index: int
    ) -> None:
        super().__init__(application=app)
        self._monitor = monitor
        self._index = index

        self.set_decorated(False)
        self.set_title(f"Identify {monitor.name}")
        self.set_default_size(monitor.width, monitor.height)

        # Drawing area for custom rendering
        canvas = Gtk.DrawingArea()
        canvas.set_draw_func(self._draw)
        canvas.set_hexpand(True)
        canvas.set_vexpand(True)
        self.set_child(canvas)

        # Click to dismiss
        click = Gtk.GestureClick.new()
        click.connect("released", lambda *_: self.close())
        canvas.add_controller(click)

        # Auto-close after N seconds
        GLib.timeout_add_seconds(DISPLAY_SECONDS, self._auto_close)

    def _auto_close(self) -> bool:
        self.close()
        return GLib.SOURCE_REMOVE

    def _draw(self, area, cr, width, height):
        # Read theme colors
        bg = _lookup_color(area, "window_bg_color")
        fg = _lookup_color(area, "window_fg_color")
        accent = _lookup_color(area, "accent_bg_color")
        dim_fg = _rgba(fg, 0.55)

        # Semi-transparent background from theme
        cr.set_source_rgba(*_rgba(bg, 0.85))
        cr.rectangle(0, 0, width, height)
        cr.fill()

        # Big number — accent color
        cr.set_source_rgba(*accent)
        cr.select_font_face("sans-serif")
        number_size = min(width, height) * 0.35
        cr.set_font_size(number_size)
        num_text = str(self._index + 1)
        extents = cr.text_extents(num_text)
        cr.move_to(
            width / 2 - extents.width / 2,
            height / 2 - 20,
        )
        cr.show_text(num_text)

        # Monitor name
        cr.set_source_rgba(*fg)
        cr.set_font_size(min(28, height * 0.05))
        name_text = self._monitor.name
        extents = cr.text_extents(name_text)
        cr.move_to(width / 2 - extents.width / 2, height / 2 + 40)
        cr.show_text(name_text)

        # Model
        cr.set_source_rgba(*dim_fg)
        cr.set_font_size(min(20, height * 0.035))
        model_text = self._monitor.display_name
        extents = cr.text_extents(model_text)
        cr.move_to(width / 2 - extents.width / 2, height / 2 + 80)
        cr.show_text(model_text)

        # Resolution info
        cr.set_font_size(min(16, height * 0.028))
        info = f"{self._monitor.width}x{self._monitor.height}@{self._monitor.refresh_rate:.0f}Hz"
        if self._monitor.scale != 1.0:
            info += f"  (scale {self._monitor.scale}x)"
        extents = cr.text_extents(info)
        cr.move_to(width / 2 - extents.width / 2, height / 2 + 115)
        cr.show_text(info)


def _hyprctl(*args: str) -> None:
    """Run a hyprctl command, ignoring errors."""
    try:
        subprocess.run(
            ["hyprctl", *args],
            capture_output=True,
            timeout=2,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def show_identify(app: Gtk.Application, monitors: list[Monitor]) -> None:
    """Show identify overlays on all monitors.

    Sequentially focuses each monitor, creates the overlay window on it,
    then fullscreens it — ensuring each overlay lands on the right display.
    """
    _show_overlay_on_monitor(app, monitors, 0)


def _show_overlay_on_monitor(
    app: Gtk.Application, monitors: list[Monitor], index: int
) -> None:
    """Recursively show an overlay on each monitor with timing delays."""
    if index >= len(monitors):
        return

    mon = monitors[index]

    # 1. Focus the target monitor
    _hyprctl("dispatch", "focusmonitor", mon.name)

    # 2. After a short delay, create the window (opens on focused monitor)
    def _create_window() -> bool:
        overlay = IdentifyOverlay(app, mon, index)
        overlay.present()

        # 3. After another delay, fullscreen and move to next monitor
        def _fullscreen_and_next() -> bool:
            _hyprctl("dispatch", "fullscreen", "0")
            # Proceed to the next monitor
            GLib.timeout_add(150, lambda: _show_overlay_on_monitor(
                app, monitors, index + 1
            ) or GLib.SOURCE_REMOVE)
            return GLib.SOURCE_REMOVE

        GLib.timeout_add(150, _fullscreen_and_next)
        return GLib.SOURCE_REMOVE

    GLib.timeout_add(150, _create_window)
