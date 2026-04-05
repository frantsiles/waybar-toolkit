"""Visual canvas that draws monitor rectangles proportionally."""

from __future__ import annotations

import math

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk  # noqa: E402

from waybar_toolkit.monitors.backend import Monitor  # noqa: E402

# Colors (RGBA)
COLOR_BG = (0.12, 0.12, 0.14, 1.0)
COLOR_MONITOR = (0.22, 0.24, 0.28, 1.0)
COLOR_MONITOR_HOVER = (0.28, 0.30, 0.35, 1.0)
COLOR_SELECTED = (0.35, 0.55, 0.95, 1.0)
COLOR_BORDER = (0.4, 0.42, 0.48, 1.0)
COLOR_TEXT = (0.9, 0.9, 0.92, 1.0)
COLOR_SUBTEXT = (0.6, 0.62, 0.66, 1.0)

CANVAS_PADDING = 40
MIN_RECT_WIDTH = 120


class MonitorCanvas(Gtk.DrawingArea):
    """Draws a scaled representation of the monitor layout."""

    def __init__(self) -> None:
        super().__init__()

        self._monitors: list[Monitor] = []
        self._selected_index: int = 0
        self._hover_index: int = -1
        self._rects: list[tuple[float, float, float, float]] = []  # drawn rects
        self._on_select_callback = None

        self.set_content_width(500)
        self.set_content_height(200)
        self.set_draw_func(self._draw)
        self.set_hexpand(True)
        self.set_vexpand(True)

        # Click handling
        click = Gtk.GestureClick.new()
        click.connect("released", self._on_click)
        self.add_controller(click)

        # Hover handling
        motion = Gtk.EventControllerMotion.new()
        motion.connect("motion", self._on_motion)
        motion.connect("leave", self._on_leave)
        self.add_controller(motion)

    def set_monitors(self, monitors: list[Monitor]) -> None:
        self._monitors = monitors
        if self._selected_index >= len(monitors):
            self._selected_index = 0
        self.queue_draw()

    def set_selected(self, index: int) -> None:
        if 0 <= index < len(self._monitors):
            self._selected_index = index
            self.queue_draw()

    def get_selected(self) -> int:
        return self._selected_index

    def connect_select(self, callback) -> None:
        """Register a callback(index) for when a monitor is clicked."""
        self._on_select_callback = callback

    def _hit_test(self, x: float, y: float) -> int:
        """Return index of monitor at (x, y) or -1."""
        for i, (rx, ry, rw, rh) in enumerate(self._rects):
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                return i
        return -1

    def _on_click(self, gesture, n_press, x, y):
        idx = self._hit_test(x, y)
        if idx >= 0:
            self._selected_index = idx
            self.queue_draw()
            if self._on_select_callback:
                self._on_select_callback(idx)

    def _on_motion(self, controller, x, y):
        idx = self._hit_test(x, y)
        if idx != self._hover_index:
            self._hover_index = idx
            self.queue_draw()

    def _on_leave(self, controller):
        if self._hover_index >= 0:
            self._hover_index = -1
            self.queue_draw()

    def _draw(self, area, cr, width, height):
        """Cairo draw function."""
        # Background
        cr.set_source_rgba(*COLOR_BG)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        if not self._monitors:
            cr.set_source_rgba(*COLOR_TEXT)
            cr.select_font_face("sans-serif")
            cr.set_font_size(14)
            cr.move_to(width / 2 - 60, height / 2)
            cr.show_text("No monitors detected")
            return

        # Calculate scale to fit all monitors in the canvas
        sorted_mons = sorted(self._monitors, key=lambda m: m.x)

        # Total virtual desktop size
        max_x = max(m.x + m.scaled_width for m in sorted_mons)
        max_y = max(m.y + m.scaled_height for m in sorted_mons)

        available_w = width - CANVAS_PADDING * 2
        available_h = height - CANVAS_PADDING * 2

        scale_x = available_w / max(max_x, 1)
        scale_y = available_h / max(max_y, 1)
        scale = min(scale_x, scale_y)

        # Ensure minimum rectangle width
        if scale * min(m.scaled_width for m in sorted_mons) < MIN_RECT_WIDTH:
            scale = MIN_RECT_WIDTH / min(m.scaled_width for m in sorted_mons)

        # Center the layout
        total_w = max_x * scale
        total_h = max_y * scale
        offset_x = (width - total_w) / 2
        offset_y = (height - total_h) / 2

        self._rects = []

        for i, mon in enumerate(self._monitors):
            rx = offset_x + mon.x * scale
            ry = offset_y + mon.y * scale
            rw = mon.scaled_width * scale
            rh = mon.scaled_height * scale

            self._rects.append((rx, ry, rw, rh))

            # Monitor rectangle
            is_selected = i == self._selected_index
            is_hovered = i == self._hover_index

            # Fill
            if is_selected:
                cr.set_source_rgba(*COLOR_SELECTED, 0.3)
            elif is_hovered:
                cr.set_source_rgba(*COLOR_MONITOR_HOVER)
            else:
                cr.set_source_rgba(*COLOR_MONITOR)

            _rounded_rect(cr, rx, ry, rw, rh, 8)
            cr.fill()

            # Border
            if is_selected:
                cr.set_source_rgba(*COLOR_SELECTED)
                cr.set_line_width(2.5)
            else:
                cr.set_source_rgba(*COLOR_BORDER)
                cr.set_line_width(1.0)

            _rounded_rect(cr, rx, ry, rw, rh, 8)
            cr.stroke()

            # Monitor number (big)
            cr.set_source_rgba(*COLOR_TEXT)
            cr.select_font_face("sans-serif")
            cr.set_font_size(min(28, rh * 0.3))
            num_text = str(i + 1)
            extents = cr.text_extents(num_text)
            cr.move_to(
                rx + rw / 2 - extents.width / 2,
                ry + rh * 0.4,
            )
            cr.show_text(num_text)

            # Monitor name
            cr.set_font_size(min(11, rh * 0.1))
            cr.set_source_rgba(*COLOR_SUBTEXT)
            name_text = mon.name
            extents = cr.text_extents(name_text)
            cr.move_to(rx + rw / 2 - extents.width / 2, ry + rh * 0.55)
            cr.show_text(name_text)

            # Resolution + scale
            info_text = f"{mon.width}x{mon.height}"
            if mon.scale != 1.0:
                info_text += f" @{mon.scale}x"
            cr.set_font_size(min(10, rh * 0.09))
            extents = cr.text_extents(info_text)
            cr.move_to(rx + rw / 2 - extents.width / 2, ry + rh * 0.7)
            cr.show_text(info_text)

            # Model name
            if mon.model:
                model_text = mon.model
                cr.set_font_size(min(9, rh * 0.08))
                extents = cr.text_extents(model_text)
                cr.move_to(rx + rw / 2 - extents.width / 2, ry + rh * 0.82)
                cr.show_text(model_text)


def _rounded_rect(cr, x, y, w, h, r):
    """Draw a rounded rectangle path."""
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()
