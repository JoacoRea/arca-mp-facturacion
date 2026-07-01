"""Script de prueba manual: consulta un comprobante puntual a ARCA (WSFEv1).

Reutiliza el cliente SOAP de facturar.py (mismo SSLAdapter y WSDL).
"""
import login
import facturar
from config import CUIT, PTO_VTA


def main():
    creds = login.obtener_credenciales_validas()
    client = facturar.cliente_wsfe()

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
