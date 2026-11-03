# v0.55 · Iconos y emojis en todo el sistema

Un solo vocabulario en [views/emoji.py](../views/emoji.py): el mismo emoji dice lo mismo en todas las páginas.

## Dónde aparecen

- **Estados**, en etiquetas y en cualquier tabla con columna de estado:
  - Impresiones: ⏳ En cola · 🖨️ En producción · ⏸️ Pausado · ⛔ Bloqueado · ✅ Terminado
  - Pedidos: 🕒 Pendiente · 📦 Listo · ✅ Entregado · 🚫 Cancelado · 🔩 Insumos pendientes · 🧩 Componentes pendientes
  - Máquinas: 🟢 Disponible · 🖨️ Imprimiendo · 🔧 Mantenimiento · 🔴 Fuera de servicio
  - Dinero: ✅ Pagado · 🌓 Parcial · ⏰ Vencido · 🟢 Activa · 🚫 Cancelada o Anulado
  - Compras: 📝 Solicitado · 👍 Confirmado · 🚚 En camino · ✅ Recibido
  - Cotizaciones: 📝 Borrador · 📤 Enviada · 🤝 Aceptada · ❌ Rechazada · ⏰ Vencida
- **Pestañas** de todas las páginas, por ejemplo:
  - Gastos: 🧾 Movimientos · 💸 Por pagar · 🔁 Costos recurrentes · 📊 Resumen
  - Ventas: 🧾 Registro de ventas · 💰 Cobros del período
  - Tesorería: 🔄 Cobrar / pagar · 👥 Socios · 🏦 Cuentas
  - Colección Origen: 📖 Recetas · 🛒 Venta y pedido · ✏️ Crear receta · 🧩 Componentes · 📦 Inventario
  - Pedido: 🏭 Producción · 🔩 Insumos · 🧰 Preparación · 📁 Documentos · 🕘 Historial
- **Selectores y filtros** (23):
  - Pedidos: 🟢 Activos · ✅ Entregados · 🚫 Cancelados
  - Hoy: 🛠️ Trabajos · 🖨️ Máquinas · 🧩 Piezas sin asignar · 🛒 Por pedir · 🚚 Por recibir
  - Compras: 📂 Abiertos · ✅ Recibidos
  - Formularios: ➕ Nueva · ♻️ Reutilizar · 🔀 Repartir en varias
- **Títulos de sección:** los 21 que no tenían icono ahora lo tienen (presupuesto, socios, costos, gastos, tesorería, factura…).
- **Inventario** (v0.54): 📦 🧵 🚚 🔖 🧾 en secciones; 🟢 🟠 🤝 ⚪ en saldos; 📥 🏬 en ubicaciones.

## Regla técnica

Los emojis se agregan solo en lo que se muestra. Los valores guardados de pestañas y selectores siguen siendo la palabra sola (por ejemplo, «Movimientos»):

- Las pestañas reciben su emoji por CSS.
- Los selectores lo reciben con su formato.

Por eso la navegación entre páginas, las opciones recordadas y las pruebas no cambian. Una palabra sin emoji asignado se muestra igual que antes.
