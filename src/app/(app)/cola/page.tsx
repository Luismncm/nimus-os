'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Job, JobCard, ProgressDialog, ScheduleDialog } from '@/components/Production';
import { api } from '@/lib/api';
import { CloseIcon } from '@/components/Icon';

type MachineRow = {
  id: number; code: string; name: string; status: string; material: string; availability: string; pending_units: number;
  current: { id: number; code: string; part: string } | null; next: { id: number; code: string; part: string } | null;
};
type Review = { job_id: number; text: string; fix: 'reschedule' | 'plan' | 'machine' | 'progress'; label: string; rank: number };
type Queue = { now: string; jobs: Job[]; machines: MachineRow[]; review: Review[]; causes: string[] };

// The queue's state counts are also its quick filters, as in the local app.
const QUICK: Record<string, (j: Job) => boolean> = {
  Todas: () => true,
  'En marcha': (j) => j.status === 'En producción',
  'Con horario': (j) => j.slot.state === 'Reservada',
  'Sin horario': (j) => j.status !== 'Terminado' && (j.slot.state === 'Sin horario' || j.slot.state === 'Sin duración'),
  'Con problema': (j) => j.issues.length > 0,
  Bloqueadas: (j) => j.status === 'Bloqueado' || (j.order_blocked && j.status !== 'Terminado'),
};
const MACHINE_TONE: Record<string, string> = { Disponible: 'green', Imprimiendo: 'blue', Mantenimiento: 'orange', 'Fuera de servicio': 'red' };

export default function Cola() {
  const [data, setData] = useState<Queue | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState<{ text: string; tone: 'ok' | 'bad' } | null>(null);
  const [search, setSearch] = useState('');
  const [quick, setQuick] = useState('Todas');
  const [machine, setMachine] = useState('Todas');
  const [order, setOrder] = useState<number | null>(null);
  const [finished, setFinished] = useState(false);
  const [allReview, setAllReview] = useState(false);
  const [fix, setFix] = useState<{ kind: 'plan' | 'progress'; job: Job } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    // Arriving from a machine or an order narrows the queue to it.
    const params = new URLSearchParams(window.location.search);
    if (params.get('maquina')) setMachine(params.get('maquina')!);
    if (params.get('pedido')) setOrder(Number(params.get('pedido')));
  }, []);
  const load = useCallback(() => api<Queue>(`/cola${finished ? '?terminados=true' : ''}`).then(setData).catch((e) => setError(e.message)), [finished]);
  useEffect(() => { load(); }, [load]);
  const done = (text: string) => { setNotice({ text, tone: 'ok' }); setFix(null); load(); };
  const failed = (text: string) => { setNotice({ text, tone: 'bad' }); load(); };

  const filtered = useMemo(() => {
    if (!data) return [];
    const needle = search.trim().toLowerCase();
    return data.jobs.filter((j) => (machine === 'Todas' || (machine === 'none' ? j.machine_id === null : String(j.machine_id) === machine))
      && (order === null || j.order_id === order)
      && (!needle || [j.code, j.order, j.project, j.client, j.part, j.material, j.item].join(' ').toLowerCase().includes(needle)));
  }, [data, search, machine, order]);
  if (error) return <div className="error">{error}</div>;
  if (!data) return <div className="empty">Cargando la cola…</div>;

  const counts = Object.fromEntries(Object.entries(QUICK).map(([k, f]) => [k, filtered.filter(f).length]));
  const shown = filtered.filter(QUICK[quick] || QUICK.Todas);
  const unscheduled = filtered.filter((j) => j.slot.state === 'Sin horario' && j.status !== 'Terminado' && !j.closed && !j.rides_on).map((j) => j.id);
  const byId = Object.fromEntries(data.jobs.map((j) => [j.id, j]));
  const review = data.review.filter((r) => filtered.some((j) => j.id === r.job_id));
  const groups = [...data.machines.map((m) => ({ key: String(m.id), machine: m as MachineRow | null, jobs: shown.filter((j) => j.machine_id === m.id) })),
                  { key: 'none', machine: null, jobs: shown.filter((j) => j.machine_id === null || !data.machines.some((m) => m.id === j.machine_id)) }]
    .filter((g) => (machine === 'Todas' || machine === g.key) && (g.jobs.length || (g.machine && quick === 'Todas' && !search && order === null)));

  async function scheduleAll() {
    setBusy(true);
    try {
      const r = await api<{ scheduled: number; skipped: { reason: string }[] }>('/cola/programar', { method: 'POST', body: JSON.stringify({ job_ids: unscheduled }) });
      setNotice({ text: `${r.scheduled ? `${r.scheduled} impresiones programadas en el primer horario libre.` : 'Ninguna impresión se pudo programar.'}${r.skipped.length ? ` ${r.skipped.length} sin programar: ${r.skipped[0].reason}` : ''}`, tone: r.scheduled ? 'ok' : 'bad' });
      load();
    } catch (e) { failed((e as Error).message); } finally { setBusy(false); }
  }

  async function reschedule(jobId: number) {
    setBusy(true);
    try {
      const r = await api<{ start: string }>(`/cola/${jobId}/reprogramar`, { method: 'POST' });
      done(`Reprogramado en el primer horario libre: ${r.start.replace('T', ' ')}.`);
    } catch (e) { failed((e as Error).message); } finally { setBusy(false); }
  }

  const pending = filtered.reduce((n, j) => n + (j.status === 'Terminado' ? 0 : j.remaining), 0);
  return (
    <>
      <div className="head">
        <div>
          <h1>Cola de producción</h1>
          <p>{counts['En marcha']} en marcha · {pending} unidades pendientes · {data.machines.filter((m) => m.status === 'Disponible').length} de {data.machines.length} impresoras disponibles</p>
        </div>
      </div>

      {notice && <div className={notice.tone === 'ok' ? 'notice' : 'error notice-bad'} role="status">{notice.text}<button onClick={() => setNotice(null)} aria-label="Ocultar aviso"><CloseIcon /></button></div>}

      <div className="filters">
        <input type="search" placeholder="Pieza, cliente, material, pedido o trabajo" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Buscar en la cola" />
        <select value={machine} onChange={(e) => setMachine(e.target.value)} aria-label="Máquina">
          <option value="Todas">Todas las máquinas</option>
          {data.machines.map((m) => <option key={m.id} value={String(m.id)}>{m.code}</option>)}
          <option value="none">Sin máquina</option>
        </select>
        <label className="check inline"><input type="checkbox" checked={finished} onChange={(e) => setFinished(e.target.checked)} /><span>Ver terminadas</span></label>
      </div>
      <div className="toolbar" style={{ marginBottom: 14 }}>
        <div className="pills" role="group" aria-label="Estado rápido">
          {Object.keys(QUICK).filter((k) => k === 'Todas' || counts[k] || k === quick).map((k) => (
            <button key={k} className={`pill${quick === k ? ' on' : ''}`} aria-pressed={quick === k} onClick={() => setQuick(k)}>{k} · {counts[k]}</button>
          ))}
          {order !== null && <button className="pill on" onClick={() => setOrder(null)}>Pedido {data.jobs.find((j) => j.order_id === order)?.order || order} ×</button>}
        </div>
        {unscheduled.length > 0 && <button className="btn small" onClick={scheduleAll} disabled={busy}>Programar {unscheduled.length} sin horario</button>}
      </div>

      {review.length > 0 && (
        <section className="card review" style={{ marginBottom: 18 }}>
          <h2 className="section-title">Por resolver · {review.length}</h2>
          {(allReview ? review : review.slice(0, 3)).map((r) => {
            const job = byId[r.job_id];
            return (
              <div className="row" key={r.job_id}>
                <span><strong>{job.part}</strong> <span className="who">· {job.code} · {job.machine || 'sin máquina'}</span><div className="issue">{r.text}</div></span>
                {r.fix === 'reschedule' ? <button className="btn small" disabled={busy} onClick={() => reschedule(r.job_id)}>{r.label}</button>
                  : r.fix === 'plan' ? <button className="btn small" onClick={() => setFix({ kind: 'plan', job })}>{r.label}</button>
                  : r.fix === 'progress' ? <button className="btn small" onClick={() => setFix({ kind: 'progress', job })}>{r.label}</button>
                  : <span className="hint">Asigna máquina en Editar trabajo (app local)</span>}
              </div>
            );
          })}
          {review.length > 3 && <button className="btn small ghost" onClick={() => setAllReview((v) => !v)}>{allReview ? 'Ver menos' : `Ver los ${review.length}`}</button>}
        </section>
      )}

      {!shown.length && <div className="card empty">Sin trabajos para estos filtros.</div>}
      {groups.map((g) => (
        <section className="lane" key={g.key}>
          <header className="lane-head">
            {g.machine ? (
              <>
                <div><strong>{g.machine.code}</strong> <span className="muted">· {g.machine.name}</span>
                  <div className="hint">{g.machine.availability}{g.machine.material ? ` · filamento ${g.machine.material}` : ''}</div></div>
                <span className={`badge ${MACHINE_TONE[g.machine.status] || ''}`}>{g.machine.status}</span>
              </>
            ) : <div><strong>Sin máquina</strong><div className="hint">Procesos externos y piezas aún sin impresora</div></div>}
          </header>
          {g.jobs.length ? g.jobs.map((j) => <JobCard key={`${j.id}-${j.revision}`} job={j} causes={data.causes} onDone={done} onError={failed} />)
            : <div className="hint" style={{ padding: '6px 2px 12px' }}>Sin trabajos en cola.</div>}
        </section>
      ))}
      <p className="muted" style={{ marginTop: 18 }}>
        Las piezas por asignar se reparten desde cada <Link href="/pedidos">pedido</Link>. El calendario y la edición completa de trabajos siguen en la app local por ahora.
      </p>

      {fix?.kind === 'plan' && <ScheduleDialog jobId={fix.job.id} onClose={() => setFix(null)} onDone={done} />}
      {fix?.kind === 'progress' && <ProgressDialog job={fix.job} onClose={() => setFix(null)} onDone={done} />}
    </>
  );
}
