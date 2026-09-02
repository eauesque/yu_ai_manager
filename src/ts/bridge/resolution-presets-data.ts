/**
 * Bridge Resolution Presets — shared data module
 *
 * Preset list for SD 1.5 / SDXL Trained / SDXL Cheat Sheet.
 * Source: https://civitai.com/articles/2246/sdxl-image-size-cheat-sheet (Cheat Sheet group)
 */

export type PresetGroup = 'sd15' | 'sdxl_trained' | 'sdxl_cheatsheet';

export interface Preset {
  key: string;        // stable unique id used as <option value>
  group: PresetGroup;
  label: string;      // English display text, e.g. "Portrait 2:3 — 832×1216"
  w: number;
  h: number;
}

export const RESOLUTION_PRESETS: Preset[] = [
  // SD 1.5 (512)
  { key: 'sd15_512_512',   group: 'sd15', label: 'Square 512×512',      w: 512, h: 512 },
  { key: 'sd15_512_768',   group: 'sd15', label: 'Portrait 512×768',    w: 512, h: 768 },
  { key: 'sd15_768_512',   group: 'sd15', label: 'Landscape 768×512',   w: 768, h: 512 },
  { key: 'sd15_640_896',   group: 'sd15', label: 'Portrait+ 640×896',   w: 640, h: 896 },
  { key: 'sd15_896_640',   group: 'sd15', label: 'Landscape+ 896×640',  w: 896, h: 640 },

  // SDXL Trained
  { key: 'sdxl_1024_1024', group: 'sdxl_trained', label: 'Square 1024×1024',          w: 1024, h: 1024 },
  { key: 'sdxl_896_1152',  group: 'sdxl_trained', label: 'Portrait 3:4 — 896×1152',   w: 896,  h: 1152 },
  { key: 'sdxl_1152_896',  group: 'sdxl_trained', label: 'Landscape 4:3 — 1152×896',  w: 1152, h: 896 },
  { key: 'sdxl_832_1216',  group: 'sdxl_trained', label: 'Portrait 2:3 — 832×1216',   w: 832,  h: 1216 },
  { key: 'sdxl_1216_832',  group: 'sdxl_trained', label: 'Landscape 3:2 — 1216×832',  w: 1216, h: 832 },
  { key: 'sdxl_768_1344',  group: 'sdxl_trained', label: 'Portrait 9:16 — 768×1344',  w: 768,  h: 1344 },
  { key: 'sdxl_1344_768',  group: 'sdxl_trained', label: 'Landscape 16:9 — 1344×768', w: 1344, h: 768 },
  { key: 'sdxl_640_1536',  group: 'sdxl_trained', label: 'Portrait tall — 640×1536',  w: 640,  h: 1536 },
  { key: 'sdxl_1536_640',  group: 'sdxl_trained', label: 'Landscape wide — 1536×640', w: 1536, h: 640 },

  // SDXL Cheat Sheet (Civitai)
  { key: 'cs_832_1248',    group: 'sdxl_cheatsheet', label: 'Portrait 2:3 — 832×1248',     w: 832,  h: 1248 },
  { key: 'cs_880_1176',    group: 'sdxl_cheatsheet', label: 'Standard 3:4 — 880×1176',     w: 880,  h: 1176 },
  { key: 'cs_912_1144',    group: 'sdxl_cheatsheet', label: 'Large 4:5 — 912×1144',        w: 912,  h: 1144 },
  { key: 'cs_768_1360',    group: 'sdxl_cheatsheet', label: 'Selfie 9:16 — 768×1360',      w: 768,  h: 1360 },
  { key: 'cs_1176_888',    group: 'sdxl_cheatsheet', label: 'SD TV 4:3 — 1176×888',        w: 1176, h: 888 },
  { key: 'cs_1224_856',    group: 'sdxl_cheatsheet', label: 'IMAX 1.43:1 — 1224×856',      w: 1224, h: 856 },
  { key: 'cs_1312_792',    group: 'sdxl_cheatsheet', label: 'European 1.66:1 — 1312×792',  w: 1312, h: 792 },
  { key: 'cs_1360_768',    group: 'sdxl_cheatsheet', label: 'HD 16:9 — 1360×768',          w: 1360, h: 768 },
  { key: 'cs_1392_752',    group: 'sdxl_cheatsheet', label: 'Widescreen 1.85:1 — 1392×752', w: 1392, h: 752 },
  { key: 'cs_1568_664',    group: 'sdxl_cheatsheet', label: 'Cinemascope 2.35:1 — 1568×664', w: 1568, h: 664 },
  { key: 'cs_1576_656',    group: 'sdxl_cheatsheet', label: 'Anamorphic 2.39:1 — 1576×656', w: 1576, h: 656 },
  { key: 'cs_1296_800',    group: 'sdxl_cheatsheet', label: 'Golden 1.618:1 — 1296×800',   w: 1296, h: 800 },
];

const BY_KEY: Map<string, Preset> = new Map(
  RESOLUTION_PRESETS.map((p) => [p.key, p]),
);

export function findPreset(key: string): Preset | null {
  return BY_KEY.get(key) ?? null;
}

export const GROUPS = ['sd15', 'sdxl_trained', 'sdxl_cheatsheet'] as const satisfies readonly PresetGroup[];
