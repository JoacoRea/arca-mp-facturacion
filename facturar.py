import ssl
import datetime
import requests
from zeep import Client
from zeep.transports import Transport
from requests.adapters import HTTPAdapter

import login
from config import CUIT, PTO_VTA

CBTE_TIPO = 11  # Factura C
WSFE_WSDL = "https://servicios1.afip.gov.ar/wsfev1/service.asmx?WSDL"

# Cómo se factura la operación (campo Concepto de WSFEv1). Cambia qué fechas
# acepta ARCA: con Productos no se mandan fechas de servicio, y con Servicios
# son obligatorias.
CONCEPTO_PRODUCTOS = 1
CONCEPTO_SERVICIOS = 2
CONCEPTO_PRODUCTOS_Y_SERVICIOS = 3
CONCEPTOS = {
    CONCEPTO_PRODUCTOS: "Productos",
    CONCEPTO_SERVICIOS: "Servicios",
    CONCEPTO_PRODUCTOS_Y_SERVICIOS: "Productos y Servicios",
}

# Tipos de documento del receptor (campo DocTipo de WSFEv1).
DOC_CUIT = 80
DOC_DNI = 96
DOC_CONSUMIDOR_FINAL = 99

# Condición frente al IVA del receptor (RG 5616). Solo las que tienen sentido
# como cliente de un monotributista que emite Factura C.
CONDICION_IVA_RECEPTOR = {
    1: "IVA Responsable Inscripto",
    4: "IVA Sujeto Exento",
    5: "Consumidor Final",
    6: "Responsable Monotributo",
    7: "Sujeto No Categorizado",
    13: "Monotributista Social",
}
CONDICION_CONSUMIDOR_FINAL = 5


class SSLAdapter(HTTPAdapter):
    """Adapter que baja el nivel de seguridad SSL para servidores viejos como los de ARCA."""
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)


_client = None


def cliente_wsfe():
    """Cliente SOAP de WSFEv1, cacheado a nivel módulo: bajar y parsear el WSDL
    es lento y no hace falta repetirlo por cada operación (p. ej. al facturar
    varios turnos seguidos)."""
    global _client
    if _client is None:
        session = requests.Session()
        session.mount("https://", SSLAdapter())
        transport = Transport(session=session, timeout=60, operation_timeout=90)
        _client = Client(WSFE_WSDL, transport=transport)
    return _client


def _errores_arca(resultado):
    """Errores a nivel respuesta de WSFE (token vencido, punto de venta inválido,
    etc.). Cuando vienen, el resto de la respuesta suele estar vacío."""
    if getattr(resultado, "Errors", None):
        return [f"{err.Code}: {err.Msg}" for err in resultado.Errors.Err]
    return []


def emitir_factura_c(importe, fecha=None, concepto=CONCEPTO_SERVICIOS,
                     doc_tipo=DOC_CONSUMIDOR_FINAL, doc_nro=0,
                     condicion_iva_receptor=CONDICION_CONSUMIDOR_FINAL,
                     fecha_servicio=None):
    """Emite una Factura C en ARCA (WSFEv1) por `importe`.

    fecha: datetime.date/datetime a usar como fecha del comprobante (hoy si no se pasa).
    concepto: 1 = Productos, 2 = Servicios, 3 = Productos y Servicios.
    doc_tipo/doc_nro: 99/0 = Consumidor Final (default). Pasar 80/CUIT o 96/DNI para
    facturar a alguien identificado.
    condicion_iva_receptor: condición del cliente frente al IVA (RG 5616).
    fecha_servicio: date del período de servicio prestado (por ejemplo, el día en que
    entró la transferencia). Solo se usa con concepto 2 o 3; si no se pasa, se usa la
    fecha del comprobante.

    Devuelve un dict:
      {"ok": True, "cae": ..., "vencimiento_cae": ..., "numero": ..., "pto_vta": ...}
      {"ok": False, "error": [...]}
    """
    importe = round(float(importe), 2)
    if importe <= 0:
        return {"ok": False, "error": ["El importe a facturar tiene que ser mayor a cero"]}
    if concepto not in CONCEPTOS:
        return {"ok": False, "error": [f"Concepto inválido: {concepto}"]}

    creds = login.obtener_credenciales_validas()
    auth = {"Token": creds["token"], "Sign": creds["sign"], "Cuit": CUIT}

    client = cliente_wsfe()

    ultimo = client.service.FECompUltimoAutorizado(Auth=auth, PtoVta=PTO_VTA, CbteTipo=CBTE_TIPO)
    errores = _errores_arca(ultimo)
    if errores:
        return {"ok": False, "error": errores}
    proximo_nro = ultimo.CbteNro + 1

    fecha_cbte = (fecha or datetime.datetime.now(login.ZONA_AR)).strftime("%Y%m%d")

    detalle = {
        "Concepto": concepto,
        "DocTipo": doc_tipo,
        "DocNro": doc_nro,
        "CbteDesde": proximo_nro,
        "CbteHasta": proximo_nro,
        "CbteFch": fecha_cbte,
        "ImpTotal": importe,
        "ImpTotConc": 0,
        "ImpNeto": importe,
        "ImpOpEx": 0,
        "ImpIVA": 0,
        "ImpTrib": 0,
        "MonId": "PES",
        "MonCotiz": 1,
        "CondicionIVAReceptorId": condicion_iva_receptor,
    }

    # Las fechas de servicio son obligatorias con Concepto 2 y 3, y ARCA rechaza
    # el comprobante si se mandan con Concepto 1 (Productos).
    if concepto in (CONCEPTO_SERVICIOS, CONCEPTO_PRODUCTOS_Y_SERVICIOS):
        fecha_serv = fecha_servicio.strftime("%Y%m%d") if fecha_servicio else fecha_cbte
        detalle["FchServDesde"] = fecha_serv
        detalle["FchServHasta"] = fecha_serv
        # La plata ya está cobrada, pero ARCA no acepta un vencimiento de pago
        # anterior a la fecha del comprobante: se usa la fecha de emisión.
        detalle["FchVtoPago"] = fecha_cbte

    factura = {
        "FeCabReq": {"CantReg": 1, "PtoVta": PTO_VTA, "CbteTipo": CBTE_TIPO},
        "FeDetReq": {"FECAEDetRequest": [detalle]},
    }

    resultado = client.service.FECAESolicitar(Auth=auth, FeCAEReq=factura)
    errores = _errores_arca(resultado)
    if errores:
        return {"ok": False, "error": errores}
    detalle = resultado.FeDetResp.FECAEDetResponse[0]

    if detalle.Resultado == "A":
        return {
            "ok": True,
            "cae": detalle.CAE,
            "vencimiento_cae": detalle.CAEFchVto,
            "numero": proximo_nro,
            "pto_vta": PTO_VTA,
            "importe": importe,
            "fecha_emision": fecha_cbte,
            "concepto": concepto,
            "concepto_texto": CONCEPTOS[concepto],
            "doc_tipo": doc_tipo,
            "doc_nro": doc_nro,
        }

    observaciones = []
    if detalle.Observaciones:
        observaciones = [f"{obs.Code}: {obs.Msg}" for obs in detalle.Observaciones.Obs]
    return {"ok": False, "error": observaciones or ["Rechazada sin detalle de ARCA"]}


def consultar_facturas_arca(desde=None):
    """Reconstruye la lista de Facturas C emitidas consultando directamente a
    ARCA (WSFEv1), comprobante por comprobante — no hay un endpoint de ARCA
    que devuelva "todo el historial" de una sola vez. Solo se debe llamar a
    pedido explícito del usuario: hace una consulta HTTP por cada comprobante,
    así que puede tardar si hay muchos.

    `desde`: date opcional; si se pasa, se recorre del comprobante más nuevo al
    más viejo y se corta al encontrar uno anterior (los números de comprobante
    son cronológicos), así no se consulta historial que no se va a mostrar."""
    creds = login.obtener_credenciales_validas()
    auth = {"Token": creds["token"], "Sign": creds["sign"], "Cuit": CUIT}
    client = cliente_wsfe()

    ultimo = client.service.FECompUltimoAutorizado(Auth=auth, PtoVta=PTO_VTA, CbteTipo=CBTE_TIPO)
    errores = _errores_arca(ultimo)
    if errores:
        raise RuntimeError("ARCA devolvió un error: " + "; ".join(errores))
    ultimo_nro = ultimo.CbteNro

    facturas = []
    for nro in range(ultimo_nro, 0, -1):
        resultado = client.service.FECompConsultar(
            Auth=auth,
            FeCompConsReq={"CbteTipo": CBTE_TIPO, "CbteNro": nro, "PtoVta": PTO_VTA},
        )
        detalle = resultado.ResultGet
        if detalle is None:
            continue

        if desde is not None and detalle.CbteFch:
            fecha_dt = datetime.datetime.strptime(detalle.CbteFch, "%Y%m%d").date()
            if fecha_dt < desde:
                break

        facturas.append({
            "numero": nro,
            "pto_vta": detalle.PtoVta,
            "fecha_emision": detalle.CbteFch,
            "monto": detalle.ImpTotal,
            "cae": detalle.CodAutorizacion,
            "vencimiento_cae": detalle.FchVto,
        })

    return facturas


if __name__ == "__main__":
    # Prueba manual: factura de $100 a Consumidor Final, fecha de hoy.
    resultado = emitir_factura_c(importe=100.00)
    print("\n--- RESULTADO ---")
    print(resultado)
