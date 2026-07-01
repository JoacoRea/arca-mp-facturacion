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


def _cliente_wsfe():
    session = requests.Session()
    session.mount("https://", SSLAdapter())
    transport = Transport(session=session)
    return Client(WSFE_WSDL, transport=transport)


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

    client = _cliente_wsfe()

    ultimo = client.service.FECompUltimoAutorizado(Auth=auth, PtoVta=PTO_VTA, CbteTipo=CBTE_TIPO)
    proximo_nro = ultimo.CbteNro + 1

    fecha_cbte = (fecha or datetime.datetime.now()).strftime("%Y%m%d")

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
    pedido explícito del usuario: hace una consulta HTTP por cada comprobante
    emitido, así que puede tardar si hay muchos.

    `desde`: date opcional; si se pasa, se descartan los comprobantes con
    fecha de emisión anterior."""
    creds = login.obtener_credenciales_validas()
    auth = {"Token": creds["token"], "Sign": creds["sign"], "Cuit": CUIT}
    client = _cliente_wsfe()

    ultimo = client.service.FECompUltimoAutorizado(Auth=auth, PtoVta=PTO_VTA, CbteTipo=CBTE_TIPO)
    ultimo_nro = ultimo.CbteNro

    facturas = []
    for nro in range(1, ultimo_nro + 1):
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
                continue

        facturas.append({
            "numero": nro,
            "pto_vta": detalle.PtoVta,
            "fecha_emision": detalle.CbteFch,
            "monto": detalle.ImpTotal,
            "cae": detalle.CodAutorizacion,
            "vencimiento_cae": detalle.FchVto,
        })

    facturas.sort(key=lambda f: f["numero"], reverse=True)
    return facturas


if __name__ == "__main__":
    # Prueba manual: factura de $100 a Consumidor Final, fecha de hoy.
    resultado = emitir_factura_c(importe=100.00)
    print("\n--- RESULTADO ---")
    print(resultado)
