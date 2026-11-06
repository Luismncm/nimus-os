# v0.71 · Costo de receta desde G-code y recetas TAP BAR NFC

«Editar costo de pieza» acepta ahora un G-code: lee gramos y tiempo del slicer y deja la fuente como «G-code: archivo». El diálogo usa los mismos campos que una impresión real (Filamento · MXN/kg y Máquina · MXN/h) y arranca con el mismo precio del carrete (o 380 MXN/kg), así el costo de referencia y el real parten del mismo número. En el catálogo quedaron TAP BAR NFC 2, 3 y 4 con 2, 3 y 4 CHIPS NFC respectivamente. [Detalle](docs/COSTO_RECETAS_V071.md).

# v0.69 · Insumos y consumibles: una sola pantalla (1 de 2)

Insumos (cable, foco, empaque) y consumibles (filamento, resina, pintura, tornillería) vivían en dos pantallas separadas, cada una con su tabla y su editor de mínimos. Ahora comparten una sola pantalla en Inventario → Insumos y consumibles: una tabla combinada con filtro por tipo y buscador, un panel de detalle con las mismas acciones de siempre, y dos desplegables con las columnas más finas para quien las necesite. Falta la parte 2: integrar el inventario de Colección Origen al Inventario general. [Detalle](docs/INVENTARIO_V069.md).

# v0.68 · Costos de impresión: obligatorio, tarifa por máquina y lectura de G-code

Sin gramos capturados, el botón de guardar una impresión queda deshabilitado: ya no se puede crear un trabajo sin su costo de filamento. Cada máquina tiene su propia tarifa MXN/h (Máquinas → editar) y la rellena sola al elegirla. Un cargador opcional de G-code lee el tiempo y el peso de filamento que Bambu Studio, OrcaSlicer, PrusaSlicer o Cura ya calcularon, para no capturarlos a mano. [Detalle](docs/COSTOS_V068.md).

# v0.67 · Eliminar gastos efectuados (app local)

Los gastos ya solo se podían cancelar (quedan como histórico). Ahora, desde Más opciones en su detalle, también se pueden eliminar por completo — sin dejar registro, a diferencia de cancelar. Se bloquea solo cuando queda una referencia externa sin destino: un socio que lo cubrió, una compra de inventario, el costo adicional de un pedido o un gasto de la migración histórica. Funciona igual en SQLite y Postgres; por ahora, disponible solo en la app local. [Detalle](docs/ELIMINAR_GASTOS_V067.md).

# v0.57 · Negocio más orgánico: cuentas con historial, Gastos y Ventas más ligeros

Cada cuenta (en Resumen y previsión y en Tesorería) tiene ahora un botón «Ver historial» que lleva directo a sus movimientos filtrados. Las tres páginas de Negocio se leen como una sola barra conectada, con la actual resaltada. Las cifras principales de Ventas, Gastos y Control de gastos pasan de una fila plana de números a tarjetas con borde de color según si hay algo pendiente. El bloque de correspondencia con la hoja de control migrada se redujo a un solo enlace. [Detalle](docs/NEGOCIO_V057.md).

# v0.56 · Eliminar piezas y trabajos terminados, sin restricción general

Ya se puede eliminar un trabajo, pieza, producto o pedido completo aunque tenga producción terminada o iniciada. Solo se bloquea cuando ya movió piezas a inventario (Colección, stock o entrega) o tiene una falla de calidad registrada: ahí la base de datos no permite deshacerlo sin descuadrar existencias o perder el historial. Un pedido entregado o cancelado sigue siendo de solo lectura. [Detalle](docs/ELIMINAR_V056.md).

# v0.55 · Iconos y emojis en todo el sistema

Un solo vocabulario de emojis (views/emoji.py) para estados en etiquetas y tablas, pestañas de todas las páginas y 23 selectores. Los 21 títulos de sección que no tenían icono ahora lo tienen. Los valores internos no cambian, así que la navegación y las opciones recordadas siguen igual. [Detalle](docs/ICONOS_V055.md).

# v0.54 · Inventario: 📦 stock encontrado, iconos y menos pasos

«📦 Stock encontrado» registra varias piezas encontradas a la vez, en una tabla (pieza por modelo, cantidad y ubicación). Se guardan juntas y se pueden revertir. Inventario usa un selector de secciones con emojis y construye solo la sección abierta. La ficha de pieza muestra su saldo en una línea y tres acciones: 🔁 Mover, 📦 Encontré más y 🚚 Pedir. [Detalle](docs/INVENTARIO_V054.md).

# v0.53 · Costo de impresión capturado una sola vez

Al asignar una pieza se capturan duración, gramos y precio del filamento por kg (380 MXN/kg si el carrete no está registrado), con el costo calculado en vivo. Esos valores son el costo real al terminar: ya no hay «estimado» y luego «real», ni avisos de costeo pendiente. «Corregir costo» queda solo para cambios. [Detalle](docs/COSTO_V053.md).

# v0.52 · Refactor: menos código repetido

Sin cambios de reglas de negocio. Se eliminaron código muerto y 51 imports sin uso. Exportaciones CSV, validaciones de servicios, pedido desde cotización o venta, ventanas de anulación y formularios de pago ahora tienen una sola implementación. El CSV de producción ahora también se protege contra fórmulas. La lista de impresoras de la barra lateral ya no se repite en Hoy, Cola y Máquinas. [Detalle](docs/REFACTOR_V052.md).

# v0.51 · Auditoría UX/UI y un Hoy que se lee en segundos

Hoy abre con un saludo y una frase con lo importante del día, tarjetas de Pulso por área (total, alertas e «Ir a…»), una Agenda de hoy en orden de hora y prioridades más compactas. En todo el sistema se limpiaron los encabezados, se unificaron los selectores de sección y se dio peso a iconos e insignias. [Guía y hallazgos](docs/UX_V051.md).

# v0.50 · Navegación, Pedidos y Cola más claros

La barra lateral muestra un contador en vivo junto a cada sección (pedidos atrasados, impresiones en marcha o con problema, prototipos activos, máquinas detenidas), marca la página actual y, en Taller, lista las impresoras con lo que imprimen y su tiempo restante. Pedidos reúne sus filtros en una barra y cambia las métricas por un Enfoque que filtra con un clic; sus tarjetas del tablero son más compactas. La Cola convierte sus estados en filtros rápidos, compacta Por resolver y junta sus controles de Operar en una línea. [Guía](docs/UX_V050.md).

# v0.49 · Una forma de leer cada página

Cada página pone su título y sus acciones en una misma línea, sin descripciones repetidas. Hoy se volvió una sola página: el bloque «Herramientas del taller» se repartió entre las tarjetas de pedidos, Producir → Máquinas y Entregar. Ventas abre con filtros, cifras y tabla; la papelera quedó al final. El resumen de dinero completo vive solo en Control de gastos; Tesorería y Registro de gastos lo muestran en una línea con enlace. [Guía](docs/UX_V049.md).

# v0.48 · Entornos, Colección Origen e inventario separado

Taller (turquesa), Negocio (azul marino) y Colección Origen (negro con dorado) tienen cada uno su paleta; el menú lateral cambia con el selector Taller / Negocio. Colección Origen se distingue en dorado y negro en la cola, el calendario y los pedidos; los prototipos siguen en violeta. Los botones de formularios ya comparten el estilo del sistema. Inventario es el general y Colección Origen → Inventario reúne piezas, bases por color e insumos de Origen. Se quitaron pasos repetidos al tomar inventario en un pedido y en las entradas de insumos. [Guía de entornos y redundancias](docs/ENTORNOS_V048.md).

# v0.47 · Inventario más claro y disponibilidad en el pedido

El conteo de Inventario se lee como una suma (Disponibles + Reservadas = En taller), cada pantalla lleva nombre y propósito, y Pedidos pasó a **Compras**. El pedido tiene una vista **Inventario** que muestra, pieza por pieza, su flujo (inventario → impresión → terminada), qué existe, qué está por entrar y cuánto se puede tomar o **devolver**; las piezas se ven en tarjetas. Inventario separa lo **por entrar** por fase (por imprimir, imprimiendo, a punto de salir). [Guía del inventario](docs/INVENTARIO_V047.md).

# v0.46 · Interfaz renovada y captura única de impresiones

Tema más fresco, botones con una sola acción principal por pantalla y encabezados compactos. Nueva impresión, Asignar pieza y prototipos usan el mismo bloque de captura (cantidades, tiempo, filamento, impresora y horario), sin datos repetidos. Cola, Pedidos y el detalle del pedido reordenan sus acciones. [Guía de la interfaz](docs/INTERFAZ_V046.md).

# v0.45 · Stock sin pedido y cola agrupada

**Nueva impresión** distingue **Pedido**, **Stock** y **Prototipo**. El stock puede ir **Directo a inventario**, sin pedido vinculado: cada pieza buena entra a Colección al registrarse. Los pedidos reconocen esas piezas y **Usar inventario** las toma en vez de imprimirlas. La cola agrupada por Máquina, Estado o Para qué es comparte un mismo diseño a todo lo ancho. [Guía de stock y cola](docs/STOCK_Y_COLA.md).

# v0.44 · Compras vinculadas a Gastos

Al crear pedidos de inventario se registra su total y se elige **Por pagar** o **Ya pagado**. Pedido, gasto y pago inicial se guardan juntos. Las recepciones no duplican gastos. Los pedidos anteriores pueden vincularse a un gasto existente. [Guía de compras y gastos](docs/COMPRAS_Y_GASTOS.md).

# v0.43 · Finanzas integradas

El saldo usa automáticamente las cuentas y los movimientos existentes. **Total en cuentas**, **Gastos proyectados** y **Después de gastos** comparten el mismo cálculo en Tesorería y Gastos. Las previsiones por concepto se convierten en gastos sin duplicar importes. Consulta [la guía de finanzas](docs/FINANZAS_INTEGRADAS.md).

La planeación detallada y las versiones anteriores se conservan como opción. Las cuentas existentes se calculan automáticamente; Conciliar saldos sólo sirve para ajustar diferencias contra banco y caja.

# v0.40 · Conteo de bases por color

Inventario → Bases por color: Base, CAP y Tapa con conteos físicos, disponibles, reservados y en B2B. Incluye colores en cero, juegos de base disponibles y entradas con la referencia seleccionada. [Guía del conteo de bases](docs/CONTEO_BASES.md).

# v0.39 · Fabricación e insumos separados

La fabricación cuenta solo piezas por producir; cables, focos y empaque tienen su propio control de inventario. Pestaña Insumos dentro del pedido, reservas desde existencias, indicadores separados en Pedidos y Hoy, y filtro de faltantes. El 100% de fabricación conserva los requisitos de componentes y preparación para entregar. [Guía de avance de fabricación](docs/AVANCE_FABRICACION.md).

# v0.38 · Pedidos de inventario

Agregar inventario distingue **Entrada física** y **Pedido**. Seguimiento por proveedor y fecha, recepciones parciales, cancelación del saldo pendiente y entradas al inventario al confirmar la llegada. Integrado con reposición y Notificaciones. [Guía de pedidos de inventario](docs/PEDIDOS_INVENTARIO.md).

# v0.37 · Costo de impresión por parámetros

Calculadora por gramos, precio por gramo, tiempo y tarifa por hora, por pieza o lote. Desglose de material y tiempo, acceso desde Origen e Inventario y actualización versionada de costos de recetas. [Guía de costo de impresión](docs/COSTO_IMPRESION.md).

# v0.36 · Notificaciones

Acceso al final de la barra lateral y panel por pedidos, cobros, pagos, insumos y producción. Búsqueda, prioridades, saldos restantes y acceso directo al registro, con cuatro avisos por página. [Guía de notificaciones](docs/NOTIFICACIONES.md).

# v0.35 · Avisos en la barra lateral

Un solo acceso de Avisos con contadores de insumos y pendientes, vista previa limitada y actualización cada minuto. Los detalles se abren al pulsarlo; se retiran las señales duplicadas de Hoy e Inventario. [Guía de avisos](docs/AVISOS_LATERALES.md).

# v0.34 · Reposición de insumos

Inventario → Reposición de insumos: mínimos por componente, saldo neto con pedidos comprometidos y faltantes en negativo. Avisos discretos ámbar/rojo, sin bloquear la emisión de pedidos ni inventar existencias físicas. [Guía de reposición](docs/REPOSICION_INSUMOS.md).

# v0.33 · Control de producción

Capacidad por máquina, horarios sin cruces, fallas y reimpresiones, consumos y margen real por pedido y avisos operativos. Conserva las funciones y datos de NIMUS OS v0.32. [Guía de control de producción](docs/CONTROL_PRODUCCION.md).

# v0.32 · Navegación y diseño de NIMUS OS

Barra lateral por áreas **Taller / Negocio**, buscador de las quince secciones y accesos nativos con indicación de página activa. Jerarquía de encabezados, acciones principales y menús secundarios; tema común refinado para botones, formularios, tarjetas y tablas. Microinteracciones del tablero con movimiento reducido y confirmación de guardado nativa. [Guía de interfaz](docs/INTERFAZ_OS.md).

# v0.31 · Carrito y flujo comercial de Origen

**Colección Origen → Venta y pedido** reúne varias combinaciones modelo/color en una captura editable. Permite guardar cotización, venta confirmada o pedido operativo, con cálculo conjunto de reservas y faltantes. Las recetas se conservan al convertir documentos en producción. Las condiciones son editables por venta, con autorización manual y **sin anticipo mínimo fijo inicial**. Historial de acuerdos, responsables, cambios y cancelaciones; costos congelados al confirmar venta y escenario de preparación solo con datos completos. [Guía del flujo comercial](docs/FLUJO_COMERCIAL.md).

# v0.30 · Pedidos por modelo y variante de color

Al hacer un pedido de Origen se elige **modelo → color de base → cantidad**. Los tres modelos y tres colores tienen sus nueve recetas internas; se conservan las existentes y se completan solo las faltantes. Todos los colores siguen disponibles para pedir, con indicación de componentes libres, fabricación e insumos por comprar. Se reservan piezas al confirmar; la disponibilidad no representa lámparas ya ensambladas.

# v0.29 · Configurador continuo de recetas

Nueva vista **Crear receta** a página completa: pantalla, color de base e insumos con resumen en vivo de los siete componentes, existencias libres y costos capturados. Borrador de sesión que se conserva al navegar, tarjetas de componentes para continuar seleccionando y acceso a recetas ya existentes para evitar duplicados. **Componentes** divide pantallas, base y colores e insumos; **Recetas** contiene las combinaciones publicadas.

# v0.28 · Modelos de pantalla y colores de base

Origen distingue tres modelos de pantalla (Cirrus, Cúmulo y Strato) y un modelo de base con tres colores (beige, gris niebla y negro noche). CAP y tapa siguen el color de la base. Los modelos sin lámpara publicada ya aparecen en el selector y permiten preparar su combinación. La pantalla genérica PLA IVORY queda retirada de nuevas operaciones; se conserva el historial y el material de las pantallas válidas.

# v0.27 · Colección Origen

Gestión dedicada de lámparas completas: pantalla, juego de base compatible (BASE/CAP/TAPA), cable, foco y empaque. Componentes compartidos, fabricación separada de compra, reservas de insumos y disponibilidad por modelo. Preparado para nuevas formas y otros artículos. [Guía de Origen](docs/COLECCION_ORIGEN.md).

# v0.26 · Gestión de catálogo y recetas

Búsqueda y galería de productos, ficha con acciones contextuales y pestañas de receta vigente, editor, costos e historial. Cantidades editables en tabla, comparación de cambios y borradores de sesión. Variantes, piezas compartidas y protección de publicación concurrente. [Guía de catálogo](docs/CATALOGO_Y_RECETAS.md).

# v0.25 · Tablero interactivo y fotografías

Kanban con arrastre y alternativa por teclado, movimientos validados, fotos en productos/piezas e inventario con galería. Paleta azul petróleo, accesos operativos y pestañas persistentes. [Guía de tablero y fotos](docs/TABLERO_Y_FOTOS.md).

# v0.24 · Inventario y paleta de interfaz

Inventario con resumen de piezas físicas, disponibles, reservadas y asignadas a clientes; ficha de pieza, filtros, reservas vinculadas a pedidos e historial más claro. Paleta marfil, grafito y bronce con colores de estado sobrios. [Guía de inventario](docs/INVENTARIO_OPERACION.md).

# v0.23 · Productos, piezas y acciones de estado

Despiece con tabla de cantidades por producto, gestión compacta de piezas y foco en la pieza nueva. Acciones de preparación, revisión de todos los productos y controles de estado de trabajos. Reinicio solicitado de los pedidos de lámparas e inventario Origen, con respaldo y registro del alcance.

# v0.22 · Hoy y detalle del pedido

Resumen de prioridades, capacidad y cobros/pagos; navegación por áreas y filtros visibles. El pedido tiene encabezado operativo, acción contextual y pestañas Producción, Preparación, Documentos e Historial. [Guía de operación](docs/HOY_Y_DETALLE.md).

# v0.21 · Seguimiento visual de pedidos

Tablero por etapas, tarjetas consistentes, filtros de atención y seguimiento rápido. Alterna entre Tablero, Lista y Tabla y consulta hitos reales desde el detalle. [Guía de pedidos](docs/PEDIDOS_TABLERO.md).

# v0.20 · Socios y mejora de UX financiera

Acceso directo a **Tesorería → Socios**, captura manual de aportaciones con fecha, cuenta, importe y referencia, conciliación y anulación con historial. La entrada se registra una vez como capital. Presupuesto tiene totales en vivo, señal de cambios sin guardar y borradores por mes durante la sesión. Consulta [la guía de Socios](docs/SOCIOS_OPERACION.md).

## v0.19 · Presupuesto mensual y control financiero

Nueva sección **Tesorería → Presupuesto mensual**: fijos y variables por categoría, topes esenciales/ajustables/opcionales, comparación con pagos reales, propuestas editables desde recurrentes o mes anterior, copia entre meses e historial. Proyección de cobros y pagos a 3, 6 o 12 meses y escenarios de cobertura operativa con ventas netas, margen después de costos directos e IVA explícito. Los presupuestos no generan transacciones reales. Consulta [la guía de presupuesto](docs/PRESUPUESTO_MENSUAL.md).

## v0.18 · Costos de Origen y utilidad

Nueva vista **Costos y utilidad**, también accesible desde Catálogo y recetas y el detalle de cada venta. Costos por pieza, por lote y por receta, adicionales por producto y utilidad bruta estimada sin IVA, después de descuentos. Las ventas conservan versiones de su costeo.

Referencias aproximadas de Copia de COSTOS: 12 piezas y 5 recetas. El sistema recalcula CAP a $16.70; costos capturados Cirrus $400.55 y Cúmulo $407.15. Falta confirmar ensamble. Las impresiones vinculadas a catálogo pueden publicar sus consumos y tarifas como nueva referencia de costo.

[Guía de costos](docs/COSTOS_ORIGEN.md) · [Cotejo de ingresos y gastos](docs/cotejo_2026-10-11/COTEJO_2026-10-11.html).

---
# v0.17 · Aportaciones y conciliación

Cinco inyecciones históricas de SOCIOS ($233,000 MXN) registradas como entradas de capital a banco. Una aportación de $60,000 conserva fecha y socio pendientes de completar. Las ventas y cobros existentes se conservan.

- Tesorería → Movimientos → Conciliar movimiento: fecha, importe, cuenta efectiva, método y referencia.
- Tesorería → Socios → Editar aportación: datos e importe del capital recibido.
- Gastos → Conciliar gasto: importes, IVA y clasificación; opción explícita para ajustar también un pago único completo. Las compras cubiertas por socios actualizan su cobertura sin salida de caja/banco.
- Motivo obligatorio, historial anterior/corregido, control de ediciones concurrentes y transacciones completas. La fila original de Sheets se conserva y reimportar no duplica ni sobrescribe correcciones.

Consulta [la guía de operación](docs/TESORERIA_OPERACION.md). Base de datos v13; respaldo antes de actualizar.

---
## Tesorería operativa · v0.16

Resumen por banco y caja; movimientos con concepto, contraparte, categoría, comprobante y filtros; pendientes de captura; documentos por cobrar/pagar; socios con búsqueda y exportación. Todo el historial incluye los pagos sin fecha; las consultas por período los excluyen. Consulta [la guía de operación](docs/TESORERIA_OPERACION.md).

El flujo registrado se distingue del saldo disponible, cuya conciliación está pendiente. Las fechas de gasto y pago se revisan por separado. Se puede completar la clasificación de un gasto histórico conservando su fecha desconocida. Esta actualización solo cambia vistas y consultas; conserva los movimientos y la exclusión de ingresos solicitada.

## Migración de gastos · 11 de octubre de 2026

Se agregaron 141 gastos de MOVIMIENTOS y 11 compras pagadas por Ali de SOCIOS (152 gastos, $489,894.79 MXN). Se conservaron conceptos, proveedores, cuentas, comprobantes, importes y filas de origen. Los 69 gastos sin fecha están en Gastos → Históricos sin fecha y Tesorería → Por revisar, con exportación CSV. Los conceptos/categorías faltantes se identifican como pendientes. Los gastos ya pagados no generan cuentas por pagar.

Las compras pagadas por Ali quedan cubiertas como aportación, sin salida de caja/banco. DEVOLUCION CLIMA se vincula al reembolso de SOCIOS por $7,248.84 para contar una sola salida. Por indicación del usuario no se importaron VENTAS ni las cinco inyecciones de socios ($233,000). Los ingresos, pagos de ventas, producción e inventario existentes se conservaron. La conciliación de saldos queda pendiente.

Los importes se redondean a centavos por movimiento. Las compras del socio suman $202,803.39; el resumen de la hoja redondea el total acumulado a $202,803.38. Se preservan los valores originales en el registro de origen. No se calcula IVA cuando falta un desglose consistente.

El esquema 12 agrega trazabilidad y pagos directos de socios. La migración es transaccional, conserva respaldos y evita duplicados al repetir el archivo de origen. Consulta docs/migration_gastos_2026-10-11/migration_report.json.

# NIMUS Production v0.14

## Cola de producción por máquina · v0.14

- **Por máquina:** un panel por equipo, con el estado real, impresión en marcha o siguiente lote, unidades pendientes y carga estimada. El resto de la cola se consulta en un desplegable con selector de lote, sin llenar la pantalla de tarjetas.
- **Colores:** azul = máquina imprimiendo, verde = disponible, naranja = mantenimiento o trabajo pausado, rojo = fuera de servicio o bloqueado. El texto y los iconos acompañan el color. Los lotes terminados y las máquinas archivadas se distinguen en su historial.
- **Lista de trabajos** mantiene la operación por tarjetas; **Tabla** permite consultar toda la cola y gestionar un lote seleccionado.
- **Filtros:** máquina, estado, búsqueda, pedido, prioridad, proceso y programación (Todos, Hoy, Próximos 7 días, Vencidos o Sin programar). Hoy/próximos usan el inicio programado o, cuando falta, el fin estimado capturado. Sin programar identifica lotes sin inicio programado aunque ya tengan un fin manual.
- **Mostrar vacías** incluye máquinas activas sin lotes que coincidan con la consulta. Si la máquina está ocupada por un trabajo oculto por los filtros, el panel lo indica y el siguiente inicio continúa bloqueado por las reglas existentes.
- **Acciones:** iniciar, pausar, terminar, registrar avance, editar, programar o abrir pedido. Los filtros y la vista elegida se conservan durante la sesión; Limpiar filtros restablece la consulta.
- **Carga estimada:** suma la duración completa de los lotes abiertos que coinciden con la consulta y muestra cuántos carecen de duración. No descuenta el tiempo transcurrido ni las pausas y no representa una hora automática de disponibilidad.

No hay migración de datos: continúa el esquema 11. Se verificaron 14 pruebas de interfaz/operación existentes y de continuidad entre vistas, más revisión en navegador con base DEMO independiente. La instalación respalda código y base y comprueba que todas las filas permanecen iguales.

## Agenda de impresión, facturas PDF y correcciones · v0.13

**Agenda de impresión** (Operación) reúne calendario por máquina, próximas impresiones y costos previstos. Filtra por fecha, máquina, estado de operación y texto (pedido, cliente, pieza o material). Incluye pendientes sin fecha y horarios vencidos en la lista para poder resolverlos, aunque queden fuera del período del calendario. Las coincidencias en una misma máquina y los inicios/fines vencidos generan avisos dentro de NIMUS. No se envían notificaciones externas todavía. Las fechas de fin manual ya capturadas aparecen como triángulos cuando falta el inicio; no se inventa una hora de inicio.

1. Desde la agenda, Hoy, Cola de producción o un trabajo del pedido, pulsa **Programar / consumos**.
2. Indica **inicio programado** (fecha y hora local), **duración** en horas/minutos y **gramos estimados del lote completo**. Se puede incluir material para soportes y merma. Guardar programación no inicia la máquina.
3. Al pulsar **Iniciar**, se registra el inicio real. El fin previsto se calcula con el inicio real y la duración. En Hora de inicio real se puede corregir la hora de un trabajo ya iniciado; no se admite una hora futura o posterior al término.
4. En Consumo real y costos opcionales, registra gramos reales y tarifas de **MXN/kg de material** y **MXN/h de máquina**. El costo previsto es gramos/1000 × tarifa de material + minutos/60 × tarifa de máquina, con redondeo a centavos. Las tarifas quedan fijadas en ese trabajo; no se inventan tarifas para datos anteriores.
5. **Costos previstos** muestra material, máquina y total por impresión; el total solo suma lotes con datos completos. Es previsión, no genera gastos ni pagos. La agenda exporta CSV con fechas, duración, gramos y costo.
6. Los trabajos de pedidos entregados conservan su historial y son de solo lectura. Las pausas no descuentan automáticamente minutos de impresión: revisa la estimación al reprogramar.

**Factura y PDF** está en los detalles de Ventas y Gastos. Indica Sí/No lleva factura, folio/referencia, y adjunta un PDF de hasta 10 MB. Puedes marcar Sí y subir el archivo más tarde. Permite reemplazarlo, retirarlo y descargarlo; el archivo se guarda dentro de la base SQLite y sus respaldos. Marcar factura no cambia el IVA, total ni pagos. En gastos se mantiene consistente con el tipo y referencia de comprobante. En las ventas nuevas también está el check Lleva factura.

**Corrección de ventas:** selecciona una venta en el listado y pulsa Eliminar venta seleccionada, o usa Más opciones → Eliminar venta. Pasa a una papelera recuperable, se excluye de los totales y conserva historial/documentos. Las ventas con pagos vigentes o pedido vinculado requieren revisar primero esas operaciones. La papelera permite restaurarlas. No existe eliminación permanente en esta versión.

**Eliminar partidas** permite quitar productos de una venta directa activa sin historial de pagos, factura PDF ni pedido vinculado. Muestra el total corregido, recalcula descuento e IVA y conserva el contenido anterior y motivo en el historial. Para quitar todas las partidas usa Eliminar venta. Las cotizaciones aceptadas y sus ventas conservan su alcance original.

Migración a esquema 11: agrega documentos, papelera, historial de correcciones y planificación sin modificar las filas anteriores. Validación: 166 pruebas, ensayo de migración de una copia de datos reales, calendario visual y carga/descarga de PDF DEMO con identidad de bytes comprobada.

## Tesorería y operación diaria · v0.12

- **Tesorería** reúne Resumen y cuentas, Ventas, Gastos y Cotizaciones.
- **Cuentas:** crea, renombra, clasifica (Banco, Efectivo, Pasarela u Otra) y archiva cuentas. Una cuenta archivada conserva su historial y no recibe pagos nuevos.
- **Cobros:** en ventas directas y cotizaciones elige el método y la cuenta donde se recibió el dinero. Los cobros de una cotización se comparten con su venta: aparecen una sola vez en Tesorería.
- **Pagos de gastos:** la cuenta efectiva del pago determina la salida, aunque sea distinta de la cuenta prevista. Los nombres nuevos capturados en Gastos se incorporan como Otra y pueden clasificarse desde Cuentas.
- **Resumen:** consulta entradas, salidas y flujo neto por fecha del movimiento, cuenta y tipo; exporta CSV y abre el registro de origen. Incluye anticipos de cotizaciones y excluye pagos anulados. Es flujo registrado, no un saldo bancario: no incorpora saldos iniciales, transferencias internas ni aportaciones de socios.
- **Cobros anteriores:** se conservan sin inferir su cuenta por el método. Elige un movimiento sin cuenta y pulsa Asignar cuenta a este cobro. Esta asignación no modifica importe, fecha ni saldo. Para corregir una cuenta ya asignada, anula el registro de pago y vuelve a capturarlo.
- **Hoy:** cuatro frentes Producir / Entregar / Cobrar / Pagar con búsqueda, vencimientos y acciones directas. Cobra o paga sin abandonar la bandeja; revisa, empaca y confirma entregas desde sus pedidos. Las herramientas detalladas del taller siguen en un desplegable.
- **Continuidad:** los filtros se conservan durante la sesión al cambiar de pantalla o abrir un detalle. Continuar permite retomar el último pedido, venta, gasto o cotización abierto.
- **Reutilizar venta:** copia cliente, partidas y condiciones en una captura nueva; conserva fechas nuevas y no copia pagos, pedido ni cotización vinculados. Gastos y despieces conservan sus funciones de reutilización existentes.

La migración a esquema 10 agrega cuentas y relaciones con pagos. Conserva las filas anteriores, incluyendo producción, inventario, ventas, cobros y gastos. Los pagos de gastos anteriores conservan la cuenta explícitamente capturada. Se crean respaldos antes de instalar. Validación: 151 pruebas de regresión y flujos nuevos, prueba de migración con copia de datos reales y revisión en navegador con base DEMO separada.

## Gastos: movimientos, pagos y costos recurrentes

Estructura basada en [NIMUS · Control](https://docs.google.com/spreadsheets/d/1jmCHf1QxrXEZLHcKPJ5ArfY8qK2v6r951KKS-uW7PvU/edit). Se reutilizaron los campos, categorías preferidas, cuentas y unidades como opciones de captura. La implementación inicial solo reutilizaba la estructura; consulta la migración de gastos descrita arriba para el historial importado. La hoja original no se modificó.

1. **Gastos → Nuevo gasto:** concepto, categoría, proveedor, unidad, naturaleza (Fijo, Variable o Desarrollo / único), cuenta prevista, fecha y vencimiento opcional. Las propiedades permiten reutilizar valores anteriores o escribir nuevos.
2. **Importes:** elige Sin desglose, Subtotal + IVA 16%, Total con IVA 16% o Desglose manual. En Sin desglose se conserva el total sin inventar un IVA de cero. Calcular total muestra el resultado antes de registrar.
3. **Comprobante:** indica Pendiente, Factura, Recibo / nota o Sin comprobante, y su folio/referencia. El control destaca comprobantes pendientes y facturas sin desglose. Puedes adjuntar la factura PDF desde la pestaña Factura y PDF del gasto.
4. **Pago:** por defecto el gasto queda Por pagar. El check Pagado completo en la fecha del gasto registra gasto y liquidación juntos, de forma atómica. Para abonos o fechas distintas utiliza Registrar pago desde el detalle o Pagar desde Por pagar. La cuenta efectiva pertenece al pago y puede diferir de la cuenta prevista.
5. **Movimientos y Resumen:** filtros por fecha del gasto, concepto/proveedor/folio, categoría, unidad, naturaleza y estado; CSV y resumen por categoría. Pagado en el período usa la fecha del pago, incluso para gastos de otros meses. Saldo de estos gastos usa la fecha del gasto. Por pagar y Vencido abarcan todas las fechas y respetan los demás filtros.
6. **Costos recurrentes:** define nombre, concepto, importe, naturaleza y periodicidad mensual, bimestral, trimestral, semestral, anual o única. El equivalente mensual sirve como previsión y no suma a los gastos reales. Desarrollo / único requiere periodicidad Único. Editar un costo no cambia los gastos ya registrados.
7. **Registrar período:** crea explícitamente un gasto pendiente a partir del costo. Los períodos son de calendario: mes, pares de meses, trimestre, semestre o año. Un costo Único permite un solo registro. Se impide duplicar un mismo período, incluso después de cancelarlo; para correcciones revisa el original o registra un gasto manual con su motivo.
8. **Correcciones:** Editar gasto conserva historial. Los importes se bloquean cuando existe historial de pagos; clasificación, comprobante, notas y vencimiento siguen editables. Anular pago requiere motivo y conserva el registro original; no procesa reembolsos. Solo se cancela un gasto sin pagos vigentes. Reutilizar gasto copia sus datos sin copiar pagos, comprobante, pedido ni fechas anteriores.

La sección es un control operativo de gastos. No calcula saldos bancarios ni mezcla transferencias entre cuentas, aportaciones de socios o costos previstos con gastos pagados. Tampoco aumenta inventario al capturar una compra. Estos movimientos se gestionan en sus flujos correspondientes.

Migración aditiva al esquema 9 con respaldo de código y base. La carpeta instalada conserva el nombre `NIMUS_Production_v0.3`; la versión visible es v0.11. Los módulos y registros anteriores se conservan.

## Incorporado en v0.10

## Ventas y control de cobranza

- **Ventas → Nueva venta directa:** captura cliente reutilizable (o Público en general), concepto, fecha, canal y productos/servicios. Permite descuento, IVA opcional, notas y vencimiento de pago. Calcular total revisa importes sin guardar; Registrar venta genera el folio VEN y abre su detalle.
- **Desde cotización:** acepta la cotización y pulsa Registrar venta desde su detalle o desde Ventas. Cada cotización origina una sola venta. Conserva precios, partidas, pedido y pagos; no se copian ni se duplican los anticipos.
- **Registrar pago:** permite anticipos, abonos o liquidación, fecha, método y referencia. Los pagos de una venta desde cotización se consultan y corrigen en ambos apartados como un mismo registro. Las ventas directas usan folios PAG; las cotizaciones conservan REC.
- **Control general:** filtros por fecha de venta, cliente/referencia, origen, canal y cobranza. Vendido y Saldo de estas ventas usan la fecha de venta; Cobrado usa la fecha real del pago, incluyendo cobros de ventas anteriores al período. La cartera y el vencido de todas las fechas respetan los demás filtros. Cotizaciones sin venta registrada no suman aquí.
- **Pedido opcional:** Crear pedido incluye únicamente partidas Para fabricar. Si ya existe un pedido de la cotización, se abre el mismo. Hay acceso de regreso a Ventas desde Pedidos. Servicios y ventas de productos disponibles pueden permanecer sin pedido.
- **Exportación:** CSV de la consulta y comprobante HTML por venta para imprimir o guardar como PDF. El comprobante presenta partidas, impuestos/descuentos, pagos y saldo.
- **Correcciones:** la venta confirmada conserva su alcance. Los pagos pueden anularse con motivo y conservan historial. Una venta sin pagos vigentes puede cancelarse con motivo; deja de sumar en los indicadores. La cancelación no procesa reembolsos ni cancela automáticamente producción o inventario. Para corregir el alcance, cancela la captura y registra una nueva; para cotizaciones, duplica la cotización.

El registro comercial no descuenta piezas ni simula fabricación o entrega. Se conserva la gestión de inventario existente. La migración al esquema 8 agrega el módulo sin convertir cotizaciones/pedidos históricos automáticamente ni crear ventas DEMO en la base real.

La aplicación instalada conserva su carpeta del escritorio `NIMUS_Production_v0.3`. La versión visible ahora es v0.10. Antes de actualizar se respalda código y base de datos; una restauración requiere ambas copias de la misma versión.

## Incorporado en v0.9

## Cotizaciones y flujo comercial

Basado en COTIZADOR_NIMUS_VOLUMEN_CORREGIDO.html, integrado en la misma base local.

1. Abre Cotizaciones y pulsa Nueva cotización. Completa cliente, proyecto y partidas; marca Para fabricar solo en productos que pasarán al taller.
2. Edita cantidades y precios en la tabla. Agrega rangos en Precios por volumen; Hasta vacío indica un rango abierto. Selecciona el número de partida y pulsa Aplicar volumen y guardar. El descuento de referencia no se aplica por segunda vez.
3. Calcular y guardar conserva los datos en SQLite y muestra subtotal, descuento global, IVA opcional del 16% y total en MXN. Los importes se redondean a centavos. Cambios sin guardar no se exportan.
4. Contacto y alcance incluye solución, contexto, nivel, tecnología, objetivo, referencia, entrega y responsable. Notas, condiciones e imágenes permite hasta cuatro prototipos PNG/JPG/WEBP de 3 MB cada uno, con descripción editable.
5. Vista para cliente descarga un HTML autocontenido. Ábrelo y pulsa Imprimir / guardar como PDF. No depende de fuentes o servicios externos.
6. Pagos y recibos registra importes realmente recibidos, fecha, método, concepto y referencia, con folio REC. El recibo muestra el saldo; nunca inventa un pago. Puedes anular un registro con motivo, conservando su historial. Esto no procesa transacciones ni devoluciones.
7. Cambia Estado comercial a Aceptada y pulsa Crear pedido. Solo las partidas Para fabricar se convierten en items con cantidades enteras. Define después el despiece o reutiliza uno existente. No se deduce stock ni se simula impresión. El vínculo permite abrir pedido o cotización en ambos sentidos.
8. Una cotización con pedido o historial de pagos conserva su alcance. Duplicar crea un nuevo folio editable sin pagos ni pedido asociado. Enviada es una marca manual, no envía correos ni mensajes.

Incluye los pendientes v0.8: impresión rápida por item/pieza y entradas manuales de inventario con motivo, reversión y reservas. La carpeta del escritorio conserva el nombre NIMUS_Production_v0.3.

Migración al esquema 7 con respaldo previo. Se conservan los registros existentes y no se copian datos DEMO a producción.

## Incorporado en v0.8

## Impresión rápida y entradas manuales

- En Pedidos, el panel Impresión rápida permite marcar un item completo o cada pieza de Impresión 3D / Resina.
- El check registra todas las unidades buenas pendientes, termina los trabajos existentes y registra las unidades sin asignar con máquina no especificada. No inicia impresoras ni confirma revisión, empaque o entrega.
- Para cantidades parciales o correcciones, usa Avance / Editar trabajo en los trabajos asociados. Los trabajos bloqueados deben revisarse antes de completarse.
- Colección / Inventario permite Agregar inventario sin producir: elige una existencia, pieza del catálogo o nueva referencia; indica unidades, ubicación y motivo.
- Las entradas manuales se distinguen de Producción y se pueden revertir desde Movimientos cuando las unidades siguen disponibles. Las reservas se respetan.
- Los materiales y nombres ya utilizados se pueden reutilizar. Las pestañas y paneles conservan su estado.
- La migración a esquema 6 respalda la base y conserva sus registros anteriores. No agrega existencias ni producción retroactivas.

## Notas de v0.7

Herramienta local para responder: **¿qué debemos fabricar, cuánto falta y qué debemos mover ahora?**
Python, Streamlit y SQLite. Sin cuentas, servicios cloud ni sincronización externa.

## Nuevo en v0.7: operación diaria y preparación

- **Hoy → Operar el taller:** entregas vencidas y de hoy, bloqueos, piezas sin asignar, trabajos en marcha y arranque del siguiente trabajo por máquina.
- **Hoy → Revisión y empacado:** elige el pedido y marca Revisión final, Empacado y Listo para salida. La pestaña seleccionada se conserva al guardar.
- **Hoy → Planificar y gestionar:** resumen de pedidos, items revisados, preparación pendiente, despieces por definir y carga de máquinas.
- **Pedidos → Preparación del pedido:** los mismos checks, checklist de items e historial de cambios.
- Cada item tiene un check **Revisado** y una **Etiqueta** reutilizable (por ejemplo Caja 2, B2B o frágil), sin editar su información completa.
- Los checks son controles manuales. No completan trabajos, no generan existencias y no confirman entrega. Pueden desmarcarse mientras el pedido esté activo. Un pedido entregado conserva su historial de solo lectura.
- Las etiquetas también se incluyen en la búsqueda de pedidos. Los cambios tienen fecha y se evita sobrescribir una actualización realizada desde otra ventana.
- Migración aditiva al esquema 5 con respaldo automático `pre-v07`. Los checks anteriores a esta versión comienzan pendientes; no se inventa una revisión o un empaque ya realizado.

## Incorporado en v0.6: captura ágil, catálogo y recetas

- **Agregar item → Reutilizar despiece:** elige un producto anterior y su nueva cantidad. Se copian las piezas con sus materiales y procesos, escaladas por producto. Solo se ofrecen despieces con cantidades enteras por unidad.
- **Agregar pieza → Reutilizar pieza:** recupera nombre, material, proceso y notas; indica unidades por producto. **Guardar y agregar otra** mantiene abierto el formulario y conserva material, proceso y cantidad.
- Los paneles de items y trabajos conservan su apertura. **Despiece rápido** guarda todos sus campos juntos, sin recargar al cambiar cada opción.
- **Guardar como receta**, dentro de un item, convierte su despiece en una definición reutilizable sin modificar el pedido original.
- **Catálogo y recetas:** crea productos, piezas con variantes y versiones de recetas. Una nueva versión se aplica a pedidos futuros; las versiones anteriores quedan conservadas.
- **Pedidos → Desde receta:** elige producto, cantidad y destino Cliente o Stock. Revisa las columnas Necesarias, Libres, A reservar y A fabricar. Al confirmar se reservan las existencias y se crean piezas de producción solo para los faltantes. Si cambiaron los saldos, pulsa Recalcular.
- **Inventario → Reservas por pedido:** las reservas se descuentan del disponible, no del saldo físico. La producción de receta entra en inventario y queda reservada para su pedido. Al entregar al cliente se registra la salida; al cerrar un lote para Stock se liberan sus piezas en Stock.
- **Existencias anteriores:** usa Vincular a pieza del catálogo y confirma compatibilidad de variante. No se mezclan modelos ni se infiere stock histórico automáticamente.
- **Máquinas:** agregar, editar código/nombre/disponibilidad/notas y eliminar equipos sin trabajos. Los equipos con historial se archivan después de terminar o reasignar pendientes y se pueden reactivar.

La receta mide **componentes cubiertos**, no lámparas ensambladas. Ensamble con consumo de componentes e inventario de producto terminado queda fuera de esta versión. Los pedidos personalizados conservan su flujo anterior.

La base migra a esquema 4 con respaldo automático `data/backups/*pre-v06*.db`. El instalador conserva además una copia del código anterior. No reemplaces la base actual por una de demostración. Después de migrar, el código v0.5 requiere restaurar también su respaldo de base para volver a esa versión.

## Interfaz y propiedades reutilizables

- Nueva paleta verde petróleo, estados con iconos y color, métricas agrupadas y botones con jerarquía consistente.
- En producción, **Avance** es la acción principal; **Terminar** registra todas las unidades restantes.
- Pedidos con selector de activos/entregados; cola con filtros agrupados y botón **Limpiar filtros**.
- Materiales, modelos/items, nombres de pieza y clientes permiten **seleccionar un valor guardado o escribir uno nuevo y pulsar Enter**. El valor queda disponible para siguientes registros después de guardar. También funciona en Despiece rápido y clientes B2B.
- Las listas toman los valores de los registros existentes y el historial de inventario. Omiten vacíos y agrupan variantes de mayúsculas y espacios; materiales diferentes siguen separados. No crean un catálogo independiente de insumos.
- Inventario identifica los saldos globales y muestra la pieza seleccionada antes de asignar. Al cambiar filtros se selecciona una pieza del resultado vigente. Cada asignación nueva empieza sin la cantidad/cliente anteriores; usa Stock como origen si no quedan piezas en Colección.
- Se conserva el control transaccional de saldos, la entrada única por avance, el historial y la protección contra sobreasignaciones.

## Ejecutar en Windows

Requisito: Python **3.11 o superior**. La versión se verificó con Python 3.12 y Streamlit 1.65.

Haz doble clic en **INICIAR_WINDOWS.bat**. Si esta copia de NIMUS ya está funcionando, abre su navegador sin iniciar otro servidor. Si está cerrada, crea `.venv` si hace falta, prepara las dependencias y abre la aplicación.
Normalmente usa <http://localhost:8502>. Si otra aplicación ocupa ese puerto, elige uno libre entre 8502 y 8512 y muestra la dirección en la terminal. La primera instalación requiere internet; el uso diario funciona localmente.

También puedes ejecutar en PowerShell, sin activar el entorno:

```powershell
cd "C:\Users\fella\Desktop\NIMUS_Production_v0.3"
.\.venv\Scripts\python.exe scripts\launch_windows.py
```

Instalación manual en una carpeta nueva:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-local.txt
.\.venv\Scripts\python.exe scripts\launch_windows.py
```

Para detener una instancia iniciada por el lanzador: `Ctrl+C` en su terminal. Volver a ejecutar el iniciador abre la instancia que ya está activa. Para comprobarlo sin abrir el navegador, ejecuta `.venv\Scripts\python.exe scripts\launch_windows.py --check`.
En macOS/Linux: `bash iniciar_mac_linux.sh`.

## Flujo de taller

1. **Pedidos → Nuevo pedido:** cliente/proyecto, entrega y prioridad.
2. **Agregar item:** producto y cantidad, por ejemplo Lámpara Origen ×10.
3. **Despiece rápido:** escribe un nombre de pieza por línea y su cantidad por producto. Para 10 lámparas, Base/Pantalla/Tapa/Placa ×1 crea **10 de cada una**, 40 unidades en total. Para cantidades distintas usa **Agregar pieza**, que pide el total de esa pieza para el item.
4. **Repartir:** introduce las cantidades por máquina en una sola ventana; por ejemplo Base ×10 → P1 ×4, P2 ×4 y P3 ×2. También puedes distribuir automáticamente entre las disponibles o asignar unidades fuera de impresora. El reparto completo se guarda en una transacción.
5. **Iniciar**, registrar **Avance**, **Pausar**, **Bloquear** o **Terminar** desde la tarjeta del trabajo. En Avance registra el total de unidades buenas del lote, no un incremento.
6. Al completar todas las piezas, el pedido pasa a **Listo**. Confirma **Marcar entregado** para conservarlo en el histórico.

Los procesos fuera de impresora usan **Sin máquina**. Se admiten Impresión 3D, Resina, Postproceso, Ensamble, Grabado, Empaque y Producción externa.

### Seis vistas

- **Hoy:** métricas y disponibilidad de tus máquinas al principio, acción recomendada según la fase del pedido, trabajo sugerido, producción en curso y atención por vencimientos/bloqueos. Pulsa una máquina para abrir su cola.
- **Pedidos:** tarjetas con búsqueda, entrega y progreso; **Abrir** muestra el árbol Pedido → Item → Pieza → Trabajos y el siguiente paso. Despiece rápido y reparto por pieza. Editar/eliminar están en los menús de cada registro. El filtro **Entregados** conserva el histórico.
- **Cola de producción:** tarjetas con acciones directas y una pestaña de tabla compacta. Filtros por máquina/estado/prioridad/proyecto/proceso. **Activos** es el filtro inicial; **Todos** incluye los terminados. Al entrar desde un pedido o una máquina se aplica su filtro.
- **Máquinas:** ocupación automática, trabajo actual, avance, fin estimado, siguiente trabajo y disponibilidad/notas dentro de cada tarjeta.
- **Inventario:** piezas Origen y generales; saldos físicos, disponibles y reservados, B2B, entregas e historial exportable.
- **Catálogo y recetas:** productos, piezas reutilizables y despieces versionados.

### Colección Origen → inventario → B2B o stock

Al crear o editar un item, activa **Producir para inventario de Colección Origen** antes de registrar avances. El nombre del item identifica el modelo de lámpara. Los pedidos normales continúan funcionando igual.

- **Avance** y **Terminar** ingresan las nuevas unidades buenas de piezas con proceso **Impresión 3D** o **Resina**. Base, pantalla, tapa y demás componentes se cuentan por separado. Ensamble, empaque y otros procesos no generan otro ingreso de la misma pieza.
- Modelo, nombre de pieza, material y proceso iguales acumulan cantidades de distintos lotes/pedidos. Se ignoran mayúsculas y espacios repetidos al agrupar; colores o variantes deben distinguirse en el material o nombre del modelo/pieza.
- **Inventario colección → Inventario → Asignar / trasladar piezas** permite mover de Colección a Stock, regresar de Stock a Colección o asignar a un cliente B2B desde ambos. B2B representa asignación de piezas, no confirmación de envío o facturación.
- **Asignaciones B2B** muestra el saldo por cliente. **Movimientos** conserva fecha, cantidad, origen, destino, cliente y el trabajo/pedido de cada ingreso. Puedes exportar inventario y movimientos a CSV.
- Para corregir un traslado o asignación completa, usa **Revertir movimiento** e indica el motivo. No se borra el historial. Si esas piezas ya se movieron de nuevo, devuelve o revierte primero los movimientos posteriores.
- Para corregir producción, edita el avance del trabajo. Reducirlo descuenta de Colección y se rechaza si las piezas ya se movieron a Stock o B2B y no queda saldo suficiente. Devuélvelas primero; la corrección y el avance se guardan juntos o no se guarda ninguno.

Ejemplo: 10 bases impresas → 10 por asignar → 4 a un cliente B2B + 3 a stock → 3 por asignar, 3 en stock y 4 asignadas a B2B. No se generan existencias por cantidades planeadas ni por unidades fallidas.

Los items existentes se mantienen sin colección. No hay ingresos retroactivos automáticos. Una vez registrada producción, el modelo/destino del item y la identidad de sus piezas no se pueden cambiar; crea otro item/pieza para otro modelo o material. Consulta [guía de inventario](docs/INVENTARIO_ORIGEN_V04.md).

La interfaz usa los logos originales de NIMUS en `assets/brand/`, navegación lateral, estados con texto y color y un tema nativo de Streamlit. Los SVG mantienen las formas originales; se ajustó el área visible y se añadió una versión blanca para la barra lateral. Los originales de referencia están incluidos, sin modificar la carpeta de marca suministrada.

**Exportar y respaldar** está en la barra lateral. **Actualizar** vuelve a leer SQLite y recalcula vencimientos; cada acción también actualiza la vista.

## Cantidades, estados e integridad

- `quantity_required` es el **total físico para el item**. Cambiar la cantidad comercial del item no multiplica ni cambia silenciosamente sus piezas.
- La suma de cantidades de trabajos, incluidos los terminados, no puede superar la cantidad requerida. Reduce un trabajo o aumenta explícitamente la pieza antes de reasignar.
- Las terminadas son enteros entre cero y la cantidad del trabajo. Solo cuentan unidades realmente buenas; el estado por sí mismo nunca inventa progreso.
- **Terminar (+N)** registra todas las unidades restantes como terminadas. Para un lote parcial usa **Avance**. Si un lote tuvo fallos, puedes reducir su cantidad hasta las unidades buenas desde **Más → Editar trabajo** y asignar el resto a otro trabajo.
- Un trabajo con todas las unidades completadas pasa a **Terminado**. No se permite guardar Terminado con terminadas parciales. Antes de entregar, se pueden corregir cantidades y reabrir un trabajo como Pausado; la corrección recalcula el pedido.
- Una impresora admite **un solo trabajo en producción**. Pausar, bloquear, terminar o reasignar libera la impresora anterior. Mantenimiento/Fuera de servicio impiden iniciar; los trabajos pueden esperar en su cola.
- El progreso de item y pedido es `SUM(unidades terminadas) / SUM(unidades requeridas)`. Ejemplo: 32/40 = **80%**. No se promedian porcentajes ni se multiplican piezas por trabajos o por cantidad de item.
- Un item sin piezas muestra un aviso y evita entregar el pedido, aunque el despiece definido marque 100%.
- Estados de pedido: Pendiente, En producción, Bloqueado, Listo, Entregado. Los primeros cuatro se derivan de los trabajos y del bloqueo manual; Entregado se confirma explícitamente. Bloqueado tiene precedencia sobre Listo.
- Bloquear un pedido impide iniciar/reanudar trabajos, pero permite registrar el avance de uno que ya estaba en curso. Un trabajo bloqueado también señala el pedido como Bloqueado; los demás trabajos pueden continuar.
- Estados de trabajo: En cola, En producción, Pausado, Bloqueado, Terminado. Fechas de inicio y fin real se registran automáticamente.
- Prioridades de trabajo y pedido son independientes: al crear un trabajo hereda la del pedido. Cambiar después la prioridad del pedido no altera las prioridades específicas ya asignadas.
- El siguiente sugerido usa prioridad del trabajo, entrega, fin estimado y antigüedad. Excluye trabajos bloqueados, pedidos bloqueados manualmente y máquinas no disponibles. Los procesos sin máquina pueden iniciar en paralelo.
- Un trabajo vence por su fin estimado; si no tiene, se usa el día de entrega del pedido. Una fecha de entrega vence al terminar ese día. Un fin estimado con hora vence en esa hora.
- El histórico entregado es de solo lectura. Solo se eliminan registros sin producción iniciada, con confirmación y borrado en cascada. No se pueden borrar trabajos iniciados ni ramas que los contengan.
- SQLite usa claves foráneas, restricciones de cantidades/estados, disparadores de capacidad, índice de ocupación única y transacciones `BEGIN IMMEDIATE`. Las ediciones de trabajos detectan una versión desactualizada de otra ventana.

## Arquitectura y estructura

```text
app.py                     Arranque y navegación
db.py                      Conexiones, esquema, migración y respaldos
models/constants.py        Estados, procesos y prioridades compartidos
services/production.py     Reglas y operaciones transaccionales
services/queries.py        Lecturas, métricas, filtros y CSV
services/workflow.py       Próximo paso del pedido y reparto equilibrado
services/inventory.py      Entradas, saldos, asignaciones y reversiones de colección
models/inventory_schema.py Migración aditiva del inventario
utils/calculations.py      Progreso ponderado por cantidades
utils/dates.py             Fechas y hora del taller
views/                     Hoy, Pedidos, Cola, Máquinas y formularios
assets/brand/              Logotipo e isotipo originales y variantes SVG
.streamlit/config.toml     Tema nativo y configuración local
scripts/check_runtime.py   Comprueba dependencias antes de iniciar
scripts/launch_windows.py  Reutiliza la instancia activa o elige un puerto libre
tests/                     Lógica, SQLite, migración y UI con AppTest
docs/                      Análisis inicial y detalle de migración
data/nimus_production.db   Base operativa
data/backups/              Respaldos automáticos/manuales
```

Las tablas de producción son `orders`, `items`, `parts`, `production_jobs` y `machines`. v0.4 añade `inventory_skus` e `inventory_movements`; los saldos se calculan desde movimientos inmutables y no se editan manualmente.
Las cantidades completadas de piezas/items/pedidos **se calculan**, no se duplican en SQLite.
Los IDs son enteros autoincrementales; la interfaz muestra ORD/ITEM/PART/JOB-0001. Los códigos de pedidos y trabajos existentes se conservan.
Una lectura de las cinco tablas genera una instantánea coherente, sin consultas adicionales por cada item o pieza.

La base se resuelve desde la carpeta del código, no desde el directorio de la terminal. Para una base de pruebas alternativa:

```powershell
$env:NIMUS_DB_PATH = "C:\ruta\pruebas.db"
```

Las nuevas horas se registran como hora local de **America/Mexico_City**. Se puede cambiar con `NIMUS_TIMEZONE` a una zona IANA. Las fechas antiguas se conservan tal como estaban; no se les supone una zona distinta.

## Migración desde v0.1

Se ejecuta automáticamente al abrir v0.2 o v0.3. Antes de cambiar SQLite se crea `data/backups/*-pre-v02-*.db` mediante la API de respaldo de SQLite.
La actualización es transaccional e idempotente (`PRAGMA user_version = 2`). Si hay datos incompatibles se cancela por completo con un mensaje y se conserva el respaldo.
No se infieren nuevas cantidades a partir de los items. Consulta [detalle de migración](docs/MIGRACION_V02.md).

**v0.3 no cambia el esquema SQLite**: conserva la versión 2 y las cantidades existentes. El despiece automático solo aplica a las piezas nuevas creadas con esa acción. Consulta [mejoras de interfaz](docs/UX_V03.md).

**v0.4 actualiza SQLite al esquema 3** de forma aditiva: agrega `items.collection` y las dos tablas de inventario. Antes de migrar esquema 2 se crea `data/backups/*-pre-v04-*.db`; si falla, se revierte todo. Las filas existentes mantienen sus valores y ninguna producción anterior se supone perteneciente a Origen. Para volver a v0.3, restaura también el respaldo de esquema 2 con todas las instancias cerradas.

## Respaldar y recuperar

- Con la aplicación abierta: barra lateral → **Exportar y respaldar → Respaldar SQLite**, o doble clic en **RESPALDAR_WINDOWS.bat**. Es una copia coherente aun con la base abierta.
- Copia periódicamente el archivo generado de `data/backups/` a otra ubicación/disco. Los respaldos en el mismo disco no protegen de una falla del disco.
- Con todas las instancias cerradas también puedes copiar `data/nimus_production.db`.
- Para recuperar, detén **todas** las instancias, conserva la base actual con otro nombre y copia el respaldo a `data/nimus_production.db`. No mezcles una base restaurada con archivos `-wal`/`-shm` de otra versión. Si existieran, conserva el conjunto original aparte con la app cerrada antes de restaurar.
- Para volver al código v0.1, restaura también su base pre-v02. No abras el esquema v0.2 con el código antiguo.

## CSV

**CSV de producción** mantiene los nombres originales, incluido `completed_quantity`, y añade IDs de items/piezas, `quantity_completed`, prioridad del trabajo, fechas reales y notas. UTF-8 con BOM para Windows/Excel. Conserva pedidos/items/piezas sin trabajos y pedidos entregados.

Es una tabla plana **por trabajo**: las cantidades de pieza se repiten si hay varios trabajos. Suma `job_quantity`/`quantity_completed` para analizar trabajos; no sumes `quantity_required` repetida.
**CSV de piezas** contiene exactamente una fila por pieza, con requeridas, asignadas, completadas, restantes y sin asignar. Usa este archivo para totales por proyecto en Sheets/Looker Studio.
No hay sincronización con Google Sheets.

## Verificar

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Las 92 pruebas usan datos temporales. Cubren progreso, sobreasignación, actualizaciones concurrentes, máquinas, estados, cascadas, histórico, CSV, migración/rollback, reparto atómico, despiece, entradas automáticas, dispersión B2B/stock, reversiones, doble envío, reutilización de propiedades, selección de piezas después de filtrar, inicio del programa y las seis vistas con Streamlit AppTest. La entrada de un material nuevo y su posterior reutilización también se verificaron en navegador con datos DEMO aislados.

## Alcance deliberado

Aplicación para una estación local: sin autenticación multiusuario, cloud, telemetría, inventario general de insumos, costos, facturación, dependencias entre procesos ni estimador automático de tiempos. El inventario nuevo cubre piezas impresas Origen; no descuenta componentes para ensamblar lámparas completas. Hay historial de inventario, pero no auditoría de todas las ediciones de producción. El fin estimado es manual y la utilización es instantánea. Para historiales grandes, el siguiente paso sería paginar/filtrar en SQL.


