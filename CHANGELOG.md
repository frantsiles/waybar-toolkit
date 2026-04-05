# Changelog

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
