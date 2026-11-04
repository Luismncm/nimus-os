'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { api, money } from '@/lib/api';

type Recipe = { product_id: number; recipe_id: number; name: string; variant: string; collection: string; total_cents: number; known_cents: number; missing: string[]; lines: { name: string; variant: string; quantity: number; supply: string; material_cents: number | null; machine_cents: number | null; fixed_cents: number | null; line_cents: number | null; missing: string[] }[]; extras: { label: string; cents: number }[] };
type Sale = { id: number; code: string; client: string; project: string; sold_on: string; net_cents: number; cost_cents: number | null; profit_cents: number | null; margin_percent: number | null; state: string };
type Order = { order_id: number; code: string; project: string; client: string; status: string; development: boolean; revenue_cents: number | null; cost_cents: number; estimated_cents: number; margin_cents: number | null; margin_percent: number | null; complete: boolean; costed_jobs: number; job_count: number; consumables_cents: number; extras_cents: number };
type Data = { recipes: Recipe[]; sales: Sale[]; orders: Order[] };
const TABS = ['Recetas y costos', 'Utilidad por venta', 'Costo por pedido'] as const;
const pct = (v: number | null) => (v == null ? '—' : `${v.toLocaleString('es-MX', { maximumFractionDigits: 1 })}%`);
const cents = (v: number | null | undefined) => (v == null ? '—' : money(v));

export default function Costos() {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState('');
  const [tab, setTab] = useState<(typeof TABS)[number]>('Recetas y costos');
  const [recipe, setRecipe] = useState<number | null>(null);
  useEffect(() => { api<Data>('/costos').then((d) => { setData(d); setRecipe(d.recipes[0]?.recipe_id ?? null); }).catch((e) => setError(e.message)); }, []);
  if (error) return <div className="error">{error}</div>;
  if (!data) return <div className="empty">Calculando costos…</div>;
  const complete = data.sales.filter((s) => s.state === 'Completo');
  const r = data.recipes.find((x) => x.recipe_id === recipe);
  return (
    <>
      <div className="head"><div><h1>Costos y utilidad</h1><p>Costos sin IVA. La utilidad total solo suma ventas con todas sus partidas costeadas.</p></div></div>
      <div className="pills" role="tablist" style={{ marginBottom: 16 }}>
        {TABS.map((t) => <button key={t} role="tab" aria-selected={tab === t} className={`pill${tab === t ? ' on' : ''}`} onClick={() => setTab(t)}>{t}</button>)}
      </div>

      {tab === 'Recetas y costos' && (
        <>
          <div className="filters">
            <select value={recipe ?? ''} onChange={(e) => setRecipe(Number(e.target.value))} aria-label="Receta a costear">
              {data.recipes.map((x) => <option key={x.recipe_id} value={x.recipe_id}>{x.name}{x.variant ? ` · ${x.variant}` : ''}</option>)}
            </select>
            <Link className="btn small ghost" href="/catalogo">Ver catálogo</Link>
          </div>
          {r ? (
            <section className="card">
              <div className="toolbar"><div><strong className="big">{r.name}{r.variant ? ` · ${r.variant}` : ''}</strong><div className="hint">{r.collection}</div></div>
                <div className="totals num"><strong>Costo por pieza {money(r.total_cents)}</strong>{r.missing.length > 0 && <div className="issue">Faltan datos: {r.missing.join(', ')}</div>}</div></div>
              <div className="table-wrap split" style={{ marginTop: 12 }}>
                <table>
                  <thead><tr><th>Componente</th><th className="right">Cantidad</th><th className="right">Material</th><th className="right">Máquina</th><th className="right">Fijo</th><th className="right">Total</th></tr></thead>
                  <tbody>{r.lines.map((l, i) => (
                    <tr key={i} style={{ cursor: 'default' }}><td><strong>{l.name}</strong>{l.variant ? ` · ${l.variant}` : ''}<div className="hint">{l.supply}{l.missing.length ? ` · falta ${l.missing.join(', ')}` : ''}</div></td>
                      <td className="right num">{l.quantity}</td><td className="right num">{cents(l.material_cents)}</td><td className="right num">{cents(l.machine_cents)}</td><td className="right num">{cents(l.fixed_cents)}</td><td className="right num">{cents(l.line_cents)}</td></tr>
                  ))}</tbody>
                </table>
              </div>
              {r.extras.length > 0 && <p className="hint" style={{ marginTop: 10 }}>Directos por lámpara: {r.extras.map((x) => `${x.label} ${money(x.cents)}`).join(' · ')}</p>}
            </section>
          ) : <div className="card empty">Publica una receta en Catálogo para costearla.</div>}
        </>
      )}

      {tab === 'Utilidad por venta' && (
        <>
          <div className="grid pulse">
            <div className="card tile"><div className="label">Ventas con costo completo</div><div className="value">{complete.length} / {data.sales.length}</div></div>
            <div className="card tile"><div className="label">Venta neta · costos completos</div><div className="value">{money(complete.reduce((n, s) => n + s.net_cents, 0))}</div></div>
            <div className="card tile green"><div className="label">Utilidad bruta · costos completos</div><div className="value">{complete.length ? money(complete.reduce((n, s) => n + (s.profit_cents || 0), 0)) : 'Pendiente'}</div></div>
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Venta</th><th>Cliente</th><th className="right">Venta neta</th><th className="right">Costo</th><th className="right">Utilidad</th><th className="right">Margen</th><th>Costeo</th></tr></thead>
              <tbody>{data.sales.map((s) => (
                <tr key={s.id} onClick={() => (window.location.href = `/ventas?venta=${s.id}`)}><td><strong>{s.code}</strong><div className="hint">{s.project}</div></td><td>{s.client}</td>
                  <td className="right num">{money(s.net_cents)}</td><td className="right num">{cents(s.cost_cents)}</td><td className="right num">{cents(s.profit_cents)}</td><td className="right num">{pct(s.margin_percent)}</td>
                  <td><span className={`badge ${s.state === 'Completo' ? 'green' : s.state === 'Revisar cambios' ? 'orange' : ''}`}>{s.state}</span></td></tr>
              ))}</tbody>
            </table>
          </div>
          <p className="muted" style={{ marginTop: 10 }}>Asignar los costos de una venta sigue en la app local por ahora.</p>
        </>
      )}

      {tab === 'Costo por pedido' && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Pedido</th><th>Estado</th><th className="right">Venta neta</th><th className="right">Costo real</th><th className="right">Margen</th><th>Costeo</th></tr></thead>
            <tbody>{data.orders.map((o) => (
              <tr key={o.order_id} onClick={() => (window.location.href = `/pedidos/${o.order_id}`)}>
                <td><strong>{o.code}</strong><div className="hint">{o.project}{o.client ? ` · ${o.client}` : ''}{o.development ? ' · desarrollo' : ''}</div></td><td>{o.status}</td>
                <td className="right num">{o.development ? 'No es venta' : cents(o.revenue_cents)}</td><td className="right num">{money(o.cost_cents)}<div className="hint">estimado {money(o.estimated_cents)}</div></td>
                <td className="right num">{o.development ? '—' : `${cents(o.margin_cents)} · ${pct(o.margin_percent)}`}</td>
                <td><span className={`badge ${o.complete ? 'green' : ''}`}>{o.complete ? 'Completo' : `${o.costed_jobs}/${o.job_count} impresiones`}</span></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </>
  );
}
