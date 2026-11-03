# Revisión inicial de NIMUS Production v0.1

Se revisaron todos los archivos propios: app.py, db.py, requirements.txt, README, lanzadores de Windows/macOS/Linux y .gitignore; además del esquema, integridad, relaciones y filas de SQLite. No se encontraron instrucciones AGENTS.md en el proyecto ni en sus carpetas superiores.

## Arquitectura anterior

Streamlit ejecutaba un único app.py (cinco secciones, formularios y cálculos UI). db.py combinaba DDL, consultas, creación/actualización y métricas. SQLite ya modelaba orders → items → parts → production_jobs y machines, con índices de relaciones y borrado en cascada. No había tests ni control de versión del esquema.

## Hallazgos

- Hoy intentaba seleccionar la columna inexistente `job_code` cuando había trabajos imprimiendo; la consulta devolvía `code`.
- Crear un trabajo no validaba capacidad por pieza ni ocupación de máquina.
- Actualizar terminadas recortaba cantidades negativas/excesivas silenciosamente; marcar Listo no garantizaba completar el lote.
- MIN(required, completed) ocultaba sobreproducción, en vez de impedirla.
- Los estados de máquinas podían contradecir los trabajos; una impresora admitía múltiples trabajos simultáneos.
- Había cálculos de progreso repetidos en SQL/UI, consultas por cada item/pieza y strings de estados inconsistentes.
- IDs a partir de MAX(id) podían reutilizar códigos eliminados y entrar en carrera entre escritores.
- Faltaban edición general, borrado controlado, filtros, atrasos, fechas reales, prioridad de trabajo, respaldo y migraciones.
- El CSV era útil y se conserva; necesita distinguir la granularidad por trabajo para evitar duplicar totales de piezas.
- Los lanzadores instalaban dependencias en cada inicio, incluso sin necesidad.

## Base observada antes de modificar

`integrity_check=ok`, sin violaciones de claves foráneas. Un pedido (EXPO DECO), un item (BASES ×10), una pieza (BASE ORIGEN NEGRA, requerida 1), cero trabajos y máquinas P1–P4.
La pieza requerida 1 es un dato existente, no un error demostrado: se preserva. La nueva UI indica que las piezas son cantidades totales y permite editarla explícitamente.

## Decisión

Mantener Python/Streamlit/SQLite. Separar persistencia, reglas, lecturas/cálculos y cuatro vistas. Incorporar migración y pruebas antes de actualizar la carpeta original. No añadir infraestructura, ORM, API HTTP propia ni sincronización externa.
