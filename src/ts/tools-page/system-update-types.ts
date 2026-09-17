export interface ExtStatus {
  name: string;
  version: string;
  source: string;
  status: string;
  enabled: boolean;
  description: string;
  commits_behind?: number;
  local_head?: string;
  remote_head?: string;
}

export interface UnifiedCheckResult {
  system: {
    current: string;
    latest: string;
    update_available: boolean;
    install_type: string;
    error?: string;
  };
  extensions: ExtStatus[];
  summary: {
    total: number;
    up_to_date: number;
    update_available: number;
    unknown: number;
    builtin: number;
  };
}

export interface ApiEnvelope<T> {
  ok?: boolean;
  error?: string | null;
  data?: T;
}

export interface ApiErrorPayload {
  error?: string | null;
}

export interface SystemUpdateCheckResult {
  current?: string;
  latest?: string;
  update_available?: boolean;
  install_type?: string;
  docker_command?: string;
  error?: string;
}

export interface UpdateStatusResult {
  install_type?: string;
  update_in_progress?: boolean;
  version?: string;
}

export interface UpdateActionResult {
  accepted?: boolean;
  message?: string;
  code?: string;
  update_system?: boolean;
  update_extensions?: boolean;
  error?: string | null;
}

export interface ExtensionUpdateResult {
  message?: string;
  error?: string | null;
}

export interface UpdateProgressPayload {
  step?: string;
  status?: string;
  detail?: string;
  unified?: boolean | string;
}
