#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Waybar Toolkit Installer ==="
echo ""

# Check dependencies
check_dep() {
    if ! command -v "$1" &>/dev/null; then
        echo "⚠  Missing dependency: $1"
        return 1
    fi
    return 0
}

echo "Checking dependencies..."
MISSING=0
check_dep python3 || MISSING=1
check_dep pip || MISSING=1

# Check Python GTK4 bindings
if ! python3 -c "import gi; gi.require_version('Gtk', '4.0')" 2>/dev/null; then
    echo "⚠  Missing: PyGObject with GTK4 support"
    echo "   Install with: sudo pacman -S python-gobject gtk4"
    MISSING=1
fi

# Check for compositor tools
if command -v hyprctl &>/dev/null; then
    echo "✔  hyprctl found (Hyprland)"
elif command -v wlr-randr &>/dev/null; then
    echo "✔  wlr-randr found (generic wlroots)"
else
    echo "⚠  No monitor backend found. Install hyprctl or wlr-randr."
    MISSING=1
fi

if [ "$MISSING" -eq 1 ]; then
    echo ""
    echo "Please install missing dependencies and try again."
    exit 1
fi

echo ""
echo "Installing waybar-toolkit..."
pip install --user --break-system-packages "$PROJECT_DIR"

echo ""
echo "✔  Installation complete!"
echo ""
echo "Usage:"
echo "  waybar-toolkit          # Open the utility hub"
echo "  waybar-toolkit -m       # Open Monitor Manager directly"
echo ""
echo "Add to Waybar:"
echo "  See config/waybar-module.jsonc for the module configuration."
