'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';

type Data = {
  minutes: number;
  capacity: { id: number; code: string; name: string; status: string; free_from: string | null; pending_units: number; unplanned: number; hours: number }[];
  failures: { id: number; job: string; part: string; order: string; order_id: number; cause: string; notes: string; rejected: number; waste_grams: number | null; created_at: string; reprint: string | null; remaining: number }[];
  notices: { identity: string; kind: string; detail: string; severity: 'red' | 'orange' | 'gray'; state: string; record_kind: string; record_id: number | string }[];
};
const TABS = ['Avisos', 'Capacidad', 'Fallas'] as const;
const at = (iso: string | null) => (iso ? iso.replace('T', ' ').slice(0, 16) : '—');

export default function Control() {
  const [tab, setTab] = useState<(typeof TABS)[number]>('Avisos');
  const [minutes, setMinutes] = useState(120);
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState('');
  const [seen, setSeen] = useState(false);
  const load = useCallback(() => api<Data>(`/control?minutos=${minutes}`).then(setData).catch((e) => setError(e.message)), [minutes]);
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load]);

  async function resolve(identity: string, snooze?: number) {
    try {
      await api(`/control/avisos/${identity}`, { method: 'POST', body: JSON.stringify({ snooze_minutes: snooze ?? null }) });
      load();
    } catch (e) { setError((e as Error).message); }
  }

  if (!data) return error ? <div className="error">{error}</div> : <div className="empty">Cargando control…</div>;
  const pending = data.notices.filter((n) => n.state === 'Pendiente');
  const notices = seen ? data.notices : pending;
  const link = (n: Data['notices'][number]) => (n.record_kind === 'Pedido' ? `/pedidos/${n.record_id}` : n.record_kind === 'Máquina' ? '/maquinas' : n.record_kind === 'Trabajo' ? '/cola' : null);
  return (
    <>
      <div className="head"><div><h1>Control de producción</h1><p>{pending.length} avisos pendientes · {data.failures.length} fallas registradas</p></div></div>
      {error && <div className="error" style={{ marginBottom: 12 }}>{error}</div>}
      <div className="pills" role="tablist" style={{ marginBottom: 16 }}>
        {TABS.map((t) => <button key={t} role="tab" aria-selected={tab === t} className={`pill${tab === t ? ' on' : ''}`} onClick={() => setTab(t)}>{t}{t === 'Avisos' && pending.length ? ` · ${pending.length}` : ''}</button>)}
      </div>

      {tab === 'Avisos' && (
        <section className="card">
          <div className="toolbar" style={{ marginBottom: 6 }}>
            <h2 className="section-title" style={{ margin: 0 }}>Avisos del taller</h2>
            <label className="check inline"><input type="checkbox" checked={seen} onChange={(e) => setSeen(e.target.checked)} /><span>Incluir vistos y pospuestos</span></label>
          </div>
          {notices.length ? notices.map((n) => {
            const href = link(n);
            return (
              <div className="row" key={n.identity}>
                <span>
                  <span className={`badge ${n.severity === 'gray' ? '' : n.severity}`}>{n.kind}</span>{n.state !== 'Pendiente' && <span className="badge"> {n.state}</span>}
                  <div style={{ marginTop: 4 }}>{href ? <Link href={href} style={{ color: 'inherit' }}>{n.detail}</Link> : n.detail}</div>
                </span>
                {n.state === 'Pendiente' && (
                  <span className="badges">
                    <button className="btn small" onClick={() => resolve(n.identity)}>Visto</button>
                    <button className="btn small ghost" onClick={() => resolve(n.identity, 60)}>Posponer 1 h</button>
                  </span>
                )}
              </div>
            );
          }) : <div className="empty">Sin avisos pendientes.</div>}
        </section>
      )}

      {tab === 'Capacidad' && (
        <>
          <div className="filters">
            <label className="inline-label">Bloque requerido · minutos
              <input type="number" inputMode="numeric" min={1} max={525600} step={30} value={minutes} onChange={(e) => setMinutes(Math.max(1, Number(e.target.value) || 1))} />
            </label>
            <span className="muted">Primer intervalo libre desde ahora con esa duración. Las máquinas imprimen en paralelo.</span>
          </div>
          <div className="grid cards3">
            {data.capacity.map((r) => (
              <section className="card machine" key={r.id}>
                <div className="toolbar"><div><strong className="big">{r.code}</strong><div className="hint">{r.name}</div></div><span className="badge">{r.status}</span></div>
                <div className="facts">
                  <div><span>Primer espacio libre</span>{r.free_from ? at(r.free_from) : 'Pendiente: revisa el estado o el trabajo en marcha'}</div>
                  <div><span>Pendiente</span>{r.pending_units} unidades · {r.hours} h capturadas</div>
                  <div><span>Sin intervalo completo</span>{r.unplanned} lotes</div>
                </div>
                <Link className="btn small" href={`/cola?maquina=${r.id}`}>Ver su cola</Link>
              </section>
            ))}
          </div>
        </>
      )}

      {tab === 'Fallas' && (
        <section className="card">
          <div className="grid pulse" style={{ marginBottom: 12 }}>
            <div className="tile card"><div className="label">Eventos</div><div className="value">{data.failures.length}</div></div>
            <div className="tile card"><div className="label">Rechazadas</div><div className="value">{data.failures.reduce((n, f) => n + f.rejected, 0)}</div></div>
            <div className="tile card"><div className="label">Merma capturada</div><div className="value">{data.failures.reduce((n, f) => n + (f.waste_grams || 0), 0).toLocaleString('es-MX')} g</div></div>
          </div>
          {data.failures.length ? data.failures.map((f) => (
            <div className="row" key={f.id}>
              <span><strong>{f.job} · {f.part} · {f.cause}</strong>
                <div className="hint">{f.order} · {at(f.created_at)} · {f.rejected} rechazadas · {f.waste_grams != null ? `${f.waste_grams} g` : 'merma pendiente'}{f.notes ? ` · ${f.notes}` : ''}</div></span>
              <span className="badges">
                {f.reprint ? <span className={`badge ${f.reprint === 'Finalizada' ? 'green' : 'orange'}`}>Reimpresión · {f.reprint}</span>
                  : f.remaining > 0 ? <span className="badge orange">{f.remaining} por reimprimir</span> : null}
                <Link className="btn small ghost" href={`/pedidos/${f.order_id}`}>Pedido</Link>
              </span>
            </div>
          )) : <div className="empty">Sin fallas registradas. La acción Falla está en cada impresión iniciada de la cola.</div>}
        </section>
      )}
    </>
  );
}
