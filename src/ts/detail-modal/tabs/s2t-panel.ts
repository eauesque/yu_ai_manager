/**
 * s2t-panel.ts — S2T (Speech-to-Text) tab: video/audio transcription
 *
 * Provides transcription functionality as the 4th tab in the modal.
 * Displays existing transcription results automatically, or allows the user to run transcription via the button.
 */

interface S2tSegment {
  text: string;
  start: number;
  end: number;
}
import { getAppApi, getNavApi } from '../../shared/browser-apis';
import { copyToClipboard } from '../../shared/clipboard';

function _tr(key: string, fb: string): string {
  return getAppApi().tr(key, fb) || fb;
}

function _fmtTime(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

/* -- HTML generation -- */

export function renderS2tTabContent(fileId: number): string {
  let html = '<div class="s2t-panel">';

  // Action bar
  html += '<div class="s2t-actions">';
  html += `<select id="s2tLang-${fileId}" class="input-sm">`;
  html += '<option value="ja">日本語</option>';
  html += '<option value="en">English</option>';
  html += '<option value="zh">中文</option>';
  html += '<option value="ko">한국어</option>';
  html += '<option value="">Auto</option>';
  html += '</select>';
  html += `<button type="button" id="s2tRunBtn-${fileId}" class="btn-small s2t-btn-run">`;
  html += '\uD83C\uDFA4 ' + _tr('detail.s2t_transcribe', 'Transcribe');
  html += '</button>';
  html += `<span id="s2tStatus-${fileId}" class="meta-status"></span>`;
  html += '</div>';

  // Results display area
  html += `<div id="s2tResult-${fileId}" class="s2t-result" style="display:none;">`;
  html += `<div class="s2t-result-header">`;
  html += `<span id="s2tBackend-${fileId}" class="s2t-backend-badge"></span>`;
  html += `<button type="button" id="s2tCopyBtn-${fileId}" class="btn-small s2t-btn-copy" title="Copy">\uD83D\uDCCB</button>`;
  html += '</div>';
  html += `<div id="s2tText-${fileId}" class="s2t-text"></div>`;
  html += `<details id="s2tSegments-${fileId}" class="s2t-segments">`;
  html += `<summary>${_tr('detail.s2t_segments', 'Segments')}</summary>`;
  html += `<div id="s2tSegmentList-${fileId}" class="s2t-segment-list"></div>`;
  html += '</details>';
  html += '</div>';

  // Placeholder when not yet executed
  html += `<div id="s2tEmpty-${fileId}" class="s2t-empty">`;
  html += `<p>${_tr('detail.s2t_no_transcript', 'No transcript yet. Click "Transcribe" to start.')}</p>`;
  html += '</div>';

  html += '</div>';
  return html;
}

/* -- Initialization -- */

export function initS2tTab(fileId: number): void {
  _bindRunBtn(fileId);
  _bindCopyBtn(fileId);
  _loadExistingTranscript(fileId);
}

function _bindRunBtn(fileId: number): void {
  const btn = document.getElementById(`s2tRunBtn-${fileId}`);
  if (!btn) return;
  btn.addEventListener('click', () => _runTranscribe(fileId));
}

function _bindCopyBtn(fileId: number): void {
  const btn = document.getElementById(`s2tCopyBtn-${fileId}`);
  if (!btn) return;
  btn.addEventListener('click', () => {
    const textEl = document.getElementById(`s2tText-${fileId}`);
    if (!textEl) return;
    void copyToClipboard(textEl.textContent || '').then(() => {
      getNavApi().showToast(_tr('detail.s2t_copied', 'Copied to clipboard'));
    });
  });
}

/* -- Load existing results -- */

async function _loadExistingTranscript(fileId: number): Promise<void> {
  try {
    const resp = await getAppApi().apiFetch(`/ext/speech-to-text/api/s2t/transcript/${fileId}`);
    if (!resp.ok) return;
    const json = await resp.json();
    if (json.status === 'ok' && json.text) {
      _showResult(fileId, json.text, json.segments || [], json.backend || '');
      _showS2tBadge();
    }
  } catch {
    // No results — do nothing
  }
}

/* -- Transcription execution -- */

async function _runTranscribe(fileId: number): Promise<void> {
  const btn = document.getElementById(`s2tRunBtn-${fileId}`) as HTMLButtonElement | null;
  const status = document.getElementById(`s2tStatus-${fileId}`);
  const langSel = document.getElementById(`s2tLang-${fileId}`) as HTMLSelectElement | null;
  const lang = langSel?.value || '';

  if (btn) btn.disabled = true;
  if (status) {
    status.textContent = _tr('detail.s2t_processing', 'Processing...');
    status.classList.add('meta-status-loading');
  }

  try {
    const resp = await getAppApi().apiFetch('/ext/speech-to-text/api/s2t/transcribe-video', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_id: fileId, language: lang }),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ error: resp.statusText }));
      throw new Error(err.error || err.detail || `HTTP ${resp.status}`);
    }

    const json = await resp.json();
    if (status) {
      status.textContent = '';
      status.classList.remove('meta-status-loading');
    }

    _showResult(fileId, json.text || '', json.segments || [], json.backend || '');
    _showS2tBadge();
    getNavApi().showToast(_tr('detail.s2t_done', 'Transcription complete'));
  } catch (e) {
    if (status) {
      status.textContent = (e as Error).message;
      status.classList.remove('meta-status-loading');
      status.classList.add('meta-status-error');
    }
    getNavApi().showToast(_tr('detail.s2t_error', 'Transcription failed'), true);
  } finally {
    if (btn) btn.disabled = false;
  }
}

/* -- Results display -- */

function _showResult(fileId: number, text: string, segments: S2tSegment[], backend: string): void {
  const resultEl = document.getElementById(`s2tResult-${fileId}`);
  const emptyEl = document.getElementById(`s2tEmpty-${fileId}`);
  const textEl = document.getElementById(`s2tText-${fileId}`);
  const backendEl = document.getElementById(`s2tBackend-${fileId}`);
  const segListEl = document.getElementById(`s2tSegmentList-${fileId}`);

  if (emptyEl) emptyEl.style.display = 'none';
  if (resultEl) resultEl.style.display = '';
  if (textEl) textEl.textContent = text;
  if (backendEl && backend) {
    backendEl.textContent = backend;
    backendEl.style.display = '';
  }

  if (segListEl && segments.length > 0) {
    segListEl.innerHTML = segments.map(seg =>
      `<div class="s2t-seg-row"><span class="s2t-seg-time">[${_fmtTime(seg.start)} - ${_fmtTime(seg.end)}]</span> <span class="s2t-seg-text">${_escHtml(seg.text)}</span></div>`
    ).join('');
  }
}

function _escHtml(s: string): string {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

/* -- Badge display -- */

function _showS2tBadge(): void {
  const badge = document.querySelector('.mi-tab-badge-s2t') as HTMLElement | null;
  if (badge) {
    badge.textContent = '\u2713';
    badge.style.display = '';
  }
}
