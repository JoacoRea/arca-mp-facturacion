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
    if not os.path.exists(HISTORIAL_PATH):
        return {}
    with open(HISTORIAL_PATH, encoding="utf-8") as f:
        return json.load(f)


def ya_facturada(mp_id):
    return str(mp_id) in cargar_historial()


def registrar_factura(mp_id, transferencia, resultado):
    """Guarda que la transferencia `mp_id` ya se facturó. Llamar solo tras un resultado ok."""
    historial = cargar_historial()
    historial[str(mp_id)] = {
        "mp_id": mp_id,
        "fecha_transferencia": transferencia.get("fecha"),
        "fecha_emision": resultado.get("fecha_emision"),
        "monto": transferencia.get("monto"),
        "de": transferencia.get("de"),
        "cae": resultado.get("cae"),
        "numero": resultado.get("numero"),
        "pto_vta": resultado.get("pto_vta"),
        "vencimiento_cae": resultado.get("vencimiento_cae"),
    }
    with open(HISTORIAL_PATH, "w", encoding="utf-8") as f:
        json.dump(historial, f, indent=2, ensure_ascii=False)


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
