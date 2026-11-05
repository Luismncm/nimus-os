# v0.69 · Insumos y consumibles: una sola pantalla (1 de 2)

## Qué cambió

Insumos (cable, foco, empaque — componentes comprados de Colección Origen) y consumibles (filamento,
resina, pintura, tornillería) vivían en dos pantallas separadas, cada una con su propia tabla, su
propio buscador y su propio editor de mínimos: "Filamento y consumibles" en Inventario, y
"Insumos y reposición" dentro de Colección Origen → Inventario. Para gestionar cantidades y costos
había que aprender y revisar dos sistemas aunque la pregunta fuera la misma: "¿qué me está por
faltar?".

Ahora ambos viven en **Inventario → Insumos y consumibles**, una sola pantalla:

- Una tabla combinada (nombre, variante, categoría, disponible, comprometido, mínimo, en pedido),
  con un filtro de tipo (Todos / Consumible / Insumo) y un buscador de texto.
- Un solo panel de detalle: al elegir una fila se abren las mismas acciones de siempre
  (Registrar consumo, Contar/pesar, Pedir… para un consumible; Pedir reposición, Registrar entrada
  física… para un insumo) — nada de eso cambió, solo dónde se llega a ellas.
- El aviso de "filamentos de la cola sin registrar" con sus botones de alta rápida sigue ahí.
- Dos expandibles ("Desglose de consumibles" y "Desglose de insumos") conservan las columnas más
  finas que tenían las pantallas anteriores (equivale a, valor en existencia, físico, reservado,
  sin cubrir, reposición sugerida) para quien las necesite, sin saturar la vista principal.
- El editor de mínimos por lote de insumos (la cuadrícula para capturar varios mínimos de una vez)
  sigue disponible, ahora dentro de la misma pantalla.

Insumos y consumibles siguen siendo **dos cosas distintas por dentro** — un insumo es una pieza
del catálogo con reservas por pedido; un consumible se cuenta por peso o volumen con su propio
envase — y eso no cambia: fusionarlos en una sola tabla de base de datos habría significado
reescribir las reservas o el conteo por peso sin necesidad real. Lo que se unificó es la pantalla:
un solo lugar para mirar, buscar y actuar.

Todo lo que antes abría la pantalla de insumos (la campana de notificaciones, los avisos de la
barra lateral, el botón "Mínimos y reposición" de Colección Origen, el registro de una entrada
física de un insumo nuevo) ahora abre esta misma pantalla unificada.

## Qué es la parte 2 (pendiente, no incluida aquí)

El usuario pidió además que el inventario de Colección Origen (sus piezas y "Bases por color") se
integre a las mismas pantallas del Inventario general, en vez de tener su propia pestaña aparte.
Eso es un cambio independiente y de tamaño similar a este — toca `views/origin_ui.py`,
`views/collection.py` (el filtro `is_origin` de Existencias) y varios puntos de navegación
(`open_origin_inventory`, `views/base_inventory_ui.py`, `views/catalog_forms.py`,
`views/origin_cart.py`, `views/control.py`) — y se deja para una siguiente sesión, con el mismo
cuidado de pruebas y verificación que esta.

## Cómo se implementó

- `services/supplies.py` (nuevo): junta `services.consumables.items()` y `services.restock.rows()`
  en una sola lista, cada fila marcada con su `kind` y con textos ya formateados para la tabla.
  No cambia ni toca el esquema de la base de datos.
- `views/supplies_ui.py` (nuevo): la pantalla unificada. Su panel de detalle no duplica lógica:
  llama a `consumables_ui.item_panel(row)` o `restock_ui.item_panel(row)` según el tipo — ambas
  funciones se extrajeron de las pantallas anteriores, que ahora están retiradas (nada navega ya
  a sus antiguas `panel()` de nivel superior).
- `views/collection.py`: la pestaña "Filamento y consumibles" pasa a "Insumos y consumibles"; los
  nombres antiguos de sesión se traducen (`old_tabs`) para quien tenía la pestaña anterior
  recordada en su sesión.
- `views/restock_ui.py::open_restock()`, `views/supply_ui.py::open_inventory()`,
  `views/origin_forms.py::receipt_form()`: todos los puntos que antes abrían la pantalla de
  Colección Origen para insumos ahora abren la pantalla unificada en Inventario.

## Verificación

- Suite completa: 549/550 — el único que no pasa (`test_reset_origen`) ya fallaba antes de este
  cambio, por un módulo externo (`cotejo`) ajeno al proyecto.
- `scripts/test_postgres.py` sobre los 10 módulos de prueba que tocan esta área
  (`test_restock`, `test_consumables`, `test_sidebar_attention`, `test_notifications`,
  `test_origin`, `test_base_inventory`, `test_inventory_ui`, `test_inventory_presentation`,
  `test_found_stock`, `test_inbound`): 84/84 — este cambio no toca el esquema, así que el riesgo en
  Postgres era bajo, pero se verificó igual.
- Verificado en el navegador, contra una copia de la base real (nunca la base real en sí): la tabla
  combinada carga consumibles e insumos reales juntos, el filtro de tipo y el buscador funcionan,
  el panel de detalle de un consumible y de un insumo abren sus acciones de siempre, los dos
  expandibles de desglose y el editor de mínimos por lote se despliegan sin error, y el botón
  "Pedir reposición" de un insumo abre el mismo diálogo "Agregar inventario" de antes.
