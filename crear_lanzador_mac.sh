#!/bin/bash
# Crea "Facturar.app" en esta misma carpeta: un lanzador de doble clic, para que
# abrir la app no requiera pasar por la Terminal. Se corre una sola vez, después
# de instalar las dependencias.
#
# Es un applet de AppleScript compilado con osacompile, que ya viene en macOS.
# A propósito no se usa PyInstaller: no hay nada que compilar ni firmar, y al
# crearse en la propia computadora, Gatekeeper no lo bloquea.
set -e

carpeta="$(cd "$(dirname "$0")" && pwd)"
destino="$carpeta/Facturar.app"

if [ -x "$carpeta/.venv/bin/python" ]; then
    piton="$carpeta/.venv/bin/python"
else
    piton="$(command -v python3)"
    echo "Aviso: no se encontró el entorno virtual .venv, se usa $piton"
fi

# El ícono: se reempaqueta icon.ico como .icns. Las dos cosas guardan las
# imágenes como PNG adentro, así que alcanza con cambiar el envoltorio.
if [ ! -f "$carpeta/icon.icns" ] && [ -f "$carpeta/icon.ico" ]; then
    "$piton" - "$carpeta" <<'PYTHON' || echo "Aviso: no se pudo armar el ícono, el lanzador va a usar el genérico"
import pathlib, struct, sys

carpeta = pathlib.Path(sys.argv[1])
datos = (carpeta / "icon.ico").read_bytes()
PNG = b"\x89PNG\r\n\x1a\n"
TIPOS = {16: b"icp4", 32: b"icp5", 64: b"icp6", 128: b"ic07", 256: b"ic08", 512: b"ic09"}

bloques = b""
for i in range(struct.unpack("<H", datos[4:6])[0]):
    ancho, _, _, _, _, _, largo, salto = struct.unpack("<BBBBHHII", datos[6 + i * 16:22 + i * 16])
    ancho = ancho or 256
    imagen = datos[salto:salto + largo]
    if ancho in TIPOS and imagen[:8] == PNG:
        bloques += TIPOS[ancho] + struct.pack(">I", len(imagen) + 8) + imagen

if bloques:
    (carpeta / "icon.icns").write_bytes(b"icns" + struct.pack(">I", len(bloques) + 8) + bloques)
PYTHON
fi

rm -rf "$destino"
guion="$(mktemp -t lanzador)".applescript

cat > "$guion" <<APPLESCRIPT
set carpeta to "$carpeta"
set piton to "$piton"

-- Se lanza en segundo plano y a los pocos segundos se chequea que siga viva.
-- Si arrancó bien, este applet termina y deja la ventana abierta; si se cayó al
-- arrancar, se muestra el motivo en pantalla en vez de no pasar nada.
set orden to "cd " & quoted form of carpeta & " && nohup " & quoted form of piton & " gui_galicia.py > facturacion_lanzador.log 2>&1 & sleep 4; kill -0 \$! 2>/dev/null || { cat facturacion_lanzador.log >&2; exit 1; }"

try
    do shell script orden
on error mensaje
    display dialog "No se pudo abrir la app de facturacion." & return & return & mensaje buttons {"Cerrar"} default button 1 with icon stop
end try
APPLESCRIPT

osacompile -o "$destino" "$guion"
rm -f "$guion"

if [ -f "$carpeta/icon.icns" ]; then
    cp "$carpeta/icon.icns" "$destino/Contents/Resources/applet.icns"
    touch "$destino"
fi

echo
echo "Listo: $destino"
echo "Abrilo con doble clic, o arrastralo al Dock para que quede a mano."
