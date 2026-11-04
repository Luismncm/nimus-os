'use client';

import Link from 'next/link';
import { FormEvent, useCallback, useEffect, useState } from 'react';
import Modal from '@/components/Modal';
import { newKey, STATUS_TONE } from '@/components/Production';
import { useUser } from '@/components/Shell';
import { api, money } from '@/lib/api';

type Project = {
  id: number; code: string; name: string; goal: string; status: string; running: number; waiting: number; finished: number;
  grams_estimated: number; grams_used: number;
  money: { estimated_cents: number; real_cents: number; consumables_cents: number; budget_cents: number | null; budget_left: number | null } | null;
  jobs: { id: number; code: string; part: string; material: string; machine: string; status: string; schedule: string }[];
};
type Data = { projects: Project[]; priorities: string[]; processes: string[] };
type MachineOption = { id: number; code: string; status: string; material: string };

export default function Desarrollo() {
  const user = useUser();
  const [data, setData] = useState<Data | null>(null);
  const [machines, setMachines] = useState<MachineOption[]>([]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState<{ text: string; tone: 'ok' | 'bad' } | null>(null);
  const [closed, setClosed] = useState(false);
  const [open, setOpen] = useState<{ kind: 'new' } | { kind: 'edit' | 'print'; project: Project } | null>(null);
  const load = useCallback(() => api<Data>('/desarrollo').then(setData).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); api<{ machines: MachineOption[] }>('/maquinas').then((d) => setMachines(d.machines)).catch(() => {}); }, [load]);
  const done = (text: string) => { setNotice({ text, tone: 'ok' }); setOpen(null); load(); };

  async function toggle(p: Project) {
    try {
      await api(`/desarrollo/${p.id}/${p.status === 'Activo' ? 'cerrar' : 'reabrir'}`, { method: 'POST' });
      done(p.status === 'Activo' ? 'Proyecto cerrado; su historial se conserva.' : 'Proyecto reabierto.');
    } catch (e) { setNotice({ text: (e as Error).message, tone: 'bad' }); }
  }

  if (error) return <div className="error">{error}</div>;
  if (!data) return <div className="empty">Cargando proyectos…</div>;
  const active = data.projects.filter((p) => p.status === 'Activo');
  const shown = closed ? data.projects : active;
  const finances = user?.role === 'admin';
  return (
    <>
      <div className="head">
        <div><h1>Desarrollo y prototipos</h1>
          <p>{active.length} proyectos activos · {active.reduce((n, p) => n + p.running, 0)} impresiones en marcha · {active.reduce((n, p) => n + p.waiting, 0)} en cola · {Math.round(active.reduce((n, p) => n + p.grams_estimated, 0)).toLocaleString('es-MX')} g previstos
            {finances && ` · costo real ${money(active.reduce((n, p) => n + (p.money?.real_cents || 0), 0))}`}</p></div>
        <button className="btn primary" onClick={() => setOpen({ kind: 'new' })}>Nuevo proyecto</button>
      </div>
      {notice && <div className={notice.tone === 'ok' ? 'notice' : 'error notice-bad'} role="status">{notice.text}<button onClick={() => setNotice(null)} aria-label="Ocultar aviso">×</button></div>}
      <label className="check inline" style={{ marginBottom: 14 }}><input type="checkbox" checked={closed} onChange={(e) => setClosed(e.target.checked)} /><span>Mostrar proyectos cerrados</span></label>

      {!shown.length && <div className="card empty">Aún no hay proyectos activos. Crea uno para lanzar impresiones de prueba sin mezclarlas con pedidos ni ventas.</div>}
      <div className="stack">
        {shown.map((p) => {
          const m = p.money;
          const used = m && m.budget_cents ? Math.min(100, Math.round((m.real_cents / m.budget_cents) * 100)) : 0;
          return (
            <section className="card project" key={p.id}>
              <div className="toolbar">
                <div><strong className="big">{p.name}</strong> <span className="muted">· {p.code}</span>{p.goal && <div className="hint">{p.goal}</div>}</div>
                <span className={`badge ${p.status === 'Activo' ? 'violet' : ''}`}>{p.status}</span>
              </div>
              <div className="badges" style={{ margin: '10px 0' }}>
                {p.running > 0 && <span className="badge blue">{p.running} en marcha</span>}
                {p.waiting > 0 && <span className="badge">{p.waiting} en cola</span>}
                <span className={`badge ${p.finished ? 'green' : ''}`}>{p.finished} terminadas</span>
                <span className="badge">Filamento {Math.round(p.grams_estimated)} g previstos · {Math.round(p.grams_used)} g reales</span>
              </div>
              {m && (
                <div className="hint" style={{ marginBottom: 10 }}>
                  {m.estimated_cents ? `Costo estimado ${money(m.estimated_cents)}` : 'Costo estimado: faltan gramos, duración o tarifas'} · costo real {money(m.real_cents)}
                  {m.consumables_cents ? ` (incluye ${money(m.consumables_cents)} de consumibles)` : ''} · sin IVA, no es venta
                  {m.budget_cents != null && (
                    <div style={{ marginTop: 6 }}>
                      <span className="bar wide" aria-label={`${used}% del presupuesto`}><span style={{ width: `${used}%`, background: (m.budget_left ?? 0) < 0 ? 'var(--red)' : undefined }} /></span>
                      {money(m.real_cents)} de {money(m.budget_cents)} · {(m.budget_left ?? 0) < 0 ? 'presupuesto excedido' : `quedan ${money(m.budget_left)}`}
                    </div>
                  )}
                </div>
              )}
              <div className="badges">
                {p.status === 'Activo' && <button className="btn small primary" onClick={() => setOpen({ kind: 'print', project: p })}>Lanzar impresión</button>}
                {(p.running > 0 || p.waiting > 0) && <Link className="btn small" href={`/cola?pedido=${p.id}`}>Ver en la cola</Link>}
                {p.status === 'Activo' && <button className="btn small" onClick={() => setOpen({ kind: 'edit', project: p })}>Editar</button>}
                <button className="btn small ghost" onClick={() => toggle(p)}>{p.status === 'Activo' ? 'Cerrar proyecto' : 'Reabrir'}</button>
              </div>
              {p.jobs.length > 0 && (
                <details className="jobs" open={p.running + p.waiting > 0}>
                  <summary>Impresiones · {p.jobs.length}</summary>
                  {p.jobs.map((j) => (
                    <div className="row" key={j.id}>
                      <span><strong>{j.part}</strong> <span className="who">· {j.code} · {j.material || 'sin material'} · {j.machine || 'sin máquina'}</span><div className="hint">{j.schedule}</div></span>
                      <span className={`badge ${STATUS_TONE[j.status] || ''}`}>{j.status}</span>
                    </div>
                  ))}
                </details>
              )}
            </section>
          );
        })}
      </div>

      {open?.kind === 'new' && <ProjectDialog priorities={data.priorities} finances={finances} onClose={() => setOpen(null)} onDone={done} />}
      {open?.kind === 'edit' && <ProjectDialog project={open.project} priorities={data.priorities} finances={finances} onClose={() => setOpen(null)} onDone={done} />}
      {open?.kind === 'print' && <PrintDialog project={open.project} processes={data.processes} machines={machines} onClose={() => setOpen(null)} onDone={done} />}
    </>
  );
}

function ProjectDialog({ project, priorities, finances, onClose, onDone }: { project?: Project; priorities: string[]; finances: boolean; onClose: () => void; onDone: (m: string) => void }) {
  const budget = project?.money?.budget_cents;
  const [form, setForm] = useState({ name: project?.name || '', goal: project?.goal || '', budget: budget != null ? String(budget / 100) : '', priority: 'Media', deadline: '' });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function save(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    const body = { ...form, budget: form.budget === '' ? null : Number(form.budget), deadline: form.deadline || null };
    try {
      await api(project ? `/desarrollo/${project.id}` : '/desarrollo', { method: project ? 'PUT' : 'POST', body: JSON.stringify(body) });
      onDone(project ? 'Proyecto guardado.' : 'Proyecto creado. Ya puedes lanzar sus impresiones.');
    } catch (err) { setError((err as Error).message); setBusy(false); }
  }
  return (
    <Modal title={project ? `Editar ${project.name}` : 'Nuevo proyecto'} onClose={onClose}>
      <form className="stack" onSubmit={save}>
        {!project && <label>Proyecto<input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Lámpara colgante v2" /></label>}
        <label><span>Objetivo <span className="muted optional">· opcional</span></span><textarea rows={2} value={form.goal} onChange={(e) => setForm({ ...form, goal: e.target.value })} /></label>
        {/* The workshop role never sees money: it neither reads nor overwrites the budget. */}
        {finances && <label><span>Presupuesto · MXN <span className="muted optional">· opcional</span></span><input type="number" inputMode="decimal" min={0} step="0.01" value={form.budget} onChange={(e) => setForm({ ...form, budget: e.target.value })} /></label>}
        {!project && (
          <div className="pair">
            <label>Prioridad<select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>{priorities.map((p) => <option key={p}>{p}</option>)}</select></label>
            <label><span>Fecha objetivo <span className="muted optional">· opcional</span></span><input type="date" value={form.deadline} onChange={(e) => setForm({ ...form, deadline: e.target.value })} /></label>
          </div>
        )}
        {error && <div className="error">{error}</div>}
        <div className="actions">
          <button type="button" className="btn" onClick={onClose}>Cancelar</button>
          <button className="btn primary" disabled={busy}>{busy ? 'Guardando…' : project ? 'Guardar' : 'Crear proyecto'}</button>
        </div>
      </form>
    </Modal>
  );
}

function PrintDialog({ project, processes, machines, onClose, onDone }: { project: Project; processes: string[]; machines: MachineOption[]; onClose: () => void; onDone: (m: string) => void }) {
  const [key] = useState(newKey);
  const [form, setForm] = useState({ piece: '', quantity: '1', material: '', process: processes[0] || 'Impresión 3D', machine: '', start: '', hours: '', minutes: '', grams: '', notes: '' });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const set = (field: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [field]: e.target.value });
  const duration = (Number(form.hours) || 0) * 60 + (Number(form.minutes) || 0);
  async function save(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try {
      await api(`/desarrollo/${project.id}/impresion`, { method: 'POST', body: JSON.stringify({
        piece: form.piece, quantity: Number(form.quantity), material: form.material, process: form.process,
        machine_id: form.machine ? Number(form.machine) : null, planned_start: form.start || null, duration_minutes: duration || null,
        estimated_grams: form.grams === '' ? null : Number(form.grams), notes: form.notes, request_key: key }) });
      onDone(`Impresión de ${form.piece} lanzada en ${project.name}.`);
    } catch (err) { setError((err as Error).message); setBusy(false); }
  }
  const picked = machines.find((m) => String(m.id) === form.machine);
  return (
    <Modal title={`Lanzar impresión · ${project.name}`} onClose={onClose}>
      <form className="stack" onSubmit={save}>
        <div className="pair">
          <label>Pieza<input required value={form.piece} onChange={set('piece')} placeholder="Difusor" /></label>
          <label>Cantidad<input type="number" inputMode="numeric" min={1} required value={form.quantity} onChange={set('quantity')} /></label>
        </div>
        <div className="pair">
          <label>Material<input value={form.material} onChange={set('material')} placeholder="PLA" /></label>
          <label>Proceso<select value={form.process} onChange={set('process')}>{processes.map((p) => <option key={p}>{p}</option>)}</select></label>
        </div>
        <label>Máquina<select value={form.machine} onChange={set('machine')}>
          <option value="">Sin máquina</option>
          {machines.map((m) => <option key={m.id} value={m.id}>{m.code} · {m.status}{m.material ? ` · ${m.material}` : ''}</option>)}
        </select></label>
        {picked && form.material && picked.material && picked.material.toLowerCase() !== form.material.toLowerCase() && <div className="issue">{picked.code} tiene {picked.material}: habrá que cambiar el filamento.</div>}
        <label><span>Inicio programado <span className="muted optional">· opcional</span></span><input type="datetime-local" value={form.start} onChange={set('start')} /></label>
        <div className="pair">
          <label>Horas<input type="number" inputMode="numeric" min={0} value={form.hours} onChange={set('hours')} /></label>
          <label>Minutos<input type="number" inputMode="numeric" min={0} max={59} value={form.minutes} onChange={set('minutes')} /></label>
        </div>
        <label><span>Gramos estimados <span className="muted optional">· opcional</span></span><input type="number" inputMode="decimal" min={0} step="0.1" value={form.grams} onChange={set('grams')} /></label>
        <label><span>Notas <span className="muted optional">· opcional</span></span><textarea rows={2} value={form.notes} onChange={set('notes')} /></label>
        {error && <div className="error">{error}</div>}
        <div className="actions">
          <button type="button" className="btn" onClick={onClose}>Cancelar</button>
          <button className="btn primary" disabled={busy}>{busy ? 'Guardando…' : 'Lanzar impresión'}</button>
        </div>
      </form>
    </Modal>
  );
}
