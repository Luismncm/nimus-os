'use client';

import { useRouter } from 'next/navigation';
import { FormEvent, useCallback, useEffect, useState } from 'react';
import Modal from '@/components/Modal';
import { newKey } from '@/components/Production';
import { api } from '@/lib/api';

type Product = { name: string; variant: string; recipe_id: number | null };

type Plan = { fingerprint: string; lines: { component_id: number; name: string; variant: string; supply: string; needed: number; available: number; reserved: number; to_make: number; to_buy: number }[] };

/** Recalculates the plan as quantity or stock use change; the order is refused if stock moved since. */
export function RecipeOrderDialog({ product, priorities, onClose }: { product: Product; priorities: string[]; onClose: () => void }) {
  const router = useRouter();
  const [key] = useState(newKey);
  const [form, setForm] = useState({ quantity: '1', fulfillment: 'Cliente', client: '', project: '', deadline: '', priority: 'Media', use_stock: true });
  const [plan, setPlan] = useState<Plan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const quantity = Math.max(1, Math.floor(Number(form.quantity) || 1));
  const recalc = useCallback(() => {
    setPlan(null);
    api<Plan>(`/catalogo/recetas/${product.recipe_id}/plan?cantidad=${quantity}&stock=${form.use_stock}`).then(setPlan).catch((e) => setError(e.message));
  }, [product.recipe_id, quantity, form.use_stock]);
  useEffect(() => { const t = setTimeout(recalc, 250); return () => clearTimeout(t); }, [recalc]);
  async function save(e: FormEvent) {
    e.preventDefault(); if (!plan) return; setBusy(true); setError('');
    try {
      const r = await api<{ order_id: number }>(`/catalogo/recetas/${product.recipe_id}/pedido`, { method: 'POST', body: JSON.stringify({
        ...form, quantity, deadline: form.deadline, expected_fingerprint: plan.fingerprint, request_key: key }) });
      router.push(`/pedidos/${r.order_id}`);
    } catch (err) { setError((err as Error).message); setBusy(false); }
  }
  return (
    <Modal title={`Pedido de ${product.name}${product.variant ? ` · ${product.variant}` : ''}`} onClose={onClose} wide>
      <form className="stack" onSubmit={save}>
        <div className="pair">
          <label>Cantidad<input type="number" inputMode="numeric" min={1} required value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} /></label>
          <label>Para<select value={form.fulfillment} onChange={(e) => setForm({ ...form, fulfillment: e.target.value })}><option value="Cliente">Un cliente</option><option value="Stock">Producir para stock</option></select></label>
        </div>
        {form.fulfillment === 'Cliente' && <label>Cliente<input required value={form.client} onChange={(e) => setForm({ ...form, client: e.target.value })} /></label>}
        <div className="pair">
          <label><span>Fecha de entrega <span className="muted optional">· opcional</span></span><input type="date" value={form.deadline} onChange={(e) => setForm({ ...form, deadline: e.target.value })} /></label>
          <label>Prioridad<select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>{priorities.map((p) => <option key={p}>{p}</option>)}</select></label>
        </div>
        <label><span>Proyecto <span className="muted optional">· opcional</span></span><input value={form.project} onChange={(e) => setForm({ ...form, project: e.target.value })} placeholder={`${product.name} ×${quantity}`} /></label>
        <label className="check"><input type="checkbox" checked={form.use_stock} onChange={(e) => setForm({ ...form, use_stock: e.target.checked })} /><span>Usar existencias disponibles (las reserva para este pedido)</span></label>
        <div className="table-wrap split">
          <table>
            <thead><tr><th>Componente</th><th className="right">Necesarias</th><th className="right">Disponibles</th><th className="right">Se reservan</th><th className="right">A fabricar</th><th className="right">A comprar</th></tr></thead>
            <tbody>{plan ? plan.lines.map((l) => (
              <tr key={l.component_id}><td><strong>{l.name}</strong>{l.variant ? ` · ${l.variant}` : ''}<div className="hint">{l.supply}</div></td>
                <td className="right num">{l.needed}</td><td className="right num">{l.available}</td><td className="right num">{l.reserved}</td>
                <td className="right num">{l.to_make}</td><td className="right num">{l.to_buy}</td></tr>
            )) : <tr><td colSpan={6} className="muted">Calculando…</td></tr>}</tbody>
          </table>
        </div>
        {error && <div className="error">{error}{error.includes('Recalcular') && <> <button type="button" className="btn small" onClick={() => { setError(''); recalc(); }}>Recalcular</button></>}</div>}
        <div className="actions">
          <button type="button" className="btn" onClick={onClose}>Cancelar</button>
          <button className="btn primary" disabled={busy || !plan}>{busy ? 'Creando…' : 'Crear y abrir pedido'}</button>
        </div>
      </form>
    </Modal>
  );
}
