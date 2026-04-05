# 🔧 Waybar Toolkit

A utility hub for Wayland compositors (Hyprland, Sway, wlroots-based) with Waybar integration.

Built with **Python + GTK4**. Manage your monitors, identify displays, swap positions, and save layout profiles — all from a clean GUI or directly from your Waybar.

## Features

### Process Manager
- **Real-time system stats** — Live CPU and RAM charts with 2-minute history (Cairo rendering)
- **Process list** — View all running processes with PID, name, user, CPU%, MEM%, and state
- **Three view modes**:
  - **Flat** — Sortable list (click column headers to sort by any field)
  - **Tree** — Hierarchical parent→child view with expand/collapse
  - **By User** — Grouped by user with collapsible sections and per-group stats
- **Search & filter** — Instant search by process name, command, user, or PID
- **Send signals** — SIGTERM, SIGKILL, SIGSTOP, SIGCONT, SIGHUP to selected process
- **Process details** — Full command line, executable path, working directory, threads, memory, open FDs, context switches
- **Waybar stats module** — `custom/stats` showing CPU/RAM in the bar with rich tooltip
- **No external dependencies** — reads directly from `/proc` (no `psutil` required)

### Monitor Manager
- **Visual layout** — See your monitors as proportional rectangles with resolution, scale, and model info
- **Identify** — Flash a big number on each display (like Windows/KDE Plasma)
- **Drag & drop reorder** — Grab a monitor and drag it to swap positions
- **Swap positions** — Move monitors left/right with toolbar buttons
- **Brightness control** — Adjust brightness per monitor in real time
  - Laptop (eDP): via `brightnessctl` (backlight)
  - External monitors: via `ddcutil` (DDC/CI) — see [Known Limitations](#known-limitations)
- **Contrast control** — Adjust contrast on DDC/CI-capable external monitors
- **Configure** — Change resolution, refresh rate, scale, and transform per monitor
- **Apply** — Instantly apply changes via `hyprctl` or `wlr-randr`
- **Profiles** — Save and load named monitor layouts (e.g. "docked", "gaming")

### Waybar Integration
- Custom Waybar module with one-click access
- Left-click opens the utility hub, right-click opens Monitor Manager directly

## Screenshots

*Coming soon*

## Requirements

- Python 3.10+
- GTK4 with PyGObject (`python-gobject`, `gtk4`)
- One of:
  - **Hyprland** (uses `hyprctl`)
  - **wlr-randr** (for Sway or other wlroots compositors)
- Optional (for brightness/contrast):
  - `brightnessctl` — laptop backlight control
  - `ddcutil` — external monitor DDC/CI control

## Installation

### Arch Linux

```bash
# Install dependencies
sudo pacman -S python-gobject gtk4

# Clone and install
git clone https://github.com/frantsiles/waybar-toolkit.git
cd waybar-toolkit
pip install --user --break-system-packages .
```

Or use the install script:

```bash
./scripts/install.sh
```

### From source (any distro)

```bash
git clone https://github.com/frantsiles/waybar-toolkit.git
cd waybar-toolkit
pip install --user .
```

## Usage

```bash
# Open the utility hub
waybar-toolkit

# Open Monitor Manager directly
waybar-toolkit -m
waybar-toolkit --monitors

# Open Process Manager directly
waybar-toolkit -p
waybar-toolkit --processes

# Print system stats as JSON (for Waybar)
waybar-toolkit-stats
```

## Waybar Configuration

Add to your Waybar config (`~/.config/waybar/config.jsonc`):

1. Add `"custom/toolkit"` and/or `"custom/stats"` to your modules array (e.g. `"modules-right"`)
2. Add the module definitions:

```json
"custom/toolkit": {
    "format": "🔧",
    "tooltip": true,
    "tooltip-format": "Waybar Toolkit",
    "on-click": "waybar-toolkit",
    "on-click-right": "waybar-toolkit --monitors",
    "on-click-middle": "waybar-toolkit --processes"
},
"custom/stats": {
    "exec": "waybar-toolkit-stats",
    "return-type": "json",
    "interval": 2,
    "tooltip": true,
    "on-click": "waybar-toolkit --processes"
}
```

## Monitor Profiles

Profiles are saved in `~/.config/waybar-toolkit/profiles/` as JSON files. They store position, resolution, scale, and transform for each monitor by output name.

This is useful when you frequently switch between setups (e.g. docking/undocking a laptop, switching a monitor between PC and a game console).

## Project Structure

```
waybar_toolkit/
├── app.py                    # GTK Application + CLI entry point
├── main_window.py            # Utility hub window
├── monitors/
│   ├── backend.py            # hyprctl/wlr-randr abstraction
│   ├── brightness.py         # Brightness/contrast (brightnessctl + ddcutil)
│   ├── monitor_canvas.py     # Visual monitor layout (Cairo)
│   ├── monitor_window.py     # Monitor Manager window
│   ├── identify.py           # Identify overlay per monitor
│   └── profiles.py           # Save/load monitor profiles
├── processes/
│   ├── backend.py            # /proc reader, signals, system stats
│   ├── charts.py             # Real-time CPU/RAM charts (Cairo)
│   ├── process_window.py     # Process Manager window
│   ├── tree.py               # Process tree & user grouping
│   └── waybar_stats.py       # JSON output for Waybar module
└── utils/
    └── compositor.py         # Compositor detection
```

## Known Limitations

### NVIDIA + DDC/CI (external monitor brightness/contrast)

On systems with **NVIDIA proprietary drivers**, `ddcutil` can **read** DDC/CI values (brightness, contrast) from external monitors but **cannot write** them. This is a known NVIDIA driver limitation that also affects Waybar's built-in backlight module — it only works on the laptop's primary display (eDP), not on external monitors.

This means:
- **Laptop display (eDP)**: Brightness slider works perfectly via `brightnessctl`
- **External monitors (HDMI/DP)**: Brightness and contrast sliders are displayed and read the current values, but changes will not take effect on NVIDIA

**Workaround options:**
- Install `ddcci-driver-linux-dkms` (AUR) which creates kernel backlight devices for external monitors, bypassing the `ddcutil` write issue
- Use the monitor's physical OSD buttons to adjust brightness/contrast
- On AMD/Intel GPUs, `ddcutil` write should work without issues

## Built With AI Assistance

This project was built with the help of **Oz (Warp AI)** as a development assistant. The architecture, code, and implementation were produced collaboratively — the author provided the vision, requirements, and testing, while the AI assisted with Python/GTK4 code generation.

Transparency matters. This is open source because the goal is to help the Wayland/Hyprland community, not to take credit for work that isn't entirely manual.

## Contributing

Contributions are welcome! Feel free to open issues or PRs.

## License

MIT — see [LICENSE](LICENSE)
