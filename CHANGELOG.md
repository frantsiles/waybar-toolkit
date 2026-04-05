# Changelog

## [0.3.0] - 2026-04-05

### Added
- **Process Manager** — Full-featured process viewer and manager
  - Real-time CPU and RAM charts with ~2min history (Cairo rendering)
  - Three view modes: Flat (sortable), Tree (hierarchical), By User (grouped)
  - Clickable column headers for sorting by PID, Name, User, CPU%, MEM%, State
  - Search/filter by process name, command, user, or PID
  - Send signals to processes: SIGTERM, SIGKILL, SIGSTOP, SIGCONT, SIGHUP
  - Detailed process info panel: cmdline, exe, cwd, threads, memory, FDs, context switches
  - Auto-refresh every 2 seconds
- **Waybar stats module** (`custom/stats`)
  - Shows live CPU/RAM usage in Waybar bar text
  - Rich tooltip with CPU%, RAM usage, process count, load average, uptime
  - CSS classes for conditional styling: `normal`, `warning`, `critical`
  - Entry point: `waybar-toolkit-stats`
- New CLI flag `-p` / `--processes` to open Process Manager directly
- Middle-click on toolkit Waybar module opens Process Manager
- Process backend reads directly from `/proc` — no `psutil` dependency

## [0.2.0] - 2026-04-05

### Added
- Drag-and-drop monitor reordering in visual layout
  - Grab any monitor and drag it to swap with its neighbor
  - Visual feedback: drag shadow, drop indicator line, grab cursor
  - 6px drag threshold to distinguish clicks from drags

## [0.1.0] - 2026-04-05

### Added
- Initial release
- Monitor Manager utility
  - Visual monitor layout with Cairo rendering
  - Identify monitors (fullscreen overlay, auto-dismiss)
  - Swap monitor positions (left/right)
  - Change resolution, refresh rate, scale, transform
  - Apply changes via hyprctl (Hyprland) or wlr-randr (generic)
  - Save/load named monitor profiles
- Utility hub window with extensible grid layout
- Waybar custom module integration
- CLI support (`waybar-toolkit`, `waybar-toolkit -m`)
- Hyprland and generic wlroots compositor support
