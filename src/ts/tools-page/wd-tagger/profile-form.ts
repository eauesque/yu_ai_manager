/**
 * wd-tagger/profile-form.ts -- Profile manager form view (schema v2).
 *
 * DOM construction policy: createElement + textContent/value + appendChild only.
 * Avoid HTML string insertion and inline event handlers.
 */

import { customConfirm } from '../../shared/dialog';

export type ProfileFormMode = 'create' | 'edit' | 'duplicate';

export type ProfileV2 = Record<string, unknown> & {
  id: string;
  display_name: string;
  profile_version?: number | string;
  model_id: string;
  adapter_family?: string;
  backend?: string;
  hf_subdir?: string;
  files?: Array<{ name: string; required?: boolean; size_hint_mb?: number }>;
  tag_source?: Record<string, unknown>;
  threshold_source?: Record<string, unknown>;
  preprocess_spec?: Record<string, unknown>;
  supports_categories?: string[];
  categories_mode?: string;
  builtin?: boolean;
  origin?: string;
  overrides_builtin?: boolean;
};

export interface ProfileFormCallbacks {
  mode: ProfileFormMode;
  profile?: ProfileV2 | undefined;
  onCancel: () => void;
  onSaved: () => void;
}

export interface ProfileFormApi {
  getState: () => ProfileV2;
}

type BannerKind = 'ok' | 'error' | 'info';

function _t(key: string, fallback: string): string {
  try {
    if (typeof window.tr === 'function') {
      const v = String((window.tr as (k: string, f?: string) => unknown)(key, fallback));
      return v || fallback;
    }
  } catch { /* ignore */ }
  return fallback;
}

function _clear(el: HTMLElement): void {
  while (el.firstChild) el.removeChild(el.firstChild);
}

function _csrfHeadersForUnsafe(): HeadersInit {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  try {
    const anyWin = window as unknown as { csrfHeader?: () => unknown };
    const h = typeof anyWin.csrfHeader === 'function' ? anyWin.csrfHeader() : null;
    if (h && typeof h === 'object') return { ...headers, ...(h as Record<string, string>) };
  } catch { /* ignore */ }
  return headers;
}

async function _apiJson(path: string, init?: RequestInit): Promise<{ res: Response; json: any }> {
  const res = await fetch(path, init);
  let json: any = null;
  try {
    json = await res.json();
  } catch {
    json = null;
  }
  return { res, json };
}

function _mkBanner(container: HTMLElement): { show: (kind: BannerKind, text: string) => void; clear: () => void } {
  const host = document.createElement('div');
  host.style.cssText = 'margin:10px 0 12px;font-size:12px;';
  container.appendChild(host);
  let timer: ReturnType<typeof setTimeout> | null = null;
  function clear(): void {
    host.textContent = '';
    if (timer) clearTimeout(timer);
    timer = null;
  }
  function show(kind: BannerKind, text: string): void {
    clear();
    if (!text) return;
    const el = document.createElement('div');
    el.textContent = text;
    el.style.cssText = [
      'padding:8px 10px', 'border-radius:6px',
      kind === 'ok' ? 'background:rgba(0,160,80,0.12);border:1px solid rgba(0,160,80,0.25)'
        : kind === 'error' ? 'background:rgba(176,0,32,0.10);border:1px solid rgba(176,0,32,0.20)'
          : 'background:rgba(0,128,255,0.10);border:1px solid rgba(0,128,255,0.20)',
    ].join(';');
    host.appendChild(el);
    timer = setTimeout(() => { if (host.contains(el)) el.remove(); }, 5000);
  }
  return { show, clear };
}

function _mkFieldRow(labelText: string, input: HTMLElement, helpText?: string): HTMLElement {
  const row = document.createElement('div');
  row.style.cssText = 'display:flex;flex-direction:column;gap:4px;margin:8px 0;';
  const lab = document.createElement('label');
  lab.textContent = labelText;
  lab.style.cssText = 'font-size:12px;opacity:0.85;';
  if (input instanceof HTMLInputElement || input instanceof HTMLSelectElement || input instanceof HTMLTextAreaElement) {
    if (input.id) lab.htmlFor = input.id;
  }
  row.appendChild(lab);
  row.appendChild(input);
  if (helpText) {
    const help = document.createElement('div');
    help.textContent = helpText;
    help.style.cssText = 'font-size:11px;opacity:0.7;';
    row.appendChild(help);
  }
  return row;
}

function _mkAccordionSection(title: string): { root: HTMLElement; content: HTMLElement; setOpen: (open: boolean) => void } {
  const root = document.createElement('div');
  root.style.cssText = 'border:1px solid var(--border,#ddd);border-radius:8px;margin:10px 0;overflow:hidden;';
  const header = document.createElement('button');
  header.type = 'button';
  header.className = 'btn btn-secondary';
  header.style.cssText = 'width:100%;display:flex;justify-content:space-between;align-items:center;border:none;border-radius:0;text-align:left;padding:10px 12px;';
  header.dataset.action = 'toggle-section';
  root.appendChild(header);

  const hText = document.createElement('span');
  hText.textContent = title;
  header.appendChild(hText);

  const caret = document.createElement('span');
  caret.textContent = '▾';
  caret.style.cssText = 'opacity:0.7;';
  header.appendChild(caret);

  const content = document.createElement('div');
  content.style.cssText = 'padding:10px 12px;';
  root.appendChild(content);

  function setOpen(open: boolean): void {
    content.hidden = !open;
    caret.textContent = open ? '▾' : '▸';
  }
  setOpen(true);

  header.addEventListener('click', () => {
    setOpen(!!content.hidden);
  });

  return { root, content, setOpen };
}

function _idValid(id: string): boolean {
  const re = /^[a-z0-9][a-z0-9_-]{0,63}$/;
  return re.test(id);
}

function _cloneProfile(p: ProfileV2): ProfileV2 {
  try {
    return JSON.parse(JSON.stringify(p)) as ProfileV2;
  } catch {
    return { ...p };
  }
}

function _defaultProfile(): ProfileV2 {
  return {
    id: '',
    display_name: '',
    profile_version: 2,
    adapter_family: 'wd',
    backend: 'onnx',
    model_id: '',
    hf_subdir: '',
    files: [],
    tag_source: { type: 'csv' },
    threshold_source: { type: 'global_per_category', thresholds: { general: 0.35 } },
    default_thresholds: { general: 0.35 },
    preprocess_spec: {
      input_size: 448,
      dtype: 'float32',
      layout: 'NHWC',
      channel_order: 'RGB',
      resize_strategy: 'longest_side_pad',
      scale: 1.0,
      mean: [0, 0, 0],
      std: [1, 1, 1],
    },
    supports_categories: ['general'],
    categories_mode: 'from_tag_source',
  };
}

export function renderProfileForm(container: HTMLElement, cb: ProfileFormCallbacks): ProfileFormApi {
  const orig = cb.profile ? _cloneProfile(cb.profile) : null;
  const state: { profile: ProfileV2; saving: boolean; testing: boolean; fieldErrors: Map<string, string> } = {
    profile: orig ? _cloneProfile(orig) : _defaultProfile(),
    saving: false,
    testing: false,
    fieldErrors: new Map(),
  };
  if (cb.mode === 'duplicate' && orig) {
    state.profile.id = `${orig.id || 'profile'}-copy`;
  }
  if (cb.mode === 'create') {
    state.profile.profile_version = 2;
  }

  const header = document.createElement('div');
  header.style.cssText = 'display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;';
  container.appendChild(header);

  const title = document.createElement('div');
  title.style.cssText = 'font-weight:600;';
  title.textContent = cb.mode === 'edit'
    ? _t('tools.wt_profile_form_edit', 'Edit profile')
    : cb.mode === 'duplicate'
      ? _t('tools.wt_profile_form_duplicate', 'Duplicate profile')
      : _t('tools.wt_profile_form_new', 'New profile');
  header.appendChild(title);

  const actionsTop = document.createElement('div');
  actionsTop.style.cssText = 'display:flex;gap:8px;align-items:center;flex-wrap:wrap;';
  header.appendChild(actionsTop);

  const saveBtn = document.createElement('button');
  saveBtn.type = 'button';
  saveBtn.className = 'btn btn-primary';
  saveBtn.textContent = _t('tools.wt_profile_save', 'Save');
  saveBtn.dataset.action = 'save';
  actionsTop.appendChild(saveBtn);

  const testBtn = document.createElement('button');
  testBtn.type = 'button';
  testBtn.className = 'btn btn-secondary';
  testBtn.textContent = _t('tools.wt_profile_test', 'Test (dry-run download)');
  testBtn.dataset.action = 'test';
  actionsTop.appendChild(testBtn);

  const cancelBtn = document.createElement('button');
  cancelBtn.type = 'button';
  cancelBtn.className = 'btn btn-secondary';
  cancelBtn.textContent = _t('tools.wt_profile_cancel', 'Cancel');
  cancelBtn.dataset.action = 'cancel';
  actionsTop.appendChild(cancelBtn);

  const banner = _mkBanner(container);

  const metaSec = _mkAccordionSection(_t('tools.wt_profile_section_meta', 'Metadata'));
  container.appendChild(metaSec.root);

  const modelSec = _mkAccordionSection(_t('tools.wt_profile_section_model', 'Model & files'));
  container.appendChild(modelSec.root);

  const tagSec = _mkAccordionSection(_t('tools.wt_profile_section_tag', 'Tag source'));
  container.appendChild(tagSec.root);

  const threshSec = _mkAccordionSection(_t('tools.wt_profile_section_thresh', 'Threshold source'));
  container.appendChild(threshSec.root);

  const prepSec = _mkAccordionSection(_t('tools.wt_profile_section_prep', 'Preprocess & categories'));
  container.appendChild(prepSec.root);

  // Field map for validation errors
  const fieldEl = new Map<string, HTMLElement>();

  function markFieldError(name: string, msg: string): void {
    const el = fieldEl.get(name) as (HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement | null);
    if (!el) return;
    el.title = msg;
    el.style.borderColor = 'rgba(176,0,32,0.55)';
  }

  function clearFieldErrors(): void {
    state.fieldErrors.clear();
    for (const [k, el] of fieldEl.entries()) {
      const inp = el as (HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement);
      inp.title = '';
      inp.style.borderColor = '';
    }
  }

  function setSaving(v: boolean): void {
    state.saving = v;
    saveBtn.disabled = v || state.testing;
    testBtn.disabled = v || state.testing;
    cancelBtn.disabled = v || state.testing;
  }

  function setTesting(v: boolean): void {
    state.testing = v;
    saveBtn.disabled = v || state.saving;
    testBtn.disabled = v || state.saving;
    cancelBtn.disabled = v || state.saving;
  }

  function readFieldString(key: keyof ProfileV2): string {
    const v = state.profile[key];
    return typeof v === 'string' ? v : v == null ? '' : String(v);
  }

  // ── Metadata ───────────────────────────────────────
  const idInput = document.createElement('input');
  idInput.type = 'text';
  idInput.id = 'wt-profile-id';
  idInput.name = 'id';
  idInput.value = readFieldString('id');
  idInput.placeholder = 'wd14-swinv2-v3';
  idInput.autocomplete = 'off';
  idInput.style.cssText = 'width:100%;';
  metaSec.content.appendChild(_mkFieldRow(_t('tools.wt_profile_id', 'id'), idInput, '^[a-z0-9][a-z0-9_-]{0,63}$'));
  fieldEl.set('id', idInput);

  const idHint = document.createElement('div');
  idHint.style.cssText = 'font-size:11px;opacity:0.75;margin-top:-4px;';
  metaSec.content.appendChild(idHint);

  const dnInput = document.createElement('input');
  dnInput.type = 'text';
  dnInput.id = 'wt-profile-display-name';
  dnInput.name = 'display_name';
  dnInput.value = readFieldString('display_name');
  dnInput.style.cssText = 'width:100%;';
  metaSec.content.appendChild(_mkFieldRow(_t('tools.wt_profile_display_name', 'display_name'), dnInput));
  fieldEl.set('display_name', dnInput);

  const pvInput = document.createElement('input');
  pvInput.type = 'text';
  pvInput.id = 'wt-profile-version';
  pvInput.name = 'profile_version';
  pvInput.value = '2';
  pvInput.readOnly = true;
  pvInput.style.cssText = 'width:100%;opacity:0.7;';
  metaSec.content.appendChild(_mkFieldRow(_t('tools.wt_profile_profile_version', 'profile_version'), pvInput));
  fieldEl.set('profile_version', pvInput);

  function updateIdHint(): void {
    const v = (idInput.value || '').trim();
    if (!v) {
      idHint.textContent = '';
      idInput.style.borderColor = '';
      return;
    }
    if (_idValid(v)) {
      idHint.textContent = _t('tools.wt_profile_id_ok', 'OK');
      idHint.style.color = '';
      idInput.style.borderColor = '';
    } else {
      idHint.textContent = _t('tools.wt_profile_id_invalid', 'Invalid id');
      idHint.style.color = '#b00020';
      idInput.style.borderColor = 'rgba(176,0,32,0.55)';
    }
  }

  idInput.addEventListener('input', () => {
    state.profile.id = (idInput.value || '').trim();
    updateIdHint();
  });
  dnInput.addEventListener('input', () => { state.profile.display_name = (dnInput.value || '').trim(); });
  updateIdHint();

  // ── Model & Files ──────────────────────────────────
  const afSel = document.createElement('select');
  afSel.id = 'wt-profile-adapter-family';
  afSel.name = 'adapter_family';
  afSel.style.cssText = 'width:100%;';
  for (const v of ['wd', 'camie', 'oppai', 'generic_onnx']) {
    const opt = document.createElement('option');
    opt.value = v;
    opt.textContent = v;
    afSel.appendChild(opt);
  }
  afSel.value = readFieldString('adapter_family') || 'wd';
  modelSec.content.appendChild(_mkFieldRow(_t('tools.wt_profile_adapter_family', 'adapter_family'), afSel));
  fieldEl.set('adapter_family', afSel);

  const beSel = document.createElement('select');
  beSel.id = 'wt-profile-backend';
  beSel.name = 'backend';
  beSel.style.cssText = 'width:100%;';
  {
    const opt = document.createElement('option');
    opt.value = 'onnx';
    opt.textContent = 'onnx';
    beSel.appendChild(opt);
  }
  beSel.value = readFieldString('backend') || 'onnx';
  modelSec.content.appendChild(_mkFieldRow(_t('tools.wt_profile_backend', 'backend'), beSel));
  fieldEl.set('backend', beSel);

  const modelIdInput = document.createElement('input');
  modelIdInput.type = 'text';
  modelIdInput.id = 'wt-profile-model-id';
  modelIdInput.name = 'model_id';
  modelIdInput.value = readFieldString('model_id');
  modelIdInput.placeholder = 'SmilingWolf/wd-swinv2-tagger-v3';
  modelIdInput.style.cssText = 'width:100%;';
  modelSec.content.appendChild(_mkFieldRow(_t('tools.wt_profile_model_id', 'model_id'), modelIdInput));
  fieldEl.set('model_id', modelIdInput);

  const subdirInput = document.createElement('input');
  subdirInput.type = 'text';
  subdirInput.id = 'wt-profile-hf-subdir';
  subdirInput.name = 'hf_subdir';
  subdirInput.value = readFieldString('hf_subdir');
  subdirInput.placeholder = 'optional/subdir';
  subdirInput.style.cssText = 'width:100%;';
  modelSec.content.appendChild(_mkFieldRow(_t('tools.wt_profile_hf_subdir', 'hf_subdir'), subdirInput));
  fieldEl.set('hf_subdir', subdirInput);

  afSel.addEventListener('change', () => { state.profile.adapter_family = afSel.value; });
  beSel.addEventListener('change', () => { state.profile.backend = beSel.value; });
  modelIdInput.addEventListener('input', () => { state.profile.model_id = (modelIdInput.value || '').trim(); });
  subdirInput.addEventListener('input', () => { state.profile.hf_subdir = (subdirInput.value || '').trim(); });

  const filesTitle = document.createElement('div');
  filesTitle.textContent = _t('tools.wt_profile_files', 'files');
  filesTitle.style.cssText = 'font-size:12px;opacity:0.85;margin-top:10px;';
  modelSec.content.appendChild(filesTitle);

  const filesList = document.createElement('div');
  modelSec.content.appendChild(filesList);

  const addFileBtn = document.createElement('button');
  addFileBtn.type = 'button';
  addFileBtn.className = 'btn btn-secondary';
  addFileBtn.textContent = _t('tools.wt_profile_add_file', '+ Add file');
  addFileBtn.dataset.action = 'add-file';
  modelSec.content.appendChild(addFileBtn);

  function renderFiles(): void {
    _clear(filesList);
    const files = Array.isArray(state.profile.files) ? state.profile.files : [];
    for (let idx = 0; idx < files.length; idx++) {
      const f = files[idx] || { name: '' };
      const row = document.createElement('div');
      row.style.cssText = 'display:grid;grid-template-columns:1fr auto auto auto;gap:8px;align-items:center;margin:8px 0;';
      filesList.appendChild(row);

      const name = document.createElement('input');
      name.type = 'text';
      name.id = `wt-profile-file-name-${idx}`;
      name.name = `files.${idx}.name`;
      name.value = String(f.name || '');
      name.placeholder = 'model.onnx';
      name.style.cssText = 'width:100%;';
      row.appendChild(name);
      fieldEl.set(name.name, name);

      const reqLab = document.createElement('label');
      reqLab.style.cssText = 'display:flex;align-items:center;gap:6px;font-size:12px;';
      const req = document.createElement('input');
      req.type = 'checkbox';
      req.id = `wt-profile-file-required-${idx}`;
      req.name = `files.${idx}.required`;
      req.checked = !!f.required;
      reqLab.appendChild(req);
      reqLab.appendChild(document.createTextNode(_t('tools.wt_profile_required', 'required')));
      row.appendChild(reqLab);
      fieldEl.set(req.name, req);

      const size = document.createElement('input');
      size.type = 'number';
      size.id = `wt-profile-file-size-${idx}`;
      size.name = `files.${idx}.size_hint_mb`;
      size.value = f.size_hint_mb == null ? '' : String(f.size_hint_mb);
      size.min = '0';
      size.step = '1';
      size.style.cssText = 'width:110px;';
      row.appendChild(size);
      fieldEl.set(size.name, size);

      const del = document.createElement('button');
      del.type = 'button';
      del.className = 'btn btn-secondary';
      del.textContent = _t('tools.wt_profile_remove', 'Remove');
      del.dataset.action = 'remove-file';
      del.dataset.index = String(idx);
      row.appendChild(del);

      name.addEventListener('input', () => {
        const cur = Array.isArray(state.profile.files) ? state.profile.files : [];
        if (!cur[idx]) cur[idx] = { name: '' };
        cur[idx].name = (name.value || '').trim();
        state.profile.files = cur;
      });
      req.addEventListener('change', () => {
        const cur = Array.isArray(state.profile.files) ? state.profile.files : [];
        if (!cur[idx]) cur[idx] = { name: '' };
        cur[idx].required = req.checked;
        state.profile.files = cur;
      });
      size.addEventListener('input', () => {
        const cur = Array.isArray(state.profile.files) ? state.profile.files : [];
        if (!cur[idx]) cur[idx] = { name: '' };
        const n = parseInt(size.value, 10);
        if (Number.isFinite(n)) cur[idx].size_hint_mb = n;
        else delete cur[idx].size_hint_mb;
        state.profile.files = cur;
      });
    }
    // file names changed → refresh dependent selects
    renderTagSubform();
    renderThrSubform();
  }
  renderFiles();

  // ── Tag source (skeleton) ──────────────────────────
  const tagType = document.createElement('div');
  tagType.style.cssText = 'display:flex;gap:10px;flex-wrap:wrap;';
  tagSec.content.appendChild(tagType);

  const tagTypes = ['csv', 'json_list', 'json_dict', 'composite'] as const;
  const tagTypeName = 'tag_source.type';
  function getTagType(): string {
    const ts = state.profile.tag_source;
    const v = ts && typeof ts === 'object' ? String((ts as any).type || '') : '';
    return v || 'csv';
  }
  function setTagType(v: string): void {
    const ts = (state.profile.tag_source && typeof state.profile.tag_source === 'object') ? state.profile.tag_source : {};
    (ts as any).type = v;
    state.profile.tag_source = ts as any;
  }
  for (const v of tagTypes) {
    const lab = document.createElement('label');
    lab.style.cssText = 'display:flex;align-items:center;gap:6px;font-size:12px;';
    const r = document.createElement('input');
    r.type = 'radio';
    r.name = tagTypeName;
    r.id = `wt-profile-tag-type-${v}`;
    r.value = v;
    r.checked = getTagType() === v;
    lab.appendChild(r);
    lab.appendChild(document.createTextNode(v));
    tagType.appendChild(lab);
    fieldEl.set(r.name + ':' + v, r);
    r.addEventListener('change', () => {
      if (!r.checked) return;
      setTagType(v);
      renderTagSubform();
    });
  }

  const tagSub = document.createElement('div');
  tagSec.content.appendChild(tagSub);

  function renderTagSubform(): void {
    _clear(tagSub);
    const type = getTagType();
    const ts = (state.profile.tag_source && typeof state.profile.tag_source === 'object') ? state.profile.tag_source : {};
    state.profile.tag_source = ts as any;

    const mkFileSelect = (id: string, name: string, value: string): HTMLSelectElement => {
      const sel = document.createElement('select');
      sel.id = id;
      sel.name = name;
      sel.style.cssText = 'width:100%;';
      const empty = document.createElement('option');
      empty.value = '';
      empty.textContent = _t('tools.wt_profile_file_select', '(select file)');
      sel.appendChild(empty);
      const files = Array.isArray(state.profile.files) ? state.profile.files : [];
      for (const f of files) {
        const fn = String(f?.name || '').trim();
        if (!fn) continue;
        const opt = document.createElement('option');
        opt.value = fn;
        opt.textContent = fn;
        sel.appendChild(opt);
      }
      sel.value = value || '';
      return sel;
    };

    if (type === 'csv') {
      const fileRef = mkFileSelect('wt-profile-tag-csv-file', 'tag_source.file', String((ts as any).file || ''));
      tagSub.appendChild(_mkFieldRow(_t('tools.wt_profile_tag_csv_file', 'file'), fileRef));
      fieldEl.set(fileRef.name, fileRef);

      const delimiter = document.createElement('input');
      delimiter.type = 'text';
      delimiter.id = 'wt-profile-tag-csv-delim';
      delimiter.name = 'tag_source.delimiter';
      delimiter.value = String((ts as any).delimiter ?? ',');
      delimiter.style.cssText = 'width:100%;';
      tagSub.appendChild(_mkFieldRow(_t('tools.wt_profile_tag_csv_delimiter', 'delimiter'), delimiter));
      fieldEl.set(delimiter.name, delimiter);

      const nameCol = document.createElement('input');
      nameCol.type = 'text';
      nameCol.id = 'wt-profile-tag-csv-name-col';
      nameCol.name = 'tag_source.name_col';
      nameCol.value = String((ts as any).name_col ?? 'name');
      nameCol.style.cssText = 'width:100%;';
      tagSub.appendChild(_mkFieldRow(_t('tools.wt_profile_tag_csv_name_col', 'name_col'), nameCol));
      fieldEl.set(nameCol.name, nameCol);

      const catCol = document.createElement('input');
      catCol.type = 'text';
      catCol.id = 'wt-profile-tag-csv-cat-col';
      catCol.name = 'tag_source.category_col';
      catCol.value = String((ts as any).category_col ?? 'category');
      catCol.style.cssText = 'width:100%;';
      tagSub.appendChild(_mkFieldRow(_t('tools.wt_profile_tag_csv_category_col', 'category_col'), catCol));
      fieldEl.set(catCol.name, catCol);

      const catMap = document.createElement('textarea');
      catMap.id = 'wt-profile-tag-csv-cat-map';
      catMap.name = 'tag_source.category_map';
      catMap.rows = 4;
      catMap.style.cssText = 'width:100%;font-family:ui-monospace, SFMono-Regular, Menlo, monospace;font-size:12px;';
      catMap.value = typeof (ts as any).category_map === 'string' ? String((ts as any).category_map) : JSON.stringify((ts as any).category_map ?? {}, null, 2);
      tagSub.appendChild(_mkFieldRow(_t('tools.wt_profile_tag_csv_category_map', 'category_map'), catMap));
      fieldEl.set(catMap.name, catMap);

      fileRef.addEventListener('change', () => { (ts as any).file = fileRef.value; });
      delimiter.addEventListener('input', () => { (ts as any).delimiter = (delimiter.value || '').slice(0, 8); });
      nameCol.addEventListener('input', () => { (ts as any).name_col = (nameCol.value || '').trim(); });
      catCol.addEventListener('input', () => { (ts as any).category_col = (catCol.value || '').trim(); });
      catMap.addEventListener('input', () => { (ts as any).category_map = catMap.value; });
    } else if (type === 'json_list') {
      const fileRef = mkFileSelect('wt-profile-tag-jsonlist-file', 'tag_source.file', String((ts as any).file || ''));
      tagSub.appendChild(_mkFieldRow(_t('tools.wt_profile_tag_json_list_file', 'file'), fileRef));
      fieldEl.set(fileRef.name, fileRef);

      const schema = document.createElement('textarea');
      schema.id = 'wt-profile-tag-jsonlist-schema';
      schema.name = 'tag_source.schema';
      schema.rows = 6;
      schema.style.cssText = 'width:100%;font-family:ui-monospace, SFMono-Regular, Menlo, monospace;font-size:12px;';
      schema.value = typeof (ts as any).schema === 'string' ? String((ts as any).schema) : JSON.stringify((ts as any).schema ?? {}, null, 2);
      tagSub.appendChild(_mkFieldRow(_t('tools.wt_profile_tag_json_list_schema', 'schema'), schema));
      fieldEl.set(schema.name, schema);

      fileRef.addEventListener('change', () => { (ts as any).file = fileRef.value; });
      schema.addEventListener('input', () => { (ts as any).schema = schema.value; });
    } else if (type === 'json_dict') {
      const fileRef = mkFileSelect('wt-profile-tag-jsondict-file', 'tag_source.file', String((ts as any).file || ''));
      tagSub.appendChild(_mkFieldRow(_t('tools.wt_profile_tag_json_dict_file', 'file'), fileRef));
      fieldEl.set(fileRef.name, fileRef);

      const mapping = document.createElement('textarea');
      mapping.id = 'wt-profile-tag-jsondict-mapping';
      mapping.name = 'tag_source.mapping';
      mapping.rows = 8;
      mapping.style.cssText = 'width:100%;font-family:ui-monospace, SFMono-Regular, Menlo, monospace;font-size:12px;';
      mapping.value = typeof (ts as any).mapping === 'string' ? String((ts as any).mapping) : JSON.stringify((ts as any).mapping ?? {}, null, 2);
      tagSub.appendChild(_mkFieldRow(_t('tools.wt_profile_tag_json_dict_mapping', 'mapping'), mapping));
      fieldEl.set(mapping.name, mapping);

      fileRef.addEventListener('change', () => { (ts as any).file = fileRef.value; });
      mapping.addEventListener('input', () => { (ts as any).mapping = mapping.value; });
    } else {
      const comp = document.createElement('textarea');
      comp.id = 'wt-profile-tag-composite';
      comp.name = 'tag_source.sources';
      comp.rows = 10;
      comp.style.cssText = 'width:100%;font-family:ui-monospace, SFMono-Regular, Menlo, monospace;font-size:12px;';
      comp.value = typeof (ts as any).sources === 'string' ? String((ts as any).sources) : JSON.stringify((ts as any).sources ?? [], null, 2);
      tagSub.appendChild(_mkFieldRow(_t('tools.wt_profile_tag_composite_sources', 'sources'), comp));
      fieldEl.set(comp.name, comp);
      comp.addEventListener('input', () => { (ts as any).sources = comp.value; });
    }
  }
  renderTagSubform();

  // ── Threshold source (skeleton) ────────────────────
  const thrType = document.createElement('div');
  thrType.style.cssText = 'display:flex;gap:10px;flex-wrap:wrap;';
  threshSec.content.appendChild(thrType);

  const thrTypes = ['global_per_category', 'per_tag_json'] as const;
  const thrTypeName = 'threshold_source.type';
  function getThrType(): string {
    const ts = state.profile.threshold_source;
    const v = ts && typeof ts === 'object' ? String((ts as any).type || '') : '';
    return v || 'global_per_category';
  }
  function setThrType(v: string): void {
    const ts = (state.profile.threshold_source && typeof state.profile.threshold_source === 'object') ? state.profile.threshold_source : {};
    (ts as any).type = v;
    state.profile.threshold_source = ts as any;
  }
  for (const v of thrTypes) {
    const lab = document.createElement('label');
    lab.style.cssText = 'display:flex;align-items:center;gap:6px;font-size:12px;';
    const r = document.createElement('input');
    r.type = 'radio';
    r.name = thrTypeName;
    r.id = `wt-profile-thr-type-${v}`;
    r.value = v;
    r.checked = getThrType() === v;
    lab.appendChild(r);
    lab.appendChild(document.createTextNode(v));
    thrType.appendChild(lab);
    fieldEl.set(r.name + ':' + v, r);
    r.addEventListener('change', () => {
      if (!r.checked) return;
      setThrType(v);
      renderThrSubform();
    });
  }

  const thrSub = document.createElement('div');
  threshSec.content.appendChild(thrSub);

  function renderThrSubform(): void {
    _clear(thrSub);
    const type = getThrType();
    const ts = (state.profile.threshold_source && typeof state.profile.threshold_source === 'object') ? state.profile.threshold_source : {};
    state.profile.threshold_source = ts as any;

    const mkFileSelect = (id: string, name: string, value: string): HTMLSelectElement => {
      const sel = document.createElement('select');
      sel.id = id;
      sel.name = name;
      sel.style.cssText = 'width:100%;';
      const empty = document.createElement('option');
      empty.value = '';
      empty.textContent = _t('tools.wt_profile_file_select', '(select file)');
      sel.appendChild(empty);
      const files = Array.isArray(state.profile.files) ? state.profile.files : [];
      for (const f of files) {
        const fn = String(f?.name || '').trim();
        if (!fn) continue;
        const opt = document.createElement('option');
        opt.value = fn;
        opt.textContent = fn;
        sel.appendChild(opt);
      }
      sel.value = value || '';
      return sel;
    };

    if (type === 'global_per_category') {
      const thresholds = ((ts as any).thresholds && typeof (ts as any).thresholds === 'object') ? (ts as any).thresholds : {};
      (ts as any).thresholds = thresholds;

      const grid = document.createElement('div');
      grid.style.cssText = 'display:grid;grid-template-columns:repeat(2, minmax(0, 1fr));gap:10px;';
      thrSub.appendChild(grid);

      const mkNum = (key: string, labelKey: string, fallback: string, def: number): void => {
        const inp = document.createElement('input');
        inp.type = 'number';
        inp.min = '0.01';
        inp.max = '0.99';
        inp.step = '0.01';
        inp.id = `wt-profile-thr-${key}`;
        inp.name = `threshold_source.thresholds.${key}`;
        const cur = thresholds[key];
        inp.value = cur == null ? String(def) : String(cur);
        inp.style.cssText = 'width:100%;';
        grid.appendChild(_mkFieldRow(_t(labelKey, fallback), inp));
        fieldEl.set(inp.name, inp);
        inp.addEventListener('input', () => {
          const n = parseFloat(inp.value);
          if (Number.isFinite(n)) thresholds[key] = n;
        });
      };

      mkNum('general', 'tools.wt_profile_thr_general', 'general', 0.35);
      mkNum('character', 'tools.wt_profile_thr_character', 'character', 0.85);
      mkNum('copyright', 'tools.wt_profile_thr_copyright', 'copyright', 0.35);
      mkNum('artist', 'tools.wt_profile_thr_artist', 'artist', 0.35);
      mkNum('meta', 'tools.wt_profile_thr_meta', 'meta', 0.35);
    } else {
      const fileRef = mkFileSelect('wt-profile-thr-per-tag-file', 'threshold_source.file', String((ts as any).file || ''));
      thrSub.appendChild(_mkFieldRow(_t('tools.wt_profile_thr_per_tag_file', 'file'), fileRef));
      fieldEl.set(fileRef.name, fileRef);

      const fallbackMode = document.createElement('select');
      fallbackMode.id = 'wt-profile-thr-fallback-mode';
      fallbackMode.name = 'threshold_source.fallback.mode';
      fallbackMode.style.cssText = 'width:100%;';
      for (const v of ['global', 'category_default']) {
        const opt = document.createElement('option');
        opt.value = v;
        opt.textContent = v;
        fallbackMode.appendChild(opt);
      }
      fallbackMode.value = String((ts as any).fallback?.mode || 'global');
      thrSub.appendChild(_mkFieldRow(_t('tools.wt_profile_thr_fallback_mode', 'fallback.mode'), fallbackMode));
      fieldEl.set(fallbackMode.name, fallbackMode);

      const fallbackVal = document.createElement('input');
      fallbackVal.type = 'number';
      fallbackVal.min = '0.01';
      fallbackVal.max = '0.99';
      fallbackVal.step = '0.01';
      fallbackVal.id = 'wt-profile-thr-fallback-value';
      fallbackVal.name = 'threshold_source.fallback.value';
      fallbackVal.value = String((ts as any).fallback?.value ?? 0.35);
      fallbackVal.style.cssText = 'width:100%;';
      thrSub.appendChild(_mkFieldRow(_t('tools.wt_profile_thr_fallback_value', 'fallback.value'), fallbackVal));
      fieldEl.set(fallbackVal.name, fallbackVal);

      fileRef.addEventListener('change', () => { (ts as any).file = fileRef.value; });
      fallbackMode.addEventListener('change', () => {
        (ts as any).fallback = (ts as any).fallback && typeof (ts as any).fallback === 'object' ? (ts as any).fallback : {};
        (ts as any).fallback.mode = fallbackMode.value;
      });
      fallbackVal.addEventListener('input', () => {
        const n = parseFloat(fallbackVal.value);
        (ts as any).fallback = (ts as any).fallback && typeof (ts as any).fallback === 'object' ? (ts as any).fallback : {};
        if (Number.isFinite(n)) (ts as any).fallback.value = n;
      });
    }
  }
  renderThrSubform();

  // ── Preprocess & Categories ────────────────────────
  const prep = (state.profile.preprocess_spec && typeof state.profile.preprocess_spec === 'object') ? state.profile.preprocess_spec : {};
  state.profile.preprocess_spec = prep as any;

  const getArr3 = (key: string, def: number[]): number[] => {
    const v = (prep as any)[key];
    if (Array.isArray(v) && v.length === 3) return v.map((x: unknown) => Number(x) || 0);
    (prep as any)[key] = def.slice();
    return def.slice();
  };
  const mean = getArr3('mean', [0, 0, 0]);
  const std = getArr3('std', [1, 1, 1]);

  const grid1 = document.createElement('div');
  grid1.style.cssText = 'display:grid;grid-template-columns:repeat(2, minmax(0, 1fr));gap:10px;';
  prepSec.content.appendChild(grid1);

  const inputSize = document.createElement('input');
  inputSize.type = 'number';
  inputSize.id = 'wt-profile-prep-input-size';
  inputSize.name = 'preprocess_spec.input_size';
  inputSize.value = String((prep as any).input_size ?? 448);
  inputSize.min = '1';
  inputSize.step = '1';
  inputSize.style.cssText = 'width:100%;';
  grid1.appendChild(_mkFieldRow(_t('tools.wt_profile_prep_input_size', 'input_size'), inputSize));
  fieldEl.set(inputSize.name, inputSize);

  const dtype = document.createElement('select');
  dtype.id = 'wt-profile-prep-dtype';
  dtype.name = 'preprocess_spec.dtype';
  dtype.style.cssText = 'width:100%;';
  for (const v of ['float32', 'float16', 'uint8']) {
    const opt = document.createElement('option');
    opt.value = v;
    opt.textContent = v;
    dtype.appendChild(opt);
  }
  dtype.value = String((prep as any).dtype ?? 'float32');
  grid1.appendChild(_mkFieldRow(_t('tools.wt_profile_prep_dtype', 'dtype'), dtype));
  fieldEl.set(dtype.name, dtype);

  const layout = document.createElement('select');
  layout.id = 'wt-profile-prep-layout';
  layout.name = 'preprocess_spec.layout';
  layout.style.cssText = 'width:100%;';
  for (const v of ['NHWC', 'NCHW']) {
    const opt = document.createElement('option');
    opt.value = v;
    opt.textContent = v;
    layout.appendChild(opt);
  }
  layout.value = String((prep as any).layout ?? 'NHWC');
  grid1.appendChild(_mkFieldRow(_t('tools.wt_profile_prep_layout', 'layout'), layout));
  fieldEl.set(layout.name, layout);

  const chOrder = document.createElement('select');
  chOrder.id = 'wt-profile-prep-channel-order';
  chOrder.name = 'preprocess_spec.channel_order';
  chOrder.style.cssText = 'width:100%;';
  for (const v of ['RGB', 'BGR']) {
    const opt = document.createElement('option');
    opt.value = v;
    opt.textContent = v;
    chOrder.appendChild(opt);
  }
  chOrder.value = String((prep as any).channel_order ?? 'RGB');
  grid1.appendChild(_mkFieldRow(_t('tools.wt_profile_prep_channel_order', 'channel_order'), chOrder));
  fieldEl.set(chOrder.name, chOrder);

  const resize = document.createElement('select');
  resize.id = 'wt-profile-prep-resize';
  resize.name = 'preprocess_spec.resize_strategy';
  resize.style.cssText = 'width:100%;';
  for (const v of ['letterbox', 'longest_side_pad', 'stretch']) {
    const opt = document.createElement('option');
    opt.value = v;
    opt.textContent = v;
    resize.appendChild(opt);
  }
  const curResize = String((prep as any).resize_strategy ?? 'longest_side_pad');
  resize.value = curResize === 'center_crop' ? 'letterbox' : curResize;
  grid1.appendChild(_mkFieldRow(_t('tools.wt_profile_prep_resize_strategy', 'resize_strategy'), resize));
  fieldEl.set(resize.name, resize);

  const scale = document.createElement('input');
  scale.type = 'number';
  scale.id = 'wt-profile-prep-scale';
  scale.name = 'preprocess_spec.scale';
  scale.value = String((prep as any).scale ?? 1.0);
  scale.step = '0.01';
  scale.style.cssText = 'width:100%;';
  grid1.appendChild(_mkFieldRow(_t('tools.wt_profile_prep_scale', 'scale'), scale));
  fieldEl.set(scale.name, scale);

  const mkVec3 = (prefix: 'mean' | 'std', labelKey: string, values: number[]): HTMLInputElement[] => {
    const wrap = document.createElement('div');
    wrap.style.cssText = 'margin-top:10px;';
    prepSec.content.appendChild(wrap);
    const lab = document.createElement('div');
    lab.textContent = _t(labelKey, prefix);
    lab.style.cssText = 'font-size:12px;opacity:0.85;margin-bottom:4px;';
    wrap.appendChild(lab);
    const row = document.createElement('div');
    row.style.cssText = 'display:grid;grid-template-columns:repeat(3, minmax(0, 1fr));gap:10px;';
    wrap.appendChild(row);
    const out: HTMLInputElement[] = [];
    for (let i = 0; i < 3; i++) {
      const inp = document.createElement('input');
      inp.type = 'number';
      inp.step = '0.01';
      inp.id = `wt-profile-prep-${prefix}-${i}`;
      inp.name = `preprocess_spec.${prefix}.${i}`;
      inp.value = String(values[i] ?? 0);
      inp.style.cssText = 'width:100%;';
      row.appendChild(inp);
      fieldEl.set(inp.name, inp);
      out.push(inp);
    }
    return out;
  };

  const meanInputs = mkVec3('mean', 'tools.wt_profile_prep_mean', mean);
  const stdInputs = mkVec3('std', 'tools.wt_profile_prep_std', std);

  const catWrap = document.createElement('div');
  catWrap.style.cssText = 'margin-top:12px;border-top:1px solid var(--border,#ddd);padding-top:10px;';
  prepSec.content.appendChild(catWrap);

  const supportsTitle = document.createElement('div');
  supportsTitle.textContent = _t('tools.wt_profile_supports_categories', 'supports_categories');
  supportsTitle.style.cssText = 'font-size:12px;opacity:0.85;margin-bottom:6px;';
  catWrap.appendChild(supportsTitle);

  const supports = document.createElement('div');
  supports.style.cssText = 'display:flex;gap:10px;flex-wrap:wrap;';
  catWrap.appendChild(supports);

  const cats = ['general', 'character', 'copyright', 'artist', 'meta'];
  const curSupports = Array.isArray(state.profile.supports_categories) ? state.profile.supports_categories.map(String) : ['general'];
  state.profile.supports_categories = curSupports;
  for (const c of cats) {
    const lab = document.createElement('label');
    lab.style.cssText = 'display:flex;align-items:center;gap:6px;font-size:12px;';
    const chk = document.createElement('input');
    chk.type = 'checkbox';
    chk.id = `wt-profile-cat-${c}`;
    chk.name = `supports_categories.${c}`;
    chk.checked = curSupports.includes(c);
    lab.appendChild(chk);
    lab.appendChild(document.createTextNode(c));
    supports.appendChild(lab);
    fieldEl.set(chk.name, chk);
    chk.addEventListener('change', () => {
      const next = new Set(Array.isArray(state.profile.supports_categories) ? state.profile.supports_categories : []);
      if (chk.checked) next.add(c);
      else next.delete(c);
      state.profile.supports_categories = Array.from(next);
    });
  }

  const cmTitle = document.createElement('div');
  cmTitle.textContent = _t('tools.wt_profile_categories_mode', 'categories_mode');
  cmTitle.style.cssText = 'font-size:12px;opacity:0.85;margin:10px 0 6px;';
  catWrap.appendChild(cmTitle);

  const cmRow = document.createElement('div');
  cmRow.style.cssText = 'display:flex;gap:10px;flex-wrap:wrap;';
  catWrap.appendChild(cmRow);

  const cmName = 'categories_mode';
  const cmOptions = ['from_tag_source', 'all_general'];
  const rawCm = String(state.profile.categories_mode || 'from_tag_source');
  const curCm = (rawCm === 'fixed' || rawCm === 'none') ? 'all_general' : rawCm;
  state.profile.categories_mode = curCm;
  for (const v of cmOptions) {
    const lab = document.createElement('label');
    lab.style.cssText = 'display:flex;align-items:center;gap:6px;font-size:12px;';
    const r = document.createElement('input');
    r.type = 'radio';
    r.name = cmName;
    r.id = `wt-profile-cm-${v}`;
    r.value = v;
    r.checked = curCm === v;
    lab.appendChild(r);
    lab.appendChild(document.createTextNode(v));
    cmRow.appendChild(lab);
    fieldEl.set(r.name + ':' + v, r);
    r.addEventListener('change', () => {
      if (!r.checked) return;
      state.profile.categories_mode = v;
    });
  }

  inputSize.addEventListener('input', () => { (prep as any).input_size = parseInt(inputSize.value, 10) || 0; });
  dtype.addEventListener('change', () => { (prep as any).dtype = dtype.value; });
  layout.addEventListener('change', () => { (prep as any).layout = layout.value; });
  chOrder.addEventListener('change', () => { (prep as any).channel_order = chOrder.value; });
  resize.addEventListener('change', () => { (prep as any).resize_strategy = resize.value; });
  scale.addEventListener('input', () => { const n = parseFloat(scale.value); if (Number.isFinite(n)) (prep as any).scale = n; });
  for (let i = 0; i < 3; i++) {
    meanInputs[i].addEventListener('input', () => {
      const n = parseFloat(meanInputs[i].value);
      if (Number.isFinite(n)) mean[i] = n;
      (prep as any).mean = mean.slice();
    });
    stdInputs[i].addEventListener('input', () => {
      const n = parseFloat(stdInputs[i].value);
      if (Number.isFinite(n)) std[i] = n;
      (prep as any).std = std.slice();
    });
  }

  // Files list actions
  modelSec.content.addEventListener('click', (e) => {
    const el = (e.target as HTMLElement | null)?.closest('[data-action]') as HTMLElement | null;
    if (!el) return;
    if (el.dataset.action === 'add-file') {
      const cur = Array.isArray(state.profile.files) ? state.profile.files : [];
      cur.push({ name: '', required: true });
      state.profile.files = cur;
      renderFiles();
    }
    if (el.dataset.action === 'remove-file') {
      const idx = parseInt(el.dataset.index || '', 10);
      if (!Number.isFinite(idx)) return;
      const cur = Array.isArray(state.profile.files) ? state.profile.files : [];
      cur.splice(idx, 1);
      state.profile.files = cur;
      renderFiles();
    }
  });

  function isBuiltinReadOnly(): boolean {
    if (state.profile.builtin === true) return true;
    if (String((state.profile as any).origin || '') === 'builtin') return true;
    return false;
  }

  function applyReadOnlyState(): void {
    const ro = isBuiltinReadOnly();
    const disabled = ro || state.saving || state.testing;
    const inputs = container.querySelectorAll<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>('input,textarea,select');
    for (const el of Array.from(inputs)) {
      if (el === pvInput) continue; // already readonly
      el.disabled = disabled;
    }
    saveBtn.disabled = disabled;
    testBtn.disabled = disabled;
    cancelBtn.disabled = state.saving || state.testing;
    if (ro) banner.show('info', _t('tools.wt_profile_builtin_ro', 'Built-in profile (read-only)'));
  }
  applyReadOnlyState();

  function getPayload(): ProfileV2 {
    const p = _cloneProfile(state.profile);
    p.profile_version = 2;
    p.id = (p.id || '').trim();
    p.display_name = (p.display_name || '').trim();
    p.model_id = (p.model_id || '').trim();
    return p;
  }

  async function doSave(): Promise<void> {
    clearFieldErrors();
    banner.clear();
    const payload = getPayload();
    if (!_idValid(payload.id || '')) {
      banner.show('error', _t('tools.wt_profile_id_invalid', 'Invalid id'));
      return;
    }
    if (!payload.display_name || String(payload.display_name).length > 200) {
      banner.show('error', _t('tools.wt_profile_display_name_invalid', 'Invalid display name'));
      return;
    }
    if (!payload.model_id) {
      banner.show('error', _t('tools.wt_profile_model_id_required', 'model_id is required'));
      return;
    }
    // Preflight size (1MB)
    try {
      const txt = JSON.stringify(payload);
      if (txt.length > 1024 * 1024) {
        banner.show('error', _t('tools.wt_profile_too_large', 'Profile too large'));
        return;
      }
    } catch {
      banner.show('error', _t('tools.wt_profile_validation_failed', 'Validation failed'));
      return;
    }

    // builtin id collision confirmation (client-side best-effort)
    if (cb.mode !== 'edit') {
      try {
        const res = await fetch('/api/wd-tagger/profiles');
        const data = await res.json();
        const list = (data?.data?.profiles || data?.profiles || []) as any[];
        const builtinHit = Array.isArray(list) && list.some((x) => String(x?.id || '') === payload.id && (x?.builtin === true || x?.origin === 'builtin'));
        if (builtinHit) {
          const msg = _t('tools.wt_profile_override_confirm', 'A built-in profile with this id exists. Override it?');
          if (!(await customConfirm(msg))) return;
        }
      } catch { /* ignore */ }
    }

    setSaving(true);
    applyReadOnlyState();
    const origLabel = saveBtn.textContent;
    saveBtn.textContent = _t('tools.wt_profile_saving', 'Saving...');
    try {
      const isEdit = cb.mode === 'edit' && orig && orig.id;
      const path = isEdit ? `/api/wd-tagger/profiles/${encodeURIComponent(String(orig.id))}` : '/api/wd-tagger/profiles';
      const method = isEdit ? 'PUT' : 'POST';
      const { json } = await _apiJson(path, { method, headers: _csrfHeadersForUnsafe(), body: JSON.stringify(payload) });
      if (json && json.ok === false) {
        const code = String(json.code || '');
        if (code === 'validation_failed' && Array.isArray(json.errors)) {
          for (const e of json.errors) {
            const field = String(e?.field || e?.path || e?.name || '');
            const msg = String(e?.error || e?.message || '');
            if (field) markFieldError(field, msg || _t('tools.wt_profile_validation_failed', 'Validation failed'));
          }
          banner.show('error', _t('tools.wt_profile_validation_failed', 'Validation failed'));
          return;
        }
        if (code === 'id_conflict') {
          markFieldError('id', _t('tools.wt_profile_id_conflict', 'Profile with this id already exists'));
          banner.show('error', _t('tools.wt_profile_id_conflict', 'Profile with this id already exists'));
          return;
        }
        if (code === 'id_immutable') {
          banner.show('info', _t('tools.wt_profile_id_immutable', 'id is immutable. Use Duplicate + Delete to rename.'));
          return;
        }
        if (code === 'builtin_read_only') {
          banner.show('error', _t('tools.wt_profile_builtin_ro', 'Built-in profile (read-only)'));
          return;
        }
        if (code === 'not_found') {
          banner.show('error', _t('tools.wt_profile_not_found', 'Not found. Refresh the list.'));
          return;
        }
        if (code === 'profile_too_large') {
          banner.show('error', _t('tools.wt_profile_too_large', 'Profile too large'));
          return;
        }
        banner.show('error', String(json.error || _t('tools.wt_profile_save_failed', 'Save failed')));
        return;
      }
      banner.show('ok', _t('tools.wt_profile_save_ok', 'Saved'));
      cb.onSaved();
    } finally {
      saveBtn.textContent = origLabel || _t('tools.wt_profile_save', 'Save');
      setSaving(false);
      applyReadOnlyState();
    }
  }

  async function doTest(): Promise<void> {
    banner.clear();
    const id = (state.profile.id || '').trim();
    if (!id) {
      banner.show('error', _t('tools.wt_profile_id_required', 'id is required'));
      return;
    }
    setTesting(true);
    applyReadOnlyState();
    const origLabel = testBtn.textContent;
    testBtn.textContent = _t('tools.wt_profile_running', 'Running...');
    try {
      const { json } = await _apiJson(`/api/wd-tagger/profiles/${encodeURIComponent(id)}/test`, {
        method: 'POST',
        headers: _csrfHeadersForUnsafe(),
      });
      if (json && json.ok === false) {
        const code = String(json.code || '');
        if (code === 'ssrf_blocked') banner.show('error', _t('tools.wt_profile_test_ssrf', 'Blocked redirect (SSRF prevention)'));
        else if (code === 'hf_unavailable') banner.show('error', _t('tools.wt_profile_test_hf_unavailable', 'HuggingFace unavailable'));
        else if (code === 'timeout') banner.show('error', _t('tools.wt_profile_test_timeout', 'Timeout'));
        else if (code === 'required_missing') banner.show('error', _t('tools.wt_profile_test_required_missing', 'Required file missing'));
        else banner.show('error', String(json.error || _t('tools.wt_profile_test_failed', 'Test failed')));
        return;
      }
      banner.show('ok', _t('tools.wt_profile_test_ok', 'OK'));
    } finally {
      testBtn.textContent = origLabel || _t('tools.wt_profile_test', 'Test (dry-run download)');
      setTesting(false);
      applyReadOnlyState();
    }
  }

  container.addEventListener('click', (e) => {
    const el = (e.target as HTMLElement | null)?.closest('button[data-action]') as HTMLButtonElement | null;
    if (!el) return;
    if (el.dataset.action === 'save') void doSave();
    if (el.dataset.action === 'test') void doTest();
    if (el.dataset.action === 'cancel') cb.onCancel();
  });

  return { getState: () => _cloneProfile(state.profile) };
}
