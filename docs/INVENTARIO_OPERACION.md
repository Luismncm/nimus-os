# Inventario · v0.24

Inventario controla **piezas y componentes físicos**. El catálogo describe esas piezas y las recetas indican cuántas necesita cada producto. Tener una receta no crea existencias.

## Leer el resumen

| Indicador | Significado |
|---|---|
| En taller | Piezas físicas por distribuir y en almacén. Incluye las reservadas. |
| Disponibles | Unidades libres para mover o reservar. |
| Reservadas | Apartadas para pedidos. Ya están incluidas en En taller; no se suman otra vez. |
| En clientes B2B | Piezas asignadas a clientes, mostradas aparte del taller. No confirma envío ni facturación. |

Los números cuentan componentes, no lámparas completas. Por ejemplo, 1 base + 1 pantalla + 1 tapa son 3 piezas.

## Existencias

Busca por pieza, material, modelo o folio. Usa **Mostrar** para consultar disponibles, referencias con reservas o referencias sin saldo. **Modelo y línea** filtra Origen o General. **Limpiar filtros** vuelve a la consulta completa.

La tabla breve muestra piezas libres, reservadas y en B2B. Selecciona la referencia desde **Pieza seleccionada** para mover/asignar, agregar unidades o consultar sus ubicaciones. Los indicadores superiores abarcan todo el inventario; tabla y ficha respetan los filtros.

**Desglose y referencia** explica las ubicaciones de la pieza y su vínculo de catálogo. Una pieza compartida puede utilizarse en varias recetas. **Ver desglose completo y exportar** incluye referencias, procesos, saldos físicos por ubicación y CSV.

## Entradas y movimientos

**Agregar inventario** registra unidades físicamente contadas. Selecciona una referencia existente, una pieza del catálogo o una referencia nueva, y captura cantidad, ubicación y motivo. Al guardar, el sistema enfoca la pieza registrada y limpia los filtros para mostrarla.

En pantalla, **Por distribuir** corresponde a la ubicación histórica **Colección**, y **Almacén** corresponde a **Stock**. Se conservan las mismas ubicaciones en la base y exportaciones.

**Mover o asignar** selecciona origen, destino y cantidad. Solo admite unidades libres. Las entradas suman cantidades; los traslados cambian su ubicación y las asignaciones B2B registran el cliente.

## Reservas e historial

**Reservas** muestra las piezas apartadas y permite abrir su pedido. **Clientes B2B** muestra asignaciones vigentes por cliente. **Movimientos** presenta fecha, cantidad, trayecto y estado; sus detalles contienen referencias y correcciones.

Las reversiones conservan el movimiento original. Las unidades de producción se corrigen desde su trabajo. Esta actualización de interfaz conserva existencias, reservas, documentos y movimientos.

## Paleta de interfaz

NIMUS usa superficies marfil, texto grafito, acciones bronce y navegación oscura. Verde, azul, ámbar y rojo mantienen significado de estado con tonos discretos. El tema nativo se aplica a botones, formularios, tablas y gráficos, y utiliza fuentes disponibles sin descargas externas.
