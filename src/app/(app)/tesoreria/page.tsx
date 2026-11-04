'use client';

import Link from 'next/link';
import { FormEvent, useCallback, useEffect, useState } from 'react';
import { today } from '@/components/Commercial';
import Modal from '@/components/Modal';
import { api, money } from '@/lib/api';

type Account = { id: number; name: string; kind: string; active: boolean; revision: number; balance_cents: number | null };
type Move = { source: string; id: number; code: string; paid_on: string | null; amount_cents: number; sign: number; method: string; reference: string; document: string; party: string; concept: string; account: string; category: string; record_kind: string; record_id: number };
type Data = { accounts: Account[]; kinds: string[]; rows: Move[]; income_cents: number; outflow_cents: number; net_cents: number; unassigned: number; by_account: { account_id: number | null; account: string; income: number; outflow: number; net: number }[] };
const monthStart = () => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1).toLocaleDateString('en-CA'); };
const LINK: Record<string, (id: number) => string> = { Venta: (id) => `/ventas?venta=${id}`, Cotización: () => '/cotizaciones', Gasto: () => '/gastos', Socio: () => '/socios' };

export default function Tesoreria() {
  const [range, setRange] = useState({ from: monthStart(), to: today() });
  const [account, setAccount] = useState('all');
  const [direction, setDirection] = useState('Todos');
  const [search, setSearch] = useState('');
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [edit, setEdit] = useState<Account | 'new' | null>(null);
  const load = useCallback(() => {
    const q = new URLSearchParams({ desde: range.from, hasta: range.to, cuenta: account, direccion: direction, buscar: search });
    return api<Data>(`/tesoreria?${q}`).then((d) => { setData(d); setError(''); }).catch((e) => setError(e.message));
  }, [range, account, direction, search]);
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load]);

  return (
    <>
      <div className="head"><div><h1>Tesorería</h1><p>Entradas y salidas reales por cuenta: cobros, anticipos, pagos de gastos y aportaciones.</p></div>
        <button className="btn" onClick={() => setEdit('new')}>Nueva cuenta</button></div>
      {notice && <div className="notice" role="status">{notice}<button onClick={() => setNotice('')} aria-label="Ocultar aviso">×</button></div>}
      {error && <div className="error" style={{ marginBottom: 12 }}>{error}</div>}
      {data && (
        <div className="grid cards3" style={{ marginBottom: 18 }}>
          {data.accounts.map((a) => (
            <section className="card machine" key={a.id} style={a.active ? undefined : { opacity: 0.6 }}>
              <div className="toolbar"><div><strong className="big">{a.name}</strong><div className="hint">{a.kind}{a.active ? '' : ' · archivada'}</div></div>
                <button className="btn small ghost" onClick={() => setEdit(a)}>Editar</button></div>
              <div className="value num" style={{ fontSize: 24, fontWeight: 700 }}>{a.balance_cents == null ? '—' : money(a.balance_cents)}</div>
            </section>
          ))}
        </div>
      )}
      <div className="filters">
        <label className="inline-label">Desde<input type="date" value={range.from} onChange={(e) => setRange({ ...range, from: e.target.value })} style={{ width: 160 }} /></label>
        <label className="inline-label">Hasta<input type="date" value={range.to} onChange={(e) => setRange({ ...range, to: e.target.value })} style={{ width: 160 }} /></label>
        <select value={account} onChange={(e) => setAccount(e.target.value)} aria-label="Cuenta"><option value="all">Todas las cuentas</option>{data?.accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select>
        <select value={direction} onChange={(e) => setDirection(e.target.value)} aria-label="Dirección">{['Todos', 'Entradas', 'Salidas'].map((d) => <option key={d}>{d}</option>)}</select>
        <input type="search" placeholder="Folio, cliente, proveedor o concepto" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Buscar movimiento" />
      </div>
      {data && (
        <>
          <div className="grid pulse">
            <div className="card tile green"><div className="label">Entradas</div><div className="value">{money(data.income_cents)}</div></div>
            <div className="card tile orange"><div className="label">Salidas</div><div className="value">{money(data.outflow_cents)}</div></div>
            <div className={`card tile ${data.net_cents < 0 ? 'red' : ''}`}><div className="label">Neto del periodo</div><div className="value">{money(data.net_cents)}</div>{data.unassigned > 0 && <span className="issue">{data.unassigned} sin cuenta asignada</span>}</div>
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Fecha</th><th>Movimiento</th><th>Contraparte</th><th>Cuenta</th><th className="right">Entrada</th><th className="right">Salida</th></tr></thead>
              <tbody>{data.rows.map((r) => (
                <tr key={`${r.source}-${r.id}`} style={{ cursor: 'default' }}>
                  <td>{r.paid_on || '—'}</td>
                  <td><strong>{r.code}</strong> <span className="hint">· {LINK[r.record_kind] ? <Link href={LINK[r.record_kind](r.record_id)}>{r.document}</Link> : r.document}</span><div className="hint">{r.concept}{r.method ? ` · ${r.method}` : ''}</div></td>
                  <td>{r.party || '—'}</td><td>{r.account}</td>
                  <td className="right num">{r.sign === 1 ? money(r.amount_cents) : ''}</td><td className="right num">{r.sign === -1 ? money(r.amount_cents) : ''}</td>
                </tr>
              ))}</tbody>
            </table>
            {!data.rows.length && <div className="empty">Sin movimientos en este periodo.</div>}
          </div>
        </>
      )}
      {edit && data && <AccountDialog account={edit === 'new' ? null : edit} kinds={data.kinds} onClose={() => setEdit(null)} onDone={(m) => { setNotice(m); setEdit(null); load(); }} />}
    </>
  );
}

function AccountDialog({ account, kinds, onClose, onDone }: { account: Account | null; kinds: string[]; onClose: () => void; onDone: (m: string) => void }) {
  const [form, setForm] = useState({ name: account?.name || '', kind: account?.kind || kinds[0], active: account?.active ?? true });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function save(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try {
      await api(account ? `/tesoreria/cuentas/${account.id}` : '/tesoreria/cuentas', { method: account ? 'PUT' : 'POST', body: JSON.stringify({ ...form, expected_revision: account?.revision ?? null }) });
      onDone('Cuenta guardada.');
    } catch (err) { setError((err as Error).message); setBusy(false); }
  }
  return (
    <Modal title={account ? `Editar ${account.name}` : 'Nueva cuenta'} onClose={onClose}>
      <form className="stack" onSubmit={save}>
        <label>Nombre<input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Banco principal, caja del taller…" /></label>
        <label>Tipo<select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>{kinds.map((k) => <option key={k}>{k}</option>)}</select></label>
        <label className="check"><input type="checkbox" checked={form.active} onChange={(e) => setForm({ ...form, active: e.target.checked })} /><span>Activa para nuevos movimientos</span></label>
        <p className="muted">Las cuentas archivadas conservan su historial.</p>
        {error && <div className="error">{error}</div>}
        <div className="actions"><button type="button" className="btn" onClick={onClose}>Cancelar</button><button className="btn primary" disabled={busy}>{busy ? 'Guardando…' : 'Guardar cuenta'}</button></div>
      </form>
    </Modal>
  );
}
