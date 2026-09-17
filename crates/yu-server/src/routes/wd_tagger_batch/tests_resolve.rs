use super::test_helpers::{
    build_test_state, insert_active_file, insert_active_tagged_file, insert_deleted_file,
};
use super::*;

#[tokio::test]
async fn resolve_targets_rejects_limit_over_500() {
    let state = build_test_state().await;
    let req = BatchRequest {
        file_ids: Some(vec![1]),
        scan_root: None,
        limit: 501,
        force: false,
    };
    let result = resolve_targets(&state, &req).await;
    assert!(matches!(result, Err(BatchError::InvalidValue("limit"))));
}

#[tokio::test]
async fn resolve_targets_rejects_negative_limit() {
    let state = build_test_state().await;
    let req = BatchRequest {
        file_ids: Some(vec![1]),
        scan_root: None,
        limit: -1,
        force: false,
    };
    let result = resolve_targets(&state, &req).await;
    assert!(matches!(result, Err(BatchError::InvalidValue("limit"))));
}

#[tokio::test]
async fn resolve_targets_file_ids_wins_over_scan_root() {
    let state = build_test_state().await;
    insert_active_file(&state, 101).await;
    insert_active_file(&state, 102).await;
    let req = BatchRequest {
        file_ids: Some(vec![101, 102]),
        scan_root: Some("/some/other/root".into()),
        limit: 100,
        force: false,
    };
    let (ids, scope) = resolve_targets(&state, &req).await.unwrap();
    assert_eq!(scope, "batch");
    assert_eq!(ids, vec![101, 102]);
}

#[tokio::test]
async fn resolve_targets_file_ids_filters_deleted_before_limit() {
    let state = build_test_state().await;
    insert_active_file(&state, 201).await;
    insert_deleted_file(&state, 202).await;
    insert_active_file(&state, 203).await;
    let req = BatchRequest {
        file_ids: Some(vec![201, 202, 203]),
        scan_root: None,
        limit: 2,
        force: false,
    };
    let (ids, _) = resolve_targets(&state, &req).await.unwrap();
    // 202 is filtered out (deleted) before limit=2 is applied, so both
    // remaining active ids [201, 203] make it through. If limit were
    // applied before the filter this would incorrectly yield [201].
    assert_eq!(ids, vec![201, 203]);
}

#[tokio::test]
async fn resolve_targets_file_ids_limit_zero_returns_all_active_ids() {
    let state = build_test_state().await;
    insert_active_file(&state, 211).await;
    insert_deleted_file(&state, 212).await;
    insert_active_file(&state, 213).await;
    let req = BatchRequest {
        file_ids: Some(vec![211, 212, 213]),
        scan_root: None,
        limit: 0,
        force: false,
    };

    let (ids, scope) = resolve_targets(&state, &req).await.unwrap();

    assert_eq!(scope, "batch");
    assert_eq!(ids, vec![211, 213]);
}

#[tokio::test]
async fn resolve_targets_backfill_excludes_already_tagged_unless_force() {
    let state = build_test_state().await;
    insert_active_file(&state, 301).await;
    // The shared fixture (`build_test_state`) pre-populates files 1/2,
    // neither of which is tagged under the *configured* default model
    // (only under fixture model-a/model-b) — soft-delete them so this
    // test only sees the files it inserted itself.
    sqlx::query("UPDATE files SET is_deleted = 1 WHERE id IN (1, 2)")
        .execute(&state.db)
        .await
        .unwrap();
    insert_active_tagged_file(&state, 302).await;
    let req = BatchRequest {
        file_ids: None,
        scan_root: None,
        limit: 100,
        force: false,
    };
    let (ids, scope) = resolve_targets(&state, &req).await.unwrap();
    assert_eq!(scope, "backfill");
    assert_eq!(ids, vec![301]);

    let req_forced = BatchRequest {
        file_ids: None,
        scan_root: None,
        limit: 100,
        force: true,
    };
    let (mut ids2, _) = resolve_targets(&state, &req_forced).await.unwrap();
    ids2.sort();
    assert_eq!(ids2, vec![301, 302]);
}

#[tokio::test]
async fn resolve_targets_backfill_limit_zero_returns_all_targets() {
    let state = build_test_state().await;
    sqlx::query("UPDATE files SET is_deleted = 1")
        .execute(&state.db)
        .await
        .unwrap();
    for id in 311..=313 {
        insert_active_file(&state, id).await;
    }
    let req = BatchRequest {
        file_ids: None,
        scan_root: None,
        limit: 0,
        force: false,
    };

    let (mut ids, scope) = resolve_targets(&state, &req).await.unwrap();

    ids.sort();
    assert_eq!(scope, "backfill");
    assert_eq!(ids, vec![311, 312, 313]);
}

#[tokio::test]
async fn resolve_targets_backfill_scan_root_filters_by_path_prefix() {
    let state = build_test_state().await;
    insert_active_file(&state, 401).await; // path: /img/batch-401.png
    sqlx::query("UPDATE files SET path = ? WHERE id = ?")
        .bind("/library/root_a/inside.png")
        .bind(401)
        .execute(&state.db)
        .await
        .unwrap();
    insert_active_file(&state, 402).await;
    sqlx::query("UPDATE files SET path = ? WHERE id = ?")
        .bind("/library/root_b/other.png")
        .bind(402)
        .execute(&state.db)
        .await
        .unwrap();

    let req = BatchRequest {
        file_ids: None,
        scan_root: Some("/library/root_a".into()),
        limit: 100,
        force: false,
    };
    let (ids, scope) = resolve_targets(&state, &req).await.unwrap();
    assert_eq!(scope, "backfill");
    assert_eq!(ids, vec![401]);
}

#[tokio::test]
async fn resolve_targets_backfill_scan_root_with_trailing_separator_matches_paths() {
    let state = build_test_state().await;
    insert_active_file(&state, 411).await;
    sqlx::query("UPDATE files SET path = ? WHERE id = ?")
        .bind("/library/root_a/inside.png")
        .bind(411)
        .execute(&state.db)
        .await
        .unwrap();

    let req = BatchRequest {
        file_ids: None,
        scan_root: Some("/library/root_a/".into()),
        limit: 100,
        force: false,
    };
    let (ids, scope) = resolve_targets(&state, &req).await.unwrap();

    assert_eq!(scope, "backfill");
    assert_eq!(ids, vec![411]);
}

#[tokio::test]
async fn resolve_targets_backfill_scan_root_of_only_separators_is_treated_as_unset() {
    let state = build_test_state().await;
    // The shared fixture pre-populates files 1/2 which are not tagged under
    // the configured default model (see other tests in this file) -- soft
    // delete them so this test only sees the file it inserted itself.
    sqlx::query("UPDATE files SET is_deleted = 1 WHERE id IN (1, 2)")
        .execute(&state.db)
        .await
        .unwrap();
    insert_active_file(&state, 421).await;
    sqlx::query("UPDATE files SET path = ? WHERE id = ?")
        .bind("/anywhere/else.png")
        .bind(421)
        .execute(&state.db)
        .await
        .unwrap();

    for root in ["/", "\\"] {
        let req = BatchRequest {
            file_ids: None,
            scan_root: Some(root.into()),
            limit: 100,
            force: false,
        };
        let (ids, scope) = resolve_targets(&state, &req).await.unwrap();
        assert_eq!(scope, "backfill");
        assert_eq!(
            ids,
            vec![421],
            "scan_root={root:?} should apply no LIKE filter"
        );
    }
}

#[test]
fn scan_root_like_patterns_escapes_wildcards_and_covers_both_separators() {
    let (forward, backward) = scan_root_like_patterns("/lib/50%_off");
    assert_eq!(forward, "/lib/50~%~_off/%");
    assert_eq!(backward, "\\lib\\50~%~_off\\%");
}
