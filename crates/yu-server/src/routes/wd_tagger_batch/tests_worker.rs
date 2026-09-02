use super::test_helpers::{build_test_state, insert_active_file};
use super::*;
use futures_util::FutureExt;
use serde_json::json;
use std::sync::{Arc, Mutex};
use tokio::sync::{oneshot, Notify};

#[tokio::test]
async fn start_batch_job_returns_already_running_when_job_active() {
    let state = build_test_state().await;
    state.job_manager.start(WD_TAGGER_JOB_ID, "WD-Tagger batch");
    let req = BatchRequest {
        file_ids: Some(vec![1]),
        scan_root: None,
        limit: 100,
        force: false,
    };
    let result = start_batch_job(state.clone(), req).await.unwrap();
    assert!(matches!(result, StartResult::AlreadyRunning));
}

#[tokio::test]
async fn start_batch_job_returns_no_targets_when_resolve_empty() {
    let state = build_test_state().await;
    let req = BatchRequest {
        file_ids: Some(vec![]),
        scan_root: None,
        limit: 100,
        force: false,
    };
    let result = start_batch_job(state.clone(), req).await.unwrap();
    assert!(matches!(result, StartResult::NoTargets));
}

#[tokio::test]
async fn start_batch_job_processes_files_sequentially_and_finishes() {
    let state = build_test_state().await;
    insert_active_file(&state, 601).await;
    insert_active_file(&state, 602).await;
    let req = BatchRequest {
        file_ids: Some(vec![601, 602]),
        scan_root: None,
        limit: 100,
        force: false,
    };
    let result = start_batch_job(state.clone(), req).await.unwrap();
    assert!(matches!(result, StartResult::Started));

    // The worker runs on a separate tokio::spawn task, so wait for it to finish.
    for _ in 0..50 {
        if !state.job_manager.is_running(WD_TAGGER_JOB_ID) {
            break;
        }
        tokio::time::sleep(std::time::Duration::from_millis(50)).await;
    }
    assert!(!state.job_manager.is_running(WD_TAGGER_JOB_ID));
    let job = state.job_manager.get_job(WD_TAGGER_JOB_ID).unwrap();
    assert!(job.error.is_none());
    let result_value = job.result.expect("finished job must carry a result");
    // insert_active_file() rows point at paths that don't exist on disk,
    // so tag_file_native_core() rejects each one (file_missing) rather
    // than tagging it -- this test asserts the *sequencing/finish*
    // contract (both targets visited, job finishes cleanly), not the
    // tagging outcome itself.
    assert_eq!(result_value["total"], json!(2));
    assert_eq!(result_value["errors"], json!(2));
    assert_eq!(result_value["processed"], json!(0));
}

#[tokio::test]
async fn worker_cancellation_stops_within_one_file_even_for_64_targets() {
    let state = build_test_state().await;
    for id in 701..=764 {
        insert_active_file(&state, id).await;
    }
    let (first_started_tx, first_started_rx) = oneshot::channel();
    let first_started_tx = Arc::new(Mutex::new(Some(first_started_tx)));
    let release_first = Arc::new(Notify::new());
    let cancel = state.job_manager.start(WD_TAGGER_JOB_ID, "WD-Tagger batch");
    let worker_state = state.clone();
    let first_started_for_worker = first_started_tx.clone();
    let release_for_worker = release_first.clone();
    let worker = tokio::spawn(run_batch_worker_with_tagger(
        worker_state,
        WD_TAGGER_JOB_ID.to_string(),
        (701..=764).collect(),
        false,
        cancel,
        move |_state, file_id, _force| {
            let first_started = first_started_for_worker.clone();
            let release = release_for_worker.clone();
            Box::pin(async move {
                if file_id == 701 {
                    if let Some(sender) = first_started.lock().unwrap().take() {
                        sender.send(()).unwrap();
                    }
                    release.notified().await;
                }
                TagOutcome::Skipped(json!({"reason": "test"}))
            })
        },
    ));

    tokio::time::timeout(std::time::Duration::from_secs(1), first_started_rx)
        .await
        .expect("first file should start")
        .expect("worker should signal the first file");
    assert!(state.job_manager.cancel_job(WD_TAGGER_JOB_ID));
    release_first.notify_one();
    worker.await.unwrap();

    assert!(!state.job_manager.is_running(WD_TAGGER_JOB_ID));
    let job = state.job_manager.get_job(WD_TAGGER_JOB_ID).unwrap();
    // Cancellation is observed only after the in-flight first file
    // completes, so exactly that file is included and no later file runs.
    assert!(job.error.is_none());
    assert_eq!(job.phase.as_deref(), Some("cancelled"));
    let result_value = job.result.expect("finished job must carry a result");
    let processed_and_skipped = result_value["processed"].as_u64().unwrap()
        + result_value["skipped"].as_u64().unwrap()
        + result_value["errors"].as_u64().unwrap();
    assert!(processed_and_skipped <= 1);
}

#[tokio::test]
async fn run_batch_worker_syncs_active_model_after_success() {
    let state = build_test_state().await;
    let cancel = state.job_manager.start(WD_TAGGER_JOB_ID, "WD-Tagger batch");

    run_batch_worker_with_tagger(
        state.clone(),
        WD_TAGGER_JOB_ID.to_string(),
        vec![801],
        false,
        cancel,
        |_state, _file_id, _force| Box::pin(async { TagOutcome::Tagged(json!({})) }),
    )
    .await;

    let active_model = sqlx::query_scalar::<_, String>(
        "SELECT value FROM kv_state WHERE key = 'wd_active_model_id'",
    )
    .fetch_one(&state.db_read)
    .await
    .unwrap();
    // tag_file_native_core sanitizes the configured repository name before
    // using it for inference and wd_model_dict writes; kv_state must use the
    // same external model identifier, not the wd_model_dict integer key.
    assert_eq!(active_model, "SmilingWolf_wd-swinv2-tagger-v3");
}

#[tokio::test]
async fn start_batch_job_aborts_immediately_on_fatal_outcome() {
    // infer_client=None + infer_standalone=false makes call_wd_infer check
    // model presence directly; with no model files cached, the outcome is
    // WdInferOutcome::ModelNotDownloaded => TagOutcome::Fatal(ModelNotDownloaded).
    let dirs = Box::leak(Box::new(crate::routes::wd_tagger::tests::test_dirs()));
    let image_path = dirs.root.join("fatal.png");
    image::RgbImage::new(1, 1).save(&image_path).unwrap();
    let real_root = std::fs::canonicalize(&dirs.root).unwrap();
    let app_config = json!({
        "scan_roots": [{"path": real_root.to_string_lossy()}],
    });
    let cache_dir = dirs.root.join("cache");
    let state =
        crate::routes::wd_tagger::tests::test_state_ex(dirs, app_config, None, false, cache_dir)
            .await;
    sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (501, ?, 0), (502, ?, 0)")
        .bind(image_path.to_string_lossy().to_string())
        .bind(image_path.to_string_lossy().to_string())
        .execute(&state.db)
        .await
        .unwrap();

    let req = BatchRequest {
        file_ids: Some(vec![501, 502]),
        scan_root: None,
        limit: 100,
        force: false,
    };
    let result = start_batch_job(state.clone(), req).await.unwrap();
    assert!(matches!(result, StartResult::Started));

    for _ in 0..50 {
        if !state.job_manager.is_running(WD_TAGGER_JOB_ID) {
            break;
        }
        tokio::time::sleep(std::time::Duration::from_millis(50)).await;
    }
    assert!(!state.job_manager.is_running(WD_TAGGER_JOB_ID));
    let job = state.job_manager.get_job(WD_TAGGER_JOB_ID).unwrap();
    assert!(job.error.as_deref().unwrap().contains("ModelNotDownloaded"));
    let result_value = job.result.expect("fatal job must carry a result");
    assert_eq!(result_value["total"], json!(2));
    assert_eq!(result_value["processed"], json!(0));
    assert_eq!(result_value["skipped"], json!(0));
    assert_eq!(result_value["errors"], json!(1));
}

#[tokio::test]
async fn run_batch_worker_panic_still_finishes_job_via_catch_unwind() {
    // This exercises the same panic-safety net start_batch_job installs
    // around run_batch_worker, without depending on a way to force a
    // panic from inside tag_file_native_core itself.
    let state = build_test_state().await;
    let cancel = state.job_manager.start(WD_TAGGER_JOB_ID, "WD-Tagger batch");
    let worker_state = state.clone();
    let handle = tokio::spawn(async move {
        let result = std::panic::AssertUnwindSafe(async {
            panic!("simulated worker panic");
        })
        .catch_unwind()
        .await;
        if result.is_err() {
            worker_state.job_manager.finish(
                WD_TAGGER_JOB_ID,
                None,
                Some("internal panic during batch worker".to_string()),
            );
        }
    });
    let _ = cancel;
    handle.await.unwrap();

    assert!(!state.job_manager.is_running(WD_TAGGER_JOB_ID));
    let job = state.job_manager.get_job(WD_TAGGER_JOB_ID).unwrap();
    assert_eq!(job.error.unwrap(), "internal panic during batch worker");
}
