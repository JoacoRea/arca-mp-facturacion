import base64
import datetime
import os
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs7
from zeep import Client
from zeep.transports import Transport
import requests
import re
import json

from config import CERT_PATH, KEY_PATH

# --- Configuración ---
SERVICE = "wsfe"  # facturación electrónica
WSAA_WSDL = "https://wsaa.afip.gov.ar/ws/services/LoginCms?wsdl"  # PRODUCCIÓN

def generar_tra():
    """Genera el Ticket Request Access (XML) que se va a firmar."""
    ahora = datetime.datetime.now()
    generation_time = (ahora - datetime.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S-03:00")
    expiration_time = (ahora + datetime.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S-03:00")
    unique_id = str(int(ahora.timestamp()))

    tra = f"""<?xml version="1.0" encoding="UTF-8"?>
<loginTicketRequest version="1.0">
  <header>
    <uniqueId>{unique_id}</uniqueId>
    <generationTime>{generation_time}</generationTime>
    <expirationTime>{expiration_time}</expirationTime>
  </header>
  <service>{SERVICE}</service>
</loginTicketRequest>"""

    with open("tra.xml", "w", encoding="utf-8") as f:
        f.write(tra)

def firmar_tra():
    """Firma el TRA generando un CMS (PKCS7) adjunto en DER, tal como pide ARCA.

    Antes se hacía shelling out a `openssl cms -sign`, pero eso requiere tener
    OpenSSL instalado y en el PATH (en esta máquina venía de Git para Windows,
    algo que no se puede asumir en la compu de otra persona). Con la librería
    `cryptography` no hace falta ningún ejecutable externo.
    """
    with open(CERT_PATH, "rb") as f:
        certificado = x509.load_pem_x509_certificate(f.read())
    with open(KEY_PATH, "rb") as f:
        clave_privada = serialization.load_pem_private_key(f.read(), password=None)
    with open("tra.xml", "rb") as f:
        tra_bytes = f.read()

    firmado = (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(tra_bytes)
        .add_signer(certificado, clave_privada, hashes.SHA256())
        .sign(serialization.Encoding.DER, [])
    )

    with open("tra.cms", "wb") as f:
        f.write(firmado)

def pedir_token():
    """Manda el CMS firmado a WSAA y devuelve el token + sign."""
    with open("tra.cms", "rb") as f:
        cms_bytes = f.read()
    cms_b64 = base64.b64encode(cms_bytes).decode("utf-8")

    client = Client(WSAA_WSDL)
    response = client.service.loginCms(in0=cms_b64)
    return response


def _generar_credenciales():
    """Corre el flujo completo (TRA + firma + WSAA) y guarda credenciales.json con su vencimiento."""
    generar_tra()
    firmar_tra()
    resultado = pedir_token()

    token = re.search(r"<token>(.*?)</token>", resultado).group(1)
    sign = re.search(r"<sign>(.*?)</sign>", resultado).group(1)
    expiration_time = re.search(r"<expirationTime>(.*?)</expirationTime>", resultado).group(1)

    creds = {"token": token, "sign": sign, "expiration_time": expiration_time}
    with open("credenciales.json", "w") as f:
        json.dump(creds, f)

    return creds


def obtener_credenciales_validas():
    """Devuelve credenciales vigentes, renovándolas solas contra WSAA si no existen o ya vencieron."""
    if os.path.exists("credenciales.json"):
        with open("credenciales.json") as f:
            creds = json.load(f)

        vencimiento = creds.get("expiration_time")
        if vencimiento:
            vencimiento_dt = datetime.datetime.fromisoformat(vencimiento)
            margen = datetime.timedelta(minutes=5)
            ahora = datetime.datetime.now(vencimiento_dt.tzinfo)
            if ahora < vencimiento_dt - margen:
                return creds

    return _generar_credenciales()


if __name__ == "__main__":
    print("Generando TRA...")
    print("Firmando...")
    print("Pidiendo token a WSAA (producción)...")
    creds = _generar_credenciales()
    print(f"\nToken y sign guardados en credenciales.json (vence {creds['expiration_time']})")