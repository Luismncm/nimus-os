"""Invoice metadata and PDF bytes are backed up atomically with the local database."""
import re
from db import connect
from utils.dates import timestamp

MAX_BYTES=10*1024*1024


def validate_pdf(upload):
    if upload is None: return None,None
    filename,content=upload
    filename=str(filename).replace('\\','/').split('/')[-1]
    filename=re.sub(r'[\x00-\x1f<>:"|?*]','_',filename)[:180]
    if not filename.lower().endswith('.pdf'): raise ValueError('Adjunta un archivo PDF.')
    if not isinstance(content,bytes) or not content or len(content)>MAX_BYTES:
        raise ValueError('El PDF debe tener contenido y pesar como máximo 10 MB.')
    if not content.startswith(b'%PDF-') or b'%%EOF' not in content[-2048:]:
        raise ValueError('El archivo no parece un PDF completo. Exporta nuevamente la factura como PDF.')
    return filename,content


def _owner(conn,kind,identity):
    if kind not in ('sale','expense'): raise ValueError('Tipo de registro no válido.')
    row=conn.execute(f"SELECT * FROM {'sales' if kind=='sale' else 'expenses'} WHERE id=?",(identity,)).fetchone()
    if not row: raise ValueError('El registro ya no está disponible.')
    return row


def _get(conn,kind,identity):
    owner=_owner(conn,kind,identity)
    row=conn.execute('SELECT * FROM invoice_documents WHERE owner_type=? AND owner_id=?',(kind,identity)).fetchone()
    result=dict(row) if row else dict(owner_type=kind,owner_id=identity,required=None,reference='',filename=None,content=None,revision=0,updated_at=None)
    if kind=='expense':
        result.update(required=None if owner['receipt_type']=='Pendiente' else owner['receipt_type']=='Factura',reference=owner['receipt_ref'])
    result.update(owner_revision=owner['revision'],editable=owner['status'] in ('Activa','Activo'),code=owner['code'])
    return result


def get(kind,identity):
    with connect() as conn:return _get(conn,kind,identity)


def _save(conn,kind,identity,required,reference='',upload=None,clear_pdf=False,*,expected_revision,expected_owner_revision):
    current=_get(conn,kind,identity)
    if not current['editable']: raise ValueError('El registro cancelado conserva sus documentos.')
    if current['revision']!=expected_revision or current['owner_revision']!=expected_owner_revision:
        raise ValueError('El registro cambió. Actualiza antes de guardar la factura.')
    if not isinstance(required,bool): raise ValueError('Indica si lleva factura o no.')
    reference=str(reference or '').strip()
    if len(reference)>250:raise ValueError('La referencia debe tener como máximo 250 caracteres.')
    if clear_pdf and upload:raise ValueError('Elige reemplazar o retirar el PDF, no ambas acciones.')
    filename,content=validate_pdf(upload) if upload else (None,None) if clear_pdf else (current['filename'],current['content'])
    if not required and content:raise ValueError('Para conservar un PDF, indica Sí lleva factura. Para quitarlo, marca Retirar PDF.')
    conn.execute('''INSERT INTO invoice_documents(owner_type,owner_id,required,reference,filename,content,revision,updated_at)
        VALUES(?,?,?,?,?,?,1,?) ON CONFLICT(owner_type,owner_id) DO UPDATE SET required=excluded.required,
        reference=excluded.reference,filename=excluded.filename,content=excluded.content,
        revision=invoice_documents.revision+1,updated_at=excluded.updated_at''',
        (kind,identity,int(required),reference,filename,content,timestamp()))
    if kind=='expense':
        owner=_owner(conn,kind,identity)
        receipt='Factura' if required else 'Sin comprobante' if owner['receipt_type'] in ('Factura','Pendiente') else owner['receipt_type']
        conn.execute('UPDATE expenses SET receipt_type=?,receipt_ref=?,revision=revision+1,updated_at=? WHERE id=?',(receipt,reference,timestamp(),identity))
        from services.expenses import _audit
        _audit(conn,identity,'Factura: '+('con PDF' if content else 'PDF pendiente' if required else 'no aplica'))
    else:
        conn.execute('UPDATE sales SET revision=revision+1,updated_at=? WHERE id=?',(timestamp(),identity))
        conn.execute('INSERT INTO sale_events(sale_id,detail,created_at) VALUES(?,?,?)',
            (identity,'Factura: '+('con PDF' if content else 'PDF pendiente' if required else 'no aplica'),timestamp()))


def save(kind,identity,required,reference='',upload=None,clear_pdf=False,*,expected_revision,expected_owner_revision):
    with connect(write=True) as conn:
        _save(conn,kind,identity,required,reference,upload,clear_pdf,expected_revision=expected_revision,expected_owner_revision=expected_owner_revision)


def initial(conn,kind,identity,required):
    # Used during creation. Duplicate form submission must never overwrite later documents.
    if not isinstance(required,bool):raise ValueError('Indica si lleva factura o no.')
    prior=conn.execute('SELECT required FROM invoice_documents WHERE owner_type=? AND owner_id=?',(kind,identity)).fetchone()
    if prior and bool(prior['required'])!=required:raise ValueError('La venta ya se registró con otra opción de factura. Abre su detalle para cambiarla.')
    conn.execute('''INSERT OR IGNORE INTO invoice_documents(owner_type,owner_id,required,revision,updated_at)
        VALUES(?,?,?,1,?)''',(kind,identity,int(required),timestamp()))


def statuses(kind):
    with connect() as conn:
        if kind=='expense':
            rows=conn.execute("SELECT e.id owner_id,CASE WHEN receipt_type='Pendiente' THEN NULL ELSE receipt_type='Factura' END required,d.filename FROM expenses e LEFT JOIN invoice_documents d ON d.owner_type='expense' AND d.owner_id=e.id").fetchall()
        else:
            rows=conn.execute("SELECT s.id owner_id,d.required,d.filename FROM sales s LEFT JOIN invoice_documents d ON d.owner_type='sale' AND d.owner_id=s.id").fetchall()
    return {r['owner_id']:'Por definir' if r['required'] is None else 'No lleva factura' if not r['required'] else 'PDF adjunto' if r['filename'] else 'Factura · PDF pendiente' for r in rows}
