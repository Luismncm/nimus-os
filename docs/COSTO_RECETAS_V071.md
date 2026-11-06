# v0.71 · Costo de receta desde G-code y recetas TAP BAR NFC

## Qué cambió

### G-code también en el costo de una pieza del catálogo

En **Costos y utilidad → Recetas y costos → Editar costo de pieza** (y en cualquier otro lugar que abre el mismo diálogo «Costo de pieza»: Catálogo, Inventario, Colección Origen), cuando el cálculo es **Impresión por parámetros** hay un cargador **Subir G-code · opcional**, igual que al asignar una impresión (v0.68):

- Lee el tiempo y el peso de filamento que el slicer ya calculó (Bambu Studio, OrcaSlicer, PrusaSlicer, Cura) y llena **Gramos**, **Tiempo · horas** y **Tiempo · minutos**.
- Respeta «Por pieza» / «Por lote»: con «Por lote», los gramos del G-code son los de la placa completa y se reparten entre las piezas producidas.
- La **Fuente o motivo** queda como `G-code: <archivo>`, así el historial de versiones del costo dice de dónde salió.
- Si el archivo no trae esos datos, avisa y se capturan a mano. Un archivo nuevo llena los campos una sola vez: una corrección manual posterior no se pisa.

### Mismos precios y nombres que una impresión real

Antes, el costo de referencia de una pieza pedía **Precio por gramo · MXN/g** y **Tarifa de tiempo · MXN/h**, mientras que una impresión en la cola pide **Filamento · MXN/kg** y **Máquina · MXN/h**. Ahora el diálogo usa los mismos dos campos y la misma fórmula escrita (`gramos × MXN/kg ÷ 1,000 + horas × MXN/h`).

Si la pieza aún no tiene precio de filamento guardado, el campo arranca con el **mismo precio que usaría una impresión**: el del carrete registrado en Insumos y consumibles para ese material, o el promedio de 380 MXN/kg. Así el costo de referencia de una receta y el costo real de imprimirla parten del mismo número. Los costos ya guardados no cambian: se muestran convertidos a MXN/kg (0.44 MXN/g → 440 MXN/kg) con el mismo importe.

### Recetas TAP BAR NFC 2, 3 y 4 (datos, ya aplicados)

Una TAP BAR de N taps lleva N CHIPS NFC impresos. En el catálogo quedaron:

| Producto | Receta |
|---|---|
| TAP BAR NFC 2 (PRO-0011) | 1 × TAP BAR 2 (CMP-0019, nueva) + 2 × CHIPS NFC (CMP-0018) |
| TAP BAR NFC 3 (PRO-0006) | 1 × TAP BAR 3 (CMP-0017) + 3 × CHIPS NFC — versión 2; la versión 1 tenía solo 1 CHIPS NFC |
| TAP BAR NFC 4 (PRO-0012) | 1 × TAP BAR 4 (CMP-0020, nueva) + 4 × CHIPS NFC |

Se registraron con las funciones normales del catálogo (nueva versión de receta, sin editar la anterior): los pedidos y ventas que ya usaban la versión 1 de TAP BAR NFC 3 se conservan. TAP BAR 2, TAP BAR 4 y CHIPS NFC todavía no tienen costo de pieza: súbeles su G-code desde «Editar costo de pieza» para completar el costo de las tres recetas.

## Cómo se implementó

- `views/costing_forms.py`: `gcode_fill()` usa `services/gcode.py` (el mismo lector de v0.68). Va **fuera** del formulario del diálogo, porque un `st.form` solo se vuelve a ejecutar al enviarlo; escribe en las mismas claves de sesión que usan los campos de abajo, y esos campos solo reciben `value=` la primera vez (`_seed`), para no chocar con los valores que puso el G-code.
- El precio por kg se convierte a MXN/g antes de `costing.printing_inputs`, así que el formato guardado (centavos por kg) y todos los costos existentes quedan igual.

## Verificación

- `tests/test_print_cost.py`: dos pruebas nuevas (el G-code llena gramos, horas, minutos y la fuente, y el precio arranca en 380 MXN/kg; un archivo sin datos avisa y no llena nada) y las existentes actualizadas a MXN/kg con los mismos importes.
- Suite completa: 550/551 — el único que no pasa es `test_reset_origen`, ajeno a este cambio (módulo `cotejo`).
- `scripts/test_postgres.py tests.test_print_cost`: 13/13.
- Navegador, contra una copia de la base real: TAP BAR NFC 4 aparece con sus dos líneas; en «Editar costo de pieza» de CHIPS NFC, subir un G-code llenó 12.4 g, 0 h 42 min y 380 MXN/kg, sin avisos de Streamlit.
