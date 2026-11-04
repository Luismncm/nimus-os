'use client';

import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import Modal from '@/components/Modal';
import { newKey } from '@/components/Production';
import { api } from '@/lib/api';

type Piece = {
  id: number; code: string; label: string; part: string; model: string; product: string; reference: string; collection: string;
  material: string; process: string; role: string; supply: string; component_id: number | null; free: number; reserved: number;
  physical: number; b2b: number; delivered: number; collection_free: number; stock_free: number; unassigned: number; stock: number; state: string;
};
type Movement = { id: number; code: string; sku_id: number; created_at: string; kind: string; source: string; destination: string; quantity: number; part: string; product: string; client: string; notes: string; job: string; order: string; state: string; reversible: boolean };
type Supply = { id: number; name: string; category: string; unit: string; spec: string; color: string; balance: number; minimum: number; committed: number; free_after: number; on_order: number; state: string; attention: boolean };
type Restock = { id: number; name: string; variant: string; net: number; minimum: number; physical: number; reserved: number; on_order: number; replenish: number; critical: boolean; attention: boolean };
type Purchase = { kind: string; id: number; code: string; what: string; supplier: string; status: string; ordered_on: string | null; expected_on: string | null; overdue: boolean; quantity: number; received: number; remaining: number; unit: string; token: string };
type Data = { pieces: Piece[]; movements: Movement[]; supplies: Supply[]; restock: Restock[]; purchases: Purchase[]; reservations: { id: number; order: string; project: string; part: string; variant: string; location: string; quantity: number }[]; clients: { client: string; part: string; product: string; quantity: number }[] };

const TABS = ['Existencias', 'Filamento y consumibles', 'Compras', 'Reservas y clientes', 'Movimientos'] as const;
const STATE_TONE: Record<string, string> = { Disponible: 'green', Reservada: 'orange', 'En clientes': 'blue', 'Sin saldo': '' };
const PLACE: Record<string, string> = { Colección: 'Por distribuir', Stock: 'Almacén', B2B: 'Cliente B2B' };
const day = (iso: string | null) => (iso ? iso.slice(0, 10) : '—');
const qty = (n: number, unit: string) => `${Number(n.toFixed(2)).toLocaleString('es-MX')} ${unit}`;

type Open = { kind: 'entry' | 'move'; piece: Piece } | { kind: 'reverse'; movement: Movement } | { kind: 'supply'; supply: Supply } | { kind: 'receive'; purchase: Purchase } | null;

export default function Inventario() {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [tab, setTab] = useState<(typeof TABS)[number]>('Existencias');
  const [search, setSearch] = useState('');
  const [line, setLine] = useState('Todas');
  const [state, setState] = useState('Todos');
  const [selected, setSelected] = useState<number | null>(null);
  const [open, setOpen] = useState<Open>(null);
  const load = useCallback(() => api<Data>('/inventario').then(setData).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);
  const done = (text: string) => { setNotice(text); setOpen(null); load(); };

  const pieces = useMemo(() => {
    if (!data) return [];
    const term = search.trim().toLowerCase();
    return data.pieces.filter((p) => (line === 'Todas' || p.collection === line)
      && (state === 'Todos' || (state === 'Con disponibles' && p.free > 0) || (state === 'Con reservas' && p.reserved > 0) || (state === 'Sin saldo' && p.physical === 0 && p.b2b === 0))
      && (!term || [p.code, p.label, p.product, p.material, p.process, p.collection, p.reference].join(' ').toLowerCase().includes(term)));
  }, [data, search, line, state]);
  if (error) return <div className="error">{error}</div>;
  if (!data) return <div className="empty">Cargando inventario…</div>;

  const totals = pieces.reduce((t, p) => ({ free: t.free + p.free, reserved: t.reserved + p.reserved, physical: t.physical + p.physical, b2b: t.b2b + p.b2b }), { free: 0, reserved: 0, physical: 0, b2b: 0 });
  const lines = ['Todas', ...Array.from(new Set(data.pieces.map((p) => p.collection)))];
  const piece = data.pieces.find((p) => p.id === selected) || null;
  const openPurchases = data.purchases.filter((p) => p.remaining > 0);
  const attention = data.supplies.filter((s) => s.attention).length + data.restock.filter((r) => r.attention).length;
  const badge = (t: string) => (t === 'Compras' && openPurchases.length ? ` · ${openPurchases.length}` : t === 'Filamento y consumibles' && attention ? ` · ${attention}` : '');

  return (
    <>
      <div className="head"><div><h1>Inventario</h1><p>{data.pieces.length} referencias · En taller = Disponibles + Reservadas · cantidades en piezas</p></div></div>
      {notice && <div className="notice" role="status">{notice}<button onClick={() => setNotice('')} aria-label="Ocultar aviso">×</button></div>}
      <div className="grid pulse">
        <div className="card tile"><div className="label">Disponibles</div><div className="value">{totals.free}</div><span className="muted">libres para mover o reservar</span></div>
        <div className="card tile orange"><div className="label">Reservadas</div><div className="value">{totals.reserved}</div><span className="muted">apartadas para pedidos</span></div>
        <div className="card tile"><div className="label">En taller</div><div className="value">{totals.physical}</div><span className="muted">disponibles + reservadas</span></div>
        <div className="card tile"><div className="label">En clientes B2B</div><div className="value">{totals.b2b}</div><span className="muted">ya no cuentan en el taller</span></div>
      </div>
      <div className="pills" role="tablist" style={{ marginBottom: 14 }}>
        {TABS.map((t) => <button key={t} role="tab" aria-selected={tab === t} className={`pill${tab === t ? ' on' : ''}`} onClick={() => setTab(t)}>{t}{badge(t)}</button>)}
      </div>

      {tab === 'Existencias' && (
        <>
          <div className="filters">
            <input type="search" placeholder="Pieza, modelo, material o referencia" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Buscar pieza" />
            <select value={line} onChange={(e) => setLine(e.target.value)} aria-label="Línea">{lines.map((l) => <option key={l} value={l}>{l === 'Todas' ? 'Todas las líneas' : l}</option>)}</select>
            <select value={state} onChange={(e) => setState(e.target.value)} aria-label="Saldo">{['Todos', 'Con disponibles', 'Con reservas', 'Sin saldo'].map((s) => <option key={s}>{s}</option>)}</select>
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Pieza</th><th>Línea</th><th>Material</th><th className="right">Por distribuir</th><th className="right">Almacén</th><th className="right">Reservadas</th><th className="right">B2B</th><th>Estado</th></tr></thead>
              <tbody>
                {pieces.map((p) => (
                  <tr key={p.id} tabIndex={0} onClick={() => setSelected(p.id)} onKeyDown={(e) => e.key === 'Enter' && setSelected(p.id)} aria-selected={selected === p.id}>
                    <td><strong>{p.label}</strong><div className="hint">{p.code} · {p.reference}</div></td>
                    <td>{p.collection}</td><td>{p.material || '—'}</td>
                    <td className="right num">{p.collection_free}</td><td className="right num">{p.stock_free}</td><td className="right num">{p.reserved}</td><td className="right num">{p.b2b}</td>
                    <td><span className={`badge ${STATE_TONE[p.state] || ''}`}>{p.state}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!pieces.length && <div className="card empty">Sin piezas para estos filtros.</div>}
          {piece && (
            <section className="card" style={{ marginTop: 16 }}>
              <div className="toolbar">
                <div><strong className="big">{piece.label}</strong> <span className="muted">· {piece.code} · {piece.material || 'sin material'} · {piece.process}</span>
                  <div className="hint">Por distribuir {piece.collection_free} libres de {piece.unassigned} · Almacén {piece.stock_free} libres de {piece.stock} · {piece.delivered} entregadas</div></div>
                <span className="badges">
                  <button className="btn small primary" onClick={() => setOpen({ kind: 'entry', piece })}>Entrada</button>
                  <button className="btn small" disabled={piece.free < 1} onClick={() => setOpen({ kind: 'move', piece })}>Mover o asignar</button>
                  <button className="btn small ghost" onClick={() => setSelected(null)}>Cerrar</button>
                </span>
              </div>
              <MovementList rows={data.movements.filter((m) => m.sku_id === piece.id).slice(0, 12)} onReverse={(m) => setOpen({ kind: 'reverse', movement: m })} />
            </section>
          )}
        </>
      )}

      {tab === 'Filamento y consumibles' && (
        <div className="grid two">
          <section className="card">
            <h2 className="section-title">Filamento y consumibles</h2>
            {data.supplies.length ? data.supplies.map((s) => (
              <div className="row" key={s.id}>
                <span><strong>{s.name}</strong> <span className="who">· {s.category}{s.color ? ` · ${s.color}` : ''}</span>
                  <div className="hint">Saldo {qty(s.balance, s.unit)} · comprometido {qty(s.committed, s.unit)} · libre después {qty(s.free_after, s.unit)}{s.minimum ? ` · mínimo ${qty(s.minimum, s.unit)}` : ''}{s.on_order ? ` · en camino ${qty(s.on_order, s.unit)}` : ''}</div></span>
                <span className="badges">{s.attention && <span className="badge orange">{s.state}</span>}<button className="btn small" onClick={() => setOpen({ kind: 'supply', supply: s })}>Registrar</button></span>
              </div>
            )) : <div className="empty">Sin filamento ni consumibles registrados.</div>}
          </section>
          <section className="card">
            <h2 className="section-title">Insumos y reposición</h2>
            {data.restock.length ? data.restock.map((r) => (
              <div className="row" key={r.id}>
                <span><strong>{r.name}</strong> <span className="who">· {r.variant || 'Estándar'}</span>
                  <div className="hint">Saldo neto {r.net} · mínimo {r.minimum} · en taller {r.physical} · reservados {r.reserved}{r.on_order ? ` · en camino ${r.on_order}` : ''}</div></span>
                {r.attention ? <span className={`badge ${r.critical ? 'red' : 'orange'}`}>Reponer {r.replenish}</span> : <span className="badge green">Cubierto</span>}
              </div>
            )) : <div className="empty">Sin insumos con mínimo.</div>}
          </section>
        </div>
      )}

      {tab === 'Compras' && (
        <section className="card">
          <h2 className="section-title">Compras a proveedores</h2>
          {data.purchases.length ? data.purchases.map((p) => (
            <div className="row" key={`${p.kind}-${p.id}`}>
              <span><strong>{p.code} · {p.what}</strong> <span className="who">· {p.kind}{p.supplier ? ` · ${p.supplier}` : ''}</span>
                <div className="hint">Pedido {day(p.ordered_on)} · llega {day(p.expected_on)} · {p.received} de {p.quantity} {p.unit} recibidos</div></span>
              <span className="badges">
                <span className={`badge ${p.overdue ? 'red' : p.remaining ? 'blue' : 'green'}`}>{p.overdue ? 'Llegada vencida' : p.status}</span>
                {p.remaining > 0 && <button className="btn small" onClick={() => setOpen({ kind: 'receive', purchase: p })}>Recibir</button>}
              </span>
            </div>
          )) : <div className="empty">Sin compras registradas. Los pedidos a proveedor se crean en la app local por ahora.</div>}
        </section>
      )}

      {tab === 'Reservas y clientes' && (
        <div className="grid two">
          <section className="card">
            <h2 className="section-title">Reservas por pedido · {data.reservations.length}</h2>
            {data.reservations.length ? data.reservations.map((r) => (
              <div className="row" key={r.id}><span><strong>{r.order}</strong> <span className="who">· {r.project}</span><div className="hint">{r.part}{r.variant ? ` · ${r.variant}` : ''} · {r.location}</div></span><span className="amount">{r.quantity}</span></div>
            )) : <div className="empty">Sin reservas activas.</div>}
          </section>
          <section className="card">
            <h2 className="section-title">Asignado a clientes B2B</h2>
            {data.clients.length ? data.clients.map((c, i) => (
              <div className="row" key={i}><span><strong>{c.client}</strong> <span className="who">· {c.part} · {c.product}</span></span><span className="amount">{c.quantity}</span></div>
            )) : <div className="empty">Nada asignado a clientes.</div>}
          </section>
        </div>
      )}

      {tab === 'Movimientos' && (
        <section className="card">
          <h2 className="section-title">Movimientos recientes</h2>
          <MovementList rows={data.movements.slice(0, 120)} onReverse={(m) => setOpen({ kind: 'reverse', movement: m })} withPiece />
        </section>
      )}

      {open?.kind === 'entry' && <EntryDialog piece={open.piece} onClose={() => setOpen(null)} onDone={done} />}
      {open?.kind === 'move' && <MoveDialog piece={open.piece} onClose={() => setOpen(null)} onDone={done} />}
      {open?.kind === 'reverse' && <ReverseDialog movement={open.movement} onClose={() => setOpen(null)} onDone={done} />}
      {open?.kind === 'supply' && <SupplyDialog supply={open.supply} onClose={() => setOpen(null)} onDone={done} />}
      {open?.kind === 'receive' && <ReceiveDialog purchase={open.purchase} onClose={() => setOpen(null)} onDone={done} />}
    </>
  );
}

function MovementList({ rows, onReverse, withPiece = false }: { rows: Movement[]; onReverse: (m: Movement) => void; withPiece?: boolean }) {
  if (!rows.length) return <div className="empty">Sin movimientos.</div>;
  return (
    <>
      {rows.map((m) => (
        <div className="row" key={m.id}>
          <span><strong>{m.code} · {m.kind}</strong> <span className="who">· {m.created_at.slice(0, 16).replace('T', ' ')}</span>
            <div className="hint">{withPiece ? `${m.part} · ` : ''}{m.source} → {m.destination}{m.client ? ` · ${m.client}` : ''}{m.order ? ` · ${m.order}` : ''}{m.job ? ` · ${m.job}` : ''}{m.notes ? ` · ${m.notes}` : ''}</div></span>
          <span className="badges">
            <span className="amount">{m.quantity}</span>
            {m.state !== 'Registrado' && <span className="badge">{m.state}</span>}
            {m.reversible && <button className="btn small ghost" onClick={() => onReverse(m)}>Revertir</button>}
          </span>
        </div>
      ))}
    </>
  );
}

function useForm(onDone: (m: string) => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [key] = useState(newKey);
  async function run(path: string, body: object, message: string) {
    setBusy(true); setError('');
    try { await api(path, { method: 'POST', body: JSON.stringify({ ...body, request_key: key }) }); onDone(message); }
    catch (e) { setError((e as Error).message); setBusy(false); }
  }
  return { busy, error, run };
}

function Actions({ busy, label, onClose }: { busy: boolean; label: string; onClose: () => void }) {
  return (
    <div className="actions">
      <button type="button" className="btn" onClick={onClose}>Cancelar</button>
      <button className="btn primary" disabled={busy}>{busy ? 'Guardando…' : label}</button>
    </div>
  );
}

function EntryDialog({ piece, onClose, onDone }: { piece: Piece; onClose: () => void; onDone: (m: string) => void }) {
  const [form, setForm] = useState({ quantity: '1', destination: 'Colección', reason: 'Stock encontrado' });
  const { busy, error, run } = useForm(onDone);
  const submit = (e: FormEvent) => { e.preventDefault(); run('/inventario/entrada', { sku_id: piece.id, quantity: Number(form.quantity), destination: form.destination, reason: form.reason }, `Entrada registrada: +${form.quantity} ${piece.label}.`); };
  return (
    <Modal title={`Entrada · ${piece.label}`} onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        <div className="pair">
          <label>Cantidad<input type="number" inputMode="numeric" min={1} required value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} /></label>
          <label>Dónde queda<select value={form.destination} onChange={(e) => setForm({ ...form, destination: e.target.value })}>{['Colección', 'Stock'].map((p) => <option key={p} value={p}>{PLACE[p]}</option>)}</select></label>
        </div>
        <label>Motivo<input required value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} /></label>
        <p className="muted">Para piezas encontradas o hechas fuera de una impresión. Lo que sale de la cola entra solo al terminar el trabajo.</p>
        {error && <div className="error">{error}</div>}
        <Actions busy={busy} label="Registrar entrada" onClose={onClose} />
      </form>
    </Modal>
  );
}

function MoveDialog({ piece, onClose, onDone }: { piece: Piece; onClose: () => void; onDone: (m: string) => void }) {
  const first = piece.collection_free > 0 ? 'Colección' : 'Stock';
  const [form, setForm] = useState({ source: first, destination: first === 'Colección' ? 'Stock' : 'Colección', quantity: '1', client: '', notes: '' });
  const { busy, error, run } = useForm(onDone);
  const free = form.source === 'Colección' ? piece.collection_free : piece.stock_free;
  const submit = (e: FormEvent) => { e.preventDefault(); run('/inventario/mover', { sku_id: piece.id, ...form, quantity: Number(form.quantity) }, form.destination === 'B2B' ? `${form.quantity} asignadas a ${form.client}.` : `${form.quantity} movidas a ${PLACE[form.destination]}.`); };
  return (
    <Modal title={`Mover · ${piece.label}`} onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        <div className="pair">
          <label>Desde<select value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value, destination: e.target.value === form.destination ? (e.target.value === 'Colección' ? 'Stock' : 'Colección') : form.destination })}>
            {['Colección', 'Stock'].map((p) => <option key={p} value={p}>{PLACE[p]} · {p === 'Colección' ? piece.collection_free : piece.stock_free} libres</option>)}</select></label>
          <label>Hacia<select value={form.destination} onChange={(e) => setForm({ ...form, destination: e.target.value })}>
            {['Colección', 'Stock', 'B2B'].filter((p) => p !== form.source).map((p) => <option key={p} value={p}>{PLACE[p]}</option>)}</select></label>
        </div>
        <label>Cantidad<input type="number" inputMode="numeric" min={1} max={Math.max(1, free)} required value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} /></label>
        {form.destination === 'B2B' && <label>Cliente B2B<input required value={form.client} onChange={(e) => setForm({ ...form, client: e.target.value })} /></label>}
        <label><span>Notas <span className="muted optional">· opcional</span></span><input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></label>
        <p className="muted">Las reservas de pedidos no se pueden mover. B2B no confirma envío ni facturación.</p>
        {error && <div className="error">{error}</div>}
        <Actions busy={busy} label="Guardar movimiento" onClose={onClose} />
      </form>
    </Modal>
  );
}

function ReverseDialog({ movement, onClose, onDone }: { movement: Movement; onClose: () => void; onDone: (m: string) => void }) {
  const [reason, setReason] = useState('');
  const { busy, error, run } = useForm(onDone);
  const submit = (e: FormEvent) => { e.preventDefault(); run(`/inventario/movimientos/${movement.id}/revertir`, { reason }, 'Movimiento revertido. Historial conservado.'); };
  return (
    <Modal title={`Revertir ${movement.code}`} onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        <p>{movement.kind} · {movement.part} · {movement.quantity} · {movement.source} → {movement.destination}</p>
        <label>Motivo<input required value={reason} onChange={(e) => setReason(e.target.value)} /></label>
        <p className="muted">Se registra el movimiento contrario; el original queda en el historial.</p>
        {error && <div className="error">{error}</div>}
        <Actions busy={busy} label="Revertir" onClose={onClose} />
      </form>
    </Modal>
  );
}

function SupplyDialog({ supply, onClose, onDone }: { supply: Supply; onClose: () => void; onDone: (m: string) => void }) {
  const [form, setForm] = useState({ kind: 'Entrada', amount: '', job_code: '', notes: '' });
  const { busy, error, run } = useForm(onDone);
  const submit = (e: FormEvent) => { e.preventDefault(); run(`/consumibles/${supply.id}/movimiento`, { ...form, amount: Number(form.amount) }, form.kind === 'Conteo' ? 'Conteo guardado.' : `${form.kind} registrada.`); };
  return (
    <Modal title={supply.name} onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        <p className="muted">Saldo actual {qty(supply.balance, supply.unit)}.</p>
        <div className="pills" role="radiogroup" aria-label="Tipo de registro">
          {['Entrada', 'Consumo', 'Conteo'].map((k) => <button type="button" key={k} role="radio" aria-checked={form.kind === k} className={`pill${form.kind === k ? ' on' : ''}`} onClick={() => setForm({ ...form, kind: k })}>{k}</button>)}
        </div>
        <label>{form.kind === 'Conteo' ? `Saldo contado · ${supply.unit}` : `Cantidad · ${supply.unit}`}<input type="number" inputMode="decimal" min={form.kind === 'Conteo' ? 0 : 0.01} step="any" required value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></label>
        {form.kind === 'Consumo' && <label><span>Trabajo <span className="muted optional">· opcional</span></span><input value={form.job_code} onChange={(e) => setForm({ ...form, job_code: e.target.value })} placeholder="JOB-0090" /></label>}
        <label><span>Notas <span className="muted optional">· opcional</span></span><input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></label>
        {form.kind === 'Conteo' && <p className="muted">El conteo fija el saldo a lo que hay en el estante y registra la diferencia.</p>}
        {error && <div className="error">{error}</div>}
        <Actions busy={busy} label={`Guardar ${form.kind.toLowerCase()}`} onClose={onClose} />
      </form>
    </Modal>
  );
}

function ReceiveDialog({ purchase, onClose, onDone }: { purchase: Purchase; onClose: () => void; onDone: (m: string) => void }) {
  const [form, setForm] = useState({ quantity: String(purchase.remaining), notes: '' });
  const { busy, error, run } = useForm(onDone);
  const path = purchase.kind === 'Piezas e insumos' ? `/compras/piezas/${purchase.id}/recibir` : `/compras/consumibles/${purchase.id}/recibir`;
  const submit = (e: FormEvent) => { e.preventDefault(); run(path, { quantity: Number(form.quantity), notes: form.notes, expected_token: purchase.token }, `Recepción de ${purchase.code} registrada.`); };
  return (
    <Modal title={`Recibir ${purchase.code}`} onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        <p><strong>{purchase.what}</strong> <span className="muted">· faltan {purchase.remaining} {purchase.unit}</span></p>
        <label>Cantidad recibida · {purchase.unit}<input type="number" inputMode="numeric" min={1} max={purchase.remaining} required value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} /></label>
        <label><span>Notas <span className="muted optional">· opcional</span></span><input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></label>
        {error && <div className="error">{error}</div>}
        <Actions busy={busy} label="Registrar recepción" onClose={onClose} />
      </form>
    </Modal>
  );
}
