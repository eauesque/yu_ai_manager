/** WebWorker communication protocol type definitions */

export interface RegexFilterRequest {
  type: 'regex-filter';
  id: number;
  items: FilterItem[];
  pattern: string;
  flags: string;
}

export interface FilterItem {
  positive?: string;
  negative?: string;
  artist?: string;
  path?: string;
  [key: string]: unknown;
}

export interface RegexFilterResponse {
  type: 'regex-filter';
  id: number;
  filtered: FilterItem[];
}

export interface ErrorResponse {
  type: 'error';
  id: number;
  message: string;
}

export type WorkerRequest = RegexFilterRequest;
export type WorkerResponse = RegexFilterResponse | ErrorResponse;
