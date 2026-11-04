'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import { DeliverDialog, PaymentDialog, SplitDialog } from '@/components/Actions';
import { useUser } from '@/components/Shell';
import { api, money } from '@/lib/api';

type Detail = {
  id: number; code: string; project: string; client: string; status: string; priority: string; deadline: string | null; notes: string; progress: number;
  fulfillment: string | null;
  items: { id: number; name: string; quantity: number; parts: { id: number; name: string; required: number; process: string; material: string; unassigned: number }[] }[];
  trail: {
    quote: { id: number; code: string; total_cents: number } | null;
    sale: { id: number; code: string; status: string; payment_status: string; balance_cents: number; due_on: string | null } | null;
    missing_sale: boolean; missing_deadline: boolean;
  };
  step: { lane: string; action: string; pending: string[]; blocked: boolean; delivered: boolean; can_deliver: boolean; unassigned: number };
};

type Open = { kind: 'deliver' } | { kind: 'split' } | { kind: 'pay'; sale: number } | null;

export default function Pedido() {
  const { id } = useParams<{ id: string }>();
  const user = useUser();
  const [order, setOrder] = useState<Detail | null>(null);
  const [error, setError] = useState('');
  const [open, setOpen] = useState<Open>(null);
  const [notice, setNotice] = useState('');
  const load = useCallback(() => api<Detail>(`/pedidos/${id}`).then(setOrder).catch((e) => setError(e.message)), [id]);
  useEffect(() => { load(); }, [load]);
  if (error) return <div className="error">{error}</div>;
  if (!order) return <div className="empty">Cargando pedido…</div>;
  const { trail, step } = order;
  const owed = trail.sale && trail.sale.status === 'Activa' && trail.sale.balance_cents > 0 ? trail.sale : null;
  const stock = order.fulfillment === 'Stock';
  const done = (message: string, next: Open = null) => { setNotice(message); setOpen(next); load(); };

  // One primary action, the same order the local stepper uses: hand over when it can, else assign what is pending.
  const primary = step.can_deliver
    ? <button className="btn primary" onClick={() => setOpen({ kind: 'deliver' })}>{stock ? 'Liberar a stock' : 'Confirmar entrega'}</button>
    : !step.delivered && step.unassigned > 0
      ? <button className="btn primary" onClick={() => setOpen({ kind: 'split' })}>Repartir piezas · {step.unassigned} sin asignar</button>
      : null;

  return (
    <>
      <Link href="/pedidos" className="muted">← Todos los pedidos</Link>
      <div className="head" style={{ marginTop: 8 }}>
        <div>
          <h1>{order.code} · {order.project}</h1>
          <p>{order.client || 'Sin cliente'} · Prioridad {order.priority.toLowerCase()} · {order.deadline ? `Entrega ${order.deadline}` : 'Sin fecha de entrega'}</p>
        </div>
        <span className={`badge ${step.delivered ? 'green' : step.blocked ? 'red' : 'blue'}`}>{order.status}</span>
      </div>

      {notice && <div className="notice" role="status">{notice}<button onClick={() => setNotice('')} aria-label="Ocultar aviso">×</button></div>}

      {!step.delivered && (
        <section className="card next" style={{ marginBottom: 18 }}>
          <div className="what">
            <strong>Siguiente paso · {step.action}</strong>
            <span>{step.lane}{step.lane !== 'Producir' && step.lane !== 'Planificar' && step.pending.length ? ` · falta: ${step.pending.join(', ')}` : ''}</span>
          </div>
          {primary}
        </section>
      )}

      <section className="card" style={{ marginBottom: 18 }}>
        <h2 className="section-title">Rastreo</h2>
        <div className="toolbar">
          <div className="badges">
            {trail.quote && <span className="badge accent">{trail.quote.code} · cotizado {money(trail.quote.total_cents)}</span>}
            {trail.sale && <span className={`badge ${owed ? 'orange' : 'green'}`}>{trail.sale.code} · {owed ? `por cobrar ${money(trail.sale.balance_cents)}` : trail.sale.payment_status}</span>}
            {trail.sale?.due_on && <span className="badge">Vence {trail.sale.due_on}</span>}
            {trail.missing_sale && <span className="badge orange">Sin venta vinculada</span>}
            {trail.missing_deadline && <span className="badge orange">Sin fecha de entrega</span>}
            {!trail.quote && !trail.sale && !trail.missing_sale && <span className="muted">Pedido interno, sin venta.</span>}
          </div>
          {owed && user?.role === 'admin' && <button className="btn small" onClick={() => setOpen({ kind: 'pay', sale: owed.id })}>Cobrar</button>}
        </div>
      </section>

      <section className="card">
        <h2 className="section-title">Productos y piezas · {order.progress}% fabricado</h2>
        {order.items.map((item) => (
          <div key={item.id} style={{ marginBottom: 14 }}>
            <strong>{item.name}</strong> <span className="muted">×{item.quantity}</span>
            {item.parts.map((p) => (
              <div className="row" key={p.id}>
                <span>{p.name} <span className="who">· {p.process}{p.material ? ` · ${p.material}` : ''}</span></span>
                <span className="badges">
                  <span className="badge">{p.required} requeridas</span>
                  {p.unassigned > 0 && <span className="badge orange">{p.unassigned} sin asignar</span>}
                </span>
              </div>
            ))}
          </div>
        ))}
      </section>

      {open?.kind === 'deliver' && (
        <DeliverDialog order={{ id: order.id, code: order.code, project: order.project, client: order.client, stock, owed }}
                       canCollect={user?.role === 'admin'} onClose={() => setOpen(null)}
                       onDone={(message, sale) => done(message, sale ? { kind: 'pay', sale } : null)} />
      )}
      {open?.kind === 'split' && <SplitDialog orderId={order.id} onClose={() => setOpen(null)} onDone={(m) => done(m)} />}
      {open?.kind === 'pay' && <PaymentDialog saleId={open.sale} onClose={() => setOpen(null)} onDone={(m) => done(m)} />}
    </>
  );
}
