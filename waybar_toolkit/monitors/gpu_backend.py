import subprocess
import platform
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class GPUBackend:
    """
    Unified backend for retrieving GPU information across vendors (Nvidia, Intel, AMD).
    """

    def __init__(self) -> None:
        self.gpu_info: Dict[str, Any] = {}
        self._detect_gpu_vendor()

    def _run_safe(self, cmd: list[str], timeout: int = 5) -> Optional[str]:
        """Helper to run shell commands safely."""
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            logger.warning(f"Command failed: {' '.join(cmd)}. Error: {e.stderr}")
            return None
        except subprocess.TimeoutExpired:
            logger.warning(f"Command timed out: {' '.join(cmd)}")
            return None
        except FileNotFoundError:
            logger.warning(f"Command not found: {cmd[0]}")
            return None

    def _detect_gpu_vendor(self) -> None:
        """
        Attempts to detect the GPU vendor and gather basic information.
        Prioritizes vendor-specific tools (nvidia-smi, etc.).
        """
        vendor = "Unknown"
        details: Any = "Could not determine GPU vendor."

        # 1. Nvidia Detection (using nvidia-smi)
        if self._run_safe(["nvidia-smi"]) is not None:
            vendor = "Nvidia"
            details = self._get_nvidia_info()
        # 2. Intel/AMD Detection (using lspci or similar)
        else:
            lspci_output = self._run_safe(["lspci", "-v"])
            if lspci_output:
                if "VGA compatible controller" in lspci_output:
                    if "NVIDIA" in lspci_output:
                        vendor = "Nvidia"
                        details = self._get_nvidia_info()
                    elif "Intel" in lspci_output:
                        vendor = "Intel"
                        details = self._get_intel_info()
                    elif "AMD" in lspci_output:
                        vendor = "AMD"
                        details = self._get_amd_info()
                    else:
                        vendor = "PCI Detected"
                        details = f"PCI detected, but vendor not explicitly identified: {lspci_output[:500]}..."
                else:
                    details = "No VGA controller detected via lspci."
            else:
                details = "Could not run lspci or no GPU detected."

        self.gpu_info = {"vendor": vendor, "details": details}

    def _get_nvidia_info(self) -> Dict[str, Any]:
        """Retrieves detailed information using nvidia-smi."""
        smi_output = self._run_safe(["nvidia-smi"])
        if not smi_output:
            return {"usage": "N/A", "memory": "N/A", "temperature": "N/A"}

        # Simple parsing for key metrics
        usage = "N/A"
        memory = "N/A"
        temp = "N/A"

        # Example parsing logic (highly dependent on nvidia-smi output format)
        try:
            usage_line = [line for line in smi_output.split('\n') if "GPU Utilization" in line][0]
            usage = usage_line.split()[-1]
        except IndexError:
            pass

        try:
            mem_line = [line for line in smi_output.split('\n') if "Memory Usage" in line][0]
            memory = mem_line.split()[-1]
        except IndexError:
            pass

        try:
            temp_line = [line for line in smi_output.split('\n') if "Temperature" in line][0]
            temp = temp_line.split()[-1]
        except IndexError:
            pass

        return {"usage": usage, "memory": memory, "temperature": temp}

    def _get_intel_info(self) -> Dict[str, Any]:
        """Retrieves basic information for Intel GPUs (placeholder)."""
        # Implementation would typically involve reading /sys/class/drm or using intel_gpu_top
        return {"usage": "N/A", "memory": "N/A", "temperature": "N/A", "vendor": "Intel"}

    def _get_amd_info(self) -> Dict[str, Any]:
        """Retrieves basic information for AMD GPUs (placeholder)."""
        # Implementation would typically involve reading /sys/class/drm or using amdgpu_top
        return {"usage": "N/A", "memory": "N/A", "temperature": "N/A", "vendor": "AMD"}

    def get_gpu_info(self) -> Dict[str, Any]:
        """Returns the collected GPU information."""
        return self.gpu_info
