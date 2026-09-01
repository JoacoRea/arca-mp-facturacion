"""Resolución de rutas que funciona igual corriendo desde código fuente que
empaquetado como .exe (PyInstaller --onefile).

Hay dos nociones de "carpeta base" distintas:
  - Datos del usuario (config.py, certificado, clave, credenciales, historial,
    log): tienen que vivir al lado del .exe real y persistir entre corridas.
  - Recursos empaquetados (gui.html, icon.ico): en modo --onefile viven en la
    carpeta temporal donde PyInstaller descomprime todo en cada arranque.
Si se usa la carpeta equivocada para cada cosa, o los datos del usuario se
pierden en cada corrida, o los recursos no se encuentran.
"""
import os
import sys


def _frozen():
    return getattr(sys, "frozen", False)


def _base_datos():
    if _frozen():
        carpeta = os.path.dirname(sys.executable)
        # En macOS, PyInstaller en modo ventana arma un paquete .app y el
        # ejecutable queda enterrado en MiApp.app/Contents/MacOS/. Los datos del
        # usuario no pueden vivir ahí adentro: desaparecen al reemplazar la app
        # por una versión nueva, y macOS trata el paquete como una unidad que se
        # mueve entera. Se usa la carpeta que contiene al .app, que es la que la
        # persona ve y respalda.
        if sys.platform == "darwin" and carpeta.endswith("/Contents/MacOS"):
            return os.path.dirname(os.path.dirname(os.path.dirname(carpeta)))
        return carpeta
    return os.path.dirname(os.path.abspath(__file__))


def _base_recursos():
    if _frozen():
        return getattr(sys, "_MEIPASS", _base_datos())
    return os.path.dirname(os.path.abspath(__file__))


def ruta_datos(*partes):
    """Ruta a un archivo de datos del usuario (junto al .exe o al código fuente)."""
    return os.path.join(_base_datos(), *partes)


def ruta_recurso(*partes):
    """Ruta a un recurso empaquetado (HTML, ícono)."""
    return os.path.join(_base_recursos(), *partes)


# Al empaquetar con PyInstaller, la carpeta del .exe no queda en sys.path por
# default — hace falta agregarla a mano para que `import config` (el archivo
# de datos del usuario, al lado del .exe) funcione.
if _frozen() and _base_datos() not in sys.path:
    sys.path.insert(0, _base_datos())
