"""Every sale ever made, grouped by period, and the shares that say where the money comes from.

One read (load) and pure aggregations; amounts are in cents, shares in percent with one decimal.
"""
from __future__ import annotations

import json
import re
import unicodedata

from db import connect

GROUPINGS = ('Mes', 'Trimestre', 'Año')
ORIGIN_LINE, CUSTOM_LINE = 'Colección Origen', 'Personalizado y otros'
ORIGIN_UNKNOWN = 'ORIGEN · SIN MODELO'


def load(conn=None) -> list[dict]:
    def read(conn):
        origin = {r[0] for r in conn.execute('SELECT recipe_id FROM origin_recipes')}
        models = {plain(r[0]).split()[0] for r in conn.execute('''SELECT DISTINCT p.name FROM origin_recipes o
            JOIN recipe_versions v ON v.id=o.recipe_id JOIN catalog_products p ON p.id=v.product_id''') if plain(r[0])}
        # Only the lines are read from the payload: it can also carry large images.
        rows = [dict(r) for r in conn.execute('''SELECT s.id,s.code,s.status,s.total_cents,s.sold_on,s.channel,s.quote_id,
            json_extract(s.payload,'$.client') client,json_extract(s.payload,'$.lines') lines,
            COALESCE((SELECT SUM(p.amount_cents) FROM sales_payment_ledger p WHERE p.sale_id=s.id AND p.voided_at IS NULL),0) paid_cents
            FROM sales s WHERE NOT EXISTS(SELECT 1 FROM sales_trash t WHERE t.sale_id=s.id) ORDER BY s.sold_on,s.id''')]
        for r in rows:
            r['client'] = (r['client'] or '').strip() or 'Sin cliente'
            r['origin'] = 'Cotización' if r['quote_id'] else 'Directa'
            r['lines'] = [dict(zip(('product', 'line'), classify(l.get('description'), l.get('recipe_id'), origin, models)),
                               quantity=l.get('quantity') or 0, amount_cents=l.get('amount_cents') or 0) for l in json.loads(r['lines'] or '[]')]
        return rows
    if conn is not None:
        return read(conn)
    with connect() as conn:
        return read(conn)


def plain(text: str | None) -> str:
    """Upper case without accents, so LÁMPARA CÚMULO and lampara cumulo read the same."""
    return ''.join(c for c in unicodedata.normalize('NFKD', text or '') if not unicodedata.combining(c)).upper().strip()


def product(description: str | None) -> str:
    """CIRRUS · BEIGE and CIRRUS · GRIS NIEBLA are both CIRRUS: the model sells, the color is a variant."""
    return plain(description).split(' · ')[0].strip() or 'SIN DESCRIPCIÓN'


def classify(description: str | None, recipe_id, origin_recipes: set, models: set) -> tuple[str, str]:
    """(product, line) of a sale line. Lines typed by hand before recipes existed still count as Origen when they
    name a model (Lámpara Cúmulo), say ORIGEN, or carry an ORG- code (ORG-BD-CIR)."""
    text = plain(description)
    words = set(re.findall(r'[A-Z0-9]+', text))
    code = text.startswith('ORG-')
    model = next((m for m in sorted(models) if m in words or (code and text.rsplit('-', 1)[-1] == m[:3])), None)
    if model:
        return model, ORIGIN_LINE
    if recipe_id in origin_recipes or code or 'ORIGEN' in words:
        return ORIGIN_UNKNOWN, ORIGIN_LINE
    return product(description), CUSTOM_LINE


def years(rows: list[dict]) -> list[str]:
    return sorted({r['sold_on'][:4] for r in rows if r['sold_on']}, reverse=True)


def select(rows: list[dict], year: str | None = None) -> list[dict]:
    return [r for r in rows if r['sold_on'] and (year is None or r['sold_on'].startswith(year))]


def bucket(day: str, grouping: str) -> str:
    if grouping == 'Año':
        return day[:4]
    if grouping == 'Trimestre':
        return f"{day[:4]}-T{(int(day[5:7]) - 1) // 3 + 1}"
    return day[:7]


def _following(period: str, grouping: str) -> str:
    if grouping == 'Año':
        return str(int(period) + 1)
    year, part = int(period[:4]), int(period[-1] if grouping == 'Trimestre' else period[5:7])
    size = 4 if grouping == 'Trimestre' else 12
    year, part = (year + 1, 1) if part == size else (year, part + 1)
    return f'{year}-T{part}' if grouping == 'Trimestre' else f'{year}-{part:02d}'


def _ratio(part, whole):
    return round(100 * part / whole, 1) if whole else None


def active(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r['status'] == 'Activa']


def timeline(rows: list[dict], grouping: str = 'Mes') -> list[dict]:
    """One row per period from the first sale to the last, empty periods included, so changes compare neighbours."""
    sales = active(rows)
    if not sales:
        return []
    groups: dict[str, list[dict]] = {}
    for r in sales:
        groups.setdefault(bucket(r['sold_on'], grouping), []).append(r)
    total = sum(r['total_cents'] for r in sales)
    period, last, result, cumulative, before = min(groups), max(groups), [], 0, None
    while True:
        own = groups.get(period, [])
        sold = sum(r['total_cents'] for r in own)
        cumulative += sold
        result.append(dict(period=period, count=len(own), sold_cents=sold, ticket_cents=sold // len(own) if own else None,
                           collected_percent=_ratio(sum(min(r['paid_cents'], r['total_cents']) for r in own), sold),
                           change_percent=_ratio(sold - before, before) if before else None,
                           share_percent=_ratio(sold, total), cumulative_cents=cumulative))
        before = sold
        if period == last:
            return result
        period = _following(period, grouping)


def headline(rows: list[dict]) -> dict:
    sales = active(rows)
    sold = sum(r['total_cents'] for r in sales)
    by_client: dict[str, list[int]] = {}
    for r in sales:
        entry = by_client.setdefault(r['client'].casefold(), [0, 0])
        entry[0] += r['total_cents'];entry[1] += 1
    top3 = sum(sorted((v[0] for v in by_client.values()), reverse=True)[:3])
    lines = [l for r in sales for l in r['lines']]
    months = [m for m in timeline(rows, 'Mes') if m['count']]
    best = max(months, key=lambda m: m['sold_cents']) if months else None
    return dict(sold_cents=sold, count=len(sales), ticket_cents=sold // len(sales) if sales else None,
                collected_percent=_ratio(sum(min(r['paid_cents'], r['total_cents']) for r in sales), sold),
                balance_cents=sum(max(0, r['total_cents'] - r['paid_cents']) for r in sales),
                cancelled_percent=_ratio(len(rows) - len(sales), len(rows)),
                clients=len(by_client), repeat_percent=_ratio(sum(v[1] > 1 for v in by_client.values()), len(by_client)),
                top3_percent=_ratio(top3, sold),
                origin_percent=_ratio(sum(l['amount_cents'] for l in lines if l['line'] == ORIGIN_LINE), sum(l['amount_cents'] for l in lines)),
                best_month=best['period'] if best else None, best_month_cents=best['sold_cents'] if best else None,
                first_sale=sales[0]['sold_on'] if sales else None, last_sale=sales[-1]['sold_on'] if sales else None)


def shares(rows: list[dict], field: str) -> list[dict]:
    """Sales and money by one field of the sale (channel, origin), largest first."""
    groups: dict[str, list[int]] = {}
    for r in active(rows):
        entry = groups.setdefault(r[field] or 'Sin dato', [0, 0])
        entry[0] += r['total_cents'];entry[1] += 1
    total = sum(v[0] for v in groups.values())
    return [dict(name=k, count=v[1], sold_cents=v[0], share_percent=_ratio(v[0], total))
            for k, v in sorted(groups.items(), key=lambda kv: -kv[1][0])]


def line_shares(rows: list[dict], field: str = 'product', limit: int | None = None) -> list[dict]:
    """Units and line amounts (before discount and IVA) by product or by line, largest first."""
    groups: dict[str, list[float]] = {}
    for r in active(rows):
        for l in r['lines']:
            entry = groups.setdefault(l[field], [0, 0, set()])
            entry[0] += l['amount_cents'];entry[1] += l['quantity'];entry[2].add(r['id'])
    total = sum(v[0] for v in groups.values())
    ranked = sorted(groups.items(), key=lambda kv: -kv[1][0])
    return [dict(name=k, sold_cents=v[0], units=v[1], count=len(v[2]), share_percent=_ratio(v[0], total))
            for k, v in (ranked[:limit] if limit else ranked)]


def clients(rows: list[dict], limit: int | None = 10) -> list[dict]:
    groups: dict[str, dict] = {}
    for r in active(rows):
        g = groups.setdefault(r['client'].casefold(), dict(client=r['client'], count=0, sold_cents=0, first=r['sold_on'], last=r['sold_on']))
        g['count'] += 1;g['sold_cents'] += r['total_cents'];g['last'] = r['sold_on']
    total = sum(g['sold_cents'] for g in groups.values())
    ranked = sorted(groups.values(), key=lambda g: -g['sold_cents'])
    return [dict(g, share_percent=_ratio(g['sold_cents'], total)) for g in (ranked[:limit] if limit else ranked)]
