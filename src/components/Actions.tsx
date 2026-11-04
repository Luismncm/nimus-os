'use client';

/**
 * The day's three hand-offs, as in the local app: deliver an order (then collect what it still owes),
 * collect a payment, and split pending pieces into jobs. Every rule lives in the API's services; these
 * forms only gather the data and show the service's own message when it refuses.
 */
import { FormEvent, useEffect, useMemo, useState } from 'react';
import Modal from '@/components/Modal';
import { api, money } from '@/lib/api';

const today = () => new Date().toLocaleDateString('en-CA');
const newKey = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`);

type SaleForm = {
  id: number; code: string; client: string; status: string; balance_cents: number; paid_cents: number;
  revision: number; quote_revision: number | null; concept: string; methods: string[]; accounts: { id: number; name: string; kind: string }[];
};

/** Money received for a sale. One request key per opened form, so a double click records one payment. */
export function PaymentDialog({ saleId, onClose, onDone }: { saleId: number; onClose: () => void; onDone: (message: string) => void }) {
  const [sale, setSale] = useState<SaleForm | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [key] = useState(newKey);
  const [form, setForm] = useState({ amount: '', paid_on: today(), method: 'Transferencia', account_id: '', concept: '', reference: '' });

  useEffect(() => {
    api<SaleForm>(`/ventas/${saleId}/cobro`).then((row) => {
      setSale(row);
      setForm((f) => ({ ...f, amount: (row.balance_cents / 100).toFixed(2), concept: row.concept, account_id: row.accounts[0] ? String(row.accounts[0].id) : '' }));
    }).catch((e) => setError(e.message));
  }, [saleId]);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!sale) return;
    setBusy(true); setError('');
    try {
      const result = await api<{ balance_cents: number }>(`/ventas/${saleId}/pagos`, {
        method: 'POST',
        body: JSON.stringify({ ...form, amount: Number(form.amount), account_id: Number(form.account_id), request_key: key,
                               expected_revision: sale.revision, expected_quote_revision: sale.quote_revision }),
      });
      onDone(result.balance_cents ? `Pago registrado. ${sale.code} aún debe ${money(result.balance_cents)}.` : `Pago registrado. ${sale.code} quedó liquidada.`);
    } catch (e) {
      setError((e as Error).message); setBusy(false);
    }
  }

  const set = (field: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [field]: e.target.value });
  return (
    <Modal title="Registrar cobro" onClose={onClose}>
      {!sale ? (error ? <div className="error">{error}</div> : <div className="empty">Cargando venta…</div>) : (
        <form className="stack" onSubmit={save}>
          <p className="muted"><strong className="ink">{sale.code} · {sale.client}</strong><br />Saldo pendiente: <span className="num">{money(sale.balance_cents)}</span></p>
          <div className="pair">
            <label>Monto recibido · MXN<input type="number" inputMode="decimal" min="0.01" step="0.01" required value={form.amount} onChange={set('amount')} /></label>
            <label>Fecha del pago<input type="date" required max={today()} value={form.paid_on} onChange={set('paid_on')} /></label>
          </div>
          <label>Método de pago<select value={form.method} onChange={set('method')}>{sale.methods.map((m) => <option key={m}>{m}</option>)}</select></label>
          {sale.accounts.length ? (
            <label>Cuenta donde se recibió<select required value={form.account_id} onChange={set('account_id')}>
              {sale.accounts.map((a) => <option key={a.id} value={a.id}>{a.name} · {a.kind}</option>)}
            </select></label>
          ) : <div className="error">Agrega o activa una cuenta en Tesorería → Cuentas para registrar el cobro.</div>}
          <label>Concepto<input required value={form.concept} onChange={set('concept')} /></label>
          <label><span>Referencia / folio <span className="muted optional">· opcional</span></span><input value={form.reference} onChange={set('reference')} /></label>
          {error && <div className="error">{error}</div>}
          <div className="actions">
            <button type="button" className="btn" onClick={onClose}>Cancelar</button>
            <button className="btn primary" disabled={busy || !sale.accounts.length}>{busy ? 'Guardando…' : 'Guardar pago recibido'}</button>
          </div>
        </form>
      )}
    </Modal>
  );
}

export type DeliverTarget = { id: number; code: string; project: string; client: string; stock: boolean; owed?: { code: string; balance_cents: number } | null };

/** Hand an order over. If its sale still owes, offer to record the payment right after, as the local app does. */
export function DeliverDialog({ order, canCollect, onClose, onDone }: {
  order: DeliverTarget; canCollect: boolean; onClose: () => void; onDone: (message: string, collectSale?: number) => void;
}) {
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [collect, setCollect] = useState(true);

  async function confirm() {
    setBusy(true); setError('');
    try {
      const result = await api<{ collect: { id: number } | null }>(`/pedidos/${order.id}/entregar`, { method: 'POST' });
      const message = order.stock ? 'Lote cerrado. Piezas disponibles en Stock.' : 'Pedido entregado; conservado en el histórico.';
      onDone(message, collect && canCollect && result.collect ? result.collect.id : undefined);
    } catch (e) {
      setError((e as Error).message); setBusy(false);
    }
  }

  return (
    <Modal title={order.stock ? 'Liberar a stock' : 'Entregar pedido'} onClose={onClose}>
      <div className="stack">
        <p><strong>{order.code} · {order.project}</strong>{order.client ? ` · ${order.client}` : ''}</p>
        <p className="muted">{order.stock ? 'Las piezas reservadas quedarán disponibles en Stock.' : 'Se descontarán las piezas reservadas y se registrará la entrega. Quedará en el histórico, de solo lectura.'}</p>
        {canCollect && order.owed && (
          <label className="check">
            <input type="checkbox" checked={collect} onChange={(e) => setCollect(e.target.checked)} />
            <span>Registrar el cobro de {order.owed.code} ({money(order.owed.balance_cents)} por cobrar) al confirmar</span>
          </label>
        )}
        {error && <div className="error">{error}</div>}
        <div className="actions">
          <button type="button" className="btn" onClick={onClose}>Cancelar</button>
          <button className="btn primary" onClick={confirm} disabled={busy}>{busy ? 'Guardando…' : order.stock ? 'Cerrar lote y liberar' : 'Confirmar entrega'}</button>
        </div>
      </div>
    </Modal>
  );
}

type Plan = {
  parts: { id: number; name: string; item: string; material: string; unassigned: number }[];
  machines: { id: number; code: string; name: string; status: string; material: string; availability: string }[];
  suggestion: { part_id: number; machine_id: number | null; quantity: number }[];
};
const NONE = 'none';
const cell = (part: number, machine: number | null) => `${part}:${machine ?? NONE}`;
const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** Every pending piece against every machine: type the units, or start from the automatic suggestion. */
export function SplitDialog({ orderId, onClose, onDone }: { orderId: number; onClose: () => void; onDone: (message: string) => void }) {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [amounts, setAmounts] = useState<Record<string, number>>({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { api<Plan>(`/pedidos/${orderId}/reparto`).then(setPlan).catch((e) => setError(e.message)); }, [orderId]);

  const columns = useMemo(() => (plan ? [...plan.machines.map((m) => ({ id: m.id as number | null, code: m.code, hint: m.availability, material: m.material })),
                                          { id: null, code: 'Sin máquina', hint: 'Fuera de impresora', material: '' }] : []), [plan]);
  const allocations = plan ? plan.parts.flatMap((p) => columns.map((c) => ({ part_id: p.id, machine_id: c.id, quantity: amounts[cell(p.id, c.id)] || 0 }))).filter((a) => a.quantity > 0) : [];
  const over = plan ? plan.parts.map((p) => ({ p, extra: columns.reduce((n, c) => n + (amounts[cell(p.id, c.id)] || 0), 0) - p.unassigned })).filter((r) => r.extra > 0) : [];
  const assigned = allocations.reduce((n, a) => n + a.quantity, 0);
  const pending = plan ? plan.parts.reduce((n, p) => n + p.unassigned, 0) : 0;

  function suggest() {
    if (!plan) return;
    setAmounts(Object.fromEntries(plan.suggestion.map((s) => [cell(s.part_id, s.machine_id), s.quantity])));
  }

  async function save() {
    setBusy(true); setError('');
    try {
      const result = await api<{ jobs: number }>(`/pedidos/${orderId}/reparto`, { method: 'POST', body: JSON.stringify({ allocations }) });
      onDone(`${result.jobs === 1 ? '1 trabajo creado' : `${result.jobs} trabajos creados`}. Ya puedes iniciarlos desde la cola o las máquinas.`);
    } catch (e) {
      setError((e as Error).message); setBusy(false);
    }
  }

  return (
    <Modal title="Repartir piezas pendientes" onClose={onClose} wide>
      {!plan ? (error ? <div className="error">{error}</div> : <div className="empty">Cargando piezas…</div>) : !plan.parts.length ? (
        <div className="empty">Todas las piezas ya tienen trabajo asignado.</div>
      ) : (
        <div className="stack">
          <div className="toolbar">
            <span className="muted">{plural(plan.parts.length, 'pieza', 'piezas')} · {plural(pending, 'unidad', 'unidades')} sin asignar. Las del mismo material aparecen juntas.</span>
            <span className="badges">
              <button type="button" className="btn small" onClick={suggest}>Distribuir automáticamente</button>
              <button type="button" className="btn small ghost" onClick={() => setAmounts({})}>Vaciar</button>
            </span>
          </div>
          <div className="table-wrap split">
            <table>
              <thead>
                <tr>
                  <th>Pieza</th><th className="right">Sin asignar</th>
                  {columns.map((c) => <th key={c.code} title={c.hint}>{c.code}<div className="hint">{[c.material, c.hint].filter(Boolean).join(' · ')}</div></th>)}
                </tr>
              </thead>
              <tbody>
                {plan.parts.map((p) => (
                  <tr key={p.id} className={over.some((o) => o.p.id === p.id) ? 'warn' : undefined}>
                    <td><strong>{p.name}</strong><div className="hint">{p.item}{p.material ? ` · ${p.material}` : ''}</div></td>
                    <td className="right num">{p.unassigned}</td>
                    {columns.map((c) => (
                      <td key={c.code}>
                        <input type="number" inputMode="numeric" min={0} max={p.unassigned} step={1} aria-label={`${p.name} en ${c.code}`}
                               value={amounts[cell(p.id, c.id)] || ''} placeholder="0"
                               onChange={(e) => setAmounts({ ...amounts, [cell(p.id, c.id)]: Math.max(0, Math.floor(Number(e.target.value) || 0)) })} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {over.length ? <div className="error">Reduce el reparto antes de guardar · {over.map((o) => `${o.p.name}: sobran ${o.extra}`).join(' · ')}</div>
            : <p className="muted">{plural(assigned, 'unidad', 'unidades')} en {plural(allocations.length, 'trabajo', 'trabajos')} · {pending - assigned} sin asignar. Se crean en cola con la prioridad del pedido.</p>}
          {error && <div className="error">{error}</div>}
          <div className="actions">
            <button type="button" className="btn" onClick={onClose}>Cancelar</button>
            <button className="btn primary" onClick={save} disabled={busy || !allocations.length || over.length > 0}>
              {busy ? 'Guardando…' : `Crear ${plural(allocations.length, 'trabajo', 'trabajos')}`}
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}
