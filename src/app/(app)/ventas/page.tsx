'use client';

import Link from 'next/link';
import { FormEvent, useCallback, useEffect, useState } from 'react';
import { PaymentDialog } from '@/components/Actions';
import { clean, Draft, LinesEditor, ReasonDialog, today } from '@/components/Commercial';
import Modal from '@/components/Modal';
import { newKey } from '@/components/Production';
import { api, money } from '@/lib/api';
import { CloseIcon } from '@/components/Icon';

type Row = { id: number; code: string; sold_on: string; client: string; project: string; origin: string; quote: string; channel: string; status: string; payment_status: string; due_on: string | null; overdue: boolean; total_cents: number; paid_cents: number; balance_cents: number; order_id: number | null };
type Report = { rows: Row[]; channels: string[]; count: number; sold_cents: number; collected_cents: number; balance_cents: number; total_balance_cents: number; overdue_cents: number };
type Payment = { id: number; code: string; amount_cents: number; paid_on: string; method: string; concept: string; reference: string; account: string; voided: boolean; void_reason: string };
type Sale = Row & { revision: number; quote_revision: number | null; quote_id: number | null; notes: string; cancel_reason: string; produce: boolean; lines: { description: string; quantity: number; price: number; amount_cents: number; produce: boolean }[]; totals: { subtotal: number; discount: number; tax: number; total: number }; payments: Payment[] };

const monthStart = () => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1).toLocaleDateString('en-CA'); };
const PAY_TONE: Record<string, string> = { Liquidada: 'green', 'Pago parcial': 'orange', 'Por cobrar': 'blue', Cancelada: '' };
type Open = { kind: 'new' } | { kind: 'pay' } | { kind: 'void'; payment: Payment } | { kind: 'due' } | { kind: 'cancel' } | { kind: 'order' } | null;

export default function Ventas() {
  const [range, setRange] = useState({ from: monthStart(), to: today() });
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('Todos');
  const [report, setReport] = useState<Report | null>(null);
  const [sale, setSale] = useState<Sale | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [open, setOpen] = useState<Open>(null);
  const load = useCallback(() => {
    const q = new URLSearchParams({ desde: range.from, hasta: range.to, buscar: search, cobranza: status });
    return api<Report>(`/ventas?${q}`).then((r) => { setReport(r); setError(''); }).catch((e) => setError(e.message));
  }, [range, search, status]);
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load]);
  const pick = useCallback((id: number) => api<Sale>(`/ventas/${id}`).then(setSale).catch((e) => setError(e.message)), []);
  useEffect(() => { const id = new URLSearchParams(window.location.search).get('venta'); if (id) pick(Number(id)); }, [pick]);
  const done = (text: string) => { setNotice(text); setOpen(null); load(); if (sale) pick(sale.id); };

  return (
    <>
      <div className="head">
        <div><h1>Ventas y cobranza</h1><p>{report ? `${report.count} ventas activas en el periodo · por cobrar en total ${money(report.total_balance_cents)}${report.overdue_cents ? ` · vencido ${money(report.overdue_cents)}` : ''}` : 'Cargando…'}</p></div>
        <button className="btn primary" onClick={() => setOpen({ kind: 'new' })}>Nueva venta</button>
      </div>
      {notice && <div className="notice" role="status">{notice}<button onClick={() => setNotice('')} aria-label="Ocultar aviso"><CloseIcon /></button></div>}
      {error && <div className="error" style={{ marginBottom: 12 }}>{error}</div>}
      <div className="filters">
        <label className="inline-label">Desde<input type="date" value={range.from} onChange={(e) => setRange({ ...range, from: e.target.value })} style={{ width: 160 }} /></label>
        <label className="inline-label">Hasta<input type="date" value={range.to} onChange={(e) => setRange({ ...range, to: e.target.value })} style={{ width: 160 }} /></label>
        <input type="search" placeholder="Folio, cliente, concepto o cotización" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Buscar venta" />
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Cobranza">{['Todos', 'Por cobrar', 'Pago parcial', 'Liquidada', 'Cancelada'].map((s) => <option key={s}>{s}</option>)}</select>
      </div>
      {report && (
        <div className="grid pulse">
          <div className="card tile"><div className="label">Vendido</div><div className="value">{money(report.sold_cents)}</div><span className="muted">{report.count} ventas activas</span></div>
          <div className="card tile"><div className="label">Cobrado en el periodo</div><div className="value">{money(report.collected_cents)}</div></div>
          <div className={`card tile ${report.balance_cents ? 'orange' : ''}`}><div className="label">Saldo de estas ventas</div><div className="value">{money(report.balance_cents)}</div></div>
        </div>
      )}
      {report && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Folio</th><th>Fecha</th><th>Cliente</th><th>Canal</th><th>Cobranza</th><th>Vence</th><th className="right">Total</th><th className="right">Saldo</th></tr></thead>
            <tbody>
              {report.rows.map((r) => (
                <tr key={r.id} tabIndex={0} onClick={() => pick(r.id)} onKeyDown={(e) => e.key === 'Enter' && pick(r.id)} aria-selected={sale?.id === r.id}>
                  <td><strong>{r.code}</strong><div className="hint">{r.project}{r.quote ? ` · ${r.quote}` : ''}</div></td>
                  <td>{r.sold_on}</td><td>{r.client}</td><td>{r.channel}</td>
                  <td><span className={`badge ${r.status === 'Cancelada' ? '' : PAY_TONE[r.payment_status] || ''}`}>{r.status === 'Cancelada' ? 'Cancelada' : r.payment_status}</span></td>
                  <td>{r.due_on ? <span className={r.overdue ? 'issue' : ''}>{r.due_on}</span> : '—'}</td>
                  <td className="right num">{money(r.total_cents)}</td><td className="right num">{money(r.balance_cents)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!report.rows.length && <div className="empty">Sin ventas en este periodo.</div>}
        </div>
      )}

      {sale && (
        <section className="card" style={{ marginTop: 16 }}>
          <div className="toolbar">
            <div><strong className="big">{sale.code} · {sale.client}</strong> <span className="muted">· {sale.project} · {sale.channel} · {sale.sold_on}</span>
              <div className="hint">{sale.quote ? `Desde ${sale.quote} · ` : 'Venta directa · '}{sale.order_id ? <Link href={`/pedidos/${sale.order_id}`}>pedido vinculado</Link> : 'sin pedido'}{sale.cancel_reason ? ` · cancelada: ${sale.cancel_reason}` : ''}</div></div>
            <span className="badges">
              {sale.status === 'Activa' && sale.balance_cents > 0 && <button className="btn small primary" onClick={() => setOpen({ kind: 'pay' })}>Cobrar {money(sale.balance_cents)}</button>}
              {sale.status === 'Activa' && <button className="btn small" onClick={() => setOpen({ kind: 'due' })}>{sale.due_on ? `Vence ${sale.due_on}` : 'Poner vencimiento'}</button>}
              {sale.status === 'Activa' && !sale.order_id && sale.produce && <button className="btn small" onClick={() => setOpen({ kind: 'order' })}>Crear pedido</button>}
              <a className="btn small" href={`/api/ventas/${sale.id}/documento`} target="_blank" rel="noreferrer">Comprobante</a>
              {sale.status === 'Activa' && <button className="btn small ghost" onClick={() => setOpen({ kind: 'cancel' })}>Cancelar venta</button>}
            </span>
          </div>
          <div className="grid two" style={{ marginTop: 12 }}>
            <div>
              <h2 className="section-title">Partidas</h2>
              {sale.lines.map((l, i) => <div className="row" key={i}><span>{l.description} <span className="who">×{l.quantity}{l.produce ? ' · fabricar' : ''}</span></span><span className="amount">{money(l.amount_cents)}</span></div>)}
              <p className="hint" style={{ marginTop: 8 }}>Subtotal {money(sale.totals.subtotal)} · Descuento −{money(sale.totals.discount)} · IVA {money(sale.totals.tax)} · <strong>Total {money(sale.total_cents)}</strong></p>
            </div>
            <div>
              <h2 className="section-title">Pagos · cobrado {money(sale.paid_cents)}</h2>
              {sale.payments.length ? sale.payments.map((p) => (
                <div className="row" key={p.id}>
                  <span><strong>{p.code}</strong> <span className="who">· {p.paid_on} · {p.method} · {p.account}</span><div className="hint">{p.concept}{p.reference ? ` · ${p.reference}` : ''}{p.voided ? ` · anulado: ${p.void_reason}` : ''}</div></span>
                  <span className="badges"><span className={`amount${p.voided ? ' muted' : ''}`} style={p.voided ? { textDecoration: 'line-through' } : undefined}>{money(p.amount_cents)}</span>
                    {!p.voided && <button className="btn small ghost" onClick={() => setOpen({ kind: 'void', payment: p })}>Anular</button>}</span>
                </div>
              )) : <div className="empty">Sin pagos registrados.</div>}
            </div>
          </div>
        </section>
      )}

      {open?.kind === 'new' && <NewSale channels={report?.channels || []} onClose={() => setOpen(null)} onDone={(m, id) => { done(m); pick(id); }} />}
      {open?.kind === 'pay' && sale && <PaymentDialog saleId={sale.id} onClose={() => setOpen(null)} onDone={done} />}
      {open?.kind === 'void' && sale && <ReasonDialog title={`Anular ${open.payment.code}`} note="Corrige un registro; no devuelve dinero. El historial se conserva." label="Anular registro" path={`/ventas/${sale.id}/pagos/${open.payment.id}/anular`} extra={{}} onClose={() => setOpen(null)} onDone={() => done('Pago anulado. Saldo actualizado.')} />}
      {open?.kind === 'cancel' && sale && <ReasonDialog title={`Cancelar ${sale.code}`} note="Deja de sumar en ventas y saldos. El pedido, la cotización y el inventario se gestionan aparte." label="Confirmar cancelación" path={`/ventas/${sale.id}/cancelar`} extra={{ expected_revision: sale.revision }} onClose={() => setOpen(null)} onDone={() => done('Venta cancelada. Historial conservado.')} />}
      {open?.kind === 'due' && sale && <DueDialog sale={sale} onClose={() => setOpen(null)} onDone={done} />}
      {open?.kind === 'order' && sale && <OrderDialog sale={sale} onClose={() => setOpen(null)} />}
    </>
  );
}

function NewSale({ channels, onClose, onDone }: { channels: string[]; onClose: () => void; onDone: (m: string, id: number) => void }) {
  const [key] = useState(newKey);
  const [draft, setDraft] = useState<Draft>({ client: '', project: '', discount: 0, iva: false, lines: [{ description: '', quantity: 1, price: '', produce: false }] });
  const [meta, setMeta] = useState({ sold_on: today(), due_on: '', channel: 'Venta al público' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function save(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try {
      const r = await api<{ id: number }>('/ventas', { method: 'POST', body: JSON.stringify({ payload: clean(draft), ...meta, request_key: key }) });
      onDone('Venta registrada.', r.id);
    } catch (err) { setError((err as Error).message); setBusy(false); }
  }
  return (
    <Modal title="Nueva venta directa" onClose={onClose} wide>
      <form className="stack" onSubmit={save}>
        <LinesEditor draft={draft} onChange={setDraft} />
        <div className="pair">
          <label>Fecha de venta<input type="date" required max={today()} value={meta.sold_on} onChange={(e) => setMeta({ ...meta, sold_on: e.target.value })} /></label>
          <label><span>Vencimiento de pago <span className="muted optional">· opcional</span></span><input type="date" value={meta.due_on} onChange={(e) => setMeta({ ...meta, due_on: e.target.value })} /></label>
        </div>
        <label>Canal<select value={meta.channel} onChange={(e) => setMeta({ ...meta, channel: e.target.value })}>{channels.map((c) => <option key={c}>{c}</option>)}</select></label>
        <p className="muted">Registrar una venta no descuenta inventario ni marca un pedido como entregado. Para una venta con cotización, conviértela desde Cotizaciones.</p>
        {error && <div className="error">{error}</div>}
        <div className="actions"><button type="button" className="btn" onClick={onClose}>Cancelar</button><button className="btn primary" disabled={busy}>{busy ? 'Guardando…' : 'Registrar venta'}</button></div>
      </form>
    </Modal>
  );
}

function DueDialog({ sale, onClose, onDone }: { sale: Sale; onClose: () => void; onDone: (m: string) => void }) {
  const [due, setDue] = useState(sale.due_on || '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function save(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try { await api(`/ventas/${sale.id}/vencimiento`, { method: 'POST', body: JSON.stringify({ due_on: due, expected_revision: sale.revision }) }); onDone(due ? `Vencimiento de ${sale.code}: ${due}.` : 'Vencimiento quitado.'); }
    catch (err) { setError((err as Error).message); setBusy(false); }
  }
  return (
    <Modal title={`Vencimiento de ${sale.code}`} onClose={onClose}>
      <form className="stack" onSubmit={save}>
        <label>Fecha de vencimiento<input type="date" value={due} onChange={(e) => setDue(e.target.value)} /></label>
        <p className="muted">Sin fecha, el saldo nunca aparece como vencido. La fecha anterior queda en el historial.</p>
        {error && <div className="error">{error}</div>}
        <div className="actions"><button type="button" className="btn" onClick={onClose}>Cancelar</button><button className="btn primary" disabled={busy}>{busy ? 'Guardando…' : 'Guardar'}</button></div>
      </form>
    </Modal>
  );
}

function OrderDialog({ sale, onClose }: { sale: Sale; onClose: () => void }) {
  const [deadline, setDeadline] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function save(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try {
      const r = await api<{ order_id: number }>(`/ventas/${sale.id}/pedido`, { method: 'POST', body: JSON.stringify({ deadline, expected_revision: sale.revision, expected_quote_revision: sale.quote_revision }) });
      window.location.href = `/pedidos/${r.order_id}`;
    } catch (err) { setError((err as Error).message); setBusy(false); }
  }
  return (
    <Modal title={`Crear pedido desde ${sale.code}`} onClose={onClose}>
      <form className="stack" onSubmit={save}>
        {sale.lines.filter((l) => l.produce).map((l, i) => <p key={i}>{l.quantity} × {l.description}</p>)}
        <label><span>Fecha comprometida de entrega <span className="muted optional">· opcional</span></span><input type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} /></label>
        <p className="muted">Se crean los productos para fabricar; después define sus piezas en el pedido.</p>
        {error && <div className="error">{error}</div>}
        <div className="actions"><button type="button" className="btn" onClick={onClose}>Cancelar</button><button className="btn primary" disabled={busy}>{busy ? 'Creando…' : 'Crear y abrir pedido'}</button></div>
      </form>
    </Modal>
  );
}
