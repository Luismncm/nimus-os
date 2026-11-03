# v0.57 · Negocio más orgánico: cuentas con historial, Gastos y Ventas más ligeros

## Acceder al historial de cada cuenta

Antes, para ver los movimientos de una cuenta había que ir a Tesorería → Movimientos y elegirla a mano en el filtro. Ahora cada tarjeta de cuenta tiene su propio botón **Ver historial**:

- En **Resumen y previsión** → «Dónde está el dinero» (cada tarjeta de cuenta).
- En **Tesorería y cuentas** → pestaña **Cuentas**, junto a «Editar cuenta».

Al pulsarlo, se abre Tesorería en la pestaña Movimientos, con esa cuenta ya elegida en el filtro y el panel de filtros visible (antes quedaba colapsado por defecto), con todo el historial (no solo el mes).

## Las tres páginas de Negocio, conectadas

«Resumen y previsión», «Gastos y comprobantes» y «Cuentas y movimientos» ahora se leen como una sola barra de navegación arriba de cada página, con la página actual resaltada (fondo e información del color de Negocio), igual que ya pasa con las secciones de la barra lateral. Antes eran tres enlaces sueltos sin indicar dónde estabas.

## Gastos y Ventas: menos pared de números

Las cifras principales de **Ventas y cobranza** (Vendido, Cobrado, Saldo, Ventas activas) y de **Registro de gastos** (Registrado, Pagado, Por pagar de la consulta, Comprobantes por revisar) ahora son tarjetas con un borde de color a la izquierda, naranja cuando hay algo pendiente que atender (saldo, comprobantes) y el color propio de Negocio cuando todo está en orden — el mismo lenguaje visual que ya usa Hoy. Son los mismos `st.metric` de siempre, así que se leen y se exportan igual; solo cambia el acabado.

**Control de gastos** (Resumen y previsión) usa la misma tarjeta para Total en cuentas / Gastos proyectados / Después de gastos, con el borde en rojo cuando el proyectado deja el saldo en negativo.

## Menos ruido burocrático

En Tesorería → Resumen, el bloque «Correspondencia con la hoja de control» (una tabla completa de a qué pestaña de la hoja de cálculo migrada corresponde cada sección) se redujo a un solo botón discreto, «Hoja de control histórica», al final de la pestaña. La explicación detallada ya no hacía falta para el uso diario y competía por atención con los datos del día.

## Verificación

- Suite completa del proyecto: ver resultado al cierre de esta sesión.
- En el navegador, con la copia de prueba: se probó el enlace «Ver historial» desde Resumen y previsión hasta Tesorería → Movimientos (filtro y pestaña correctos, 133 movimientos de esa cuenta), y desde la pestaña Cuentas de Tesorería. Se confirmó que las tres páginas de Negocio resaltan su pestaña actual en la barra superior.
- Dos pruebas se ajustaron porque comprobaban un texto que pasó de `st.caption` a `st.metric` (mismo dato, otra forma): `tests/test_expenses.py`.
