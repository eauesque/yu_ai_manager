/**
 * extensions-config-dialog.ts -- Modal overlay for extension config.
 * Opens the config modal, renders form fields, handles save/cancel.
 */

import { ConfigField, ConfigSchema, _t, _toast, buildField, collectValues } from './extensions-config-fields';

let _overlay: HTMLDivElement | null = null;

function _close(): void {
  if (_overlay) {
    _overlay.remove();
    _overlay = null;
  }
  document.removeEventListener('keydown', _onKeydown);
}

function _onKeydown(e: KeyboardEvent): void {
  if (e.key === 'Escape') _close();
}

export async function openConfigModal(extName: string): Promise<void> {
  _close();

  // Fetch config schema
  let schema: ConfigSchema;
  try {
    const resp = await fetch(`/api/extensions/${encodeURIComponent(extName)}/config`);
    const json = await resp.json();
    schema = json.data?.config_schema || json.config_schema || {};
  } catch {
    _toast(_t('settings.ext_config_load_failed', 'Failed to load config'));
    return;
  }

  // API returns { key: {type, value, label, ...} } object -- convert to fields array
  let fields: ConfigField[] = schema.fields || [];
  if (fields.length === 0 && typeof schema === 'object') {
    // Convert object-keyed schema to fields array
    const schemaObj = schema as Record<string, unknown>;
    for (const [key, def] of Object.entries(schemaObj)) {
      if (key === 'fields' || key === 'values') continue;
      if (def && typeof def === 'object') {
        const d = def as Record<string, unknown>;
        fields.push({
          key,
          type: String(d.type || 'string'),
          label: d.label != null ? String(d.label) : undefined,
          description: d.description != null ? String(d.description) : undefined,
          default: d.default,
          value: d.value,
          options: Array.isArray(d.options) ? d.options.map(String) : undefined,
          model_source: d.model_source != null ? String(d.model_source) : undefined,
        });
      }
    }
  }
  if (fields.length === 0) {
    _toast(_t('settings.ext_no_config', 'No configurable options'));
    return;
  }

  const currentValues: Record<string, unknown> = schema.values || {};

  // Overlay
  _overlay = document.createElement('div');
  _overlay.style.cssText =
    'position:fixed;inset:0;z-index:10000;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;';
  _overlay.onclick = (e) => {
    if (e.target === _overlay) _close();
  };

  // Modal
  const modal = document.createElement('div');
  modal.style.cssText =
    'background:var(--card);border-radius:12px;padding:24px;max-width:480px;width:90%;max-height:80vh;overflow-y:auto;box-shadow:0 8px 32px rgba(0,0,0,0.3);';

  // Header
  const header = document.createElement('h3');
  header.style.cssText = 'margin:0 0 16px;font-size:16px;color:var(--text);';
  header.textContent = `${extName} — ${_t('settings.ext_config', 'Config')}`;
  modal.appendChild(header);

  // Form
  const form = document.createElement('div');
  for (const field of fields) {
    form.appendChild(buildField(field, currentValues, form, extName));
  }
  modal.appendChild(form);

  // Buttons
  const btnRow = document.createElement('div');
  btnRow.style.cssText = 'display:flex;justify-content:flex-end;gap:8px;margin-top:16px;';

  const cancelBtn = document.createElement('button');
  cancelBtn.type = 'button';
  cancelBtn.textContent = _t('common.cancel', 'Cancel');
  cancelBtn.style.cssText =
    'padding:7px 16px;border:1px solid rgba(128,128,128,0.3);border-radius:6px;background:transparent;color:var(--text);cursor:pointer;font-size:13px;';
  cancelBtn.onclick = _close;
  btnRow.appendChild(cancelBtn);

  const saveBtn = document.createElement('button');
  saveBtn.type = 'button';
  saveBtn.textContent = _t('common.save', 'Save');
  saveBtn.style.cssText =
    'padding:7px 16px;border:none;border-radius:6px;background:var(--accent);color:#fff;cursor:pointer;font-size:13px;font-weight:600;';
  saveBtn.onclick = async () => {
    const values = collectValues(form);
    try {
      const resp = await fetch(`/api/extensions/${encodeURIComponent(extName)}/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ values }),
      });
      const json = await resp.json();
      if (resp.ok) {
        _toast(_t('settings.ext_config_saved', 'Config saved'));
        _close();
      } else {
        _toast(json.error || json.data?.error || 'Save failed');
      }
    } catch {
      _toast(_t('settings.ext_config_save_failed', 'Failed to save config'));
    }
  };
  btnRow.appendChild(saveBtn);

  modal.appendChild(btnRow);
  _overlay.appendChild(modal);
  document.body.appendChild(_overlay);
  document.addEventListener('keydown', _onKeydown);
}
