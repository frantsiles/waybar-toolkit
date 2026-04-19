#!/usr/bin/env bash
# Runs waybar-toolkit directly from source (no reinstall needed).
# Usage: ./run-dev.sh [args...]
#   ./run-dev.sh -m       # Monitor Manager
#   ./run-dev.sh -p       # Process Manager
#   ./run-dev.sh -w       # Waybar Config Editor
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

exec python3 -m waybar_toolkit.app "$@"
