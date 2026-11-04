'use client';

import { FormEvent, useCallback, useEffect, useState } from 'react';
import Modal from '@/components/Modal';
import { RecipeOrderDialog } from '@/components/RecipeOrder';
import { api } from '@/lib/api';
import { CloseIcon } from '@/components/Icon';

type Line = { component_id: number; name: string; variant: string; material: string; process: string; quantity: number };
type Product = { id: number; code: string; name: string; variant: string; collection: string; recipe_id: number | null; version: number | null; versions: number; retired: boolean; lines: Line[] };
type Component = { id: number; code: string; name: string; variant: string; material: string; process: string; collection: string; used_in: string[] };
type Data = { products: Product[]; components: Component[]; processes: string[]; priorities: string[] };

export default function Catalogo() {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [tab, setTab] = useState<'Productos y recetas' | 'Piezas reutilizables'>('Productos y recetas');
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState<{ kind: 'component' | 'product' } | { kind: 'order'; product: Product } | null>(null);
  const load = useCallback(() => api<Data>('/catalogo').then(setData).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);
  const done = (text: string) => { setNotice(text); setOpen(null); load(); };
  if (error) return <div className="error">{error}</div>;
  if (!data) return <div className="empty">Cargando catálogo…</div>;
  const term = search.trim().toLowerCase();
  const products = data.products.filter((p) => !term || [p.code, p.name, p.variant, p.collection].join(' ').toLowerCase().includes(term));
  const components = data.components.filter((c) => !term || [c.code, c.name, c.variant, c.material, c.collection].join(' ').toLowerCase().includes(term));

  return (
    <>
      <div className="head">
        <div><h1>Catálogo y recetas</h1><p>{data.products.length} productos · {data.components.length} piezas reutilizables</p></div>
        <span className="badges">
          <button className="btn" onClick={() => setOpen({ kind: 'component' })}>Nueva pieza</button>
          <button className="btn primary" onClick={() => setOpen({ kind: 'product' })}>Nuevo producto</button>
        </span>
      </div>
      {notice && <div className="notice" role="status">{notice}<button onClick={() => setNotice('')} aria-label="Ocultar aviso"><CloseIcon /></button></div>}
      <div className="filters">
        <div className="pills" role="tablist">
          {(['Productos y recetas', 'Piezas reutilizables'] as const).map((t) => <button key={t} role="tab" aria-selected={tab === t} className={`pill${tab === t ? ' on' : ''}`} onClick={() => setTab(t)}>{t}</button>)}
        </div>
        <input type="search" placeholder="Nombre, variante, material o código" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Buscar en el catálogo" />
      </div>

      {tab === 'Productos y recetas' ? (
        <div className="grid cards3">
          {products.map((p) => (
            <section className="card machine" key={p.id}>
              <div className="toolbar">
                <div><strong className="big">{p.name}</strong><div className="hint">{p.variant || 'Variante general'} · {p.collection} · {p.code}</div></div>
                {p.recipe_id ? <span className="badge accent">Receta v{p.version}</span> : <span className="badge orange">Sin receta</span>}
              </div>
              {p.retired && <div className="issue">Usa una pieza retirada: publica una receta nueva en la app local antes de crear pedidos.</div>}
              {p.lines.length ? (
                <div>{p.lines.map((l) => (
                  <div className="row" key={l.component_id}><span>{l.name}{l.variant ? ` · ${l.variant}` : ''} <span className="who">· {l.material || l.process}</span></span><span className="amount">×{l.quantity}</span></div>
                ))}</div>
              ) : <p className="hint">Define su receta en la app local (Editar receta).</p>}
              {p.recipe_id && !p.retired && <button className="btn small primary" onClick={() => setOpen({ kind: 'order', product: p })}>Crear pedido</button>}
            </section>
          ))}
          {!products.length && <div className="card empty">Sin productos.</div>}
        </div>
      ) : (
        <section className="card">
          {components.map((c) => (
            <div className="row" key={c.id}>
              <span><strong>{c.name}</strong>{c.variant ? ` · ${c.variant}` : ''} <span className="who">· {c.code} · {c.material || 'sin material'} · {c.process} · {c.collection}</span>
                <div className="hint">{c.used_in.length ? `En ${c.used_in.join(', ')}` : 'Aún no está en ninguna receta'}</div></span>
              <span className="badge">{c.used_in.length} productos</span>
            </div>
          ))}
          {!components.length && <div className="empty">Sin piezas.</div>}
        </section>
      )}
      <p className="muted" style={{ marginTop: 16 }}>Editar recetas, duplicar variantes y fotos siguen en la app local por ahora.</p>

      {open?.kind === 'component' && <ComponentDialog processes={data.processes} onClose={() => setOpen(null)} onDone={done} />}
      {open?.kind === 'product' && <ProductDialog onClose={() => setOpen(null)} onDone={done} />}
      {open?.kind === 'order' && <RecipeOrderDialog product={open.product} priorities={data.priorities} onClose={() => setOpen(null)} />}
    </>
  );
}

function Save({ busy, label, onClose }: { busy: boolean; label: string; onClose: () => void }) {
  return <div className="actions"><button type="button" className="btn" onClick={onClose}>Cancelar</button><button className="btn primary" disabled={busy}>{busy ? 'Guardando…' : label}</button></div>;
}

function ComponentDialog({ processes, onClose, onDone }: { processes: string[]; onClose: () => void; onDone: (m: string) => void }) {
  const [form, setForm] = useState({ name: '', variant: '', material: '', process: processes[0] || 'Impresión 3D', collection: 'General' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function save(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try { await api('/catalogo/componentes', { method: 'POST', body: JSON.stringify(form) }); onDone(`Pieza ${form.name} lista para usarse en recetas.`); }
    catch (err) { setError((err as Error).message); setBusy(false); }
  }
  return (
    <Modal title="Nueva pieza reutilizable" onClose={onClose}>
      <form className="stack" onSubmit={save}>
        <div className="pair">
          <label>Nombre<input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="PANTALLA" /></label>
          <label><span>Variante <span className="muted optional">· opcional</span></span><input value={form.variant} onChange={(e) => setForm({ ...form, variant: e.target.value })} placeholder="CIRRUS" /></label>
        </div>
        <div className="pair">
          <label>Material<input value={form.material} onChange={(e) => setForm({ ...form, material: e.target.value })} placeholder="PLA" /></label>
          <label>Proceso<select value={form.process} onChange={(e) => setForm({ ...form, process: e.target.value })}>{processes.map((p) => <option key={p}>{p}</option>)}</select></label>
        </div>
        <label>Línea<select value={form.collection} onChange={(e) => setForm({ ...form, collection: e.target.value })}>{['General', 'Origen'].map((c) => <option key={c}>{c}</option>)}</select></label>
        {error && <div className="error">{error}</div>}
        <Save busy={busy} label="Crear pieza" onClose={onClose} />
      </form>
    </Modal>
  );
}

function ProductDialog({ onClose, onDone }: { onClose: () => void; onDone: (m: string) => void }) {
  const [form, setForm] = useState({ name: '', variant: '', collection: 'General' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function save(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try { await api('/catalogo/productos', { method: 'POST', body: JSON.stringify(form) }); onDone(`Producto ${form.name} creado. Define su receta en la app local.`); }
    catch (err) { setError((err as Error).message); setBusy(false); }
  }
  return (
    <Modal title="Nuevo producto" onClose={onClose}>
      <form className="stack" onSubmit={save}>
        <label>Nombre<input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
        <div className="pair">
          <label><span>Variante <span className="muted optional">· opcional</span></span><input value={form.variant} onChange={(e) => setForm({ ...form, variant: e.target.value })} /></label>
          <label>Línea<select value={form.collection} onChange={(e) => setForm({ ...form, collection: e.target.value })}>{['General', 'Origen'].map((c) => <option key={c}>{c}</option>)}</select></label>
        </div>
        {error && <div className="error">{error}</div>}
        <Save busy={busy} label="Crear producto" onClose={onClose} />
      </form>
    </Modal>
  );
}
