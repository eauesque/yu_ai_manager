use std::{collections::BTreeMap, path::Path};

use serde_json::{json, Value};
use sqlx::{Row, SqlitePool};

use crate::state::SharedState;

const DB_CHUNK_SIZE: usize = 500;

#[derive(Debug, Default, PartialEq, Eq)]
pub(crate) struct BatchStats {
    pub tagged: usize,
    pub empty: usize,
    pub errors: usize,
    pub done: usize,
}

impl BatchStats {
    fn record_tagged(&mut self, count: usize) {
        self.tagged += count;
        self.done += count;
        self.assert_invariant();
    }

    fn record_empty(&mut self) {
        self.empty += 1;
        self.done += 1;
        self.assert_invariant();
    }

    fn record_error(&mut self, count: usize) {
        self.errors += count;
        self.done += count;
        self.assert_invariant();
    }

    fn assert_invariant(&self) {
        assert_eq!(
            self.tagged + self.empty + self.errors,
            self.done,
            "Tagger mesh accounting invariant violated"
        );
    }
}

/// Processes one work-stealing batch. Cancellation is checked per item because
/// `work_steal` only stops dequeuing new batches after cancellation.
pub(crate) async fn run_tagger_batch_worker(
    state: &SharedState,
    peer: &crate::routes::tagger_servers::ResolvedTaggerPeer,
    batch: Vec<(i64, String)>,
    threshold: f64,
    cancel: &tokio_util::sync::CancellationToken,
) -> (BatchStats, BTreeMap<String, usize>) {
    let model_id = crate::routes::wd_tagger::configured_model_id_string(state);
    let config = crate::routes::auto_stubs::read_config_json(state);
    let tagger_config = &config["extensions"]["builtin-wd-tagger"];
    let general_thr = tagger_config["general_threshold"]
        .as_f64()
        .map(crate::num::narrow_f32)
        .unwrap_or(0.35_f32);
    let character_thr = tagger_config["character_threshold"]
        .as_f64()
        .map(crate::num::narrow_f32)
        .unwrap_or(0.85_f32);
    let mut stats = BatchStats::default();
    let mut dropped = BTreeMap::new();
    let mut writes = Vec::new();

    for (file_id, path) in batch {
        if cancel.is_cancelled() {
            break;
        }
        let raw_tags = match &peer.transport {
            // Python uses the lan-cowork tagger engine; Rust uses yu-infer.
            // The sidecar pre-filters at configured thresholds before request filtering.
            None => match crate::routes::wd_infer::call_wd_infer(
                state,
                Path::new(&path),
                &model_id,
                general_thr,
                character_thr,
            )
            .await
            {
                crate::routes::wd_infer::WdInferOutcome::Success(result) => Value::Array(
                    result
                        .tags
                        .into_iter()
                        .map(|tag| json!({"tag": tag.tag, "confidence": tag.confidence}))
                        .collect(),
                ),
                outcome => {
                    record_drop(&mut stats, &mut dropped, local_failure_reason(&outcome), 1);
                    continue;
                }
            },
            Some(remote) => match crate::tagger_peer_client::tag_remote_image(
                &state.db,
                remote,
                Path::new(&path),
            )
            .await
            {
                Ok(tags) => Value::Array(tags),
                Err(_) => {
                    record_drop(&mut stats, &mut dropped, "remote_error", 1);
                    continue;
                }
            },
        };
        let (tags, reason) = filter_valid_tagger_tags(&raw_tags, threshold);
        if let Some(reason) = reason {
            record_drop(&mut stats, &mut dropped, &reason, 1);
        } else if tags.is_empty() {
            stats.record_empty();
        } else {
            writes.push((file_id, tags, peer_source(&peer.name)));
        }
    }

    if !writes.is_empty() {
        let count = writes.len();
        record_write_result(
            &mut stats,
            &mut dropped,
            count,
            save_tagger_tags_batch(&state.db, &writes).await.is_ok(),
        );
    }
    (stats, dropped)
}

fn peer_source(name: &str) -> String {
    format!("mesh:{name}")
}

fn local_failure_reason(outcome: &crate::routes::wd_infer::WdInferOutcome) -> &'static str {
    match outcome {
        crate::routes::wd_infer::WdInferOutcome::PathRejected => "path_rejected",
        crate::routes::wd_infer::WdInferOutcome::ModelNotDownloaded => "model_not_downloaded",
        crate::routes::wd_infer::WdInferOutcome::BackendError(_) => "backend_error",
        crate::routes::wd_infer::WdInferOutcome::Unreachable(_) => "unreachable",
        // Callers only reach here on a failure outcome. Naming the surprise is
        // better than unwinding a batch worker over it: a wrong reason string
        // shows up in the stats, a panic loses the whole batch.
        crate::routes::wd_infer::WdInferOutcome::Success(_) => "unexpected_success",
    }
}

fn record_drop(
    stats: &mut BatchStats,
    dropped: &mut BTreeMap<String, usize>,
    reason: &str,
    count: usize,
) {
    *dropped.entry(reason.to_owned()).or_default() += count;
    stats.record_error(count);
}

fn record_write_result(
    stats: &mut BatchStats,
    dropped: &mut BTreeMap<String, usize>,
    count: usize,
    saved: bool,
) {
    if saved {
        stats.record_tagged(count);
    } else {
        record_drop(stats, dropped, "save_fail", count);
    }
}

async fn save_tagger_tags_batch(
    db: &SqlitePool,
    items: &[(i64, Vec<Value>, String)],
) -> Result<(), sqlx::Error> {
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs() as i64;
    let mut tx = db.begin().await?;
    for (file_id, tags, source) in items {
        for tag in tags {
            sqlx::query(
                "INSERT INTO file_hailo_tags (file_id, tag_name, confidence, source, created_at) \
                 VALUES (?, ?, ?, ?, ?) \
                 ON CONFLICT(file_id, tag_name) DO UPDATE SET \
                   confidence = excluded.confidence, source = excluded.source, created_at = excluded.created_at",
            )
            .bind(file_id)
            .bind(tag["tag"].as_str().unwrap_or_default())
            .bind(tag["confidence"].as_f64().unwrap_or_default())
            .bind(source)
            .bind(now)
            .execute(&mut *tx)
            .await?;
        }
    }
    tx.commit().await
}

pub(crate) async fn get_untagged_file_ids(
    db: &SqlitePool,
    limit: i64,
) -> Result<Vec<i64>, sqlx::Error> {
    sqlx::query_scalar("SELECT f.id FROM files f WHERE f.is_deleted = 0 AND NOT EXISTS (SELECT 1 FROM file_hailo_tags h WHERE h.file_id = f.id) ORDER BY f.id LIMIT ?")
        .bind(limit)
        .fetch_all(db)
        .await
}

pub(crate) async fn filter_untagged(
    db: &SqlitePool,
    file_ids: &[i64],
) -> Result<Vec<i64>, sqlx::Error> {
    let mut result = Vec::new();
    for chunk in file_ids.chunks(DB_CHUNK_SIZE) {
        let placeholders = std::iter::repeat_n("?", chunk.len())
            .collect::<Vec<_>>()
            .join(",");
        let sql = format!("SELECT f.id FROM files f WHERE f.id IN ({placeholders}) AND f.is_deleted = 0 AND NOT EXISTS (SELECT 1 FROM file_hailo_tags h WHERE h.file_id = f.id)");
        let mut query = sqlx::query(&sql);
        for id in chunk {
            query = query.bind(id);
        }
        let active = query
            .fetch_all(db)
            .await?
            .into_iter()
            .map(|row| row.get::<i64, _>(0))
            .collect::<std::collections::HashSet<_>>();
        result.extend(chunk.iter().copied().filter(|id| active.contains(id)));
    }
    Ok(result)
}

pub(crate) async fn iter_active_paths(
    db: &SqlitePool,
    file_ids: &[i64],
) -> Result<Vec<(i64, String)>, sqlx::Error> {
    let mut result = Vec::new();
    for chunk in file_ids.chunks(DB_CHUNK_SIZE) {
        let placeholders = std::iter::repeat_n("?", chunk.len())
            .collect::<Vec<_>>()
            .join(",");
        let sql =
            format!("SELECT id, path FROM files WHERE id IN ({placeholders}) AND is_deleted = 0");
        let mut query = sqlx::query(&sql);
        for id in chunk {
            query = query.bind(id);
        }
        let paths = query
            .fetch_all(db)
            .await?
            .into_iter()
            .map(|row| (row.get::<i64, _>(0), row.get::<String, _>(1)))
            .collect::<std::collections::HashMap<_, _>>();
        result.extend(
            chunk
                .iter()
                .filter_map(|id| paths.get(id).map(|path| (*id, path.clone()))),
        );
    }
    Ok(result)
}

pub(crate) fn filter_valid_tagger_tags(
    raw_tags: &Value,
    threshold: f64,
) -> (Vec<Value>, Option<String>) {
    let Some(tags) = raw_tags.as_array() else {
        return (
            Vec::new(),
            Some(
                if raw_tags.is_null() {
                    "none"
                } else {
                    "not_list"
                }
                .into(),
            ),
        );
    };
    let mut filtered = Vec::new();
    for (index, item) in tags.iter().enumerate() {
        let Some(item) = item.as_object() else {
            return (Vec::new(), Some(format!("invalid_item_{index}")));
        };
        let Some(tag) = item
            .get("tag")
            .and_then(Value::as_str)
            .filter(|tag| !tag.is_empty())
        else {
            return (Vec::new(), Some(format!("invalid_tag_{index}")));
        };
        let Some(confidence) = item.get("confidence").and_then(Value::as_f64) else {
            return (Vec::new(), Some(format!("invalid_confidence_{index}")));
        };
        if confidence >= threshold {
            filtered.push(json!({"tag": tag, "confidence": confidence}));
        }
    }
    (filtered, None)
}

pub(crate) fn log_tagger_dropped(context: &str, counts: &BTreeMap<String, usize>) {
    let total: usize = counts.values().sum();
    if total > 0 {
        tracing::warn!(
            "{context} dropped {total} items: {}",
            counts
                .iter()
                .map(|(reason, count)| format!("{reason}={count}"))
                .collect::<Vec<_>>()
                .join(", ")
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use sqlx::sqlite::SqlitePoolOptions;

    async fn test_db() -> SqlitePool {
        let db = SqlitePoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .unwrap();
        sqlx::query("CREATE TABLE files (id INTEGER PRIMARY KEY, path TEXT NOT NULL, is_deleted INTEGER NOT NULL)").execute(&db).await.unwrap();
        sqlx::query("CREATE TABLE file_hailo_tags (file_id INTEGER NOT NULL, tag_name TEXT, confidence REAL, source TEXT, created_at INTEGER, UNIQUE(file_id, tag_name))")
            .execute(&db)
            .await
            .unwrap();
        db
    }

    async fn insert_file(db: &SqlitePool, id: i64, deleted: bool) {
        sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (?, ?, ?)")
            .bind(id)
            .bind(format!("/{id}.jpg"))
            .bind(deleted)
            .execute(db)
            .await
            .unwrap();
    }

    #[test]
    fn filter_valid_tagger_tags_matches_python_drop_reasons_and_rejects_whole_list() {
        assert_eq!(
            filter_valid_tagger_tags(&Value::Null, 0.35),
            (vec![], Some("none".into()))
        );
        assert_eq!(
            filter_valid_tagger_tags(&json!({}), 0.35),
            (vec![], Some("not_list".into()))
        );
        assert_eq!(
            filter_valid_tagger_tags(&json!(["bad"]), 0.35),
            (vec![], Some("invalid_item_0".into()))
        );
        assert_eq!(
            filter_valid_tagger_tags(&json!([{"tag": "", "confidence": 1.0}]), 0.35),
            (vec![], Some("invalid_tag_0".into()))
        );
        assert_eq!(
            filter_valid_tagger_tags(&json!([{"tag": "a", "confidence": true}]), 0.35),
            (vec![], Some("invalid_confidence_0".into()))
        );
        assert_eq!(
            filter_valid_tagger_tags(
                &json!([{"tag": "good", "confidence": 0.9}, {"tag": "", "confidence": 0.9}]),
                0.35
            ),
            (vec![], Some("invalid_tag_1".into()))
        );
    }

    #[test]
    fn filter_valid_tagger_tags_filters_only_after_full_validation() {
        assert_eq!(
            filter_valid_tagger_tags(
                &json!([{"tag": "low", "confidence": 0.34}, {"tag": "high", "confidence": 0.35}]),
                0.35
            ),
            (vec![json!({"tag": "high", "confidence": 0.35})], None)
        );
    }

    #[tokio::test]
    async fn db_helpers_chunk_at_500_preserve_input_order_and_skip_deleted() {
        let db = test_db().await;
        for id in 1..=502 {
            insert_file(&db, id, id == 501).await;
        }
        sqlx::query("INSERT INTO file_hailo_tags (file_id) VALUES (2)")
            .execute(&db)
            .await
            .unwrap();
        let ids = (1..=502).rev().collect::<Vec<_>>();
        let expected = ids
            .iter()
            .copied()
            .filter(|id| *id != 2 && *id != 501)
            .collect::<Vec<_>>();
        assert_eq!(filter_untagged(&db, &ids).await.unwrap(), expected);
        assert_eq!(
            iter_active_paths(&db, &ids)
                .await
                .unwrap()
                .into_iter()
                .map(|(id, _)| id)
                .collect::<Vec<_>>(),
            ids.iter()
                .copied()
                .filter(|id| *id != 501)
                .collect::<Vec<_>>()
        );
    }

    #[tokio::test]
    async fn get_untagged_file_ids_orders_and_limits_active_files() {
        let db = test_db().await;
        insert_file(&db, 3, false).await;
        insert_file(&db, 1, false).await;
        insert_file(&db, 2, true).await;
        sqlx::query("INSERT INTO file_hailo_tags (file_id) VALUES (3)")
            .execute(&db)
            .await
            .unwrap();
        assert_eq!(get_untagged_file_ids(&db, 10).await.unwrap(), vec![1]);
    }

    #[test]
    fn local_non_success_outcomes_count_errors_without_aborting() {
        let outcomes = [
            crate::routes::wd_infer::WdInferOutcome::PathRejected,
            crate::routes::wd_infer::WdInferOutcome::ModelNotDownloaded,
            crate::routes::wd_infer::WdInferOutcome::BackendError("down".into()),
            crate::routes::wd_infer::WdInferOutcome::Unreachable("down".into()),
        ];
        let mut stats = BatchStats::default();
        let mut dropped = BTreeMap::new();
        for outcome in &outcomes {
            record_drop(&mut stats, &mut dropped, local_failure_reason(outcome), 1);
        }
        assert_eq!(
            stats,
            BatchStats {
                tagged: 0,
                empty: 0,
                errors: 4,
                done: 4
            }
        );
        assert_eq!(dropped["backend_error"], 1);
        assert_eq!(dropped["unreachable"], 1);
    }

    #[test]
    fn empty_filtered_list_counts_empty_not_tagged() {
        let (tags, reason) =
            filter_valid_tagger_tags(&json!([{"tag": "low", "confidence": 0.1}]), 0.35);
        assert!(tags.is_empty());
        assert!(reason.is_none());
        let mut stats = BatchStats::default();
        stats.record_empty();
        assert_eq!(
            stats,
            BatchStats {
                tagged: 0,
                empty: 1,
                errors: 0,
                done: 1
            }
        );
    }

    #[test]
    #[should_panic(expected = "Tagger mesh accounting invariant violated")]
    fn accounting_invariant_catches_miscounted_branch() {
        BatchStats {
            tagged: 1,
            empty: 0,
            errors: 0,
            done: 0,
        }
        .assert_invariant();
    }

    #[test]
    fn failed_batch_write_counts_no_tags_and_all_items_as_errors() {
        let mut stats = BatchStats::default();
        let mut dropped = BTreeMap::new();
        record_write_result(&mut stats, &mut dropped, 3, false);
        assert_eq!(
            stats,
            BatchStats {
                tagged: 0,
                empty: 0,
                errors: 3,
                done: 3
            }
        );
        assert_eq!(dropped["save_fail"], 3);
    }

    #[test]
    fn successful_batch_write_counts_tags_only_after_success() {
        let mut stats = BatchStats::default();
        let mut dropped = BTreeMap::new();
        record_write_result(&mut stats, &mut dropped, 2, true);
        assert_eq!(
            stats,
            BatchStats {
                tagged: 2,
                empty: 0,
                errors: 0,
                done: 2
            }
        );
        assert!(dropped.is_empty());
    }

    #[tokio::test]
    async fn batch_write_uses_mesh_peer_source() {
        let db = test_db().await;
        save_tagger_tags_batch(
            &db,
            &[(
                7,
                vec![json!({"tag": "cat", "confidence": 0.9})],
                "mesh:edge-a".into(),
            )],
        )
        .await
        .unwrap();
        let source: String =
            sqlx::query_scalar("SELECT source FROM file_hailo_tags WHERE file_id = 7")
                .fetch_one(&db)
                .await
                .unwrap();
        assert_eq!(source, "mesh:edge-a");
    }

    #[test]
    fn peer_source_is_mesh_name() {
        assert_eq!(peer_source("edge-a"), "mesh:edge-a");
    }
}
