/**
 * extensions-config-fields.ts -- Form field builder and value collector
 * for the extension config modal.
 */

import { getAppApi } from '../shared/browser-apis';

export interface ConfigField {
  key: string;
  type: string;          // "bool" | "string" | "number" | "integer" | "enum"
  label?: string | undefined;
  description?: string | undefined;
  default?: unknown;
  value?: unknown;
  options?: string[] | undefined;       // choices for enum type
  model_source?: string | undefined;    // "ollama" -- dynamically fetch model list
}

export interface ConfigSchema {
  fields?: ConfigField[];
  values?: Record<string, unknown>;
}

export function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

export function _toast(msg: string): void {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 3000);
}

/** Fetch model list from Ollama API and update the select element */
async function _fetchOllamaModels(
  formContainer: HTMLElement, select: HTMLSelectElement, currentVal: string,
): Promise<void> {
  // Find the base_url input within the form
  const baseUrlEl = formContainer.querySelector<HTMLInputElement | HTMLSelectElement>(
    '[data-config-key="base_url"]',
  );
  const baseUrl = baseUrlEl?.value || 'http://localhost:11434';

  // Show loading state
  select.disabled = true;
  const prevText = select.options[0]?.textContent || '';
  if (select.options.length <= 1) {
    select.options[0] && (select.options[0].textContent = 'Loading...');
  }

  try {
    const resp = await fetch('/api/analysis/ollama/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ollama_url: baseUrl }),
    });
    const json = await resp.json();
    const data = json.data || json;

    if (!data.connected || !Array.isArray(data.models)) {
      _toast(data.error || 'Ollama not connected');
      // Restore original text
      if (select.options[0]) select.options[0].textContent = prevText;
      select.disabled = false;
      return;
    }

    // Clear select and populate with new model list
    select.innerHTML = '';
    const models: string[] = data.models.map((m: { name: string }) => m.name);
    let found = false;
    for (const name of models) {
      const o = document.createElement('option');
      o.value = name;
      o.textContent = name;
      if (name === currentVal) {
        o.selected = true;
        found = true;
      }
      select.appendChild(o);
    }
    // Add current value at top if not in list
    if (currentVal && !found) {
      const o = document.createElement('option');
      o.value = currentVal;
      o.textContent = `${currentVal} (not found)`;
      o.selected = true;
      select.insertBefore(o, select.firstChild);
    }
    if (models.length === 0) {
      const o = document.createElement('option');
      o.value = '';
      o.textContent = '(no models)';
      select.appendChild(o);
    }
  } catch {
    _toast('Failed to fetch Ollama models');
    if (select.options[0]) select.options[0].textContent = prevText;
  } finally {
    select.disabled = false;
  }
}

export function buildField(
  field: ConfigField, currentValues: Record<string, unknown>, formContainer: HTMLElement,
  extName: string,
): HTMLDivElement {
  const row = document.createElement('div');
  row.style.cssText = 'margin-bottom:14px;';

  // Try i18n key ext.<extName>.config.<fieldKey>.label, fallback to field.label
  const labelKey = `ext.${extName}.config.${field.key}.label`;
  const descKey = `ext.${extName}.config.${field.key}.description`;

  const label = document.createElement('label');
  label.style.cssText = 'display:block;font-size:13px;font-weight:600;color:var(--text);margin-bottom:4px;';
  label.textContent = _t(labelKey, field.label || field.key);
  row.appendChild(label);

  const rawDesc = field.description || '';
  const descText = rawDesc ? _t(descKey, rawDesc) : '';
  if (descText) {
    const hint = document.createElement('div');
    hint.style.cssText = 'font-size:11px;color:var(--muted);margin-bottom:6px;';
    hint.textContent = descText;
    row.appendChild(hint);
  }

  const val = currentValues[field.key] ?? field.value ?? field.default;
  const fieldType = field.type?.toLowerCase() || 'string';

  const selectCss =
    'width:100%;padding:6px 10px;border-radius:6px;border:1px solid rgba(128,128,128,0.3);background:var(--bg);color:var(--text);font-size:13px;';
  const inputCss = selectCss;

  if (fieldType === 'bool' || fieldType === 'boolean') {
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.dataset.configKey = field.key;
    cb.dataset.configType = 'bool';
    cb.checked = !!val;
    cb.style.cssText = 'width:18px;height:18px;cursor:pointer;';
    row.appendChild(cb);
  } else if (fieldType === 'enum' && field.options) {
    const sel = document.createElement('select');
    sel.dataset.configKey = field.key;
    sel.dataset.configType = 'enum';
    sel.style.cssText = selectCss;
    for (const opt of field.options) {
      const o = document.createElement('option');
      o.value = opt;
      o.textContent = opt;
      if (String(val) === opt) o.selected = true;
      sel.appendChild(o);
    }
    row.appendChild(sel);
  } else if (field.model_source === 'ollama') {
    const wrapper = document.createElement('div');
    wrapper.style.cssText = 'display:flex;gap:6px;align-items:center;';

    const sel = document.createElement('select');
    sel.dataset.configKey = field.key;
    sel.dataset.configType = 'model_source';
    sel.style.cssText = selectCss + 'flex:1;';

    // Insert current value as default option
    const curVal = val != null ? String(val) : '';
    if (curVal) {
      const o = document.createElement('option');
      o.value = curVal;
      o.textContent = curVal;
      o.selected = true;
      sel.appendChild(o);
    }
    wrapper.appendChild(sel);

    const refreshBtn = document.createElement('button');
    refreshBtn.type = 'button';
    refreshBtn.textContent = '\u21BB';
    refreshBtn.title = _t('settings.ext_refresh_models', 'Refresh models');
    refreshBtn.style.cssText =
      'padding:4px 10px;border-radius:6px;border:1px solid rgba(128,128,128,0.3);background:var(--bg);color:var(--text);cursor:pointer;font-size:16px;flex-shrink:0;';
    refreshBtn.onclick = () => _fetchOllamaModels(formContainer, sel, curVal);
    wrapper.appendChild(refreshBtn);
    row.appendChild(wrapper);

    // Auto-load on first render (executed after form is added to DOM)
    setTimeout(() => _fetchOllamaModels(formContainer, sel, curVal), 100);
  } else if (fieldType === 'number' || fieldType === 'integer') {
    const inp = document.createElement('input');
    inp.type = 'number';
    inp.dataset.configKey = field.key;
    inp.dataset.configType = 'number';
    inp.value = val != null ? String(val) : '';
    inp.style.cssText = inputCss + 'max-width:200px;';
    if (fieldType === 'integer') inp.step = '1';
    row.appendChild(inp);
  } else {
    const inp = document.createElement('input');
    inp.type = 'text';
    inp.dataset.configKey = field.key;
    inp.dataset.configType = 'string';
    inp.value = val != null ? String(val) : '';
    inp.style.cssText = inputCss;
    row.appendChild(inp);
  }

  return row;
}

export function collectValues(container: HTMLElement): Record<string, unknown> {
  const values: Record<string, unknown> = {};
  const inputs = container.querySelectorAll<HTMLElement>('[data-config-key]');
  inputs.forEach((el) => {
    const key = (el as HTMLElement).dataset.configKey!;
    const type = (el as HTMLElement).dataset.configType || 'string';
    if (type === 'bool') {
      values[key] = (el as HTMLInputElement).checked;
    } else if (type === 'number') {
      const v = (el as HTMLInputElement).value;
      values[key] = v === '' ? null : Number(v);
    } else {
      // string, enum, model_source -- all use .value
      values[key] = (el as HTMLInputElement | HTMLSelectElement).value;
    }
  });
  return values;
}
