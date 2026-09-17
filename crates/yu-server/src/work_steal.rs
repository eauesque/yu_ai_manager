use std::{
    collections::VecDeque,
    sync::{
        atomic::{AtomicUsize, Ordering},
        Arc,
    },
};
use tokio::sync::Mutex;
use tokio_util::sync::CancellationToken;

pub(crate) struct StealOutcome {
    pub processed: usize,
    pub cancelled: bool,
}
pub(crate) async fn work_steal<T, W, F, Fut>(
    items: Vec<T>,
    workers: Vec<W>,
    batch_size: usize,
    cancel: CancellationToken,
    work: F,
) -> StealOutcome
where
    T: Send + 'static,
    W: Clone + Send + 'static,
    F: Fn(W, Vec<T>) -> Fut + Send + Sync + 'static,
    Fut: std::future::Future<Output = ()> + Send + 'static,
{
    if items.is_empty() || workers.is_empty() {
        return StealOutcome {
            processed: 0,
            cancelled: cancel.is_cancelled(),
        };
    }
    // Zero cannot dequeue a batch; one preserves forward progress.
    let batch_size = batch_size.max(1);
    let items = Arc::new(Mutex::new(VecDeque::from(items)));
    let processed = Arc::new(AtomicUsize::new(0));
    let work = Arc::new(work);
    let mut tasks = Vec::with_capacity(workers.len());
    for worker in workers {
        let (items, processed, work, cancel) = (
            items.clone(),
            processed.clone(),
            work.clone(),
            cancel.clone(),
        );
        tasks.push(tokio::spawn(async move {
            loop {
                let mut batch = Vec::with_capacity(batch_size);
                for _ in 0..batch_size {
                    if cancel.is_cancelled() {
                        break;
                    } // Guard drops here, before work(...).await, so workers can steal.
                    let Some(item) = items.lock().await.pop_front() else {
                        break;
                    };
                    batch.push(item);
                }
                if batch.is_empty() {
                    break;
                }
                let count = batch.len();
                work(worker.clone(), batch).await;
                processed.fetch_add(count, Ordering::Relaxed);
            }
        }));
    }
    for task in tasks {
        let _ = task.await;
    }
    StealOutcome {
        processed: processed.load(Ordering::Relaxed),
        cancelled: cancel.is_cancelled(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        sync::{
            atomic::{AtomicUsize, Ordering},
            Arc,
        },
        time::Duration,
    };
    #[tokio::test]
    async fn every_item_is_handled_once_across_multiple_batches() {
        let seen = Arc::new(Mutex::new(Vec::new()));
        let out = work_steal(
            (0..25).collect(),
            vec![0, 1, 2],
            8,
            CancellationToken::new(),
            {
                let seen = seen.clone();
                move |_, batch| {
                    let seen = seen.clone();
                    async move { seen.lock().await.extend(batch) }
                }
            },
        )
        .await;
        let mut got = seen.lock().await.clone();
        got.sort_unstable();
        assert_eq!(got, (0..25).collect::<Vec<_>>());
        assert_eq!(out.processed, 25);
        assert!(!out.cancelled);
    }
    #[tokio::test]
    async fn fast_worker_steals_strictly_more_work_without_locking_during_run() {
        let counts = Arc::new([AtomicUsize::new(0), AtomicUsize::new(0)]);
        work_steal(
            (0..40).collect(),
            vec![0usize, 1],
            1,
            CancellationToken::new(),
            {
                let counts = counts.clone();
                move |worker, batch| {
                    let counts = counts.clone();
                    async move {
                        if worker == 1 {
                            tokio::time::sleep(Duration::from_millis(3)).await;
                        }
                        counts[worker].fetch_add(batch.len(), Ordering::Relaxed);
                    }
                }
            },
        )
        .await;
        assert!(counts[0].load(Ordering::Relaxed) > counts[1].load(Ordering::Relaxed));
    }
    #[tokio::test]
    // Per-item cancellation belongs to the caller's batch closure (Piece B).
    async fn cancellation_stops_dequeuing_further_batches() {
        let cancel = CancellationToken::new();
        let runs = Arc::new(AtomicUsize::new(0));
        let out = work_steal((0..16).collect(), vec![0], 8, cancel.clone(), {
            let runs = runs.clone();
            move |_, batch| {
                let runs = runs.clone();
                let cancel = cancel.clone();
                async move {
                    runs.fetch_add(batch.len(), Ordering::Relaxed);
                    cancel.cancel()
                }
            }
        })
        .await;
        assert_eq!(out.processed, 8);
        assert_eq!(runs.load(Ordering::Relaxed), 8);
        assert!(out.cancelled);
    }
}
