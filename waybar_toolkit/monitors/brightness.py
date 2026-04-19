"""Brightness and contrast control backend.

Laptop displays (eDP): brightnessctl (backlight)
External monitors: ddcutil (DDC/CI)
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import Optional


def _run_safe(cmd: list[str], timeout: int = 10) -> Optional[str]:
    """Run a command, return stdout or None on error."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode == 0:
            return result.stdout
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return None


class BrightnessBackend:
    """Unified brightness/contrast backend.

    Auto-detects:
    - brightnessctl backlight devices → mapped to eDP outputs
    - ddcutil DDC/CI displays → mapped to external outputs via DRM connector
    """

    def __init__(self) -> None:
        self._backlight_device: Optional[str] = None
        self._backlight_max: int = 100
        self._ddc_displays: dict[str, int] = {}  # monitor_name -> display_number
        self._ddc_by_model: dict[str, int] = {}  # edid_model -> display_number (fallback)
        self._detect_devices()

    def _detect_devices(self) -> None:
        """Detect available brightness control devices."""
        self._detect_backlight()
        self._detect_ddc()

    def _detect_backlight(self) -> None:
        """Find backlight device via brightnessctl."""
        output = _run_safe(["brightnessctl", "-l"])
        if not output:
            return

        current_device = None
        for line in output.splitlines():
            device_match = re.match(
                r"Device '(.+?)' of class '(.+?)'", line.strip()
            )
            if device_match:
                name, cls = device_match.group(1), device_match.group(2)
                if cls == "backlight":
                    current_device = name
            elif current_device and "Max brightness:" in line:
                try:
                    self._backlight_max = int(
                        line.strip().split(":")[-1].strip()
                    )
                except ValueError:
                    self._backlight_max = 100
                self._backlight_device = current_device
                break

    def _detect_ddc(self) -> None:
        """Find DDC/CI displays via ddcutil detect.

        Builds two maps:
        - _ddc_displays: DRM connector name → display number (preferred)
        - _ddc_by_model: EDID model string → display number (fallback when
          ddcutil cannot determine the DRM connector, e.g. some HDMI setups)
        """
        output = _run_safe(["ddcutil", "detect"])
        if not output:
            return

        display_num: Optional[int] = None
        edid_model: Optional[str] = None
        has_connector = False
        is_valid = True

        for line in output.splitlines():
            display_match = re.match(r"Display\s+(\d+)", line.strip())
            if display_match:
                # Flush previous display that had no connector
                if display_num is not None and is_valid and not has_connector and edid_model:
                    self._ddc_by_model[edid_model] = display_num
                display_num = int(display_match.group(1))
                edid_model = None
                has_connector = False
                is_valid = True

            if line.startswith("Invalid display"):
                # Flush the previous valid display that had no DRM connector
                if display_num is not None and is_valid and not has_connector and edid_model:
                    self._ddc_by_model[edid_model] = display_num
                is_valid = False
                display_num = None
                edid_model = None
                has_connector = False

            model_match = re.match(r"\s*Model:\s+(.+)", line)
            if model_match and display_num is not None and is_valid:
                edid_model = model_match.group(1).strip()

            connector_match = re.match(
                r"\s*DRM_connector:\s+card\d+-(.+)", line
            )
            if connector_match and display_num is not None and is_valid:
                monitor_name = connector_match.group(1).strip()
                self._ddc_displays[monitor_name] = display_num
                has_connector = True

        # Flush last display
        if display_num is not None and is_valid and not has_connector and edid_model:
            self._ddc_by_model[edid_model] = display_num

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_ddc_available(self, monitor_name: str, model: str = "") -> bool:
        """Check if DDC/CI is available, by connector name or EDID model fallback."""
        return monitor_name in self._ddc_displays or (
            bool(model) and model in self._ddc_by_model
        )

    def query_vcp(
        self, monitor_name: str, vcp_code: int, model: str = ""
    ) -> Optional[tuple[int, int]]:
        """Query a VCP code via DDC/CI.

        Returns (current_value, max_value) or None if unavailable.
        Tries connector-name lookup first, then EDID model as fallback.
        """
        display = self._ddc_displays.get(monitor_name)
        if display is None and model:
            display = self._ddc_by_model.get(model)
        if display is None:
            return None
        output = _run_safe(
            [
                "ddcutil",
                "getvcp",
                f"{vcp_code:02X}",
                "--display",
                str(display),
                "--brief",
            ],
            timeout=8,
        )
        if output:
            for line in output.splitlines():
                parts = line.strip().split()
                if len(parts) < 3 or parts[0].upper() != "VCP":
                    continue
                kind = parts[2].upper()
                try:
                    if kind == "C" and len(parts) >= 5:
                        # Continuous: "VCP XX C <current> <max>"
                        return int(parts[3]), int(parts[4])
                    elif kind == "SNC" and len(parts) >= 4:
                        # Simple non-continuous: "VCP XX SNC x<hex>"
                        val = int(parts[3].lstrip("x"), 16)
                        return val, val
                except ValueError:
                    continue
        return None

    def supports_brightness(self, monitor_name: str) -> bool:
        """Check if brightness control is available for a monitor."""
        if monitor_name.startswith("eDP") and self._backlight_device:
            return True
        return monitor_name in self._ddc_displays

    def supports_contrast(self, monitor_name: str) -> bool:
        """Check if contrast control is available (DDC only)."""
        return monitor_name in self._ddc_displays

    def get_brightness(self, monitor_name: str) -> Optional[int]:
        """Get current brightness (0–100) for a monitor."""
        if monitor_name.startswith("eDP") and self._backlight_device:
            return self._get_backlight_brightness()
        if monitor_name in self._ddc_displays:
            return self._get_ddc_value(monitor_name, 0x10)
        return None

    def set_brightness(self, monitor_name: str, value: int) -> bool:
        """Set brightness (0–100). Applied immediately."""
        value = max(0, min(100, value))
        if monitor_name.startswith("eDP") and self._backlight_device:
            return self._set_backlight_brightness(value)
        if monitor_name in self._ddc_displays:
            return self._set_ddc_value(monitor_name, 0x10, value)
        return False

    def get_contrast(self, monitor_name: str) -> Optional[int]:
        """Get current contrast (0–100) for a monitor (DDC only)."""
        if monitor_name in self._ddc_displays:
            return self._get_ddc_value(monitor_name, 0x12)
        return None

    def set_contrast(self, monitor_name: str, value: int) -> bool:
        """Set contrast (0–100). DDC only, applied immediately."""
        value = max(0, min(100, value))
        if monitor_name in self._ddc_displays:
            return self._set_ddc_value(monitor_name, 0x12, value)
        return False

    # ------------------------------------------------------------------
    # Backlight (brightnessctl)
    # ------------------------------------------------------------------

    def _get_backlight_brightness(self) -> Optional[int]:
        output = _run_safe(
            ["brightnessctl", "-d", self._backlight_device, "get"]
        )
        if output:
            try:
                raw = int(output.strip())
                return round(raw * 100 / self._backlight_max)
            except ValueError:
                pass
        return None

    def _set_backlight_brightness(self, percent: int) -> bool:
        result = _run_safe(
            ["brightnessctl", "-d", self._backlight_device, "set", f"{percent}%"]
        )
        return result is not None

    # ------------------------------------------------------------------
    # DDC/CI (ddcutil)
    # ------------------------------------------------------------------

    def _get_ddc_value(
        self, monitor_name: str, vcp_code: int
    ) -> Optional[int]:
        display = self._ddc_displays.get(monitor_name)
        if display is None:
            return None
        output = _run_safe(
            ["ddcutil", "getvcp", str(vcp_code), "--display", str(display)]
        )
        if output:
            match = re.search(r"current value\s*=\s*(\d+)", output)
            if match:
                return int(match.group(1))
        return None

    def _set_ddc_value(
        self, monitor_name: str, vcp_code: int, value: int
    ) -> bool:
        display = self._ddc_displays.get(monitor_name)
        if display is None:
            return False
        result = _run_safe(
            [
                "ddcutil",
                "setvcp",
                str(vcp_code),
                str(value),
                "--display",
                str(display),
            ]
        )
        return result is not None
