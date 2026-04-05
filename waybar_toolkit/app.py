"""Waybar Toolkit — main application entry point."""

from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio, GLib  # noqa: E402

from waybar_toolkit.main_window import MainWindow
from waybar_toolkit.monitors.monitor_window import MonitorWindow


APP_ID = "dev.waybar-toolkit"


class WaybarToolkitApp(Gtk.Application):
    """GTK4 application for Waybar Toolkit."""

    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self._direct_monitor = False

        # CLI options
        self.add_main_option(
            "monitors",
            ord("m"),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.NONE,
            "Open Monitor Manager directly",
            None,
        )

    def do_command_line(self, command_line):
        options = command_line.get_options_dict()
        if options.contains("monitors"):
            self._direct_monitor = True
        self.activate()
        return 0

    def do_activate(self):
        # If already running, present existing window
        win = self.get_active_window()
        if win:
            win.present()
            return

        if self._direct_monitor:
            win = MonitorWindow(self)
        else:
            win = MainWindow(self)

        win.present()


def main() -> None:
    app = WaybarToolkitApp()
    app.run(sys.argv)


if __name__ == "__main__":
    main()
