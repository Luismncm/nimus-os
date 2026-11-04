'use client';

import { FormEvent, useCallback, useEffect, useState } from 'react';
import { ReasonDialog, today } from '@/components/Commercial';
import Modal from '@/components/Modal';
import { newKey } from '@/components/Production';
import { api, money } from '@/lib/api';
import { CloseIcon } from '@/components/Icon';

type Row = { id: number; code: string; expense_on: string | null; due_on: string | null; concept: string; category: string; subtype: string; supplier: string; account: string; unit: string; cost_type: string; status: string; payment_status: string; overdue: boolean; total_cents: number; paid_cents: number; balance_cents: number; receipt_type: string; control: string; order: string; revision: number };
type Detail = Row & { notes: string; receipt_ref: string; tax_mode: string; subtotal_cents: number | null; tax_cents: number | null; cancel_reason: string; payments: { id: number; code: string; amount_cents: number; paid_on: string; account: string; method: string; reference: string; voided: boolean; void_reason: string }[] };
type Options = { categories: Record<string, string[]>; cost_types: string[]; receipts: string[]; tax_modes: string[]; units: string[]; methods: string[]; accounts: string[] };
type Data = { rows: Row[]; pending: Row[]; total_cents: number; paid_cents: number; balance_cents: number; all_balance_cents: number; overdue_cents: number; missing_receipts: number; options: Options };
const monthStart = () => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1).toLocaleDateString('en-CA'); };
const TONE: Record<string, string> = { Pagado: 'green', 'Pago parcial': 'orange', 'Por pagar': 'blue' };
type Open = { kind: 'new' } | { kind: 'pay'; row: Row } | { kind: 'void'; id: number; code: string } | { kind: 'cancel' } | null;

export default function Gastos() {
  const [range, setRange] = useState({ from: monthStart(), to: today() });
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('Todos');
  const [data, setData] = useState<Data | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [open, setOpen] = useState<Open>(null);
  const load = useCallback(() => {
    const q = new URLSearchParams({ desde: range.from, hasta: range.to, buscar: search, estado: status });
    return api<Data>(`/gastos?${q}`).then((d) => { setData(d); setError(''); }).catch((e) => setError(e.message));
  }, [range, search, status]);
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load]);
  const pick = useCallback((id: number) => api<Detail>(`/gastos/${id}`).then(setDetail).catch((e) => setError(e.message)), []);
  const done = (text: string, id?: number) => { setNotice(text); setOpen(null); load(); if (id || detail) pick(id || detail!.id); };

  return (
    <>
      <div className="head">
        <div><h1>Gastos y comprobantes</h1><p>{data ? `Por pagar en total ${money(data.all_balance_cents)}${data.overdue_cents ? ` · vencido ${money(data.overdue_cents)}` : ''}${data.missing_receipts ? ` · ${data.missing_receipts} sin comprobante completo` : ''}` : 'Cargando…'}</p></div>
        <button className="btn primary" onClick={() => setOpen({ kind: 'new' })} disabled={!data}>Nuevo gasto</button>
      </div>
      {notice && <div className="notice" role="status">{notice}<button onClick={() => setNotice('')} aria-label="Ocultar aviso"><CloseIcon /></button></div>}
      {error && <div className="error" style={{ marginBottom: 12 }}>{error}</div>}

      {data && data.pending.length > 0 && (
        <section className="card" style={{ marginBottom: 18 }}>
          <h2 className="section-title">Por pagar primero</h2>
          {data.pending.slice(0, 6).map((r) => (
            <div className="row" key={r.id}>
              <span><strong>{r.code} · {r.concept}</strong> <span className="who">· {r.supplier || r.category}</span>
                <div className="hint">{r.due_on ? `Vence ${r.due_on}` : 'Sin vencimiento'} · {r.account}</div></span>
              <span className="badges">{r.overdue && <span className="badge red">Vencido</span>}<span className="amount">{money(r.balance_cents)}</span>
                <button className="btn small" onClick={() => setOpen({ kind: 'pay', row: r })}>Pagar</button></span>
            </div>
          ))}
        </section>
      )}

      <div className="filters">
        <label className="inline-label">Desde<input type="date" value={range.from} onChange={(e) => setRange({ ...range, from: e.target.value })} style={{ width: 160 }} /></label>
        <label className="inline-label">Hasta<input type="date" value={range.to} onChange={(e) => setRange({ ...range, to: e.target.value })} style={{ width: 160 }} /></label>
        <input type="search" placeholder="Folio, concepto, proveedor o categoría" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Buscar gasto" />
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Pago">{['Todos', 'Por pagar', 'Pago parcial', 'Pagado'].map((s) => <option key={s}>{s}</option>)}</select>
      </div>
      {data && (
        <>
          <div className="grid pulse">
            <div className="card tile"><div className="label">Gastos del periodo</div><div className="value">{money(data.total_cents)}</div></div>
            <div className="card tile"><div className="label">Pagado en el periodo</div><div className="value">{money(data.paid_cents)}</div></div>
            <div className={`card tile ${data.balance_cents ? 'orange' : ''}`}><div className="label">Saldo de estos gastos</div><div className="value">{money(data.balance_cents)}</div></div>
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Folio</th><th>Fecha</th><th>Categoría</th><th>Proveedor</th><th>Pago</th><th>Comprobante</th><th className="right">Total</th><th className="right">Saldo</th></tr></thead>
              <tbody>{data.rows.map((r) => (
                <tr key={r.id} tabIndex={0} onClick={() => pick(r.id)} onKeyDown={(e) => e.key === 'Enter' && pick(r.id)} aria-selected={detail?.id === r.id}>
                  <td><strong>{r.code}</strong><div className="hint">{r.concept}</div></td><td>{r.expense_on || '—'}</td><td>{r.category}<div className="hint">{r.subtype}</div></td><td>{r.supplier || '—'}</td>
                  <td><span className={`badge ${r.status === 'Cancelado' ? '' : TONE[r.payment_status] || ''}`}>{r.status === 'Cancelado' ? 'Cancelado' : r.payment_status}</span></td>
                  <td>{r.receipt_type}{r.control !== 'Completo' && <div className="issue">{r.control}</div>}</td>
                  <td className="right num">{money(r.total_cents)}</td><td className="right num">{money(r.balance_cents)}</td>
                </tr>
              ))}</tbody>
            </table>
            {!data.rows.length && <div className="empty">Sin gastos en este periodo.</div>}
          </div>
        </>
      )}

      {detail && (
        <section className="card" style={{ marginTop: 16 }}>
          <div className="toolbar">
            <div><strong className="big">{detail.code} · {detail.concept}</strong> <span className="muted">· {detail.category} · {detail.supplier}</span>
              <div className="hint">{detail.expense_on} · {detail.tax_mode}{detail.subtotal_cents != null ? ` · subtotal ${money(detail.subtotal_cents)} + IVA ${money(detail.tax_cents)}` : ''} · {detail.unit} · {detail.cost_type}{detail.order ? ` · ${detail.order}` : ''}{detail.cancel_reason ? ` · cancelado: ${detail.cancel_reason}` : ''}</div></div>
            <span className="badges">
              {detail.status === 'Activo' && detail.balance_cents > 0 && <button className="btn small primary" onClick={() => setOpen({ kind: 'pay', row: detail })}>Pagar {money(detail.balance_cents)}</button>}
              {detail.status === 'Activo' && <button className="btn small ghost" onClick={() => setOpen({ kind: 'cancel' })}>Cancelar gasto</button>}
            </span>
          </div>
          {detail.notes && <p className="hint">{detail.notes}</p>}
          <h2 className="section-title" style={{ marginTop: 12 }}>Pagos · pagado {money(detail.paid_cents)} de {money(detail.total_cents)}</h2>
          {detail.payments.length ? detail.payments.map((p) => (
            <div className="row" key={p.id}>
              <span><strong>{p.code}</strong> <span className="who">· {p.paid_on} · {p.account} · {p.method}{p.reference ? ` · ${p.reference}` : ''}</span>{p.voided && <div className="hint">Anulado: {p.void_reason}</div>}</span>
              <span className="badges"><span className="amount" style={p.voided ? { textDecoration: 'line-through' } : undefined}>{money(p.amount_cents)}</span>
                {!p.voided && <button className="btn small ghost" onClick={() => setOpen({ kind: 'void', id: p.id, code: p.code })}>Anular</button>}</span>
            </div>
          )) : <div className="empty">Sin pagos registrados.</div>}
        </section>
      )}

      {open?.kind === 'new' && data && <NewExpense options={data.options} onClose={() => setOpen(null)} onDone={(m, id) => done(m, id)} />}
      {open?.kind === 'pay' && data && <PayExpense row={open.row} options={data.options} onClose={() => setOpen(null)} onDone={(m) => done(m, open.row.id)} />}
      {open?.kind === 'void' && <ReasonDialog title={`Anular ${open.code}`} note="Corrige un registro; el historial se conserva." label="Anular registro" path={`/gastos/pagos/${open.id}/anular`} extra={{}} onClose={() => setOpen(null)} onDone={() => done('Pago anulado; historial conservado.')} />}
      {open?.kind === 'cancel' && detail && <ReasonDialog title={`Cancelar ${detail.code}`} note="Deja de sumar en gastos y saldos; el historial se conserva." label="Cancelar gasto" path={`/gastos/${detail.id}/cancelar`} extra={{ expected_revision: detail.revision }} onClose={() => setOpen(null)} onDone={() => done('Gasto cancelado.')} />}
    </>
  );
}

function NewExpense({ options, onClose, onDone }: { options: Options; onClose: () => void; onDone: (m: string, id: number) => void }) {
  const [key] = useState(newKey);
  const categories = Object.keys(options.categories);
  const [form, setForm] = useState({ expense_on: today(), due_on: '', concept: '', category: categories[0], subtype: '', supplier: '', account: options.accounts[0] || '', tax_mode: options.tax_modes[0], amount: '', tax: '', cost_type: options.cost_types[0], unit: options.units[0], receipt_type: options.receipts[0], receipt_ref: '', notes: '' });
  const [paid, setPaid] = useState(false);
  const [method, setMethod] = useState(options.methods[0]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const set = (f: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [f]: e.target.value });
  async function save(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try {
      const r = await api<{ id: number }>('/gastos', { method: 'POST', body: JSON.stringify({ payload: { ...form, amount: Number(form.amount), tax: Number(form.tax) || 0, due_on: form.due_on || '' }, request_key: key, paid, account: form.account, method }) });
      onDone(paid ? 'Gasto registrado y pagado.' : 'Gasto registrado por pagar.', r.id);
    } catch (err) { setError((err as Error).message); setBusy(false); }
  }
  return (
    <Modal title="Nuevo gasto" onClose={onClose} wide>
      <form className="stack" onSubmit={save}>
        <label>Concepto<input required value={form.concept} onChange={set('concept')} /></label>
        <div className="pair">
          <label>Categoría<select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value, subtype: '' })}>{categories.map((c) => <option key={c}>{c}</option>)}</select></label>
          <label><span>Tipo <span className="muted optional">· opcional</span></span><select value={form.subtype} onChange={set('subtype')}><option value="">—</option>{(options.categories[form.category] || []).map((s) => <option key={s}>{s}</option>)}</select></label>
        </div>
        <div className="pair">
          <label>Proveedor<input value={form.supplier} onChange={set('supplier')} /></label>
          <label>Cuenta que paga<select value={form.account} onChange={set('account')}>{options.accounts.map((a) => <option key={a}>{a}</option>)}</select></label>
        </div>
        <div className="pair">
          <label>Cómo se captura el importe<select value={form.tax_mode} onChange={set('tax_mode')}>{options.tax_modes.map((m) => <option key={m}>{m}</option>)}</select></label>
          <label>{form.tax_mode === 'Subtotal + IVA 16%' || form.tax_mode === 'Desglose manual' ? 'Subtotal · MXN' : 'Total · MXN'}<input type="number" inputMode="decimal" min="0.01" step="0.01" required value={form.amount} onChange={set('amount')} /></label>
        </div>
        {form.tax_mode === 'Desglose manual' && <label>IVA · MXN<input type="number" inputMode="decimal" min={0} step="0.01" value={form.tax} onChange={set('tax')} /></label>}
        <div className="pair">
          <label>Fecha del gasto<input type="date" required max={today()} value={form.expense_on} onChange={set('expense_on')} /></label>
          <label><span>Vencimiento <span className="muted optional">· opcional</span></span><input type="date" value={form.due_on} onChange={set('due_on')} /></label>
        </div>
        <div className="pair">
          <label>Unidad<select value={form.unit} onChange={set('unit')}>{options.units.map((u) => <option key={u}>{u}</option>)}</select></label>
          <label>Tipo de costo<select value={form.cost_type} onChange={set('cost_type')}>{options.cost_types.map((c) => <option key={c}>{c}</option>)}</select></label>
        </div>
        <div className="pair">
          <label>Comprobante<select value={form.receipt_type} onChange={set('receipt_type')}>{options.receipts.map((r) => <option key={r}>{r}</option>)}</select></label>
          <label><span>Folio del comprobante <span className="muted optional">· opcional</span></span><input value={form.receipt_ref} onChange={set('receipt_ref')} /></label>
        </div>
        <label className="check"><input type="checkbox" checked={paid} onChange={(e) => setPaid(e.target.checked)} /><span>Ya está pagado completo (registra el pago con la fecha del gasto)</span></label>
        {paid && <label>Método<select value={method} onChange={(e) => setMethod(e.target.value)}>{options.methods.map((m) => <option key={m}>{m}</option>)}</select></label>}
        {error && <div className="error">{error}</div>}
        <div className="actions"><button type="button" className="btn" onClick={onClose}>Cancelar</button><button className="btn primary" disabled={busy}>{busy ? 'Guardando…' : 'Registrar gasto'}</button></div>
      </form>
    </Modal>
  );
}

function PayExpense({ row, options, onClose, onDone }: { row: Row; options: Options; onClose: () => void; onDone: (m: string) => void }) {
  const [key] = useState(newKey);
  const [form, setForm] = useState({ amount: (row.balance_cents / 100).toFixed(2), paid_on: today(), account: options.accounts.includes(row.account) ? row.account : options.accounts[0] || '', method: options.methods[0], reference: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function save(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try { await api(`/gastos/${row.id}/pagos`, { method: 'POST', body: JSON.stringify({ ...form, amount: Number(form.amount), request_key: key, expected_revision: row.revision }) }); onDone(`Pago de ${row.code} registrado.`); }
    catch (err) { setError((err as Error).message); setBusy(false); }
  }
  return (
    <Modal title={`Pagar ${row.code}`} onClose={onClose}>
      <form className="stack" onSubmit={save}>
        <p><strong>{row.concept}</strong> <span className="muted">· saldo {money(row.balance_cents)}</span></p>
        <div className="pair">
          <label>Monto pagado · MXN<input type="number" inputMode="decimal" min="0.01" step="0.01" required value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></label>
          <label>Fecha del pago<input type="date" required max={today()} value={form.paid_on} onChange={(e) => setForm({ ...form, paid_on: e.target.value })} /></label>
        </div>
        <label>Cuenta de salida<select value={form.account} onChange={(e) => setForm({ ...form, account: e.target.value })}>{options.accounts.map((a) => <option key={a}>{a}</option>)}</select></label>
        <label>Método<select value={form.method} onChange={(e) => setForm({ ...form, method: e.target.value })}>{options.methods.map((m) => <option key={m}>{m}</option>)}</select></label>
        <label><span>Referencia <span className="muted optional">· opcional</span></span><input value={form.reference} onChange={(e) => setForm({ ...form, reference: e.target.value })} /></label>
        <p className="muted">Registra solo pagos ya realizados.</p>
        {error && <div className="error">{error}</div>}
        <div className="actions"><button type="button" className="btn" onClick={onClose}>Cancelar</button><button className="btn primary" disabled={busy}>{busy ? 'Guardando…' : 'Guardar pago'}</button></div>
      </form>
    </Modal>
  );
}
