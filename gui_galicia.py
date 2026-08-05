"""Interfaz de escritorio de la variante Banco Galicia: se carga el Excel que
exporta el Home Banking, se eligen a mano qué créditos facturar y cómo
(servicio o producto, a consumidor final o al titular identificado), y se
emiten las Facturas C en ARCA.

Es la misma app que gui.py pero con otra fuente de datos: Galicia no tiene API
pública de movimientos, así que en vez de consultar Mercado Pago se lee el
archivo que baja la persona. Todo lo demás (login contra WSAA, emisión por
WSFEv1, historial local, onboarding del certificado) es compartido.

La UI vive en gui_galicia.html; acá solo está la lógica que se expone al JS.
"""
import datetime
import logging
import os

import webview

import rutas
import registro
import onboarding  # tiene que importarse primero: garantiza que config.py exista

import extracto_galicia
import facturar
import historial

registro.configurar("facturacion_galicia")
log = logging.getLogger("facturacion_galicia")

HTML_PATH = rutas.ruta_recurso("gui_galicia.html")
ICON_PATH = rutas.ruta_recurso("icon.ico")

TIPOS_ARCHIVO = {
    "crt": ("Certificado (*.crt;*.pem)",),
    "key": ("Clave privada (*.key;*.pem)",),
}

TIPOS_EXTRACTO = ("Extracto de Galicia (*.xlsx)", "Todos los archivos (*.*)")

DIAS_POR_PERIODO = {
    "mes": 30,
    "3meses": 91,
    "6meses": 182,
    "anio": 365,
    "todo": None,
}

# Perfil de facturación de este usuario: todo lo que factura es asesoría, o sea
# un servicio, cobrado por transferencia bancaria y facturado a consumidor
# final. Estos son los valores con los que arranca la pantalla; cada movimiento
# se puede cambiar a mano si alguna vez hace falta una excepción.
PERFIL = {
    "concepto": facturar.CONCEPTO_SERVICIOS,
    "receptor": "final",
    "condicion_iva": facturar.CONDICION_CONSUMIDOR_FINAL,
    "detalle": "Asesoría",
    "fecha_modo": "hoy",
    # WSFEv1 no tiene campo de condición de venta: existe en "Comprobantes en
    # Línea" (el formulario web de ARCA), no en el Web Service. Se guarda en el
    # historial local para que el registro propio quede completo, pero no se le
    # manda a ARCA porque no hay dónde.
    "condicion_venta": "Transferencia bancaria",
}

# A partir de cierto importe, ARCA exige identificar al comprador aunque sea
# consumidor final. El monto lo actualiza ARCA cada tanto por resolución: esto
# es solo un aviso en pantalla (no bloquea nada), así que si quedó viejo,
# cambiá el número acá.
UMBRAL_IDENTIFICACION_CF = 417_288

# Cuántos días para atrás acepta ARCA que se fecha un comprobante, según el
# concepto. Se usa para avisar antes de emitir, no para bloquear.
TOLERANCIA_FECHA = {
    facturar.CONCEPTO_PRODUCTOS: 5,
    facturar.CONCEPTO_SERVICIOS: 10,
    facturar.CONCEPTO_PRODUCTOS_Y_SERVICIOS: 10,
}


def _fecha_movimiento(movimiento):
    try:
        return datetime.date.fromisoformat(movimiento["fecha"])
    except (KeyError, TypeError, ValueError):
        return None


class Api:
    def __init__(self):
        self._movimientos = {}
        self._extracto = None

    # --- Onboarding ---
    def estado_onboarding(self):
        return {"necesita_onboarding": onboarding.necesita_onboarding(requiere_mp=False)}

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
                cuit=datos.get("cuit", ""),
                pto_vta=datos.get("pto_vta", ""),
                requiere_mp=False,
            )
            log.info("config.py guardado (onboarding completado)")
            return {"ok": True}
        except Exception as e:
            log.exception("Error guardando config.py")
            return {"ok": False, "error": str(e)}

    def cerrar_app(self):
        webview.windows[0].destroy()

    # --- Extracto de Galicia ---
    def opciones_facturacion(self):
        """Opciones que la interfaz ofrece en los desplegables de cada movimiento."""
        return {
            "conceptos": [{"id": k, "nombre": v} for k, v in facturar.CONCEPTOS.items()],
            "condiciones_iva": [{"id": k, "nombre": v} for k, v in facturar.CONDICION_IVA_RECEPTOR.items()],
            "umbral_identificacion": UMBRAL_IDENTIFICACION_CF,
            "tolerancia_fecha": {str(k): v for k, v in TOLERANCIA_FECHA.items()},
            "perfil": PERFIL,
        }

    def elegir_extracto(self):
        """Abre el explorador para elegir el Excel bajado del Home Banking."""
        seleccion = webview.windows[0].create_file_dialog(
            webview.FileDialog.OPEN, file_types=TIPOS_EXTRACTO
        )
        if not seleccion:
            return {"ok": False, "cancelado": True}
        return self.cargar_extracto(seleccion[0])

    def cargar_extracto(self, ruta):
        """Lee el extracto y marca qué movimientos ya se facturaron antes."""
        try:
            datos = extracto_galicia.leer_extracto(ruta)
        except ValueError as e:
            log.warning("Extracto rechazado (%s): %s", ruta, e)
            return {"ok": False, "error": str(e)}
        except Exception as e:
            log.exception("Error leyendo el extracto %s", ruta)
            return {"ok": False, "error": f"No se pudo leer el archivo: {e}"}

        try:
            hist = historial.cargar_historial()
        except Exception as e:
            log.exception("Error leyendo el historial al cargar el extracto")
            return {"ok": False, "error": str(e)}

        for movimiento in datos["movimientos"]:
            registro_previo = hist.get(movimiento["id"])
            movimiento["ya_facturada"] = registro_previo is not None
            movimiento["cae_previo"] = registro_previo.get("cae") if registro_previo else None

        self._movimientos = {m["id"]: m for m in datos["movimientos"]}
        self._extracto = datos

        log.info(
            "Extracto cargado: archivo=%s, movimientos=%s, ya facturados=%s",
            os.path.basename(str(ruta)),
            len(datos["movimientos"]),
            sum(1 for m in datos["movimientos"] if m["ya_facturada"]),
        )
        return {
            "ok": True,
            "archivo": os.path.basename(str(ruta)),
            "cuentas": datos["cuentas"],
            "movimientos": datos["movimientos"],
            "debitos_ignorados": datos["debitos_ignorados"],
        }

    # --- Facturación ---
    def _preparar(self, movimiento, item):
        """Traduce lo elegido en pantalla para ese movimiento a los parámetros de
        WSFEv1. Levanta ValueError con un mensaje mostrable si la combinación no
        se puede facturar."""
        try:
            concepto = int(item.get("concepto") or PERFIL["concepto"])
        except (TypeError, ValueError):
            raise ValueError("Concepto inválido")
        if concepto not in facturar.CONCEPTOS:
            raise ValueError("Concepto inválido")

        receptor = str(item.get("receptor") or PERFIL["receptor"])
        if receptor == "final":
            doc_tipo, doc_nro = facturar.DOC_CONSUMIDOR_FINAL, 0
            condicion = facturar.CONDICION_CONSUMIDOR_FINAL
        elif receptor == "dni":
            if not movimiento.get("dni"):
                raise ValueError("El extracto no trae un CUIL de persona del que sacar el DNI")
            doc_tipo, doc_nro = facturar.DOC_DNI, int(movimiento["dni"])
            condicion = facturar.CONDICION_CONSUMIDOR_FINAL
        elif receptor == "cuit":
            if not movimiento.get("cuit"):
                raise ValueError("El extracto no trae el CUIT del titular para esta transferencia")
            doc_tipo, doc_nro = facturar.DOC_CUIT, int(movimiento["cuit"])
            try:
                condicion = int(item.get("condicion_iva") or PERFIL["condicion_iva"])
            except (TypeError, ValueError):
                raise ValueError("Condición frente al IVA inválida")
            if condicion not in facturar.CONDICION_IVA_RECEPTOR:
                raise ValueError("Condición frente al IVA inválida")
        else:
            raise ValueError(f"Receptor inválido: {receptor}")

        fecha_emision = _fecha_movimiento(movimiento) if item.get("fecha_modo") == "movimiento" else None

        return {
            "importe": movimiento["monto"],
            "fecha": fecha_emision,
            "concepto": concepto,
            "doc_tipo": doc_tipo,
            "doc_nro": doc_nro,
            "condicion_iva_receptor": condicion,
            # Sin fecha_servicio: el período "desde"/"hasta" del servicio es el
            # día en que se factura, no el día en que entró la transferencia.
            "fecha_servicio": None,
        }

    def facturar(self, items):
        """Emite una Factura C por cada movimiento elegido, con las opciones que
        se hayan marcado para cada uno."""
        # Se lee el historial una sola vez y, si está dañado, no se factura nada:
        # sin historial confiable no se puede saber qué ya se facturó.
        try:
            hist = historial.cargar_historial()
        except Exception as e:
            log.exception("Error leyendo el historial antes de facturar")
            return [{"id": (item or {}).get("id"), "ok": False, "error": [str(e)]} for item in items]

        resultados = []
        for item in items:
            id_ = str((item or {}).get("id"))
            movimiento = self._movimientos.get(id_)
            if not movimiento:
                continue
            if id_ in hist:
                resultados.append({"id": id_, "ok": False, "error": ["Ya estaba facturada"]})
                continue

            try:
                parametros = self._preparar(movimiento, item)
            except ValueError as e:
                resultados.append({"id": id_, "ok": False, "error": [str(e)]})
                continue

            try:
                resultado = facturar.emitir_factura_c(**parametros)
            except Exception as e:
                log.exception("Error emitiendo factura para el movimiento %s", id_)
                resultado = {"ok": False, "error": [str(e)]}

            if resultado.get("ok"):
                detalle = str(item.get("detalle") or "").strip()[:200]
                historial.registrar_factura(id_, movimiento, resultado, extra={
                    "origen": "galicia",
                    "cuit_titular": movimiento.get("cuit"),
                    "concepto": resultado.get("concepto"),
                    "concepto_texto": resultado.get("concepto_texto"),
                    "doc_tipo": resultado.get("doc_tipo"),
                    "doc_nro": resultado.get("doc_nro"),
                    "detalle": detalle,
                    # No viaja a ARCA (WSFEv1 no tiene el campo): queda acá para
                    # que el registro propio esté completo.
                    "condicion_venta": PERFIL["condicion_venta"],
                    "cuenta": movimiento.get("cuenta"),
                })
                movimiento["ya_facturada"] = True
                movimiento["cae_previo"] = resultado.get("cae")
                log.info(
                    "Factura emitida: monto=%s concepto=%s cae=%s numero=%s",
                    movimiento["monto"], resultado.get("concepto_texto"),
                    resultado.get("cae"), resultado.get("numero"),
                )
            else:
                log.warning("Factura rechazada para el movimiento %s: %s", id_, resultado.get("error"))

            resultado["id"] = id_
            resultados.append(resultado)

        return resultados

    # --- Historial ---
    def listar_historial(self, periodo="mes"):
        dias = DIAS_POR_PERIODO.get(periodo, DIAS_POR_PERIODO["mes"])
        desde = (datetime.date.today() - datetime.timedelta(days=dias)) if dias else None

        try:
            registros = historial.listar_facturas(desde=desde)
        except Exception as e:
            log.exception("Error leyendo el historial local")
            return {"registros": [], "total": 0, "error": str(e)}

        total = round(sum(r.get("monto") or 0 for r in registros), 2)
        return {"registros": registros, "total": total}

    def consultar_historial_arca(self, periodo="mes"):
        """Reconstruye el historial consultando directamente a ARCA (WSFEv1) en vez
        de leer historial_facturas.json. Solo se llama cuando el usuario toca el
        botón "Consultar desde ARCA" — nunca automáticamente."""
        dias = DIAS_POR_PERIODO.get(periodo, DIAS_POR_PERIODO["mes"])
        desde = (datetime.date.today() - datetime.timedelta(days=dias)) if dias else None

        try:
            registros = facturar.consultar_facturas_arca(desde=desde)
        except Exception as e:
            log.exception("Error consultando historial directo a ARCA")
            return {"ok": False, "error": str(e)}

        total = round(sum(r.get("monto") or 0 for r in registros), 2)
        log.info("Consulta de historial a ARCA: periodo=%s, encontradas=%s", periodo, len(registros))
        return {"ok": True, "registros": registros, "total": total}


if __name__ == "__main__":
    log.info("App iniciada (variante Banco Galicia)")
    webview.create_window(
        "Facturación Galicia → ARCA",
        HTML_PATH,
        js_api=Api(),
        width=1040,
        height=700,
        min_size=(760, 520),
        background_color="#F4F6F9",
    )
    webview.start(icon=ICON_PATH)
