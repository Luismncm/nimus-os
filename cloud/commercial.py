"""Commercial routes of the cloud app: sales and collections, quotations and their documents. Administration only.

Same services as views/sales.py and views/quotations.py. Totals are always computed by the service from the
lines (quotations.calculate), never trusted from the screen; every change carries the revision the screen
loaded, and creating a sale or a payment carries a request key.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from cloud import auth
from cloud.routes import write

router = APIRouter(prefix='/api')
STATUSES = ('Borrador', 'Enviada', 'Aceptada', 'Cancelada')


class Draft(BaseModel):
    payload: dict


class DirectSale(BaseModel):
    payload: dict
    sold_on: str
    due_on: str = ''
    channel: str = 'Venta al público'
    request_key: str


class Revision(BaseModel):
    expected_revision: int
    expected_quote_revision: int | None = None


class DueDate(Revision):
    due_on: str = ''


class Cancel(Revision):
    reason: str


class OrderFrom(Revision):
    deadline: str = ''


class Void(BaseModel):
    reason: str


class QuoteSave(BaseModel):
    payload: dict
    expected_revision: int
    status: str = 'Borrador'


class QuoteStatus(BaseModel):
    status: str
    expected_revision: int


class QuotePayment(BaseModel):
    amount: float
    paid_on: str
    method: str
    concept: str
    reference: str = ''
    account_id: int
    request_key: str
    expected_revision: int


class QuoteSale(BaseModel):
    sold_on: str
    due_on: str = ''
    channel: str = 'B2B'
    request_key: str
    expected_revision: int


def _lines(data):
    return [dict(description=l['description'], quantity=l['quantity'], price=l['price'], produce=bool(l.get('produce')),
                 amount_cents=l['amount_cents'], recipe_id=l.get('recipe_id')) for l in data.get('lines', [])]


def _payments(rows):
    return [dict(id=p['id'], code=p.get('code') or '', amount_cents=p['amount_cents'], paid_on=p['paid_on'], method=p.get('method') or '',
                 concept=p.get('concept') or '', reference=p.get('reference') or '', account=p.get('account_name') or '',
                 voided=bool(p.get('voided_at')), void_reason=p.get('void_reason') or '') for p in rows]


@router.post('/comercial/calcular')
def calculate(body: Draft, user=Depends(auth.admin)):
    """Totals of a draft (subtotal, discount, IVA, total) with the same rules the save applies."""
    from services import quotations as q
    d = write(q.calculate, body.payload)
    return dict(lines=_lines(d), totals=d['totals'])


@router.get('/ventas')
def sales(desde: str, hasta: str, buscar: str = '', canal: str = 'Todos', cobranza: str = 'Todos', user=Depends(auth.admin)):
    from services import sales as s
    r = write(s.report, desde, hasta, search=buscar, channel=canal, payment_status=cobranza)
    rows = [dict(id=x['id'], code=x['code'], sold_on=x['sold_on'], client=x['client'] or '', project=x['project'] or '', origin=x['origin'],
                 quote=x['quote_code'] or '', channel=x['channel'], status=x['status'], payment_status=x['payment_status'],
                 due_on=x['due_on'] or None, overdue=x['overdue'], total_cents=x['total_cents'], paid_cents=x['paid_cents'],
                 balance_cents=x['balance_cents'], order_id=x['order_id']) for x in r['rows']]
    return dict(rows=rows, channels=s.CHANNELS, count=r['count'], sold_cents=r['sold_cents'], collected_cents=r['collected_cents'],
                balance_cents=r['balance_cents'], total_balance_cents=r['total_balance_cents'], overdue_cents=r['overdue_cents'])


@router.get('/ventas/{sale_id}')
def sale(sale_id: int, user=Depends(auth.admin)):
    from services import sales as s
    x = write(s.get_sale, sale_id)
    d = x['data']
    return dict(id=x['id'], code=x['code'], sold_on=x['sold_on'], due_on=x['due_on'] or None, channel=x['channel'], status=x['status'],
                payment_status=x['payment_status'], client=x['client'] or '', project=x['project'] or '', quote_id=x['quote_id'],
                quote=x['quote_code'] or '', order_id=x['order_id'], revision=x['revision'], quote_revision=x['quote_revision'],
                total_cents=x['total_cents'], paid_cents=x['paid_cents'], balance_cents=x['balance_cents'], overdue=x['overdue'],
                cancel_reason=x.get('cancel_reason') or '', notes=d.get('notes') or '', lines=_lines(d), totals=d['totals'],
                payments=_payments(x['payments']), produce=any(l.get('produce') for l in d.get('lines', [])))


@router.post('/ventas')
def sale_create(body: DirectSale, user=Depends(auth.admin)):
    from services import sales as s
    if body.channel not in s.CHANNELS:
        raise HTTPException(status_code=400, detail='Selecciona un canal de venta.')
    return dict(ok=True, id=write(s.create_direct, body.payload, body.sold_on, body.due_on, body.channel, request_key=body.request_key))


@router.post('/ventas/{sale_id}/pagos/{payment_id}/anular')
def sale_void(sale_id: int, payment_id: int, body: Void, user=Depends(auth.admin)):
    from services import sales as s
    write(s.void_payment, sale_id, payment_id, body.reason)
    return dict(ok=True)


@router.post('/ventas/{sale_id}/vencimiento')
def sale_due(sale_id: int, body: DueDate, user=Depends(auth.admin)):
    from services import sales as s
    write(s.set_due_date, sale_id, body.due_on, expected_revision=body.expected_revision)
    return dict(ok=True)


@router.post('/ventas/{sale_id}/cancelar')
def sale_cancel(sale_id: int, body: Cancel, user=Depends(auth.admin)):
    from services import sales as s
    write(s.cancel, sale_id, body.reason, expected_revision=body.expected_revision)
    return dict(ok=True)


@router.post('/ventas/{sale_id}/pedido')
def sale_order(sale_id: int, body: OrderFrom, user=Depends(auth.admin)):
    from services import sales as s
    order = write(s.create_order, sale_id, body.deadline, expected_revision=body.expected_revision,
                  expected_quote_revision=body.expected_quote_revision)
    return dict(ok=True, order_id=order)


@router.get('/ventas/{sale_id}/documento', response_class=HTMLResponse)
def sale_document(sale_id: int, user=Depends(auth.admin)):
    from services import sales as s
    from services.quotation_document import document
    return HTMLResponse(document(write(s.get_sale, sale_id), receipt=True, sale=True))


@router.get('/cotizaciones')
def quotes(user=Depends(auth.admin)):
    from services.quotations import list_quotes
    return dict(rows=[dict(id=r['id'], code=r['code'], status=r['status'], client=r['client'] or '', project=r['project'] or '',
                           total_cents=r['total_cents'], paid_cents=r['paid_cents'], valid_until=r['valid_until'],
                           order_id=r['order_id'], updated_at=r['updated_at']) for r in list_quotes()],
                statuses=STATUSES)


@router.get('/cotizaciones/{quote_id}')
def quote(quote_id: int, user=Depends(auth.admin)):
    from services import sales as s, treasury
    from services.quotations import get_quote
    x = write(get_quote, quote_id)
    return dict(id=x['id'], code=x['code'], status=x['status'], revision=x['revision'], order_id=x['order_id'], sale_id=x['sale_id'],
                sale_status=x['sale_status'], locked=x['locked'], total_cents=x['total_cents'], paid_cents=x['paid_cents'],
                balance_cents=x['balance_cents'], payload=x['data'], lines=_lines(x['data']), totals=x['data']['totals'],
                payments=_payments(x['payments']), channels=s.CHANNELS,
                accounts=[dict(id=a['id'], name=a['name'], kind=a['kind']) for a in treasury.accounts(active_only=True)])


@router.post('/cotizaciones')
def quote_create(copy_id: int | None = None, user=Depends(auth.admin)):
    """A new draft, or a copy of another quotation with fresh dates (to change a locked scope)."""
    from services.quotations import create_quote
    return dict(ok=True, id=write(create_quote, copy_id))


@router.put('/cotizaciones/{quote_id}')
def quote_save(quote_id: int, body: QuoteSave, user=Depends(auth.admin)):
    from services.quotations import save_quote
    if body.status not in STATUSES:
        raise HTTPException(status_code=400, detail='Estado no válido.')
    write(save_quote, quote_id, body.payload, expected_revision=body.expected_revision, status=body.status)
    return dict(ok=True)


@router.post('/cotizaciones/{quote_id}/estado')
def quote_status(quote_id: int, body: QuoteStatus, user=Depends(auth.admin)):
    from services.quotations import set_status
    write(set_status, quote_id, body.status, expected_revision=body.expected_revision)
    return dict(ok=True)


@router.post('/cotizaciones/{quote_id}/pagos')
def quote_payment(quote_id: int, body: QuotePayment, user=Depends(auth.admin)):
    """An advance on an accepted quotation, before (or without) its sale."""
    from services.quotations import record_payment
    pid = write(record_payment, quote_id, body.amount, body.paid_on, body.method, body.concept, body.reference,
                request_key=body.request_key, expected_revision=body.expected_revision, account_id=body.account_id)
    return dict(ok=True, payment_id=pid)


@router.post('/cotizaciones/{quote_id}/venta')
def quote_sale(quote_id: int, body: QuoteSale, user=Depends(auth.admin)):
    from services import sales as s
    if body.channel not in s.CHANNELS:
        raise HTTPException(status_code=400, detail='Selecciona un canal de venta.')
    sid = write(s.from_quote, quote_id, body.sold_on, body.due_on, body.channel, request_key=body.request_key,
                expected_revision=body.expected_revision)
    return dict(ok=True, sale_id=sid)


@router.post('/cotizaciones/{quote_id}/pedido')
def quote_order(quote_id: int, body: OrderFrom, user=Depends(auth.admin)):
    from services.quotations import convert_to_order
    return dict(ok=True, order_id=write(convert_to_order, quote_id, body.deadline, expected_revision=body.expected_revision))


@router.get('/cotizaciones/{quote_id}/documento', response_class=HTMLResponse)
def quote_document(quote_id: int, recibo: bool = False, user=Depends(auth.admin)):
    from services.quotation_document import document
    from services.quotations import get_quote
    return HTMLResponse(document(write(get_quote, quote_id), receipt=recibo))
