/**
 * annotations-panel.ts — Notes tab: show and manage file annotations.
 *
 * Shows all annotations for the current file (from any source, read-only
 * for non-user sources). Users can add/edit/delete their own notes
 * (source="user", key="note").
 */

import { getAppApi } from '../../shared/browser-apis';
import { customConfirm } from '../../shared/dialog';

function _tr(key: string, fb: string): string {
  return getAppApi().tr(key, fb) || fb;
}

function _fmtDate(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/* -- HTML generation (panel shell only — content populated via DOM) -- */

export function renderAnnotationsTabContent(fileId: number): string {
  const loadingText = getAppApi().escapeHtml(_tr('common.loading', 'Loading...'));
  const placeholderText = getAppApi().escapeHtml(_tr('detail.ann_placeholder', 'Add a personal note for this file...'));
  const addLabel = getAppApi().escapeHtml(_tr('detail.ann_add_label', 'Add note'));
  const saveLabel = getAppApi().escapeHtml(_tr('common.save', 'Save'));

  return `<div class="ann-panel" id="annPanel-${fileId}">
  <div id="annList-${fileId}" class="ann-list"><div class="ann-loading">${loadingText}</div></div>
  <div class="ann-add-form">
    <div class="ann-add-label">${addLabel}</div>
    <textarea id="annInput-${fileId}" class="ann-textarea" rows="3" placeholder="${placeholderText}"></textarea>
    <div style="display:flex;gap:8px;margin-top:6px;">
      <button type="button" id="annSaveBtn-${fileId}" class="btn-small ann-btn-save">${saveLabel}</button>
      <span id="annStatus-${fileId}" class="meta-status"></span>
    </div>
  </div>
</div>`;
}

/* -- Types -- */

interface Annotation {
  id: number;
  file_id: number;
  source: string;
  key: string;
  value: string;
  confidence: number | null;
  created_at: number;
}

/* -- Render annotation list using DOM methods (no innerHTML with user data) -- */

function _renderList(fileId: number, annotations: Annotation[]): void {
  const container = document.getElementById(`annList-${fileId}`);
  if (!container) return;

  while (container.firstChild) container.removeChild(container.firstChild);

  if (annotations.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'ann-empty';
    empty.textContent = _tr('detail.ann_empty', 'No annotations yet.');
    container.appendChild(empty);
    return;
  }

  // Group by source
  const bySource = new Map<string, Annotation[]>();
  for (const ann of annotations) {
    const list = bySource.get(ann.source) || [];
    list.push(ann);
    bySource.set(ann.source, list);
  }

  for (const [source, items] of bySource) {
    const isUser = source === 'user';
    const group = document.createElement('div');
    group.className = 'ann-source-group';

    const label = document.createElement('div');
    label.className = 'ann-source-label';
    label.textContent = isUser ? _tr('detail.ann_source_user', 'Your notes') : source;
    group.appendChild(label);

    for (const ann of items) {
      const item = document.createElement('div');
      item.className = 'ann-item';
      item.dataset.annSource = ann.source;
      item.dataset.annKey = ann.key;

      const body = document.createElement('div');
      body.className = 'ann-item-body';

      if (ann.key !== 'note') {
        const badge = document.createElement('span');
        badge.className = 'ann-key-badge';
        badge.textContent = ann.key;
        body.appendChild(badge);
        body.appendChild(document.createTextNode(' '));
      }

      const valueEl = document.createElement('span');
      valueEl.className = 'ann-value';
      valueEl.textContent = ann.value;
      body.appendChild(valueEl);
      item.appendChild(body);

      const meta = document.createElement('div');
      meta.className = 'ann-item-meta';

      const dateEl = document.createElement('span');
      dateEl.className = 'ann-date';
      dateEl.textContent = _fmtDate(ann.created_at);
      meta.appendChild(dateEl);

      if (ann.confidence !== null && ann.confidence !== undefined) {
        const conf = document.createElement('span');
        conf.className = 'ann-conf';
        conf.textContent = ' ' + Math.round(ann.confidence * 100) + '%';
        meta.appendChild(conf);
      }

      if (isUser) {
        const delBtn = document.createElement('button');
        delBtn.type = 'button';
        delBtn.className = 'ann-btn-delete';
        delBtn.dataset.annSource = ann.source;
        delBtn.dataset.annKey = ann.key;
        delBtn.dataset.fileId = String(fileId);
        delBtn.title = _tr('common.delete', 'Delete');
        delBtn.textContent = '\u2715';
        delBtn.addEventListener('click', () => _deleteAnnotation(fileId, ann.source, ann.key));
        meta.appendChild(delBtn);
      }

      item.appendChild(meta);
      group.appendChild(item);
    }

    container.appendChild(group);
  }
}

/* -- Initialization -- */

export function initAnnotationsTab(fileId: number): void {
  _loadAnnotations(fileId);
  _bindSaveBtn(fileId);
}

async function _loadAnnotations(fileId: number): Promise<void> {
  const container = document.getElementById(`annList-${fileId}`);
  if (!container) return;

  try {
    const res = await fetch(`/api/annotations/${fileId}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const annotations: Annotation[] = data.annotations || [];

    // Populate textarea with existing user note if any
    const userNote = annotations.find(a => a.source === 'user' && a.key === 'note');
    const textarea = document.getElementById(`annInput-${fileId}`) as HTMLTextAreaElement | null;
    if (textarea && userNote) {
      textarea.value = userNote.value;
    }

    _renderList(fileId, annotations);
  } catch (e) {
    if (container) {
      while (container.firstChild) container.removeChild(container.firstChild);
      const err = document.createElement('div');
      err.className = 'ann-empty ann-error';
      err.textContent = _tr('detail.ann_load_failed', 'Failed to load annotations.');
      container.appendChild(err);
    }
    console.error('[annotations] load error:', e);
  }
}

function _bindSaveBtn(fileId: number): void {
  const btn = document.getElementById(`annSaveBtn-${fileId}`);
  if (!btn) return;
  btn.addEventListener('click', () => _saveNote(fileId));
}

async function _saveNote(fileId: number): Promise<void> {
  const textarea = document.getElementById(`annInput-${fileId}`) as HTMLTextAreaElement | null;
  const statusEl = document.getElementById(`annStatus-${fileId}`);
  const value = (textarea?.value || '').trim();
  if (!value) return;

  if (statusEl) statusEl.textContent = _tr('common.saving', 'Saving...');

  try {
    const res = await fetch('/api/annotations/batch-set', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        items: [{ file_id: fileId, source: 'user', key: 'note', value }],
      }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    if (statusEl) {
      statusEl.textContent = '\u2705 ' + _tr('common.saved', 'Saved');
      setTimeout(() => { if (statusEl) statusEl.textContent = ''; }, 2000);
    }
    await _loadAnnotations(fileId);
  } catch (e) {
    if (statusEl) statusEl.textContent = '\u274C ' + _tr('detail.ann_save_failed', 'Save failed');
    console.error('[annotations] save error:', e);
  }
}

async function _deleteAnnotation(fileId: number, source: string, key: string): Promise<void> {
  if (!await customConfirm(_tr('detail.ann_delete_confirm', 'Delete this annotation?'), { danger: true })) return;

  try {
    const res = await fetch('/api/annotations/batch-delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source, file_ids: [fileId], key }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    await _loadAnnotations(fileId);
  } catch (e) {
    console.error('[annotations] delete error:', e);
  }
}
