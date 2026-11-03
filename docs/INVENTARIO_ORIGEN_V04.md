# Inventario de Colección Origen · NIMUS v0.4

## Flujo

**Pedido de producción → item marcado Colección Origen → piezas impresas → inventario por asignar → cliente B2B o stock.**

En el formulario del item, activa **Producir para inventario de Colección Origen**. Usa como nombre el modelo de lámpara; utiliza el mismo nombre en los lotes posteriores. El inventario distingue modelo, pieza, material y proceso (Impresión 3D o Resina).

Registra las unidades buenas desde **Avance** o **Terminar**. Entran al inventario automáticamente, incluidas las de lotes parciales. Pausar, reanudar, actualizar una pantalla o guardar de nuevo el mismo avance no suma piezas otra vez.

Ejemplo: 10 bases impresas, 4 asignadas a Tienda Norte, 3 a Stock. Quedan 3 en Colección, 3 en Stock y 4 asignadas a B2B. Esas cuatro son una asignación; la app no afirma que ya estén enviadas o facturadas.

## Nueva vista

- **Inventario:** saldos por modelo/pieza/material/proceso, filtros y CSV. Selecciona la pieza y pulsa **Asignar / trasladar piezas**.
- **Asignaciones B2B:** cantidades netas por cliente y componente.
- **Movimientos:** entradas, correcciones de producción, traslados, asignaciones y reversiones. Incluye el trabajo y pedido que originaron cada entrada y un CSV completo.

Puedes mover Colección ↔ Stock y asignar a B2B desde cualquiera de los dos. Nunca se permite gastar un saldo que no existe. Los nombres de clientes se agrupan sin distinguir mayúsculas o espacios repetidos.

## Correcciones

Los movimientos se conservan. Una reversión devuelve **toda** la cantidad del traslado/asignación original y deja una nueva fila con el motivo. Para ajustar una cantidad parcialmente, revierte la asignación completa y crea la correcta. Si el destino ya no tiene saldo, deshaz primero las operaciones posteriores.

Para reducir unidades buenas, usa **Más → Editar trabajo**. La app descuenta de Colección dentro de la misma transacción que corrige el avance. Si no hay suficiente porque ya se dispersaron, regresa esas piezas antes. Los saldos del mismo modelo/pieza/material/proceso son compartidos entre lotes; no se hace trazabilidad física individual de cada unidad.

El modelo/destino de un item y el nombre/material/proceso de una pieza con producción se mantienen para conservar la identidad del inventario. Cantidades y notas siguen editables según las reglas existentes. Los pedidos entregados conservan su histórico; las asignaciones de su inventario pueden continuar sin modificar ese pedido.

## Datos y actualización

Esquema SQLite 2 → 3: columna `items.collection`, catálogo `inventory_skus` y movimientos `inventory_movements`. Migración aditiva con respaldo previo y rollback si ocurre un error. No se reclasifican items ni se cargan cantidades históricas automáticamente.

Unidades planeadas, fallidas, ensamble y empaque no generan ingresos. Esta versión no representa lámparas completas ensambladas, inventario general de materia prima ni facturación.

La carpeta del Escritorio conserva su nombre `NIMUS_Production_v0.3` para mantener sus accesos; el contenido y la interfaz están actualizados a **v0.4**. Ejecuta `INICIAR_WINDOWS.bat` y abre http://127.0.0.1:8502.

59 pruebas cubren producción existente, migración desde esquemas anteriores, recepción incremental, separación de materiales, asignación concurrente, reversiones, correcciones atómicas, duplicados y formularios de la vista.
