# v0.39 · Fabricación e insumos separados

La barra de **Fabricación** cuenta las piezas pendientes de producir del pedido y las unidades buenas registradas en sus trabajos. Cable, foco, empaque y otros componentes de la receta cuyo abastecimiento sea **Comprar** aparecen en **Insumos**, con cantidades necesarias, cubiertas y por reservar.

Ejemplo: dos lámparas requieren ocho piezas impresas y seis insumos comprados. Al terminar las ocho impresiones, Fabricación indica **8/8 · 100%**, aunque todavía falten seis insumos. Si los seis insumos se reservan primero, Fabricación sigue en **0/8 · 0%**.

Las piezas impresas que ya existían y fueron reservadas para el pedido aparecen como **De inventario**. Solo los faltantes planificados para fabricar forman parte de la barra. Cuando todo se cubre con existencias, se muestra **Sin fabricación requerida**, sin una barra de 0/0. Los productos manuales sin despiece siguen pendientes de definición.

## Operación diaria

1. En **Pedidos**, consulta la fabricación y el indicador de insumos en el tablero, tarjetas o lista. La tabla tiene columnas independientes para fabricación, piezas por fabricar e insumos por reservar.
2. Al resolver la fabricación, el pedido pasa a **Preparar**. Si faltan insumos, el siguiente paso es **Gestionar insumos**, que abre su pestaña dentro del mismo pedido.
3. En **Insumos**, revisa las cantidades y pulsa **Reservar insumos disponibles**. El botón asigna existencias físicas disponibles; no recibe compras ni registra impresiones. Si faltan existencias, abre Inventario para registrar su llegada o dar seguimiento a su pedido de compra.
4. Completa ensamble, revisión y preparación. **100% de fabricación no significa pedido entregable**: deben estar cubiertas todas las necesidades y satisfechos los controles de salida.

El filtro **Atención → Insumos pendientes**, el resumen de **Hoy** y **Notificaciones** permiten ubicar esos pendientes. Las cantidades de producción de Hoy excluyen los insumos comprados.

## Datos y compatibilidad

La clasificación usa el abastecimiento del catálogo y la receta; no adivina por el nombre del componente. Los despieces manuales siguen representando trabajos por fabricar. La separación es de lectura y no reclasifica registros históricos ni modifica cantidades, movimientos, reservas, costos, ventas o pagos existentes. Las cifras internas de cobertura completa se conservan para las validaciones de entrega y costos. No requiere migración de la base de datos (esquema 23).
