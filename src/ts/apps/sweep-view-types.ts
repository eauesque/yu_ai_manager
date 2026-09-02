export interface SweepAxis {
  param: string;
  index: number;
  total: number;
  value: unknown;
  series: unknown[];
}

export interface SweepMeta {
  id: string;
  bridge: string;
  axes: SweepAxis[];
  base_seed: number;
  created_at: number;
}

export interface SweepFilesEntry {
  path: string;
  axis_0_index?: number;
  axis_0_value?: unknown;
  axis_1_index?: number;
  axis_1_value?: unknown;
  axis_2_index?: number;
  axis_2_value?: unknown;
  file_id: number | null;
}

export interface FileMeta {
  positive?: string;
  positive_prompt?: string;
  negative?: string;
  negative_prompt?: string;
  parameters?: Record<string, unknown>;
  model?: string;
  path?: string;
  [k: string]: unknown;
}
