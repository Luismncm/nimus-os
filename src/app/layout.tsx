import type { Metadata, Viewport } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'NIMUS · OS',
  description: 'Taller, producción y negocio de NIMUS.',
};

export const viewport: Viewport = { width: 'device-width', initialScale: 1, themeColor: '#0F252C' };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
