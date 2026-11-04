'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { DeliverDialog, DeliverTarget, PaymentDialog } from '@/components/Actions';
import { api, longDate, money } from '@/lib/api';

type MoneyRow = { id: number; code: string; party: string; balance_cents: number; due_on: string | null; overdue: boolean };
type Today = {
  date: string;
  produce: { units: number; pieces: number; available_machines: number };
  deliver: { overdue: number; today: number; ready: number; rows: (DeliverTarget & { deadline: string | null })[] };
  collect: { total_cents: number; overdue: number; rows: MoneyRow[] } | null;
  pay: { total_cents: number; overdue: number; rows: MoneyRow[] } | null;
  attention: { id: number; code: string; project: string; client: string; status: string; deadline: string | null; reasons: string[]; progress: number }[];
  machines: { id: number; code: string; name: string; status: string; current: string | null; next: string | null }[];
};

const REASON_TONE: Record<string, string> = { 'Entrega vencida': 'red', Bloqueado: 'red', 'Entrega hoy': 'orange', 'Insumos pendientes': 'orange', 'Listo para preparar': 'green' };

function MoneyPanel({ title, data, onCollect }: { title: string; data: NonNullable<Today['collect']>; onCollect?: (id: number) => void }) {
  return (
    <section className="card">
      <h2 className="section-title">{title} · <span className="muted num">{money(data.total_cents)}</span></h2>
      {data.rows.length ? data.rows.map((r) => (
        <div className="row" key={r.id}>
          <span><strong>{r.code}</strong> <span className="who">· {r.party}</span></span>
          <span className="badges">
            <span className={`badge ${r.overdue ? 'red' : 'blue'}`}>{r.overdue ? 'Vencido' : r.due_on ? `Vence ${r.due_on}` : 'Sin fecha'}</span>
            <span className="amount">{money(r.balance_cents)}</span>
            {onCollect && <button className="btn small" onClick={() => onCollect(r.id)} aria-label={`Cobrar ${r.code}`}>Cobrar</button>}
          </span>
        </div>
      )) : <div className="empty">Al día.</div>}
    </section>
  );
}

export default function Hoy() {
  const [data, setData] = useState<Today | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [deliver, setDeliver] = useState<DeliverTarget | null>(null);
  const [pay, setPay] = useState<number | null>(null);
  const load = useCallback(() => api<Today>('/hoy').then(setData).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);
  if (error) return <div className="error">{error}</div>;
  if (!data) return <div className="empty">Cargando el día…</div>;
  const line = [
    data.deliver.overdue && `${data.deliver.overdue} entregas vencidas`,
    data.deliver.today && `${data.deliver.today} para hoy`,
    `${data.machines.filter((m) => m.status === 'Imprimiendo').length} de ${data.machines.length} impresoras trabajando`,
  ].filter(Boolean).join(', ');

  return (
    <>
      <div className="head">
        <div>
          <h1>Hoy · {longDate(data.date)}</h1>
          <p>{line}.</p>
        </div>
      </div>

      {notice && <div className="notice" role="status">{notice}<button onClick={() => setNotice('')} aria-label="Ocultar aviso">×</button></div>}

      <div className="grid pulse">
        <div className="card tile"><div className="label">Producir</div><div className="value">{data.produce.units}</div><span className="muted">{data.produce.pieces} piezas por repartir</span></div>
        <div className={`card tile ${data.deliver.overdue ? 'red' : data.deliver.today ? 'orange' : ''}`}><div className="label">Entregar</div><div className="value">{data.deliver.overdue + data.deliver.today + data.deliver.ready}</div>
          <div className="badges">{data.deliver.overdue > 0 && <span className="badge red">{data.deliver.overdue} vencidas</span>}{data.deliver.today > 0 && <span className="badge orange">{data.deliver.today} hoy</span>}{data.deliver.ready > 0 && <span className="badge green">{data.deliver.ready} listos</span>}</div></div>
        {data.collect && <div className={`card tile ${data.collect.overdue ? 'orange' : ''}`}><div className="label">Cobrar</div><div className="value">{money(data.collect.total_cents)}</div><span className="muted">{data.collect.overdue} vencidos</span></div>}
        {data.pay && <div className={`card tile ${data.pay.overdue ? 'orange' : ''}`}><div className="label">Pagar</div><div className="value">{money(data.pay.total_cents)}</div><span className="muted">{data.pay.overdue} vencidos</span></div>}
      </div>

      {data.deliver.rows.length > 0 && (
        <section className="card" style={{ marginBottom: 22 }}>
          <h2 className="section-title">Listos para entregar</h2>
          {data.deliver.rows.map((o) => (
            <div className="row" key={o.id}>
              <Link href={`/pedidos/${o.id}`} style={{ color: 'inherit' }}>
                <strong>{o.code}</strong> <span className="who">· {o.project}{o.client ? ` · ${o.client}` : ''}{o.deadline ? ` · entrega ${o.deadline}` : ''}</span>
              </Link>
              <span className="badges">
                {o.owed && <span className="badge orange">{money(o.owed.balance_cents)} por cobrar</span>}
                <button className="btn small" onClick={() => setDeliver(o)}>{o.stock ? 'Liberar a stock' : 'Entregar'}</button>
              </span>
            </div>
          ))}
        </section>
      )}

      <div className="grid two" style={{ marginBottom: 22 }}>
        <section className="card">
          <h2 className="section-title">Pedidos por atender</h2>
          {data.attention.length ? data.attention.map((o) => (
            <Link href={`/pedidos/${o.id}`} className="row" key={o.id} style={{ color: 'inherit' }}>
              <span>
                <strong>{o.code}</strong> <span className="who">· {o.project}{o.client ? ` · ${o.client}` : ''}</span>
                <div className="badges" style={{ marginTop: 4 }}>{o.reasons.map((r) => <span key={r} className={`badge ${REASON_TONE[r] || 'accent'}`}>{r}</span>)}</div>
              </span>
              <span className="bar" aria-label={`${o.progress}% fabricado`}><span style={{ width: `${o.progress}%` }} /></span>
            </Link>
          )) : <div className="empty">Nada pendiente.</div>}
        </section>
        <section className="card">
          <h2 className="section-title">Taller ahora</h2>
          {data.machines.map((m) => (
            <div className="row" key={m.id}>
              <span><strong>{m.code}</strong> <span className="who">· {m.current ? `Imprimiendo ${m.current}` : m.next ? `Siguiente: ${m.next}` : 'Libre'}</span></span>
              <span className={`badge ${m.status === 'Disponible' ? 'green' : m.status === 'Imprimiendo' ? 'blue' : 'orange'}`}>{m.status}</span>
            </div>
          ))}
        </section>
      </div>

      {data.collect && data.pay && (
        <div className="grid two">
          <MoneyPanel title="Cobros prioritarios" data={data.collect} onCollect={setPay} />
          <MoneyPanel title="Pagos prioritarios" data={data.pay} />
        </div>
      )}

      {deliver && (
        <DeliverDialog order={deliver} canCollect={!!data.collect} onClose={() => setDeliver(null)}
                       onDone={(message, sale) => { setNotice(message); setDeliver(null); setPay(sale ?? null); load(); }} />
      )}
      {pay !== null && <PaymentDialog saleId={pay} onClose={() => setPay(null)} onDone={(m) => { setNotice(m); setPay(null); load(); }} />}
    </>
  );
}
