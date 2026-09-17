export function tr(key: string, fallback: string): string {
  const w = window as unknown as { tr?: (k: string, f?: string) => string };
  return typeof w.tr === 'function' ? w.tr(key, fallback) : fallback;
}

export function setText(id: string, text: string): void {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

export function hideSpinner(): void {
  const el = document.getElementById('sweepViewLoading');
  if (el) el.style.display = 'none';
}

export function showError(message: string): void {
  hideSpinner();
  const host = document.getElementById('sweepViewMessages');
  if (!host) return;
  host.textContent = '';
  const banner = document.createElement('div');
  banner.style.cssText =
    'padding:10px 12px;border-left:3px solid #e57373;' +
    'background:rgba(229,115,115,0.08);border-radius:4px;';
  banner.textContent = message;
  host.appendChild(banner);
}
