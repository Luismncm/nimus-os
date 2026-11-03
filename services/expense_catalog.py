"""Reference structure from NIMUS · Control; no historical transactions or amounts."""

CATEGORIES = {
    'Producción / materiales': ['Filamento / materia prima','Chips NFC / electrónica','Adhesivos / fijación','Empaque / embalaje','Consumibles de impresión'],
    'Producción / servicios externos': ['Servicios externos de producción'],
    'Producto / I+D': ['Prototipos / pruebas','Desarrollo de software externo'],
    'Personal / nómina': ['Nómina','Bonos / comisiones de personal'],
    'Servicios profesionales': ['Honorarios profesionales','Freelance / contratistas'],
    'Marketing / contenido': ['Pauta digital','Producción de contenido','Diseño / branding'],
    'Ventas / prospección': ['Eventos / networking','Gasolina / prospección comercial','Comisiones de venta','Material comercial / promocional'],
    'Software / SaaS': ['SaaS / suscripciones','IA / productividad'],
    'Infraestructura digital': ['Hosting / infraestructura','Dominios','Correo / almacenamiento'],
    'Operación / oficina': ['Oficina / papelería','Herramientas menores de producción'],
    'Instalaciones / servicios': ['Renta / espacio','Electricidad','Agua','Internet / telefonía','Limpieza'],
    'Logística / traslados / envíos': ['Mensajería / envíos','Envíos de insumos','Gasolina / traslados operativos'],
    'Equipo / activos': ['Compra de equipo','Cómputo / periféricos','Herramientas / equipo de taller','Mobiliario / adecuaciones'],
    'Mantenimiento / reparaciones': ['Mantenimiento de impresoras','Reparaciones','Refacciones'],
    'Legal / contable / administrativo': ['Servicios contables','Servicios legales / notariales'],
    'Impuestos': ['Impuestos','Derechos / licencias / permisos'],
    'Comisiones / financiero': ['Comisiones bancarias','Comisiones de pasarela','Intereses / cargos financieros'],
    'Viajes / representación': ['Viáticos / representación'],
    'Capacitación / conocimiento': ['Cursos / capacitación'],
    'Reembolsos / ajustes': ['Reembolso','Ajuste / regularización'],
    'Otros egresos': ['Gasto no clasificado'],
}
ACCOUNTS = ('Cuenta bancaria NIMUS','Efectivo / caja','Tarjeta / pasarela','Otra')
UNITS = ('NIMUS','LÜP','Nubi')
COST_TYPES = ('Variable','Fijo','Desarrollo / único')
RECEIPTS = ('Pendiente','Factura','Recibo / nota','Sin comprobante')
TAX_MODES = ('Sin desglose','Subtotal + IVA 16%','Total con IVA 16%','Desglose manual')
PERIODS = {'Mensual':1,'Bimestral':2,'Trimestral':3,'Semestral':6,'Anual':12,'Único':None}
