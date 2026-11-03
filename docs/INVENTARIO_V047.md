# v0.47 · Inventario más claro y disponibilidad en el pedido

Cambia cómo se cuenta y se nombra el inventario, y agrega al pedido una vista para saber qué piezas ya existen. Las reglas y los datos siguen iguales.

## Inventario

- **Un solo conteo, de izquierda a derecha:** **Disponibles** + **Reservadas** = **En taller**. Después van **En clientes B2B** (ya no cuentan en el taller) y **En camino** (excedente de impresiones que aún no terminan). Cada cifra explica en su ayuda qué incluye.
- La tabla de piezas muestra **Libres**, **Reservadas**, **En taller** y **B2B**. La ficha repite los tres conteos y trae la tabla **Por distribuir / Almacén** a la vista, sin abrir ventanas. El popover queda solo para la referencia y el vínculo al catálogo.
- **Piezas iguales se distinguen por su modelo:** la tabla tiene una columna **Modelo** (la variante de la pieza del catálogo, como CIRRUS, CUMULO o STRATO; en piezas sin catálogo, el producto para el que se imprimieron). Ese modelo también aparece junto al nombre en la ficha, la galería, las reservas, los clientes B2B y los movimientos («PANTALLA · CIRRUS»), y la búsqueda lo encuentra.
- Cada pantalla lleva su nombre y una línea que dice para qué sirve:

| Pestaña | Encabezado |
|---|---|
| Existencias | Piezas en inventario · N referencias; En camino |
| Filamento y consumibles | Filamento y consumibles |
| **Compras** (antes Pedidos) | Compras de piezas, insumos y filamento |
| Bases por color | Bases por color |
| **Reservas y clientes** (antes Reservas y Clientes B2B) | Reservas por pedido; Clientes B2B |
| Movimientos | Movimientos de inventario |
| Reposición de insumos | Reposición de insumos |

«Pedidos» se llamaba igual que la pantalla de producción; por eso ahora es **Compras**. Reservas y clientes B2B comparten pestaña, porque las dos responden a «qué piezas ya tienen destino». Los enlaces y avisos que apuntaban a los nombres anteriores siguen funcionando.

## Pedido: disponibilidad contra inventario

En **Producción** hay una vista nueva, **Inventario** (con la cantidad que se puede tomar, por ejemplo «Inventario · 2»). Muestra cada pieza del pedido contra lo que hay:

- Arriba, cuatro cifras: **Necesarias**, **De inventario** (ya tomadas), **Por asignar** y **Libres ahora**.
- Una fila por pieza, de lo más accionable a lo menos, con su estado:

| Estado | Significa |
|---|---|
| Disponible | El inventario cubre todo lo que falta asignar |
| Parcial | Cubre una parte |
| En camino | Solo viene como excedente de otra impresión |
| Imprimir | Sin inventario: hay que imprimirla |
| Asignada | Ya tiene impresión |
| Cubierta | Salió completa del inventario |

- Cada fila dice cuánto necesita, cuánto es de inventario, cuánto tiene impresión y cuánto falta, y **dónde** está (por ubicación y de qué modelo viene). **Tomar N** abre la ventana de siempre solo con esa pieza.
- En la vista **Piezas**, una pieza por asignar sin inventario ahora lo dice («Sin inventario: hay que imprimirla»), en lugar de no mostrar nada.

### Flujo de cada pieza

Cada fila tiene una barra con las unidades del pedido repartidas por etapa: **de inventario → terminadas → en curso → en cola → sin asignar**. Debajo, lo que hay físicamente: **En taller N · libres · reservadas**. Cuando algo aún se imprime para inventario, la fila lo dice (**N por entrar**, con su impresión, máquina, estado y hora de término), venga de un excedente de otro pedido o de un stock directo.

### Devolver a inventario (desasignar)

Si tomaste piezas del catálogo de inventario, el botón **Devolver N** las desasigna: la reserva se libera, las piezas vuelven a estar libres para otros pedidos y el pedido las tiene otra vez **por asignar** para imprimirlas. Puedes devolver solo una parte.

Las piezas libres (sin catálogo) que ya se tomaron de inventario no se pueden devolver: su consumo queda ligado al trabajo en el historial de movimientos, que no se borra. La fila lo avisa; para corregirlo, registra una entrada manual en Inventario.

## Piezas del pedido en tarjetas

En la vista **Piezas**, cada pieza es una tarjeta (tres por fila) con su nombre, material, una barra de estado, dónde están las unidades (inventario o en camino) y su acción: **Asignar N**, **Terminada** o **Cubierta**. Las impresiones de la pieza van plegadas en la propia tarjeta (**N impresiones**) y se abren solas si algo está imprimiendo.

## Inventario: lo que está por entrar

En **Existencias**, el bloque **Por entrar a inventario** reúne lo que aún se imprime para el inventario: el excedente de pedidos y el **stock directo**. Cada fila tiene su fase: **Por imprimir**, **Imprimiendo** o **A punto de salir** (imprimiendo y con término en las próximas 2 horas), con su máquina y hora de término. La cifra **En camino** de arriba suma lo mismo.

No requiere migración de la base de datos.
