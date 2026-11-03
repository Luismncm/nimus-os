# Migración SQLite v0.1 → v0.2

La base original tenía `user_version=0`. La migración en `db.init_db()` crea una copia previa con `Connection.backup()`, obtiene un bloqueo de escritura, lee las cinco tablas, reconstruye el esquema dentro de la misma transacción, restaura IDs/relaciones/datos y valida integridad. No usa `executescript` para evitar commits implícitos durante la migración. Conserva también `sqlite_sequence`, incluso para IDs de registros ya eliminados.

Si cualquier inserción, FK, índice único o verificación falla, SQLite revierte toda la transacción. El archivo vuelve a su esquema original y el mensaje muestra el respaldo. No se borran filas inválidas para hacer pasar la migración. Los respaldos se conservan; no hay limpieza automática.

## Cambios

| Elemento anterior | v0.2 |
| --- | --- |
| orders.status = Abierto | Pendiente; luego recalculado desde producción |
| jobs.status = Pendiente | En cola |
| jobs.status = Imprimiendo | En producción |
| jobs.status = Postproceso | Pausado; revisar/continuar desde la cola |
| jobs.status = Listo con terminadas parciales | Pausado y nota de revisión; no inventa unidades |
| Cualquier trabajo con todas las unidades completadas | Terminado |
| parts.process = Externo | Producción externa |
| jobs.completed_quantity | quantity_completed (CSV conserva ambos nombres) |
| Prioridad solo del pedido | Copiada inicialmente al trabajo; después independiente |
| Sin fechas reales | started_at/completed_at basadas en created_at/updated_at para trabajos antiguos; no son mediciones históricas exactas |
| Máquina manualmente Imprimiendo | Reconciliada con trabajos en producción |
| Pedido Bloqueado | Conservado como bloqueo manual |
| Pedido Entregado | Conservado, incluso si el registro antiguo estaba incompleto |

El registro `migration_log` deja constancia de filas normalizadas. Los valores originales completos están en el respaldo, incluidas notas y estados anteriores. No se modifica `quantity_required` por la cantidad comercial del item.

Se añaden CHECK de estados y cantidades enteras, índices de relaciones/estado, unicidad de máquina en producción, límites de asignación y protecciones del histórico. Los totales completados de piezas no se almacenan; se suman desde trabajos.

## Incompatibilidades que cancelan la migración

Piezas sobreasignadas; cantidades negativas, no enteras o superiores al lote; dos trabajos en producción en una impresora; relaciones huérfanas; estados/procesos desconocidos; nombres obligatorios vacíos; trabajos activos en máquinas de mantenimiento/fuera de servicio. El mensaje incluye la causa de SQLite o los IDs de piezas sobreasignadas.

En esos casos se debe revisar la información con la versión anterior o sobre una copia; no conviene ajustar producción automáticamente. Cierra instancias v0.1 antes de iniciar v0.2. Una base de una versión futura se rechaza sin modificarla.

## Respaldo manual

Desde la raíz, con el entorno del proyecto:

```powershell
.\.venv\Scripts\python.exe -c "from db import backup_database; print(backup_database())"
```

La [API de respaldo de SQLite en Python](https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup) permite copiar coherentemente una base abierta. Las conexiones se cierran explícitamente para liberar los archivos en Windows.
