"""
Resolución de rutas robusta para modo DESARROLLO y modo EMPAQUETADO (.exe PyInstaller).

get_base_dir():
    Carpeta base PERSISTENTE en disco. Aquí viven los datos que se LEEN y ESCRIBEN:
    mileforum.db, los modelos que el Aprendiz reescribe in-place (bundles), el historial
    y la memoria del Ágora, y los cucurucho_*.json que el operador edita.

    - En .exe (PyInstaller --onefile) sys.frozen es True y __file__ apunta a la carpeta
      temporal sys._MEIPASS, que se recrea en cada arranque y se borra al cerrar.
      Por eso se usa Path(sys.executable).parent (la carpeta del ejecutable real).
    - En modo desarrollo (python/uvicorn) se usa la carpeta de este archivo (backend/).

get_resource_dir():
    Recursos EMBEBIDOS de solo-lectura si se compilara con --add-data (sys._MEIPASS).
"""
import sys
from pathlib import Path


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.resolve()


def get_resource_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).parent.resolve()
