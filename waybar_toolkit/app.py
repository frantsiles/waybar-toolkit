"""Waybar Toolkit — main application entry point."""

from __future__ import annotations

import gi
import sys

gi.require_version("Gtk", "4")
from gi.repository import Gtk, Gio, GLib  # noqa: E402

from waybar_toolkit.main_window import MainWindow
from waybar_toolkit.monitors.monitor_window import MonitorWindow
from waybar_toolkit.processes.process_window import ProcessWindow
from waybar_toolkit.monitors.backend import MonitorBackend
from waybar_toolkit.monitors.gpu_backend import GPUBackend


APP_ID = "dev.waybar-toolkit"


class WaybarToolkitApp(Gtk.Application):
    """GTK4 application for Waybar Toolkit."""

    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self._direct_monitor = False
        self._direct_processes = False
        self.monitor_backend = MonitorBackend()
        self.gpu_backend = GPUBackend()

        # CLI options
        self.add_main_option(
            "monitors",
            ord("m"),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.NONE,
            "Open Monitor Manager directly",
            None,
        )
        self.add_main_option(
            "processes",
            ord("p"),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.NONE,
            "Open Process Manager directly",
            None,
        )

    def do_command_line(self, command_line):
        options = command_line.get_options_dict()
        if options.contains("monitors"):
            self._direct_monitor = True
        if options.contains("processes"):
            self._direct_processes = True
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
        elif self._direct_processes:
            win = ProcessWindow(self)
        else:
            win = MainWindow(self)

        win.present()


def main() -> None:
    app = WaybarToolkitApp()
    app.run(sys.argv)


if __name__ == "__main__":
    main()
