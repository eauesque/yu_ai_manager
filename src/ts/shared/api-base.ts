const DEFAULT_API_BASE = 'http://127.0.0.1:5000';

export const API_BASE: string = (() => {
  const saved = (localStorage.getItem('apiBase') || '').trim();
  if (saved) return saved.replace(/\/$/, '');
  if (location.protocol === 'file:') return DEFAULT_API_BASE;
  return '';
})();

export function apiUrl(path: string): string {
  const p = (path || '').startsWith('/') ? path : '/' + path;
  return API_BASE ? API_BASE + p : p;
}
