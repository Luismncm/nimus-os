'use client';

import { FormEvent, useCallback, useEffect, useState } from 'react';
import { today } from '@/components/Commercial';
import Modal from '@/components/Modal';
import { newKey } from '@/components/Production';
import { api, money } from '@/lib/api';

type Row = { id: number; code: string; moved_on: string | null; partner: string; movement: string; concept: string; party: string; amount_cents: number; sign: number; account: string; reference: string; receipt: string; expense: string; voided: boolean; void_reason: string; pending_cents: number; can_void: boolean; token: string | null };
type Data = { rows: Row[]; partners: string[]; accounts: { id: number; name: string; kind: string }[]; injected_cents: number; covered_cents: number; reimbursable_cents: number };

export default function Socios() {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [partner, setPartner] = useState('Todos');
  const [showVoided, setShowVoided] = useState(false);
  const [open, setOpen] = useState<{ kind: 'new' } | { kind: 'void'; row: Row } | null>(null);
  const load = useCallback(() => api<Data>('/socios').then(setData).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);
  const done = (text: string) => { setNotice(text); setOpen(null); load(); };
  if (error) return <div className="error">{error}</div>;
  if (!data) return <div className="empty">Cargando socios…</div>;
  const names = Array.from(new Set(data.rows.map((r) => r.partner))).sort();
  const rows = data.rows.filter((r) => (partner === 'Todos' || r.partner === partner) && (showVoided || !r.voided));
  return (
    <>
      <div className="head"><div><h1>Socios y aportaciones</h1><p>Las aportaciones suman entradas de capital en la cuenta elegida; las compras pagadas por un socio no salen del banco.</p></div>
        <button className="btn primary" onClick={() => setOpen({ kind: 'new' })}>Nueva aportación</button></div>
      {notice && <div className="notice" role="status">{notice}<button onClick={() => setNotice('')} aria-label="Ocultar aviso">×</button></div>}
      <div className="grid pulse">
        <div className="card tile"><div className="label">Aportaciones a cuenta</div><div className="value">{money(data.injected_cents)}</div></div>
        <div className="card tile"><div className="label">Compras cubiertas por socios</div><div className="value">{money(data.covered_cents)}</div></div>
        <div className={`card tile ${data.reimbursable_cents ? 'orange' : ''}`}><div className="label">Reembolsable pendiente</div><div className="value">{money(data.reimbursable_cents)}</div></div>
      </div>
      <div className="filters">
        <select value={partner} onChange={(e) => setPartner(e.target.value)} aria-label="Socio"><option value="Todos">Todos los socios</option>{names.map((n) => <option key={n}>{n}</option>)}</select>
        <label className="check inline"><input type="checkbox" checked={showVoided} onChange={(e) => setShowVoided(e.target.checked)} /><span>Incluir anulados</span></label>
      </div>
      <section className="card">
        {rows.length ? rows.map((r) => (
          <div className="row" key={r.id}>
            <span><strong>{r.code} · {r.movement}</strong> <span className="who">· {r.partner} · {r.moved_on || 'sin fecha'}</span>
              <div className="hint">{r.concept}{r.account ? ` · ${r.account}` : ''}{r.expense ? ` · ${r.expense}` : ''}{r.reference ? ` · ${r.reference}` : ''}{r.voided ? ` · anulado: ${r.void_reason}` : ''}</div></span>
            <span className="badges">
              {r.pending_cents > 0 && <span className="badge orange">Reembolsable {money(r.pending_cents)}</span>}
              <span className="amount" style={r.voided ? { textDecoration: 'line-through' } : undefined}>{money(r.amount_cents)}</span>
              {r.can_void && <button className="btn small ghost" onClick={() => setOpen({ kind: 'void', row: r })}>Anular</button>}
            </span>
          </div>
        )) : <div className="empty">Sin movimientos de socios.</div>}
      </section>
      {open?.kind === 'new' && <InjectionDialog data={data} onClose={() => setOpen(null)} onDone={done} />}
      {open?.kind === 'void' && <VoidDialog row={open.row} onClose={() => setOpen(null)} onDone={done} />}
    </>
  );
}

function InjectionDialog({ data, onClose, onDone }: { data: Data; onClose: () => void; onDone: (m: string) => void }) {
  const [key] = useState(newKey);
  const [form, setForm] = useState({ partner: data.partners[0] || '', amount: '', moved_on: today(), account_id: data.accounts[0] ? String(data.accounts[0].id) : '', concept: 'Inyección a cuenta NIMUS', reference: '', receipt: 'Pendiente', notes: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const set = (f: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [f]: e.target.value });
  async function save(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try { await api('/socios', { method: 'POST', body: JSON.stringify({ ...form, amount: Number(form.amount), account_id: Number(form.account_id), request_key: key }) }); onDone('Aportación registrada.'); }
    catch (err) { setError((err as Error).message); setBusy(false); }
  }
  return (
    <Modal title="Nueva aportación de socio" onClose={onClose}>
      <form className="stack" onSubmit={save}>
        <label>Socio<input required list="socios" value={form.partner} onChange={set('partner')} /><datalist id="socios">{data.partners.map((p) => <option key={p} value={p} />)}</datalist></label>
        <div className="pair">
          <label>Importe · MXN<input type="number" inputMode="decimal" min="0.01" step="0.01" required value={form.amount} onChange={set('amount')} /></label>
          <label>Fecha de recepción<input type="date" required max={today()} value={form.moved_on} onChange={set('moved_on')} /></label>
        </div>
        <label>Cuenta donde entró<select value={form.account_id} onChange={set('account_id')}>{data.accounts.map((a) => <option key={a.id} value={a.id}>{a.name} · {a.kind}</option>)}</select></label>
        <label>Concepto<input required value={form.concept} onChange={set('concept')} /></label>
        <div className="pair">
          <label><span>Referencia <span className="muted optional">· opcional</span></span><input value={form.reference} onChange={set('reference')} /></label>
          <label>Comprobante<select value={form.receipt} onChange={set('receipt')}>{['Pendiente', 'Transferencia', 'Recibo', 'Sin comprobante'].map((r) => <option key={r}>{r}</option>)}</select></label>
        </div>
        {error && <div className="error">{error}</div>}
        <div className="actions"><button type="button" className="btn" onClick={onClose}>Cancelar</button><button className="btn primary" disabled={busy || !data.accounts.length}>{busy ? 'Guardando…' : 'Registrar aportación'}</button></div>
      </form>
    </Modal>
  );
}

function VoidDialog({ row, onClose, onDone }: { row: Row; onClose: () => void; onDone: (m: string) => void }) {
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function save(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try { await api(`/socios/${row.id}/anular`, { method: 'POST', body: JSON.stringify({ reason, expected: row.token }) }); onDone('Aportación anulada; historial conservado.'); }
    catch (err) { setError((err as Error).message); setBusy(false); }
  }
  return (
    <Modal title={`Anular ${row.code}`} onClose={onClose}>
      <form className="stack" onSubmit={save}>
        <p>{row.partner} · {money(row.amount_cents)} · {row.moved_on}</p>
        <label>Motivo<input required value={reason} onChange={(e) => setReason(e.target.value)} /></label>
        {error && <div className="error">{error}</div>}
        <div className="actions"><button type="button" className="btn" onClick={onClose}>Volver</button><button className="btn primary" disabled={busy}>{busy ? 'Guardando…' : 'Anular aportación'}</button></div>
      </form>
    </Modal>
  );
}
