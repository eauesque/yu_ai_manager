/**
 * tools/qr-core.ts — QR code payload builder and renderer.
 * Converted from runtime-tools-qr-core.js
 */

import { getAppApi } from '../../shared/browser-apis';

const { escapeHtml, tr } = getAppApi();

export interface QrPayloadResult {
  ok: boolean;
  qrText: string;
  /**
   * If set, the copy button should copy this text instead of qrText.
   * Used when a compact fallback QR is shown but the user wants the original text.
   */
  copyText?: string;
  infoText: string;
  /** Diagnostic detail shown in the info line when ok=false. */
  diagText?: string;
  /** Orange warning note shown below the QR when a compact fallback was applied. */
  fallbackNote?: string;
}

/** Returns the UTF-8 byte length of a string. Used for QR capacity checks. */
function _byteLength(s: string): number {
  return new TextEncoder().encode(s).length;
}

/** QR Version 40 / Byte mode maximum: 2953 bytes. */
const QR_MAX_BYTES = 2953;
/** Warn threshold before hitting the hard limit. */
const QR_WARN_BYTES = 2500;

/**
 * Level 1 compact: strips large / redundant fields to keep the
 * payload small enough for QR encoding. Retains p/n for prompt data.
 */
function _compactMeta(shareData: Record<string, unknown>): string {
  const compact: Record<string, unknown> = {};
  const KEEP_KEYS = ['p', 'n', 'seed', 'steps', 'cfg', 'sampler', 'model', 'size', 'id'];
  for (const k of KEEP_KEYS) {
    if (k in shareData) compact[k] = shareData[k];
  }
  return JSON.stringify(compact);
}

/**
 * Level 2 compact: reproduction parameters only — no p/n.
 * Used as last-resort fallback when even Level 1 doesn't fit.
 */
function _compactMetaLevel2(shareData: Record<string, unknown>): string {
  const compact: Record<string, unknown> = {};
  const KEEP_KEYS = ['seed', 'steps', 'cfg', 'sampler', 'model', 'size', 'id'];
  for (const k of KEEP_KEYS) {
    if (k in shareData) compact[k] = shareData[k];
  }
  return JSON.stringify(compact);
}

export function buildQrPayload(
  mode: string,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  shareData: Record<string, any>,
): QrPayloadResult {
  let qrText = '';
  let infoText = '';

  switch (mode) {
    case 'positive':
      qrText = shareData.p || shareData.prompt || shareData.raw_prompt || '';
      infoText = tr('qr.info.positive_len', { count: qrText.length });
      break;
    case 'negative':
      qrText = shareData.n || shareData.negative || shareData.raw_negative || '';
      infoText = tr('qr.info.negative_len', { count: qrText.length });
      break;
    case 'meta':
      qrText = JSON.stringify(shareData);
      infoText = tr('qr.info.meta_len', { count: qrText.length });
      break;
    case 'url': {
      const encoded = btoa(unescape(encodeURIComponent(JSON.stringify(shareData))));
      qrText = `${window.location.origin}/share?data=${encoded}`;
      infoText = tr('qr.info.url');
      break;
    }
  }

  // Use UTF-8 byte length for QR capacity checks (not JS string length).
  // CJK characters are 3 bytes each in UTF-8 — using .length would
  // undercount and allow payloads that overflow the QR RS-block table.
  const bytes = _byteLength(qrText);

  if (bytes > QR_WARN_BYTES) {
    infoText += ' ' + tr('qr.info.compressing');
    if (mode === 'meta') {
      // Strip non-essential fields to reduce payload size.
      qrText = _compactMeta(shareData);
    }
  }

  const finalBytes = _byteLength(qrText);
  if (finalBytes > QR_MAX_BYTES) {
    // ── Compact fallback ────────────────────────────────────────────────────
    //
    // positive/negative: the original text doesn't fit.
    // Fallback to Level 2 meta compact (seed/steps/cfg/sampler/model/size/id).
    // The copy button still copies the ORIGINAL text so users can still get
    // the full prompt — only the QR encodes the compact params.
    if (mode === 'positive' || mode === 'negative') {
      const fallbackQr = _compactMetaLevel2(shareData);
      if (_byteLength(fallbackQr) <= QR_MAX_BYTES) {
        return {
          ok: true,
          qrText: fallbackQr,
          copyText: qrText,   // original text for copy button
          infoText: tr('qr.info.params_only', 'パラメータのみ'),
          fallbackNote: tr('qr.fallback.text_too_long', 'テキストが長すぎるため、再生成パラメータのみを QR に表示しています。コピーボタンで全文を取得できます。'),
        };
      }
      // Level 2 also too long — fall through to error
    }

    // meta mode: Level 1 was already applied above; try Level 2 (drop p/n).
    if (mode === 'meta') {
      const level2 = _compactMetaLevel2(shareData);
      if (_byteLength(level2) <= QR_MAX_BYTES) {
        return {
          ok: true,
          qrText: level2,
          infoText: tr('qr.info.params_only', 'パラメータのみ'),
          fallbackNote: tr('qr.fallback.prompt_excluded', 'プロンプトが長すぎるため除外しました。seed / steps / cfg / sampler / model / size のみを表示しています。'),
        };
      }
      // Level 2 also too long — fall through to error
    }

    // ── Hard error: no compact variant fits ────────────────────────────────
    const diagText = `UTF-8: ${finalBytes} bytes / 上限 ${QR_MAX_BYTES} bytes (超過: ${finalBytes - QR_MAX_BYTES} bytes)`;
    console.warn('[QR] payload too large —', diagText, { mode, qrText });
    return {
      ok: false,
      qrText,
      infoText: tr('qr.info.too_long'),
      diagText,
    };
  }

  return {
    ok: true,
    qrText,
    infoText,
  };
}

export function renderQr(container: HTMLElement | null, qrText: string): void {
  if (!container) return;
  container.innerHTML = '';

  if (typeof QRCode !== 'undefined' && qrText) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const QRC = QRCode as any;
    new QRCode(container, {
      text: qrText,
      width: 200,
      height: 200,
      colorDark: '#000000',
      colorLight: '#ffffff',
      correctLevel: QRC.CorrectLevel?.M,
    });
    return;
  }

  if (!qrText) {
    container.innerHTML = `<div style="color:#666;font-size:11px;padding:20px;">${escapeHtml(tr('qr.no_content'))}</div>`;
    return;
  }

  container.innerHTML = `<div style="color:#333;font-size:11px;padding:20px;">${escapeHtml(tr('qr.load_failed'))}<br>${escapeHtml(tr('qr.use_text_copy'))}</div>`;
}
