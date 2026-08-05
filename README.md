# App de Facturación -> ARCA

App de escritorio para emitir Facturas C en ARCA (ex AFIP) a partir de las
transferencias que uno recibe. Pensada para monotributistas que cobran por
transferencia directa y tienen que facturar a mano cobro por cobro.

Hay **dos variantes** que comparten todo el motor (login contra WSAA, emisión
por WSFEv1, historial local, asistente de certificado) y se diferencian solo en
de dónde salen los movimientos:

| Variante | Se abre con | Fuente de los movimientos |
|---|---|---|
| Mercado Pago | `python gui.py` | API de Mercado Pago (automática) |
| Banco Galicia | `python gui_galicia.py` | Excel exportado del Home Banking |

La variante de Galicia existe porque el banco no tiene API pública de
movimientos: la persona baja el Excel del Home Banking y la app lo lee.

## Cómo funciona (Mercado Pago)

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

## Cómo funciona (Banco Galicia)

1. En el Home Banking: Cuentas → Movimientos → se elige el período y se
   exporta a Excel.
2. Se abre la app (`python gui_galicia.py`) y se elige ese archivo. Aparecen
   todos los **créditos** del extracto (los débitos se ignoran: nunca se
   facturan), con fecha, importe, nombre y CUIT del titular que transfirió.
3. Se tildan los que hay que facturar. Todos vienen ya con el perfil de
   facturación puesto (ver abajo); si alguna vez hace falta una excepción, se
   puede cambiar movimiento por movimiento, o fijar otro valor para todos en
   la barra "Cómo facturar":
   - **Concepto**: Productos, Servicios, o Productos y Servicios.
   - **Receptor**: consumidor final, o identificado con el DNI o el CUIT del
     titular que sale del extracto (con su condición frente al IVA).
   - **Detalle**, que queda guardado en el historial local.
   - **Fecha de la factura**: hoy (lo normal) o la del movimiento.
4. Se emiten las Facturas C y se guarda el historial local, igual que en la
   variante de Mercado Pago.

### Perfil de facturación

Todo lo que se factura por acá sale siempre igual, así que ese es el estado
inicial de la pantalla (`PERFIL`, arriba de todo en `gui_galicia.py`):

| Dato | Valor | Cómo viaja a ARCA |
|---|---|---|
| Tipo de comprobante | Factura C | `CbteTipo = 11` |
| Condición de IVA del receptor | Consumidor Final | `DocTipo 99` / `DocNro 0` / `CondicionIVAReceptorId 5` |
| Tipo | Servicio | `Concepto = 2` |
| Producto / servicio | Asesoría | solo al historial local |
| Condición de venta | Transferencia bancaria | solo al historial local |
| Fechas "desde" y "hasta" del servicio | Día de facturación | `FchServDesde = FchServHasta = CbteFch` |

Las dos filas que dicen "solo al historial local" son campos que WSFEv1
**no tiene**: la descripción del producto/servicio y la condición de venta
existen en "Comprobantes en Línea" (el formulario web de ARCA), no en el Web
Service. La app los guarda en `historial_facturas.json` para que el registro
propio quede completo, pero no aparecen en el comprobante que emite ARCA.
Para cambiar cualquiera de estos valores por defecto, se edita `PERFIL`.

Cada movimiento del extracto recibe un ID propio y estable (fecha + importe +
texto del movimiento), así que se puede volver a importar el mismo mes —o un
período que se superponga— sin riesgo de facturar dos veces lo mismo: lo ya
facturado aparece marcado y bloqueado.

Detalles que vale saber:

- El extracto no trae número de operación, y el nombre del titular viene
  recortado por el banco (`GRICELDA NOEMI ZUPEL`): es lo que hay.
- El CUIT se valida con su dígito verificador antes de ofrecerlo como
  receptor; si no es válido, ese movimiento solo se puede facturar a
  consumidor final.
- El DNI se deduce del CUIL de las personas físicas (27-13242063-2 → DNI
  13242063).
- La Factura C emitida por Web Service no lleva descripción de los ítems, así
  que el "detalle" que se escribe en pantalla (por defecto, "Asesoría") es
  solo para el historial propio: a ARCA no viaja.

## Requisitos

- Windows 10/11 con WebView2 Runtime (viene instalado de fábrica en
  versiones actualizadas de Windows).
- Python 3.10+
- Clave Fiscal nivel 3 en ARCA, un certificado digital propio y un Punto de
  Venta habilitado como "Web Services".
- Solo para la variante de Mercado Pago: una cuenta en Mercado Pago
  Developers con su Access Token de producción. La de Galicia no necesita
  ninguna credencial del banco — solo el Excel.

## Instalación

```
pip install -r requirements.txt
python gui.py            # variante Mercado Pago
python gui_galicia.py    # variante Banco Galicia
```

Si es la primera vez que se corre en esa compu (no existe `config.py` ni
certificado), se abre un asistente de configuración que:

- Genera localmente la clave privada y la solicitud de certificado (CSR)
  para subir a ARCA, o permite cargar un certificado ya emitido.
- Pide el CUIT y el Punto de Venta (y el Access Token de Mercado Pago, si es
  la variante de MP).
- Arma `config.py` con esos datos.

También se puede armar `config.py` a mano copiando `config.example.py`.

## Empaquetar como .exe

Para no depender de tener Python instalado:

```
pip install pyinstaller

# Variante Mercado Pago
pyinstaller --onefile --noconsole --name "BeautyBiller" --icon icon.ico --add-data "gui.html;." --add-data "icon.ico;." gui.py

# Variante Banco Galicia
pyinstaller --onefile --noconsole --name "FacturacionGalicia" --icon icon.ico --add-data "gui_galicia.html;." --add-data "icon.ico;." gui_galicia.py
```

Genera un `.exe` en `dist/`, un solo archivo. Se le puede pasar esa carpeta (o
solo el `.exe`, que arma `config.py` solo la primera vez) a cualquier otra
persona sin que necesite instalar nada más.

## Estructura

Compartido por las dos variantes:

- `onboarding.py` — asistente de primera configuración.
- `login.py` — autenticación contra WSAA (ARCA), con renovación automática
  del token.
- `facturar.py` — emisión de comprobantes vía WSFEv1 (concepto, receptor y
  fechas de servicio configurables), y consulta directa del historial de
  facturas ya emitidas.
- `historial.py` — registro local de qué movimientos ya se facturaron.
- `rutas.py` — resolución de rutas de archivos, compatible tanto con correr
  desde código fuente como empaquetado en un `.exe`.
- `registro.py` — logging a archivo para poder diagnosticar problemas sin
  acceso directo a la pantalla del usuario.

Variante Mercado Pago:

- `gui.py` / `gui.html` — interfaz de escritorio (pywebview).
- `consultar_transferencias.py` — búsqueda de transferencias recibidas en
  Mercado Pago.
- `main.py` — versión por consola del mismo flujo, útil para debug.

Variante Banco Galicia:

- `gui_galicia.py` / `gui_galicia.html` — interfaz de escritorio.
- `extracto_galicia.py` — lectura del Excel del Home Banking. Se puede correr
  suelto para ver qué entiende de un archivo:
  `python extracto_galicia.py extracto.xlsx`.

## Notas

- Todo corre contra producción real de ARCA y Mercado Pago (no hay entorno
  de homologación/sandbox configurado).
- La firma del TRA y la generación de clave/CSR se hacen con la librería
  `cryptography` — no hace falta tener OpenSSL instalado.
- Las dos variantes comparten `config.py` y `historial_facturas.json`, así que
  pueden convivir en la misma carpeta sin pisarse (los IDs de Mercado Pago y
  los del extracto de Galicia no se solapan).
- El formato del Excel de Galicia no está documentado por el banco. Si en
  algún momento lo cambian, lo primero que hay que mirar es la detección de
  encabezados en `extracto_galicia.py`.
