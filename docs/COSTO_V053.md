# v0.53 · Costo de impresión capturado una sola vez

## Al asignar una pieza (y en Nueva impresión, inventario y prototipos)

El bloque de la impresión pide, en una línea:

- **Duración** (h y min)
- **Filamento · g**
- **Filamento · MXN/kg**: viene lleno con el precio del carrete registrado en Filamento y consumibles. Si el filamento no está registrado, viene con el **promedio de 380 MXN/kg** (≈ 0.38 MXN por gramo). Se puede cambiar ahí mismo.
- **Máquina · MXN/h**: opcional. En 0, la impresión cuesta solo su filamento.

Debajo se ve el costo en vivo. Por ejemplo: **Costo de impresión $45.60** · 120 g × $380.00/kg.

## Al terminar

Ya no hay un «estimado» y luego un «real». Lo capturado al asignar **es** el costo de la impresión:

- Una impresión terminada cierra su costo sola, con esos gramos, esa duración y esas tarifas.
- Desaparecen el aviso «Costeo pendiente» y el «Costeo provisional» por impresiones sin confirmar. Solo quedan cuando faltan los gramos o cuando una falla pide revisar el consumo.
- El antiguo botón «Costo real» ahora se llama **Corregir costo** y es opcional: sirve solo si algo cambió (por ejemplo, una reimpresión con merma).

## Reglas

| Dato | Regla |
|---|---|
| Precio del filamento | El capturado al asignar. Si no hay, el del carrete registrado. Si tampoco hay, 380 MXN/kg. |
| Tarifa de máquina | Vacía o 0 significa sin costo de máquina (antes dejaba el costo como desconocido). |
| Tiempo | La duración capturada. Una corrección manual la reemplaza. |
| Gramos | Los capturados. Una corrección manual o una falla los reemplazan. |

Las impresiones anteriores sin precio de filamento se costean con el promedio de 380 MXN/kg cuando tienen gramos.
