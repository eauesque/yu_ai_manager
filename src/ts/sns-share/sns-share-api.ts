/**
 * sns-share/sns-share-api.ts — SNS Share API calls.
 */

import { getAppApi } from '../shared/browser-apis';

function _fetch(url: string, init?: RequestInit): Promise<Response> {
  return getAppApi().apiFetch(url, init);
}

export interface SnsPreviewResult {
  text: string;
  graphemes: number;
  meta: Record<string, string>;
}

export async function fetchSnsPreview(
  fileId: number,
  template?: string,
): Promise<SnsPreviewResult> {
  const params = new URLSearchParams({ file_id: String(fileId) });
  if (template) params.set('template', template);
  const resp = await _fetch(`/api/sns/preview?${params}`);
  const json = await resp.json();
  return json.data || json;
}

export async function fetchXIntentUrl(fileId: number): Promise<string> {
  const resp = await _fetch(`/api/sns/x/intent?file_id=${fileId}`);
  const json = await resp.json();
  return (json.data || json).url || '';
}

export async function postToBluesky(
  fileId: number,
  text?: string,
  attachImage: boolean = true,
): Promise<{ ok: boolean; uri?: string; error?: string }> {
  const body: Record<string, unknown> = { file_id: fileId, attach_image: attachImage };
  if (text !== undefined) body.text = text;
  const resp = await _fetch('/api/sns/bluesky/post', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const json = await resp.json();
  if (!resp.ok) return { ok: false, error: json.error || resp.statusText };
  return { ok: true, uri: (json.data || json).uri };
}

export async function testBlueskyConnection(): Promise<{
  ok: boolean;
  handle?: string;
  display_name?: string;
  error?: string;
}> {
  const resp = await _fetch('/api/sns/bluesky/test', { method: 'POST' });
  const json = await resp.json();
  if (!resp.ok) return { ok: false, error: json.error || resp.statusText };
  const d = json.data || json;
  return { ok: true, handle: d.handle, display_name: d.display_name };
}

export async function loadSnsConfig(): Promise<Record<string, unknown>> {
  const resp = await _fetch('/api/sns/config');
  const json = await resp.json();
  return json.data || json;
}

export async function saveSnsConfig(data: {
  bluesky_handle: string;
  bluesky_app_password: string;
  post_template: string;
}): Promise<boolean> {
  const resp = await _fetch('/api/sns/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return resp.ok;
}
