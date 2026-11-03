# Análisis · software para granjas de impresión 3D (27/10/2026)

Revisión rápida de herramientas del nicho para tomar lo que sirve a la operación diaria de NIMUS. Las fuentes son páginas y documentación de cada proveedor o de su competencia: tómense como referencia, no como verificación independiente.

## Qué hacen las herramientas de referencia

| Herramienta | Lo más útil para NIMUS |
|---|---|
| **Printago** | Asigna un trabajo solo a una impresora en línea, marcada como lista, con el material correcto cargado y con las etiquetas requeridas. El material puede ser genérico (cualquier color de "PLA básico"). Advierte no cambiar carretes con el emparejamiento automático activo. |
| **SimplyPrint** | "Smart routing": compara cama, material, boquilla, color, volumen y peso de filamento antes de mandar a una impresora; agrupa variantes de material ("cualquier PLA"). Cola con línea de tiempo y aprobación. |
| **Bambu Farm Manager** | Gratuito y local (LAN) para A1/P1/X1: panel con el avance en tiempo real de toda la flota y cola según disponibilidad de impresoras. Sus competidores le señalan menos estadísticas e historial. |
| **OctoFarm** | Panel único sobre varias instancias de OctoPrint, con filamento por impresora e historial. Su desarrollo parece detenido (última versión estable reportada en 2022). |

## Patrones comunes y cómo quedan en NIMUS

1. **Filamento cargado por impresora** → nuevo: cada máquina registra qué material tiene montado; la cola y la asignación lo muestran y lo usan.
2. **Asignación a la impresora adecuada** → nuevo: al capturar o repartir, NIMUS sugiere la máquina que **antes queda libre con el material cargado** (si ninguna lo tiene, la que antes queda libre y avisa del cambio de filamento).
3. **Panel en vivo de la flota** → nuevo: tarjetas por impresora con estado, avance estimado por tiempo, hora de término y siguiente trabajo, con actualización automática.
4. **Etiquetas claras** → nuevo: impresora, venta, pedido, stock y prototipo con el mismo formato e iconos en toda la cola.
5. **Segmentación** → nuevo: agrupar la cola por máquina, por estado o por para qué es.

## Lo que no se hace todavía (y por qué)

- **Conexión directa con las impresoras** (avance real, cámara, iniciar desde NIMUS): requiere integrar la red local de Bambu Lab (MQTT con código de acceso) u OctoPrint. El avance actual es **estimado por tiempo** a partir del inicio real y la duración. Es el siguiente paso natural si se quiere monitoreo real.
- **Detección de fallas por IA** (tipo Obico): depende de cámaras.
- **Color exacto en el emparejamiento**: NIMUS compara por nombre de material; usar el mismo nombre que en las piezas.

## Fuentes

- [SimplyPrint · Smart routing](https://simplyprint.io/features/smart-routing)
- [Printago · Smart queue](https://docs.printago.io/docs/core-features/smart-queue) · [Auto-assign con filamento coincidente](https://printago.io/blog/auto-assign-print-jobs-to-free-printer-with-matching-filament)
- [Bambu Farm Manager · wiki](https://wiki.bambulab.com/en/software/bambu-farm-manager) · [Bambu Lab blog](https://blog.bambulab.com/bambu-lab-introduces-local-fleet-control-with-bambu-farm-manager/)
- [OctoFarm · GitHub](https://github.com/NotExpectedYet/OctoFarm)
