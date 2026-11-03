"""One-click completion of a visible, unchanged set of printing parts."""
import hashlib
import json

from db import connect
from services import production as p
from services.inventory import PRINT_PROCESSES, sync_production
from utils.dates import timestamp


def fingerprint(parts):
    # The stored name: the snapshot shows catalog pieces with their model (base_name keeps the original).
    rows = [(r['id'], r['quantity_required'], r['process'], r['material'], r.get('base_name', r['name']), r.get('collection', ''), r.get('item_name', ''),
             [(j['id'], j['updated_at']) for j in sorted(r['jobs'], key=lambda j: j['id'])])
            for r in sorted(parts, key=lambda r: r['id'])]
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode()).hexdigest()


def finish_printing(item_id, *, part_id=None, expected_fingerprint):
    with connect(write=True) as conn:
        item = p._get(conn, 'items', item_id)
        order = p._editable(conn, item['order_id'])
        if order['blocked_manually']:
            raise ValueError('Libera el bloqueo del pedido antes de registrar impresión.')
        parts = [dict(r) for r in conn.execute('SELECT * FROM parts WHERE item_id=? ORDER BY id', (item_id,))
                 if r['process'] in PRINT_PROCESSES and (part_id is None or r['id'] == part_id)]
        if not parts:
            raise ValueError('Este item no tiene piezas de impresión pendientes definidas.')
        for part in parts:
            part.update(collection=item['collection'], item_name=item['name'])
            part['jobs'] = [dict(j) for j in conn.execute('SELECT * FROM production_jobs WHERE part_id=? ORDER BY id', (part['id'],))]
        if fingerprint(parts) != expected_fingerprint:
            raise ValueError('La impresión cambió en otra ventana. Actualiza antes de marcarla.')
        if any(j['status'] == 'Bloqueado' for part in parts for j in part['jobs']):
            raise ValueError('Hay trabajos bloqueados. Revísalos antes de completar la impresión.')
        total = 0
        for part in parts:
            for job in part['jobs']:
                if job['status'] == 'Terminado':
                    continue
                total += job['quantity'] - job['quantity_completed']
                p._save_job(conn, job, quantity=job['quantity'], quantity_completed=job['quantity'],
                            status='Terminado', machine_id=job['machine_id'], priority=job['priority'],
                            expected_end=job['expected_end'], notes=job['notes'])
            unassigned = part['quantity_required'] - sum(j['quantity'] for j in part['jobs'])
            if unassigned:
                p._validate_job(conn, part['id'], unassigned, unassigned, None, 'Terminado')
                jid, code = p._code(conn, 'production_jobs', 'JOB')
                now = timestamp()
                conn.execute('''INSERT INTO production_jobs(id,code,part_id,quantity,quantity_completed,status,priority,
                    started_at,completed_at,notes,created_at,updated_at) VALUES(?,?,?,?,?,'Terminado',?,?,?,?,?,?)''',
                    (jid, code, part['id'], unassigned, unassigned, order['priority'], now, now,
                     'Registro rápido de impresión desde el pedido. Máquina no especificada.', now, now))
                sync_production(conn, jid, 0, unassigned)
                total += unassigned
        if total:
            conn.execute('INSERT INTO operation_events(order_id,detail,created_at) VALUES(?,?,?)',
                         (order['id'], f"Impresión registrada · {item['name']} · {total} unidades buenas" +
                          (f" · {parts[0]['name']}" if part_id else ''), timestamp()))
            p.refresh_order(conn, order['id'])
        return total
