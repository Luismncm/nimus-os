'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { api, money } from '@/lib/api';

type Data = {
  health: { cash_cents: number; burn_cents: number; runway_months: number | null; result_cents: number; coverage_percent: number | null; margin_percent: number | null; break_even_cents: number | null; break_even_multiple: number | null; partner_share_percent: number | null; collection_percent: number | null; receivable_cents: number; payable_cents: number; liquidity: number | null; overall: string; verdict: string; tones: Record<string, string> };
  trend: { month: string; collected: number; injected: number; paid: number }[];
  month: { month: string; registered_cents: number; paid_cents: number; pending_cents: number; overdue_cents: number; projected_cents: number; after_cents: number | null; unassigned_cents: number; accounts: { id: number; name: string; kind: string; balance_cents: number | null; pending_cents: number; after_cents: number | null; confirmed_at: string | null }[] };
};
const TONE: Record<string, string> = { Crítico: 'red', Atención: 'orange', Sano: 'green', Estable: 'green' };
const pct = (v: number | null) => (v == null ? '—' : `${v.toLocaleString('es-MX', { maximumFractionDigits: 1 })}%`);
const tone = (t?: string) => (t === 'Crítico' ? 'red' : t === 'Atención' ? 'orange' : '');

export default function Resumen() {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState('');
  useEffect(() => { api<Data>('/resumen').then(setData).catch((e) => setError(e.message)); }, []);
  if (error) return <div className="error">{error}</div>;
  if (!data) return <div className="empty">Cargando resumen…</div>;
  const h = data.health, m = data.month;
  const max = Math.max(1, ...data.trend.map((t) => Math.max(t.collected, t.injected, t.paid)));
  return (
    <>
      <div className="head"><div><h1>Resumen y previsión</h1><p>Promedio de los últimos meses cerrados y previsión de caja de {m.month}.</p></div></div>
      <section className={`card verdict ${TONE[h.overall] || ''}`} style={{ marginBottom: 18 }}>
        <span className={`badge ${TONE[h.overall] || ''}`}>{h.overall}</span>
        <p style={{ margin: '8px 0 0' }}>{h.verdict}</p>
      </section>
      <div className="grid pulse">
        <div className="card tile"><div className="label">Caja</div><div className="value">{money(h.cash_cents)}</div><span className="muted">en cuentas registradas</span></div>
        <div className={`card tile ${tone(h.tones.runway)}`}><div className="label">Alcanza para</div><div className="value">{h.runway_months == null ? '—' : `${h.runway_months} meses`}</div><span className="muted">gasto mensual {money(h.burn_cents)}</span></div>
        <div className={`card tile ${tone(h.tones.coverage)}`}><div className="label">Ventas cubren</div><div className="value">{pct(h.coverage_percent)}</div><span className="muted">del gasto mensual</span></div>
        <div className={`card tile ${tone(h.tones.partner)}`}><div className="label">Dinero del socio</div><div className="value">{pct(h.partner_share_percent)}</div><span className="muted">de lo que entra</span></div>
        <div className="card tile"><div className="label">Por cobrar</div><div className="value">{money(h.receivable_cents)}</div><span className="muted">cobranza {pct(h.collection_percent)}</span></div>
        <div className="card tile"><div className="label">Por pagar</div><div className="value">{money(h.payable_cents)}</div><span className="muted">liquidez {h.liquidity ?? '—'}×</span></div>
      </div>

      <div className="grid two">
        <section className="card">
          <h2 className="section-title">Entradas y salidas por mes</h2>
          {data.trend.map((t) => (
            <div key={t.month} className="trend">
              <div className="hint"><strong className="ink">{t.month}</strong> · cobrado {money(t.collected)} · socio {money(t.injected)} · pagado {money(t.paid)}</div>
              <div className="bars" aria-hidden="true">
                <span className="b in" style={{ width: `${(t.collected / max) * 100}%` }} />
                <span className="b partner" style={{ width: `${(t.injected / max) * 100}%` }} />
                <span className="b out" style={{ width: `${(t.paid / max) * 100}%` }} />
              </div>
            </div>
          ))}
          <div className="badges" style={{ marginTop: 8 }}><span className="badge green">Cobrado</span><span className="badge violet">Aportado por socio</span><span className="badge orange">Pagado</span></div>
        </section>
        <section className="card">
          <h2 className="section-title">Previsión de {m.month}</h2>
          <div className="facts" style={{ marginBottom: 12 }}>
            <div><span>Gastos registrados del mes</span>{money(m.registered_cents)} · pagado {money(m.paid_cents)}</div>
            <div><span>Por pagar</span>{money(m.pending_cents)}{m.overdue_cents ? ` · vencido ${money(m.overdue_cents)}` : ''}</div>
            <div><span>Caja después de pagar lo pendiente</span>{m.after_cents == null ? 'Confirma saldos en la app local' : money(m.after_cents)}</div>
          </div>
          {m.accounts.map((a) => (
            <div className="row" key={a.id}><span><strong>{a.name}</strong> <span className="who">· {a.kind}{a.confirmed_at ? '' : ' · saldo por movimientos'}</span>
              <div className="hint">Por pagar desde aquí {money(a.pending_cents)}</div></span>
              <span className="amount">{a.balance_cents == null ? '—' : money(a.balance_cents)}{a.after_cents != null && <div className="hint">después {money(a.after_cents)}</div>}</span></div>
          ))}
          {m.unassigned_cents > 0 && <p className="issue">{money(m.unassigned_cents)} por pagar sin cuenta asignada.</p>}
          <p className="hint" style={{ marginTop: 10 }}><Link href="/gastos">Ver gastos por pagar</Link> · <Link href="/tesoreria">Ver tesorería</Link></p>
        </section>
      </div>
    </>
  );
}
