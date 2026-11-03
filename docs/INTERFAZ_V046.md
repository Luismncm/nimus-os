# v0.46 · Interfaz renovada y captura única de impresiones

Cambia el aspecto y el orden de las pantallas. Las reglas, los datos y lo que se puede hacer siguen iguales.

## Tema

- Paleta más clara: el turquesa de la marca es la acción principal, sobre fondos neutros. Verde, azul, naranja, rojo y violeta conservan su significado (listo, en curso, atención, problema y prototipo).
- Los botones tienen la misma altura y un peso de letra claro, y responden al pasar el cursor. En cada pantalla, el botón principal es el único relleno de color: por ejemplo, **Nueva impresión** en la Cola o **Desde receta** en Pedidos. Las acciones de cada fila (Asignar, Por resolver) son secundarias.
- Las métricas, tarjetas de impresora, tarjetas de pedido y paneles tienen superficie blanca con una sombra suave. Los bloques de formulario se agrupan en secciones con un fondo tenue.
- El encabezado ocupa una sola línea (título y fecha). Debajo van el área y la descripción. El contenido empieza más arriba.
- La barra de avance, la franja de 24 h y el calendario usan los mismos colores, definidos en un solo lugar (`views/kind_style.py`).

## Color de los botones por intención

El color dice **qué hace** un botón, no qué tan importante es. La importancia la da el estilo: relleno (principal), con borde (secundario) o solo texto (terciario).

| Color | Intención | Ejemplos |
|---|---|---|
| Turquesa relleno | Acción principal de la pantalla | Nueva impresión, Iniciar, Repartir piezas, Desde receta |
| Verde | Completar o entregar | Terminar, Entregar, Confirmar entrega, Cerrar lote |
| Naranja | Detener, avisar o corregir | Pausar, Falla, Reimprimir, Separar, botones de Por resolver |
| Rojo | Bloquear, eliminar, anular o cancelar | Bloquear, Eliminar trabajo o pedido, Anular registro, Cancelar venta |
| Azul | Usar inventario en vez de imprimir | Usar inventario, Tomar de inventario, Sumar a otra impresión |

Las acciones secundarias llevan un tono suave (fondo tenue y texto de color). Las confirmaciones (Eliminar definitivamente, Confirmar entrega, Tomar de inventario, Registrar falla) llevan el color sólido de su intención. En el menú **Más** de cada impresión, las acciones de trabajo van arriba y Bloquear y Eliminar quedan al final, separadas por una línea.

Los colores se asignan en `views/theme.py` (`INTENTS`) según la clave del botón. Para dar color a un botón nuevo basta con que su clave termine como una de esa lista, por ejemplo `_finish`, `_pause` o `_delete`.

### Botones importantes y color de inicio

- El botón principal de cada zona tiene un relleno turquesa más profundo, un borde de luz arriba, una sombra más marcada y más peso de letra; deshabilitado se ve apagado.
- **Iniciar**, **Reanudar** e **Iniciar siguiente** van en azul, el color de «imprimiendo», porque llevan la impresión a ese estado.

## Un color por pedido

Cada pedido de cliente tiene su propio color, fijo según su número. Se ve igual donde aparezca:

- En el **tablero y las tarjetas de Pedidos**: borde izquierdo y etiqueta con el código del pedido.
- En el **detalle del pedido**: la misma etiqueta junto al código.
- En la **cola** y en las impresiones de cada pieza: borde de la tarjeta y etiqueta «código · cliente».

Son ocho tonos (índigo, rosa, oliva, coral, cian, dorado, café y pizarra) que no se parecen a los colores de estado ni al violeta. **Los prototipos conservan el violeta y el stock el azul**, así que un pedido, un lote de stock y un prototipo nunca se confunden. Los colores se definen en `views/kind_style.py` (`IDENTITY`).

## Una sola forma de preparar una impresión

**Nueva impresión** (para pedido, stock o prototipo) y **Asignar pieza** usan el mismo bloque, en el mismo orden:

1. **Qué se imprime**: pedido o proyecto, pieza, **Unidades** y **Extra para inventario** en una sola línea. Debajo, un resumen: «Se imprimen 5: 3 para el pedido + 2 a inventario».
2. **Cómo y dónde**: duración (h y min), filamento en gramos y tarifa de máquina en una sola línea. Debajo, las impresoras ordenadas por filamento cargado y primer horario libre (la sugerida ya viene elegida), el horario (primer libre, sin horario u otra fecha) y las notas.
3. El botón dice lo que va a hacer: «Agregar a la cola · 3 + 2 en P2 · hoy 10:00».

La ventana aparte **Lanzar impresión de prototipo** ya no existe. Desde Desarrollo y prototipos se abre **Nueva impresión** con **Prototipo** y el proyecto ya elegidos. La tarifa de máquina, que antes solo se podía capturar en Nueva impresión, ahora también se puede capturar al asignar una pieza.

## Cantidades

- Cada cantidad lleva un ícono: unidades, extra, duración, gramos y tarifa.
- **Registrar avance** tiene atajos **+1** y **Todas**, y dice cuánto suma o corrige ese registro frente a lo ya registrado.

## Orden de las pantallas

- **Cola de producción**: arriba la barra de vistas (Operar, Asignar, Calendario, Tabla) junto a **Nueva impresión**. Debajo, la búsqueda y los filtros, y luego el estado. **Por resolver** se abre solo cuando hay algo que frena el taller (una impresión pasada de su fin, horarios encimados o inicios vencidos). Si no, queda plegado con su cantidad.
- **Pedidos**: los botones de crear van a la derecha. Cada tarjeta muestra el estado, la prioridad y la entrega en una sola fila (la fecha completa aparece al pasar el cursor) y un resumen de productos, revisiones y piezas en una línea, con **Abrir** y **Seguimiento** juntos.
- **Detalle del pedido**: una barra superior con **Todos los pedidos** a la izquierda y **Agregar producto** y **Más acciones** a la derecha. El aviso de piezas en inventario indica de qué producto es cada pieza.

No requiere migración de la base de datos.
