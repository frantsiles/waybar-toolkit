import subprocess
import sys
import logging
from datetime import datetime
from typing import Any, Dict

# Importamos la lógica que desarrollamos
# Asumimos que la ruta de importación es correcta.
try:
    from waybar_toolkit.monitors.gpu_backend import GPUBackend
except ImportError:
    # Fallback simple si el entorno de Waybar no puede resolver la importación
    logging.error("Could not import GPUBackend. Ensure the project structure and PYTHONPATH are correct.")
    GPUBackend = None


def get_gpu_info_for_waybar() -> str:
    """
    Obtiene la información de la GPU y la formatea para ser visible en Waybar.
    """
    if GPUBackend is None:
        return "GPU: Error"

    try:
        backend = GPUBackend()
        info: Dict[str, Any] = backend.get_gpu_info()

        # Formateo simple para Waybar: "Temperatura: XXX | Uso: YYY"
        temp = str(info.get("temperature", "N/A"))
        usage = str(info.get("usage", "N/A"))
        mem = str(info.get("memory", "N/A"))

        if temp != "N/A" and usage != "N/A":
            return f"⚡ GPU: {temp} | Uso: {usage} | Mem: {mem}"
        else:
            return f"⚡ GPU: Datos no disponibles"

    except Exception as e:
        logging.error(f"Error al obtener info de GPU: {e}")
        return "⚡ GPU: Fallo"


def main():
    """
    Función principal que se ejecuta cuando Waybar llama a este script.
    Imprime el resultado formateado a stdout.
    """
    info = get_gpu_info_for_waybar()
    print(info)


if __name__ == "__main__":
    main()
