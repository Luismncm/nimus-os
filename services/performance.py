"""Business performance for a period, compared with the period just before it.

Everything is read in one pass (load) and aggregated by pure functions, so a period change never queries again.
"""
from __future__ import annotations

from datetime import date, timedelta

from db import connect
from utils.dates import now

PERIODS = ('Este mes', 'Mes anterior', 'Últimos 90 días', 'Este año')


def period(name: str, today: date | None = None) -> tuple[date, date]:
    today = today or now().date()
    if name == 'Mes anterior':
        end = today.replace(day=1) - timedelta(days=1)
        return end.replace(day=1), end
    if name == 'Últimos 90 días':
        return today - timedelta(days=89), today
    if name == 'Este año':
        return today.replace(month=1, day=1), today
    return today.replace(day=1), today


def _last_year(day: date) -> date:
    try:
        return day.replace(year=day.year - 1)
    except ValueError:  # 29 de febrero
        return day.replace(year=day.year - 1, day=28)


def previous(start: date, end: date) -> tuple[date, date]:
    """The span to compare with: month to date against the same days of last month, a year against last year."""
    if start.day == 1 and (start.year, start.month) == (end.year, end.month):
        prior_end_of_month = start - timedelta(days=1)
        prior_start = prior_end_of_month.replace(day=1)
        return prior_start, min(prior_start + (end - start), prior_end_of_month)
    if (start.month, start.day) == (1, 1) and start.year == end.year:
        return _last_year(start), _last_year(end)
    prior_end = start - timedelta(days=1)
    return prior_end - (end - start), prior_end


def load(conn=None) -> dict:
    def read(conn):
        rows = lambda sql: [dict(r) for r in conn.execute(sql)]
        live = 'NOT EXISTS(SELECT 1 FROM sales_trash t WHERE t.sale_id=s.id)'
        return dict(
            sales=rows(f"""SELECT s.id,s.status,s.total_cents,s.sold_on,json_extract(s.payload,'$.client') client
                FROM sales s WHERE {live}"""),
            receipts=rows(f"""SELECT p.amount_cents,p.paid_on FROM sales_payment_ledger p JOIN sales s ON s.id=p.sale_id
                WHERE p.voided_at IS NULL AND {live}"""),
            expenses=rows("SELECT total_cents,expense_on FROM expenses WHERE status='Activo'"),
            payments=rows("""SELECT p.amount_cents,p.paid_on FROM expense_payments p JOIN expenses e ON e.id=p.expense_id
                WHERE p.voided_at IS NULL AND e.status='Activo'"""),
            # Customer deliveries only: prototypes and prints to stock have no client or promised date.
            # Delivered on the day dispatch was checked, otherwise the day the order was closed.
            deliveries=rows("""SELECT o.id,o.code,o.client,o.deadline,substr(o.created_at,1,10) created_on,
                substr(COALESCE((SELECT checked_at FROM order_stages g WHERE g.order_id=o.id AND g.stage='dispatch'),o.updated_at),1,10) delivered_on
                FROM orders o WHERE o.status='Entregado'
                AND o.id NOT IN (SELECT order_id FROM development_projects)
                AND o.id NOT IN (SELECT order_id FROM stock_runs)
                AND o.id NOT IN (SELECT order_id FROM order_cancellations)"""),
            jobs=rows("""SELECT j.id,j.machine_id,j.quantity_completed,substr(j.completed_at,1,10) completed_on,
                m.total_seconds,m.tracking_complete FROM production_jobs j LEFT JOIN production_metrics m ON m.job_id=j.id
                WHERE j.status='Terminado' AND j.completed_at IS NOT NULL"""),
            failures=rows("""SELECT f.rejected_units,substr(f.created_at,1,10) created_on,j.machine_id
                FROM production_failures f JOIN production_jobs j ON j.id=f.job_id"""),
            machines=rows('SELECT id,code,name,archived FROM machines ORDER BY code'),
        )
    if conn is not None:
        return read(conn)
    with connect() as conn:
        return read(conn)


def _within(rows, field, start, end):
    lo, hi = start.isoformat(), end.isoformat()
    return [r for r in rows if r[field] and lo <= r[field][:10] <= hi]


def _ratio(part, whole):
    return round(100 * part / whole, 1) if whole else None


def summary(data: dict, start: date, end: date) -> dict:
    sales = [s for s in _within(data['sales'], 'sold_on', start, end) if s['status'] == 'Activa']
    sold = sum(s['total_cents'] for s in sales)
    collected = sum(r['amount_cents'] for r in _within(data['receipts'], 'paid_on', start, end))
    paid_out = sum(r['amount_cents'] for r in _within(data['payments'], 'paid_on', start, end))
    delivered = _within(data['deliveries'], 'delivered_on', start, end)
    promised = [o for o in delivered if o['deadline']]
    on_time = sum(o['delivered_on'] <= o['deadline'] for o in promised)
    lead = [(date.fromisoformat(o['delivered_on']) - date.fromisoformat(o['created_on'])).days for o in delivered]
    jobs = _within(data['jobs'], 'completed_on', start, end)
    pieces = sum(j['quantity_completed'] for j in jobs)
    rejected = sum(f['rejected_units'] for f in _within(data['failures'], 'created_on', start, end))
    timed = [j for j in jobs if j['tracking_complete']]
    return dict(
        sold_cents=sold, sales_count=len(sales), ticket_cents=sold // len(sales) if sales else None,
        collected_cents=collected, expenses_cents=sum(e['total_cents'] for e in _within(data['expenses'], 'expense_on', start, end)),
        paid_out_cents=paid_out, cash_cents=collected - paid_out,
        delivered=len(delivered), promised=len(promised), on_time=on_time, on_time_percent=_ratio(on_time, len(promised)),
        lead_days=round(sum(lead) / len(lead), 1) if lead else None,
        lots=len(jobs), pieces=pieces, rejected=rejected, reject_percent=_ratio(rejected, pieces + rejected),
        machine_hours=round(sum(j['total_seconds'] for j in timed) / 3600, 1), untimed_lots=len(jobs) - len(timed),
    )


def compare(data: dict, start: date, end: date) -> dict:
    prior = previous(start, end)
    return dict(start=start, end=end, prior_start=prior[0], prior_end=prior[1],
                current=summary(data, start, end), prior=summary(data, *prior))


def months(data: dict, end: date, count: int = 6) -> list[dict]:
    """The last few calendar months up to the one containing end, oldest first; the current month runs to end."""
    first = end.replace(day=1)
    rows = []
    for back in range(count - 1, -1, -1):
        year, month = divmod(first.year * 12 + first.month - 1 - back, 12)
        start = date(year, month + 1, 1)
        stop = min(end, (start + timedelta(days=32)).replace(day=1) - timedelta(days=1))
        s = summary(data, start, stop)
        rows.append(dict(month=start.strftime('%Y-%m'), sold_cents=s['sold_cents'], collected_cents=s['collected_cents'],
                         expenses_cents=s['expenses_cents'], pieces=s['pieces'], delivered=s['delivered']))
    return rows


def by_machine(data: dict, start: date, end: date) -> list[dict]:
    hours_available = ((end - start).days + 1) * 24
    jobs = _within(data['jobs'], 'completed_on', start, end)
    failures = _within(data['failures'], 'created_on', start, end)
    rows = []
    for m in data['machines']:
        own = [j for j in jobs if j['machine_id'] == m['id']]
        if m['archived'] and not own:
            continue
        hours = sum(j['total_seconds'] for j in own if j['tracking_complete']) / 3600
        pieces = sum(j['quantity_completed'] for j in own)
        rejected = sum(f['rejected_units'] for f in failures if f['machine_id'] == m['id'])
        rows.append(dict(code=m['code'], name=m['name'], lots=len(own), pieces=pieces, hours=round(hours, 1),
                         use_percent=_ratio(hours, hours_available), rejected=rejected,
                         reject_percent=_ratio(rejected, pieces + rejected)))
    return rows


def top_clients(data: dict, start: date, end: date, limit: int = 5) -> list[dict]:
    totals: dict[str, list[int]] = {}
    for s in _within(data['sales'], 'sold_on', start, end):
        if s['status'] == 'Activa':
            entry = totals.setdefault((s['client'] or 'Sin cliente').strip() or 'Sin cliente', [0, 0])
            entry[0] += s['total_cents'];entry[1] += 1
    ranked = sorted(totals.items(), key=lambda kv: -kv[1][0])[:limit]
    sold = sum(v[0] for v in totals.values())
    return [dict(client=k, sold_cents=v[0], count=v[1], share_percent=_ratio(v[0], sold)) for k, v in ranked]
