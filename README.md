# 🔧 Waybar Toolkit

A utility hub for Wayland compositors (Hyprland, Sway, wlroots-based) with Waybar integration.

Built with **Python + GTK4**. Manage your monitors, identify displays, swap positions, and save layout profiles — all from a clean GUI or directly from your Waybar.

## Features

### Monitor Manager
- **Visual layout** — See your monitors as proportional rectangles with resolution, scale, and model info
- **Identify** — Flash a big number on each display (like Windows/KDE Plasma)
- **Drag & drop reorder** — Grab a monitor and drag it to swap positions
- **Swap positions** — Move monitors left/right with toolbar buttons
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
```

## Waybar Configuration

Add to your Waybar config (`~/.config/waybar/config.jsonc`):

1. Add `"custom/toolkit"` to your modules array (e.g. `"modules-right"`)
2. Add the module definition:

```json
"custom/toolkit": {
    "format": "🔧",
    "tooltip": true,
    "tooltip-format": "Waybar Toolkit",
    "on-click": "waybar-toolkit",
    "on-click-right": "waybar-toolkit --monitors"
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
│   ├── monitor_canvas.py     # Visual monitor layout (Cairo)
│   ├── monitor_window.py     # Monitor Manager window
│   ├── identify.py           # Identify overlay per monitor
│   └── profiles.py           # Save/load monitor profiles
└── utils/
    └── compositor.py         # Compositor detection
```

## Built With AI Assistance

This project was built with the help of **Oz (Warp AI)** as a development assistant. The architecture, code, and implementation were produced collaboratively — the author provided the vision, requirements, and testing, while the AI assisted with Python/GTK4 code generation.

Transparency matters. This is open source because the goal is to help the Wayland/Hyprland community, not to take credit for work that isn't entirely manual.

## Contributing

Contributions are welcome! Feel free to open issues or PRs.

## License

MIT — see [LICENSE](LICENSE)
