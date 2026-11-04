# Migración de NIMUS OS a Vercel

## Decisiones

| Tema | Decisión |
|---|---|
| Base de datos | **Postgres** (Neon, integrado en el panel de Vercel). |
| Interfaz | **Next.js** (React), lo nativo de Vercel, pensada para escritorio, tableta y celular. |
| Lógica del negocio | **API en Python (FastAPI)** que reutiliza los 69 servicios actuales sin reescribirlos. |
| Alcance | **Todo el sistema:** los 16 módulos, por fases. |

## Por qué así

- Los **69 servicios** (unas 10,000 líneas: pedidos, cola, cobros, inventario, costos, tesorería…) no dependen de Streamlit y tienen **510 pruebas**. Reescribirlos sería perder lo probado.
- Las **95 pantallas** de Streamlit sí hay que reescribirlas: Vercel no puede ejecutar Streamlit, que necesita un servidor siempre encendido y una conexión websocket.
- La base no puede ser un archivo SQLite: en Vercel el disco se borra en cada despliegue.

## Arquitectura

```
Navegador (escritorio / tableta / celular)
   │  HTTPS, sesión con cookie segura
   ▼
Vercel
 ├─ Next.js (src/app)        pantallas: Hoy, Pedidos, Cola, Ventas, …
 └─ /api  FastAPI (Python)   api/index.py → services/* (los mismos de hoy)
                │
                ▼
          Postgres (Neon)    los mismos datos, ids y reglas
```

### Capa de datos dual

`db.connect()` sigue siendo la única puerta a la base:

- **Sin `DATABASE_URL`:** SQLite local, exactamente como hoy. La app de Streamlit sigue funcionando durante toda la migración.
- **Con `DATABASE_URL=postgres://…`:** la misma API sobre Postgres. Una capa de compatibilidad (`pgcompat/`) traduce el SQL de los servicios:
  - parámetros `?`;
  - `INSERT OR IGNORE`;
  - el id recién creado (`lastrowid`);
  - consultas a `PRAGMA` y `sqlite_master`;
  - funciones JSON.

  También convierte los errores de Postgres en los mismos errores que hoy muestran las pantallas.
- **Las reglas que hoy viven en los 124 disparadores de SQLite** se traducen a funciones de Postgres que dan los mismos mensajes. Ejemplos: no pagar de más, no borrar con dependientes, no editar lo conciliado.
- **Criterio de terminado:** las 510 pruebas pasan contra Postgres igual que contra SQLite.

### Datos

- `scripts/migrar_a_postgres.py` copia todas las tablas de `data/nimus_production.db` a Postgres conservando ids y fechas, reajusta las secuencias y **verifica** conteos y totales por tabla (ventas, pagos, gastos, movimientos) antes de dar el visto bueno.
- Antes de cada carga se hace un respaldo local (`backup_database`).
- La base local no se borra ni se modifica.

### Acceso

- Hoy la app no tiene inicio de sesión porque solo abre en la computadora del taller. En la nube **todo** requiere sesión.
- Usuarios con contraseña cifrada (scrypt) en la base, y sesión en cookie segura (`httpOnly`, firmada con `NIMUS_SECRET`).
- Roles iniciales: **admin** (todo) y **taller** (producción, sin finanzas).

## Fases

Cada fase termina desplegada, probada y usable. Hasta el corte final, la app local sigue siendo la principal.

| Fase | Contenido | Estado |
|---|---|---|
| **0 · Fundaciones** | Capa dual SQLite/Postgres, esquema y reglas en Postgres, pruebas en Postgres, script de migración de datos, API con inicio de sesión, estructura de Vercel y Next.js con sesión. | Hecha |
| **1 · Hoy y Pedidos** | Resumen del día, tablero de pedidos, detalle con rastreo, entrega y cobro. | Hecha (v0.61) |
| 2 · Producción | Cola (operar, asignar, calendario, tabla), Máquinas, Control de producción, Desarrollo y prototipos. | Pendiente |
| 3 · Productos y existencias | Inventario, compras, reposición, Colección Origen, Catálogo y recetas, fotos. | Pendiente |
| 4 · Comercial | Ventas y cobranza, Cotizaciones, documentos PDF. | Pendiente |
| 5 · Finanzas | Resumen y previsión, Gastos y comprobantes, Tesorería, Socios. | Pendiente |
| 6 · Rentabilidad | Costos y utilidad, Estado de rendimiento. | Pendiente |
| 7 · Corte | Última copia de datos, la nube pasa a ser la principal y la app local queda de respaldo de solo lectura. | Pendiente |

## Estado de la Fase 0 (v0.60)

| Pieza | Dónde | Verificado |
|---|---|---|
| Capa dual SQLite/Postgres | `db.py`, `pgcompat/` | La app local sigue en SQLite sin instalar nada nuevo. |
| Esquema en Postgres | `pgcompat/schema.py` | Las 83 tablas, 29 índices, la vista y los 124 disparadores de reglas se crean sin errores. |
| Pruebas contra Postgres | `scripts/test_postgres.py` | **485 de 510 pasan**, incluida la de pagos simultáneos. 24 se saltan a propósito: migran o respaldan archivos SQLite (`@sqlite_only`) y en Postgres no aplican. La única falla, `test_reset_origen`, ya existía en SQLite (le falta el módulo `cotejo`). |
| Migración de datos | `scripts/migrar_a_postgres.py` | Con una copia de los datos reales: 2,160 filas de 65 tablas; conteos y totales de dinero iguales. Saldos idénticos en ambas bases ($7,632.00 por cobrar y $5,201.52 por pagar). |
| API | `api/index.py`, `cloud/` | Salud, sesión, Hoy, Pedidos y detalle con rastreo. Sin sesión responde 401. |
| Usuarios | `scripts/crear_usuario.py`, o `NIMUS_ADMIN_EMAIL` / `NIMUS_ADMIN_PASSWORD` para el primer administrador | Contraseñas con scrypt y cookie firmada. |
| Interfaz | `src/` (Next.js 15) | Inicio de sesión, Hoy, Pedidos y detalle, adaptable a celular; compila para producción. |

### Dependencias

- `requirements.txt` ahora es el de la **nube** (FastAPI, psycopg, sqlglot, Pillow, tzdata), porque Vercel lo lee automáticamente.
- La app local usa `requirements-local.txt`. Los lanzadores (`INICIAR_WINDOWS.bat`, `iniciar_mac_linux.sh`, `scripts/check_runtime.py`) ya apuntan ahí.

### Desarrollo local de la versión web

```bash
npm install
npm run dev        # Next.js en :3000 y la API en :8000 (necesita DATABASE_URL y NIMUS_SECRET)
```

## Estado de la Fase 1 (v0.61)

| Acción | API | Pantalla | Reglas |
|---|---|---|---|
| Entregar o liberar a stock | `POST /api/pedidos/{id}/entregar` | Detalle del pedido (siguiente paso) y Hoy → Listos para entregar | Las de `production.deliver_order`: listo, preparado y, si se pidió, saldo liquidado. Al entregar ofrece cobrar el saldo de la venta, como la app local. |
| Cobrar | `GET /api/ventas/{id}/cobro`, `POST /api/ventas/{id}/pagos` | Hoy → Cobros prioritarios y Rastreo del pedido | Solo administración. Revisión de la venta (otro cambio la rechaza), clave por formulario (un doble clic guarda un pago) y el tope del saldo de la base. |
| Repartir piezas | `GET/POST /api/pedidos/{id}/reparto` | Detalle del pedido | `production.create_order_jobs`: todo o nada. La distribución automática es la misma de la app local (`assign_suggest.auto_split`). |

Pruebas: `tests/test_cloud_api.py` (sesión, encabezado X-NIMUS, roles, reintentos, revisiones y reparto), en Postgres.

## Despliegue en Vercel (paso a paso)

1. En vercel.com → **Add New → Project** → importa `Luismncm/nimus-os`. El framework (Next.js) se detecta solo.
2. En el proyecto → **Storage → Create Database → Neon (Postgres)** y conéctala al proyecto: Vercel agrega `DATABASE_URL`.
3. En **Settings → Environment Variables** agrega:
   - `NIMUS_SECRET`: un valor aleatorio de 64 caracteres (te lo genero cuando llegues aquí).
   - `NIMUS_ADMIN_EMAIL` y `NIMUS_ADMIN_PASSWORD`: los escribes tú; crean el primer administrador en el primer inicio de sesión.
4. **Deploy.** `https://…vercel.app/api/health` debe responder `"ok": true`.
5. **Datos:** con la `DATABASE_URL` de Neon en tu computadora, corre `python scripts/migrar_a_postgres.py`. Copia y verifica todo; si algo no cuadra, no guarda nada.

## Lo que necesito de ti (cuando llegue cada paso)

1. **Vercel:** crear la cuenta (o entrar) e importar el repo `Luismncm/nimus-os`.
2. **Neon:** en Vercel → Storage → crear la base Postgres. Vercel pone `DATABASE_URL` sola.
3. **Variables:** `NIMUS_SECRET` (te doy un valor generado) y el correo y contraseña del primer administrador, que escribes tú.
4. **Visto bueno** del conteo de datos antes del corte.
