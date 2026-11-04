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
| **2 · Producción** | Cola (operar, asignar, calendario, tabla), Máquinas, Control de producción, Desarrollo y prototipos. | Hecha (v0.62). Siguen solo en la app local: calendario, tabla con CSV, nueva impresión de pedido, editar trabajo, reimprimir y corregir costo |
| **3 · Productos y existencias** | Inventario, compras, reposición, Colección Origen, Catálogo y recetas, fotos. | Hecha (v0.63). Siguen solo en la app local: editar recetas, duplicar variantes, fotos, crear lámparas y colores de Origen, nuevas compras a proveedor y mínimos de reposición |
| **4 · Comercial** | Ventas y cobranza, Cotizaciones, documentos PDF. | Hecha (v0.64). Siguen solo en la app local: facturas (CFDI), corrección de partidas, flujo comercial con condiciones, imágenes y rangos de volumen de la cotización |
| **5 · Finanzas** | Resumen y previsión, Gastos y comprobantes, Tesorería, Socios. | Hecha (v0.65). Siguen solo en la app local: presupuesto mensual, gastos recurrentes (plantillas), confirmar saldos, editar y corregir gastos o movimientos conciliados, compras pagadas por socio y su reembolso |
| **6 · Rentabilidad** | Costos y utilidad, Estado de rendimiento. | Hecha (v0.66), de consulta. Siguen solo en la app local: editar perfiles de costo de piezas, extras de receta y asignar costos a una venta |
| 7 · Corte | Última copia de datos, la nube pasa a ser la principal y la app local queda de respaldo de solo lectura. | Pendiente: necesita la cuenta de Vercel y la base Neon (ver abajo) |

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

## Estado de la Fase 2 (v0.62)

| Pantalla | Qué hace en la web | API |
|---|---|---|
| Cola de producción | Impresiones por máquina con estados rápidos, búsqueda y filtro por máquina o pedido. Iniciar, pausar, reanudar, terminar, bloquear y liberar; avance, falla y horario (con el primer horario libre). "Por resolver" con su arreglo y "Programar N sin horario". | `GET /api/cola`, `POST /api/cola/{id}/accion\|avance\|falla\|horario\|reprogramar`, `POST /api/cola/programar` |
| Máquinas | Estado, impresión actual y siguiente, disponibilidad, filamento cargado y carga. Agregar, editar, filamento, archivar y reactivar. | `GET/POST /api/maquinas`, `PUT /api/maquinas/{id}`, `POST /api/maquinas/{id}/filamento\|archivo` |
| Control de producción | Avisos (visto, posponer), capacidad por bloque de tiempo y fallas. Costos y margen pasa a la Fase 6. | `GET /api/control`, `POST /api/control/avisos/{id}` |
| Desarrollo y prototipos | Proyectos con impresiones, filamento y, para administración, costo y presupuesto. Nuevo, editar, cerrar, reabrir y lanzar impresión de prototipo. | `GET/POST /api/desarrollo`, `PUT /api/desarrollo/{id}`, `POST /api/desarrollo/{id}/cerrar\|reabrir\|impresion` |

Cada acción manda la revisión con la que se dibujó la pantalla: si el trabajo cambió en otro dispositivo, se rechaza en vez de sobrescribir. Fallas e impresiones de prototipo llevan clave por formulario. El rol taller no ve ni modifica presupuestos. Pruebas: `tests/test_cloud_production.py`.

## Estado de la Fase 3 (v0.63)

| Pantalla | Qué hace en la web | API |
|---|---|---|
| Inventario | Saldos por pieza (por distribuir, almacén, reservadas, B2B) con filtros; entrada, mover o asignar a B2B y revertir, siempre como movimientos nuevos. Filamento y consumibles (entrada, consumo, conteo), insumos con reposición, compras con recepción, reservas, clientes B2B y movimientos. | `GET /api/inventario`, `POST /api/inventario/entrada\|mover`, `POST /api/inventario/movimientos/{id}/revertir`, `POST /api/consumibles/{id}/movimiento`, `POST /api/compras/piezas\|consumibles/{id}/recibir` |
| Catálogo y recetas | Productos con su receta vigente y piezas reutilizables con los productos que las usan. Nueva pieza, nuevo producto y pedido desde receta con el plan de reservas y faltantes. | `GET /api/catalogo`, `POST /api/catalogo/componentes\|productos`, `GET /api/catalogo/recetas/{id}/plan`, `POST /api/catalogo/recetas/{id}/pedido` |
| Colección Origen | Lámparas por modelo y color con su composición, pedidos de lámparas con lo que falta y reserva de insumos disponibles. | `GET /api/origen`, `POST /api/origen/pedidos/{id}/reservar` |

El pedido desde receta manda la huella del plan: si las existencias cambiaron, pide recalcular en vez de reservar de más. El rol taller ve cantidades, no el valor del inventario. Pruebas: `tests/test_cloud_products.py`.

## Estado de la Fase 4 (v0.64)

Solo administración. Los totales siempre los calcula el servicio (`quotations.calculate`), también en la vista previa mientras se escriben las partidas.

| Pantalla | Qué hace en la web | API |
|---|---|---|
| Ventas y cobranza | Ventas por periodo con búsqueda y cobranza; vendido, cobrado y saldos. Detalle con partidas y pagos: cobrar, anular pago, vencimiento, crear pedido, comprobante imprimible y cancelar. Venta directa nueva. | `GET /api/ventas`, `GET/POST /api/ventas/{id}…`, `POST /api/ventas` |
| Cotizaciones | Lista por estado; editar partidas, descuento, IVA y vigencia; guardar como borrador, enviada o aceptada; anticipo, convertir en venta, crear pedido, duplicar, cancelar; documento y recibo imprimibles. | `GET/POST /api/cotizaciones`, `GET/PUT /api/cotizaciones/{id}`, `POST /api/cotizaciones/{id}/estado\|pagos\|venta\|pedido` |

Pruebas: `tests/test_cloud_commercial.py`.

## Estado de la Fase 5 (v0.65)

Solo administración. El dinero solo se mueve como pagos registrados; anular conserva el historial.

| Pantalla | Qué hace en la web | API |
|---|---|---|
| Resumen y previsión | Diagnóstico (crítico, atención, sano), caja, meses que alcanza, cobertura de ventas, peso del dinero del socio, por cobrar y por pagar; entradas y salidas de seis meses; previsión del mes por cuenta. | `GET /api/resumen` |
| Gastos y comprobantes | Por pagar primero; gastos por periodo con búsqueda; detalle con pagos. Nuevo gasto (con cuatro formas de capturar el IVA y opción de pagado completo), pagar, anular pago, cancelar. | `GET/POST /api/gastos`, `GET /api/gastos/{id}`, `POST /api/gastos/{id}/pagos\|cancelar`, `POST /api/gastos/pagos/{id}/anular` |
| Tesorería | Saldo por cuenta y movimientos reales del periodo (cobros, anticipos, pagos de gastos, aportaciones) con filtros. Nueva cuenta y edición. | `GET /api/tesoreria`, `POST/PUT /api/tesoreria/cuentas` |
| Socios y aportaciones | Aportaciones, compras cubiertas y reembolsable pendiente; nueva aportación y anulación con la huella de conciliación. | `GET/POST /api/socios`, `POST /api/socios/{id}/anular` |

Pruebas: `tests/test_cloud_finance.py`.

## Estado de la Fase 6 (v0.66)

| Pantalla | Qué hace en la web | API |
|---|---|---|
| Costos y utilidad | Costo por receta (material, máquina, fijo y directos por lámpara, con lo que falta capturar), utilidad por venta (solo suma las ventas con costo completo) y costo real contra venta por pedido. | `GET /api/costos` |
| Estado de rendimiento | Este mes, mes anterior, 90 días o el año contra el periodo anterior: vendido, cobrado, gastos, flujo, entregas a tiempo, piezas, horas de máquina y rechazo; seis meses, uso por máquina y clientes principales. | `GET /api/rendimiento` |

Pruebas: `tests/test_cloud_profitability.py`.

## Qué queda solo en la app local

Las 16 secciones ya se pueden usar en la web para el trabajo diario. Estas tareas menos frecuentes siguen en la app local hasta una fase siguiente:

- **Producción:** calendario, tabla con CSV, nueva impresión de pedido (las de prototipo sí están), editar trabajo, reimprimir y corregir costo.
- **Productos:** editar recetas, duplicar variantes, fotos, crear lámparas y colores de Origen, nuevas compras a proveedor y mínimos de reposición.
- **Comercial:** facturas (CFDI), corrección de partidas, flujo comercial con condiciones, imágenes y rangos de volumen.
- **Finanzas:** presupuesto mensual, gastos recurrentes, confirmar saldos, correcciones conciliadas y compras pagadas por socio.
- **Rentabilidad:** editar perfiles de costo y asignar costos a una venta.

Mientras ambas apps existan, solo una debe ser la principal: la local sobre SQLite hasta el corte, o la web sobre Neon después. Si se escribe en las dos, los datos se separan.

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
