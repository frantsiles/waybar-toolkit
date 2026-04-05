# Changelog

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
