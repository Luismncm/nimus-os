# Interfaz de NIMUS OS · v0.32

La barra lateral reúne las secciones en **Taller** y **Negocio**. Cambiar de área permite explorar sus accesos sin salir de la página actual. Al abrir otra sección, el área se ajusta a esa página y su enlace queda marcado. Todos los destinos conservan su ruta y los borradores de sesión siguen disponibles.

- **Taller:** Hoy, Pedidos, Cola de producción, Agenda de impresión, Colección Origen, Inventario, Catálogo y recetas y Máquinas.
- **Negocio:** Ventas y cobranza, Cotizaciones, Tesorería y cuentas, Gastos, Presupuesto mensual, Socios y aportaciones y Costos y utilidad.

**Buscar una sección…** permite localizar cualquier destino escribiendo su nombre. Se limpia después de abrir la página para poder buscar de nuevo. En pantallas pequeñas usa el control nativo para abrir o cerrar la barra lateral.

Los encabezados indican área y sección. Los botones principales usan el acento petróleo; las acciones complementarias conservan un estilo secundario. En Catálogo y Tesorería, los accesos menos frecuentes se agrupan en **Más acciones** o **Gestiones relacionadas**. Los cambios siguen guardándose desde sus formularios y acciones; seleccionar una sección no modifica datos.

**Herramientas** contiene Actualizar, exportaciones CSV, respaldo y la preferencia **Reducir movimiento del tablero**. Esta preferencia dura la sesión. El tablero también respeta automáticamente el movimiento reducido del dispositivo.

Las microinteracciones del tablero se limitan al realce de tarjetas, botones y progreso. Al solicitar un movimiento, el control indica que está validando y bloquea pulsaciones repetidas. El diálogo de validación conserva las reglas operativas. Los guardados prolongados muestran un indicador nativo; las confirmaciones y errores se mantienen visibles según el resultado.

La actualización modifica presentación y navegación. No cambia reglas de producción, recetas, cobros, gastos, presupuestos ni movimientos de inventario, y no requiere migrar la base de datos. Colores, tipografía, bordes y botones usan el tema nativo de Streamlit; no se inyectan estilos globales ni se cargan fuentes externas.
