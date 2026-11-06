# v0.72 · Prototipos: bitácora, reportes técnicos y archivos por proyecto

## Qué cambió

En **Desarrollo y prototipos** cada proyecto mostraba sus impresiones, filamento y costo, pero no había dónde dejar lo aprendido en cada prueba ni dónde encontrar sus archivos. Ahora cada proyecto tiene:

- **Panel del proyecto** (botón **Abrir panel** en su tarjeta): el proyecto ocupa toda la página, con sus acciones arriba (Nota, Reporte técnico, Archivo o enlace, Lanzar impresión, Más), cuatro cifras (reportes, impresiones, filamento, costo real contra presupuesto) y cuatro vistas:
  - **Bitácora**: notas y reportes, lo fijado primero y luego lo más reciente, con buscador y filtro Notas / Reportes.
  - **Reportes técnicos**: tabla de reportes con filtro por resultado (Aprobado, Ajustar, Rechazado, Sin resultado) y el reporte elegido completo debajo.
  - **Archivos y enlaces**: todas las rutas y enlaces del proyecto, de dónde vienen y sus botones para abrirlos.
  - **Impresiones**: las impresiones del proyecto con cuántos reportes tiene cada una, y «Reporte de esta impresión» para documentar una en particular.
- **Notas** para ideas, pendientes y acuerdos.
- **Reportes técnicos** de cada prueba: título, resultado, la impresión probada (opcional) y el contenido (qué se probó, parámetros, qué salió, siguiente paso). Admite formato (negritas, listas, enlaces) y se pueden editar, fijar arriba o eliminar.
- **Archivos y enlaces**: rutas de archivos o carpetas de este equipo o de la red (modelos, perfiles de slicer, fotos) y enlaces web (Drive, documentación). Se agregan sueltos al proyecto o dentro de una nota o reporte, uno por línea como «Nombre | dirección». Acepta la ruta tal cual la copia Windows con «Copiar como ruta de acceso» (con comillas) y direcciones `file:///`.
- **Accesos rápidos**: los enlaces fijados (estrella) aparecen en la tarjeta del proyecto y en el encabezado del panel; un clic abre el archivo con su programa, la carpeta en el Explorador, o la página web.

La tarjeta de la lista ahora resume la bitácora (notas, reportes, archivos, resultado del último reporte) y tiene **Nota** directa. «Costos» y el detalle de piezas pasaron al menú **Más**; la tabla de impresiones vive en el panel.

## Cómo se implementó

- Migración v35 → v36 (`models/development_schema.py::create_development_journal_schema`), con respaldo automático: tablas `development_entries` (nota o reporte, resultado solo en reportes, impresión por código de trabajo sin llave foránea para que borrar una impresión no borre su reporte) y `development_links` (del proyecto o de una entrada; se borran con su entrada).
- `services/development_journal.py`: guardar y editar entradas con control de revisión (un doble clic no duplica ni falla), enlaces, fijar, eliminar, y los resúmenes para la lista. Valida que la impresión del reporte sea del proyecto. Un proyecto cerrado conserva su bitácora editable: el cierre solo impide lanzar impresiones.
- `services/local_files.py`: abre archivos y carpetas en este equipo (la app local corre aquí). Por seguridad nunca ejecuta programas ni scripts desde un enlace (`.exe`, `.bat`, `.ps1`, `.lnk`…): para esos solo abre su carpeta. Una ruta que no existe (o una unidad de red desconectada) se marca «No encontrado».
- `views/development_panel.py` (panel, formularios y tarjetas) y `views/development.py` (lista).
- De paso: los importes de la tarjeta («$203.65 de $1,500.00») se leían como fórmula matemática y perdían el signo de pesos; ya se muestran bien.

## Pendiente fuera de este cambio

La base en la nube (Neon) no se migra sola: `pgcompat` construye el esquema completo en una base vacía, pero no aplica migraciones a una existente. La web no usa todavía la bitácora, así que no le afecta; aun así conviene preparar un script de migración incremental para Postgres antes de exponerla, y aplicar también la columna `machines.hourly_rate_cents` de la v0.68.

## Verificación

- `tests/test_development_journal.py` (7 pruebas): reporte con resultado, impresión y enlaces; doble clic; impresión de otro proyecto rechazada; nota sin resultado; edición con revisión y eliminación con sus enlaces; limpieza y rechazo de direcciones; bitácora en proyecto cerrado; migración 35 → 36 con respaldo; estado y apertura de archivos (programas bloqueados); y el flujo en la interfaz: abrir panel, crear reporte con archivo, verlo en Reportes técnicos, fijarlo y abrirlo desde la tarjeta.
- Suite completa en SQLite y las pruebas de desarrollo en Postgres (`scripts/test_postgres.py`).
- Navegador, contra una copia de la base real: panel, reporte con archivo, filtro por resultado, accesos rápidos en la tarjeta. No se abrió ningún programa en el equipo durante la revisión; la apertura está cubierta por la prueba con el lanzador simulado.
