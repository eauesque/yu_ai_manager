/**
 * Polling for the OCR job.
 *
 * The five OCR routes answer 202 with a `run_id` and run under a single job
 * whose id is fixed to "ocr". A poller that matches only on `job_id` — the way
 * the wd-tagger poller does — cannot tell one submission from the next, so it
 * happily reports someone else's run as its own. Every wait here is therefore
 * scoped to the `run_id` the submit returned, which the server carries in
 * `JobDict.detail` (the dict deliberately omits `started_at`, so `detail` is
 * the only run identity available to a client).
 */

export interface OcrSubmitResponse {
  job_id: string;
  run_id: string;
  label: string;
}

export interface OcrJobState {
  job_id: string;
  label: string;
  running: boolean;
  phase?: string;
  current?: number;
  total?: number;
  percent?: number;
  message?: string;
  /** The run_id. See the note above. */
  detail?: string;
  error?: string;
  elapsed_seconds: number;
  result?: Record<string, unknown>;
}

export class OcrRunReplaced extends Error {
  constructor() {
    super('another OCR run replaced this one');
    this.name = 'OcrRunReplaced';
  }
}

export class OcrJobFailed extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'OcrJobFailed';
  }
}

type Fetcher = (url: string, init?: RequestInit) => Promise<Response>;

/**
 * Submit an OCR job. Returns the run identity; throws with the server's own
 * message on 400/401/404/409/503 so the caller can show why it was refused
 * rather than a generic failure.
 */
export async function submitOcrJob(
  fetcher: Fetcher,
  url: string,
  body: Record<string, unknown>,
): Promise<OcrSubmitResponse> {
  const response = await fetcher(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const payload = (await response.json()) as Record<string, unknown>;
  if (response.status === 202) {
    return payload as unknown as OcrSubmitResponse;
  }
  if (response.status === 409) {
    // The 409 body describes the job already running, not this request.
    const label = typeof payload.label === 'string' ? payload.label : 'an OCR job';
    throw new OcrJobFailed(`${label} is already running`);
  }
  const message = typeof payload.error === 'string' ? payload.error : `HTTP ${response.status}`;
  throw new OcrJobFailed(message);
}

export interface PollOptions {
  /** Milliseconds between polls. */
  intervalMs?: number;
  /** Give up after this long. Guards against a job that never finishes. */
  timeoutMs?: number;
  /** Called with each observation of *our* run, for progress display. */
  onProgress?: (job: OcrJobState) => void;
  /** Injection point for tests; defaults to setTimeout. */
  sleep?: (ms: number) => Promise<void>;
}

const defaultSleep = (ms: number): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Wait for the run identified by `runId` to finish.
 *
 * Resolves with the finished job. Throws `OcrRunReplaced` if a different run
 * took over the slot (our result is gone and will never appear), and
 * `OcrJobFailed` if the job ended with an error.
 */
export async function waitForOcrRun(
  fetcher: Fetcher,
  runId: string,
  options: PollOptions = {},
): Promise<OcrJobState> {
  const intervalMs = options.intervalMs ?? 1000;
  const timeoutMs = options.timeoutMs ?? 30 * 60 * 1000;
  const sleep = options.sleep ?? defaultSleep;
  const deadline = Date.now() + timeoutMs;

  for (;;) {
    const response = await fetcher('/api/jobs/ocr');
    if (response.status === 404) {
      // HISTORY_TTL_SECS is 60: a finished job disappears a minute later. If we
      // never saw it finish, we cannot claim it succeeded.
      throw new OcrRunReplaced();
    }
    const job = (await response.json()) as OcrJobState;

    if (job.detail !== runId) {
      throw new OcrRunReplaced();
    }
    if (!job.running) {
      if (job.error) throw new OcrJobFailed(job.error);
      return job;
    }
    options.onProgress?.(job);

    if (Date.now() >= deadline) {
      throw new OcrJobFailed('timed out waiting for the OCR job');
    }
    await sleep(intervalMs);
  }
}

/** Submit and wait in one call. */
export async function runOcrJob(
  fetcher: Fetcher,
  url: string,
  body: Record<string, unknown>,
  options: PollOptions = {},
): Promise<OcrJobState> {
  const submitted = await submitOcrJob(fetcher, url, body);
  return waitForOcrRun(fetcher, submitted.run_id, options);
}

/** Cancel the run identified by `runId`. A stale id is refused with 409. */
export async function cancelOcrRun(fetcher: Fetcher, runId: string): Promise<void> {
  const response = await fetcher('/api/ocr/cancel', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ run_id: runId }),
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as Record<string, unknown>;
    const message = typeof payload.error === 'string' ? payload.error : `HTTP ${response.status}`;
    throw new OcrJobFailed(message);
  }
}
