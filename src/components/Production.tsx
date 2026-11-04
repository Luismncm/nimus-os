'use client';

/**
 * A print in the queue and what can be done with it, as views/common.job_actions does locally:
 * one primary action for its state, progress, failure and schedule, and the actions that stop it last.
 * Each write sends the revision the card was drawn with; if the print changed elsewhere the API refuses
 * and the card shows why.
 */
import { FormEvent, useEffect, useState } from 'react';
import Modal from '@/components/Modal';
import { api } from '@/lib/api';

export type Job = {
  id: number; code: string; part: string; item: string; process: string; quantity: number; completed: number; remaining: number;
  status: string; priority: string; material: string; notes: string; machine_id: number | null; machine: string;
  order_id: number; order: string; project: string; client: string; revision: string; plan_revision: number;
  destination: { kind: string; label: string };
  slot: { state: string; line: string; start: string | null; end: string | null; minutes: number | null };
  issues: string[]; change_filament: boolean; loaded: string; started: boolean; order_blocked: boolean; closed: boolean;
  rides_on: string | null; reprint: string | null; can_start: boolean;
};

export const newKey = () => (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`);

const KIND_TONE: Record<string, string> = { Pedido: 'green', Origen: 'orange', Stock: 'blue', Prototipo: 'violet' };
export const STATUS_TONE: Record<string, string> = { 'En producción': 'blue', Pausado: 'orange', 'En cola': '', Bloqueado: 'red', Terminado: 'green' };

type Done = (message: string) => void;
type Act = { label: string; action: string };

const ACTIONS: Record<string, { primary: Act | null; more: Act[] }> = {
  'En cola': { primary: { label: 'Iniciar', action: 'start' }, more: [{ label: 'Terminar', action: 'finish' }, { label: 'Bloquear', action: 'block' }] },
  'En producción': { primary: null, more: [{ label: 'Terminar', action: 'finish' }, { label: 'Pausar', action: 'pause' }, { label: 'Bloquear', action: 'block' }] },
  Pausado: { primary: { label: 'Reanudar', action: 'start' }, more: [{ label: 'Terminar', action: 'finish' }, { label: 'Bloquear', action: 'block' }] },
  Bloqueado: { primary: { label: 'Liberar a cola', action: 'unblock' }, more: [] },
  Terminado: { primary: null, more: [] },
};

export function JobCard({ job, causes, onDone, onError }: { job: Job; causes: string[]; onDone: Done; onError: (m: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<'progress' | 'failure' | 'schedule' | null>(null);
  const state = ACTIONS[job.status] || ACTIONS.Terminado;

  async function act(action: string, label: string) {
    setBusy(true);
    try {
      await api(`/cola/${job.id}/accion`, { method: 'POST', body: JSON.stringify({ action, expected_revision: job.revision }) });
      onDone(`${job.code} · ${label.toLowerCase()}: hecho.`);
    } catch (e) {
      onError(`${job.code}: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  const percent = job.quantity ? Math.round((job.completed / job.quantity) * 100) : 0;
  return (
    <article className={`job kind-${(job.destination.kind || 'Pedido').toLowerCase()}`}>
      <div className="job-main">
        <div className="badges">
          <strong>{job.part}</strong> <span className="muted">×{job.quantity} · {job.code}</span>
          <span className={`badge ${STATUS_TONE[job.status] || ''}`}>{job.status}</span>
          <span className={`badge ${KIND_TONE[job.destination.kind] || ''}`}>{job.destination.label}</span>
          {job.priority === 'Alta' && <span className="badge orange">Alta</span>}
          {job.change_filament && <span className="badge orange" title={`La impresora tiene ${job.loaded}; esta impresión usa ${job.material}.`}>Cambiar filamento</span>}
          {job.reprint && <span className="badge orange">Reimpresión · {job.reprint}</span>}
        </div>
        <div className="hint">{job.slot.line} · {job.completed}/{job.quantity} buenas · {job.material || 'Sin material'}{job.machine ? '' : ' · sin máquina'}</div>
        {job.issues.map((text) => <div className="issue" key={text}>{text}</div>)}
        {job.order_blocked && job.status !== 'Terminado' && <div className="issue">Pedido bloqueado: no se puede iniciar ni reanudar.</div>}
        <span className="bar" aria-label={`${percent}% terminado`}><span style={{ width: `${percent}%` }} /></span>
      </div>
      <div className="job-actions">
        {job.closed ? <span className="hint">Pedido entregado o cancelado · solo lectura</span>
          : job.rides_on && job.status !== 'Terminado' ? <span className="hint">Se termina con {job.rides_on}.</span>
          : job.status === 'Terminado' ? <span className="hint">Terminado</span> : (
            <>
              {job.status === 'En producción' && <button className="btn small primary" onClick={() => setOpen('progress')} disabled={busy}>Avance</button>}
              {state.primary && (
                <button className="btn small primary" disabled={busy || (state.primary.action === 'start' && !job.can_start)}
                        title={state.primary.action === 'start' && !job.can_start ? 'La máquina no está disponible o el pedido está bloqueado.' : undefined}
                        onClick={() => act(state.primary!.action, state.primary!.label)}>{state.primary.label}</button>
              )}
              {job.status !== 'En producción' && job.status !== 'Bloqueado' && <button className="btn small" onClick={() => setOpen('progress')} disabled={busy}>Avance</button>}
              {job.started && <button className="btn small" onClick={() => setOpen('failure')} disabled={busy}>Falla</button>}
              <button className="btn small ghost" onClick={() => setOpen('schedule')} disabled={busy}>Horario</button>
              {state.more.length > 0 && (
                <details className="more">
                  <summary className="btn small ghost" aria-label={`Más acciones de ${job.code}`}>Más</summary>
                  <div className="menu">
                    {state.more.map((a) => (
                      <button key={a.action} className={a.action === 'block' ? 'danger' : undefined} disabled={busy}
                              onClick={(e) => { (e.currentTarget.closest('details') as HTMLDetailsElement).open = false; act(a.action, a.label); }}>
                        {a.action === 'finish' ? `Terminar (+${job.remaining})` : a.label}
                      </button>
                    ))}
                  </div>
                </details>
              )}
            </>
          )}
      </div>
      {open === 'progress' && <ProgressDialog job={job} onClose={() => setOpen(null)} onDone={(m) => { setOpen(null); onDone(m); }} />}
      {open === 'failure' && <FailureDialog job={job} causes={causes} onClose={() => setOpen(null)} onDone={(m) => { setOpen(null); onDone(m); }} />}
      {open === 'schedule' && <ScheduleDialog jobId={job.id} onClose={() => setOpen(null)} onDone={(m) => { setOpen(null); onDone(m); }} />}
    </article>
  );
}

function useSave(onDone: Done) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function run(call: () => Promise<unknown>, message: string) {
    setBusy(true); setError('');
    try {
      await call();
      onDone(message);
    } catch (e) {
      setError((e as Error).message); setBusy(false);
    }
  }
  return { busy, error, run };
}

/** Total good pieces so far; reaching the quantity finishes the print. */
export function ProgressDialog({ job, onClose, onDone }: { job: Job; onClose: () => void; onDone: Done }) {
  const [value, setValue] = useState(String(job.completed));
  const { busy, error, run } = useSave(onDone);
  const total = Number(value);
  function save(e: FormEvent) {
    e.preventDefault();
    run(() => api(`/cola/${job.id}/avance`, { method: 'POST', body: JSON.stringify({ quantity_completed: total, expected_revision: job.revision }) }),
        total >= job.quantity ? `${job.code} terminado.` : `Avance guardado: ${total}/${job.quantity} buenas.`);
  }
  return (
    <Modal title="Registrar avance" onClose={onClose}>
      <form className="stack" onSubmit={save}>
        <p><strong>{job.code} · {job.part}</strong> <span className="muted">· {job.project}</span></p>
        <label>Piezas buenas en total<input type="number" inputMode="numeric" min={0} max={job.quantity} step={1} required value={value} onChange={(e) => setValue(e.target.value)} /></label>
        <p className="muted">De {job.quantity}. {total >= job.quantity ? 'Al llegar al total el trabajo queda terminado.' : `Faltarán ${Math.max(0, job.quantity - total)}.`}</p>
        {error && <div className="error">{error}</div>}
        <div className="actions">
          <button type="button" className="btn" onClick={onClose}>Cancelar</button>
          <button className="btn primary" disabled={busy}>{busy ? 'Guardando…' : 'Guardar avance'}</button>
        </div>
      </form>
    </Modal>
  );
}

/** Rejected pieces and their cause; the print pauses and frees its booked time, as in the local app. */
export function FailureDialog({ job, causes, onClose, onDone }: { job: Job; causes: string[]; onClose: () => void; onDone: Done }) {
  const [key] = useState(newKey);
  const [form, setForm] = useState({ rejected: '1', cause: causes[0] || '', notes: '', waste: '', previously_good: false });
  const { busy, error, run } = useSave(onDone);
  const available = form.previously_good ? job.completed : job.remaining;
  function save(e: FormEvent) {
    e.preventDefault();
    run(() => api(`/cola/${job.id}/falla`, { method: 'POST', body: JSON.stringify({
      rejected_units: Number(form.rejected), cause: form.cause, notes: form.notes, waste_grams: form.waste === '' ? null : Number(form.waste),
      previously_good: form.previously_good, request_key: key, expected_revision: job.revision }) }),
      `Falla registrada en ${job.code}. El trabajo quedó en pausa y sin horario.`);
  }
  return (
    <Modal title="Registrar falla" onClose={onClose}>
      <form className="stack" onSubmit={save}>
        <p><strong>{job.code} · {job.part}</strong> <span className="muted">· {job.completed}/{job.quantity} buenas</span></p>
        <label className="check">
          <input type="checkbox" checked={form.previously_good} onChange={(e) => setForm({ ...form, previously_good: e.target.checked })} />
          <span>Las rechazadas ya estaban contadas como buenas</span>
        </label>
        <div className="pair">
          <label>Piezas rechazadas<input type="number" inputMode="numeric" min={1} max={Math.max(1, available)} required value={form.rejected} onChange={(e) => setForm({ ...form, rejected: e.target.value })} /></label>
          <label><span>Merma · g <span className="muted optional">· opcional</span></span><input type="number" inputMode="decimal" min={0} step="0.1" value={form.waste} onChange={(e) => setForm({ ...form, waste: e.target.value })} /></label>
        </div>
        <label>Causa<select value={form.cause} onChange={(e) => setForm({ ...form, cause: e.target.value })}>{causes.map((c) => <option key={c}>{c}</option>)}</select></label>
        <label><span>Notas <span className="muted optional">· opcional</span></span><textarea rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></label>
        <p className="muted">Hasta {available} piezas en esta opción. Después puedes reimprimir las pendientes desde la app local.</p>
        {error && <div className="error">{error}</div>}
        <div className="actions">
          <button type="button" className="btn" onClick={onClose}>Cancelar</button>
          <button className="btn primary" disabled={busy || available < 1}>{busy ? 'Guardando…' : 'Registrar falla'}</button>
        </div>
      </form>
    </Modal>
  );
}

type Plan = { code: string; part: string; machine: string; planned_start: string | null; duration_minutes: number | null; estimated_grams: number | null; revision: number; job_revision: string; first_free: string | null };

/** Start, duration and grams; offers the machine's first free slot for that duration. */
export function ScheduleDialog({ jobId, onClose, onDone }: { jobId: number; onClose: () => void; onDone: Done }) {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [form, setForm] = useState({ start: '', hours: '', minutes: '', grams: '' });
  const [loadError, setLoadError] = useState('');
  const { busy, error, run } = useSave(onDone);
  useEffect(() => {
    api<Plan>(`/cola/${jobId}/horario`).then((p) => {
      setPlan(p);
      const d = p.duration_minutes || 0;
      setForm({ start: (p.planned_start || '').slice(0, 16), hours: d ? String(Math.floor(d / 60)) : '', minutes: d ? String(d % 60) : '', grams: p.estimated_grams == null ? '' : String(p.estimated_grams) });
    }).catch((e) => setLoadError(e.message));
  }, [jobId]);
  const duration = (Number(form.hours) || 0) * 60 + (Number(form.minutes) || 0);
  function save(e: FormEvent) {
    e.preventDefault();
    if (!plan) return;
    run(() => api(`/cola/${jobId}/horario`, { method: 'POST', body: JSON.stringify({
      planned_start: form.start || null, duration_minutes: duration || null, estimated_grams: form.grams === '' ? null : Number(form.grams),
      expected_revision: plan.revision, expected_job_revision: plan.job_revision }) }), `Horario de ${plan.code} guardado.`);
  }
  return (
    <Modal title="Horario de la impresión" onClose={onClose}>
      {!plan ? (loadError ? <div className="error">{loadError}</div> : <div className="empty">Cargando…</div>) : (
        <form className="stack" onSubmit={save}>
          <p><strong>{plan.code} · {plan.part}</strong> <span className="muted">· {plan.machine || 'sin máquina'}</span></p>
          <label>Inicio programado<input type="datetime-local" value={form.start} onChange={(e) => setForm({ ...form, start: e.target.value })} /></label>
          {plan.first_free && plan.first_free.slice(0, 16) !== form.start && (
            <button type="button" className="btn small" onClick={() => setForm({ ...form, start: plan.first_free!.slice(0, 16) })}>
              Usar el primer horario libre · {plan.first_free.replace('T', ' ')}
            </button>
          )}
          <div className="pair">
            <label>Horas<input type="number" inputMode="numeric" min={0} value={form.hours} onChange={(e) => setForm({ ...form, hours: e.target.value })} /></label>
            <label>Minutos<input type="number" inputMode="numeric" min={0} max={59} value={form.minutes} onChange={(e) => setForm({ ...form, minutes: e.target.value })} /></label>
          </div>
          <label><span>Gramos estimados <span className="muted optional">· opcional</span></span><input type="number" inputMode="decimal" min={0} step="0.1" value={form.grams} onChange={(e) => setForm({ ...form, grams: e.target.value })} /></label>
          <p className="muted">Con inicio y duración la impresión reserva la máquina; un cruce con otra reserva se rechaza.</p>
          {error && <div className="error">{error}</div>}
          <div className="actions">
            <button type="button" className="btn" onClick={onClose}>Cancelar</button>
            <button className="btn primary" disabled={busy}>{busy ? 'Guardando…' : 'Guardar horario'}</button>
          </div>
        </form>
      )}
    </Modal>
  );
}
