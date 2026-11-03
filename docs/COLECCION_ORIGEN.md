# Colección Origen · v0.31

## Hacer un pedido por modelo y color

Pulsa **Crear pedido** en Colección Origen, o **Desde receta** en Pedidos/Hoy. Se abre **Venta y pedido**. Elige:

1. **Modelo de lámpara:** Cirrus, Cúmulo o Strato.
2. **Color de base:** beige, gris niebla o negro noche.
3. **Cantidad** y **Agregar al pedido**. Repite para otros modelos y colores del mismo cliente.
4. **Pedido operativo**, **Cotización** o **Venta confirmada**. Completa cliente y, para documentos comerciales, los precios acordados.

El carrito permite cambiar cantidades, duplicar y quitar combinaciones. Su resumen reparte el stock compartido entre todas las lámparas sin contarlo dos veces. Consulta [el flujo comercial](FLUJO_COMERCIAL.md) para autorizaciones, pagos, entrega y cancelaciones.

Los nueve cruces modelo/color están configurados como recetas internas de componentes. La selección de pedido se organiza por modelo y variante; no requiere buscar productos por sus nombres completos. Los artículos con otras recetas siguen en **Otros productos**.

Todos los colores se pueden pedir aun sin stock. La selección informa la capacidad con componentes libres y el estado para la cantidad elegida:

- **Para ensamblar:** alcanza la pantalla, BASE/CAP/TAPA y los tres insumos.
- **Completar insumos:** alcanzan las piezas impresas; falta cable, foco o empaque.
- **Por fabricar:** falta al menos una pieza impresa; el plan también muestra las compras necesarias.

Un **juego de base libre** requiere una BASE, un CAP y una TAPA del mismo color y material. Tener solo bases no completa el juego. Se excluyen las reservas de otros pedidos y las unidades asignadas a clientes B2B.

El plan distingue componentes **A reservar**, **A fabricar** y **A comprar**. Confirmar fija la receta, reserva piezas libres y crea producción solamente para las piezas impresas faltantes. Si las existencias cambian, usa **Actualizar plan** antes de confirmar. Los insumos comprados no generan trabajos de impresión.

Los colores comparten pantalla e insumos: sus capacidades no se suman. La disponibilidad indica capacidad para completar y ensamblar; el ensamble físico y la revisión se confirman en el pedido.

La actualización completa únicamente las recetas faltantes. Conserva las recetas previas y los movimientos de pedidos, inventario y tesorería. No crea existencias ni pedidos al registrar las combinaciones.

## Crear una receta con selección continua

Entra en **Crear receta**. El configurador muestra las selecciones a la izquierda y **Tu receta** a la derecha. Puedes elegir pantalla y color de base en cualquier orden; los cambios actualizan el resumen inmediatamente.

1. **Pantalla:** elige Cirrus, Cúmulo o Strato. Si un modelo tiene varios acabados, aparecerá un selector adicional de material/color.
2. **Base y color:** elige beige, gris niebla o negro noche. BASE, CAP y TAPA se incorporan con el mismo color y material.
3. **Insumos:** cable, foco y empaque se completan automáticamente cuando solo hay una referencia de cada uno. Usa **Elegir especificaciones** para cambiar las opciones cuando existan otras.

El resumen muestra los siete componentes y las unidades libres en inventario. **Costo de componentes** aparece completo cuando los siete tienen costo capturado; ensamble y otros directos se revisan en Costos después de publicar. No es una estimación de utilidad ni una confirmación de ensamble físico.

Puedes escribir un nombre propio o usar el que se genera a partir de pantalla y color. Pulsa **Publicar receta** para guardar la combinación. Si ya existe, el configurador muestra **Abrir receta existente**.

El borrador se conserva al cambiar de pestaña o sección durante la misma sesión. **Continuar receta** lo recupera. Cerrar o reiniciar la sesión puede perderlo; **Empezar otra receta** limpia la selección actual. No se escriben recetas ni movimientos de inventario mientras seleccionas.

Desde **Componentes**, las tarjetas **Usar esta pantalla** y **Usar este color** continúan un borrador nuevo conservando las demás selecciones. Si estabas editando una receta publicada, preparan otra combinación para conservar la identidad anterior.

## Modelos y colores

Hay **tres modelos de pantalla: Cirrus, Cúmulo y Strato**. Comparten por ahora el material PLA MATTE IVORY y su color. El material no es otro modelo de pantalla.

Hay **un modelo de base: Base Origen**, con **tres variantes de color: beige, gris niebla y negro noche**. Elegir el color incorpora BASE, CAP y TAPA compatibles. Cambiar de color conserva el modelo de base.

Una lámpara publicada combina un modelo de pantalla, un color de base y sus insumos. El número de combinaciones publicadas es independiente del número de modelos. Strato aparece aunque todavía no tenga una lámpara publicada: elige su modelo y color en **Crear receta**.

La referencia genérica de pantalla «PLA IVORY», sin forma definida, se retira del catálogo activo, los selectores y las nuevas operaciones. Sus recetas y movimientos anteriores se conservan. El material PLA MATTE IVORY sigue disponible en las tres pantallas válidas.

## Una lámpara completa

Cada receta incluye una unidad de cada componente: **pantalla, base, CAP, tapa, cable, foco y empaque**.

- La pantalla se define por modelo/forma, material y color. Se comparte entre variantes de base compatibles. Se pueden crear nuevas formas y colores.
- Una variante de color del modelo de base agrupa BASE, CAP y TAPA del mismo color y material. Elegir el color incorpora las tres piezas; sus existencias físicas siguen contándose por separado.
- Cable, foco y empaque son insumos comprados. Pueden compartirse entre modelos y tener otras especificaciones en el futuro.

Los tres colores se vinculan a las piezas existentes bajo el mismo modelo de base. No se crean existencias por definir un componente.

## Pantalla de operación

**Colección Origen** reúne siete áreas:

- **Recetas:** combinaciones publicadas, composición de siete componentes, pedido, disponibilidad y costos.
- **Venta y pedido:** carrito de combinaciones, precios y condiciones comerciales con resumen conjunto.
- **Crear receta:** configurador continuo y borrador de sesión, con resumen de la selección.
- **Componentes:** tarjetas de pantallas y colores de base, más gestión de insumos. Agregar color de base crea juntas BASE, CAP y TAPA. Cable, foco y empaque conservan entradas físicas, fotografía y costo unitario.
- **Inventario:** existencias físicas, libres y reservadas de todos los componentes, incluidos los que todavía tienen saldo cero. Comparte el mismo registro de movimientos del inventario general.
- **Pedidos:** faltantes de fabricación o de compra y reserva de insumos recibidos.
- **Otros artículos:** productos de Origen que usan composiciones diferentes; se gestionan con el catálogo general.

Para otra combinación de pantalla/base usa **Crear otra combinación** en una receta publicada. Para cambiar sus especificaciones usa **Editar receta**. Pantalla/modelo y color de base se conservan al editar; para otros usa una combinación nueva. Los cambios crean versiones; los pedidos anteriores conservan la receta que usaron. Catálogo abre el mismo configurador para las lámparas de Origen.

## Pedir, fabricar y abastecer

El pedido multiplica los siete componentes por la cantidad de lámparas. Reserva las existencias libres y crea piezas de producción solo para lo que falta fabricar. Los insumos faltantes aparecen en **A comprar** y no generan trabajos de impresión.

Al recibir una compra, usa **Registrar entrada física**. Después, en el pedido o en **Colección Origen → Pedidos**, pulsa **Reservar insumos disponibles**. La entrada registra inventario; los gastos y pagos se capturan en sus secciones correspondientes.

Terminar las piezas impresas no completa el pedido si faltan cable, foco o empaque. Una vez cubiertos los componentes, confirma el ensamble/revisión de las lámparas y la preparación antes de entregar. Para lotes de stock se requiere revisión; su cierre libera componentes a Almacén.

**Lámparas completables** expresa capacidad basada en componentes libres para ensamblar. No es una cantidad de productos ya ensamblados. Los modelos comparten stock, por lo que sus capacidades no se suman.

## Costos

Cable, foco y empaque se costean como componentes de la receta. Sus valores no se vuelven a sumar como adicionales. Ensamble/mano de obra y otros directos permanecen en costos adicionales.

Las referencias anteriores de kit eléctrico, foco y empaque se conservan como estimaciones visibles una sola vez. El costo completo permanece pendiente hasta confirmar el costo unitario de los nuevos insumos, especialmente el cable, cuya referencia previa era un kit eléctrico. Usa **Costear componente** para capturar el importe real.

## Actualización

La actualización añade nuevas versiones completas a las lámparas existentes que tienen una composición inequívoca de pantalla + base + CAP + tapa. Conserva todas las versiones anteriores, pedidos, finanzas y movimientos de inventario. No crea saldos físicos, compras ni pagos.

Esta mejora de interfaz no cambia los registros existentes. Reinicia NIMUS después de actualizar para cargar el configurador.
