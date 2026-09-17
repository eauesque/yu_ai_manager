/**
 * WD-Tagger tag display and XMP viewer for the detail modal.
 *
 * Loads WD tags from the API after modal opens and renders them
 * into the #wdTagsContainer placeholder.
 */

import { showAiTabBadge } from '../../detail-modal/tabs/modal-tabs';
import { getAppApi, getNavApi } from '../../shared/browser-apis';

const { tr } = getAppApi();
const { showToast } = getNavApi();

const CATEGORY_CLASS: Record<string, string> = {
  general: 'wt-tag-general',
  character: 'wt-tag-character',
  copyright: 'wt-tag-copyright',
  rating: 'wt-tag-rating',
};
const SHOW_ALL_MODELS_STORAGE_KEY = 'wdTagsShowAllModels';

function _esc(text: string): string {
  const d = document.createElement('div');
  d.textContent = text;
  return d.innerHTML;
}

function _escAttr(text: string): string {
  return _esc(text).replace(/"/g, '&quot;');
}

function _t(key: string, fallback: string): string {
  return tr(key, fallback);
}

interface WdTag {
  tag_name: string;
  confidence: number;
  category: string;
  model: string;
}

function _showAllModelsEnabled(): boolean {
  try {
    return localStorage.getItem(SHOW_ALL_MODELS_STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

function _setShowAllModelsEnabled(enabled: boolean): void {
  try {
    localStorage.setItem(SHOW_ALL_MODELS_STORAGE_KEY, enabled ? '1' : '0');
  } catch { /* ignore */ }
}

function _modelLabel(model: string): string {
  const normalized = model || _t('tools.wt_active_model_none', '(none)');
  const parts = normalized.split('/');
  return parts[parts.length - 1] || normalized;
}

function _groupTags(tags: WdTag[], keyFn: (tag: WdTag) => string): Record<string, WdTag[]> {
  const grouped: Record<string, WdTag[]> = {};
  for (const tag of tags) {
    const key = keyFn(tag);
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(tag);
  }
  return grouped;
}

function _renderHeader(tagsCount: number, showAllModels: boolean): string {
  return [
    '<div class="wt-tags-header">',
    '<h3>\uD83C\uDFF7\uFE0F WD Tags <span style="font-size:12px;color:#666;font-weight:normal;">(',
    String(tagsCount),
    ')</span></h3>',
    '<label class="wt-model-toggle">',
    '<input type="checkbox" id="wdTagsShowAllModelsToggle"',
    showAllModels ? ' checked' : '',
    '>',
    '<span>',
    _esc(_t('tools.wt_show_all_models', 'Show all models')),
    '</span>',
    '</label>',
    '</div>',
  ].join('');
}

function _renderTagList(tags: WdTag[], showConfidence: boolean): string {
  let html = '<div class="wt-tag-list">';
  for (const t of tags) {
    const cls = CATEGORY_CLASS[t.category] || 'wt-tag-general';
    const pct = (t.confidence * 100).toFixed(1);
    html += '<span class="wt-tag ' + cls + '" title="' + pct + '%" style="cursor:pointer;" data-action="detailModalApi.searchByTag" data-action-arg="' + _escAttr(t.tag_name) + '">';
    html += _esc(t.tag_name);
    if (showConfidence) {
      html += ' <span class="wt-tag-confidence">' + _esc(pct) + '%</span>';
    }
    html += '</span>';
  }
  html += '</div>';
  return html;
}

function _renderTagsByCategory(tags: WdTag[], showConfidence: boolean): string {
  const grouped = _groupTags(tags, (tag) => tag.category || 'general');
  const multipleCategories = Object.keys(grouped).length > 1;
  const order = ['general', 'character', 'copyright', 'rating'];
  let html = '';

  for (const cat of [...order, ...Object.keys(grouped).filter((cat) => !order.includes(cat)).sort()]) {
    const catTags = grouped[cat];
    if (!catTags || catTags.length === 0) continue;

    if (multipleCategories) {
      html += '<div style="margin-top:4px;margin-bottom:2px;font-size:11px;color:#888;">' + _esc(cat) + '</div>';
    }
    html += _renderTagList(catTags, showConfidence);
  }

  return html;
}

function _renderWdTags(tags: WdTag[], showAllModels: boolean): string {
  let html = '<div class="meta-section">';
  html += _renderHeader(tags.length, showAllModels);

  if (showAllModels) {
    const byModel = _groupTags(tags, (tag) => tag.model || '');
    for (const model of Object.keys(byModel).sort()) {
      const modelTags = byModel[model];
      html += '<div class="wt-model-group">';
      html += '<div class="wt-model-group-header">';
      html += '<span class="wt-model-label">' + _esc(_t('tools.wt_model_label', 'Model')) + '</span>';
      html += '<span class="wt-model-badge" title="' + _escAttr(model) + '">' + _esc(_modelLabel(model)) + '</span>';
      html += '<span class="wt-model-count">' + String(modelTags.length) + '</span>';
      html += '</div>';
      html += _renderTagsByCategory(modelTags, true);
      html += '</div>';
    }
  } else {
    html += _renderTagsByCategory(tags, false);
  }

  html += '</div>';
  return html;
}

function _bindShowAllToggle(fileId: number): void {
  const toggle = document.getElementById('wdTagsShowAllModelsToggle') as HTMLInputElement | null;
  if (!toggle) return;
  toggle.addEventListener('change', () => {
    _setShowAllModelsEnabled(toggle.checked);
    void loadWdTags(fileId);
  });
}

/**
 * Load and render WD tags for a file into the modal placeholder.
 */
export async function loadWdTags(fileId: number): Promise<void> {
  const container = document.getElementById('wdTagsContainer');
  if (!container) return;
  const showAllModels = _showAllModelsEnabled();

  try {
    const suffix = showAllModels ? '?all=1' : '';
    const res = await fetch(`/api/wd-tagger/tags/${fileId}${suffix}`);
    // On 429, silently give up -- retrying would worsen the rate-limit storm
    if (res.status === 429) return;
    const data = await res.json();
    const tags: WdTag[] = data.tags || data.data?.tags || [];

    if (tags.length === 0) {
      container.innerHTML = '';
      container.style.display = 'none';
      return;
    }

    container.style.display = '';
    showAiTabBadge();

    container.innerHTML = _renderWdTags(tags, showAllModels);
    _bindShowAllToggle(fileId);
  } catch {
    container.innerHTML = '';
    container.style.display = 'none';
  }
}


/**
 * View XMP metadata for a file in a modal overlay.
 */
export async function viewXmpModal(fileId: number): Promise<void> {
  try {
    const res = await fetch(`/api/wd-tagger/xmp/${fileId}`);
    const data = await res.json();
    const xmp = data.xmp || data.data?.xmp;
    if (!xmp) {
      showToast(_t('tools.wt_xmp_not_found', 'No XMP data found'), true);
      return;
    }

    const modal = document.createElement('div');
    modal.className = 'wt-xmp-modal-overlay';
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });

    const content = document.createElement('div');
    content.className = 'wt-xmp-modal';

    let html = '<h3 style="margin:0 0 12px;font-size:15px;">' + _esc(_t('tools.wt_xmp_title', 'XMP Metadata')) + '</h3>';

    if (xmp.dc_subject && xmp.dc_subject.length > 0) {
      html += '<div style="margin-bottom:10px;"><strong>' + _esc(_t('tools.wt_xmp_dc_subject', 'dc:subject tags:')) + '</strong><div class="wt-tag-list" style="margin-top:4px;">';
      for (const tag of xmp.dc_subject) {
        html += '<span class="wt-tag wt-tag-general">' + _esc(tag) + '</span>';
      }
      html += '</div></div>';
    }

    if (xmp.wdtag && Object.keys(xmp.wdtag).length > 0) {
      html += '<div style="margin-bottom:10px;"><strong>' + _esc(_t('tools.wt_xmp_wdtag_info', 'wdtag info:')) + '</strong><ul style="margin:4px 0;padding-left:20px;font-size:12px;">';
      for (const [k, v] of Object.entries(xmp.wdtag)) {
        html += '<li>' + _esc(k) + ': ' + _esc(String(v)) + '</li>';
      }
      html += '</ul></div>';
    }

    if (xmp.raw_xml) {
      html += '<details style="margin-top:10px;"><summary style="cursor:pointer;font-size:12px;">' + _esc(_t('tools.wt_xmp_raw_xml', 'Raw XML')) + '</summary>';
      html += '<pre style="max-height:300px;overflow:auto;font-size:11px;background:rgba(0,0,0,0.2);padding:8px;border-radius:6px;white-space:pre-wrap;">' + _esc(xmp.raw_xml) + '</pre>';
      html += '</details>';
    }

    html += '<button class="btn btn-secondary wt-xmp-close" style="margin-top:12px;">' + _esc(_t('tools.wt_close', 'Close')) + '</button>';
    content.innerHTML = html;
    content.querySelector('.wt-xmp-close')?.addEventListener('click', () => modal.remove());
    modal.appendChild(content);
    document.body.appendChild(modal);
  } catch {
    showToast(_t('tools.wt_xmp_load_failed', 'Failed to load XMP data'), true);
  }
}
