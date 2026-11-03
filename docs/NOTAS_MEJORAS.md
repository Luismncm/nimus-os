# Notas de mejora · NIMUS OS

Lista de trabajo para próximas versiones. Cada nota dice qué se observa hoy, por qué estorba y qué se propone.
Prioridad: **P1** = afecta el uso diario · **P2** = mejora clara · **P3** = pulido.

---

## Hecho · 21/10/2026 · Shell y navegación

- Barra lateral con orden fijo: Notificaciones arriba, buscador, área, páginas y Herramientas.
- El encabezado de cada página usa el mismo nombre que la barra lateral; ruta Área / Grupo / Página.
- Herramientas como desplegable legible (el popover mostraba texto oscuro sobre fondo oscuro).
- Las notificaciones reutilizan los datos de la página en vez de leer la base dos veces; los CSV se generan al descargar.

## Hecho · 21/10/2026 · Pedidos P1 (notas 1–4)

- **Avance único:** `breakdown()` en `services/order_progress.py` cuenta Terminadas · En curso · En cola · Sin asignar (siempre suman las requeridas). Barra apilada en `views/progress_ui.py`, usada por el detalle, las tarjetas de pedido y Hoy.
- **Una tabla de piezas por producto** con Requeridas / De inventario (recetas) · Por fabricar · Terminadas · En curso · En cola · Sin asignar · Avance.
- **Encabezado:** una tarjeta, paso a paso de etapas, 3 métricas (Por fabricar, Sin asignar, Insumos por reservar) y siguiente paso con su botón. Las acciones secundarias están en "Más acciones".
- **Productos:** título con terminadas y avisos en color, orden por lo que requiere acción y filtro Por asignar · En producción · Completos.
- **Reparto múltiple:** "Repartir piezas" (siguiente paso) y "Repartir pendientes del producto" abren una tabla de piezas × máquinas; se guarda todo o nada (`create_order_jobs`). La distribución automática deja cada pieza completa en la máquina disponible con menos carga.
- Cada pieza tiene un solo botón "Asignar N"; "Crear un trabajo con fecha y notas" queda en Opciones de pieza.
- Sin cambiar: el check de revisión del producto sigue siendo manual (nota 6) y "Trabajos asociados" sigue como desplegable (nota 5).

## Hecho · 21/10/2026 · Cola de producción y Agenda de impresión

- **Modelo de tiempo único** (`services/timeline.py`): cada trabajo activo está En marcha, Sin fin (en marcha sin fin vigente: bloquea la máquina), Reservada (inicio + duración), Sin duración (no reserva) o Sin horario. Cada máquina responde "Libre ahora · hasta…", "Ocupada hasta… · luego libre" o "Bloqueada".
- **Cola:** filtros en una línea, resumen con trabajos sin horario y con problema de horario, franja de 24 h por máquina, horario de cada lote en una línea ("hoy 17:27 → mañana 03:26 · 10 h · faltan 10 h") y problemas explicados en rojo. Se retiró la tabla compacta repetida (sigue la vista Tabla, ahora con columna Horario).
- **Agenda:** periodos de un clic (Hoy, 3, 7, 14 días o personalizado), métricas con horas, bloque "Requiere atención" con botón Corregir horario, todas las máquinas en el calendario con línea de "ahora" y borde rojo en cruces o vencidos, y lista dividida en Por programar y Con horario.
- **Programar:** la ventana muestra la ocupación de la máquina y ofrece el primer horario libre que cabe con la duración, empezando en el siguiente cuarto de hora a 5 min o más. Texto claro de cómo se calcula el fin y qué pasa al iniciar y pausar.

## Hecho · 21/10/2026 · Filamento, consumibles y estado de pedidos

- **Consumibles por unidad** (Inventario → Filamento y consumibles): filamento, resina, pintura, adhesivo, tornillería, limpieza, empaque u otro. Cada uno se controla en g, ml o piezas; se captura también en kg o L. Envase configurable (carrete 1 kg, botella 1 L, bolsa 100 pzas).
- **Saldo por historial inalterable**: entrada sin pedido, consumo (opcionalmente ligado a un trabajo), conteo o pesaje que deja la diferencia como ajuste. El saldo no puede quedar negativo.
- **Filamento contra la cola**: compara el saldo con los gramos estimados de los trabajos abiertos ("No alcanza para la cola", "Bajo mínimo") y avisa de filamentos usados en piezas que aún no están registrados. Mantiene al día la lectura que usan los avisos de Control; el formulario "Material disponible" de Control registra un conteo en el mismo historial.
- **Pedidos de consumibles** por envases (CON-0001), con gasto opcional en Gastos, recepción parcial y cancelación (si no llegó nada ni se pagó, también se cancela el gasto).
- **Un solo flujo de estado** para pedidos de piezas/insumos y de consumibles: Solicitado → Confirmado → En camino → Recibido parcial → Recibido, o Cancelado. Resumen de estados y llegadas vencidas en Inventario → Pedidos.
- Migración a esquema 27 con respaldo `pre-consumibles-v27`; las lecturas de material anteriores pasan a ser saldo inicial.
- **Siguiente paso previsto (no hecho):** rastreo por carrete/envase con código o QR. Se agrega una tabla `consumable_packages` y un `package_id` opcional en los movimientos; los saldos actuales no cambian.

## Hecho · 21/10/2026 · Costo de consumibles y vínculo con pedidos

- **Costo de referencia por envase** (sin IVA) en cada consumible; se actualiza con el precio pagado al recibir un pedido con gasto. Se muestran costo por kg/L/pza y valor en existencia.
- **Cada consumo guarda su costo** en el momento (cambios de precio posteriores no lo reescriben) y puede ligarse a un **pedido** o a un **trabajo de impresión**.
- **Costos y margen del pedido** suma los consumibles usados en él. El filamento ligado a un lote se lista pero no se suma otra vez, porque ya entra por el costo real del lote; consumos sin costo dejan el margen provisional.
- Desde el pedido: **Más acciones → Registrar consumible usado**. En Control → Costos y margen, sección **Consumibles del pedido**. En **Costo real** del lote se sugiere el costo de referencia del filamento en MXN/kg.
- Migración a esquema 28 con respaldo `pre-costos-consumibles-v28`.

## Hecho · 21/10/2026 · Hoy con abastecimiento y un solo formulario de compras

- **Hoy:** métrica **Por abastecer**, chips de conteo en lugar del texto largo, nueva área **Abastecer** (Por pedir · Por recibir · Todo) y tarjeta **Insumos y materiales** en el resumen. Capacidad con la misma frase de disponibilidad que la Cola y la Agenda.
- **Abastecer** reúne insumos por pieza en negativo o mínimo, consumibles bajo mínimo o que no alcanzan para la cola y pedidos de compra abiertos. Lo ya cubierto por un pedido abierto se marca como cubierto en vez de pedirse otra vez.
- **Un solo "Agregar inventario"** para piezas/insumos y filamento/consumibles: misma elección Entrada física / Pedido, mismos datos de proveedor, llegada, gasto de la compra (total obligatorio), fechas y notas. Se abre igual desde Inventario, Pedidos, Reposición, Filamento y consumibles y Hoy.

## Hecho · 23/10/2026 · Desarrollo y prototipos

- **Proyectos de desarrollo** (Taller → Desarrollo y prototipos): objetivo, presupuesto opcional, activo o cerrado. Internamente son un pedido marcado como desarrollo, así reutilizan cola, agenda, reservas, filamento contra la cola, costo real y consumibles.
- **Lanzar impresión de prototipo** en un paso (pieza, unidades, material, máquina, duración, gramos, horario, tarifa de máquina opcional), todo en una transacción. Muestra existencia del filamento, disponibilidad de la máquina y primer horario libre. El costo de referencia del filamento valora la estimación. También desde Hoy → Imprimir prototipo.
- **No son ventas:** sin ingreso ni margen (Costos muestra "Costo de desarrollo" contra el presupuesto), fuera del tablero de pedidos, de entregas y preparación en Hoy y de las notificaciones de pedidos. Sí cuentan en piezas por asignar, en la cola y en el filamento previsto.
- **En la cola y la agenda:** insignia "Prototipo" y filtro Tipo de trabajo (Todos / Pedidos / Prototipos).
- Cerrar un proyecto requiere sus impresiones terminadas; se puede reabrir. Migración a esquema 29 con respaldo `pre-desarrollo-v29`.

## Hecho · 27/10/2026 · Cola para el día a día

- **Nueva impresión** (Cola y Hoy): primero ¿para qué es? (Pedido o stock / Prototipo); luego pedido o proyecto, pieza existente por asignar o pieza nueva, y los mismos datos de máquina, duración, gramos, tarifa y horario con primer horario libre. Todo en una transacción (`services/capture.py`).
- **Vista Operar** (predeterminada): una línea por impresión agrupada por máquina, con su destino (Pedido · cliente · venta, Stock o Prototipo · proyecto), horario, avance y acciones en la misma línea.
- **Por resolver**: inicios vencidos y cruces con **Pasar al primer horario libre** en un clic (misma duración), sin duración → Capturar duración, impresión sin máquina → Asignar máquina, en marcha sin fin → Avance o terminar.
- Filtro **Para qué es**: Pedidos / Stock / Prototipos. La insignia de destino también aparece en Por máquina y Lista de trabajos.

## Hecho · 27/10/2026 · Producción del pedido sin desplegables

- **Piezas / Impresiones** dentro de la pestaña Producción del pedido.
- **Piezas:** productos elegidos como pestañas (Todos + cada producto con terminadas y sin asignar) y mostrados abiertos; cada pieza lleva debajo sus trabajos en línea (máquina, unidades, estado, horario, aviso y acciones). Ya no hay desplegables por producto ni por "trabajos".
- **Impresiones:** la cola propia del pedido agrupada por máquina con las mismas líneas de Operar, Nueva impresión para el pedido, Repartir pendientes y Registrar impresión terminada. Sustituye el selector "Iniciar, pausar o terminar producción".
- Al repartir una pieza, cada máquina muestra su disponibilidad ("Libre ahora", "Ocupada hasta…").

## Hecho · 27/10/2026 · Bloque de producción sintetizado

- **Se retiró "Agenda de impresión".** Su calendario es ahora la vista **Calendario** de la Cola (periodos Hoy / 3 / 7 / 14 días, todas las máquinas, línea de ahora, cruces en rojo). "Requiere atención" ya estaba en Por resolver y la lista de próximas en Operar; gramos, costo previsto y CSV pasaron a la vista **Tabla**.
- **Cola con 3 vistas:** Operar (por máquina con su franja de 24 h, opción de mostrar máquinas libres), Calendario y Tabla. Cada línea de Operar tiene **Horario** para programar sin salir de la cola.
- **Menú lateral:** Trabajo diario (Hoy, Pedidos) y **Producción** (Cola de producción, Desarrollo y prototipos, Control de producción).
- **Colores por tipo** en tarjetas (`views/kind_style.py`): pedidos con barra verde, stock azul, **prototipos violeta con fondo tintado**; también en la franja de 24 h, el calendario, las líneas de trabajo del pedido y las tarjetas de proyectos.

## Hecho · 27/10/2026 · Etiquetas, asignación inteligente y piso en vivo

Basado en el análisis de software de granjas ([ANALISIS_SOFTWARE_GRANJAS.md](ANALISIS_SOFTWARE_GRANJAS.md)).

- **Etiquetas únicas** (`views/tags.py`): impresora (color por estado y filamento cargado), venta (verde), pedido · cliente (gris), stock (azul), prototipo (violeta), prioridad alta y "Cambiar filamento" cuando la impresora tiene otro material.
- **Filamento cargado por impresora** (esquema 30, `machine_loadout`): se registra desde cada tarjeta del piso.
- **Asignación sugerida** (`services/assign_suggest.py`): primero la impresora con el material cargado; si otra queda libre más de 1 h antes, gana esa (cambiar carrete cuesta menos que esperar). Se usa en Nueva impresión (máquina preseleccionada con su motivo), en Asignar N ("Asignar todo a…") y en Repartir pendientes.
- **Piso en vivo** en Operar: una tarjeta por impresora con lo que imprime, para quién, avance estimado, hora de término y tiempo restante, o "Libre" con el siguiente trabajo; borde azul imprimiendo, verde libre, naranja atención. Se actualiza cada 30 s.
- **Agrupar por** Máquina, Estado o Para qué es.
- Pendiente: conexión directa con las impresoras (Bambu Lab por red local) para avance real en lugar de estimado.

## Hecho · 27/10/2026 · Excedente a inventario y revisión antes de imprimir

- **Unidades extra para inventario** (esquema 31, `job_extras`): al asignar (Asignar N, Nueva impresión, Editar trabajo) se puede imprimir más de lo que pide el pedido. El trabajo conserva las unidades del pedido (el avance y los límites no cambian) y el excedente entra a Colección en Inventario al terminar la impresión; si el trabajo se reabre, se retira. Etiqueta azul "+N a inventario" en la pieza y en la Cola. Los prototipos no mandan excedente a inventario.
- **Revisión de inventario antes de imprimir** (`services/piece_stock.py`): cada pieza por asignar muestra cuántas iguales hay libres (Stock + Colección, sin contar reservas). En Asignar N y Nueva impresión aparece el aviso "Ya hay N en inventario… para no duplicar".
- **Tomar de inventario** en piezas de catálogo/receta: reserva esas unidades para el pedido y baja lo que falta por imprimir (cuenta como "de inventario" en el avance).
- Pendiente: tomar de inventario en piezas de pedidos personalizados (hoy solo se informa cuántas hay); el costo de material del excedente queda en el pedido que lo imprimió.

## Hecho · 27/10/2026 · Panel de asignación

- **Vista Asignar** en la Cola de producción (todas las piezas pendientes, respeta los filtros de pedido, proceso, búsqueda y "Para qué es") y en la pestaña Producción de cada pedido (`views/assign_panel.py`). El conteo de unidades por asignar va en la pestaña.
- **Izquierda:** piezas por asignar, primero pedidos de prioridad alta y entrega más próxima; filtro por material; cada una con producto, material, pedido, entrega y "N en inventario". Lista con desplazamiento propio cuando son muchas.
- **Derecha:** la pieza elegida con su inventario, unidades, duración, gramos, excedente a inventario, filamento disponible y **tarjetas de impresora** ordenadas por la sugerencia (filamento cargado y primer horario libre): estado, filamento cargado o cambio, cuándo queda libre y unidades en cola. Después el **horario** (primer libre con inicio → fin, sin horario u otra fecha) y un botón que resume el trabajo ("Crear trabajo · 3 + 2 en P2 · hoy 13:00").
- **Dividir entre impresoras:** si se crean menos unidades que las pendientes, la pieza sigue elegida con el resto para mandarlo a otra impresora; al completarla pasa a la siguiente.
- La ventana **Asignar N** de cada pieza usa el mismo flujo ("Una impresora") y conserva el reparto por cantidades en "Repartir en varias".

## Hecho · 27/10/2026 · Cola por máquina con el estilo del panel de asignación

- En **Operar → Agrupar por Máquina** (`views/machine_panel.py`): a la izquierda cada impresora es una tarjeta en vivo (cada 30 s) con lo que imprime, avance estimado, hora de término, impresiones en cola, horas reservadas y problemas; borde de color por estado. Arriba "Todas" y, si hay, "Sin máquina".
- **Todas** muestra el piso completo como antes (franja de 24 h y cola de cada impresora).
- **Una impresora** muestra su franja, el filamento cargado (editable), lo que imprime **Ahora**, su **cola** con acciones y **Para asignar aquí**: piezas pendientes con su filamento cargado primero; "Asignar" abre la pieza con esa impresora ya elegida.
- El filtro Máquina de la Cola enfoca esa impresora. Agrupar por Estado o Para qué es conserva el piso en vivo y las listas.

## Hecho · 27/10/2026 · Excedente en camino: usarlo antes de imprimir de más

- **En camino** (esquema 32): el "+N a inventario" de impresiones que no han terminado cuenta como inventario por llegar. Cada pieza igual (mismo componente, o mismo modelo, pieza, material y proceso) muestra "N en camino" en el pedido, en Asignar y en la ventana de la pieza; Inventario tiene el indicador **En camino** y la lista de excedentes por impresión.
- **Sumar a esa impresión** (`ride_print`): la pieza de otro pedido se imprime dentro del excedente de esa impresión. Recibe un trabajo en la misma impresora que no se inicia por separado y se termina solo cuando termina la impresión; el excedente baja en esas unidades y solo lo que nadie tomó entra a inventario. Etiquetas "En la impresión JOB-x" y "Lleva 2 de ORD-y". **Separar** lo deshace.
- **Tomar de inventario** según la pieza (`use_stock`): las de catálogo se reservan para el pedido como antes; las de pedidos personalizados ahora también, con confirmación: quedan como un trabajo terminado "De inventario" y las unidades salen de inventario para que nadie más las cuente.

---

## Pendiente · Pedidos: productos, piezas y trabajos

Objetivo: que al abrir un pedido se entienda en segundos **qué falta, de qué producto, de qué pieza y qué trabajo hay que hacer**, con una sola forma de medir el avance.

Observado en ORD-0007 (3 productos, 24 piezas, insumos pendientes) con una copia de la base.

### 1. Un solo lenguaje de avance (P1)

**Hoy:** el mismo avance aparece con nombres y números distintos:
- Encabezado: barra "Fabricación 4/24 piezas", badge "Insumos 8/18", métricas "Por fabricar 20", "Insumos por reservar 10", "Partidas revisadas 0/3".
- Dentro del producto hay dos tablas sobre las mismas piezas: *Piezas de fabricación* (Necesarias / De inventario / **Cubiertas**) y *Resumen* (Total requerido / **Terminadas** / Por asignar / Avance).
- PANTALLA aparece con "Cubiertas 3" en una y "Terminadas 3" en la otra. El usuario no sabe si es lo mismo.

**Propuesta:**
- Definir un vocabulario único y usarlo en el encabezado, los productos, las piezas, el tablero y Hoy:
  - **Requeridas** · total que necesita el pedido.
  - **De inventario** · tomadas de existencias, no se fabrican.
  - **Por fabricar** = Requeridas − De inventario.
  - **Asignadas** · ya tienen trabajo (en cola, en curso o pausado).
  - **Terminadas** · unidades buenas.
  - **Sin asignar** = Por fabricar − Asignadas.
- Unir las dos tablas del producto en una sola tabla de piezas con esas columnas.
- Una barra **apilada** por pieza, producto y pedido: Terminadas (color pleno) · En curso (azul) · En cola (tenue) · Sin asignar (gris). Así se ve de un vistazo cuánto falta *asignar* y cuánto falta *producir*. Hoy la barra solo muestra terminadas, y "3 sin asignar" es texto aparte.
- Insumos siempre como un indicador separado con el mismo formato ("Insumos 8/18 reservados"), nunca mezclado con la fabricación.
- Centralizar textos y colores en `services/order_progress.py` y `views/progress_ui.py`, para que todas las vistas lean la misma función.

### 2. Encabezado del pedido más corto (P1)

**Hoy:** dos tarjetas seguidas con información repetida: etapas como badges (Planificar/Producir/Preparar/Salida) y además "Etapa actual · Producir"; cinco métricas; una explicación fija de cómo se mide la fabricación; luego una fila de 4 botones.

**Propuesta:**
- Una sola tarjeta: identidad (código, cliente, proyecto, entrega, prioridad, estado) a la izquierda y **siguiente paso + botón principal** a la derecha.
- Etapas como un paso a paso compacto (punto lleno = hecha, anillo = actual) en lugar de 4 badges más el badge de etapa actual.
- Bajar a 3 métricas: **Por fabricar**, **Sin asignar**, **Insumos por reservar**. "Trabajos en curso" y "Partidas revisadas" pasan a la pestaña Preparación o al tooltip.
- La explicación "La fabricación mide…" va en el `help` de la barra, no como texto fijo.
- "Ver trabajos", "Costos reales y margen" y "Ver documentos" van dentro de un solo menú "Más" junto a Opciones del pedido.

### 3. Lista de productos legible sin abrirlos (P1)

**Hoy:** el título del desplegable lo mete todo en una línea: `CIRRUS · BEIGE ×3 · Fabricación · 3/12 piezas · 25% · ITEM-0016`. Cerrado no tiene barra ni estado, y no dice si falta asignar.

**Propuesta:**
- Fila por producto con: nombre y cantidad, mini barra apilada, chips de estado ("2 piezas sin asignar", "Insumos faltan 4", "Listo para ensamblar") y el código ITEM en gris al final.
- Ordenar los productos por lo que requiere acción: primero los que tienen piezas sin asignar, luego en producción, al final los completos.
- Filtro rápido arriba: Todos · Sin asignar · En producción · Completos (además de la búsqueda actual).

### 4. Asignar piezas y crear trabajos en un solo flujo (P1)

**Hoy:**
- Para gestionar una pieza hay que elegirla en el selector "Pieza para gestionar", y se ve una a la vez.
- "Repartir" y "Crear trabajo" son dos botones para casi lo mismo (asignar unidades).
- El siguiente paso del pedido propone una pieza a la vez ("Asigna 3 · BASE"), aunque haya varias pendientes con el mismo material.
- En pedidos por receta, "Opciones de pieza" aparece deshabilitado y vacío.

**Propuesta:**
- **Repartir pendientes del producto** (y del pedido): una sola ventana con una tabla editable, una fila por pieza sin asignar y columnas por máquina (P1…P4, Sin máquina). Botón "Distribuir automáticamente" y un total que valida contra Sin asignar. Se guarda en una transacción, como el reparto actual.
- Agrupar por material en esa ventana (BASE, CAP y TAPA comparten PLA LIGHT KHAKI MATTE): permite asignar las tres a la misma impresora de una vez.
- Un solo botón por pieza, **Asignar**, que abre el reparto con esa pieza preseleccionada. "Crear trabajo" queda solo como opción avanzada dentro de ese diálogo.
- Ocultar los menús vacíos o deshabilitados en vez de mostrarlos apagados.

### 5. Trabajos visibles dentro de cada pieza (P2)

**Hoy:** los trabajos están en un desplegable "Trabajos asociados" dentro de la tarjeta de la pieza, que a su vez está dentro del desplegable del producto (3 niveles). Para ver qué máquina tiene qué hay que abrir todo.

**Propuesta:**
- Debajo de cada pieza, una línea por trabajo: `P2 · 4 u · En curso · 2/4 · fin 15:30` con las acciones principales (Avance, Pausar, Terminar) en iconos.
- Vista alternativa **Por máquina** dentro del pedido: qué hace cada impresora para este pedido y en qué orden.
- Las acciones raras (editar, mover de máquina, eliminar) van al menú del trabajo.

### 6. Revisión del producto en el momento correcto (P2)

**Hoy:** el check "ensamblado y revisado" y la etiqueta aparecen arriba del producto aunque las piezas sigan en 0%.

**Propuesta:** mostrar el check deshabilitado con el motivo ("Disponible al terminar las piezas y reservar insumos") hasta que aplique, y destacarlo cuando el producto quede listo. La etiqueta puede quedarse siempre visible.

### 7. Mensajes de contexto que se contradicen (P2)

- En un pedido de cliente aparece "Colección Origen · producción para inventario". Debe decir qué significa para *este* pedido ("Sus piezas entran al inventario Origen y se reservan para el cliente"), o mostrarse solo en lotes para stock.
- "Receta v3 · Cliente" (badge) y "Receta v3 · componentes" (texto) dicen lo mismo dos veces: dejar uno.
- "Registrar impresión terminada" está separado de las piezas: integrarlo como acción "Marcar impresas" en la tabla de piezas o en la fila del producto.

### 8. Rendimiento del detalle (P3)

- `views/orders.py` llama a `list_quotes()` y `list_sales()` completos para encontrar la venta o cotización vinculada. Conviene una consulta por `order_id`.
- Revisar que la vista de piezas no recalcule datos que ya vienen en el snapshot.

### Criterios de aceptación

- Con el pedido abierto, sin desplegar nada, se puede responder: ¿cuántas piezas faltan por asignar?, ¿cuántas por producir?, ¿qué producto va más atrasado?, ¿qué insumos faltan?
- La misma pieza muestra los mismos números y palabras en el pedido, la Cola de producción, el tablero y Hoy.
- Repartir todas las piezas pendientes de un producto toma una sola ventana.
- Las pruebas existentes de pedidos, reparto y tablero siguen pasando; se agregan pruebas para el reparto múltiple y la barra apilada.
