"""Main hub window with utility buttons."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from waybar_toolkit.monitors.monitor_window import MonitorWindow
from waybar_toolkit.processes.process_window import ProcessWindow


CSS_HUB = """
.hub-window {
    background-color: @window_bg_color;
    color: @window_fg_color;
}
.hub-title {
    font-size: 18px;
    font-weight: bold;
    color: @window_fg_color;
    margin-bottom: 8px;
}
.hub-subtitle {
    font-size: 12px;
    color: alpha(@window_fg_color, 0.55);
    margin-bottom: 16px;
}
.utility-button {
    padding: 16px 24px;
    border-radius: 12px;
    background-color: @card_bg_color;
    min-width: 140px;
    min-height: 100px;
}
.utility-button:hover {
    background-color: lighter(@card_bg_color);
}
.utility-icon {
    font-size: 32px;
    margin-bottom: 8px;
}
.utility-label {
    font-size: 13px;
    color: @window_fg_color;
}
.utility-desc {
    font-size: 10px;
    color: alpha(@window_fg_color, 0.55);
}
"""


class MainWindow(Gtk.ApplicationWindow):
    """Hub window showing available utilities as a grid of buttons."""

    def __init__(self, app: Gtk.Application) -> None:
        super().__init__(application=app, title="Waybar Toolkit")
        self.set_default_size(480, 360)
        self.add_css_class("hub-window")

        self._app = app

        # CSS
        css_provider = Gtk.CssProvider()
        css_provider.load_from_string(CSS_HUB)
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        # Layout
        main_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=0,
            margin_start=24, margin_end=24, margin_top=24, margin_bottom=24,
        )
        self.set_child(main_box)

        # Header
        title = Gtk.Label(label="Waybar Toolkit")
        title.add_css_class("hub-title")
        title.set_halign(Gtk.Align.START)
        main_box.append(title)

        subtitle = Gtk.Label(label="Select a utility to open")
        subtitle.add_css_class("hub-subtitle")
        subtitle.set_halign(Gtk.Align.START)
        main_box.append(subtitle)

        # Grid of utilities
        grid = Gtk.FlowBox()
        grid.set_max_children_per_line(4)
        grid.set_min_children_per_line(2)
        grid.set_row_spacing(12)
        grid.set_column_spacing(12)
        grid.set_selection_mode(Gtk.SelectionMode.NONE)
        grid.set_homogeneous(True)
        grid.set_vexpand(True)
        main_box.append(grid)

        # -- Utilities --
        grid.append(
            self._make_utility_button(
                "🖥", "Monitors", "View, identify & arrange displays",
                self._open_monitors,
            )
        )

        grid.append(
            self._make_utility_button(
                "⚙", "Processes", "View & manage running processes",
                self._open_processes,
            )
        )

        # Placeholder for future utilities
        grid.append(
            self._make_utility_button(
                "➕", "More soon...", "Utilities will be added here",
                None,
            )
        )

    def _make_utility_button(
        self, icon: str, label: str, description: str, callback
    ) -> Gtk.Button:
        btn = Gtk.Button()
        btn.add_css_class("utility-button")
        if callback:
            btn.connect("clicked", lambda *_: callback())
        else:
            btn.set_sensitive(False)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)

        icon_label = Gtk.Label(label=icon)
        icon_label.add_css_class("utility-icon")
        box.append(icon_label)

        name_label = Gtk.Label(label=label)
        name_label.add_css_class("utility-label")
        box.append(name_label)

        desc_label = Gtk.Label(label=description)
        desc_label.add_css_class("utility-desc")
        box.append(desc_label)

        btn.set_child(box)
        return btn

    # ------------------------------------------------------------------
    # Open utilities
    # ------------------------------------------------------------------

    def _open_monitors(self) -> None:
        win = MonitorWindow(self._app)
        win.present()

    def _open_processes(self) -> None:
        win = ProcessWindow(self._app)
        win.present()
