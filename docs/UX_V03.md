# NIMUS Production v0.3 · Flujo de taller

## Cambios

- Identidad NIMUS con los SVG proporcionados, isotipo y barra lateral oscura. Tema nativo y tipografía local, sin dependencias de fuentes externas ni CSS sobre elementos internos de Streamlit.
- Hoy coloca métricas y disponibilidad de P1–P4 arriba, después la acción recomendada y los pedidos que requieren atención. El siguiente paso detecta si faltan items, despiece, asignación, producción o entrega.
- Pedidos separa la lista del detalle, con búsqueda, tarjetas, progreso y tabla opcional. El árbol conserva CRUD y solo lectura de entregados. Un pedido recién creado abre su detalle.
- Despiece rápido crea varias piezas de igual proceso/material y cantidad por producto. La cantidad comercial del item se multiplica una vez al crear: 10 productos ×1 base =10 bases.
- Repartir genera uno o varios trabajos en una sola transacción. Puede quedar una parte sin asignar. La suma no puede superar la capacidad disponible; si cualquier reparto es inválido, ninguno se guarda.
- El reparto automático usa solo las máquinas disponibles. El reparto manual permite dejar trabajos en cola para una máquina ocupada o en mantenimiento. Iniciar sigue sujeto a disponibilidad real y bloqueo del pedido.
- Avance registra un total de unidades buenas y detecta ediciones de otra ventana. Completar el lote libera la máquina y actualiza los progresos.
- Cola conserva los cinco filtros y ofrece acciones en cada tarjeta más una tabla compacta. Entrar desde pedido/máquina aplica su filtro; Activos oculta terminados, Todos los recupera.
- Máquinas integra los controles de producción y disponibilidad en cada tarjeta.

## Datos y verificación

No hay nueva migración ni cambios en cantidades históricas. Se conserva SQLite con esquema 2 y los CSV estables de v0.2. La instalación respalda código y base antes de copiar la versión nueva.

41 pruebas automatizadas cubren lógica, migración y UI. Se verifican 4+4+2, rollback de un reparto inválido, 40 unidades del despiece de 10 lámparas, avances parciales y completos, filtros y navegación. Las pruebas de navegador usan una copia aislada con registros marcados DEMO; esa base no forma parte de la entrega ni reemplaza la base operativa.

## Alcance

Se mantienen los límites de v0.2: una estación local, sin cloud, inventario/costos, telemetría, dependencias entre procesos ni cálculo automático de duración. La revisión visual cubre escritorio; el apilado en pantallas pequeñas depende de los controles nativos de Streamlit. Para muchos miles de trabajos convendrá paginar desde SQL.
