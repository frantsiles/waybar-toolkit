# Changelog
## [Unreleased]
## [0.3.2] - 2026-04-05

### Added
- Baseline quality tooling configuration for `pytest`, `ruff`, and `mypy` in project metadata.
- Initial unit tests for process tree/grouping logic and backend helper behavior.

### Changed
- Contributor workflow now includes explicit lint, format, test, and typecheck commands.
- Process refresh now reduces per-cycle `/proc` overhead by caching static per-PID metadata and using lighter dynamic reads.

### Fixed
- Replaced broad UI `except Exception` handling in critical monitor/process paths with domain-specific backend errors plus structured logging for unexpected failures.
## [0.3.1] - 2026-04-05

### Fixed
- Monitor swap selection logic now preserves the selected monitor by identity after drag-and-drop and left/right swaps, avoiding incorrect selection due to list reordering.

### Changed
- Added project contribution guidelines for human and AI contributors, including mandatory safety and quality rules for AI-generated code changes.

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
- Brightness control per monitor
  - Laptop displays (eDP): via `brightnessctl` backlight
  - External monitors: via `ddcutil` DDC/CI
  - Real-time slider with debounced apply (50ms backlight, 300ms DDC)
- Contrast control for DDC/CI-capable external monitors
- New `brightness.py` backend with auto-detection of backlight and DDC devices
- Visual section "☀ Brightness & Display" in monitor controls panel
- Graceful fallback: shows "not available" for unsupported displays

### Known Issues
- DDC/CI write operations do not work on NVIDIA proprietary drivers (brightness/contrast read-only on external monitors). This is an upstream NVIDIA driver limitation that also affects Waybar's backlight module. Workaround: install `ddcci-driver-linux-dkms` from AUR or use the monitor's physical OSD buttons.

## [0.1.1] - 2026-04-05

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
