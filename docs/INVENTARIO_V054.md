# v0.54 · Inventario: stock encontrado, iconos y menos pasos

## 📦 Stock encontrado

Es el botón principal de Inventario. Sirve para anotar lo que encuentras en los estantes, **varias piezas a la vez**.

- **Una tabla editable**, con un renglón por pieza:
  - **🧩 Pieza:** se elige por modelo (PANTALLA · CIRRUS, CAP · BEIGE…). 💡 marca las de Colección Origen, 🧩 otras piezas del catálogo y 📦 las referencias creadas en inventario.
  - **🔢 Cantidad.**
  - **📍 Ubicación:** 📥 Por distribuir o 🏬 Almacén.
  - Con «+» se agregan renglones.
- **Motivo:** viene como «Stock encontrado» y se puede cambiar (por ejemplo, «Conteo de inventario» o «Devolución»).
- **Al guardar, todo se registra junto o nada.** Los renglones de la misma pieza y ubicación se suman. Un doble clic no duplica la entrada.
- **Cada renglón queda como entrada manual** en 🧾 Movimientos, así que se puede revertir si hubo un error.
- **«Pieza nueva que no está en la lista»** abre el formulario completo para crear la referencia.

También está en:

- **La ficha de cada pieza**, como **📦 Encontré más**. Abre la misma ventana con esa pieza ya puesta.
- **El inventario vacío**, en Inventario y en Colección Origen.

## Página más simple

- **Acciones de arriba:**
  - 💡 Inventario Origen
  - **Entrada o pedido:** una referencia nueva, filamento y consumibles, o un pedido a proveedor.
  - **📦 Stock encontrado** (principal)
- **Secciones en un solo selector con emojis:** 📦 Existencias · 🧵 Filamento y consumibles · 🚚 Compras · 🔖 Reservas y clientes · 🧾 Movimientos. Solo se construye la sección abierta, así que la página carga más rápido.
- **Ficha de pieza:**
  - Una línea de saldo: 🟢 libres · 🟠 reservadas · 📦 en taller.
  - Una línea de ubicaciones: 📥 Por distribuir … · 🏬 Almacén ….
  - Tres acciones: 🔁 Mover o asignar, 📦 Encontré más y 🚚 Pedir.
  - Antes había tres métricas y una tabla de ubicaciones.
- **Tablas:**
  - Existencias: estado con su color (🟢 Disponible, 🟠 Reservada, 🤝 En clientes, ⚪ Sin saldo) y columnas 🟢 Libres, 🟠 Reservadas, 📦 En taller y 🤝 B2B.
  - Movimientos: tipo (📦 Entrada manual, 🔁 Traslado, 🤝 B2B, ↩️ Reversión…) y trayecto con iconos de lugar.
  - Por entrar a inventario: ⏳ A punto de salir, 🖨️ Imprimiendo y 🕒 Por imprimir.
- **Vista:** 📋 Tabla y ficha o 🖼️ Galería.

## Lo que no cambió

Reservas, traslados, asignaciones B2B, reversiones, pedidos a proveedor, filamento y consumibles, el inventario de Colección Origen y la exportación CSV funcionan igual.
