# App de Facturacion MP -> ARCA

App de escritorio para facturar automáticamente en ARCA (ex AFIP) a partir de
transferencias recibidas por Mercado Pago. Pensada para monotributistas que
cobran turnos/servicios por transferencia directa (sin QR ni link de pago) y
necesitan emitir Factura C a Consumidor Final.

## Cómo funciona

1. Se abre la app cuando hace falta (no corre en segundo plano, no hay servidor).
2. Trae la lista de transferencias recibidas en Mercado Pago en un rango de
   fechas configurable.
3. La persona elige manualmente cuáles son turnos reales (la cuenta de MP
   suele tener movimientos personales mezclados) — no se automatiza al 100%
   a propósito.
4. Por cada transferencia elegida, emite la Factura C correspondiente en ARCA
   (WSFEv1) y guarda un historial local para no facturar dos veces lo mismo.

También tiene una pestaña de historial de facturación (con filtro por
período) que puede reconstruirse en vivo consultando directamente a ARCA,
además de leer el registro local.

## Requisitos

- Windows 10/11 con WebView2 Runtime (viene instalado de fábrica en
  versiones actualizadas de Windows).
- Python 3.10+
- Clave Fiscal nivel 3 en ARCA, un certificado digital propio, un Punto de
  Venta habilitado como "Web Services", y una cuenta en Mercado Pago
  Developers con su Access Token de producción.

## Instalación

```
pip install -r requirements.txt
python gui.py
```

Si es la primera vez que se corre en esa compu (no existe `config.py` ni
certificado), se abre un asistente de configuración que:

- Genera localmente la clave privada y la solicitud de certificado (CSR)
  para subir a ARCA, o permite cargar un certificado ya emitido.
- Pide el CUIT, el Punto de Venta y el Access Token de Mercado Pago.
- Arma `config.py` con esos datos.

También se puede armar `config.py` a mano copiando `config.example.py`.

## Empaquetar como .exe

Para no depender de tener Python instalado:

```
pip install pyinstaller
pyinstaller --onefile --noconsole --name "BeautyBiller" --icon icon.ico --add-data "gui.html;." --add-data "icon.ico;." gui.py
```

Genera `dist/BeautyBiller.exe`, un solo archivo. Se le puede pasar esa
carpeta (o solo el `.exe`, que arma `config.py` solo la primera vez) a
cualquier otra persona sin que necesite instalar nada más.

## Estructura

- `gui.py` / `gui.html` — interfaz de escritorio (pywebview).
- `onboarding.py` — asistente de primera configuración.
- `login.py` — autenticación contra WSAA (ARCA), con renovación automática
  del token.
- `facturar.py` — emisión de comprobantes vía WSFEv1, y consulta directa del
  historial de facturas ya emitidas.
- `consultar_transferencias.py` — búsqueda de transferencias recibidas en
  Mercado Pago.
- `historial.py` — registro local de qué transferencias ya se facturaron.
- `rutas.py` — resolución de rutas de archivos, compatible tanto con correr
  desde código fuente como empaquetado en un `.exe`.
- `registro.py` — logging a archivo (`beauty_biller.log`) para poder
  diagnosticar problemas sin acceso directo a la pantalla del usuario.
- `main.py` — versión por consola del mismo flujo, útil para debug.

## Notas

- Todo corre contra producción real de ARCA y Mercado Pago (no hay entorno
  de homologación/sandbox configurado).
- La firma del TRA y la generación de clave/CSR se hacen con la librería
  `cryptography` — no hace falta tener OpenSSL instalado.
