"""Primera configuración de Beauty Biller para un usuario nuevo en su propia
compu, cuando todavía no existe config.py armado ni certificado de ARCA.

Si config.py no existe, este módulo lo crea con valores en blanco ANTES de
que cualquier otro módulo (login.py, facturar.py, consultar.py) intente
importar sus constantes — por eso gui.py importa `onboarding` primero que
nada. Con config.py garantizado (aunque esté vacío), el resto de la app no
se rompe al arrancar sin estar configurada; el wizard de gui.html se encarga
de completarlo.
"""
import os
import shutil

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

import rutas

CONFIG_PATH = rutas.ruta_datos("config.py")
CERT_PATH = rutas.ruta_datos("certificado.crt")
KEY_PATH = rutas.ruta_datos("MiClavePrivada.key")
CSR_PATH = rutas.ruta_datos("certificado.csr")

_TEMPLATE_VACIO = '''"""Datos propios de cada usuario de la app.

Todavía no se completó la primera configuración. Abrí Beauty Biller
(python gui.py) y seguí el asistente, o completá estos valores a mano.
"""

MP_ACCESS_TOKEN = None

CUIT = None

PTO_VTA = None

CERT_PATH = "certificado.crt"
KEY_PATH = "MiClavePrivada.key"
'''

if not os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(_TEMPLATE_VACIO)

import config  # noqa: E402 (tiene que ir después de garantizar que el archivo existe)


def necesita_onboarding():
    campos_ok = all([
        getattr(config, "MP_ACCESS_TOKEN", None),
        getattr(config, "CUIT", None),
        getattr(config, "PTO_VTA", None),
    ])
    cert_rel = getattr(config, "CERT_PATH", None)
    key_rel = getattr(config, "KEY_PATH", None)
    cert_ok = bool(cert_rel) and os.path.exists(rutas.ruta_datos(cert_rel))
    key_ok = bool(key_rel) and os.path.exists(rutas.ruta_datos(key_rel))
    return not (campos_ok and cert_ok and key_ok)


def estado_certificado():
    return {
        "key_existe": os.path.exists(KEY_PATH),
        "csr_existe": os.path.exists(CSR_PATH),
        "crt_existe": os.path.exists(CERT_PATH),
    }


def generar_clave_y_csr(cuit, alias):
    """Genera localmente la clave privada y la solicitud de certificado (CSR)
    que hay que subir a ARCA. Todo con la librería `cryptography` — no hace
    falta tener OpenSSL instalado ni conexión a internet."""
    if os.path.exists(KEY_PATH):
        raise FileExistsError(
            "Ya existe una clave privada generada (MiClavePrivada.key). Si generás una "
            "nueva vas a invalidar el CSR anterior si ya lo subiste a ARCA. Borrá "
            "MiClavePrivada.key y certificado.csr a mano si de verdad querés empezar de nuevo."
        )

    cuit_str = str(cuit).strip().replace("-", "")
    if not (cuit_str.isdigit() and len(cuit_str) == 11):
        raise ValueError("El CUIT debe tener 11 dígitos, sin guiones.")
    if not alias or not alias.strip():
        raise ValueError("Falta el alias del certificado.")

    clave_privada = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with open(KEY_PATH, "wb") as f:
        f.write(clave_privada.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ))

    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "AR"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Monotributista"),
        x509.NameAttribute(NameOID.COMMON_NAME, alias.strip()),
        x509.NameAttribute(NameOID.SERIAL_NUMBER, f"CUIT {cuit_str}"),
    ])
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(subject)
        .sign(clave_privada, hashes.SHA256())
    )
    with open(CSR_PATH, "wb") as f:
        f.write(csr.public_bytes(serialization.Encoding.PEM))

    return {"key_path": KEY_PATH, "csr_path": CSR_PATH}


def instalar_certificado(origen_path):
    """Copia un certificado.crt ya descargado de ARCA a la carpeta de la app."""
    shutil.copyfile(origen_path, CERT_PATH)
    return CERT_PATH


def instalar_clave(origen_path):
    """Copia una clave privada existente a la carpeta de la app (caso 'ya tengo certificado')."""
    shutil.copyfile(origen_path, KEY_PATH)
    return KEY_PATH


def guardar_config(mp_access_token, cuit, pto_vta):
    cuit_str = str(cuit).strip().replace("-", "")
    if not (cuit_str.isdigit() and len(cuit_str) == 11):
        raise ValueError("El CUIT debe tener 11 dígitos, sin guiones.")
    try:
        pto_vta_int = int(pto_vta)
    except (TypeError, ValueError):
        raise ValueError("El punto de venta debe ser un número.")
    if not mp_access_token or not mp_access_token.strip():
        raise ValueError("Falta el Access Token de Mercado Pago.")

    contenido = f'''"""Datos propios de cada usuario de la app (completado por el asistente de configuración).

Para reconfigurar, abrí Beauty Biller y usá el botón "Reconfigurar", o
editá estos valores a mano.
"""

MP_ACCESS_TOKEN = {mp_access_token.strip()!r}

CUIT = {int(cuit_str)}

PTO_VTA = {pto_vta_int}

CERT_PATH = "certificado.crt"
KEY_PATH = "MiClavePrivada.key"
'''
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(contenido)
