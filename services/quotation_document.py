"""Self-contained printable HTML, escaped and generated only from saved values.

One A4 sheet design for the quotation, the payment receipt and the sale voucher: a navy masthead with the
logo and the folio, a strip with the key facts (dates and total), client and project cards, the line items,
a totals card, conditions, and for a quotation an acceptance block. Printing keeps colors and repeats the
table header on every page.
"""
import base64
from html import escape
from pathlib import Path
from services.quotations import money

CSS = '''
:root{--ink:#151B33;--accent:#2F4C9A;--soft:#EEF2FB;--line:#E2E6EE;--muted:#66708A;--text:#1B2135;--paper:#fff;--page:#E9ECF2;--ok:#2F7A57;--warn:#B0691F;--bad:#B2434C}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--text);font:13.5px/1.55 "Segoe UI",system-ui,-apple-system,Roboto,Arial,sans-serif;font-variant-numeric:tabular-nums}
.toolbar{max-width:880px;margin:20px auto 12px;display:flex;justify-content:space-between;align-items:center;gap:12px;color:var(--muted);font-size:12px}
.toolbar button{background:var(--accent);color:#fff;border:0;border-radius:8px;padding:10px 18px;font:600 13px inherit;cursor:pointer;box-shadow:0 6px 14px -8px rgba(47,76,154,.8)}
.sheet{max-width:880px;margin:0 auto 32px;background:var(--paper);border-radius:14px;overflow:hidden;box-shadow:0 1px 2px rgba(21,27,51,.06),0 18px 40px -24px rgba(21,27,51,.35)}
.masthead{background:var(--ink);color:#fff;padding:28px 40px;display:flex;justify-content:space-between;align-items:center;gap:24px}
.brand{display:flex;flex-direction:column;gap:8px}.logo{width:132px;max-height:56px}.issuer{font-size:11.5px;color:#B9C2DE;letter-spacing:.02em}
.doc{text-align:right;display:flex;flex-direction:column;align-items:flex-end;gap:4px}
.kind{font-size:11px;text-transform:uppercase;letter-spacing:.18em;color:#B9C2DE;font-weight:600}
.folio{font-size:26px;font-weight:700;letter-spacing:-.01em}
.pill{display:inline-block;margin-top:4px;padding:3px 11px;border-radius:99px;font-size:11px;font-weight:700;letter-spacing:.02em;background:rgba(255,255,255,.12);color:#fff;border:1px solid rgba(255,255,255,.28)}
.pill.ok{background:#E3F2EA;color:#235E43;border-color:#E3F2EA}.pill.warn{background:#FBEEDC;color:#86501A;border-color:#FBEEDC}.pill.bad{background:#FBE9EA;color:#922F39;border-color:#FBE9EA}
.facts{display:grid;grid-template-columns:repeat(4,1fr);border-bottom:1px solid var(--line)}
.facts div{padding:16px 22px;border-right:1px solid var(--line)}.facts div:first-child{padding-left:40px}.facts div:last-child{border-right:0;padding-right:40px;background:var(--soft)}
.label{display:block;font-size:10.5px;text-transform:uppercase;letter-spacing:.09em;color:var(--muted);font-weight:650;margin-bottom:2px}
.facts b{font-size:14px}.facts .big{font-size:19px;color:var(--accent);font-weight:750}
.body{padding:28px 40px 8px}
h2{font-size:11.5px;text-transform:uppercase;letter-spacing:.12em;color:var(--accent);margin:26px 0 10px;font-weight:700;display:flex;align-items:center;gap:10px}
h2::after{content:"";flex:1;height:1px;background:var(--line)}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.card{border:1px solid var(--line);border-radius:12px;padding:16px 18px;break-inside:avoid}
.card .name{font-size:16px;font-weight:700;margin:2px 0 4px}
.card p{margin:0 0 4px}.muted,small{color:var(--muted);font-size:12px}
dl{display:grid;grid-template-columns:repeat(2,1fr);gap:12px 24px;margin:0}dl div{break-inside:avoid}dd{margin:0}
table{border-collapse:separate;border-spacing:0;width:100%;font-size:12.5px;border:1px solid var(--line);border-radius:12px;overflow:hidden}
th{text-align:left;background:var(--soft);color:var(--ink);font-size:10.5px;text-transform:uppercase;letter-spacing:.08em;font-weight:700;padding:10px 12px;border-bottom:1px solid var(--line)}
td{padding:11px 12px;border-bottom:1px solid var(--line);vertical-align:top;overflow-wrap:anywhere}
tbody tr:last-child td{border-bottom:0}tbody tr:nth-child(even) td{background:#FAFBFD}
td.idx{color:var(--muted);width:38px}td.desc{font-weight:600}.num{text-align:right;white-space:nowrap}
tr{break-inside:avoid}
.summary{display:grid;grid-template-columns:1fr 320px;gap:20px;margin-top:18px;align-items:start}
.totals{border:1px solid var(--line);border-radius:12px;overflow:hidden;break-inside:avoid}
.totals p{display:flex;justify-content:space-between;gap:14px;margin:0;padding:9px 16px;border-bottom:1px solid var(--line)}
.totals .grand{background:var(--ink);color:#fff;border:0;padding:14px 16px;align-items:baseline}
.totals .grand span{font-size:11px;text-transform:uppercase;letter-spacing:.12em;color:#B9C2DE;font-weight:650}.totals .grand b{font-size:22px}
.note{font-size:12px;color:var(--muted);border-left:3px solid var(--line);padding:2px 0 2px 12px}
.tiers{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.tier{border:1px solid var(--line);border-radius:12px;padding:12px 14px;break-inside:avoid}.tier strong{display:block;font-size:19px;color:var(--accent)}.tier span{display:block;font-size:11px;color:var(--muted)}
.images{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}
figure{margin:0;border:1px solid var(--line);border-radius:12px;padding:10px;break-inside:avoid}figure img{width:100%;max-height:230px;object-fit:contain;border-radius:8px;background:#F7F8FB}
figcaption{font-size:11.5px;color:var(--muted);margin-top:6px}
.terms p{margin:0}
.sign{display:grid;grid-template-columns:2fr 1fr;gap:28px;margin-top:34px;break-inside:avoid}
.sign div{border-top:1.5px solid var(--ink);padding-top:6px;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}
.state{font-weight:700}.state.ok{color:var(--ok)}.state.warn{color:var(--warn)}.state.bad{color:var(--bad)}
footer{break-inside:avoid;margin-top:22px;padding:18px 40px;background:var(--soft);border-top:1px solid var(--line);display:flex;justify-content:space-between;gap:20px;font-size:11.5px;color:var(--muted)}
footer b{color:var(--ink)}
@media(max-width:640px){.masthead,.body,footer{padding-left:20px;padding-right:20px}.facts{grid-template-columns:1fr 1fr}.facts div:first-child{padding-left:22px}
 .grid,.summary,dl,.images,.sign{grid-template-columns:1fr}.masthead{flex-direction:column;align-items:flex-start}.doc{text-align:left;align-items:flex-start}table{font-size:11px}th,td{padding:7px}}
@media print{body{background:#fff}.toolbar{display:none}.sheet{margin:0;max-width:none;border-radius:0;box-shadow:none}
 .masthead,.facts div:last-child,th,.totals .grand,footer,.pill{print-color-adjust:exact;-webkit-print-color-adjust:exact}
 thead{display:table-header-group}@page{size:A4;margin:11mm}}
'''


def document(quote, *, receipt=False, sale=False):
    d = quote['data']
    def e(value): return escape(str(value or ''), quote=True)
    def paragraph(value): return e(value).replace('\n', '<br>')
    logo = Path(__file__).resolve().parents[1] / 'assets' / 'brand' / 'nimus-light.svg'
    brand = '<img class="logo" alt="NIMUS" src="data:image/svg+xml;base64,' + base64.b64encode(logo.read_bytes()).decode() + '">' if logo.exists() else '<b>NIMUS</b>'
    cancelled = sale and quote['status'] == 'Cancelada'
    title = 'Venta cancelada' if cancelled else 'Comprobante de venta' if sale else 'Recibo de pagos' if receipt else 'Cotización'
    issued = quote['sold_on'] if sale else d['issued_on']
    date_label = 'Vencimiento de pago' if sale else 'Válida hasta'
    due = (quote['due_on'] or 'Sin fecha') if sale else d['valid_until']
    totals = d['totals']

    # The state of payments, said once in the masthead and again beside the payments.
    status, tone = '', ''
    if receipt:
        status = 'Cancelada' if cancelled else 'Sin saldo pendiente' if quote['balance_cents'] == 0 else 'Pago parcial' if quote['paid_cents'] else 'Pendiente de pago'
        tone = 'bad' if cancelled else 'ok' if quote['balance_cents'] == 0 else 'warn'
    pill = f'<span class="pill {tone}">{e(status)}</span>' if status else ''

    rows = ''.join(f'<tr><td class="idx">{i+1:02}</td><td class="desc">{e(r["description"])}</td><td class="num">{r["quantity"]:g}</td>'
                   f'<td class="num">{money(round(r["price"]*100))}</td><td class="num">{money(r["amount_cents"])}</td></tr>' for i, r in enumerate(d['lines']))
    scope = [('Solución', 'solution'), ('Contexto', 'context'), ('Nivel', 'level'), ('Material / tecnología', 'material'),
             ('Objetivo', 'objective'), ('Referencia', 'reference')]
    details = ''.join(f'<div><span class="label">{label}</span><dd>{paragraph(d[key])}</dd></div>' for label, key in scope if d[key])
    project_meta = ''.join(f'<p><span class="label">{label}</span>{e(d[key])}</p>' for label, key in (('Entrega estimada', 'lead_time'), ('Responsable', 'owner')) if d[key])

    tiers = ''
    if d['tiers']:
        tiles = ''.join(f'<div class="tier"><span>{t["minimum"]}{"–"+str(t["maximum"]) if t["maximum"] is not None else "+"} unidades</span><strong>{money(round(t["price"]*100))}</strong>'
                        f'<span>{e(t["note"])}{" · " if t["note"] else ""}{t["reference_discount"]:g}% ref.</span></div>' for t in d['tiers'])
        tiers = ('<h2>Precios por volumen</h2><div class="tiers">' + tiles + '</div><p class="note" style="margin-top:10px">Precios unitarios antes de IVA. '
                 'El descuento de referencia es informativo; los importes aplicados son los de las partidas.</p>')
    images = ''.join(f'<figure><img alt="{e(p["caption"])}" src="data:{p["mime"]};base64,{p["data"]}"><figcaption>{e(p["caption"])}</figcaption></figure>' for p in d['images'])

    discount = f'<p><span>Descuento ({d["discount"]:g}%)</span><b>−{money(totals["discount"])}</b></p>' if totals['discount'] else ''
    totals_html = (f'<div class="totals"><p><span>Subtotal</span><b>{money(totals["subtotal"])}</b></p>{discount}'
                   f'<p><span>{"IVA 16%" if d["iva"] else "Sin IVA agregado"}</span><b>{money(totals["tax"])}</b></p>'
                   f'<p class="grand"><span>Total MXN</span><b>{money(totals["total"])}</b></p></div>')
    validity = (f'<p class="note">Precios en pesos mexicanos. {"Esta cotización es válida hasta " + e(due) + "." if not sale and not receipt and due else ""}</p>')

    terms = ''
    cards = [f'<div class="card"><span class="label">{label}</span><p>{paragraph(d[key])}</p></div>'
             for label, key in (('Condiciones de pago', 'payment_terms'), ('Notas y especificaciones', 'notes')) if d[key]]
    if cards:
        # Two side by side; a single one takes the whole width.
        terms += f'<div class="{"grid " if len(cards) == 2 else ""}terms">' + ''.join(cards) + '</div>'
    if d['conditions']:
        terms += f'<div class="card terms" style="margin-top:14px"><span class="label">Condiciones comerciales</span><p>{paragraph(d["conditions"])}</p></div>'

    receipt_html = ''
    if receipt:
        payments = ''.join(f'<tr><td>{e(p["code"])}</td><td>{e(p["paid_on"])}</td><td>{e(p["concept"])}<br><small>{" · ".join(e(v) for v in (p["method"], p["reference"]) if v)}</small></td>'
                           f'<td class="num">{money(p["amount_cents"])}</td><td>{"Anulado: "+e(p["void_reason"]) if p["voided_at"] else "Registrado"}</td></tr>' for p in quote['payments'])
        receipt_html = (f'<h2>Pagos registrados · {e(quote["code"])}</h2><table><thead><tr><th>Recibo</th><th>Fecha</th><th>Concepto / referencia</th><th class="num">Monto</th><th>Estado</th></tr></thead>'
                        f'<tbody>{payments}</tbody></table><div class="summary"><div></div><div class="totals"><p><span>Pagado</span><b>{money(quote["paid_cents"])}</b></p>'
                        f'<p><span>Saldo pendiente</span><b>{money(quote["balance_cents"])}</b></p><p><span>Estado</span><b class="state {tone}">{status}</b></p></div></div>')
    if cancelled:
        receipt_html += '<p class="note" style="margin-top:14px"><b>Cancelada · excluida de ventas y cuentas por cobrar.</b> ' + e(quote['cancel_reason']) + '</p>'
    # A quotation is signed by the client to accept it; receipts and sale vouchers are not.
    sign = '' if receipt or sale else '<div class="sign"><div>Nombre y firma de aceptación del cliente</div><div>Fecha</div></div>'

    return f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(quote['code'])} · {title} · NIMUS</title>
<style>{CSS}</style></head><body>
<div class="toolbar"><span>{title} {e(quote['code'])} · vista para imprimir</span><button onclick="window.print()">Imprimir / guardar como PDF</button></div>
<main class="sheet">
<header class="masthead"><div class="brand">{brand}{'' if (d['issuer'] or '').strip().casefold() in ('', 'nimus') else '<span class="issuer">' + e(d['issuer']) + '</span>'}</div>
<div class="doc"><span class="kind">{title}</span><span class="folio">{e(quote['code'])}</span>{pill}</div></header>
<section class="facts"><div><span class="label">Emisión</span><b>{e(issued)}</b></div><div><span class="label">{date_label}</span><b>{e(due)}</b></div>
<div><span class="label">Partidas</span><b>{len(d['lines'])} · {sum(r['quantity'] for r in d['lines']):g} unidades</b></div><div><span class="label">Total MXN</span><span class="big">{money(totals['total'])}</span></div></section>
<div class="body">
<div class="grid"><div class="card"><span class="label">Cliente</span><p class="name">{e(d['client']) or '—'}</p><p>{e(d['contact'])}</p><p class="muted">{e(d['contact_channel'])}</p><p class="muted">RFC: {e(d['rfc']) or '—'}</p></div>
<div class="card"><span class="label">Proyecto</span><p class="name">{e(d['project']) or '—'}</p>{project_meta}</div></div>
{'<h2>Alcance comercial y técnico</h2><dl>' + details + '</dl>' if details else ''}
<h2>Partidas</h2><table><thead><tr><th>#</th><th>Producto / servicio</th><th class="num">Cant.</th><th class="num">P. unitario</th><th class="num">Importe</th></tr></thead><tbody>{rows}</tbody></table>
<div class="summary"><div>{validity}</div>{totals_html}</div>
{tiers}
{'<h2>Prototipos</h2><div class="images">' + images + '</div>' if images and not receipt and not sale else ''}
{'<h2>Condiciones</h2>' + terms if terms else ''}
{receipt_html}
{sign}
</div>
<footer><div><b>{e(d['issuer'])}</b><br>{paragraph(d['footer'])}</div><div style="text-align:right">{e(quote['code'])} · {title}<br>Importes en MXN</div></footer>
</main></body></html>'''.encode('utf-8')
