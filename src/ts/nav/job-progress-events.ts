import { sseSubscribe } from '../sse';
import { updateBarUI, updateQueueBadge, unwrapSseData, sseToJobInfo } from './job-progress-ui';

export function registerJobProgressEvents(
  startPoll: () => void,
  stopPoll: () => void,
  getLastSseUpdate: () => number,
  setLastSseUpdate: (ts: number) => void,
  resetIdlePolls: () => void,
): void {
  const onScanStart = (raw: unknown): void => {
    setLastSseUpdate(Date.now());
    const data = unwrapSseData(raw);
    const job = sseToJobInfo((data.job_id as string) || 'scan', data);
    job.phase = 'initializing';
    updateBarUI(job);
    startPoll();
  };
  const onScanProgress = (raw: unknown): void => {
    setLastSseUpdate(Date.now());
    resetIdlePolls();
    const data = unwrapSseData(raw);
    updateBarUI(sseToJobInfo((data.job_id as string) || 'scan', data));
    startPoll();
  };
  const onScanComplete = (raw: unknown): void => {
    setLastSseUpdate(Date.now());
    const data = unwrapSseData(raw);
    const job = sseToJobInfo((data.job_id as string) || 'scan', data);
    job.running = false;
    job.phase = 'complete';
    job.percent = 100;
    updateBarUI(job);
  };
  const onScanError = (raw: unknown): void => {
    setLastSseUpdate(Date.now());
    const data = unwrapSseData(raw);
    const job = sseToJobInfo((data.job_id as string) || 'scan', data);
    job.running = false;
    job.phase = 'error';
    job.error = (data.error as string) || 'Unknown error';
    updateBarUI(job);
  };
  const onGenericProgress = (jobId: string) => (raw: unknown) => {
    setLastSseUpdate(Date.now());
    resetIdlePolls();
    updateBarUI(sseToJobInfo(jobId, unwrapSseData(raw)));
    startPoll();
  };
  const onGenericComplete = (jobId: string) => (raw: unknown) => {
    setLastSseUpdate(Date.now());
    const job = sseToJobInfo(jobId, unwrapSseData(raw));
    job.running = false;
    job.phase = 'complete';
    job.percent = 100;
    updateBarUI(job);
  };
  sseSubscribe('scan.start', onScanStart);
  sseSubscribe('scan.progress', onScanProgress);
  sseSubscribe('scan.complete', onScanComplete);
  sseSubscribe('scan.error', onScanError);
  sseSubscribe('scan.queued', (raw) => {
    setLastSseUpdate(Date.now());
    updateQueueBadge((unwrapSseData(raw).position as number) || 0);
  });
  sseSubscribe('scan.queue_next', (raw) => {
    setLastSseUpdate(Date.now());
    updateQueueBadge((unwrapSseData(raw).remaining as number) || 0);
  });
  sseSubscribe('scan.queue_cleared', () => updateQueueBadge(0));
  sseSubscribe('hash_backfill.progress', onGenericProgress('hash-backfill'));
  sseSubscribe('hash_backfill.complete', onGenericComplete('hash-backfill'));
  sseSubscribe('semantic_index.progress', onGenericProgress('semantic-index'));
  sseSubscribe('semantic_index.complete', (raw: unknown) => {
    onGenericComplete('semantic-index')(raw);
    try {
      const tr = typeof window !== 'undefined' ? (window as any).tr as ((k: string, f: string) => string) | undefined : undefined;
      const msg = tr ? tr('semantic_index.complete_toast', '✅ セマンティック検索の準備完了！検索画面で 🧠 を試してみましょう') : '✅ Semantic index built. Try 🧠 in search!';
      import('../shared/toast').then(({ showToast }) => { showToast(msg); }).catch(() => {});
    } catch {
      // ignore
    }
  });
  sseSubscribe('yolo_detect.progress', onGenericProgress('yolo-detect'));
  sseSubscribe('yolo_detect.complete', onGenericComplete('yolo-detect'));
  sseSubscribe('fpb.progress', onGenericProgress('fpb'));
  sseSubscribe('fpb.complete', onGenericComplete('fpb'));
  sseSubscribe('fpb.error', (raw: unknown) => {
    setLastSseUpdate(Date.now());
    const job = sseToJobInfo('fpb', unwrapSseData(raw));
    job.running = false;
    job.phase = 'error';
    updateBarUI(job);
  });
  sseSubscribe('chatlog_reprocess.progress', onGenericProgress('chatlog-reprocess'));
  sseSubscribe('chatlog_reprocess.complete', onGenericComplete('chatlog-reprocess'));
}
