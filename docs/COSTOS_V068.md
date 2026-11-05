# v0.68 · Costos de impresión: obligatorio, tarifa por máquina y lectura de G-code

## Qué cambió

Tres pendientes de la sección de Costos, todos en el mismo formulario de asignar/capturar una impresión (`views/print_setup.py`):

1. **Sin gramos no hay impresión.** El botón para guardar queda deshabilitado mientras el campo **Filamento · g** esté en cero. Ya no se puede crear un trabajo de impresión sin su costo de filamento — el candado que faltaba después de v0.53, que ya dejaba el costo capturado como el costo real sin pedirlo dos veces, pero no impedía dejarlo vacío.
2. **Tarifa de máquina por impresora.** Cada máquina (Máquinas → editar) tiene ahora una **Tarifa · MXN/h** (energía y desgaste). Al elegir esa impresora en el formulario, el campo **Máquina · MXN/h** se llena solo con su tarifa — ya no hay que recordarla o escribirla cada vez. En 0 o vacío, la impresión sigue costeando solo su filamento.
3. **Subir G-code para no capturar a mano.** Un cargador opcional (**Subir G-code**) lee el tiempo y el peso de filamento que el slicer ya calculó — Bambu Studio, OrcaSlicer, PrusaSlicer y Cura — y llena Duración y Filamento · g automáticamente. Si el archivo no trae esos datos, avisa y se capturan a mano como antes.

Ningún cambio toca el precio del filamento por kg: ya se gestiona en **Filamento y consumibles** (precio del carrete registrado) y el formulario lo usa como antes, con 380 MXN/kg de respaldo si el material no está registrado.

De paso, en **Costos y utilidad → Recetas y costos**, el encabezado "Costo estimado por producto" pasa a **"Costo de referencia por producto"** con una nota aclarando que es para cotizar, no una segunda captura del costo real de una impresión — ese ya se resuelve una sola vez al asignarla (v0.53).

## Cómo se implementó

- `services/gcode.py` (nuevo): lee el encabezado/pie de un `.gcode` con expresiones regulares — tiempo (horas/minutos/segundos o solo segundos) y gramos de filamento (suma los de impresiones multicolor). Puro texto, sin dependencias nuevas.
- `machines.hourly_rate_cents` (columna nueva, migración v34→v35 en `db.py`): tarifa opcional por máquina, en centavos. La migración queda protegida con `PRAGMA table_info` antes del `ALTER TABLE`, igual que las demás columnas añadidas a una tabla existente en el proyecto (`models/consumable_schema.py`) — sin eso, una base ya migrada volvía a fallar con «duplicate column name» en la segunda llamada a `init_db()`, algo que la propia suite ya vigila (`test_additive_migration_preserves_every_existing_record`).
- `views/print_setup.py::print_setup`: el selector de impresora se mueve antes de los campos de costo para que la tarifa de la máquina elegida pueda rellenar el campo; el botón Guardar de los tres formularios que usan este bloque (`assign_panel.py`, `capture_forms.py` ×2) se deshabilita cuando el proceso es de impresión y no hay gramos capturados.

## Verificación

- Pruebas nuevas: `tests/test_gcode.py` (7, parseo de cada formato de slicer), más 2 en `tests/test_print_cost_once.py` (bloqueo sin gramos + tarifa de máquina precargada; subida de G-code llena los campos).
- Suite completa: 549/550 — el único que no pasa (`test_reset_origen`) ya fallaba antes de este cambio, por un módulo externo (`cotejo`) ajeno al proyecto.
- `scripts/test_postgres.py` sobre `test_print_cost_once`, `test_visual_operations`, `test_assign_panel` y `test_machine_panel`: todo verde: la columna nueva y la migración funcionan igual en Postgres.
- Verificado en el navegador, contra una copia de la base real (nunca la base real en sí): el botón de guardar queda apagado con el filamento en 0, se activa al capturar gramos, y la línea de costo se actualiza en vivo.
