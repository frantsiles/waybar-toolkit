"""Monitor Manager window — view, identify, and configure monitors."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Pango  # noqa: E402

from waybar_toolkit.monitors.backend import Monitor, MonitorBackend, MonitorMode
from waybar_toolkit.monitors.monitor_canvas import MonitorCanvas
from waybar_toolkit.monitors.identify import show_identify
from waybar_toolkit.monitors.profiles import ProfileManager


CSS = """
.monitor-window {
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
.info-value {
    font-size: 12px;
    color: @window_fg_color;
}
.action-button {
    padding: 6px 16px;
    border-radius: 6px;
    font-size: 12px;
}
.apply-button {
    background-color: @accent_bg_color;
    color: @accent_fg_color;
}
.apply-button:hover {
    background-color: lighter(@accent_bg_color);
}
.identify-button {
    background-color: @card_bg_color;
    color: @window_fg_color;
}
.identify-button:hover {
    background-color: lighter(@card_bg_color);
}
.swap-button {
    background-color: @card_bg_color;
    color: @window_fg_color;
    min-width: 36px;
}
.swap-button:hover {
    background-color: lighter(@card_bg_color);
}
.status-bar {
    background-color: @headerbar_bg_color;
    padding: 4px 12px;
    font-size: 11px;
    color: alpha(@window_fg_color, 0.55);
}
"""


class MonitorWindow(Gtk.Window):
    """The Monitor Manager window."""

    def __init__(self, app: Gtk.Application) -> None:
        super().__init__(application=app, title="Monitor Manager")
        self.set_default_size(680, 520)
        self.add_css_class("monitor-window")

        self._app = app
        self._backend = MonitorBackend()
        self._monitors: list[Monitor] = []
        self._profiles = ProfileManager()

        # Load CSS
        css_provider = Gtk.CssProvider()
        css_provider.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        # Main layout
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_child(main_box)

        # --- Top: Canvas ---
        self._canvas = MonitorCanvas()
        self._canvas.set_content_height(220)
        self._canvas.connect_select(self._on_monitor_selected)
        main_box.append(self._canvas)

        # --- Toolbar: Identify + Swap ---
        toolbar = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=8, margin_start=12,
            margin_end=12, margin_top=8, margin_bottom=8,
        )
        main_box.append(toolbar)

        identify_btn = Gtk.Button(label="⬜ Identify")
        identify_btn.add_css_class("action-button")
        identify_btn.add_css_class("identify-button")
        identify_btn.connect("clicked", self._on_identify)
        toolbar.append(identify_btn)

        swap_left_btn = Gtk.Button(label="◀ Move Left")
        swap_left_btn.add_css_class("action-button")
        swap_left_btn.add_css_class("swap-button")
        swap_left_btn.connect("clicked", self._on_swap_left)
        toolbar.append(swap_left_btn)

        swap_right_btn = Gtk.Button(label="Move Right ▶")
        swap_right_btn.add_css_class("action-button")
        swap_right_btn.add_css_class("swap-button")
        swap_right_btn.connect("clicked", self._on_swap_right)
        toolbar.append(swap_right_btn)

        refresh_btn = Gtk.Button(label="↻ Refresh")
        refresh_btn.add_css_class("action-button")
        refresh_btn.add_css_class("identify-button")
        refresh_btn.connect("clicked", lambda *_: self._load_monitors())
        toolbar.append(refresh_btn)

        # Spacer
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        toolbar.append(spacer)

        # Profile dropdown
        profile_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        profile_label = Gtk.Label(label="Profile:")
        profile_label.add_css_class("info-label")
        profile_box.append(profile_label)

        self._profile_dropdown = Gtk.DropDown.new_from_strings(["(none)"])
        self._profile_dropdown.set_size_request(120, -1)
        profile_box.append(self._profile_dropdown)

        save_profile_btn = Gtk.Button(label="💾 Save")
        save_profile_btn.add_css_class("action-button")
        save_profile_btn.add_css_class("identify-button")
        save_profile_btn.connect("clicked", self._on_save_profile)
        profile_box.append(save_profile_btn)

        load_profile_btn = Gtk.Button(label="📂 Load")
        load_profile_btn.add_css_class("action-button")
        load_profile_btn.add_css_class("identify-button")
        load_profile_btn.connect("clicked", self._on_load_profile)
        profile_box.append(load_profile_btn)

        toolbar.append(profile_box)

        # --- Separator ---
        main_box.append(Gtk.Separator())

        # --- Controls panel ---
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        main_box.append(scroll)

        self._controls_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=8,
            margin_start=16, margin_end=16, margin_top=12, margin_bottom=12,
        )
        scroll.set_child(self._controls_box)

        # --- Bottom: Apply bar ---
        bottom_bar = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
            margin_start=12, margin_end=12, margin_top=8, margin_bottom=8,
        )
        main_box.append(Gtk.Separator())
        main_box.append(bottom_bar)

        self._status_label = Gtk.Label(label="Ready")
        self._status_label.add_css_class("status-bar")
        self._status_label.set_hexpand(True)
        self._status_label.set_halign(Gtk.Align.START)
        bottom_bar.append(self._status_label)

        apply_btn = Gtk.Button(label="✔ Apply")
        apply_btn.add_css_class("action-button")
        apply_btn.add_css_class("apply-button")
        apply_btn.connect("clicked", self._on_apply)
        bottom_bar.append(apply_btn)

        # Load monitors
        self._load_monitors()

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_monitors(self) -> None:
        """Fetch monitors from backend and update UI."""
        try:
            self._monitors = self._backend.get_monitors()
            self._monitors.sort(key=lambda m: m.x)
            self._canvas.set_monitors(self._monitors)
            self._update_controls(0)
            self._update_profiles_dropdown()
            self._set_status(f"{len(self._monitors)} monitor(s) detected")
        except Exception as e:
            self._set_status(f"Error: {e}")

    def _update_profiles_dropdown(self) -> None:
        names = self._profiles.list_profiles()
        if not names:
            names = ["(none)"]
        self._profile_dropdown.set_model(Gtk.StringList.new(names))

    # ------------------------------------------------------------------
    # Controls for selected monitor
    # ------------------------------------------------------------------

    def _update_controls(self, index: int) -> None:
        """Rebuild controls panel for the selected monitor."""
        # Clear existing
        child = self._controls_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self._controls_box.remove(child)
            child = next_child

        if not self._monitors or index >= len(self._monitors):
            return

        mon = self._monitors[index]

        # Title
        title = Gtk.Label(label=mon.display_name)
        title.add_css_class("section-title")
        title.set_halign(Gtk.Align.START)
        self._controls_box.append(title)

        # Info grid
        grid = Gtk.Grid(column_spacing=16, row_spacing=6)
        self._controls_box.append(grid)

        row = 0

        # Output name
        grid.attach(_label("Output:"), 0, row, 1, 1)
        grid.attach(_value(mon.name), 1, row, 1, 1)
        row += 1

        # Position
        grid.attach(_label("Position:"), 0, row, 1, 1)
        grid.attach(_value(f"{mon.x}, {mon.y}"), 1, row, 1, 1)
        row += 1

        # Resolution / mode dropdown
        grid.attach(_label("Resolution:"), 0, row, 1, 1)
        mode_strings = [m.label for m in mon.modes]
        if not mode_strings:
            mode_strings = [f"{mon.width}x{mon.height}@{mon.refresh_rate:.0f}Hz"]

        mode_dropdown = Gtk.DropDown.new_from_strings(mode_strings)

        # Select current mode
        current_label = f"{mon.width}x{mon.height}@{mon.refresh_rate:.0f}Hz"
        for i, ms in enumerate(mode_strings):
            if ms == current_label:
                mode_dropdown.set_selected(i)
                break

        mode_dropdown.connect("notify::selected", self._on_mode_changed, index)
        grid.attach(mode_dropdown, 1, row, 1, 1)
        row += 1

        # Scale
        grid.attach(_label("Scale:"), 0, row, 1, 1)
        scale_adj = Gtk.Adjustment(
            value=mon.scale, lower=0.5, upper=3.0, step_increment=0.25
        )
        scale_spin = Gtk.SpinButton(adjustment=scale_adj, digits=2)
        scale_spin.connect("value-changed", self._on_scale_changed, index)
        grid.attach(scale_spin, 1, row, 1, 1)
        row += 1

        # Transform
        grid.attach(_label("Transform:"), 0, row, 1, 1)
        transforms = ["Normal", "90°", "180°", "270°", "Flipped", "Flipped 90°", "Flipped 180°", "Flipped 270°"]
        transform_dropdown = Gtk.DropDown.new_from_strings(transforms)
        transform_dropdown.set_selected(mon.transform)
        transform_dropdown.connect(
            "notify::selected", self._on_transform_changed, index
        )
        grid.attach(transform_dropdown, 1, row, 1, 1)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_monitor_selected(self, index: int) -> None:
        self._update_controls(index)

    def _on_mode_changed(self, dropdown, _pspec, mon_index: int) -> None:
        if mon_index >= len(self._monitors):
            return
        mon = self._monitors[mon_index]
        selected = dropdown.get_selected()
        if selected < len(mon.modes):
            mode = mon.modes[selected]
            mon.width = mode.width
            mon.height = mode.height
            mon.refresh_rate = mode.refresh
            self._canvas.queue_draw()

    def _on_scale_changed(self, spin, mon_index: int) -> None:
        if mon_index >= len(self._monitors):
            return
        self._monitors[mon_index].scale = spin.get_value()
        # Recalculate positions
        self._recalculate_positions()
        self._canvas.queue_draw()

    def _on_transform_changed(self, dropdown, _pspec, mon_index: int) -> None:
        if mon_index >= len(self._monitors):
            return
        self._monitors[mon_index].transform = dropdown.get_selected()
        self._canvas.queue_draw()

    def _on_identify(self, *_args) -> None:
        show_identify(self._app, self._monitors)

    def _on_swap_left(self, *_args) -> None:
        idx = self._canvas.get_selected()
        sorted_mons = sorted(enumerate(self._monitors), key=lambda t: t[1].x)
        pos = next((i for i, (orig_i, _) in enumerate(sorted_mons) if orig_i == idx), -1)
        if pos > 0:
            other_idx = sorted_mons[pos - 1][0]
            self._monitors = self._backend.swap_positions(
                self._monitors, idx, other_idx
            )
            self._canvas.set_monitors(self._monitors)
            # Keep selection on the same monitor
            new_idx = self._monitors.index(self._monitors[idx]) if idx < len(self._monitors) else 0
            self._canvas.set_selected(new_idx)
            self._update_controls(new_idx)
            self._set_status("Swapped — click Apply to confirm")

    def _on_swap_right(self, *_args) -> None:
        idx = self._canvas.get_selected()
        sorted_mons = sorted(enumerate(self._monitors), key=lambda t: t[1].x)
        pos = next((i for i, (orig_i, _) in enumerate(sorted_mons) if orig_i == idx), -1)
        if pos < len(sorted_mons) - 1:
            other_idx = sorted_mons[pos + 1][0]
            self._monitors = self._backend.swap_positions(
                self._monitors, idx, other_idx
            )
            self._canvas.set_monitors(self._monitors)
            new_idx = self._monitors.index(self._monitors[idx]) if idx < len(self._monitors) else 0
            self._canvas.set_selected(new_idx)
            self._update_controls(new_idx)
            self._set_status("Swapped — click Apply to confirm")

    def _on_apply(self, *_args) -> None:
        try:
            self._backend.apply_all(self._monitors)
            self._set_status("✔ Configuration applied!")
            # Refresh after a short delay to get the actual state
            GLib.timeout_add(500, self._load_monitors)
        except Exception as e:
            self._set_status(f"✘ Error applying: {e}")

    def _on_save_profile(self, *_args) -> None:
        dialog = _PromptDialog(self, "Save Profile", "Profile name:")
        dialog.connect("response", self._on_save_profile_response)
        dialog.present()

    def _on_save_profile_response(self, dialog, response_id) -> None:
        if response_id == "ok":
            name = dialog.get_text()
            if name:
                self._profiles.save(name, self._monitors)
                self._update_profiles_dropdown()
                self._set_status(f"Profile '{name}' saved")
        dialog.close()

    def _on_load_profile(self, *_args) -> None:
        selected = self._profile_dropdown.get_selected()
        model = self._profile_dropdown.get_model()
        if model and selected < model.get_n_items():
            name = model.get_string(selected)
            if name and name != "(none)":
                loaded = self._profiles.load(name, self._monitors)
                if loaded:
                    self._monitors = loaded
                    self._canvas.set_monitors(self._monitors)
                    self._update_controls(0)
                    self._set_status(f"Profile '{name}' loaded — click Apply to confirm")
                else:
                    self._set_status(f"Could not load profile '{name}'")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _recalculate_positions(self) -> None:
        """Recalculate X positions after scale change."""
        sorted_mons = sorted(self._monitors, key=lambda m: m.x)
        x = 0
        for mon in sorted_mons:
            mon.x = x
            x += mon.scaled_width

    def _set_status(self, text: str) -> None:
        self._status_label.set_text(text)


# ------------------------------------------------------------------
# Helper widgets
# ------------------------------------------------------------------


def _label(text: str) -> Gtk.Label:
    lbl = Gtk.Label(label=text)
    lbl.add_css_class("info-label")
    lbl.set_halign(Gtk.Align.END)
    return lbl


def _value(text: str) -> Gtk.Label:
    lbl = Gtk.Label(label=text)
    lbl.add_css_class("info-value")
    lbl.set_halign(Gtk.Align.START)
    return lbl


class _PromptDialog(Gtk.Window):
    """Simple text input dialog."""

    def __init__(self, parent: Gtk.Window, title: str, label: str) -> None:
        super().__init__(
            title=title,
            transient_for=parent,
            modal=True,
            default_width=300,
            default_height=120,
        )

        self._response_callback = None
        self._response_id = "cancel"

        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=12,
            margin_start=16, margin_end=16, margin_top=16, margin_bottom=16,
        )
        self.set_child(box)

        lbl = Gtk.Label(label=label)
        lbl.set_halign(Gtk.Align.START)
        box.append(lbl)

        self._entry = Gtk.Entry()
        self._entry.set_placeholder_text("e.g. docked, gaming, default")
        self._entry.connect("activate", self._on_ok)
        box.append(self._entry)

        btn_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=8, halign=Gtk.Align.END
        )
        box.append(btn_box)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", self._on_cancel)
        btn_box.append(cancel_btn)

        ok_btn = Gtk.Button(label="Save")
        ok_btn.add_css_class("apply-button")
        ok_btn.connect("clicked", self._on_ok)
        btn_box.append(ok_btn)

    def connect(self, signal: str, callback):
        if signal == "response":
            self._response_callback = callback
        return self

    def _on_ok(self, *_args):
        self._response_id = "ok"
        if self._response_callback:
            self._response_callback(self, "ok")

    def _on_cancel(self, *_args):
        self._response_id = "cancel"
        if self._response_callback:
            self._response_callback(self, "cancel")

    def get_text(self) -> str:
        return self._entry.get_text().strip()
