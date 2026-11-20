import { appCheck } from './firebase';
import { getToken } from 'firebase/app-check';

const BASE = import.meta.env.VITE_API_BASE_URL || '/api';
export async function apiRequest(path, { token, ...options } = {}) {
  const headers = new Headers(options.headers || {});
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (appCheck) {
    try { const result = await getToken(appCheck, false); headers.set('X-Firebase-AppCheck', result.token); } catch { /* API decides whether App Check is enforced. */ }
  }
  const response = await fetch(`${BASE}${path}`, { ...options, headers });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
  return body;
}
