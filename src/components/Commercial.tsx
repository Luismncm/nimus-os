'use client';

/**
 * Lines of a quotation or sale with live totals. The API computes the totals (quotations.calculate), so the
 * figures here are the ones that will be saved, including discount and IVA rounding.
 */
import { FormEvent, useEffect, useState } from 'react';
import Modal from '@/components/Modal';
import { api, money } from '@/lib/api';

export type DraftLine = { description: string; quantity: number | string; price: number | string; produce: boolean; recipe_id?: number | null };
export type Draft = { client: string; project: string; discount: number | string; iva: boolean; notes?: string; lines: DraftLine[]; [key: string]: unknown };
export type Totals = { subtotal: number; discount: number; tax: number; total: number };

export const today = () => new Date().toLocaleDateString('en-CA');

/** The payload as the services expect it: numbers as numbers, empty rows left out. */
export function clean(draft: Draft) {
  return {
    ...draft,
    discount: Number(draft.discount) || 0,
    lines: draft.lines.filter((l) => String(l.description).trim() || Number(l.price))
      .map((l) => ({ ...l, quantity: Number(l.quantity), price: Number(l.price) || 0 })),
  };
}

export function LinesEditor({ draft, onChange, disabled = false }: { draft: Draft; onChange: (d: Draft) => void; disabled?: boolean }) {
  const [totals, setTotals] = useState<Totals | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    const t = setTimeout(() => {
      api<{ totals: Totals }>('/comercial/calcular', { method: 'POST', body: JSON.stringify({ payload: clean(draft) }) })
        .then((r) => { setTotals(r.totals); setError(''); })
        .catch((e) => { setTotals(null); setError(e.message); });
    }, 300);
    return () => clearTimeout(t);
  }, [draft]);
  const line = (i: number, patch: Partial<DraftLine>) => onChange({ ...draft, lines: draft.lines.map((l, j) => (j === i ? { ...l, ...patch } : l)) });

  return (
    <div className="stack">
      <div className="pair">
        <label>Cliente<input disabled={disabled} value={draft.client} onChange={(e) => onChange({ ...draft, client: e.target.value })} /></label>
        <label>Proyecto o concepto<input disabled={disabled} value={draft.project} onChange={(e) => onChange({ ...draft, project: e.target.value })} /></label>
      </div>
      <div className="table-wrap split">
        <table>
          <thead><tr><th>Producto / servicio</th><th className="right">Cantidad</th><th className="right">P. unitario</th><th>Fabricar</th><th className="right">Importe</th><th /></tr></thead>
          <tbody>
            {draft.lines.map((l, i) => (
              <tr key={i}>
                <td><input disabled={disabled} style={{ textAlign: 'left', minWidth: 180 }} value={l.description} onChange={(e) => line(i, { description: e.target.value })} aria-label={`Descripción de la partida ${i + 1}`} /></td>
                <td><input disabled={disabled} type="number" inputMode="decimal" min={0} step="any" value={l.quantity} onChange={(e) => line(i, { quantity: e.target.value })} aria-label="Cantidad" /></td>
                <td><input disabled={disabled} type="number" inputMode="decimal" min={0} step="0.01" value={l.price} onChange={(e) => line(i, { price: e.target.value })} aria-label="Precio unitario" /></td>
                <td><input disabled={disabled} type="checkbox" checked={l.produce} onChange={(e) => line(i, { produce: e.target.checked })} aria-label="Para fabricar" style={{ minWidth: 0, width: 20 }} /></td>
                <td className="right num">{money(Math.round((Number(l.quantity) || 0) * (Number(l.price) || 0) * 100))}</td>
                <td>{!disabled && <button type="button" className="btn small ghost" onClick={() => onChange({ ...draft, lines: draft.lines.filter((_, j) => j !== i) })} aria-label={`Quitar partida ${i + 1}`}>×</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!disabled && <button type="button" className="btn small" style={{ justifySelf: 'start' }} onClick={() => onChange({ ...draft, lines: [...draft.lines, { description: '', quantity: 1, price: '', produce: false }] })}>Agregar partida</button>}
      <div className="toolbar">
        <div className="badges">
          <label className="inline-label">Descuento %<input disabled={disabled} type="number" inputMode="decimal" min={0} max={100} step="any" value={draft.discount} onChange={(e) => onChange({ ...draft, discount: e.target.value })} style={{ width: 90 }} /></label>
          <label className="check inline"><input disabled={disabled} type="checkbox" checked={draft.iva} onChange={(e) => onChange({ ...draft, iva: e.target.checked })} /><span>IVA 16%</span></label>
        </div>
        {totals && <div className="totals num">Subtotal {money(totals.subtotal)} · Descuento −{money(totals.discount)} · IVA {money(totals.tax)} · <strong>Total {money(totals.total)}</strong></div>}
      </div>
      {error && draft.lines.length > 0 && <div className="error">{error}</div>}
    </div>
  );
}

export function ReasonDialog({ title, note, label, path, extra, onClose, onDone }: { title: string; note: string; label: string; path: string; extra: object; onClose: () => void; onDone: () => void }) {
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function save(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try { await api(path, { method: 'POST', body: JSON.stringify({ ...extra, reason }) }); onDone(); }
    catch (err) { setError((err as Error).message); setBusy(false); }
  }
  return (
    <Modal title={title} onClose={onClose}>
      <form className="stack" onSubmit={save}>
        <p className="muted">{note}</p>
        <label>Motivo<input required value={reason} onChange={(e) => setReason(e.target.value)} /></label>
        {error && <div className="error">{error}</div>}
        <div className="actions"><button type="button" className="btn" onClick={onClose}>Volver</button><button className="btn primary" disabled={busy}>{busy ? 'Guardando…' : label}</button></div>
      </form>
    </Modal>
  );
}
