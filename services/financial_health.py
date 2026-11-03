"""Financial health: how long the cash lasts, how much of the spending sales cover and what it takes to break even.

One read (load) and a pure calculation (health) over complete months, so a half month never skews an average.
Amounts are in cents as recorded (sales and expenses with IVA when they include it); shares in percent.
"""
from __future__ import annotations

from collections import defaultdict
from contextlib import nullcontext
from datetime import date

from db import connect

WINDOWS = (3, 6)
ONE_TIME = 'Desarrollo / único'
HEALTHY, WATCH, CRITICAL = 'Sano', 'Atención', 'Crítico'


def load(conn=None) -> dict:
    with (nullcontext(conn) if conn is not None else connect()) as conn:
        months = defaultdict(lambda: dict(sold=0, collected=0, spent=0, one_time=0, paid=0, injected=0))
        live = 'NOT EXISTS(SELECT 1 FROM sales_trash t WHERE t.sale_id=s.id)'
        def add(field, sql):
            for month, value in conn.execute(sql):
                if month:
                    months[month][field] += value or 0
        add('sold', f"SELECT substr(sold_on,1,7),SUM(total_cents) FROM sales s WHERE status='Activa' AND {live} GROUP BY 1")
        add('collected', f"""SELECT substr(p.paid_on,1,7),SUM(p.amount_cents) FROM sales_payment_ledger p JOIN sales s ON s.id=p.sale_id
            WHERE p.voided_at IS NULL AND {live} GROUP BY 1""")
        add('spent', f"SELECT substr(expense_on,1,7),SUM(total_cents) FROM expenses WHERE status='Activo' AND cost_type<>'{ONE_TIME}' GROUP BY 1")
        add('one_time', f"SELECT substr(expense_on,1,7),SUM(total_cents) FROM expenses WHERE status='Activo' AND cost_type='{ONE_TIME}' GROUP BY 1")
        add('paid', """SELECT substr(p.paid_on,1,7),SUM(p.amount_cents) FROM expense_payments p JOIN expenses e ON e.id=p.expense_id
            WHERE p.voided_at IS NULL AND e.status='Activo' GROUP BY 1""")
        # Partner money that reaches the accounts, as Tesorería counts it: injections in, refunds out.
        add('injected', '''SELECT substr(moved_on,1,7),SUM(amount_cents*sign) FROM capital_movements
            WHERE voided_at IS NULL AND sign<>0 AND linked_expense_id IS NULL GROUP BY 1''')
        from services import cash_projection, costing
        cash = cash_projection.overview(conn)
        receivable = conn.execute(f'''SELECT COALESCE(SUM(MAX(0,s.total_cents-COALESCE((SELECT SUM(amount_cents) FROM sales_payment_ledger p
            WHERE p.sale_id=s.id AND p.voided_at IS NULL),0))),0) FROM sales s WHERE status='Activa' AND {live}''').fetchone()[0]
        payable = conn.execute('''SELECT COALESCE(SUM(MAX(0,e.total_cents-COALESCE((SELECT SUM(amount_cents) FROM expense_payments p
            WHERE p.expense_id=e.id AND p.voided_at IS NULL),0)-COALESCE((SELECT SUM(amount_cents) FROM partner_expense_settlements x
            WHERE x.expense_id=e.id),0))),0) FROM expenses e WHERE status='Activo' ''').fetchone()[0]
        partner = conn.execute("""SELECT COALESCE(SUM(CASE WHEN movement='Reembolso al socio' THEN -amount_cents ELSE amount_cents END),0)
            FROM capital_movements WHERE voided_at IS NULL""").fetchone()[0]
        sales = [r[0] for r in conn.execute(f"SELECT id FROM sales s WHERE status='Activa' AND {live}")]
        margins = [costing.sale_margin(sid, conn) for sid in sales]
        costed = [m for m in margins if m['complete']]
        unclassified = conn.execute("""SELECT COUNT(*) FROM expenses WHERE status='Activo'
            AND (category IN ('Sin clasificar','') OR subtype='Gasto no clasificado')""").fetchone()[0]
    return dict(months=dict(months), cash_cents=cash['total_cents'] or 0, cash_estimated=cash['estimated'], unreconciled=cash['missing'],
                undated=cash['undated'], receivable_cents=receivable, payable_cents=payable, partner_cents=partner,
                margin=dict(net=sum(m['net_revenue_cents'] for m in costed), cost=sum(m['cost_cents'] for m in costed),
                            costed=len(costed), sales=len(margins)),
                unclassified=unclassified)


def window(today: date, count: int) -> list[str]:
    """The last complete months before today's, oldest first."""
    index = today.year * 12 + today.month - 1
    return [f'{(index - back) // 12}-{(index - back) % 12 + 1:02d}' for back in range(count, 0, -1)]


def _ratio(part, whole):
    return round(100 * part / whole, 1) if whole else None


def _tone(value, healthy, watch, *, higher_is_better=True):
    if value is None:
        return None
    if not higher_is_better:
        value, healthy, watch = -value, -healthy, -watch
    return HEALTHY if value >= healthy else WATCH if value >= watch else CRITICAL


def health(data: dict, today: date, count: int = 3) -> dict:
    span = window(today, count)
    rows = [data['months'].get(m, {}) for m in span]
    avg = {k: sum(r.get(k, 0) for r in rows) // count for k in ('sold', 'collected', 'spent', 'one_time', 'paid', 'injected')}
    burn = avg['paid'] - avg['collected']
    cash = data['cash_cents']
    runway = round(cash / burn, 1) if burn > 0 else None
    margin = _ratio(data['margin']['net'] - data['margin']['cost'], data['margin']['net'])
    break_even = round(avg['spent'] * 100 / margin) if margin and margin > 0 else None
    coverage = _ratio(avg['sold'], avg['spent'])
    inflow = avg['injected'] + avg['collected']
    partner_share = _ratio(max(0, avg['injected']), inflow) if inflow > 0 else None
    sold_total = sum(m['sold'] for m in data['months'].values())
    collected_total = sum(m['collected'] for m in data['months'].values())
    collection = _ratio(min(collected_total, sold_total), sold_total)
    liquid = cash + data['receivable_cents']
    tones = dict(runway=HEALTHY if burn <= 0 else _tone(runway, 6, 3), coverage=_tone(coverage, 100, 60), margin=_tone(margin, 40, 25),
                 partner=_tone(partner_share, 20, 50, higher_is_better=False), collection=_tone(collection, 85, 70))
    states = [t for t in tones.values() if t]
    overall = CRITICAL if CRITICAL in states else WATCH if WATCH in states else HEALTHY
    return dict(months=span, average=avg, cash_cents=cash, burn_cents=burn, runway_months=runway,
                result_cents=avg['sold'] - avg['spent'], coverage_percent=coverage, margin_percent=margin,
                break_even_cents=break_even, break_even_multiple=round(break_even / avg['sold'], 1) if break_even and avg['sold'] else None,
                partner_share_percent=partner_share, collection_percent=collection,
                receivable_cents=data['receivable_cents'], payable_cents=data['payable_cents'],
                liquidity=round(liquid / data['payable_cents'], 1) if data['payable_cents'] else None,
                partner_cents=data['partner_cents'], tones=tones, overall=overall, verdict=verdict(coverage, partner_share, runway, burn))


def verdict(coverage, partner_share, runway, burn) -> str:
    if coverage is not None and coverage >= 100 and burn <= 0:
        return 'La operación se sostiene con sus propias ventas: lo vendido cubre el gasto y la caja no disminuye.'
    if partner_share is not None and partner_share > 50:
        text = 'La operación todavía no se sostiene sola: la mayor parte del dinero que entra viene del socio, no de las ventas.'
    elif coverage is not None and coverage < 100:
        text = 'Las ventas aún no cubren el gasto mensual: la diferencia sale de la caja.'
    else:
        text = 'La caja disminuye cada mes aunque las ventas cubren el gasto: revisa cobranza y pagos.'
    if runway is not None and runway < 3:
        text += f' Al ritmo actual la caja alcanza para {runway:g} meses.'
    return text


def trend(data: dict, today: date, count: int = 6) -> list[dict]:
    """Money in and out of the accounts per month, the current month included."""
    span = window(today, count - 1) + [today.strftime('%Y-%m')]
    return [dict(month=m, collected=data['months'].get(m, {}).get('collected', 0), injected=data['months'].get(m, {}).get('injected', 0),
                 paid=data['months'].get(m, {}).get('paid', 0)) for m in span]
