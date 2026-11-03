import json
from db import connect
from services import sales as s, quotations as q
from utils.dates import timestamp


def history(identity):
    with connect() as conn:
        return [dict(r) for r in conn.execute('SELECT * FROM sale_events WHERE sale_id=? ORDER BY id DESC',(identity,))]


def trash_rows():
    with connect() as conn:
        return [dict(r) for r in conn.execute('''SELECT t.*,s.code,s.revision,json_extract(s.payload,'$.client') client,
            json_extract(s.payload,'$.project') project FROM sales_trash t JOIN sales s ON s.id=t.sale_id ORDER BY t.deleted_at DESC''')]


def remove_sale(identity,reason,*,expected_revision):
    reason=str(reason or '').strip()
    if not reason: raise ValueError('Indica el motivo de eliminación.')
    with connect(write=True) as conn:
        row=s._get(conn,identity)
        if conn.execute('SELECT 1 FROM sales_trash WHERE sale_id=?',(identity,)).fetchone():return
        s._revision(row,expected_revision)
        if conn.execute('SELECT 1 FROM sales_payment_ledger WHERE sale_id=? AND voided_at IS NULL',(identity,)).fetchone():
            raise ValueError('La venta tiene pagos vigentes. Revisa y anula solo las capturas erróneas antes de eliminarla.')
        order=row['order_id']
        if row['quote_id']:
            quote=conn.execute('SELECT order_id FROM quotations WHERE id=?',(row['quote_id'],)).fetchone()
            order=quote['order_id']
        if order:raise ValueError('La venta tiene un pedido vinculado. Revisa esa operación antes de eliminarla; el pedido se conserva.')
        conn.execute('INSERT INTO sales_trash VALUES(?,?,?,?)',(identity,row['status'],reason,timestamp()))
        if row['status']=='Activa':
            conn.execute("UPDATE sales SET status='Cancelada',cancel_reason=?,cancelled_at=?,updated_at=?,revision=revision+1 WHERE id=?",(reason,timestamp(),timestamp(),identity))
        else:conn.execute('UPDATE sales SET revision=revision+1,updated_at=? WHERE id=?',(timestamp(),identity))
        conn.execute('INSERT INTO sale_events(sale_id,detail,created_at) VALUES(?,?,?)',(identity,'Enviada a papelera: '+reason,timestamp()))


def restore_sale(identity,*,expected_revision):
    with connect(write=True) as conn:
        row=s._get(conn,identity)
        trash=conn.execute('SELECT * FROM sales_trash WHERE sale_id=?',(identity,)).fetchone()
        if not trash:return
        s._revision(row,expected_revision)
        if trash['previous_status']=='Activa':
            conn.execute("UPDATE sales SET status='Activa',cancel_reason=NULL,cancelled_at=NULL,revision=revision+1,updated_at=? WHERE id=?",(timestamp(),identity))
        else:conn.execute('UPDATE sales SET revision=revision+1,updated_at=? WHERE id=?',(timestamp(),identity))
        conn.execute('DELETE FROM sales_trash WHERE sale_id=?',(identity,))
        conn.execute('INSERT INTO sale_events(sale_id,detail,created_at) VALUES(?,?,?)',(identity,'Venta restaurada desde papelera',timestamp()))


def line_lock(sale):
    if sale['status']!='Activa':return 'La venta está cancelada.'
    if sale['quote_id']:return 'Proviene de una cotización aceptada. Conserva sus partidas originales.'
    if sale['order_id']:return 'Tiene un pedido vinculado; sus partidas ya definen la producción.'
    if sale['payments']:return 'Tiene historial de pagos. Conserva sus partidas para mantener los importes del historial.'
    from services.invoices import get
    if get('sale',sale['id'])['content']:return 'Tiene una factura PDF adjunta. Revisa el documento antes de corregir las partidas.'
    return ''


def remove_lines(identity,indices,reason,*,expected_revision):
    if not indices or any(type(i) is not int for i in indices) or len(set(indices))!=len(indices):
        raise ValueError('Selecciona las partidas que deseas eliminar.')
    if not str(reason or '').strip():raise ValueError('Indica el motivo de la corrección.')
    with connect(write=True) as conn:
        row=s._get(conn,identity);s._revision(row,expected_revision)
        if row['status']!='Activa':raise ValueError('La venta está cancelada.')
        data=json.loads(row['payload'])
        if any(i<0 or i>=len(data['lines']) for i in indices):raise ValueError('Las partidas cambiaron. Actualiza la vista.')
        data['lines']=[r for i,r in enumerate(data['lines']) if i not in indices]
        if not data['lines']:raise ValueError('La venta debe conservar una partida. Para quitarla completa usa Eliminar venta.')
        data=q.calculate(data)
        # Database guard checks payment history, PDF, quote and production links in the same transaction.
        conn.execute('UPDATE sales SET payload=?,total_cents=?,revision=revision+1,updated_at=? WHERE id=?',
            (json.dumps(data,ensure_ascii=False),data['totals']['total'],timestamp(),identity))
        conn.execute('INSERT INTO sale_events(sale_id,detail,previous_payload,created_at) VALUES(?,?,?,?)',
            (identity,'Partidas eliminadas: '+', '.join(str(i+1) for i in sorted(indices))+'. Motivo: '+reason.strip(),row['payload'],timestamp()))
