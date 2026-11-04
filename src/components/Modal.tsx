'use client';

import { useEffect, useRef } from 'react';

/** A native modal dialog: focus stays inside, Escape and the backdrop close it, the page behind does not scroll. */
export default function Modal({ title, onClose, children, wide = false }: { title: string; onClose: () => void; children: React.ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
    document.documentElement.style.overflow = 'hidden';
    return () => { document.documentElement.style.overflow = ''; };
  }, []);
  return (
    <dialog ref={ref} className={`modal${wide ? ' wide' : ''}`} aria-label={title}
            onCancel={(e) => { e.preventDefault(); onClose(); }}
            onClick={(e) => { if (e.target === ref.current) onClose(); }}>
      <div className="modal-head">
        <h2>{title}</h2>
        <button type="button" className="close" onClick={onClose} aria-label="Cerrar">×</button>
      </div>
      {children}
    </dialog>
  );
}
