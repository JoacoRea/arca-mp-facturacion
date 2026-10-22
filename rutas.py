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


def carpeta_descargas():
    """Carpeta de Descargas del usuario, para abrir ahí los selectores de archivo:
    el certificado de ARCA y el extracto del banco siempre bajan ahí.

    En Windows se consulta la ubicación real (la persona puede haberla movido a
    otro disco, ej. "D:\\Descargas"); si no se puede, ~/Downloads. Devuelve ""
    si no existe, y el diálogo abre donde quiera el sistema."""
    if sys.platform == "win32":
        try:
            import ctypes
            import uuid
            from ctypes import wintypes

            class _GUID(ctypes.Structure):
                _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                            ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

            bytes_le = uuid.UUID("374DE290-123F-4565-9164-39C4925E467B").bytes_le  # FOLDERID_Downloads
            guid = _GUID.from_buffer_copy(bytes_le)
            ruta = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(ruta)) == 0:
                carpeta = ruta.value
                ctypes.windll.ole32.CoTaskMemFree(ruta)
                if carpeta and os.path.isdir(carpeta):
                    return carpeta
        except Exception:
            pass
    carpeta = os.path.join(os.path.expanduser("~"), "Downloads")
    return carpeta if os.path.isdir(carpeta) else ""


def ruta_recurso(*partes):
    """Ruta a un recurso empaquetado (HTML, ícono)."""
    return os.path.join(_base_recursos(), *partes)


# Al empaquetar con PyInstaller, la carpeta del .exe no queda en sys.path por
# default — hace falta agregarla a mano para que `import config` (el archivo
# de datos del usuario, al lado del .exe) funcione.
if _frozen() and _base_datos() not in sys.path:
    sys.path.insert(0, _base_datos())
