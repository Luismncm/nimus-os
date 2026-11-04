'use client';

import { useEffect, useState } from 'react';
import { api, money } from '@/lib/api';

type Summary = { sold_cents: number; sales_count: number; ticket_cents: number; collected_cents: number; expenses_cents: number; paid_out_cents: number; cash_cents: number; delivered: number; promised: number; on_time: number; on_time_percent: number | null; lead_days: number | null; lots: number; pieces: number; rejected: number; reject_percent: number | null; machine_hours: number; untimed_lots: number };
type Data = { period: string; periods: string[]; start: string; end: string; prior_start: string; prior_end: string; current: Summary; prior: Summary; months: { month: string; sold_cents: number; collected_cents: number; expenses_cents: number; pieces: number; delivered: number }[]; machines: { code: string; name: string; lots: number; pieces: number; hours: number; use_percent: number | null; rejected: number; reject_percent: number | null }[]; clients: { client: string; sold_cents: number; count: number; share_percent: number }[] };
const pct = (v: number | null) => (v == null ? '—' : `${v.toLocaleString('es-MX', { maximumFractionDigits: 1 })}%`);

/** Change against the prior period; for costs and rejects a rise is bad, so the tone flips. */
function Delta({ now, before, money: isMoney = false, lowerIsBetter = false }: { now: number | null; before: number | null; money?: boolean; lowerIsBetter?: boolean }) {
  if (now == null || before == null) return <span className="muted">sin comparación</span>;
  const diff = now - before;
  if (!diff) return <span className="muted">igual que antes</span>;
  const good = lowerIsBetter ? diff < 0 : diff > 0;
  return <span className={good ? 'delta up' : 'delta down'}>{diff > 0 ? '▲' : '▼'} {isMoney ? money(Math.abs(diff)) : Math.abs(Math.round(diff * 10) / 10).toLocaleString('es-MX')} vs. anterior</span>;
}

export default function Rendimiento() {
  const [period, setPeriod] = useState('Este mes');
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState('');
  useEffect(() => { api<Data>(`/rendimiento?periodo=${encodeURIComponent(period)}`).then(setData).catch((e) => setError(e.message)); }, [period]);
  if (error) return <div className="error">{error}</div>;
  if (!data) return <div className="empty">Cargando rendimiento…</div>;
  const c = data.current, p = data.prior;
  const max = Math.max(1, ...data.months.map((m) => Math.max(m.sold_cents, m.expenses_cents)));
  return (
    <>
      <div className="head"><div><h1>Estado de rendimiento</h1><p>{data.start} a {data.end}, comparado con {data.prior_start} a {data.prior_end}.</p></div>
        <div className="pills">{data.periods.map((x) => <button key={x} className={`pill${period === x ? ' on' : ''}`} aria-pressed={period === x} onClick={() => setPeriod(x)}>{x}</button>)}</div></div>

      <h2 className="section-title">Negocio</h2>
      <div className="grid pulse">
        <div className="card tile"><div className="label">Vendido</div><div className="value">{money(c.sold_cents)}</div><Delta now={c.sold_cents} before={p.sold_cents} money /><div className="hint">{c.sales_count} ventas · ticket {money(c.ticket_cents)}</div></div>
        <div className="card tile"><div className="label">Cobrado</div><div className="value">{money(c.collected_cents)}</div><Delta now={c.collected_cents} before={p.collected_cents} money /></div>
        <div className="card tile orange"><div className="label">Gastos</div><div className="value">{money(c.expenses_cents)}</div><Delta now={c.expenses_cents} before={p.expenses_cents} money lowerIsBetter /><div className="hint">pagado {money(c.paid_out_cents)}</div></div>
        <div className={`card tile ${c.cash_cents < 0 ? 'red' : 'green'}`}><div className="label">Flujo de caja</div><div className="value">{money(c.cash_cents)}</div><Delta now={c.cash_cents} before={p.cash_cents} money /></div>
      </div>
      <h2 className="section-title">Taller</h2>
      <div className="grid pulse">
        <div className="card tile"><div className="label">Entregas a tiempo</div><div className="value">{pct(c.on_time_percent)}</div><div className="hint">{c.on_time} de {c.promised} con fecha · {c.delivered} entregados{c.lead_days != null ? ` · ${c.lead_days} días promedio` : ''}</div></div>
        <div className="card tile"><div className="label">Piezas producidas</div><div className="value">{c.pieces}</div><Delta now={c.pieces} before={p.pieces} /><div className="hint">{c.lots} lotes</div></div>
        <div className="card tile"><div className="label">Horas de máquina</div><div className="value">{c.machine_hours.toLocaleString('es-MX')}</div><Delta now={c.machine_hours} before={p.machine_hours} />{c.untimed_lots > 0 && <div className="issue">{c.untimed_lots} lotes sin tiempo</div>}</div>
        <div className={`card tile ${c.reject_percent && c.reject_percent > 5 ? 'orange' : ''}`}><div className="label">Rechazo</div><div className="value">{pct(c.reject_percent)}</div><Delta now={c.reject_percent} before={p.reject_percent} lowerIsBetter /><div className="hint">{c.rejected} piezas</div></div>
      </div>

      <div className="grid two">
        <section className="card">
          <h2 className="section-title">Últimos seis meses</h2>
          {data.months.map((m) => (
            <div key={m.month} className="trend">
              <div className="hint"><strong className="ink">{m.month}</strong> · vendido {money(m.sold_cents)} · gastos {money(m.expenses_cents)} · {m.pieces} piezas · {m.delivered} entregados</div>
              <div className="bars" aria-hidden="true"><span className="b in" style={{ width: `${(m.sold_cents / max) * 100}%` }} /><span className="b out" style={{ width: `${(m.expenses_cents / max) * 100}%` }} /></div>
            </div>
          ))}
          <div className="badges" style={{ marginTop: 8 }}><span className="badge green">Vendido</span><span className="badge orange">Gastos</span></div>
        </section>
        <div className="stack">
          <section className="card">
            <h2 className="section-title">Por máquina</h2>
            {data.machines.length ? data.machines.map((m) => (
              <div className="row" key={m.code}><span><strong>{m.code}</strong> <span className="who">· {m.lots} lotes · {m.pieces} piezas · {m.hours} h</span>{m.rejected > 0 && <div className="hint">{m.rejected} rechazadas · {pct(m.reject_percent)}</div>}</span>
                <span className="bar" aria-label={`Uso ${pct(m.use_percent)}`} title={`Uso ${pct(m.use_percent)}`}><span style={{ width: `${Math.min(100, m.use_percent || 0)}%` }} /></span></div>
            )) : <div className="empty">Sin producción en el periodo.</div>}
          </section>
          <section className="card">
            <h2 className="section-title">Clientes principales</h2>
            {data.clients.length ? data.clients.map((x) => (
              <div className="row" key={x.client}><span><strong>{x.client}</strong> <span className="who">· {x.count} ventas · {pct(x.share_percent)}</span></span><span className="amount">{money(x.sold_cents)}</span></div>
            )) : <div className="empty">Sin ventas en el periodo.</div>}
          </section>
        </div>
      </div>
    </>
  );
}
