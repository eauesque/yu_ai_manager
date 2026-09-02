/**
 * ai-analysis/types.ts -- Shared type definitions for AI analysis module.
 */

export interface AiConfig {
  engine?: string;
  api_key?: string;
  model?: string;
  ollama_url?: string;
  ollama_model?: string;
  openai_api_key?: string;
  openai_model?: string;
  openai_compat_url?: string;
  openai_compat_api_key?: string;
  openai_compat_model?: string;
  is_local?: boolean;
  fallback_local_only?: boolean;
  language?: string;
}

export interface AiStats {
  total_analyzed: number;
  total_files: number;
  styles: Array<{ style: string; count: number }>;
}

export interface TrendHistoryItem {
  id: number;
  engine: string;
  analyzed_at: number;
  prompt_count: number;
  result: {
    style_tendency?: string;
    strengths?: string;
    weaknesses?: string;
    frequent_tags?: string[];
    recommendations?: string[];
    unexplored?: string[];
    raw?: string;
  };
}
