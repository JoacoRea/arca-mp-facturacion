"""Comprobante en PDF de una Factura C que ARCA ya autorizó.

El Web Service de ARCA (WSFEv1) autoriza la factura y devuelve el CAE, pero no
genera ningún documento: la factura en sí, con la descripción del servicio, la
condición de venta y los datos del emisor que exige la RG 1415, la tiene que
armar quien factura. Este módulo la arma a partir de lo que guardó el
historial más los datos del emisor, que se cargan una sola vez.

La validez no depende de que el PDF lo genere ARCA: viene de que tenga esos
datos, el CAE que ARCA ya otorgó y el código QR de la RG 4892, con el que
cualquiera puede verificar el comprobante contra ARCA.

El PDF se escribe a mano, sin librerías de PDF. Las conocidas (fpdf2,
reportlab) dependen de Pillow, que trae código compilado, y en una Mac vieja
eso puede no instalarse (pasó con cryptography). Una factura de una página son
texto, líneas y rectángulos: alcanza con lo básico del formato. El QR sale de
`qrcode`, que es Python puro.
"""
import base64
import datetime
import json
import os
import subprocess
import sys
import unicodedata

import qrcode

import historial
import rutas

DATOS_EMISOR_PATH = rutas.ruta_datos("datos_emisor.json")
CARPETA_COMPROBANTES = rutas.ruta_datos("comprobantes")

URL_QR = "https://www.afip.gob.ar/fe/qr/?p="
CBTE_TIPO_FACTURA_C = 11

# Datos del emisor que el comprobante tiene que mostrar y que ARCA no devuelve
# por Web Service. Todos son obligatorios.
CAMPOS_EMISOR = {
    "nombre": ("Nombre o razón social", 120),
    "domicilio": ("Domicilio comercial", 160),
    "iibb": ("Ingresos Brutos", 40),
    "inicio_actividades": ("Fecha de inicio de actividades", 10),
    "descripcion": ("Qué se factura", 120),
    "condicion_venta": ("Condición de venta", 40),
}

DOCUMENTOS = {80: "CUIT", 96: "DNI"}


class FaltanDatosEmisor(Exception):
    """El comprobante no se puede armar hasta que se carguen los datos del emisor."""


# --- Datos del emisor ---

def _fecha_iso(texto):
    """Acepta dd/mm/aaaa (lo que escribe una persona) o aaaa-mm-dd."""
    texto = str(texto or "").strip()
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.datetime.strptime(texto, formato).date().isoformat()
        except ValueError:
            continue
    return None


def cargar_datos_emisor(por_defecto=None):
    """Devuelve los datos guardados, completando con `por_defecto` lo que falte."""
    datos = {campo: "" for campo in CAMPOS_EMISOR}
    datos.update({k: v for k, v in (por_defecto or {}).items() if k in CAMPOS_EMISOR})
    if os.path.exists(DATOS_EMISOR_PATH):
        try:
            with open(DATOS_EMISOR_PATH, encoding="utf-8") as f:
                guardados = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise RuntimeError(
                f"El archivo {os.path.basename(DATOS_EMISOR_PATH)} está dañado. "
                "Borralo y volvé a cargar los datos del comprobante."
            ) from e
        datos.update({k: v for k, v in guardados.items() if k in CAMPOS_EMISOR and v})
    return datos


def datos_faltantes(datos):
    return [campo for campo in CAMPOS_EMISOR if not str(datos.get(campo) or "").strip()]


def guardar_datos_emisor(datos):
    """Valida y guarda los datos del emisor. Levanta ValueError con un mensaje mostrable."""
    limpios = {}
    for campo, (nombre, largo_max) in CAMPOS_EMISOR.items():
        valor = " ".join(str(datos.get(campo) or "").split())
        if not valor:
            raise ValueError(f"Falta completar: {nombre}.")
        if len(valor) > largo_max:
            raise ValueError(f"{nombre}: es demasiado largo (máximo {largo_max} caracteres).")
        limpios[campo] = valor

    fecha = _fecha_iso(limpios["inicio_actividades"])
    if fecha is None:
        raise ValueError("La fecha de inicio de actividades tiene que tener la forma dd/mm/aaaa.")
    limpios["inicio_actividades"] = fecha

    tmp = DATOS_EMISOR_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(limpios, f, indent=2, ensure_ascii=False)
    os.replace(tmp, DATOS_EMISOR_PATH)
    return limpios


# --- Formatos ---

def _fecha_corta(raw):
    """20260901 o 2026-09-01 -> 01/09/2026."""
    raw = str(raw or "")
    if raw.isdigit() and len(raw) == 8:
        return f"{raw[6:8]}/{raw[4:6]}/{raw[0:4]}"
    iso = _fecha_iso(raw[:10])
    return datetime.date.fromisoformat(iso).strftime("%d/%m/%Y") if iso else raw


def _fecha_qr(raw):
    raw = str(raw or "")
    if raw.isdigit() and len(raw) == 8:
        return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
    return _fecha_iso(raw[:10]) or raw


def _plata(monto):
    return f"{float(monto):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


# --- Código QR (RG 4892) ---

def url_qr(registro, cuit, pto_vta):
    """La URL que va en el QR: los datos del comprobante en JSON, en base64,
    tal como lo define ARCA. Al escanearla, ARCA muestra si el comprobante es
    válido."""
    datos = {
        "ver": 1,
        "fecha": _fecha_qr(registro.get("fecha_emision") or registro.get("fecha_transferencia")),
        "cuit": int(cuit),
        "ptoVta": int(pto_vta),
        "tipoCmp": CBTE_TIPO_FACTURA_C,
        "nroCmp": int(registro["numero"]),
        "importe": round(float(registro["monto"]), 2),
        "moneda": "PES",
        "ctz": 1,
        "tipoDocRec": int(registro.get("doc_tipo") or 99),
        "nroDocRec": int(registro.get("doc_nro") or 0),
        "tipoCodAut": "E",
        "codAut": int(registro["cae"]),
    }
    carga = json.dumps(datos, separators=(",", ":")).encode("utf-8")
    return URL_QR + base64.b64encode(carga).decode("ascii")


def _matriz_qr(url):
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=0)
    qr.add_data(url)
    qr.make(fit=True)
    return qr.get_matrix()


# --- PDF ---

# Anchos de las fuentes estándar del PDF (en milésimas del tamaño), para poder
# alinear texto a la derecha. Son las métricas oficiales de Helvetica para los
# caracteres 32 a 126; las letras con tilde usan el ancho de la letra base.
_ANCHOS = {
    False: [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
            556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
            1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
            667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
            333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
            556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584],
    True: [278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278,
           556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611,
           975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778,
           667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556,
           333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611,
           611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584],
}


def _ancho(texto, tamano, negrita=False):
    tabla = _ANCHOS[negrita]
    total = 0
    for c in str(texto):
        if c == "°":
            total += 400
            continue
        base = unicodedata.normalize("NFKD", c)[:1] or c
        codigo = ord(base)
        total += tabla[codigo - 32] if 32 <= codigo <= 126 else 556
    return total * tamano / 1000


def _partir(texto, ancho_max, tamano, negrita=False):
    """Corta el texto en líneas que entren en `ancho_max`."""
    lineas, actual = [], ""
    for palabra in str(texto).split():
        prueba = f"{actual} {palabra}".strip()
        if not actual or _ancho(prueba, tamano, negrita) <= ancho_max:
            actual = prueba
        else:
            lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas or [""]


def _escapar(texto):
    return str(texto).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class _Hoja:
    """Una página A4. Las coordenadas se pasan desde arriba a la izquierda, como
    se piensa un diseño; el PDF las cuenta desde abajo, y la conversión se hace acá."""

    ANCHO, ALTO = 595.28, 841.89

    def __init__(self):
        self._ops = []

    def _y(self, y):
        return self.ALTO - y

    def texto(self, x, y, texto, tamano=9, negrita=False, alinear="izquierda"):
        if alinear == "derecha":
            x -= _ancho(texto, tamano, negrita)
        elif alinear == "centro":
            x -= _ancho(texto, tamano, negrita) / 2
        fuente = "F2" if negrita else "F1"
        self._ops.append(f"BT /{fuente} {tamano:g} Tf {x:.2f} {self._y(y):.2f} Td ({_escapar(texto)}) Tj ET")

    def campo(self, x, y, etiqueta, valor, tamano=8.5):
        """Etiqueta en negrita seguida del valor, como en las facturas de ARCA."""
        self.texto(x, y, etiqueta, tamano, negrita=True)
        self.texto(x + _ancho(etiqueta, tamano, True) + 3, y, valor, tamano)

    def linea(self, x1, y1, x2, y2, grosor=0.6):
        self._ops.append(f"{grosor:g} w {x1:.2f} {self._y(y1):.2f} m {x2:.2f} {self._y(y2):.2f} l S")

    def rect(self, x, y, ancho, alto, gris=None, grosor=0.6):
        """Rectángulo con borde; `gris` (0 negro, 1 blanco) lo rellena."""
        relleno = f"{gris:g} g " if gris is not None else ""
        operador = "B" if gris is not None else "S"
        self._ops.append(
            f"q {relleno}{grosor:g} w {x:.2f} {self._y(y + alto):.2f} {ancho:.2f} {alto:.2f} re {operador} Q"
        )

    def qr(self, x, y, lado, matriz):
        modulo = lado / len(matriz)
        partes = ["q 0 g"]
        for fila, celdas in enumerate(matriz):
            # Los módulos negros seguidos de una fila van en un solo rectángulo:
            # el archivo queda más chico y no aparecen rayitas entre módulos.
            col = 0
            while col < len(celdas):
                if not celdas[col]:
                    col += 1
                    continue
                inicio = col
                while col < len(celdas) and celdas[col]:
                    col += 1
                partes.append(
                    f"{x + inicio * modulo:.3f} {self._y(y + (fila + 1) * modulo):.3f} "
                    f"{(col - inicio) * modulo:.3f} {modulo:.3f} re"
                )
        partes.append("f Q")
        self._ops.append(" ".join(partes))

    def pdf(self, titulo=""):
        contenido = "\n".join(self._ops).encode("cp1252", "replace")
        fuente = "<< /Type /Font /Subtype /Type1 /BaseFont /{} /Encoding /WinAnsiEncoding >>"
        objetos = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {self.ANCHO} {self.ALTO}] "
             "/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> /Contents 4 0 R >>").encode("ascii"),
            b"<< /Length %d >>\nstream\n" % len(contenido) + contenido + b"\nendstream",
            fuente.format("Helvetica").encode("ascii"),
            fuente.format("Helvetica-Bold").encode("ascii"),
            f"<< /Title ({_escapar(titulo)}) /Producer (Facturacion ARCA) >>".encode("cp1252", "replace"),
        ]
        salida = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        posiciones = []
        for numero, objeto in enumerate(objetos, start=1):
            posiciones.append(len(salida))
            salida += b"%d 0 obj\n" % numero + objeto + b"\nendobj\n"
        inicio_xref = len(salida)
        salida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
        for posicion in posiciones:
            salida += b"%010d 00000 n \n" % posicion
        salida += (b"trailer\n<< /Size %d /Root 1 0 R /Info 7 0 R >>\nstartxref\n%d\n%%%%EOF\n"
                   % (len(objetos) + 1, inicio_xref))
        return bytes(salida)


def generar_pdf(registro, emisor, cuit, pto_vta):
    """Arma el PDF de la factura y lo devuelve como bytes."""
    numero = int(registro["numero"])
    monto = float(registro["monto"])
    fecha_emision = registro.get("fecha_emision") or registro.get("fecha_transferencia")
    concepto = int(registro.get("concepto") or 2)  # la app de Mercado Pago siempre factura servicios
    doc_tipo = int(registro.get("doc_tipo") or 99)
    doc_nro = registro.get("doc_nro") or 0
    descripcion = registro.get("detalle") or emisor["descripcion"]
    condicion_venta = registro.get("condicion_venta") or emisor["condicion_venta"]
    receptor = str(registro.get("de") or "")
    if receptor.startswith("(") or "@" in receptor:
        receptor = ""  # marcadores como "(sin nombre en el extracto)" o un mail no van como nombre

    h = _Hoja()
    izq, der = 28, 567.28
    medio = (izq + der) / 2

    # Copia
    h.rect(izq, 28, der - izq, 20)
    h.texto(medio, 42, "ORIGINAL", 11, negrita=True, alinear="centro")

    # Encabezado, con la letra del comprobante en el centro
    h.rect(izq, 48, der - izq, 132)
    h.rect(medio - 22, 48, 44, 42, gris=1)
    h.texto(medio, 76, "C", 26, negrita=True, alinear="centro")
    h.texto(medio, 86, "COD. 011", 6.5, negrita=True, alinear="centro")
    h.linea(medio, 90, medio, 180)

    y = 78
    for linea in _partir(emisor["nombre"], medio - izq - 40, 14, negrita=True)[:2]:
        h.texto(izq + 12, y, linea, 14, negrita=True)
        y += 17
    h.campo(izq + 12, 122, "Razón Social:", emisor["nombre"][:48])
    domicilio = _partir(emisor["domicilio"], medio - izq - 110, 8.5)
    h.campo(izq + 12, 138, "Domicilio Comercial:", domicilio[0])
    if len(domicilio) > 1:
        h.texto(izq + 12 + _ancho("Domicilio Comercial:", 8.5, True) + 3, 149, " ".join(domicilio[1:]), 8.5)
    h.campo(izq + 12, 166, "Condición frente al IVA:", "Responsable Monotributo")

    x = medio + 34
    h.texto(x, 76, "FACTURA", 18, negrita=True)
    h.campo(x, 100, "Punto de Venta:", f"{int(pto_vta):05d}")
    h.campo(x + 120, 100, "Comp. Nro:", f"{numero:08d}")
    h.campo(x, 116, "Fecha de Emisión:", _fecha_corta(fecha_emision))
    h.campo(x, 138, "CUIT:", str(cuit))
    h.campo(x, 152, "Ingresos Brutos:", emisor["iibb"])
    h.campo(x, 166, "Fecha de Inicio de Actividades:", _fecha_corta(emisor["inicio_actividades"]))

    # Período facturado: solo para servicios
    y = 186
    if concepto in (2, 3):
        h.rect(izq, y, der - izq, 20)
        fecha = _fecha_corta(fecha_emision)
        h.campo(izq + 12, y + 13.5, "Período Facturado Desde:", fecha)
        h.campo(izq + 210, y + 13.5, "Hasta:", fecha)
        h.campo(izq + 330, y + 13.5, "Fecha de Vto. para el pago:", fecha)
        y += 26

    # Receptor
    h.rect(izq, y, der - izq, 50)
    documento = f"{DOCUMENTOS[doc_tipo]}: {doc_nro}" if doc_tipo in DOCUMENTOS else ""
    h.campo(izq + 12, y + 15, "CUIT/DNI:", documento)
    h.campo(izq + 170, y + 15, "Apellido y Nombre / Razón Social:", receptor[:44])
    h.campo(izq + 12, y + 30, "Condición frente al IVA:", "Consumidor Final" if doc_tipo != 80 else "")
    h.campo(izq + 12, y + 44, "Condición de venta:", condicion_venta)
    y += 58

    # Detalle
    columnas = [  # (título, x donde termina la columna, alineación)
        ("Código", izq + 48, "izquierda"),
        ("Producto / Servicio", izq + 278, "izquierda"),
        ("Cantidad", izq + 330, "derecha"),
        ("U. Medida", izq + 386, "centro"),
        ("Precio Unit.", izq + 436, "derecha"),
        ("% Bonif", izq + 476, "derecha"),
        ("Subtotal", der - 6, "derecha"),
    ]
    h.rect(izq, y, der - izq, 18, gris=0.85)
    inicio = izq + 6
    posiciones = []
    for titulo, fin, alinear in columnas:
        if alinear == "izquierda":
            xt = inicio
        elif alinear == "derecha":
            xt = fin
        else:
            xt = (inicio + fin) / 2
        posiciones.append((xt, alinear))
        h.texto(xt, y + 12.5, titulo, 8, negrita=True, alinear=alinear)
        inicio = fin + 6
    y += 32
    renglones = _partir(descripcion, columnas[1][1] - columnas[0][1] - 12, 8.5)
    valores = ["", renglones[0], "1,00", "unidades", _plata(monto), "0,00", _plata(monto)]
    for (xt, alinear), valor in zip(posiciones, valores):
        h.texto(xt, y, valor, 8.5, alinear=alinear)
    for extra in renglones[1:3]:
        y += 11
        h.texto(posiciones[1][0], y, extra, 8.5)

    # Totales
    y = 600
    h.rect(izq, y, der - izq, 62)
    for i, (etiqueta, valor, negrita) in enumerate([
        ("Subtotal: $", _plata(monto), False),
        ("Importe Otros Tributos: $", "0,00", False),
        ("Importe Total: $", _plata(monto), True),
    ]):
        fila = y + 18 + i * 17
        tamano = 10 if negrita else 9
        h.texto(der - 110, fila, etiqueta, tamano, negrita=True, alinear="derecha")
        h.texto(der - 10, fila, valor, tamano, negrita=negrita, alinear="derecha")

    # Pie: QR, autorización y CAE
    y = 676
    h.qr(izq, y, 88, _matriz_qr(url_qr(registro, cuit, pto_vta)))
    h.texto(izq + 104, y + 30, "Comprobante Autorizado", 11, negrita=True)
    h.texto(izq + 104, y + 44, "Verificable en ARCA escaneando el código QR.", 7.5)
    h.campo(der - 190, y + 30, "CAE N°:", str(registro["cae"]), tamano=9)
    h.campo(der - 190, y + 44, "Fecha de Vto. de CAE:", _fecha_corta(registro.get("vencimiento_cae")), tamano=9)
    h.texto(medio, 812, "Pág. 1/1", 7.5, alinear="centro")

    return h.pdf(titulo=f"Factura C {int(pto_vta):05d}-{numero:08d}")


def nombre_archivo(registro, pto_vta):
    fecha = _fecha_qr(registro.get("fecha_emision") or registro.get("fecha_transferencia"))
    return f"Factura C {int(pto_vta):05d}-{int(registro['numero']):08d} {fecha}.pdf"


def exportar(id_registro, por_defecto=None):
    """Genera el PDF de una factura del historial y devuelve dónde quedó guardado.

    Levanta FaltanDatosEmisor si todavía no se cargaron los datos del emisor."""
    import config

    registro = historial.cargar_historial().get(str(id_registro))
    if registro is None:
        raise ValueError("No se encontró esa factura en el historial.")
    if not registro.get("cae") or not registro.get("numero"):
        raise ValueError("Esa factura no tiene CAE guardado: no se puede armar el comprobante.")

    emisor = cargar_datos_emisor(por_defecto)
    if datos_faltantes(emisor):
        raise FaltanDatosEmisor()

    pto_vta = registro.get("pto_vta") or config.PTO_VTA
    contenido = generar_pdf(registro, emisor, config.CUIT, pto_vta)

    os.makedirs(CARPETA_COMPROBANTES, exist_ok=True)
    ruta = os.path.join(CARPETA_COMPROBANTES, nombre_archivo(registro, pto_vta))
    tmp = ruta + ".tmp"
    with open(tmp, "wb") as f:
        f.write(contenido)
    os.replace(tmp, ruta)
    return ruta


def abrir(ruta):
    """Abre el PDF con el visor que tenga configurado la computadora."""
    if sys.platform == "win32":
        os.startfile(ruta)  # noqa: S606 — es un archivo que acabamos de generar
    elif sys.platform == "darwin":
        subprocess.Popen(["open", ruta])
    else:
        subprocess.Popen(["xdg-open", ruta])
