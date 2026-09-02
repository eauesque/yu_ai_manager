import { getAppApi } from '../../shared/browser-apis';

export function t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

export function addLabeledInput(
  parent: HTMLElement,
  id: string,
  labelText: string,
  inputAttrs: Partial<HTMLInputElement> & Record<string, unknown>,
): HTMLInputElement {
  const wrap = document.createElement('div');
  const label = document.createElement('label');
  label.htmlFor = id;
  label.textContent = labelText;
  label.style.cssText = 'display:block;font-size:13px;margin-bottom:6px;';
  wrap.appendChild(label);
  const input = document.createElement('input');
  input.id = id;
  for (const [k, v] of Object.entries(inputAttrs)) {
    (input as unknown as Record<string, unknown>)[k] = v;
  }
  input.style.cssText = [
    'width:100%', 'padding:6px 8px',
    'border:1px solid var(--border,#ccc)', 'border-radius:4px',
    'font-size:13px',
    'background:var(--input-bg,#fff)', 'color:var(--fg,#222)',
  ].join(';');
  wrap.appendChild(input);
  parent.appendChild(wrap);
  return input;
}

export function showError(resultEl: HTMLElement, message: string): void {
  resultEl.textContent = '';
  const span = document.createElement('span');
  span.style.color = 'var(--danger,#c33)';
  span.textContent = message;
  resultEl.appendChild(span);
}
