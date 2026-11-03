# Tablero, fotografías y navegación · v0.25

En Pedidos, **Tablero** permite arrastrar tarjetas entre columnas. También puedes elegir una etapa y pulsar **Mover** en cada tarjeta, útil en móvil o con teclado. **Tarjetas**, **Lista** y **Tabla** conservan otras formas de consultar y operar.

## Mover un pedido

- **Planificar → Producir:** selecciona el trabajo que empieza ahora y confirma su inicio. Primero debe existir un trabajo asignado. La disponibilidad de la máquina se valida al guardar.
- **Producir → Preparar:** registra las unidades buenas desde el detalle o la cola de producción. Al completar todas las piezas el pedido cambia de etapa automáticamente. Arrastrar no inventa unidades terminadas.
- **Preparar → Salida:** confirma que revisaste todos los productos y la revisión final; en pedidos de cliente confirma también empaque y salida preparada. Los lotes destinados a stock necesitan revisión, sin empaque o despacho.
- **Salida → Preparar:** deja pendiente la salida preparada; en lotes de stock deja pendiente la revisión final. Conserva cantidades y trabajos.
- **Salida → Entregados:** confirma la entrega o liberación a stock. El pedido queda en el histórico de solo lectura y se aplican las reservas de inventario según su destino.

Antes de guardar se cotejan otra vez los datos del pedido. Si otro usuario o ventana modificó productos, cantidades, revisiones o trabajos, actualiza el tablero. Cada confirmación guarda un evento en el historial y una solicitud única para evitar duplicados.

Los bloqueos se resuelven en el detalle. Para deshacer avances de producción, corrige el trabajo correspondiente: mover una tarjeta no borra producción registrada.

## Fotografías

En **Inventario → Existencias**, selecciona una referencia y pulsa **Agregar foto**. La vista **Galería** permite reconocer las piezas por imagen y abrir su gestión. Usa **Cambiar foto** para reemplazarla o quitarla desde el diálogo.

En **Catálogo y recetas** puedes subir fotografías de productos, incluso antes de tener existencias. En **Piezas reutilizables → Fotografía de una pieza** puedes guardar una imagen compartida. Aparecerá en las referencias de inventario vinculadas a esa pieza, salvo que tengan una foto propia.

Se aceptan JPG, PNG y WebP de hasta 10 MB y 24 megapíxeles. La imagen se orienta, se ajusta a un máximo de 1600 px y se guarda como JPG o PNG. Las fotos permanecen dentro de la base de datos y se incluyen en **Crear respaldo**. Subir o cambiar fotos no registra entradas ni altera cantidades, precios o costos.

## Interfaz

La paleta usa azul petróleo para acciones, fondos minerales claros y una barra lateral oscura. Rojo indica problemas, ámbar atención y verde disponibilidad o salida. Los accesos **Ir directamente a…** llevan a pedidos, existencias, gastos y tesorería. Las pestañas de catálogo conservan la selección durante la sesión.

Reinicia NIMUS después de instalar la actualización para cargar el nuevo tema y los módulos del tablero.
