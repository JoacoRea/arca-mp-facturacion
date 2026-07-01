import ssl
import requests
from zeep import Client
from zeep.transports import Transport
from requests.adapters import HTTPAdapter

import login
from config import CUIT, PTO_VTA

WSFE_WSDL = "https://servicios1.afip.gov.ar/wsfev1/service.asmx?WSDL"

class SSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)

def main():
    creds = login.obtener_credenciales_validas()

    session = requests.Session()
    session.mount("https://", SSLAdapter())
    transport = Transport(session=session)
    client = Client(WSFE_WSDL, transport=transport)

    auth = {
        "Token": creds["token"],
        "Sign": creds["sign"],
        "Cuit": CUIT
    }

    resultado = client.service.FECompConsultar(
        Auth=auth,
        FeCompConsReq={
            "CbteTipo": 11,  # Factura C
            "CbteNro": 1,
            "PtoVta": PTO_VTA
        }
    )
    print(resultado)

if __name__ == "__main__":
    main()