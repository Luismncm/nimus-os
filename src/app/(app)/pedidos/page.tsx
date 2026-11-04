'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';

type Order = { id: number; code: string; project: string; client: string; status: string; priority: string; deadline: string | null; progress: number; fabrication: string; fulfillment: string | null; prototype: boolean; cancelled: boolean };

const STATUS_TONE: Record<string, string> = { Bloqueado: 'red', Listo: 'green', 'En producción': 'blue', Entregado: '', Pendiente: 'orange' };

export default function Pedidos() {
  const router = useRouter();
  const [orders, setOrders] = useState<Order[] | null>(null);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [scope, setScope] = useState<'Activos' | 'Entregados' | 'Todos'>('Activos');
  useEffect(() => { api<Order[]>('/pedidos').then(setOrders).catch((e) => setError(e.message)); }, []);

  const shown = useMemo(() => (orders || []).filter((o) =>
    (scope === 'Todos' || (scope === 'Entregados') === (o.status === 'Entregado'))
    && `${o.code} ${o.project} ${o.client}`.toLowerCase().includes(search.toLowerCase())), [orders, scope, search]);

  if (error) return <div className="error">{error}</div>;
  return (
    <>
      <div className="head">
        <div>
          <h1>Pedidos</h1>
          <p>Toca un pedido para ver sus piezas, su rastreo comercial y lo que falta cobrar.</p>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {(['Activos', 'Entregados', 'Todos'] as const).map((s) => (
            <button key={s} className={`btn${scope === s ? ' primary' : ''}`} onClick={() => setScope(s)} aria-pressed={scope === s}>{s}</button>
          ))}
        </div>
      </div>
      <div style={{ marginBottom: 14, maxWidth: 420 }}>
        <input type="search" placeholder="Código, cliente o proyecto" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Buscar pedido" />
      </div>
      {!orders ? <div className="empty">Cargando pedidos…</div> : (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Pedido</th><th>Proyecto</th><th>Cliente</th><th>Estado</th><th>Entrega</th><th>Fabricación</th></tr></thead>
            <tbody>
              {shown.map((o) => (
                <tr key={o.id} tabIndex={0} onClick={() => router.push(`/pedidos/${o.id}`)}
                    onKeyDown={(e) => { if (e.key === 'Enter') router.push(`/pedidos/${o.id}`); }}>
                  <td><strong>{o.code}</strong>{o.prototype && <span className="badge accent" style={{ marginLeft: 6 }}>Prototipo</span>}</td>
                  <td>{o.project}</td>
                  <td className="muted">{o.client || '—'}</td>
                  <td><span className={`badge ${STATUS_TONE[o.status] ?? ''}`}>{o.status}</span></td>
                  {/* Prototypes and stock lots are never delivered to a client, so they need no delivery date. */}
                  <td className="num">{o.deadline || (o.prototype || o.fulfillment === 'Stock' ? <span className="muted">—</span> : <span className="badge orange">Sin fecha</span>)}</td>
                  <td><span className="bar"><span style={{ width: `${o.progress}%` }} /></span></td>
                </tr>
              ))}
              {!shown.length && <tr><td colSpan={6} className="empty">Sin pedidos para esta búsqueda.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
