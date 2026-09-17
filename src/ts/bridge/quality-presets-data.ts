/**
 * Bridge Quality Presets — Type definitions, built-in presets, and localStorage helpers
 */

/* ------------------------------------------------------------------ */
/*  Type definitions                                                   */
/* ------------------------------------------------------------------ */

export interface QualityPreset {
  name: string;
  positive: string;
  negative: string;
  builtin?: boolean;
  compat: string[];   // ['sd','nai','comfy']
}

export interface AttachConfig {
  prefix: string;           // 'sdwb' | 'nab' | 'cfb'
  bridgeType: string;       // 'sd' | 'nai' | 'comfy'
  getPrompt: () => string;
  setPrompt: (v: string) => void;
  getNegative: () => string;
  setNegative: (v: string) => void;
  toolbarSelector?: string;
}

/* ------------------------------------------------------------------ */
/*  Built-in presets                                                   */
/* ------------------------------------------------------------------ */

export const BUILTIN_PRESETS: QualityPreset[] = [
  {
    name: 'SD High Quality',
    positive: 'masterpiece, best quality, very aesthetic, absurdres',
    negative: 'worst quality, bad quality, low quality, lowres, bad anatomy, bad hands, error, missing fingers, extra digit, fewer digits, cropped, jpeg artifacts',
    builtin: true,
    compat: ['sd', 'comfy'],
  },
  {
    name: 'SD Realistic',
    positive: 'photorealistic, ultra detailed, 8k, RAW photo, best quality',
    negative: 'worst quality, low quality, normal quality, lowres, bad anatomy, bad hands, watermark, text',
    builtin: true,
    compat: ['sd', 'comfy'],
  },
  {
    name: 'NAI Quality',
    positive: 'masterpiece, best quality, very aesthetic, absurdres',
    negative: 'lowres, {bad}, error, fewer, extra, missing, worst quality, jpeg artifacts, bad quality, unfinished, displeasing, chromatic aberration, extra fingers, mutated hands, signature, watermark, username',
    builtin: true,
    compat: ['nai'],
  },
  {
    name: 'NAI Artistic',
    positive: 'masterpiece, best quality, amazing quality, very aesthetic, absurdres',
    negative: 'lowres, jpeg artifacts, worst quality, watermark, blurry, very displeasing',
    builtin: true,
    compat: ['nai'],
  },
  {
    name: 'Minimal',
    positive: 'masterpiece, best quality',
    negative: 'worst quality, low quality',
    builtin: true,
    compat: ['sd', 'nai', 'comfy'],
  },
];

/* ------------------------------------------------------------------ */
/*  localStorage helpers                                               */
/* ------------------------------------------------------------------ */

const LS_KEY = 'bridge_quality_presets';

export function loadCustomPresets(): QualityPreset[] {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return [];
    return JSON.parse(raw) as QualityPreset[];
  } catch { return []; }
}

export function saveCustomPresets(list: QualityPreset[]): void {
  localStorage.setItem(LS_KEY, JSON.stringify(list));
}
