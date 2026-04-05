"""Real-time CPU and Memory charts rendered with Cairo."""

from __future__ import annotations

import math
from collections import deque

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

# Max data points (~2 min at 2s refresh)
HISTORY_SIZE = 60

# Palette for per-core lines (up to 32 cores)
_CORE_COLORS = [
    (0.35, 0.55, 0.95),  # blue
    (0.90, 0.35, 0.35),  # red
    (0.35, 0.80, 0.45),  # green
    (0.95, 0.70, 0.25),  # orange
    (0.70, 0.40, 0.90),  # purple
    (0.25, 0.80, 0.80),  # cyan
    (0.95, 0.50, 0.65),  # pink
    (0.55, 0.75, 0.30),  # lime
]


def _lookup_color(
    widget: Gtk.Widget, name: str
) -> tuple[float, float, float, float]:
    """Look up a named color from the GTK theme, with fallback."""
    ctx = widget.get_style_context()
    found, color = ctx.lookup_color(name)
    if found:
        return (color.red, color.green, color.blue, color.alpha)
    fallbacks = {
        "window_bg_color": (0.12, 0.12, 0.14, 1.0),
        "window_fg_color": (0.9, 0.9, 0.92, 1.0),
        "accent_bg_color": (0.35, 0.55, 0.95, 1.0),
        "card_bg_color": (0.22, 0.24, 0.28, 1.0),
    }
    return fallbacks.get(name, (0.5, 0.5, 0.5, 1.0))


# ---------------------------------------------------------------------------
# CPU Chart
# ---------------------------------------------------------------------------


class CpuChart(Gtk.DrawingArea):
    """Line chart showing CPU usage over time (total + per-core)."""

    def __init__(self) -> None:
        super().__init__()
        self._total_history: deque[float] = deque(maxlen=HISTORY_SIZE)
        self._core_histories: list[deque[float]] = []
        self._show_per_core: bool = True

        self.set_content_height(80)
        self.set_content_width(300)
        self.set_hexpand(True)
        self.set_draw_func(self._draw)

    def push(
        self, total: float, per_core: list[float] | None = None
    ) -> None:
        """Add a new data point and redraw."""
        self._total_history.append(total)

        if per_core:
            # Grow core histories as needed
            while len(self._core_histories) < len(per_core):
                self._core_histories.append(deque(maxlen=HISTORY_SIZE))
            for i, val in enumerate(per_core):
                self._core_histories[i].append(val)

        self.queue_draw()

    def set_show_per_core(self, show: bool) -> None:
        self._show_per_core = show
        self.queue_draw()

    def _draw(self, area: Gtk.DrawingArea, cr, width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            return

        bg = _lookup_color(self, "card_bg_color")
        fg = _lookup_color(self, "window_fg_color")
        accent = _lookup_color(self, "accent_bg_color")

        pad_left = 32
        pad_right = 8
        pad_top = 4
        pad_bottom = 16
        chart_w = width - pad_left - pad_right
        chart_h = height - pad_top - pad_bottom

        # Background
        cr.set_source_rgba(*bg)
        _rounded_rect(cr, 0, 0, width, height, 8)
        cr.fill()

        if chart_w <= 0 or chart_h <= 0:
            return

        # Grid lines (25%, 50%, 75%)
        cr.set_source_rgba(fg[0], fg[1], fg[2], 0.15)
        cr.set_line_width(0.5)
        for pct in (25, 50, 75):
            y = pad_top + chart_h * (1 - pct / 100)
            cr.move_to(pad_left, y)
            cr.line_to(pad_left + chart_w, y)
            cr.stroke()

        # Y-axis labels
        cr.set_source_rgba(fg[0], fg[1], fg[2], 0.5)
        cr.set_font_size(9)
        for pct in (0, 50, 100):
            y = pad_top + chart_h * (1 - pct / 100)
            cr.move_to(2, y + 3)
            cr.show_text(f"{pct}%")

        # Per-core lines (subtle)
        if self._show_per_core and self._core_histories:
            for i, history in enumerate(self._core_histories):
                if len(history) < 2:
                    continue
                color = _CORE_COLORS[i % len(_CORE_COLORS)]
                cr.set_source_rgba(color[0], color[1], color[2], 0.25)
                cr.set_line_width(1.0)
                self._draw_line(cr, history, pad_left, pad_top, chart_w, chart_h)
                cr.stroke()

        # Total CPU line (prominent)
        if len(self._total_history) >= 2:
            cr.set_source_rgba(accent[0], accent[1], accent[2], 0.9)
            cr.set_line_width(2.0)
            self._draw_line(
                cr, self._total_history, pad_left, pad_top, chart_w, chart_h
            )
            cr.stroke()

            # Fill under the line
            cr.set_source_rgba(accent[0], accent[1], accent[2], 0.15)
            self._draw_line(
                cr, self._total_history, pad_left, pad_top, chart_w, chart_h
            )
            n = len(self._total_history)
            x_last = pad_left + chart_w * ((n - 1) / max(HISTORY_SIZE - 1, 1))
            cr.line_to(x_last, pad_top + chart_h)
            cr.line_to(pad_left, pad_top + chart_h)
            cr.close_path()
            cr.fill()

        # Current value label
        if self._total_history:
            current = self._total_history[-1]
            cr.set_source_rgba(fg[0], fg[1], fg[2], 0.8)
            cr.set_font_size(10)
            label = f"CPU {current:.0f}%"
            cr.move_to(pad_left + 4, height - 3)
            cr.show_text(label)

    def _draw_line(
        self,
        cr,
        data: deque[float],
        x0: float,
        y0: float,
        w: float,
        h: float,
    ) -> None:
        """Draw a line from data points onto the chart area."""
        n = len(data)
        if n < 2:
            return
        for i, val in enumerate(data):
            x = x0 + w * (i / max(HISTORY_SIZE - 1, 1))
            y = y0 + h * (1 - min(val, 100) / 100)
            if i == 0:
                cr.move_to(x, y)
            else:
                cr.line_to(x, y)


# ---------------------------------------------------------------------------
# Memory Chart
# ---------------------------------------------------------------------------


class MemChart(Gtk.DrawingArea):
    """Area chart showing memory usage over time."""

    def __init__(self) -> None:
        super().__init__()
        self._used_history: deque[float] = deque(maxlen=HISTORY_SIZE)
        self._cached_history: deque[float] = deque(maxlen=HISTORY_SIZE)
        self._total_kb: int = 0

        self.set_content_height(80)
        self.set_content_width(300)
        self.set_hexpand(True)
        self.set_draw_func(self._draw)

    def push(self, used_kb: int, cached_kb: int, total_kb: int) -> None:
        """Add a new data point and redraw."""
        self._total_kb = total_kb
        if total_kb > 0:
            self._used_history.append((used_kb / total_kb) * 100)
            self._cached_history.append((cached_kb / total_kb) * 100)
        else:
            self._used_history.append(0.0)
            self._cached_history.append(0.0)
        self.queue_draw()

    def _draw(self, area: Gtk.DrawingArea, cr, width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            return

        bg = _lookup_color(self, "card_bg_color")
        fg = _lookup_color(self, "window_fg_color")

        pad_left = 32
        pad_right = 8
        pad_top = 4
        pad_bottom = 16
        chart_w = width - pad_left - pad_right
        chart_h = height - pad_top - pad_bottom

        # Background
        cr.set_source_rgba(*bg)
        _rounded_rect(cr, 0, 0, width, height, 8)
        cr.fill()

        if chart_w <= 0 or chart_h <= 0:
            return

        # Grid lines
        cr.set_source_rgba(fg[0], fg[1], fg[2], 0.15)
        cr.set_line_width(0.5)
        for pct in (25, 50, 75):
            y = pad_top + chart_h * (1 - pct / 100)
            cr.move_to(pad_left, y)
            cr.line_to(pad_left + chart_w, y)
            cr.stroke()

        # Y-axis labels
        cr.set_source_rgba(fg[0], fg[1], fg[2], 0.5)
        cr.set_font_size(9)
        for pct in (0, 50, 100):
            y = pad_top + chart_h * (1 - pct / 100)
            cr.move_to(2, y + 3)
            cr.show_text(f"{pct}%")

        # Cached area (subtle)
        if len(self._cached_history) >= 2:
            cr.set_source_rgba(0.35, 0.80, 0.45, 0.2)
            self._draw_filled_area(
                cr, self._cached_history, pad_left, pad_top, chart_w, chart_h
            )

        # Used area (prominent)
        if len(self._used_history) >= 2:
            # Fill
            cr.set_source_rgba(0.90, 0.35, 0.35, 0.25)
            self._draw_filled_area(
                cr, self._used_history, pad_left, pad_top, chart_w, chart_h
            )
            # Line
            cr.set_source_rgba(0.90, 0.35, 0.35, 0.9)
            cr.set_line_width(2.0)
            self._draw_line(
                cr, self._used_history, pad_left, pad_top, chart_w, chart_h
            )
            cr.stroke()

        # Current value label
        if self._used_history and self._total_kb > 0:
            used_pct = self._used_history[-1]
            used_gb = (self._total_kb * used_pct / 100) / (1024 * 1024)
            total_gb = self._total_kb / (1024 * 1024)
            cr.set_source_rgba(fg[0], fg[1], fg[2], 0.8)
            cr.set_font_size(10)
            cr.move_to(pad_left + 4, height - 3)
            cr.show_text(f"RAM {used_gb:.1f}/{total_gb:.1f} GB ({used_pct:.0f}%)")

    def _draw_line(
        self, cr, data: deque[float], x0: float, y0: float, w: float, h: float
    ) -> None:
        n = len(data)
        if n < 2:
            return
        for i, val in enumerate(data):
            x = x0 + w * (i / max(HISTORY_SIZE - 1, 1))
            y = y0 + h * (1 - min(val, 100) / 100)
            if i == 0:
                cr.move_to(x, y)
            else:
                cr.line_to(x, y)

    def _draw_filled_area(
        self, cr, data: deque[float], x0: float, y0: float, w: float, h: float
    ) -> None:
        n = len(data)
        if n < 2:
            return
        self._draw_line(cr, data, x0, y0, w, h)
        x_last = x0 + w * ((n - 1) / max(HISTORY_SIZE - 1, 1))
        cr.line_to(x_last, y0 + h)
        cr.line_to(x0, y0 + h)
        cr.close_path()
        cr.fill()


# ---------------------------------------------------------------------------
# Cairo helper
# ---------------------------------------------------------------------------


def _rounded_rect(
    cr, x: float, y: float, w: float, h: float, r: float
) -> None:
    """Draw a rounded rectangle path."""
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()
