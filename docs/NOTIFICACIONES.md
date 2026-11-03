# Notificaciones · v0.36

El acceso **Notificaciones** está al final de la barra lateral, después de Herramientas y la versión. Solo muestra un contador y una línea de prioridad; no abre avisos automáticamente.

Al pulsarlo se abre un panel lateral con **Todas, Pedidos, Cobros, Pagos, Insumos y Producción**, búsqueda y filtro **Solo prioritarias**. Se muestran hasta cuatro registros por página. La X, Escape o un clic fuera cierran el panel.

- **Pedidos:** vencidos, entregas de hoy, bloqueos, piezas por asignar, despiece pendiente, empaque y entrega de producción lista. Los avisos del mismo pedido se reúnen en una sola tarjeta. Se excluyen entregados y cancelados.
- **Cobros y pagos:** saldos restantes de ventas activas y gastos activos, con fecha de vencimiento. Se excluyen liquidados, cancelados y ventas en papelera. Un registro sin vencimiento se indica como sin fecha. Los importes son MXN; el saldo de la vista respeta sus filtros.
- **Insumos:** mínimos alcanzados y saldos negativos de componentes, además de avisos de material del taller. Los saldos negativos tienen prioridad sin bloquear pedidos.
- **Producción:** trabajos y máquinas pendientes; se conserva el seguimiento de avisos vistos y pospuestos en Control de producción.

Vencidos, entregas de hoy, bloqueos y saldos negativos aparecen primero. Los vencimientos futuros se muestran en azul. Los contadores se recalculan cada minuto y el panel consulta datos actuales al abrirlo o filtrarlo.

Cada tarjeta abre su pedido, venta, gasto, reposición o control operativo. La navegación no registra pagos, modifica etapas ni marca avisos como vistos. Los pendientes desaparecen al resolver su causa en la vista correspondiente.

No requiere migración: conserva el esquema 22 y todos los valores almacenados. Antes de instalar se respaldan código y base de datos.
