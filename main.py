"""Flujo manual: traer transferencias de MP, elegir cuáles son turnos, y facturarlas en ARCA.

Por ahora es por consola (la interfaz gráfica vive en gui.py/gui.html).
La decisión de qué facturar siempre la toma la persona, a propósito.
"""
import registro
import consultar_transferencias as mp
import facturar
import historial

registro.configurar()


def marcar_ya_facturadas(candidatos):
    hist = historial.cargar_historial()
    for c in candidatos:
        c["ya_facturada"] = str(c["id"]) in hist
    return candidatos


def elegir_transferencias(candidatos):
    print(f"\nSe encontraron {len(candidatos)} transferencias candidatas:\n")
    for i, c in enumerate(candidatos, start=1):
        marca = " [YA FACTURADA]" if c["ya_facturada"] else ""
        print(f"  {i}. [{c['fecha']}] ${c['monto']} — de: {c['de']} ({c['metodo']}){marca}")

    seleccion = input("\nIngresá los números a facturar separados por coma (o 'todos'), Enter para cancelar: ").strip()
    if not seleccion:
        return []
    if seleccion.lower() == "todos":
        return [c for c in candidatos if not c["ya_facturada"]]

    indices = [int(x) for x in seleccion.split(",") if x.strip().isdigit()]
    return [candidatos[i - 1] for i in indices if 1 <= i <= len(candidatos)]


def facturar_seleccionadas(seleccionadas):
    print("\nFacturando...\n")
    for t in seleccionadas:
        print(f"-> ${t['monto']} de {t['de']} ({t['fecha']})... ", end="", flush=True)

        if t["ya_facturada"]:
            print("YA FACTURADA, se omite")
            continue

        try:
            resultado = facturar.emitir_factura_c(importe=t["monto"])
        except Exception as e:
            print(f"ERROR inesperado: {e}")
            continue

        if resultado["ok"]:
            historial.registrar_factura(t["id"], t, resultado)
            print(f"OK — CAE {resultado['cae']} (Comprobante {resultado['numero']}, vence {resultado['vencimiento_cae']})")
        else:
            print(f"RECHAZADA — {resultado['error']}")


def main():
    dias_input = input("¿Cuántos días para atrás buscar transferencias? [7]: ").strip()
    dias = int(dias_input) if dias_input.isdigit() else 7

    print(f"\nConsultando transferencias de los últimos {dias} días en Mercado Pago...")
    pagos = mp.obtener_transferencias(dias=dias)
    candidatos = marcar_ya_facturadas(mp.filtrar_candidatos(pagos))

    if not candidatos:
        print("No se encontraron transferencias candidatas en ese rango.")
        return

    seleccionadas = elegir_transferencias(candidatos)
    if not seleccionadas:
        print("No se seleccionó ninguna transferencia. Cancelado.")
        return

    facturar_seleccionadas(seleccionadas)


if __name__ == "__main__":
    main()
