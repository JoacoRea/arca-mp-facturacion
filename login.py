import base64
import datetime
import os
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs7
from zeep import Client
from zeep.exceptions import Fault
import re
import json

import rutas
from config import CERT_PATH, KEY_PATH

# --- Configuración ---
SERVICE = "wsfe"  # facturación electrónica
WSAA_WSDL = "https://wsaa.afip.gov.ar/ws/services/LoginCms?wsdl"  # PRODUCCIÓN

CREDENCIALES_PATH = rutas.ruta_datos("credenciales.json")

# Argentina no usa horario de verano: el offset es -03:00 todo el año. Calcular
# las horas a partir de este huso (y no de la hora local de la PC) evita que
# WSAA rechace el TRA si la computadora está configurada en otra zona horaria.
ZONA_AR = datetime.timezone(datetime.timedelta(hours=-3))

# Traducción de los errores más comunes de WSAA a algo accionable por la usuaria.
_ERRORES_WSAA = [
    ("alreadyAuthenticated", "ARCA dice que ya hay un ticket de acceso vigente para este certificado. "
                             "Esperá unos 10 minutos y volvé a intentar (si venís de usar el certificado "
                             "en otra computadora, borrá credenciales.json)."),
    ("cms.cert.expired", "El certificado de ARCA está vencido. Generá uno nuevo en ARCA "
                         "(Administración de Certificados Digitales) y volvé a instalarlo."),
    ("cms.cert.untrusted", "ARCA no reconoce el certificado: no fue emitido por ARCA o no corresponde "
                           "al ambiente de producción."),
    ("generationTime", "ARCA rechazó la fecha del pedido. Revisá que la fecha y hora de esta "
                       "computadora estén bien configuradas."),
    ("expirationTime", "ARCA rechazó la fecha del pedido. Revisá que la fecha y hora de esta "
                       "computadora estén bien configuradas."),
]


def generar_tra():
    """Genera y devuelve el Ticket Request Access (XML) que se va a firmar."""
    ahora = datetime.datetime.now(ZONA_AR).replace(microsecond=0)
    generation_time = (ahora - datetime.timedelta(minutes=10)).isoformat()
    expiration_time = (ahora + datetime.timedelta(minutes=10)).isoformat()
    unique_id = str(int(ahora.timestamp()))

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<loginTicketRequest version="1.0">
  <header>
    <uniqueId>{unique_id}</uniqueId>
    <generationTime>{generation_time}</generationTime>
    <expirationTime>{expiration_time}</expirationTime>
  </header>
  <service>{SERVICE}</service>
</loginTicketRequest>"""

def firmar_tra(tra):
    """Firma el TRA y devuelve el CMS (PKCS7) adjunto en DER, tal como pide ARCA.

    Antes se hacía shelling out a `openssl cms -sign`, pero eso requiere tener
    OpenSSL instalado y en el PATH (en esta máquina venía de Git para Windows,
    algo que no se puede asumir en la compu de otra persona). Con la librería
    `cryptography` no hace falta ningún ejecutable externo.
    """
    with open(rutas.ruta_datos(CERT_PATH), "rb") as f:
        certificado = x509.load_pem_x509_certificate(f.read())
    with open(rutas.ruta_datos(KEY_PATH), "rb") as f:
        clave_privada = serialization.load_pem_private_key(f.read(), password=None)

    return (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(tra.encode("utf-8"))
        .add_signer(certificado, clave_privada, hashes.SHA256())
        .sign(serialization.Encoding.DER, [])
    )

def pedir_token(cms_bytes):
    """Manda el CMS firmado a WSAA y devuelve el token + sign."""
    cms_b64 = base64.b64encode(cms_bytes).decode("utf-8")

    client = Client(WSAA_WSDL)
    try:
        return client.service.loginCms(in0=cms_b64)
    except Fault as e:
        raise RuntimeError(_traducir_error_wsaa(str(e))) from e


def _traducir_error_wsaa(mensaje):
    for clave, texto in _ERRORES_WSAA:
        if clave in mensaje:
            return texto
    return f"Error de autenticación con ARCA (WSAA): {mensaje}"


def _generar_credenciales():
    """Corre el flujo completo (TRA + firma + WSAA) y guarda credenciales.json con su vencimiento."""
    tra = generar_tra()
    cms = firmar_tra(tra)
    resultado = pedir_token(cms)

    token = re.search(r"<token>(.*?)</token>", resultado).group(1)
    sign = re.search(r"<sign>(.*?)</sign>", resultado).group(1)
    expiration_time = re.search(r"<expirationTime>(.*?)</expirationTime>", resultado).group(1)

    creds = {"token": token, "sign": sign, "expiration_time": expiration_time}
    with open(CREDENCIALES_PATH, "w") as f:
        json.dump(creds, f)

    return creds


def obtener_credenciales_validas():
    """Devuelve credenciales vigentes, renovándolas solas contra WSAA si no existen o ya vencieron."""
    if os.path.exists(CREDENCIALES_PATH):
        with open(CREDENCIALES_PATH) as f:
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
    print("Generando TRA, firmando y pidiendo token a WSAA (producción)...")
    creds = _generar_credenciales()
    print(f"\nToken y sign guardados en credenciales.json (vence {creds['expiration_time']})")
