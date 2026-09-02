/**
 * shared/bridge-payload.ts
 *
 * Pure helpers for building Bridge send payloads (prompt + characters), shared
 * between detail-modal send-to-bridge and any future feature that targets the
 * `bridge_send_prompt` localStorage protocol (e.g., prompt+image simultaneous
 * send / "remix" menu).
 *
 * Stays UI-agnostic: no DOM access, no localStorage, no navigation.
 */

export type BridgeTarget = 'nai' | 'sd' | 'comfyui';
export type ImageBridgeTarget = 'nai' | 'sd' | 'comfyui';

export const NAI_META_SOURCES = new Set([
  'novelai_v4_png', 'novelai_v4_webp', 'novelai_v4',
  'novelai_png', 'novelai_webp', 'nai_webp',
]);

export interface CharacterEntry {
  // NAI v4 metadata uses either `prompt` or `char_caption` historically.
  prompt?: string;
  char_caption?: string;
  center?: { x: number; y: number } | null;
}

export interface PromptSource {
  meta_source?: string;
  positive?: string;
  negative?: string;
  parameters?: Record<string, unknown> | string | undefined;
  novelai_v4?: {
    character_prompts?: CharacterEntry[];
    negative_characters?: CharacterEntry[];
  };
  /** Checkpoint/model name from image metadata (e.g. from ComfyUI or A1111 parameters). */
  model?: string;
  /** Resolution string in "WIDTHxHEIGHT" format (e.g. "832x1216"). */
  resolution?: string;
}

export interface PromptPayload {
  prompt: string;
  negative: string;
  characters?: Array<{ prompt: string; negative: string; center?: unknown }>;
  seed?: number;
  steps?: number;
  scale?: number;
  cfg_rescale?: number;
  source: string | 'detail_modal' | 'remix' | 'prompt_library' | 'recipe_import';
  convert_warning?: string;
  // Recipe share extensions (all optional - existing consumers unaffected):
  model?: string;
  sampler?: string;
  width?: number;
  height?: number;
  scheduler?: string;
  // Extended loader fields (ComfyUI separate-load mode):
  vae?: string;
  diffusion_model?: string;
  text_encoder_1?: string;
  text_encoder_2?: string;
  clip_type?: string;
}

function extractNumericParam(params: Record<string, unknown>, ...keys: string[]): number | undefined {
  for (const k of keys) {
    const v = params[k];
    if (v == null) continue;
    const n = typeof v === 'number' ? v : Number(v);
    if (Number.isFinite(n)) return n;
  }
  return undefined;
}

function extractStringParam(params: Record<string, unknown>, ...keys: string[]): string | undefined {
  for (const k of keys) {
    const v = params[k];
    if (typeof v === 'string' && v.trim()) return v.trim();
  }
  return undefined;
}

/** Parse "WIDTHxHEIGHT" or "WIDTH×HEIGHT" resolution string into numeric width/height. */
function parseResolution(resolution: string | undefined): { width?: number; height?: number } {
  if (!resolution) return {};
  const m = resolution.match(/^(\d+)[xX×](\d+)$/);
  if (!m) return {};
  const w = parseInt(m[1], 10);
  const h = parseInt(m[2], 10);
  if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0) return {};
  return { width: w, height: h };
}

/** Extract a numeric seed from `data.parameters` regardless of casing.
 * SD/A1111 metadata keys it as `Seed`; NAI as `seed`; some sources as `noise_seed`.
 * Returns undefined if not present or not finite.
 */
export function extractSeed(data: PromptSource): number | undefined {
  const params = data.parameters;
  if (!params || typeof params !== 'object') return undefined;
  const candidates = ['Seed', 'seed', 'noise_seed'];
  for (const k of candidates) {
    const v = (params as Record<string, unknown>)[k];
    if (v == null) continue;
    const n = typeof v === 'number' ? v : Number(v);
    if (Number.isFinite(n) && n >= 0) return Math.trunc(n);
  }
  return undefined;
}

export function isNaiSource(metaSource: string | undefined): boolean {
  return !!metaSource && NAI_META_SOURCES.has(metaSource);
}

export function charText(c: CharacterEntry): string {
  return c.prompt || c.char_caption || '';
}

export async function callConvert(
  endpoint: '/ext/convert/nai-to-sd' | '/ext/convert/sd-to-nai',
  pos: string,
  neg: string,
): Promise<{ prompt: string; negative: string; ok: boolean }> {
  try {
    const r = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: pos, negative: neg }),
    });
    if (!r.ok) return { prompt: pos, negative: neg, ok: false };
    const d = await r.json();
    return {
      prompt: typeof d.prompt === 'string' ? d.prompt : pos,
      negative: typeof d.negative === 'string' ? d.negative : neg,
      ok: true,
    };
  } catch {
    return { prompt: pos, negative: neg, ok: false };
  }
}

export interface BuildPromptOptions {
  /** Source tag written into payload.source (e.g., 'detail-modal', 'prompt-library'). */
  source: string;
  /** Localized warning shown when convert fails. Defaults to a Japanese fallback. */
  convertFailedMessage?: string;
}

export async function buildPromptPayload(
  data: PromptSource,
  target: BridgeTarget,
  opts: BuildPromptOptions,
): Promise<PromptPayload> {
  const naiSrc = isNaiSource(data.meta_source);
  let pos = data.positive || '';
  let neg = data.negative || '';
  const chars = data.novelai_v4?.character_prompts ?? [];
  const negChars = data.novelai_v4?.negative_characters ?? [];
  const failMsg = opts.convertFailedMessage
    ?? 'プロンプト変換に失敗しました。元の文法のまま送信されています';
  const seed = extractSeed(data);

  const paramsObj = data.parameters && typeof data.parameters === 'object'
    ? data.parameters as Record<string, unknown>
    : {};
  // Key variants: ComfyUI/A1111 use title-case labels ("Steps", "CFG scale");
  // NAI stores raw lowercase keys ("steps", "scale", "cfg_rescale").
  const steps = extractNumericParam(paramsObj, 'Steps', 'steps');
  const scale = extractNumericParam(paramsObj, 'CFG scale', 'scale', 'cfg');
  const cfgRescale = extractNumericParam(paramsObj, 'CFG Rescale', 'cfg_rescale');

  if (target === 'nai') {
    const characters = chars.map((c, i) => {
      const negEntry = negChars[i];
      return {
        prompt: charText(c),
        negative: negEntry ? charText(negEntry) : '',
        ...(c.center ? { center: c.center } : {}),
      };
    }).filter(c => c.prompt || c.negative);

    let warning: string | undefined;
    if (!naiSrc && (pos || neg)) {
      const r = await callConvert('/ext/convert/sd-to-nai', pos, neg);
      pos = r.prompt; neg = r.negative;
      if (!r.ok) warning = failMsg;
    }
    return {
      prompt: pos,
      negative: neg,
      ...(characters.length ? { characters } : {}),
      ...(seed != null ? { seed } : {}),
      ...(steps != null ? { steps } : {}),
      ...(scale != null ? { scale } : {}),
      ...(cfgRescale != null ? { cfg_rescale: cfgRescale } : {}),
      source: opts.source,
      ...(warning ? { convert_warning: warning } : {}),
    };
  }

  const charPos = chars.map(charText).filter(Boolean);
  const charNeg = negChars.map(charText).filter(Boolean);
  if (charPos.length) pos = pos ? pos + ', ' + charPos.join(', ') : charPos.join(', ');
  if (charNeg.length) neg = neg ? neg + ', ' + charNeg.join(', ') : charNeg.join(', ');

  // Extract sampler/scheduler: ComfyUI uses title-case labels ("Sampler", "Scheduler");
  // A1111 uses "Sampler"; NAI uses lowercase "sampler" / "noise_schedule".
  const sampler = extractStringParam(paramsObj, 'Sampler', 'sampler');
  const scheduler = extractStringParam(paramsObj, 'Scheduler', 'scheduler', 'noise_schedule');

  // Model: top-level field set by resolve_detail_fields() from the DB row.
  const model = data.model || undefined;

  // Extended loader fields (ComfyUI separate-load mode):
  const vae = extractStringParam(paramsObj, 'VAE');
  const diffusionModel = extractStringParam(paramsObj, 'Diffusion Model');
  const textEncoder1 = extractStringParam(paramsObj, 'CLIP 1');
  const textEncoder2 = extractStringParam(paramsObj, 'CLIP 2');
  const clipType = extractStringParam(paramsObj, 'CLIP Type');

  // Resolution: prefer top-level "resolution" string ("WxH"), fall back to
  // per-param width/height (present in NAI metadata as lowercase keys).
  const { width, height } = (() => {
    const r = parseResolution(data.resolution);
    if (r.width != null && r.height != null) return r;
    const w = extractNumericParam(paramsObj, 'width', 'Width');
    const h = extractNumericParam(paramsObj, 'height', 'Height');
    return { width: w, height: h };
  })();

  let warning: string | undefined;
  if (naiSrc && (pos || neg)) {
    const r = await callConvert('/ext/convert/nai-to-sd', pos, neg);
    pos = r.prompt; neg = r.negative;
    if (!r.ok) warning = failMsg;
  }
  return {
    prompt: pos,
    negative: neg,
    ...(seed != null ? { seed } : {}),
    ...(steps != null ? { steps } : {}),
    ...(scale != null ? { scale } : {}),
    ...(sampler ? { sampler } : {}),
    ...(scheduler ? { scheduler } : {}),
    ...(model ? { model } : {}),
    ...(width != null ? { width } : {}),
    ...(height != null ? { height } : {}),
    ...(vae ? { vae } : {}),
    ...(diffusionModel ? { diffusion_model: diffusionModel } : {}),
    ...(textEncoder1 ? { text_encoder_1: textEncoder1 } : {}),
    ...(textEncoder2 ? { text_encoder_2: textEncoder2 } : {}),
    ...(clipType ? { clip_type: clipType } : {}),
    source: opts.source,
    ...(warning ? { convert_warning: warning } : {}),
  };
}
