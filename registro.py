"""Logging a archivo, para poder ver qué pasó si algo falla en la compu de
otra persona (sin acceso a su pantalla ni a una consola).

Nunca hay que loguear secretos: ni el Access Token de MP, ni el token/sign de
WSAA, ni el contenido de la clave privada. CAE, montos e IDs de MP no son
secretos (ya viven en historial_facturas.json) y sí se loguean.
"""
import logging
import logging.handlers
import sys

import rutas

LOG_PATH = rutas.ruta_datos("beauty_biller.log")

_configurado = False


def configurar():
    global _configurado
    if _configurado:
        return
    _configurado = True

    handler = logging.handlers.RotatingFileHandler(
        LOG_PATH, maxBytes=1_000_000, backupCount=2, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))

    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    raiz.addHandler(handler)

    def _excepcion_no_manejada(tipo, valor, tb):
        logging.getLogger("beauty_biller").critical("Error no manejado", exc_info=(tipo, valor, tb))

    sys.excepthook = _excepcion_no_manejada
