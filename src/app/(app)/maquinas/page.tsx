'use client';

import Link from 'next/link';
import { FormEvent, useCallback, useEffect, useState } from 'react';
import Modal from '@/components/Modal';
import { api } from '@/lib/api';
import { CloseIcon } from '@/components/Icon';

type Machine = {
  id: number; code: string; name: string; status: string; notes: string; material: string; pending_units: number;
  availability: string; booked_minutes: number; unscheduled: number; problems: number; free_from: string | null;
  current: { id: number; code: string; part: string } | null; next: { id: number; code: string; part: string } | null;
};
type Data = { machines: Machine[]; archived: { id: number; code: string; name: string }[]; statuses: string[] };
const TONE: Record<string, string> = { Disponible: 'green', Imprimiendo: 'blue', Mantenimiento: 'orange', 'Fuera de servicio': 'red' };
const hours = (m: number) => (m >= 60 ? `${Math.floor(m / 60)} h${m % 60 ? ` ${m % 60} min` : ''}` : `${m} min`);

export default function Maquinas() {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState<{ text: string; tone: 'ok' | 'bad' } | null>(null);
  const [edit, setEdit] = useState<Machine | 'new' | null>(null);
  const [filament, setFilament] = useState<Machine | null>(null);
  const load = useCallback(() => api<Data>('/maquinas').then(setData).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);
  const done = (text: string) => { setNotice({ text, tone: 'ok' }); setEdit(null); setFilament(null); load(); };

  async function archive(id: number, archived: boolean) {
    try {
      await api(`/maquinas/${id}/archivo`, { method: 'POST', body: JSON.stringify({ archived }) });
      done(archived ? 'Máquina archivada; su historial se conserva.' : 'Máquina reactivada.');
    } catch (e) { setNotice({ text: (e as Error).message, tone: 'bad' }); }
  }

  if (error) return <div className="error">{error}</div>;
  if (!data) return <div className="empty">Cargando máquinas…</div>;
  const count = (s: string) => data.machines.filter((m) => m.status === s).length;
  const attention = data.machines.length - count('Disponible') - count('Imprimiendo');
  return (
    <>
      <div className="head">
        <div>
          <h1>Máquinas</h1>
          <div className="badges" style={{ marginTop: 6 }}>
            <span className="badge green">{count('Disponible')} disponibles</span>
            <span className="badge blue">{count('Imprimiendo')} en producción</span>
            <span className={`badge ${attention ? 'orange' : ''}`}>{attention} requieren atención</span>
          </div>
        </div>
        <button className="btn primary" onClick={() => setEdit('new')}>Agregar máquina</button>
      </div>
      {notice && <div className={notice.tone === 'ok' ? 'notice' : 'error notice-bad'} role="status">{notice.text}<button onClick={() => setNotice(null)} aria-label="Ocultar aviso"><CloseIcon /></button></div>}

      <div className="grid cards3">
        {data.machines.map((m) => (
          <section className="card machine" key={m.id}>
            <div className="toolbar">
              <div><strong className="big">{m.code}</strong><div className="hint">{m.name}</div></div>
              <span className={`badge ${TONE[m.status] || ''}`}>{m.status}</span>
            </div>
            <div className="facts">
              <div><span>Ahora</span>{m.current ? `${m.current.code} · ${m.current.part}` : 'Sin impresión en marcha'}</div>
              <div><span>Siguiente</span>{m.next ? `${m.next.code} · ${m.next.part}` : '—'}</div>
              <div><span>Disponibilidad</span>{m.availability || m.status}</div>
              <div><span>Filamento</span>{m.material || 'Sin registrar'}</div>
              <div><span>Carga</span>{m.pending_units} unidades · {hours(m.booked_minutes)} reservadas{m.unscheduled ? ` · ${m.unscheduled} sin horario` : ''}</div>
            </div>
            {m.problems > 0 && <div className="issue">{m.problems} impresión(es) con problema de horario.</div>}
            {m.notes && <p className="hint">{m.notes}</p>}
            <div className="badges">
              <Link className="btn small primary" href={`/cola?maquina=${m.id}`}>Ver su cola</Link>
              <button className="btn small" onClick={() => setFilament(m)}>Filamento</button>
              <button className="btn small" onClick={() => setEdit(m)}>Editar</button>
              <button className="btn small ghost" onClick={() => archive(m.id, true)}>Archivar</button>
            </div>
          </section>
        ))}
      </div>
      {!data.machines.length && <div className="card empty">Agrega una máquina para comenzar o reactiva una archivada.</div>}

      {data.archived.length > 0 && (
        <section className="card" style={{ marginTop: 18 }}>
          <h2 className="section-title">Archivadas · {data.archived.length}</h2>
          {data.archived.map((m) => (
            <div className="row" key={m.id}><span><strong>{m.code}</strong> <span className="who">· {m.name}</span></span>
              <button className="btn small" onClick={() => archive(m.id, false)}>Reactivar</button></div>
          ))}
        </section>
      )}
      <p className="muted" style={{ marginTop: 18 }}>Cada máquina admite un trabajo en producción. Inicia, pausa y termina sus impresiones en la cola; pausar o terminar libera la máquina.</p>

      {edit && <MachineDialog machine={edit === 'new' ? null : edit} statuses={data.statuses} onClose={() => setEdit(null)} onDone={done} />}
      {filament && <FilamentDialog machine={filament} onClose={() => setFilament(null)} onDone={done} />}
    </>
  );
}

function MachineDialog({ machine, statuses, onClose, onDone }: { machine: Machine | null; statuses: string[]; onClose: () => void; onDone: (m: string) => void }) {
  const [form, setForm] = useState({ code: machine?.code || '', name: machine?.name || '', status: machine?.status || 'Disponible', notes: machine?.notes || '' });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function save(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try {
      await api(machine ? `/maquinas/${machine.id}` : '/maquinas', { method: machine ? 'PUT' : 'POST', body: JSON.stringify(form) });
      onDone(machine ? 'Máquina guardada.' : 'Máquina agregada.');
    } catch (err) { setError((err as Error).message); setBusy(false); }
  }
  // Imprimiendo is set by starting a print, never by hand.
  const options = statuses.filter((s) => s !== 'Imprimiendo' || machine?.status === 'Imprimiendo');
  return (
    <Modal title={machine ? `Editar ${machine.code}` : 'Agregar máquina'} onClose={onClose}>
      <form className="stack" onSubmit={save}>
        <div className="pair">
          <label>Código<input required value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="A1-04" /></label>
          <label>Estado<select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>{options.map((s) => <option key={s}>{s}</option>)}</select></label>
        </div>
        <label>Nombre<input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Bambu Lab A1" /></label>
        <label><span>Notas <span className="muted optional">· opcional</span></span><textarea rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></label>
        {error && <div className="error">{error}</div>}
        <div className="actions">
          <button type="button" className="btn" onClick={onClose}>Cancelar</button>
          <button className="btn primary" disabled={busy}>{busy ? 'Guardando…' : 'Guardar máquina'}</button>
        </div>
      </form>
    </Modal>
  );
}

function FilamentDialog({ machine, onClose, onDone }: { machine: Machine; onClose: () => void; onDone: (m: string) => void }) {
  const [material, setMaterial] = useState(machine.material);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function save(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try {
      await api(`/maquinas/${machine.id}/filamento`, { method: 'POST', body: JSON.stringify({ material }) });
      onDone(material ? `${machine.code} tiene ${material}.` : `${machine.code} sin filamento registrado.`);
    } catch (err) { setError((err as Error).message); setBusy(false); }
  }
  return (
    <Modal title={`Filamento en ${machine.code}`} onClose={onClose}>
      <form className="stack" onSubmit={save}>
        <label>Filamento cargado<input value={material} onChange={(e) => setMaterial(e.target.value)} placeholder="PLA MATTE NEGRO" /></label>
        <p className="muted">El reparto automático prefiere la máquina que ya tiene el material, y la cola avisa cuando una impresión pide cambiarlo.</p>
        {error && <div className="error">{error}</div>}
        <div className="actions">
          <button type="button" className="btn" onClick={onClose}>Cancelar</button>
          <button className="btn primary" disabled={busy}>{busy ? 'Guardando…' : 'Guardar'}</button>
        </div>
      </form>
    </Modal>
  );
}
