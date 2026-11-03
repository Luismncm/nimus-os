# v0.44 · Pedidos de inventario vinculados a Gastos

Al crear un **Pedido** desde Inventario, Colección Origen o Bases por color, captura el **Total del pedido · MXN** y elige **Por pagar** o **Ya pagado**. El importe es por toda la compra, incluidos los cargos que correspondan; no es el costo por unidad.

- **Por pagar:** crea un gasto pendiente. Puedes seleccionar una cuenta prevista; no registra una salida de dinero. El compromiso se incluye en Gastos y en Después de gastos.
- **Ya pagado:** crea el gasto y su pago en una cuenta activa existente. Requiere cuenta y forma de pago. Puedes indicar la fecha del pago; no admite pagos futuros.

Pedido, gasto, vínculo y pago inicial se guardan juntos. Si algún dato falla, no queda una compra incompleta ni un pago aislado. Reintentar no crea otro gasto. La cuenta se distingue entre banco, efectivo y pasarela como en el resto de Tesorería.

## Recepción y pagos posteriores

El inventario sigue ingresando únicamente al confirmar la recepción física. Puede llegar por partes. Recibir o revertir una entrada de inventario no crea otro gasto ni otro pago.

En Inventario → Pedidos se muestran por separado el estado de recepción y el del gasto, con total, pagado y pendiente. **Registrar pago** usa el formulario habitual, incluidos abonos. **Abrir gasto** permite consultar comprobantes, editar, conciliar o adjuntar factura/PDF. Desde el detalle del gasto, **Abrir pedido de compra** vuelve al pedido correspondiente.

Un pago posterior actualiza automáticamente el gasto vinculado y el saldo en cuentas. Después de gastos descuenta sólo el pendiente actual: no vuelve a restar lo que ya fue pagado.

## Pedidos anteriores

Los pedidos existentes sin precio conservan sus unidades e historial. No se inventan importes ni se convierten automáticamente en gastos. **Vincular gasto** permite crear su gasto con el importe real o seleccionar **Usar gasto existente** cuando ya fue capturado. Un gasto sólo puede vincularse a un pedido de inventario; enlazarlo no repite sus pagos.

Las entradas físicas destinadas a conteos iniciales o ajustes conservan su comportamiento: contar existencias no genera compras o gastos ficticios.

## Cancelaciones

Si cancelas todas las unidades pendientes de una compra sin recepción y sin pagos, su gasto pendiente se cancela en la misma operación. Se conserva el historial.

Si hubo unidades recibidas o pagos, el gasto se conserva. Ajusta el importe real o gestiona la devolución desde su detalle, según corresponda. Cancelar unidades no genera un reembolso automático ni borra salidas de banco o caja.

## Datos

La migración 25 → 26 agrega una tabla de vínculos. Conserva las cuentas, gastos, pagos, inventario, compras y previsiones existentes. Antes de instalar se respaldan código y base de datos, y se verifica que todas las filas previas permanezcan intactas.
