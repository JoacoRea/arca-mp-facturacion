"""Registro local de qué transferencias de MP ya se facturaron en ARCA.

Existe para evitar doble facturación: si la app se abre varias veces con
rangos de fecha que se superponen, la misma transferencia no vuelve a
quedar disponible para facturar una vez que ya se emitió su Factura C.
"""
import datetime
import json
import os

import rutas

HISTORIAL_PATH = rutas.ruta_datos("historial_facturas.json")


def cargar_historial():
    """Devuelve el historial como dict. Si el archivo está dañado, corta con un
    error claro en vez de devolver un historial vacío: un historial vacío haría
    que transferencias ya facturadas vuelvan a aparecer como pendientes."""
    if not os.path.exists(HISTORIAL_PATH):
        return {}
    try:
        with open(HISTORIAL_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise RuntimeError(
            f"El archivo {os.path.basename(HISTORIAL_PATH)} está dañado y no se puede leer. "
            "Restauralo desde un backup o renombralo para empezar de cero (ojo: sin historial, "
            "las transferencias ya facturadas vuelven a aparecer como pendientes)."
        ) from e


def ya_facturada(mp_id):
    return str(mp_id) in cargar_historial()


def registrar_factura(id_operacion, transferencia, resultado, extra=None):
    """Guarda que la transferencia `id_operacion` ya se facturó. Llamar solo tras un resultado ok.

    `id_operacion` es el ID del pago en Mercado Pago o, en la variante de Banco
    Galicia, el ID que arma extracto_galicia.py para esa fila del extracto.
    `extra` permite guardar datos propios de cada origen (concepto facturado,
    detalle escrito por el usuario, CUIT del titular) sin que este módulo tenga
    que conocerlos."""
    historial = cargar_historial()
    historial[str(id_operacion)] = {
        "id": str(id_operacion),
        # Se mantiene el nombre viejo del campo para no romper los historiales
        # ya guardados por versiones anteriores de la app.
        "mp_id": id_operacion,
        "fecha_transferencia": transferencia.get("fecha"),
        "fecha_emision": resultado.get("fecha_emision"),
        "monto": transferencia.get("monto"),
        "de": transferencia.get("de"),
        "cae": resultado.get("cae"),
        "numero": resultado.get("numero"),
        "pto_vta": resultado.get("pto_vta"),
        "vencimiento_cae": resultado.get("vencimiento_cae"),
        **(extra or {}),
    }
    # Escritura atómica (temporal + rename): si la app se corta a mitad de la
    # escritura, el historial anterior queda intacto en vez de corromperse.
    tmp_path = HISTORIAL_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(historial, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, HISTORIAL_PATH)


def _parsear_fecha(raw):
    """Acepta tanto YYYYMMDD (formato ARCA) como YYYY-MM-DD (formato MP)."""
    if not raw:
        return None
    raw = str(raw)
    if raw.isdigit() and len(raw) == 8:
        return datetime.datetime.strptime(raw, "%Y%m%d").date()
    try:
        return datetime.date.fromisoformat(raw[:10])
    except ValueError:
        return None


def listar_facturas(desde=None):
    """Devuelve las facturas registradas, más nuevas primero.

    `desde` es un datetime.date opcional; si se pasa, sólo se devuelven las
    facturas cuya fecha de emisión (o de transferencia, si la primera no
    está disponible) sea igual o posterior."""
    registros = list(cargar_historial().values())

    def fecha_de(registro):
        return (
            _parsear_fecha(registro.get("fecha_emision"))
            or _parsear_fecha(registro.get("fecha_transferencia"))
            or datetime.date.min
        )

    if desde is not None:
        registros = [r for r in registros if fecha_de(r) >= desde]

    registros.sort(key=fecha_de, reverse=True)
    return registros
