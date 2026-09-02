export interface RetagTag {
  tag: string;
  confidence: number;
  category: string;
}

export interface RetagSinglePayload {
  file_id: number;
  model_id: string;
  tags: RetagTag[];
  rating: string;
  elapsed_ms: number;
  inserted: number;
}

export interface RetagSingleResponse {
  ok?: boolean;
  error?: string;
  data?: RetagSinglePayload;
  file_id?: number;
  model_id?: string;
  tags?: RetagTag[];
  rating?: string;
  elapsed_ms?: number;
  inserted?: number;
}

export interface ActiveModelEntry {
  model_id: string;
  file_count: number;
}

export interface ActiveModelPayload {
  active_model_id: string | null;
  available_models: ActiveModelEntry[];
}

export interface RetagActiveState {
  activeModelId: string | null;
  availableModels: ActiveModelEntry[];
}

export interface ActiveModelResponse {
  ok?: boolean;
  error?: string | null;
  data?: ActiveModelPayload;
  active_model_id?: string | null;
  available_models?: ActiveModelEntry[];
}

export interface WdTagsResponse {
  ok?: boolean;
  error?: string | null;
  data?: { tags?: unknown[] };
  tags?: unknown[];
}
