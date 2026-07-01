"""Interfaz de escritorio (pywebview): buscar transferencias de MP, elegirlas y facturarlas en ARCA.

Se abre a demanda (no corre en segundo plano). La decisión de qué facturar
siempre la toma la persona frente a la pantalla, a propósito. La UI vive en
gui.html; este archivo solo expone la lógica de Python al JS vía js_api.
"""
import datetime
import logging
import webview

import rutas
import registro
import onboarding  # tiene que importarse primero: garantiza que config.py exista

import consultar_transferencias as mp
import facturar
import historial

registro.configurar()
log = logging.getLogger("beauty_biller")

HTML_PATH = rutas.ruta_recurso("gui.html")
ICON_PATH = rutas.ruta_recurso("icon.ico")

TIPOS_ARCHIVO = {
    "crt": ("Certificado (*.crt;*.pem)",),
    "key": ("Clave privada (*.key;*.pem)",),
}

DIAS_POR_PERIODO = {
    "mes": 30,
    "3meses": 91,
    "6meses": 182,
    "anio": 365,
    "todo": None,
}


class Api:
    def __init__(self):
        self._candidatos = []

    # --- Onboarding ---
    def estado_onboarding(self):
        return {"necesita_onboarding": onboarding.necesita_onboarding()}

    def estado_certificado(self):
        return onboarding.estado_certificado()

    def generar_certificado(self, cuit, alias):
        try:
            resultado = onboarding.generar_clave_y_csr(cuit, alias)
            log.info("Clave y CSR generados (onboarding)")
            return {"ok": True, **resultado}
        except Exception as e:
            log.exception("Error generando clave y CSR")
            return {"ok": False, "error": str(e)}

    def elegir_archivo(self, tipo):
        file_types = TIPOS_ARCHIVO.get(tipo, ())
        seleccion = webview.windows[0].create_file_dialog(webview.FileDialog.OPEN, file_types=file_types)
        if not seleccion:
            return {"ok": False}

        origen = seleccion[0]
        try:
            if tipo == "crt":
                onboarding.instalar_certificado(origen)
            else:
                onboarding.instalar_clave(origen)
        except Exception as e:
            log.exception("Error instalando archivo de tipo %s", tipo)
            return {"ok": False, "error": str(e)}

        log.info("Archivo de tipo %s instalado (onboarding)", tipo)
        return {"ok": True}

    def guardar_config_inicial(self, datos):
        try:
            onboarding.guardar_config(
                mp_access_token=datos.get("mp_access_token", ""),
                cuit=datos.get("cuit", ""),
                pto_vta=datos.get("pto_vta", ""),
            )
            log.info("config.py guardado (onboarding completado)")
            return {"ok": True}
        except Exception as e:
            log.exception("Error guardando config.py")
            return {"ok": False, "error": str(e)}

    def cerrar_app(self):
        webview.windows[0].destroy()

    def buscar_transferencias(self, dias):
        try:
            dias = int(dias)
        except (TypeError, ValueError):
            return {"ok": False, "error": "Días inválido"}

        try:
            pagos = mp.obtener_transferencias(dias=dias)
            candidatos = mp.filtrar_candidatos(pagos)
        except Exception as e:
            log.exception("Error buscando transferencias en Mercado Pago (dias=%s)", dias)
            return {"ok": False, "error": str(e)}

        hist = historial.cargar_historial()
        for c in candidatos:
            reg = hist.get(str(c["id"]))
            c["ya_facturada"] = reg is not None
            c["cae_previo"] = reg.get("cae") if reg else None

        self._candidatos = candidatos
        log.info("Búsqueda de transferencias: dias=%s, encontradas=%s", dias, len(candidatos))
        return {"ok": True, "candidatos": candidatos}

    def facturar(self, ids):
        por_id = {str(c["id"]): c for c in self._candidatos}
        resultados = []

        for id_ in ids:
            c = por_id.get(str(id_))
            if not c:
                continue
            if historial.ya_facturada(c["id"]):
                resultados.append({"id": id_, "ok": False, "error": ["Ya estaba facturada"]})
                continue
            try:
                resultado = facturar.emitir_factura_c(importe=c["monto"])
            except Exception as e:
                log.exception("Error emitiendo factura para transferencia %s", id_)
                resultado = {"ok": False, "error": str(e)}
            if resultado.get("ok"):
                historial.registrar_factura(c["id"], c, resultado)
                log.info("Factura emitida: monto=%s cae=%s numero=%s", c["monto"], resultado.get("cae"), resultado.get("numero"))
            else:
                log.warning("Factura rechazada para transferencia %s: %s", id_, resultado.get("error"))
            resultado["id"] = id_
            resultados.append(resultado)

        return resultados

    def listar_historial(self, periodo="mes"):
        dias = DIAS_POR_PERIODO.get(periodo, DIAS_POR_PERIODO["mes"])
        desde = (datetime.date.today() - datetime.timedelta(days=dias)) if dias else None

        registros = historial.listar_facturas(desde=desde)
        total = sum(r.get("monto") or 0 for r in registros)
        return {"registros": registros, "total": total}

    def consultar_historial_arca(self, periodo="mes"):
        """Reconstruye el historial consultando directamente a ARCA (WSFEv1) en
        vez de leer historial_facturas.json. Solo se llama cuando el usuario
        toca el botón "Consultar desde ARCA" — nunca automáticamente."""
        dias = DIAS_POR_PERIODO.get(periodo, DIAS_POR_PERIODO["mes"])
        desde = (datetime.date.today() - datetime.timedelta(days=dias)) if dias else None

        try:
            registros = facturar.consultar_facturas_arca(desde=desde)
        except Exception as e:
            log.exception("Error consultando historial directo a ARCA")
            return {"ok": False, "error": str(e)}

        total = sum(r.get("monto") or 0 for r in registros)
        log.info("Consulta de historial a ARCA: periodo=%s, encontradas=%s", periodo, len(registros))
        return {"ok": True, "registros": registros, "total": total}


if __name__ == "__main__":
    log.info("Beauty Biller iniciado")
    webview.create_window(
        "Beauty Biller",
        HTML_PATH,
        js_api=Api(),
        width=900,
        height=640,
        min_size=(680, 480),
        background_color="#FDEEF3",
    )
    webview.start(icon=ICON_PATH)
