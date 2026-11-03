# v0.48 · Entornos, Colección Origen e inventario separado

Esta versión ordena el sistema por entornos y quita pasos repetidos. Las funciones son las mismas que antes; solo cambia dónde está cada una.

## Tres entornos con su propia paleta

| Entorno | Acento | Dónde |
|---|---|---|
| **Taller** | Turquesa | Hoy, Pedidos, Cola, Desarrollo, Control, Inventario, Catálogo, Máquinas |
| **Negocio** | Azul marino | Ventas, Cotizaciones, Tesorería, Gastos, Socios, Costos |
| **Colección Origen** | Negro con dorado | La página de Colección Origen |

- **Página:** usa el color del área a la que pertenece. Botón principal, pestañas, controles seleccionados, enlaces y anillo de foco cambian juntos.
- **Menú lateral:** sigue el selector **Taller / Negocio**. Al cambiarlo, el fondo pasa de petróleo a azul marino.
- **Colección Origen:** botones negros con letra dorada, pestañas y selección en dorado, una línea dorada bajo el título y métricas con borde dorado.
- **Paletas en el código:** están en `views/theme.py` (`PALETTES` y `SIDEBARS`).

## Colores en la cola y en los pedidos

| Qué es | Cómo se ve |
|---|---|
| Pedido de cliente | Su propio color (índigo, rosa, oliva, coral, cian, café o pizarra), en el borde y en la etiqueta del código |
| **Colección Origen** | Etiqueta negra con letra dorada y el punto de color del pedido; tarjeta con borde dorado |
| Stock | Azul |
| Prototipo | Violeta |

- **Dónde se ve:** igual en la cola (por máquina, por estado y por «Para qué es»), en el tablero y el detalle de Pedidos, y en las impresiones de cada pieza.
- **Cola:**
  - «Para qué es» tiene un grupo propio, **Colección Origen**.
  - El filtro **Para qué es** incluye **Origen**.
- **Calendario:** tiene **Color por: Estado / Pedido**. Por pedido, cada barra toma el color de su pedido, con Origen en dorado, stock en azul y prototipos en violeta.

### También en Hoy y en Pedidos

- **Hoy:**
  - Las tarjetas de «Pedidos por atender», «Entregar», «Piezas sin asignar» y las impresiones en marcha llevan la etiqueta y el borde del color de su pedido, con Origen en dorado y negro.
  - **Repartir piezas** y **Asignar** abren el pedido en su vista **Asignar** con la pieza ya elegida, igual que la tarjeta de la pieza. Desde ahí también está **Repartir en varias**.
- **Pedidos:**
  - En el tablero, cada tarjeta tiene el borde y la etiqueta del color de su pedido; las de Colección Origen, fondo cálido y etiqueta negra con dorado, con destino «Origen».
  - Las tarjetas, la lista y el detalle usan las mismas etiquetas.

## Piezas por su modelo, no por su material

Una pieza del catálogo se muestra con su modelo: **PANTALLA · CIRRUS**, **PANTALLA · CUMULO**, **PANTALLA · STRATO**, **BASE · BEIGE**. Antes solo decía «PANTALLA» y lo que la distinguía era el material («PLA MATTE IVORY»). El nombre con modelo aparece en todas las pantallas:

- Pedidos: tarjetas, vistas Inventario y Asignar.
- Cola, calendario y Hoy.
- Tomar de inventario.
- Inventario y Colección Origen → Pedidos.

Las impresiones **Directo a inventario** también se nombran por su modelo. Si se lanzaron desde el catálogo, el modelo sale de esa pieza; si son «Pieza libre», sale del modelo que se escribió. Al capturar una pieza libre cuyo nombre existe en el catálogo por modelo, por ejemplo «PANTALLA», el formulario pide primero **Modelo \*** (CIRRUS, CUMULO o STRATO). La impresión usa esa pieza del catálogo y no se agrega a la cola sin modelo.

El material sigue en su columna o al lado, como dato del filamento para elegir impresora. En la base de datos el nombre guardado no cambia: el modelo sale de la variante de la pieza en el catálogo.

## Documento de cotización (PDF)

La cotización, el recibo de pagos y el comprobante de venta comparten un diseño nuevo en hoja A4. Se generan igual que antes: se descarga el archivo y se imprime o guarda como PDF desde el navegador.

- **Encabezado** azul marino (el color de Negocio): logotipo a la izquierda; tipo de documento y folio grandes a la derecha. En recibos y ventas, una etiqueta de estado: pagado, parcial, pendiente o cancelada.
- **Franja de datos clave:** emisión, vigencia o vencimiento, número de partidas con unidades y el **total** destacado.
- **Tarjetas de Cliente y Proyecto:**
  - Cliente: contacto, canal y RFC.
  - Proyecto: entrega estimada y responsable.
- **Alcance:** en dos columnas, solo con los datos capturados.
- **Partidas:** tabla con filas alternadas, montos alineados y encabezado que se repite en cada página.
- **Totales:** en una tarjeta con el total en franja oscura. La línea de descuento solo aparece si hay descuento.
- **Contenido opcional:**
  - Precios por volumen en tarjetas.
  - Imágenes de prototipo en dos columnas, solo en la cotización.
  - Condiciones de pago, notas y condiciones comerciales en tarjetas.
- **Cotización:** cierra con un espacio para **nombre y firma de aceptación del cliente** y la fecha.
- **Pie:** emisor y folio.
- **Al imprimir:** se conservan los colores y se evita cortar tarjetas, filas o totales entre páginas.

## Botones en todo el sistema

- **Formularios:** sus botones (**Guardar**, **Registrar**, **Crear**) ahora se ven igual que los demás. Antes no recibían el estilo.
- **Principal:** relleno con degradado y sombra en el color del entorno.
- **Secundario:** blanco, con borde suave; al pasar el cursor toma el acento del entorno.
- **Terciario:** solo texto en el acento.
- **Deshabilitado:** apagado y sin sombra.
- **Teclado:** anillo de foco visible.
- **Color por intención:** verde (terminar), naranja (pausar o corregir), rojo (eliminar), azul (inventario e iniciar). También aplica dentro de formularios.

## Inventario: general y Colección Origen, cada uno en su lugar

**Inventario** (Taller) es ahora el inventario general: todo lo que **no** es Colección Origen.

- **Pestañas:** Existencias, Filamento y consumibles, Compras, Reservas y clientes, Movimientos.
- **Cifras de arriba:** solo de esa línea.
- **Filtro de línea:** ya no existe.
- **Ir a Origen:** el botón **Inventario Origen** abre el otro inventario.

**Colección Origen → Inventario** reúne todo lo de Origen:

- **Cifras:** Disponibles, Reservadas, En taller, B2B y En camino, solo de Origen.
- **Piezas:** la misma tabla y ficha completa del inventario general: mover o asignar, agregar, pedir, costear, foto y galería, con su propia búsqueda y selección.
- **Bases por color:** viene de Inventario.
- **Insumos y reposición:** viene de Inventario.

Movimientos, compras y reservas son un mismo registro para las dos líneas y se consultan en Inventario.

Una entrada nueva lleva a su página: si registras una pieza de Origen desde Inventario, se abre Colección Origen con esa pieza elegida, y al revés. Los avisos de insumos y los enlaces a «Reposición de insumos» o «Bases por color» abren ahora Colección Origen.

## Redundancias encontradas

### Corregidas en esta versión

1. **Inventario de Origen en dos lugares.** Las piezas de Origen salían en Inventario (con filtro de línea) y en Colección Origen → Inventario, cada lugar con otra tabla y otro formulario. Ahora cada línea tiene un solo lugar.
2. **Paneles de Origen en el inventario general.** Bases por color y Reposición de insumos son solo de Origen; se movieron a Colección Origen.
3. **Tomar piezas de inventario en un pedido.** Había dos lugares con dos botones: el aviso arriba de Producción y la vista Inventario. Ahora solo se toma en la vista Inventario (**Usar inventario** o **Tomar** por fila). El aviso dice cuántas piezas hay y lleva a esa vista con **Revisar inventario**.
4. **«Repartir pendientes» repetido.** Aparecía también en la vista Impresiones del pedido. Se quitó: siguen **Repartir piezas** en el encabezado, el de cada producto y la vista **Asignar**.
5. **Dos formularios de entrada.** En Reposición de insumos, **Registrar entrada física** usaba un formulario distinto al de **Agregar inventario**. Ahora es el mismo, y al guardar vuelve a Reposición.
6. **Agregar y pedir.** En la ficha ocupaban dos filas aunque abren el mismo formulario. Ahora van juntos en una fila: **Agregar unidades** y **Pedir**.

7. **Siete caminos para asignar una pieza.** Antes eran: **Repartir piezas**, **Repartir pendientes** de cada producto, **Asignar N** de la tarjeta (su propia ventana), la vista **Asignar**, **Nueva impresión**, **Opciones → Crear un trabajo con fecha y notas** y la vista Asignar de la cola. Ahora una pieza se asigna en un solo lugar, la vista **Asignar** del pedido:
   - **Asignar N** en la tarjeta de la pieza abre esa vista con la pieza ya elegida (y quita el filtro de material si lo hubiera).
   - Ahí se elige impresora, unidades, extra para inventario, duración, filamento, horario y notas.
   - Para varias impresoras a la vez, **Repartir en varias** (junto a la pieza) abre el reparto con la sugerencia por carga y filamento.
   - Se quitó **Opciones → Crear un trabajo con fecha y notas**: la vista Asignar ya pide horario y notas.
   - **Repartir piezas** del encabezado y **Repartir pendientes** de cada producto siguen como atajos para asignar todo junto.

### Detectadas, por decidir

- **Otro formulario de entrada en Componentes.** Componentes → Insumos tiene su propio **Registrar entrada física**. Propuesta: usar el formulario común.
- **Pedidos Origen en dos listas:** Pedidos y Colección Origen → Pedidos. Esta última solo agrega **Reservar insumos**. Propuesta: un filtro **Origen** en el tablero de Pedidos y llevar «Reservar insumos» a la pestaña Insumos del pedido.
- **Saldos repetidos en Componentes.** Componentes repite los saldos (libres y reservadas) que ya muestra Inventario. Propuesta: que Componentes solo defina modelos, colores e insumos.

No requiere migración de la base de datos.
