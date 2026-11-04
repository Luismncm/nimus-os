'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { createContext, useContext, useEffect, useState } from 'react';
import { api, ApiError, User } from '@/lib/api';

/** The same sections as the local sidebar (views/shell.py). `ready` marks those already in the cloud. */
const SECTIONS: { group: string; area: 'Taller' | 'Negocio'; pages: { href: string; label: string; ready?: boolean; admin?: boolean }[] }[] = [
  { group: 'Trabajo diario', area: 'Taller', pages: [{ href: '/', label: 'Hoy', ready: true }, { href: '/pedidos', label: 'Pedidos', ready: true }] },
  { group: 'Producción', area: 'Taller', pages: [{ href: '/cola', label: 'Cola de producción' }, { href: '/desarrollo', label: 'Desarrollo y prototipos' }, { href: '/control', label: 'Control de producción' }] },
  { group: 'Productos y existencias', area: 'Taller', pages: [{ href: '/origen', label: 'Colección Origen' }, { href: '/inventario', label: 'Inventario' }, { href: '/catalogo', label: 'Catálogo y recetas' }] },
  { group: 'Equipo', area: 'Taller', pages: [{ href: '/maquinas', label: 'Máquinas' }] },
  { group: 'Comercial', area: 'Negocio', pages: [{ href: '/ventas', label: 'Ventas y cobranza', admin: true }, { href: '/cotizaciones', label: 'Cotizaciones', admin: true }] },
  { group: 'Control financiero', area: 'Negocio', pages: [{ href: '/resumen', label: 'Resumen y previsión', admin: true }, { href: '/gastos', label: 'Gastos y comprobantes', admin: true }, { href: '/tesoreria', label: 'Tesorería', admin: true }, { href: '/socios', label: 'Socios y aportaciones', admin: true }] },
  { group: 'Rentabilidad', area: 'Negocio', pages: [{ href: '/costos', label: 'Costos y utilidad', admin: true }, { href: '/rendimiento', label: 'Estado de rendimiento', admin: true }] },
];

const UserContext = createContext<User | null>(null);
export const useUser = () => useContext(UserContext);

export default function Shell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    api<User>('/auth/me')
      .then(setUser)
      .catch((exc) => {
        if (exc instanceof ApiError && exc.status === 401) router.replace('/login');
      });
  }, [router]);

  useEffect(() => setOpen(false), [path]);

  async function logout() {
    await api('/auth/logout', { method: 'POST' });
    router.replace('/login');
  }

  if (!user) return <div className="empty">Cargando…</div>;
  const current = (href: string) => (href === '/' ? path === '/' : path.startsWith(href));

  return (
    <UserContext.Provider value={user}>
      <div className="frame">
        <nav className={`side${open ? ' open' : ''}`} aria-label="Secciones">
          <div className="brand">NIMUS · OS</div>
          {SECTIONS.map((section) => {
            const pages = section.pages.filter((p) => !p.admin || user.role === 'admin');
            if (!pages.length) return null;
            return (
              <div key={section.group}>
                <div className="group">{section.group}</div>
                {pages.map((page) => (
                  <Link key={page.href} href={page.href} className={`nav${page.ready ? '' : ' soon'}`}
                        aria-current={current(page.href) ? 'page' : undefined} aria-disabled={!page.ready}
                        title={page.ready ? undefined : 'Llega en una fase siguiente de la migración'}>
                    {page.label}
                  </Link>
                ))}
              </div>
            );
          })}
          <div className="foot">
            {user.name || user.email} · {user.role === 'admin' ? 'Administración' : 'Taller'}
            <br />
            <button onClick={logout}>Cerrar sesión</button>
          </div>
        </nav>
        <div>
          <header className="topbar">
            <strong>NIMUS · OS</strong>
            <button onClick={() => setOpen((v) => !v)} aria-expanded={open}>{open ? 'Cerrar' : 'Menú'}</button>
          </header>
          <main className="main">{children}</main>
        </div>
      </div>
    </UserContext.Provider>
  );
}
