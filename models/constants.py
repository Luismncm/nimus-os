PRIORITIES = ("Alta", "Media", "Baja")
ORDER_STATUSES = ("Pendiente", "En producción", "Bloqueado", "Listo", "Entregado")
JOB_STATUSES = ("En cola", "En producción", "Pausado", "Bloqueado", "Terminado")
MACHINE_STATUSES = ("Disponible", "Imprimiendo", "Mantenimiento", "Fuera de servicio")
PROCESSES = ("Impresión 3D", "Resina", "Postproceso", "Ensamble", "Grabado", "Empaque", "Producción externa")
PRIORITY_RANK = {name: rank for rank, name in enumerate(PRIORITIES)}
