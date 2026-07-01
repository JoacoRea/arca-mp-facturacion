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


def emitir_factura_c(importe, fecha=None, concepto=2, doc_tipo=99, doc_nro=0):
    """Emite una Factura C en ARCA (WSFEv1) por `importe`.

    fecha: datetime.date/datetime a usar como fecha del comprobante (hoy si no se pasa).
    doc_tipo/doc_nro: 99/0 = Consumidor Final (default). Pasar 80/CUIT o 96/DNI si en
    algún momento se factura a alguien identificado.

    Devuelve un dict:
      {"ok": True, "cae": ..., "vencimiento_cae": ..., "numero": ..., "pto_vta": ...}
      {"ok": False, "error": [...]}
    """
    creds = login.obtener_credenciales_validas()
    auth = {"Token": creds["token"], "Sign": creds["sign"], "Cuit": CUIT}

    client = cliente_wsfe()

    ultimo = client.service.FECompUltimoAutorizado(Auth=auth, PtoVta=PTO_VTA, CbteTipo=CBTE_TIPO)
    errores = _errores_arca(ultimo)
    if errores:
        return {"ok": False, "error": errores}
    proximo_nro = ultimo.CbteNro + 1

    fecha_cbte = (fecha or datetime.datetime.now(login.ZONA_AR)).strftime("%Y%m%d")

    factura = {
        "FeCabReq": {"CantReg": 1, "PtoVta": PTO_VTA, "CbteTipo": CBTE_TIPO},
        "FeDetReq": {
            "FECAEDetRequest": [{
                "Concepto": concepto,  # 2 = Servicios
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
                "CondicionIVAReceptorId": 5,  # 5 = Consumidor Final
                "FchServDesde": fecha_cbte,
                "FchServHasta": fecha_cbte,
                "FchVtoPago": fecha_cbte,
            }]
        }
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
