# v0.52 · Refactor: menos código repetido

No cambia ninguna regla de negocio. Se cuidó que los mismos formularios conserven sus claves y sus mensajes. Las 486 pruebas que ya pasaban siguen pasando; la única que falla es `test_reset_origen`, que ya fallaba antes porque le falta el módulo `cotejo`.

**Respaldo del código previo:** `data/backups/codigo-antes-refactor-20261102-015014` (views, services, models, utils, tests, docs, app.py, db.py, README).

## Cómo se buscó la redundancia

El proyecto no tiene linters instalados, así que se usó un análisis estático propio (con `ast`) que buscó cuatro cosas:

- **Imports sin uso:** se revisó también si otro módulo o una prueba los alcanzaba a través del módulo antes de quitarlos.
- **Funciones nunca llamadas.**
- **Funciones idénticas.**
- **Funciones casi idénticas:** con similitud de tokens de 80 % o más.

## Qué se eliminó

- **Código muerto:**
  - `next_step_card` y `machine_strip` (views/components.py).
  - `_identity` (services/piece_stock.py).
  - `views/lamp_order.py`: un adaptador de compatibilidad que nadie importaba.
  - `services/cost_reference.py`: una siembra única de costos de referencia que ya no se ejecuta; los datos sembrados siguen en la base.
- **51 imports sin uso** en 30 módulos.

## Qué se unificó

| Antes | Ahora |
|---|---|
| 6 exportadores CSV, cada uno con su escritor; el CSV de producción no protegía contra fórmulas | `utils/csv_export.py`: un escritor con BOM y la misma protección en todas las exportaciones |
| `_get`, `_revision` y `_date` copiados en ventas, gastos y cotizaciones | `services/guards.py`: `fetch`, `same_revision` y `past_date`, con el mensaje propio de cada registro |
| `_encode` (JSON canónico) en conciliación y previsiones; `_table` en dos servicios | `guards.canonical` y `guards.has_table` |
| Pedido desde cotización y pedido desde venta: unas 40 líneas casi idénticas | `commerce.draft_order`, que recibe proyecto, nota y validación propios de cada documento |
| 5 ventanas de «anular o cancelar con motivo» (pagos de cotización y de venta, gastos, aportaciones) | `views/common.reason_form` |
| 2 formularios de pago recibido (cotización y venta) | `views/treasury_forms.received_payment_form` |
| `_key()` copiado en tres módulos de formularios | `views/common.request_key` |
| 15 veces `default=None if 'x' in st.session_state else …` | `views/common.remembered('x', …)` |
| `money` y `choose_front` duplicados | Una sola definición cada uno |

**Resultado:** views pasa de 9 323 a unas 9 240 líneas y services de 7 114 a unas 7 040, y hay dos módulos menos.

## Redundancia de interfaz

- La lista de **Impresoras** de la barra lateral ya no aparece en Hoy, Cola de producción ni Máquinas, porque esas páginas ya muestran cada impresora. Sigue en el resto de Taller.

## Qué se dejó igual a propósito

Algunas funciones comparten nombre en varios servicios (`_get`, `_text`, `save`, `history`, `normalize`…), pero leen tablas distintas o validan reglas distintas: son la API de cada servicio, no copias.

Las APIs de servicio que hoy solo usan las pruebas (por ejemplo `production.create_job` o `sheet_migration.import_snapshot`) se conservan, porque son operaciones válidas del dominio.
