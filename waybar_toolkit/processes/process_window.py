"""Process Manager window — view, search, and manage running processes."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, GObject, Gio, Pango  # noqa: E402

from waybar_toolkit.processes.backend import (
    ProcessBackend,
    ProcessInfo,
    SIGNALS,
)
from waybar_toolkit.processes.charts import CpuChart, MemChart
from waybar_toolkit.processes.tree import (
    build_process_tree,
    flatten_tree,
    group_by_user,
    FlatRow,
    UserGroup,
)


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

CSS = """
.process-window {
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
.toolbar-button {
    background-color: @card_bg_color;
    color: @window_fg_color;
}
.toolbar-button:hover {
    background-color: lighter(@card_bg_color);
}
.danger-button {
    background-color: #c0392b;
    color: white;
}
.danger-button:hover {
    background-color: #e74c3c;
}
.status-bar {
    background-color: @headerbar_bg_color;
    padding: 4px 12px;
    font-size: 11px;
    color: alpha(@window_fg_color, 0.55);
}
.chart-box {
    margin: 8px 12px 4px 12px;
}
.search-entry {
    min-width: 200px;
    font-size: 12px;
}
.process-row {
    padding: 4px 8px;
    font-size: 12px;
}
.process-row:hover {
    background-color: alpha(@accent_bg_color, 0.1);
}
.process-row-selected {
    background-color: alpha(@accent_bg_color, 0.2);
}
.col-header {
    font-size: 11px;
    font-weight: bold;
    color: alpha(@window_fg_color, 0.7);
    padding: 4px 8px;
}
.col-header:hover {
    color: @window_fg_color;
}
.details-box {
    background-color: @card_bg_color;
    border-radius: 8px;
    padding: 10px 12px;
    margin: 4px 12px 8px 12px;
}
.details-title {
    font-size: 12px;
    font-weight: bold;
    color: @window_fg_color;
}
.details-value {
    font-size: 11px;
    color: alpha(@window_fg_color, 0.7);
    font-family: monospace;
}
.tree-indent {
    color: alpha(@window_fg_color, 0.3);
    font-family: monospace;
    font-size: 12px;
}
.group-header {
    font-size: 12px;
    font-weight: bold;
    padding: 6px 8px;
    background-color: alpha(@accent_bg_color, 0.08);
    border-radius: 4px;
}
.cpu-high {
    color: #e74c3c;
}
.cpu-medium {
    color: #f39c12;
}
"""

# View modes
VIEW_FLAT = "Flat"
VIEW_TREE = "Tree"
VIEW_USER = "By User"

# Sort columns
SORT_PID = "PID"
SORT_NAME = "Name"
SORT_USER = "User"
SORT_CPU = "CPU%"
SORT_MEM = "MEM%"
SORT_STATE = "State"

# Refresh interval (ms)
REFRESH_MS = 2000

class ProcessListItem(GObject.Object):
    """Typed item for the process list model."""

    def __init__(
        self,
        kind: str,
        process: ProcessInfo | None = None,
        group: UserGroup | None = None,
        depth: int = 0,
        has_children: bool = False,
        expanded: bool = True,
    ) -> None:
        super().__init__()
        self.kind = kind
        self.process = process
        self.group = group
        self.depth = depth
        self.has_children = has_children
        self.expanded = expanded


class ProcessWindow(Gtk.Window):
    """The Process Manager window."""

    def __init__(self, app: Gtk.Application) -> None:
        super().__init__(application=app, title="Process Manager")
        self.set_default_size(780, 620)
        self.add_css_class("process-window")

        self._app = app
        self._backend = ProcessBackend()
        self._processes: list[ProcessInfo] = []
        self._selected_pid: int = -1
        self._view_mode: str = VIEW_FLAT
        self._sort_col: str = SORT_CPU
        self._sort_asc: bool = False
        self._search_text: str = ""
        self._collapsed_pids: set[int] = set()
        self._collapsed_users: set[str] = set()
        self._is_rebuilding_list: bool = False
        self._refresh_id: int = 0

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

        # --- Charts ---
        charts_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=8
        )
        charts_box.add_css_class("chart-box")
        main_box.append(charts_box)

        self._cpu_chart = CpuChart()
        self._mem_chart = MemChart()
        charts_box.append(self._cpu_chart)
        charts_box.append(self._mem_chart)

        # --- Toolbar ---
        toolbar = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
            margin_start=12,
            margin_end=12,
            margin_top=4,
            margin_bottom=4,
        )
        main_box.append(toolbar)

        # Search
        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_placeholder_text("Search processes...")
        self._search_entry.add_css_class("search-entry")
        self._search_entry.connect("search-changed", self._on_search_changed)
        toolbar.append(self._search_entry)

        # View mode dropdown
        view_label = Gtk.Label(label="View:")
        view_label.add_css_class("info-label")
        toolbar.append(view_label)

        self._view_dropdown = Gtk.DropDown.new_from_strings(
            [VIEW_FLAT, VIEW_TREE, VIEW_USER]
        )
        self._view_dropdown.set_selected(0)
        self._view_dropdown.connect("notify::selected", self._on_view_changed)
        toolbar.append(self._view_dropdown)

        # Spacer
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        toolbar.append(spacer)

        # Signal dropdown
        sig_label = Gtk.Label(label="Signal:")
        sig_label.add_css_class("info-label")
        toolbar.append(sig_label)

        self._signal_dropdown = Gtk.DropDown.new_from_strings(
            list(SIGNALS.keys())
        )
        self._signal_dropdown.set_selected(0)  # SIGTERM
        toolbar.append(self._signal_dropdown)

        # Send signal button
        kill_btn = Gtk.Button(label="Send Signal")
        kill_btn.add_css_class("action-button")
        kill_btn.add_css_class("danger-button")
        kill_btn.connect("clicked", self._on_send_signal)
        toolbar.append(kill_btn)

        # Refresh button
        refresh_btn = Gtk.Button(label="↻")
        refresh_btn.add_css_class("action-button")
        refresh_btn.add_css_class("toolbar-button")
        refresh_btn.set_tooltip_text("Refresh now")
        refresh_btn.connect("clicked", lambda *_: self._refresh())
        toolbar.append(refresh_btn)

        # --- Separator ---
        main_box.append(Gtk.Separator())

        # --- Column headers ---
        self._headers_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=0,
            margin_start=12,
            margin_end=12,
        )
        main_box.append(self._headers_box)
        self._build_headers()

        # --- Process list ---
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        main_box.append(scroll)

        self._list_store = Gio.ListStore.new(ProcessListItem)
        self._selection_model = Gtk.SingleSelection(model=self._list_store)
        self._selection_model.set_autoselect(False)
        self._selection_model.connect(
            "notify::selected-item", self._on_selected_item_changed
        )

        self._list_factory = Gtk.SignalListItemFactory()
        self._list_factory.connect("bind", self._on_bind_list_item)

        self._list_view = Gtk.ListView(
            model=self._selection_model,
            factory=self._list_factory,
        )
        self._list_view.set_vexpand(True)
        scroll.set_child(self._list_view)

        # --- Separator ---
        main_box.append(Gtk.Separator())

        # --- Details panel ---
        self._details_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=4
        )
        self._details_box.add_css_class("details-box")
        main_box.append(self._details_box)

        # --- Status bar ---
        self._status_label = Gtk.Label(label="Loading...")
        self._status_label.add_css_class("status-bar")
        self._status_label.set_halign(Gtk.Align.START)
        self._status_label.set_hexpand(True)
        main_box.append(self._status_label)

        # Initial load and start refresh timer
        self._refresh()
        self._refresh_id = GLib.timeout_add(REFRESH_MS, self._on_tick)

        # Stop timer when window closes
        self.connect("close-request", self._on_close)

    # ------------------------------------------------------------------
    # Column headers
    # ------------------------------------------------------------------

    def _build_headers(self) -> None:
        """Build clickable column headers."""
        child = self._headers_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._headers_box.remove(child)
            child = nxt

        columns = [
            (SORT_PID, 70),
            (SORT_NAME, 180),
            (SORT_USER, 90),
            (SORT_CPU, 70),
            (SORT_MEM, 70),
            (SORT_STATE, 60),
        ]
        for col_name, width in columns:
            arrow = ""
            if col_name == self._sort_col:
                arrow = " ▲" if self._sort_asc else " ▼"
            btn = Gtk.Button(label=f"{col_name}{arrow}")
            btn.add_css_class("col-header")
            btn.set_size_request(width, -1)
            btn.set_hexpand(col_name == SORT_NAME)
            btn.connect("clicked", self._on_header_clicked, col_name)
            self._headers_box.append(btn)

    # ------------------------------------------------------------------
    # Refresh cycle
    # ------------------------------------------------------------------

    def _on_tick(self) -> bool:
        """Periodic refresh callback."""
        self._refresh()
        return True  # Keep timer alive

    def _refresh(self) -> None:
        """Fetch processes and system stats, update everything."""
        try:
            self._processes = self._backend.get_processes()
            stats = self._backend.get_system_stats()

            # Update charts
            self._cpu_chart.push(
                stats.cpu_percent_total, stats.cpu_percent_per_core
            )
            self._mem_chart.push(
                stats.mem_used_kb, stats.mem_cached_kb, stats.mem_total_kb
            )

            # Update list
            self._rebuild_list()

            # Update status
            uptime = self._backend.format_uptime(stats.uptime_seconds)
            load = ", ".join(f"{l:.2f}" for l in stats.load_avg)
            self._set_status(
                f"{stats.process_count} processes | "
                f"CPU {stats.cpu_percent_total:.1f}% | "
                f"RAM {stats.mem_used_kb // 1024}MB / "
                f"{stats.mem_total_kb // 1024}MB | "
                f"Load: {load} | Up: {uptime}"
            )
        except Exception as e:
            self._set_status(f"Error: {e}")

    # ------------------------------------------------------------------
    # List building
    # ------------------------------------------------------------------

    def _rebuild_list(self) -> None:
        """Rebuild the process list based on view mode, sort, and filter."""
        selected_pid = self._selected_pid
        self._is_rebuilding_list = True
        # Clear
        self._list_store.remove_all()

        # Filter
        filtered = self._filter_processes(self._processes)

        if self._view_mode == VIEW_TREE:
            self._build_tree_view(filtered)
        elif self._view_mode == VIEW_USER:
            self._build_user_view(filtered)
        else:
            self._build_flat_view(filtered)

        # Preserve previous selection when possible
        selected_index = Gtk.INVALID_LIST_POSITION
        for i in range(self._list_store.get_n_items()):
            item = self._list_store.get_item(i)
            if (
                isinstance(item, ProcessListItem)
                and item.kind == "process"
                and item.process is not None
                and item.process.pid == selected_pid
            ):
                selected_index = i
                break

        self._selection_model.set_selected(selected_index)
        self._is_rebuilding_list = False

        # Keep details panel populated even if the selected process is not
        # currently visible in the active view/filter.
        if selected_pid > 0:
            self._selected_pid = selected_pid

    def _filter_processes(
        self, procs: list[ProcessInfo]
    ) -> list[ProcessInfo]:
        """Filter processes by search text."""
        if not self._search_text:
            return procs
        query = self._search_text.lower()
        return [
            p
            for p in procs
            if query in p.name.lower()
            or query in p.cmdline.lower()
            or query in p.user.lower()
            or query in str(p.pid)
        ]

    def _sort_processes(
        self, procs: list[ProcessInfo]
    ) -> list[ProcessInfo]:
        """Sort processes by the current sort column."""
        key_map = {
            SORT_PID: lambda p: p.pid,
            SORT_NAME: lambda p: p.name.lower(),
            SORT_USER: lambda p: p.user.lower(),
            SORT_CPU: lambda p: p.cpu_percent,
            SORT_MEM: lambda p: p.mem_percent,
            SORT_STATE: lambda p: p.state,
        }
        key_fn = key_map.get(self._sort_col, lambda p: p.cpu_percent)
        return sorted(procs, key=key_fn, reverse=not self._sort_asc)

    def _build_flat_view(self, procs: list[ProcessInfo]) -> None:
        """Build a flat, sorted list."""
        sorted_procs = self._sort_processes(procs)
        for proc in sorted_procs:
            self._list_store.append(
                ProcessListItem(kind="process", process=proc)
            )

    def _build_tree_view(self, procs: list[ProcessInfo]) -> None:
        """Build a tree view with indentation."""
        roots = build_process_tree(procs)
        flat_rows = flatten_tree(roots, self._collapsed_pids)
        for flat_row in flat_rows:
            self._list_store.append(
                ProcessListItem(
                    kind="process",
                    process=flat_row.process,
                    depth=flat_row.depth,
                    has_children=flat_row.has_children,
                    expanded=flat_row.expanded,
                )
            )

    def _build_user_view(self, procs: list[ProcessInfo]) -> None:
        """Build a grouped-by-user view."""
        groups = group_by_user(procs)
        for group in groups:
            is_collapsed = group.user in self._collapsed_users

            # Group header row
            self._list_store.append(
                ProcessListItem(
                    kind="group",
                    group=group,
                    expanded=not is_collapsed,
                )
            )

            if not is_collapsed:
                sorted_procs = self._sort_processes(group.processes)
                for proc in sorted_procs:
                    self._list_store.append(
                        ProcessListItem(
                            kind="process", process=proc, depth=1
                        )
                    )

    # ------------------------------------------------------------------
    # Row widgets
    # ------------------------------------------------------------------

    def _on_bind_list_item(
        self,
        _factory: Gtk.SignalListItemFactory,
        list_item: Gtk.ListItem,
    ) -> None:
        """Bind model item to a row widget in the ListView."""
        item = list_item.get_item()
        if not isinstance(item, ProcessListItem):
            list_item.set_child(None)
            return

        if item.kind == "group" and item.group is not None:
            child = self._make_group_header_widget(item.group, item.expanded)
        elif item.process is not None:
            child = self._make_process_row_widget(
                item.process,
                depth=item.depth,
                has_children=item.has_children,
                expanded=item.expanded,
            )
        else:
            child = Gtk.Box()

        list_item.set_child(child)

    def _make_process_row_widget(
        self,
        proc: ProcessInfo,
        depth: int = 0,
        has_children: bool = False,
        expanded: bool = True,
    ) -> Gtk.Widget:
        """Create a row widget for a process."""

        box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=0
        )
        box.add_css_class("process-row")

        # PID column
        pid_label = Gtk.Label(label=str(proc.pid))
        pid_label.set_size_request(70, -1)
        pid_label.set_halign(Gtk.Align.START)
        pid_label.set_xalign(0)
        pid_label.add_css_class("info-value")
        box.append(pid_label)

        # Name column (with tree indent)
        name_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=2
        )
        name_box.set_size_request(180, -1)
        name_box.set_hexpand(True)

        if depth > 0:
            indent = "  " * depth
            tree_char = ""
            if self._view_mode == VIEW_TREE:
                if has_children:
                    tree_char = "▾ " if expanded else "▸ "
                else:
                    tree_char = "  "
            indent_label = Gtk.Label(label=f"{indent}{tree_char}")
            indent_label.add_css_class("tree-indent")
            name_box.append(indent_label)

            # Make tree nodes clickable to toggle expand/collapse
            if has_children and self._view_mode == VIEW_TREE:
                toggle_btn = Gtk.Button(label=proc.name)
                toggle_btn.add_css_class("info-value")
                toggle_btn.set_has_frame(False)
                toggle_btn.connect(
                    "clicked", self._on_toggle_tree_node, proc.pid
                )
                name_box.append(toggle_btn)
            else:
                name_label = Gtk.Label(label=proc.name)
                name_label.set_halign(Gtk.Align.START)
                name_label.set_xalign(0)
                name_label.set_ellipsize(Pango.EllipsizeMode.END)
                name_label.add_css_class("info-value")
                name_box.append(name_label)
        else:
            name_label = Gtk.Label(label=proc.name)
            name_label.set_halign(Gtk.Align.START)
            name_label.set_xalign(0)
            name_label.set_ellipsize(Pango.EllipsizeMode.END)
            name_label.add_css_class("info-value")
            name_box.append(name_label)

        box.append(name_box)

        # User column
        user_label = Gtk.Label(label=proc.user)
        user_label.set_size_request(90, -1)
        user_label.set_halign(Gtk.Align.START)
        user_label.set_xalign(0)
        user_label.set_ellipsize(Pango.EllipsizeMode.END)
        user_label.add_css_class("info-label")
        box.append(user_label)

        # CPU% column
        cpu_label = Gtk.Label(label=f"{proc.cpu_percent:.1f}%")
        cpu_label.set_size_request(70, -1)
        cpu_label.set_halign(Gtk.Align.END)
        cpu_label.set_xalign(1)
        cpu_label.add_css_class("info-value")
        if proc.cpu_percent >= 50:
            cpu_label.add_css_class("cpu-high")
        elif proc.cpu_percent >= 10:
            cpu_label.add_css_class("cpu-medium")
        box.append(cpu_label)

        # MEM% column
        mem_label = Gtk.Label(label=f"{proc.mem_percent:.1f}%")
        mem_label.set_size_request(70, -1)
        mem_label.set_halign(Gtk.Align.END)
        mem_label.set_xalign(1)
        mem_label.add_css_class("info-value")
        box.append(mem_label)

        # State column
        state_label = Gtk.Label(label=proc.state)
        state_label.set_size_request(60, -1)
        state_label.set_halign(Gtk.Align.CENTER)
        state_label.add_css_class("info-label")
        box.append(state_label)

        return box

    def _make_group_header_widget(
        self, group: UserGroup, expanded: bool
    ) -> Gtk.Widget:
        """Create a group header row for user view."""

        box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=8
        )
        box.add_css_class("group-header")

        arrow = "▾" if expanded else "▸"
        toggle_btn = Gtk.Button(label=f"{arrow} {group.user}")
        toggle_btn.set_has_frame(False)
        toggle_btn.add_css_class("section-title")
        toggle_btn.connect("clicked", self._on_toggle_user_group, group.user)
        box.append(toggle_btn)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        box.append(spacer)

        stats = Gtk.Label(
            label=f"{group.count} proc | CPU {group.total_cpu:.1f}% | MEM {group.total_mem:.1f}%"
        )
        stats.add_css_class("info-label")
        box.append(stats)

        return box

    # ------------------------------------------------------------------
    # Details panel
    # ------------------------------------------------------------------

    def _update_details(self, pid: int) -> None:
        """Show detailed info for the selected process."""
        # Clear
        child = self._details_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._details_box.remove(child)
            child = nxt

        if pid <= 0:
            return

        details = self._backend.get_process_details(pid)
        if not details:
            lbl = Gtk.Label(label=f"Process {pid} no longer exists")
            lbl.add_css_class("info-label")
            self._details_box.append(lbl)
            return

        title = Gtk.Label(label=f"Details — PID {pid}")
        title.add_css_class("details-title")
        title.set_halign(Gtk.Align.START)
        self._details_box.append(title)

        grid = Gtk.Grid(column_spacing=16, row_spacing=2)
        self._details_box.append(grid)

        row = 0
        fields = [
            ("Command", details.get("cmdline", "")),
            ("Executable", details.get("exe", "N/A")),
            ("Working Dir", details.get("cwd", "N/A")),
            ("Threads", details.get("Threads", "N/A")),
            ("VM Size", details.get("VmSize", "N/A")),
            ("VM RSS", details.get("VmRSS", "N/A")),
            ("VM Swap", details.get("VmSwap", "N/A")),
            ("Open FDs", str(details.get("open_fds", "N/A"))),
            ("Vol. Ctx Switches", details.get("voluntary_ctxt_switches", "N/A")),
            ("Invol. Ctx Switches", details.get("nonvoluntary_ctxt_switches", "N/A")),
        ]
        for label_text, value_text in fields:
            lbl = Gtk.Label(label=f"{label_text}:")
            lbl.add_css_class("info-label")
            lbl.set_halign(Gtk.Align.END)
            grid.attach(lbl, 0, row, 1, 1)

            val = Gtk.Label(label=str(value_text))
            val.add_css_class("details-value")
            val.set_halign(Gtk.Align.START)
            val.set_xalign(0)
            val.set_ellipsize(Pango.EllipsizeMode.END)
            val.set_max_width_chars(80)
            val.set_selectable(True)
            grid.attach(val, 1, row, 1, 1)
            row += 1

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        self._search_text = entry.get_text().strip()
        self._rebuild_list()

    def _on_view_changed(self, dropdown, _pspec) -> None:
        views = [VIEW_FLAT, VIEW_TREE, VIEW_USER]
        idx = dropdown.get_selected()
        if idx < len(views):
            self._view_mode = views[idx]
            self._rebuild_list()

    def _on_header_clicked(self, btn, col_name: str) -> None:
        if self._sort_col == col_name:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col_name
            # Default: descending for numeric, ascending for text
            self._sort_asc = col_name in (SORT_NAME, SORT_USER, SORT_STATE)
        self._build_headers()
        self._rebuild_list()

    def _on_selected_item_changed(self, model, _pspec) -> None:
        if self._is_rebuilding_list:
            return
        item = model.get_selected_item()
        if (
            isinstance(item, ProcessListItem)
            and item.kind == "process"
            and item.process is not None
        ):
            self._selected_pid = item.process.pid
            self._update_details(self._selected_pid)

    def _on_send_signal(self, *_args) -> None:
        if self._selected_pid <= 0:
            self._set_status("No process selected")
            return

        sig_names = list(SIGNALS.keys())
        idx = self._signal_dropdown.get_selected()
        if idx >= len(sig_names):
            return

        sig_name = sig_names[idx]
        sig_val = SIGNALS[sig_name]

        ok = self._backend.send_signal(self._selected_pid, sig_val)
        if ok:
            self._set_status(
                f"Sent {sig_name} to PID {self._selected_pid}"
            )
        else:
            self._set_status(
                f"Failed to send {sig_name} to PID {self._selected_pid} (permission denied?)"
            )

    def _on_toggle_tree_node(self, btn, pid: int) -> None:
        if pid in self._collapsed_pids:
            self._collapsed_pids.discard(pid)
        else:
            self._collapsed_pids.add(pid)
        self._rebuild_list()

    def _on_toggle_user_group(self, btn, user: str) -> None:
        if user in self._collapsed_users:
            self._collapsed_users.discard(user)
        else:
            self._collapsed_users.add(user)
        self._rebuild_list()

    def _on_close(self, *_args) -> None:
        if self._refresh_id:
            GLib.source_remove(self._refresh_id)
            self._refresh_id = 0
        return False  # Allow close

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_status(self, text: str) -> None:
        self._status_label.set_text(text)
