"""Visual canvas that draws monitor rectangles proportionally."""

from __future__ import annotations

import math

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gtk  # noqa: E402

from waybar_toolkit.monitors.backend import Monitor  # noqa: E402

CANVAS_PADDING = 40
MIN_RECT_WIDTH = 120

# Fallback colors (used when theme colors are unavailable)
_FALLBACKS = {
    "window_bg_color": (0.12, 0.12, 0.14, 1.0),
    "window_fg_color": (0.9, 0.9, 0.92, 1.0),
    "accent_bg_color": (0.35, 0.55, 0.95, 1.0),
    "card_bg_color": (0.22, 0.24, 0.28, 1.0),
    "borders": (0.4, 0.42, 0.48, 1.0),
    "shade_color": (0.0, 0.0, 0.0, 0.36),
}


def _lookup_color(widget: Gtk.Widget, name: str) -> tuple[float, float, float, float]:
    """Look up a named color from the GTK theme, with fallback."""
    ctx = widget.get_style_context()
    found, color = ctx.lookup_color(name)
    if found:
        return (color.red, color.green, color.blue, color.alpha)
    return _FALLBACKS.get(name, (0.5, 0.5, 0.5, 1.0))


def _rgba(color: tuple, alpha: float | None = None) -> tuple[float, float, float, float]:
    """Return (r, g, b, a) — optionally override alpha."""
    if alpha is not None:
        return (color[0], color[1], color[2], alpha)
    return color


# Minimum pixels to move before a click becomes a drag
_DRAG_THRESHOLD = 6


class MonitorCanvas(Gtk.DrawingArea):
    """Draws a scaled representation of the monitor layout.

    Supports click-to-select and drag-to-reorder monitors horizontally.
    """

    def __init__(self) -> None:
        super().__init__()

        self._monitors: list[Monitor] = []
        self._selected_index: int = 0
        self._hover_index: int = -1
        self._rects: list[tuple[float, float, float, float]] = []  # drawn rects
        self._on_select_callback = None
        self._on_swap_callback = None

        # Drag state
        self._dragging: bool = False
        self._drag_index: int = -1
        self._drag_start_x: float = 0.0
        self._drag_offset_x: float = 0.0  # current drag displacement
        self._press_x: float = 0.0
        self._press_y: float = 0.0
        self._press_index: int = -1  # monitor pressed, before drag threshold

        self.set_content_width(500)
        self.set_content_height(200)
        self.set_draw_func(self._draw)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_cursor(Gdk.Cursor.new_from_name("default"))

        # Press / release handling via GestureDrag (better for drag detection)
        drag = Gtk.GestureDrag.new()
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        drag.connect("drag-end", self._on_drag_end)
        self.add_controller(drag)

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

    def connect_swap(self, callback) -> None:
        """Register a callback(idx_a, idx_b) for when monitors are swapped via drag."""
        self._on_swap_callback = callback

    def _hit_test(self, x: float, y: float) -> int:
        """Return index of monitor at (x, y) or -1."""
        for i, (rx, ry, rw, rh) in enumerate(self._rects):
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                return i
        return -1

    # -- Drag-and-drop ------------------------------------------------

    def _on_drag_begin(self, gesture, start_x, start_y):
        """Mouse button pressed — record start position."""
        self._press_x = start_x
        self._press_y = start_y
        self._press_index = self._hit_test(start_x, start_y)
        self._dragging = False
        self._drag_offset_x = 0.0

    def _on_drag_update(self, gesture, offset_x, offset_y):
        """Mouse moved while pressed — start drag if past threshold."""
        if self._press_index < 0:
            return

        if not self._dragging and abs(offset_x) > _DRAG_THRESHOLD:
            # Start dragging
            self._dragging = True
            self._drag_index = self._press_index
            self._selected_index = self._press_index
            self.set_cursor(Gdk.Cursor.new_from_name("grabbing"))

        if self._dragging:
            self._drag_offset_x = offset_x
            self.queue_draw()

    def _on_drag_end(self, gesture, offset_x, offset_y):
        """Mouse released — either select (click) or finish drag (swap)."""
        if self._dragging and self._drag_index >= 0:
            # Determine which monitor the dragged one crossed over
            swap_target = self._find_swap_target()
            if swap_target >= 0 and swap_target != self._drag_index:
                if self._on_swap_callback:
                    self._on_swap_callback(self._drag_index, swap_target)

            self._dragging = False
            self._drag_index = -1
            self._drag_offset_x = 0.0
            self.set_cursor(Gdk.Cursor.new_from_name("default"))
            self.queue_draw()
        else:
            # It was a click, not a drag
            idx = self._press_index
            if idx >= 0:
                self._selected_index = idx
                self.queue_draw()
                if self._on_select_callback:
                    self._on_select_callback(idx)

        self._press_index = -1

    def _find_swap_target(self) -> int:
        """Find which monitor the dragged one should swap with.

        Returns the index of the target monitor, or -1 if no swap.
        """
        if self._drag_index < 0 or not self._rects:
            return -1

        # Center of the dragged monitor at its current visual position
        rx, ry, rw, rh = self._rects[self._drag_index]
        dragged_center_x = rx + rw / 2 + self._drag_offset_x

        # Check if dragged center crossed into another monitor's area
        for i, (ox, oy, ow, oh) in enumerate(self._rects):
            if i == self._drag_index:
                continue
            # Swap if dragged center passes the other monitor's center
            other_center = ox + ow / 2
            if self._drag_offset_x > 0 and dragged_center_x > other_center:
                # Dragged right, past a neighbor
                if ox > rx:  # neighbor is to the right
                    return i
            elif self._drag_offset_x < 0 and dragged_center_x < other_center:
                # Dragged left, past a neighbor
                if ox < rx:  # neighbor is to the left
                    return i
        return -1

    # -- Hover --------------------------------------------------------

    def _on_motion(self, controller, x, y):
        if self._dragging:
            return  # drag_update handles this
        idx = self._hit_test(x, y)
        if idx != self._hover_index:
            self._hover_index = idx
            # Show grab cursor when hovering over a monitor
            if idx >= 0:
                self.set_cursor(Gdk.Cursor.new_from_name("grab"))
            else:
                self.set_cursor(Gdk.Cursor.new_from_name("default"))
            self.queue_draw()

    def _on_leave(self, controller):
        if self._hover_index >= 0:
            self._hover_index = -1
            self.set_cursor(Gdk.Cursor.new_from_name("default"))
            self.queue_draw()

    def _draw(self, area, cr, width, height):
        """Cairo draw function."""
        # Read theme colors
        bg = _lookup_color(self, "window_bg_color")
        fg = _lookup_color(self, "window_fg_color")
        accent = _lookup_color(self, "accent_bg_color")
        card = _lookup_color(self, "card_bg_color")
        border = _lookup_color(self, "borders")
        dim_fg = _rgba(fg, 0.55)

        # Background
        cr.set_source_rgba(*bg)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        if not self._monitors:
            cr.set_source_rgba(*fg)
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

        # First pass: compute rects (needed for drag drop zone detection)
        self._rects = []
        for i, mon in enumerate(self._monitors):
            rx = offset_x + mon.x * scale
            ry = offset_y + mon.y * scale
            rw = mon.scaled_width * scale
            rh = mon.scaled_height * scale
            self._rects.append((rx, ry, rw, rh))

        # Draw non-dragged monitors first, then the dragged one on top
        draw_order = list(range(len(self._monitors)))
        if self._dragging and self._drag_index >= 0:
            draw_order.remove(self._drag_index)
            draw_order.append(self._drag_index)  # draw last = on top

        for i in draw_order:
            mon = self._monitors[i]
            rx, ry, rw, rh = self._rects[i]

            is_dragged = self._dragging and i == self._drag_index
            is_selected = i == self._selected_index
            is_hovered = i == self._hover_index

            # Apply drag offset
            if is_dragged:
                rx += self._drag_offset_x

            # Drop shadow for dragged monitor
            if is_dragged:
                cr.set_source_rgba(0, 0, 0, 0.25)
                _rounded_rect(cr, rx + 4, ry + 4, rw, rh, 8)
                cr.fill()

            # Fill
            if is_dragged:
                cr.set_source_rgba(*_rgba(accent, 0.45))
            elif is_selected:
                cr.set_source_rgba(*_rgba(accent, 0.3))
            elif is_hovered:
                cr.set_source_rgba(*_rgba(card, 0.9))
            else:
                cr.set_source_rgba(*card)

            _rounded_rect(cr, rx, ry, rw, rh, 8)
            cr.fill()

            # Border
            if is_dragged:
                cr.set_source_rgba(*accent)
                cr.set_line_width(3.0)
            elif is_selected:
                cr.set_source_rgba(*accent)
                cr.set_line_width(2.5)
            else:
                cr.set_source_rgba(*border)
                cr.set_line_width(1.0)

            _rounded_rect(cr, rx, ry, rw, rh, 8)
            cr.stroke()

            # Monitor number (big)
            cr.set_source_rgba(*fg)
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
            cr.set_source_rgba(*dim_fg)
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
                cr.set_source_rgba(*dim_fg)
                extents = cr.text_extents(model_text)
                cr.move_to(rx + rw / 2 - extents.width / 2, ry + rh * 0.82)
                cr.show_text(model_text)

        # Draw drop indicator line during drag
        if self._dragging and self._drag_index >= 0:
            target = self._find_swap_target()
            if target >= 0:
                tx, ty, tw, th = self._rects[target]
                if self._drag_offset_x > 0:
                    line_x = tx + tw + 2  # right edge of target
                else:
                    line_x = tx - 2  # left edge of target
                cr.set_source_rgba(*accent)
                cr.set_line_width(3.0)
                cr.move_to(line_x, ty)
                cr.line_to(line_x, ty + th)
                cr.stroke()


def _rounded_rect(cr, x, y, w, h, r):
    """Draw a rounded rectangle path."""
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()
