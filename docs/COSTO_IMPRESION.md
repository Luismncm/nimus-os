# Costo de piezas impresas · v0.37

Las pantallas, bases, CAP y tapas de lámpara pueden costearse mediante **Impresión por parámetros**:

**Costo por pieza = gramos × precio por gramo + tiempo en horas × tarifa por hora.**

Ejemplo: 100 g × $0.44/g + 2 h 30 min × $20/h = $44 de material + $50 de tiempo = **$94 MXN por pieza**.

## Captura

- Colección Origen → Componentes → Pantallas → **Costear impresión**.
- Colección Origen → Componentes → Base y colores → **Costear base, CAP o tapa**.
- Inventario → ficha de la pieza → **Costo de esta pieza → Calcular / editar costo**.
- Receta → Costos → **Editar costo de pieza**. Elige **Impresión por parámetros** para cambiar desde un método anterior.

Selecciona **Por pieza** o **Por lote** antes de llenar los parámetros. Para un lote, captura sus gramos totales, su tiempo total y cuántas piezas produce. El sistema reparte material y tiempo una sola vez entre esas piezas. Los costos adicionales opcionales se capturan por pieza.

El precio por gramo admite cinco decimales. La tarifa de tiempo se captura en MXN/h y la duración en horas y minutos. Incluye energía o desgaste en esa tarifa si corresponde; evita duplicarlos en los adicionales.

**Calcular costo** muestra material, tiempo y total por pieza sin guardar. **Guardar costo de pieza** crea una versión nueva y actualiza el costo estimado de las recetas que usan el componente. Deja vacíos los datos desconocidos: el total permanece pendiente hasta completarlos; cero representa un valor confirmado de cero.

Los cables, focos y empaques comprados conservan su costo de compra por unidad. Los métodos anteriores siguen disponibles. Al cambiar desde un costo fijo previo, revisa el adicional por pieza antes de guardar para evitar sumar dos veces conceptos incluidos en la tarifa horaria.

El inventario físico no cambia al guardar un costo. Las ventas ya costeadas conservan su versión histórica hasta que se actualice su costeo explícitamente. Los costos unitarios se redondean a centavos; el total del lote mostrado multiplica ese costo unitario por sus piezas.

No requiere migración ni modificación de los registros existentes: esquema 22.
