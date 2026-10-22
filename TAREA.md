# Tarea: guía de instalación con capturas reales

Sos una sesión de Claude con acceso a la PC con Windows de Joaquín (control de pantalla). El objetivo es instalar **Facturación ARCA** desde cero con los datos de Joaquín, sacar una captura de cada paso y dejar terminada la guía de instalación que él va a usar con clientes.

## Contexto

- **La app:** un `.exe` de Windows que busca los cobros de Mercado Pago y emite una Factura C por cada uno en ARCA. Guarda todo (configuración, certificado, historial, PDFs) en la misma carpeta del `.exe`.
- **La guía ya existe:** es un Claude Doc, https://claude.ai/artifact/TE9tY1yb5UBbDaZ4Z6niBE. Tiene todos los pasos escritos.
  - Las capturas de la app son simuladas, de un navegador con datos inventados.
  - Las capturas de ARCA y Mercado Pago faltan. Cada una está marcada como *"Captura pendiente: …"*.
- **Tu trabajo:** reemplazar esas capturas por capturas reales de Windows, y corregir cualquier paso que no coincida con lo que de verdad aparece en pantalla (nombres de menús, botones, orden).
- **El `.exe` a usar:** artefacto *FacturacionARCA* de la corrida https://github.com/JoacoRea/arca-mp-facturacion/actions/runs/39697398011. Si venció, usá el de la corrida verde más reciente del workflow "Armar .exe de Windows" en la rama `claude/leandro-galicia-billing-app-01rupo`.

## Reglas (no negociables)

1. **Credenciales:** la Clave Fiscal y la contraseña de Mercado Pago las escribe Joaquín, nunca vos. Cuando haya que iniciar sesión, pedíselo y esperá.
2. **Nunca toques "Facturar seleccionadas".** Emitiría una factura real a nombre de Joaquín, y la app no puede anularla.
3. **Access Token:** que no aparezca en ninguna captura que se guarde. Si una pantalla lo muestra, tapalo antes de guardar la imagen, o sacá la captura antes de pegarlo.
4. **No borres nada en ARCA:** ni certificados, ni relaciones, ni puntos de venta existentes. Solo se agrega.
5. **Clave privada:** no muevas, borres ni subas `MiClavePrivada.key` a ningún lado. No toques *Generar clave y solicitud* dos veces.
6. **CUIT:** puede quedar visible, porque la guía es para uso de Joaquín. El token y las contraseñas no.
7. **Ante cualquier duda que implique emitir, borrar o pagar algo,** pará y preguntale.

## Preparación

- Carpeta nueva y vacía: `Documentos\FacturacionGuia`. **No uses** `D:\meme\Descargas (D)\FacturacionARCA_2`, que ya tiene una configuración empezada.
- Carpeta para las capturas: `Documentos\FacturacionGuia\capturas`, con nombres numerados (`01_...png`, `02_...png`).
- **Datos de Joaquín:**
  - punto de venta Web Services: **3**;
  - alias del certificado: `facturacion-guia` (si ese alias ya existe en ARCA, usá `facturacion-guia2`).
  - CUIT y cuentas: los da él.

## Capturas a sacar

Cada captura tiene que estar recortada a la ventana o la parte relevante, y en el orden de la guía:

| # | Dónde | Qué mostrar |
|---|---|---|
| 01 | Explorador | El zip descargado y el `.exe` ya en `Documentos\FacturacionGuia` |
| 02 | Windows | Aviso de SmartScreen, con "Más información" visible |
| 03 | Windows | SmartScreen con el botón "Ejecutar de todas formas" |
| 04 | Explorador | Menú "Enviar a → Escritorio (crear acceso directo)" |
| 05 | App | Bienvenida del asistente |
| 06 | App | Datos de ARCA completos (CUIT, PV 3, alias) |
| 07 | App | "Generar uno nuevo" con las instrucciones después de generar |
| 08 | Explorador | La carpeta con `certificado.csr` y `MiClavePrivada.key` |
| 09 | ARCA | Puntos de venta, con el 3 de Web Services |
| 10 | ARCA | Administración de Certificados Digitales: pantalla inicial |
| 11 | ARCA | "Agregar alias" con el alias y el `.csr` elegidos |
| 12 | ARCA | Lista de certificados con el botón para descargar |
| 13 | ARCA | Administrador de Relaciones → Nueva relación |
| 14 | ARCA | Selección del servicio WebServices → Facturación Electrónica |
| 15 | ARCA | Selección del representante (el certificado por su alias) |
| 16 | ARCA | Lista de relaciones con Facturación Electrónica asociada |
| 17 | App | Certificado y clave con tilde |
| 18 | Mercado Pago | Developers → Tus integraciones / Crear aplicación |
| 19 | Mercado Pago | Credenciales de producción, **token tapado** |
| 20 | App | Paso de Mercado Pago (sacala antes de pegar el token o tapalo) |
| 21 | App | Resumen y "Configuración guardada" |
| 22 | App | Buscar transferencias con resultados (o vacío si no hay cobros) |
| 23 | App | Historial → Consultar desde ARCA, sin error |
| 24 | App | Formulario "Datos del comprobante" completo |
| 25 | App | Un PDF abierto, si hay alguna factura en el historial; si no, omitila |

Si ARCA o Mercado Pago piden un paso que no está en la guía (adherir un servicio, activar credenciales, aceptar términos), capturalo también y agregalo a la guía en el lugar que corresponde.

## Entregable

1. **Si tenés las herramientas de Claude Docs:** editá el doc existente, sin crear uno nuevo.
   - Subí las capturas como assets del doc.
   - Reemplazá cada *"Captura pendiente"* por la imagen real.
   - Cambiá las capturas simuladas de la app por las reales de Windows.
   - Corregí los textos de los pasos donde no coincidan con la pantalla.
   - No cambies las secciones que ya están bien.
2. **Si no las tenés:** armá `Documentos\FacturacionGuia\GUIA_INSTALACION.docx` con el mismo contenido del doc (leelo desde el link) y las capturas reales.
3. **Al final, avisale a Joaquín:**
   - qué pasos cambiaron respecto de la guía original;
   - cualquier error que haya dado la app, con el contenido de `facturacion_arca.log`;
   - si *Buscar transferencias* y *Consultar desde ARCA* funcionaron. Esa es la primera prueba real de la app en Windows, y el resultado importa tanto como la guía.
