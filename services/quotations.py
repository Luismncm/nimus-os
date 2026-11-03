from services import treasury
"""Commercial quotes, volume pricing and payments with integer-cent totals."""
import base64
import io
import json
import math
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from PIL import Image
from db import connect
from services.production import _code
from utils.dates import now, timestamp, parse_deadline
from services.guards import fetch, same_revision

DETAIL_FIELDS = ('contact', 'contact_channel', 'rfc', 'solution', 'context', 'level', 'material',
                 'objective', 'reference', 'lead_time', 'owner', 'notes', 'payment_terms', 'conditions', 'issuer', 'footer')
DEFAULT_TERMS = '50% anticipo para iniciar producción.\n50% restante contra entrega.\nEnvío no incluido salvo acuerdo previo.\nCotización sujeta a disponibilidad de material.'
DEFAULT_CONDITIONS = ('Anticipo: se requiere anticipo del 50% para agendar en cola de producción. Sin anticipo confirmado no se reserva fecha.\n'
    'Archivos: el cliente proporciona logotipo, referencias, medidas y archivos disponibles. El diseño o desarrollo adicional debe incluirse en el alcance.\n'
    'Validez: al vencer la fecha indicada pueden actualizarse precios, disponibilidad y tiempos.')


def number(value, label, *, minimum=0, maximum=1000000000):
    try:
        if isinstance(value, bool): raise ValueError()
        v = Decimal(str(value))
        if not v.is_finite() or v < minimum or v > maximum: raise ValueError()
        return v
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f'{label}: ingresa un número entre {minimum} y {maximum}.') from None


def cents(value):
    return int((number(value, 'Importe') * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def money(value):
    return f'${value / 100:,.2f}'


def defaults():
    today = now().date()
    return dict(client='', project='', issued_on=today.isoformat(), valid_until=(today + timedelta(days=15)).isoformat(),
                lines=[], tiers=[], discount=0, iva=False, images=[],
                **{k: DEFAULT_TERMS if k == 'payment_terms' else DEFAULT_CONDITIONS if k == 'conditions' else
                   'NIMUS' if k == 'issuer' else 'Producto · Software · Manufactura' if k == 'footer' else '' for k in DETAIL_FIELDS})


def calculate(payload):
    """Normalize and validate every value before any persistence or conversion."""
    d = defaults()
    for field in ('client', 'project', *DETAIL_FIELDS):
        d[field] = str(payload.get(field, d[field]) or '').strip()
        if len(d[field]) > 12000: raise ValueError(f'El campo {field} es demasiado largo.')
    for field in ('issued_on', 'valid_until'):
        try: d[field] = date.fromisoformat(str(payload[field])).isoformat()
        except (KeyError, ValueError): raise ValueError('Revisa las fechas de emisión y vigencia.') from None
    if d['valid_until'] < d['issued_on']: raise ValueError('La vigencia no puede ser anterior a la emisión.')
    d['discount'] = float(number(payload.get('discount', 0), 'Descuento', maximum=100))
    d['iva'] = bool(payload.get('iva', False))
    for row in payload.get('lines', []):
        description = str(row.get('description') or '').strip()
        if not description: raise ValueError('Cada partida necesita una descripción; elimina las filas vacías.')
        quantity = number(row.get('quantity'), 'Cantidad', minimum=Decimal('0.001'), maximum=1000000)
        produce = bool(row.get('produce', False))
        if produce and quantity != quantity.to_integral():
            raise ValueError('Las partidas para fabricar requieren cantidades enteras.')
        price = cents(row.get('price'))
        amount = int((quantity * price).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        d['lines'].append(dict(description=description, quantity=float(quantity), price=price / 100,
                               produce=produce, amount_cents=amount))
        rid=row.get('recipe_id')
        if isinstance(rid,float) and math.isnan(rid):rid=None
        if rid is not None:
            if isinstance(rid,float) and rid.is_integer():rid=int(rid)
            if type(rid) is not int or rid<=0 or not produce:raise ValueError('La receta debe corresponder a una partida entera para fabricar.')
            d['lines'][-1]['recipe_id']=rid
    if len(d['lines']) > 100: raise ValueError('Usa hasta 100 partidas por cotización.')
    for row in payload.get('tiers', []):
        lo = number(row.get('minimum'), 'Desde', minimum=1, maximum=1000000)
        raw = row.get('maximum')
        hi = None if raw is None or raw == '' else number(raw, 'Hasta', minimum=lo, maximum=1000000)
        if lo != lo.to_integral() or (hi is not None and hi != hi.to_integral()):
            raise ValueError('Los rangos de volumen deben usar cantidades enteras.')
        d['tiers'].append(dict(minimum=int(lo), maximum=int(hi) if hi is not None else None,
            price=cents(row.get('price')) / 100, reference_discount=float(number(row.get('reference_discount', 0), 'Descuento de referencia', maximum=100)),
            note=str(row.get('note') or '').strip()))
    d['tiers'].sort(key=lambda r: r['minimum'])
    for previous, current in zip(d['tiers'], d['tiers'][1:]):
        if previous['maximum'] is None or previous['maximum'] >= current['minimum']:
            raise ValueError('Los rangos de volumen se superponen. Ajusta Desde y Hasta.')
    images = payload.get('images', [])
    if len(images) > 4: raise ValueError('Puedes guardar hasta cuatro imágenes por cotización.')
    for pic in images:
        try:
            raw = base64.b64decode(pic['data'], validate=True)
            if len(raw) > 3 * 1024 * 1024: raise ValueError()
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in ('PNG', 'JPEG', 'WEBP') or image.width * image.height > 25000000: raise ValueError()
                mime = Image.MIME[image.format]
                image.verify()
        except Exception:
            raise ValueError('Usa imágenes PNG, JPG o WEBP válidas, hasta 3 MB y 25 megapíxeles cada una.') from None
        d['images'].append(dict(data=pic['data'], mime=mime, caption=str(pic.get('caption', 'Prototipo'))[:300]))
    subtotal = sum(row['amount_cents'] for row in d['lines'])
    discount = int((Decimal(subtotal) * Decimal(str(d['discount'])) / 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    tax = int((Decimal(subtotal - discount) * Decimal('0.16')).quantize(Decimal('1'), rounding=ROUND_HALF_UP)) if d['iva'] else 0
    d['totals'] = dict(subtotal=subtotal, discount=discount, tax=tax, total=subtotal-discount+tax)
    return d


def apply_volume(payload, line_index):
    d = calculate(payload)
    if not 0 <= line_index < len(d['lines']): raise ValueError('Selecciona una partida para aplicar volumen.')
    line = d['lines'][line_index]
    tier = next((t for t in d['tiers'] if t['minimum'] <= line['quantity'] and
                 (t['maximum'] is None or line['quantity'] <= t['maximum'])), None)
    if not tier or tier['price'] <= 0: raise ValueError('No hay un rango con precio positivo para esa cantidad.')
    line['price'] = tier['price']  # The tier discount is a reference, never an additional deduction.
    return calculate(d)


def _get(conn, quote_id): return fetch(conn, 'quotations', quote_id, 'La cotización ya no está disponible.')


def _revision(row, expected): same_revision(row, expected, 'La cotización cambió en otra ventana. Actualiza antes de guardar.')


def create_quote(copy_id=None):
    with connect(write=True) as conn:
        d = defaults() if copy_id is None else json.loads(_get(conn, copy_id)['payload'])
        if copy_id is not None:
            d.update(issued_on=defaults()['issued_on'], valid_until=defaults()['valid_until'])
        d = calculate(d)
        qid, code = _code(conn, 'quotations', 'COT')
        stamp = timestamp()
        conn.execute('INSERT INTO quotations(id,code,payload,total_cents,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                     (qid, code, json.dumps(d, ensure_ascii=False), d['totals']['total'], stamp, stamp))
        return qid


def save_quote(quote_id, payload, *, expected_revision, status='Borrador', volume_line=None):
    if status not in ('Borrador', 'Enviada', 'Aceptada', 'Cancelada'): raise ValueError('Estado no válido.')
    d = apply_volume(payload, volume_line) if volume_line is not None else calculate(payload)
    if status in ('Enviada', 'Aceptada') and (not d['client'] or not d['lines']):
        raise ValueError('Agrega cliente y partidas antes de enviar o aceptar la cotización.')
    with connect(write=True) as conn:
        row = _get(conn, quote_id)
        _revision(row, expected_revision)
        if row['order_id'] or conn.execute('SELECT 1 FROM quotation_payments WHERE quote_id=?', (quote_id,)).fetchone():
            raise ValueError('Conserva el alcance con pedido o historial de pagos. Duplica la cotización para modificarlo.')
        conn.execute('UPDATE quotations SET payload=?,total_cents=?,status=?,revision=revision+1,updated_at=? WHERE id=?',
            (json.dumps(d, ensure_ascii=False), d['totals']['total'], status, timestamp(), quote_id))


def get_quote(quote_id):
    with connect() as conn:
        row = dict(_get(conn, quote_id))
        sale = conn.execute('SELECT id,status FROM sales WHERE quote_id=?', (quote_id,)).fetchone()
        row['sale_id'] = sale['id'] if sale else None
        row['sale_status'] = sale['status'] if sale else None
        row['payments'] = [dict(p) for p in conn.execute('SELECT * FROM quotation_payments WHERE quote_id=? ORDER BY id', (quote_id,))]
        treasury.payment_labels(conn,'quote',row['payments'])
    row['data'] = json.loads(row.pop('payload'))
    row['paid_cents'] = sum(p['amount_cents'] for p in row['payments'] if not p['voided_at'])
    row['balance_cents'] = row['total_cents'] - row['paid_cents']
    row['locked'] = bool(row['order_id'] or row['payments'] or row['sale_id'])
    return row


def set_status(quote_id, status, *, expected_revision):
    if status not in ('Borrador', 'Enviada', 'Aceptada', 'Cancelada'): raise ValueError('Estado no válido.')
    with connect(write=True) as conn:
        row = _get(conn, quote_id)
        _revision(row, expected_revision)
        data = json.loads(row['payload'])
        if row['order_id'] and status != 'Aceptada': raise ValueError('Esta cotización ya originó un pedido y conserva su aceptación.')
        if status in ('Enviada', 'Aceptada') and (not data['client'] or not data['lines']):
            raise ValueError('Completa cliente y partidas antes de enviar o aceptar.')
        if status == 'Cancelada' and conn.execute('SELECT 1 FROM quotation_payments WHERE quote_id=? AND voided_at IS NULL', (quote_id,)).fetchone():
            raise ValueError('La cotización tiene pagos vigentes. Revisa esos registros antes de cancelarla.')
        conn.execute('UPDATE quotations SET status=?,revision=revision+1,updated_at=? WHERE id=?', (status, timestamp(), quote_id))


def list_quotes():
    with connect() as conn:
        return [dict(r) for r in conn.execute('''SELECT q.id,q.code,q.status,q.total_cents,q.order_id,q.updated_at,
            json_extract(q.payload,'$.client') client,json_extract(q.payload,'$.project') project,
            json_extract(q.payload,'$.valid_until') valid_until,
            COALESCE((SELECT SUM(amount_cents) FROM quotation_payments WHERE quote_id=q.id AND voided_at IS NULL),0) paid_cents
            FROM quotations q ORDER BY q.id DESC''')]


def record_payment(quote_id, amount, paid_on, method, concept, reference='', *, request_key, expected_revision, account_id=None):
    amount = cents(amount)
    if amount <= 0 or not method.strip() or not concept.strip() or not request_key:
        raise ValueError('Indica monto positivo, método y concepto del pago recibido.')
    try: paid_on = date.fromisoformat(str(paid_on)).isoformat()
    except ValueError: raise ValueError('Revisa la fecha del pago.') from None
    if paid_on > now().date().isoformat(): raise ValueError('Registra solo pagos recibidos; la fecha no puede ser futura.')
    values = (quote_id, amount, paid_on, method.strip(), reference.strip(), concept.strip())
    with connect(write=True) as conn:
        prior = conn.execute('SELECT * FROM quotation_payments WHERE request_key=?', (request_key,)).fetchone()
        if prior:
            if tuple(prior[k] for k in ('quote_id','amount_cents','paid_on','method','reference','concept')) != values:
                raise ValueError('El pago ya se guardó con otros datos. Abre un registro nuevo.')
            treasury.check_retry(conn,'quote',prior['id'],account_id)
            return prior['id']
        q = _get(conn, quote_id)
        _revision(q, expected_revision)
        if q['status'] == 'Cancelada' or not json.loads(q['payload'])['client']:
            raise ValueError('Revisa el cliente y el estado de la cotización antes de registrar pagos.')
        paid = conn.execute('SELECT COALESCE(SUM(amount_cents),0) FROM quotation_payments WHERE quote_id=? AND voided_at IS NULL', (quote_id,)).fetchone()[0]
        if amount > q['total_cents'] - paid: raise ValueError('El pago supera el saldo pendiente. Revisa el monto.')
        pid, code = _code(conn, 'quotation_payments', 'REC')
        conn.execute('''INSERT INTO quotation_payments(id,code,quote_id,amount_cents,paid_on,method,reference,concept,request_key,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)''', (pid, code, *values, request_key, timestamp()))
        conn.execute('UPDATE quotations SET revision=revision+1,updated_at=? WHERE id=?', (timestamp(), quote_id))
        treasury.link_payment(conn,'quote',pid,account_id)
        return pid


def void_payment(payment_id, reason):
    if not reason.strip(): raise ValueError('Indica por qué se anula este registro de pago.')
    with connect(write=True) as conn:
        row = conn.execute('SELECT * FROM quotation_payments WHERE id=?', (payment_id,)).fetchone()
        if not row: raise ValueError('El pago no existe.')
        if row['voided_at']: return
        conn.execute('UPDATE quotation_payments SET void_reason=?,voided_at=? WHERE id=?', (reason.strip(), timestamp(), payment_id))
        conn.execute('UPDATE quotations SET revision=revision+1,updated_at=? WHERE id=?', (timestamp(), row['quote_id']))


def convert_to_order(quote_id, deadline='', *, expected_revision):
    """One atomic draft order. No stock, manufacturing, or payment is inferred."""
    due = parse_deadline(deadline)
    with connect(write=True) as conn:
        row = _get(conn, quote_id)
        if row['order_id']: return row['order_id']
        _revision(row, expected_revision)
        data = calculate(json.loads(row['payload']))
        if row['status'] != 'Aceptada': raise ValueError('Marca la cotización como Aceptada antes de crear el pedido.')
        from services import commerce
        return commerce.draft_order(conn, 'quote', row, data, due, project=data['project'] or data['reference'] or row['code'],
            note=f"Origen: {row['code']} · Total comercial {money(row['total_cents'])} MXN.\n{data['notes']}\nEntrega estimada: {data['lead_time']}",
            item_note=lambda line: f"{row['code']} · Precio unitario {money(cents(line['price']))} MXN. Define el despiece o reutiliza una receta.",
            missing='Indica cliente y al menos una partida marcada Para fabricar.', need_client=True)
