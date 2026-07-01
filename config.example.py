"""Datos propios de cada usuario de la app.

Copiá este archivo como config.py y completá tus datos (o simplemente
borralo / no lo crees: al abrir gui.py sin config.py, la app arranca el
asistente de primera configuración y lo arma sola).
"""

# --- Mercado Pago ---
# Token de PRODUCCIÓN de la cuenta de MP que recibe las transferencias
# (Mercado Pago Developers -> tu app -> Credenciales de producción).
MP_ACCESS_TOKEN = "APP_USR-..."

# --- ARCA / AFIP ---
# CUIT del monotributista que factura (sin puntos ni guiones).
CUIT = 20000000000

# Punto de Venta habilitado como "Web Services" en ARCA para este CUIT.
PTO_VTA = 1

# Rutas al certificado digital vinculado a este CUIT en ARCA (Administración
# de Certificados Digitales) y a su clave privada correspondiente.
CERT_PATH = "certificado.crt"
KEY_PATH = "MiClavePrivada.key"
