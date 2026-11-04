'use client';

import Link from 'next/link';
import { FormEvent, useCallback, useEffect, useState } from 'react';
import { clean, Draft, LinesEditor, today } from '@/components/Commercial';
import Modal from '@/components/Modal';
import { newKey } from '@/components/Production';
import { api, money } from '@/lib/api';
import { CloseIcon } from '@/components/Icon';

type Row = { id: number; code: string; status: string; client: string; project: string; total_cents: number; paid_cents: number; valid_until: string; order_id: number | null };
type Payment = { id: number; code: string; amount_cents: number; paid_on: string; method: string; concept: string; account: string; voided: boolean };
type Quote = {
  id: number; code: string; status: string; revision: number; order_id: number | null; sale_id: number | null; sale_status: string | null; locked: boolean;
  total_cents: number; paid_cents: number; balance_cents: number; payload: Draft & { issued_on: string; valid_until: string }; payments: Payment[];
  channels: string[]; accounts: { id: number; name: string; kind: string }[];
};
const TONE: Record<string, string> = { Borrador: '', Enviada: 'blue', Aceptada: 'green', Cancelada: 'red' };
type Open = { kind: 'pay' | 'sale' | 'order' } | null;

export default function Cotizaciones() {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [filter, setFilter] = useState('Abiertas');
  const [search, setSearch] = useState('');
  const [quote, setQuote] = useState<Quote | null>(null);
  const [draft, setDraft] = useState<Quote['payload'] | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<Open>(null);
  const load = useCallback(() => api<{ rows: Row[] }>('/cotizaciones').then((r) => setRows(r.rows)).catch((e) => setError(e.message)), []);
  const pick = useCallback((id: number) => api<Quote>(`/cotizaciones/${id}`).then((q) => { setQuote(q); setDraft(q.payload); setError(''); }).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);
  const refresh = (text: string) => { setNotice(text); setOpen(null); load(); if (quote) pick(quote.id); };

  async function create(copy?: number) {
    setBusy(true);
    try { const r = await api<{ id: number }>(`/cotizaciones${copy ? `?copy_id=${copy}` : ''}`, { method: 'POST' }); await load(); await pick(r.id); setNotice(copy ? 'Copia creada con fechas nuevas. Ajusta su alcance.' : 'Cotización nueva en borrador.'); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function save(status: string) {
    if (!quote || !draft) return;
    setBusy(true); setError('');
    try { await api(`/cotizaciones/${quote.id}`, { method: 'PUT', body: JSON.stringify({ payload: clean(draft), expected_revision: quote.revision, status }) }); refresh(status === 'Borrador' ? 'Borrador guardado.' : `Cotización guardada como ${status.toLowerCase()}.`); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function setStatus(status: string) {
    if (!quote) return;
    setBusy(true); setError('');
    try { await api(`/cotizaciones/${quote.id}/estado`, { method: 'POST', body: JSON.stringify({ status, expected_revision: quote.revision }) }); refresh(`Cotización ${status.toLowerCase()}.`); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  if (!rows) return error ? <div className="error">{error}</div> : <div className="empty">Cargando cotizaciones…</div>;
  const term = search.trim().toLowerCase();
  const shown = rows.filter((r) => (filter === 'Todas' || (filter === 'Abiertas' ? ['Borrador', 'Enviada', 'Aceptada'].includes(r.status) && !r.order_id : r.status === filter))
    && (!term || [r.code, r.client, r.project].join(' ').toLowerCase().includes(term)));
  return (
    <>
      <div className="head">
        <div><h1>Cotizaciones</h1><p>{rows.filter((r) => r.status === 'Enviada').length} enviadas esperando respuesta · {rows.filter((r) => r.status === 'Aceptada' && !r.order_id).length} aceptadas sin pedido</p></div>
        <button className="btn primary" disabled={busy} onClick={() => create()}>Nueva cotización</button>
      </div>
      {notice && <div className="notice" role="status">{notice}<button onClick={() => setNotice('')} aria-label="Ocultar aviso"><CloseIcon /></button></div>}
      <div className="filters">
        <div className="pills">{['Abiertas', 'Borrador', 'Enviada', 'Aceptada', 'Cancelada', 'Todas'].map((f) => <button key={f} className={`pill${filter === f ? ' on' : ''}`} aria-pressed={filter === f} onClick={() => setFilter(f)}>{f}</button>)}</div>
        <input type="search" placeholder="Folio, cliente o proyecto" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Buscar cotización" />
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Folio</th><th>Cliente</th><th>Estado</th><th>Vigencia</th><th className="right">Total</th><th className="right">Cobrado</th></tr></thead>
          <tbody>{shown.map((r) => (
            <tr key={r.id} tabIndex={0} onClick={() => pick(r.id)} onKeyDown={(e) => e.key === 'Enter' && pick(r.id)} aria-selected={quote?.id === r.id}>
              <td><strong>{r.code}</strong><div className="hint">{r.project}</div></td><td>{r.client || '—'}</td>
              <td><span className={`badge ${TONE[r.status] || ''}`}>{r.status}</span>{r.order_id && <span className="badge accent">Con pedido</span>}</td>
              <td>{r.valid_until}</td><td className="right num">{money(r.total_cents)}</td><td className="right num">{money(r.paid_cents)}</td>
            </tr>
          ))}</tbody>
        </table>
        {!shown.length && <div className="empty">Sin cotizaciones en esta vista.</div>}
      </div>

      {quote && draft && (
        <section className="card" style={{ marginTop: 16 }}>
          <div className="toolbar" style={{ marginBottom: 12 }}>
            <div><strong className="big">{quote.code}</strong> <span className={`badge ${TONE[quote.status] || ''}`}>{quote.status}</span>
              <div className="hint">Total {money(quote.total_cents)} · cobrado {money(quote.paid_cents)} · saldo {money(quote.balance_cents)}
                {quote.order_id && <> · <Link href={`/pedidos/${quote.order_id}`}>pedido</Link></>}{quote.sale_id && <> · <Link href={`/ventas?venta=${quote.sale_id}`}>venta {quote.sale_status?.toLowerCase()}</Link></>}</div></div>
            <span className="badges">
              <a className="btn small" href={`/api/cotizaciones/${quote.id}/documento`} target="_blank" rel="noreferrer">Documento</a>
              {quote.payments.length > 0 && <a className="btn small" href={`/api/cotizaciones/${quote.id}/documento?recibo=true`} target="_blank" rel="noreferrer">Recibo</a>}
              <button className="btn small ghost" disabled={busy} onClick={() => create(quote.id)}>Duplicar</button>
            </span>
          </div>
          {quote.locked && <p className="muted" style={{ marginBottom: 10 }}>Tiene pedido, venta o pagos: su alcance queda fijo. Duplícala para cambiarlo.</p>}
          <LinesEditor draft={draft} onChange={(d) => setDraft({ ...draft, ...d })} disabled={quote.locked || quote.status === 'Cancelada'} />
          {!quote.locked && quote.status !== 'Cancelada' && (
            <div className="pair" style={{ marginTop: 12 }}>
              <label>Emisión<input type="date" value={draft.issued_on} onChange={(e) => setDraft({ ...draft, issued_on: e.target.value })} /></label>
              <label>Válida hasta<input type="date" value={draft.valid_until} onChange={(e) => setDraft({ ...draft, valid_until: e.target.value })} /></label>
            </div>
          )}
          {error && <div className="error" style={{ marginTop: 12 }}>{error}</div>}
          <div className="actions" style={{ marginTop: 14 }}>
            {!quote.locked && quote.status !== 'Cancelada' && <>
              <button className="btn" disabled={busy} onClick={() => save('Borrador')}>Guardar borrador</button>
              <button className="btn" disabled={busy} onClick={() => save('Enviada')}>Guardar como enviada</button>
              <button className="btn primary" disabled={busy} onClick={() => save('Aceptada')}>Aceptada</button>
            </>}
            {quote.status === 'Aceptada' && quote.balance_cents > 0 && !quote.sale_id && <button className="btn" onClick={() => setOpen({ kind: 'pay' })}>Registrar anticipo</button>}
            {quote.status === 'Aceptada' && !quote.sale_id && <button className="btn primary" onClick={() => setOpen({ kind: 'sale' })}>Convertir en venta</button>}
            {quote.status === 'Aceptada' && !quote.order_id && <button className="btn" onClick={() => setOpen({ kind: 'order' })}>Crear pedido</button>}
            {quote.status !== 'Cancelada' && !quote.order_id && <button className="btn ghost" disabled={busy} onClick={() => setStatus('Cancelada')}>Cancelar cotización</button>}
          </div>
          {quote.payments.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <h2 className="section-title">Pagos</h2>
              {quote.payments.map((p) => <div className="row" key={p.id}><span><strong>{p.code}</strong> <span className="who">· {p.paid_on} · {p.method} · {p.account} · {p.concept}</span></span><span className="amount" style={p.voided ? { textDecoration: 'line-through' } : undefined}>{money(p.amount_cents)}</span></div>)}
            </div>
          )}
        </section>
      )}

      {open?.kind === 'pay' && quote && <AdvanceDialog quote={quote} onClose={() => setOpen(null)} onDone={refresh} />}
      {open?.kind === 'sale' && quote && <SaleDialog quote={quote} onClose={() => setOpen(null)} onDone={refresh} />}
      {open?.kind === 'order' && quote && <QuoteOrderDialog quote={quote} onClose={() => setOpen(null)} />}
    </>
  );
}

function Buttons({ busy, label, onClose }: { busy: boolean; label: string; onClose: () => void }) {
  return <div className="actions"><button type="button" className="btn" onClick={onClose}>Cancelar</button><button className="btn primary" disabled={busy}>{busy ? 'Guardando…' : label}</button></div>;
}

function AdvanceDialog({ quote, onClose, onDone }: { quote: Quote; onClose: () => void; onDone: (m: string) => void }) {
  const [key] = useState(newKey);
  const [form, setForm] = useState({ amount: (quote.balance_cents / 200).toFixed(2), paid_on: today(), method: 'Transferencia', account_id: quote.accounts[0] ? String(quote.accounts[0].id) : '', concept: 'Anticipo', reference: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function save(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try { await api(`/cotizaciones/${quote.id}/pagos`, { method: 'POST', body: JSON.stringify({ ...form, amount: Number(form.amount), account_id: Number(form.account_id), request_key: key, expected_revision: quote.revision }) }); onDone('Anticipo registrado.'); }
    catch (err) { setError((err as Error).message); setBusy(false); }
  }
  return (
    <Modal title={`Anticipo · ${quote.code}`} onClose={onClose}>
      <form className="stack" onSubmit={save}>
        <p className="muted">Saldo {money(quote.balance_cents)}. El 50% sugerido viene de los términos de la cotización.</p>
        <div className="pair">
          <label>Monto · MXN<input type="number" inputMode="decimal" min="0.01" step="0.01" required value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></label>
          <label>Fecha<input type="date" required max={today()} value={form.paid_on} onChange={(e) => setForm({ ...form, paid_on: e.target.value })} /></label>
        </div>
        <label>Método<select value={form.method} onChange={(e) => setForm({ ...form, method: e.target.value })}>{['Transferencia', 'Efectivo', 'Depósito', 'Tarjeta', 'Pasarela de pago', 'Otro'].map((m) => <option key={m}>{m}</option>)}</select></label>
        {quote.accounts.length ? <label>Cuenta donde se recibió<select value={form.account_id} onChange={(e) => setForm({ ...form, account_id: e.target.value })}>{quote.accounts.map((a) => <option key={a.id} value={a.id}>{a.name} · {a.kind}</option>)}</select></label>
          : <div className="error">Agrega una cuenta en Tesorería para registrar cobros.</div>}
        <label>Concepto<input required value={form.concept} onChange={(e) => setForm({ ...form, concept: e.target.value })} /></label>
        {error && <div className="error">{error}</div>}
        <Buttons busy={busy || !quote.accounts.length} label="Guardar anticipo" onClose={onClose} />
      </form>
    </Modal>
  );
}

function SaleDialog({ quote, onClose, onDone }: { quote: Quote; onClose: () => void; onDone: (m: string) => void }) {
  const [key] = useState(newKey);
  const [form, setForm] = useState({ sold_on: today(), due_on: '', channel: 'B2B' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function save(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try { await api(`/cotizaciones/${quote.id}/venta`, { method: 'POST', body: JSON.stringify({ ...form, request_key: key, expected_revision: quote.revision }) }); onDone('Venta registrada desde la cotización; sus pagos pasan a la venta.'); }
    catch (err) { setError((err as Error).message); setBusy(false); }
  }
  return (
    <Modal title={`Convertir ${quote.code} en venta`} onClose={onClose}>
      <form className="stack" onSubmit={save}>
        <div className="pair">
          <label>Fecha de venta<input type="date" required max={today()} value={form.sold_on} onChange={(e) => setForm({ ...form, sold_on: e.target.value })} /></label>
          <label><span>Vencimiento <span className="muted optional">· opcional</span></span><input type="date" value={form.due_on} onChange={(e) => setForm({ ...form, due_on: e.target.value })} /></label>
        </div>
        <label>Canal<select value={form.channel} onChange={(e) => setForm({ ...form, channel: e.target.value })}>{quote.channels.map((c) => <option key={c}>{c}</option>)}</select></label>
        {error && <div className="error">{error}</div>}
        <Buttons busy={busy} label="Registrar venta" onClose={onClose} />
      </form>
    </Modal>
  );
}

function QuoteOrderDialog({ quote, onClose }: { quote: Quote; onClose: () => void }) {
  const [deadline, setDeadline] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function save(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try { const r = await api<{ order_id: number }>(`/cotizaciones/${quote.id}/pedido`, { method: 'POST', body: JSON.stringify({ deadline, expected_revision: quote.revision }) }); window.location.href = `/pedidos/${r.order_id}`; }
    catch (err) { setError((err as Error).message); setBusy(false); }
  }
  return (
    <Modal title={`Pedido desde ${quote.code}`} onClose={onClose}>
      <form className="stack" onSubmit={save}>
        <label><span>Fecha comprometida <span className="muted optional">· opcional</span></span><input type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} /></label>
        <p className="muted">Se crean las partidas para fabricar. La cotización conserva su aceptación.</p>
        {error && <div className="error">{error}</div>}
        <Buttons busy={busy} label="Crear y abrir pedido" onClose={onClose} />
      </form>
    </Modal>
  );
}
