/** Calls to the NIMUS API: the session cookie travels by itself; writes add the X-NIMUS header the API requires. */

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const write = init.method && init.method !== 'GET';
  const response = await fetch(`/api${path}`, {
    ...init,
    credentials: 'same-origin',
    headers: { ...(write ? { 'Content-Type': 'application/json', 'X-NIMUS': '1' } : {}), ...(init.headers || {}) },
  });
  if (!response.ok) {
    let detail = 'No se pudo completar la solicitud.';
    try {
      const body = await response.json();
      if (typeof body.detail === 'string') detail = body.detail;
    } catch {}
    throw new ApiError(response.status, detail);
  }
  return response.json() as Promise<T>;
}

const pesos = new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN' });

/** Cents to pesos, as the local app shows them ($7,632.00). */
export function money(cents: number | null | undefined) {
  return pesos.format((cents ?? 0) / 100);
}

export function longDate(iso: string) {
  const date = new Date(`${iso}T12:00:00`);
  const text = date.toLocaleDateString('es-MX', { weekday: 'long', day: 'numeric', month: 'long' });
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export type User = { id: number; email: string; name: string; role: 'admin' | 'taller' };
