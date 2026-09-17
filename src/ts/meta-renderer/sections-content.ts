/**
 * Meta-renderer prompt, tags, and sections rendering.
 * Converted from static/js/meta-renderer/sections-content.js
 */

import DOMPurify from 'dompurify';

import { getPromptHighlightApi } from '../shared/browser-apis';
import { esc, escAttr, sectionOpen, sectionClose } from './utils';

interface RenderOpts {
  showCopyButtons?: boolean;
  showConvertButtons?: boolean;
  maxPromptLen?: number;
  showTagSearch?: boolean;
  showSimulatorLink?: boolean;
  /** Window namespace for convertAndCopy/convertAndShow (default: 'runtimeToolsApi') */
  convertApiNs?: string;
}

interface TagItem {
  tag: string;
  namespace?: string;
  ns?: string;
  source?: string;
}

interface TagRenderOpts extends RenderOpts {
  fileId?: number | undefined;
}

interface SectionItem {
  title: string;
  content: unknown;
  display_type: string;
  copyable?: boolean;
}

function _tr(key: string, fallback: string): string {
  return typeof window.tr === 'function' ? window.tr(key, fallback) : fallback;
}

export function renderPrompt(text: string, type: string, opts?: RenderOpts): string {
  if (!text) return '';
  const isNeg = type === 'negative';
  const label = isNeg
    ? _tr('inspect.negative', 'Negative Prompt')
    : _tr('inspect.positive', 'Positive Prompt');
  const showCopy = !opts || opts.showCopyButtons !== false;
  const showConvert = opts && opts.showConvertButtons !== false;
  const maxLen = (opts && opts.maxPromptLen) || 0;
  let displayText = text;
  if (maxLen > 0 && text.length > maxLen) displayText = text.substring(0, maxLen) + '...';

  const textId = isNeg ? 'negativeText' : 'positiveText';
  const icon = isNeg ? '\uD83D\uDEAB' : '\u270F\uFE0F';
  let html = sectionOpen(icon, label);
  const highlighted = getPromptHighlightApi().highlightPrompt(displayText) || esc(displayText);
  html += '<div class="prompt-text" id="' + textId + '">' + highlighted + '</div>';

  if (showCopy || showConvert) {
    html += '<div class="meta-prompt-actions">';
    if (showCopy) {
      const b64 = btoa(unescape(encodeURIComponent(text)));
      const copyLabel = isNeg ? (_tr('meta.negative_label', 'Negative') + ' ') : (_tr('meta.positive_label', 'Positive') + ' ');
      html += '<button class="btn-small copy-target" type="button" data-copy-b64="' + b64 + '" data-copy-label="' + copyLabel + '" style="position:relative;">' + _tr('meta.copy_original', 'Copy') + '</button>';
    }
    if (showConvert) {
      const t = isNeg ? 'negative' : 'positive';
      html += '<button class="btn-small" type="button" data-action-scope="detail-modal" data-action="convertAndCopy" data-action-arg="' + t + ':nai_to_sd">' + _tr('convert.label.sd', 'Copy (SD)') + '</button>';
      html += '<button class="btn-small" type="button" data-action-scope="detail-modal" data-action="convertAndCopy" data-action-arg="' + t + ':sd_to_nai">' + _tr('convert.label.nai', 'Copy (NAI)') + '</button>';
    }
    if (opts && opts.showSimulatorLink && typeof window.inspectPageApi?.openInSimulator === 'function') {
      const t = isNeg ? 'negative' : 'positive';
      html += '<button class="btn-small meta-btn-simulator" type="button" data-action="inspectPageApi.openInSimulator" data-action-arg="' + t + '">\uD83E\uDDEA Simulator</button>';
    }
    if (!isNeg) {
      const b64q = btoa(unescape(encodeURIComponent(text.substring(0, 200))));
      html += '<button class="btn-small meta-btn-search-prompt" type="button" data-action-scope="detail-modal" data-action="searchByPrompt" data-action-arg="' + b64q + '">\uD83D\uDD0E ' + _tr('detail.search_by_prompt', 'Search by Prompt') + '</button>';
    }
    html += '</div>';
  }
  html += sectionClose();
  return html;
}

export function renderTags(tags: TagItem[], opts?: TagRenderOpts): string {
  if ((!tags || tags.length === 0) && !(opts && opts.fileId)) return '';
  const clickable = !opts || opts.showTagSearch !== false;
  const fileId = opts?.fileId || 0;
  const metaTags = (tags || []).filter(t => t.source !== 'user');
  const userTags = (tags || []).filter(t => t.source === 'user');
  const totalCount = (tags || []).length;

  let html = sectionOpen('\uD83C\uDFF7\uFE0F', 'Tags', '(' + totalCount + ')');

  // Meta tags (read-only, clickable for search)
  if (metaTags.length > 0) {
    const grouped: Record<string, TagItem[]> = {};
    metaTags.forEach((t) => {
      const ns = t.namespace || t.ns || 'general';
      if (!grouped[ns]) grouped[ns] = [];
      grouped[ns].push(t);
    });
    const nsKeys = Object.keys(grouped);
    nsKeys.forEach((ns) => {
      const tagList = grouped[ns];
      if (nsKeys.length > 1) html += '<div class="meta-ns-header"><span class="meta-ns-label">' + esc(ns) + '</span></div>';
      html += '<div class="meta-tag-list">';
      tagList.forEach((t) => {
        const tag = t.tag;
        const searchTag = t.namespace ? t.namespace + ':' + tag : tag;
        if (clickable) html += '<span class="tag-chip" style="cursor:pointer;" data-action="detailModalApi.searchByTag" data-action-arg="' + escAttr(searchTag) + '">' + esc(tag) + '</span>';
        else html += '<span class="tag-chip">' + esc(tag) + '</span>';
      });
      html += '</div>';
    });
  }

  // User tags (removable)
  if (userTags.length > 0 || fileId) {
    html += '<div class="meta-ns-header"><span class="meta-ns-label">' + _tr('tags.user_section', 'User Tags') + '</span></div>';
    html += '<div class="meta-tag-list">';
    userTags.forEach((t) => {
      const tag = t.tag;
      const safeTag = esc(tag).replace(/\\/g, '\\\\').replace(/'/g, "\\'");
      html += '<span class="tag-chip-user">';
      if (clickable) {
        html += '<span style="cursor:pointer;" data-action="detailModalApi.searchByTag" data-action-arg="' + escAttr(tag) + '">' + esc(tag) + '</span>';
      } else {
        html += '<span>' + esc(tag) + '</span>';
      }
      if (fileId) {
        html += '<button class="tag-chip-remove" type="button" data-action-scope="detail-modal" data-action="removeUserTag" data-action-arg="' + escAttr(String(fileId)) + ':' + escAttr(tag) + '" title="Remove">&times;</button>';
      }
      html += '</span>';
    });

    // Inline add input
    if (fileId) {
      html += '<span class="tag-add-inline">';
      html += '<input type="text" id="tagAddInput" name="tagAddInput" placeholder="' + _tr('tags.add_placeholder', 'Add tag...') + '" aria-label="' + _tr('tags.add_placeholder', 'Add tag...') + '" data-action-scope="detail-modal" data-action="handleTagInputKey" data-action-event="keydown" data-action-arg="' + escAttr(String(fileId)) + '" data-tag-suggest="1" autocomplete="off">';
      html += '<button class="tag-add-btn" type="button" data-action-scope="detail-modal" data-action="addUserTag" data-action-arg="' + escAttr(String(fileId)) + '" title="Add" aria-label="' + _tr('tags.add_tag', 'Add tag') + '">+</button>';
      html += '</span>';
    }
    html += '</div>';
  }

  html += sectionClose();
  return html;
}

/** Standalone re-render helper for tag-edit module refresh. */
export function renderTagsSection(tags: TagItem[], fileId: number): string {
  return renderTags(tags, { showTagSearch: true, fileId });
}

export function renderSections(sections: SectionItem[]): string {
  if (!sections || sections.length === 0) return '';
  let html = '';
  sections.forEach((sec) => {
    html += sectionOpen('\uD83D\uDD27', sec.title);
    if (sec.display_type === 'json' && sec.content) {
      const jsonText = typeof sec.content === 'string'
        ? sec.content
        : JSON.stringify(sec.content, null, 2);
      html += '<pre class="meta-json-block">' + esc(jsonText) + '</pre>';
      if (sec.copyable) {
        const b64 = btoa(unescape(encodeURIComponent(jsonText)));
        html += '<div class="meta-section-actions">';
        html += '<button class="btn-small copy-target" type="button"'
          + ' data-copy-b64="' + b64 + '"'
          + ' data-copy-label="' + escAttr(sec.title) + ' "'
          + ' style="position:relative;">'
          + _tr('meta.copy_original', 'Copy')
          + '</button>';
        html += '<button class="btn-small" type="button"'
          + ' data-download-json-b64="' + b64 + '"'
          + ' data-download-filename="workflow.json">'
          + '⬇ ' + _tr('meta.download_json', 'Download')
          + '</button>';
        html += '</div>';
      }
    } else if (sec.display_type === 'table' && Array.isArray(sec.content)) {
      html += '<table class="meta-table">';
      sec.content.forEach((row: Record<string, unknown>) => {
        html += '<tr>';
        Object.entries(row).forEach((e) => {
          html += '<td><span class="meta-table-key">' + esc(e[0]) + ':</span> ' + esc(String(e[1])) + '</td>';
        });
        html += '</tr>';
      });
      html += '</table>';
    } else if (sec.display_type === 'list' && Array.isArray(sec.content)) {
      sec.content.forEach((item: unknown) => {
        if (item && typeof item === 'object' && !Array.isArray(item)) {
          const obj = item as Record<string, unknown>;
          if (obj.label && obj.prompt) {
            html += '<div class="meta-list-item"><span class="meta-list-label">' + esc(String(obj.label)) + '</span> ' + esc(String(obj.prompt)) + '</div>';
          } else {
            html += '<div class="meta-list-item">' + Object.entries(obj).map(([k, v]) => esc(k) + ': ' + esc(String(v))).join(', ') + '</div>';
          }
        } else {
          html += '<div class="meta-list-item">' + esc(String(item)) + '</div>';
        }
      });
    } else if (sec.display_type === 'html' && sec.content) {
      // Sanitize with DOMPurify to prevent XSS (strips scripts, iframes, event handlers, etc.)
      const raw = String(sec.content);
      const sanitized = typeof DOMPurify !== 'undefined'
        ? DOMPurify.sanitize(raw, { ALLOWED_TAGS: ['b', 'i', 'em', 'strong', 'a', 'br', 'p', 'span', 'div', 'ul', 'ol', 'li', 'code', 'pre', 'h1', 'h2', 'h3', 'h4', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'img', 'hr', 'blockquote', 'dl', 'dt', 'dd', 'sup', 'sub', 'mark'], ALLOWED_ATTR: ['href', 'src', 'alt', 'title', 'class', 'style', 'target', 'rel', 'width', 'height'] })
        : esc(raw);
      html += sanitized;
    } else {
      html += '<div class="meta-section-text">' + esc(String(sec.content || '')) + '</div>';
    }
    html += sectionClose();
  });
  return html;
}
