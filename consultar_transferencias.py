import requests
import datetime
from config import MP_ACCESS_TOKEN

URL = "https://api.mercadopago.com/v1/payments/search"
HEADERS = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}
TIMEOUT = 30  # segundos por request; sin esto una caída de red cuelga la búsqueda

# Argentina no usa horario de verano: -03:00 todo el año. Usar este huso (y no
# la hora local de la PC) mantiene el rango de fechas correcto aunque la
# computadora esté configurada en otra zona horaria.
ZONA_AR = datetime.timezone(datetime.timedelta(hours=-3))

# Tipos de operación que consideramos "candidatos a transferencia recibida"
TIPOS_RELEVANTES = ["account_fund", "money_transfer"]


def obtener_transferencias(dias=30):
    """Trae transferencias recibidas candidatas en los últimos N días, paginando."""
    hoy = datetime.datetime.now(ZONA_AR)
    desde = hoy - datetime.timedelta(days=dias)

    begin_date = desde.strftime("%Y-%m-%dT00:00:00.000-03:00")
    end_date = hoy.strftime("%Y-%m-%dT23:59:59.999-03:00")

    resultados = []
    offset = 0
    limit = 50

    while True:
        params = {
            "sort": "date_created",
            "criteria": "desc",
            "range": "date_created",
            "begin_date": begin_date,
            "end_date": end_date,
            "limit": limit,
            "offset": offset
        }
        response = requests.get(URL, headers=HEADERS, params=params, timeout=TIMEOUT)
        if response.status_code == 401:
            raise RuntimeError(
                "Mercado Pago rechazó el Access Token (401). Revisá que el token "
                "de producción en config.py esté bien copiado y siga vigente."
            )
        response.raise_for_status()
        data = response.json()
        pagos = data.get("results", [])

        if not pagos:
            break

        resultados.extend(pagos)
        offset += limit

        if offset >= data.get("paging", {}).get("total", 0):
            break

    return resultados


def filtrar_candidatos(pagos):
    """Se queda solo con los movimientos que parecen transferencias recibidas reales."""
    candidatos = []

    for p in pagos:
        operacion = p.get("operation_type")
        metodo = p.get("payment_method_id")
        estado = p.get("status")

        # Solo nos interesan transferencias acreditadas (no pagos con tarjeta, ni movimientos internos)
        if operacion in TIPOS_RELEVANTES and estado == "approved":
            payer = p.get("payer") or {}
            nombre = f"{payer.get('first_name') or ''} {payer.get('last_name') or ''}".strip()
            if not nombre:
                nombre = payer.get("email", "Desconocido")

            candidatos.append({
                "id": p["id"],
                "fecha": p["date_created"][:10],
                "monto": p["transaction_amount"],
                "de": nombre,
                "metodo": metodo,
                "operacion": operacion
            })

    return candidatos


if __name__ == "__main__":
    pagos = obtener_transferencias(dias=30)
    candidatos = filtrar_candidatos(pagos)

    print(f"\nSe encontraron {len(candidatos)} transferencias candidatas:\n")
    for c in candidatos:
        print(f"[{c['fecha']}] ${c['monto']} — de: {c['de']} ({c['metodo']})")