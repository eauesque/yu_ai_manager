use std::future::Future;

use crate::state::SharedState;

/// Spawn a job body and finish its run on every exit path.
pub fn spawn_guarded<F>(state: SharedState, job_id: &'static str, run_id: String, fut: F)
where
    F: Future<Output = Result<serde_json::Value, String>> + Send + 'static,
{
    let (done, _) = tokio::sync::oneshot::channel();
    spawn_guarded_with_done(state, job_id, run_id, fut, done);
}

/// Like [`spawn_guarded`], but signals after the run has been finished.
pub fn spawn_guarded_with_done<F>(
    state: SharedState,
    job_id: &'static str,
    run_id: String,
    fut: F,
    done: tokio::sync::oneshot::Sender<()>,
) where
    F: Future<Output = Result<serde_json::Value, String>> + Send + 'static,
{
    use futures_util::FutureExt as _;

    tokio::spawn(async move {
        match std::panic::AssertUnwindSafe(fut).catch_unwind().await {
            Ok(Ok(value)) => {
                state
                    .job_manager
                    .finish_run(job_id, &run_id, Some(value), None);
            }
            Ok(Err(message)) => {
                state
                    .job_manager
                    .finish_run(job_id, &run_id, None, Some(message));
            }
            Err(_) => {
                state.job_manager.finish_run(
                    job_id,
                    &run_id,
                    None,
                    Some("internal panic during OCR job".to_string()),
                );
            }
        }
        let _ = done.send(());
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::jobs::StartOutcome;

    #[tokio::test]
    async fn panicking_body_still_finishes_the_job() {
        let state = crate::state::semantic_test_state(false).await;
        let StartOutcome::Started(handle) = state.job_manager.start_or_current("ocr", "t", "run-1")
        else {
            panic!("first start must succeed");
        };
        let (tx, rx) = tokio::sync::oneshot::channel();
        spawn_guarded_with_done(
            state.clone(),
            "ocr",
            handle.run_id,
            async { panic!("boom") },
            tx,
        );
        rx.await.expect("guard must signal completion");
        assert!(!state.job_manager.is_running("ocr"));
        assert!(matches!(
            state.job_manager.start_or_current("ocr", "next", "run-2"),
            StartOutcome::Started(_)
        ));
    }

    #[tokio::test]
    async fn a_late_guard_does_not_publish_its_result_as_the_next_runs() {
        let state = crate::state::semantic_test_state(false).await;
        let StartOutcome::Started(a) = state.job_manager.start_or_current("ocr", "a", "run-A")
        else {
            panic!("A must start");
        };
        state.job_manager.finish_cancelled("ocr", None);
        let StartOutcome::Started(_) = state.job_manager.start_or_current("ocr", "b", "run-B")
        else {
            panic!("B must start");
        };
        let (tx, rx) = tokio::sync::oneshot::channel();
        spawn_guarded_with_done(
            state.clone(),
            "ocr",
            a.run_id,
            async { Ok(serde_json::json!({"from": "A"})) },
            tx,
        );
        rx.await.expect("guard must signal completion");
        let job = state.job_manager.get_job("ocr").expect("job present");
        assert!(job.running);
        assert_eq!(job.detail.as_deref(), Some("run-B"));
        assert!(job.result.is_none());
    }

    #[tokio::test]
    async fn error_return_finishes_with_the_message() {
        let state = crate::state::semantic_test_state(false).await;
        let StartOutcome::Started(handle) = state.job_manager.start_or_current("ocr", "t", "run-1")
        else {
            panic!("first start must succeed");
        };
        let (tx, rx) = tokio::sync::oneshot::channel();
        spawn_guarded_with_done(
            state.clone(),
            "ocr",
            handle.run_id,
            async { Err("nope".to_string()) },
            tx,
        );
        rx.await.expect("guard must signal completion");
        let job = state.job_manager.get_job("ocr").expect("job present");
        assert_eq!(job.error.as_deref(), Some("nope"));
        assert!(!job.running);
    }
}
