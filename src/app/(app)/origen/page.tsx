'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { RecipeOrderDialog } from '@/components/RecipeOrder';
import { api } from '@/lib/api';
import { CloseIcon } from '@/components/Icon';

type Lamp = { id: number; code: string; name: string; model: string; color: string; recipe_id: number | null; version: number | null; lines: { name: string; variant: string; material: string; quantity: number }[] };
type Order = { id: number; code: string; project: string; client: string; status: string; can_reserve: boolean; needs: { name: string; supply: string; quantity: number; covered: number; pending: number }[] };
type Data = { models: string[]; colors: string[]; lamps: Lamp[]; orders: Order[] };
const PRIORITIES = ['Alta', 'Media', 'Baja'];

export default function Origen() {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState<{ text: string; tone: 'ok' | 'bad' } | null>(null);
  const [model, setModel] = useState('Todos');
  const [color, setColor] = useState('Todos');
  const [order, setOrder] = useState<Lamp | null>(null);
  const load = useCallback(() => api<Data>('/origen').then(setData).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);

  async function reserve(o: Order) {
    try {
      const r = await api<{ reserved: number }>(`/origen/pedidos/${o.id}/reservar`, { method: 'POST' });
      setNotice({ text: r.reserved ? `${o.code}: ${r.reserved} insumos reservados desde existencias.` : `${o.code}: no hay insumos disponibles para reservar.`, tone: r.reserved ? 'ok' : 'bad' });
      load();
    } catch (e) { setNotice({ text: (e as Error).message, tone: 'bad' }); }
  }

  if (error) return <div className="error">{error}</div>;
  if (!data) return <div className="empty">Cargando Colección Origen…</div>;
  const lamps = data.lamps.filter((l) => (model === 'Todos' || l.model === model) && (color === 'Todos' || l.color === color));
  return (
    <>
      <div className="head">
        <div><h1>Colección Origen</h1><p>{data.lamps.length} lámparas publicadas · {data.models.length} modelos de pantalla × {data.colors.length} colores de base · {data.orders.length} pedidos activos</p></div>
        <Link className="btn" href="/inventario">Ver inventario</Link>
      </div>
      {notice && <div className={notice.tone === 'ok' ? 'notice' : 'error notice-bad'} role="status">{notice.text}<button onClick={() => setNotice(null)} aria-label="Ocultar aviso"><CloseIcon /></button></div>}

      {data.orders.length > 0 && (
        <section className="card" style={{ marginBottom: 18 }}>
          <h2 className="section-title">Pedidos de lámparas en curso</h2>
          {data.orders.map((o) => {
            // One line per component across the order's lamps: "4 FOCO · Estándar", not one per lamp.
            const sums = new Map<string, number>();
            o.needs.filter((n) => n.pending > 0).forEach((n) => sums.set(n.name, (sums.get(n.name) || 0) + n.pending));
            const pending = Array.from(sums, ([name, count]) => ({ name, pending: count }));
            return (
              <div className="row" key={o.id}>
                <span><Link href={`/pedidos/${o.id}`} style={{ color: 'inherit' }}><strong>{o.code}</strong> <span className="who">· {o.project}{o.client ? ` · ${o.client}` : ''} · {o.status}</span></Link>
                  <div className="hint">{pending.length ? `Faltan: ${pending.map((n) => `${n.pending} ${n.name}`).join(', ')}` : 'Todo cubierto o reservado'}</div></span>
                {o.can_reserve && <button className="btn small" onClick={() => reserve(o)}>Reservar insumos disponibles</button>}
              </div>
            );
          })}
        </section>
      )}

      <div className="filters">
        <select value={model} onChange={(e) => setModel(e.target.value)} aria-label="Modelo de pantalla"><option value="Todos">Todos los modelos</option>{data.models.map((m) => <option key={m}>{m}</option>)}</select>
        <select value={color} onChange={(e) => setColor(e.target.value)} aria-label="Color de base"><option value="Todos">Todos los colores</option>{data.colors.map((c) => <option key={c}>{c}</option>)}</select>
      </div>
      <div className="grid cards3">
        {lamps.map((l) => (
          <section className="card machine" key={l.id}>
            <div className="toolbar"><div><strong className="big">{l.model || l.name}</strong><div className="hint">{l.color} · {l.code}</div></div>{l.version && <span className="badge accent">Receta v{l.version}</span>}</div>
            <div>{l.lines.map((c, i) => <div className="row" key={i}><span>{c.name}{c.variant ? ` · ${c.variant}` : ''} <span className="who">· {c.material}</span></span><span className="amount">×{c.quantity}</span></div>)}</div>
            {l.recipe_id && <button className="btn small primary" onClick={() => setOrder(l)}>Crear pedido</button>}
          </section>
        ))}
        {!lamps.length && <div className="card empty">Sin lámparas para este modelo y color.</div>}
      </div>
      <p className="muted" style={{ marginTop: 16 }}>Crear lámparas nuevas, modelos de pantalla y colores de base sigue en la app local por ahora.</p>
      {order && <RecipeOrderDialog product={{ name: order.model || order.name, variant: order.color, recipe_id: order.recipe_id }} priorities={PRIORITIES} onClose={() => setOrder(null)} />}
    </>
  );
}
