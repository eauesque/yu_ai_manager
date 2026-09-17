use sqlx::SqlitePool;

pub type JobResult = Result<Option<String>, String>;

pub async fn run_db_analyze(db: &SqlitePool) -> JobResult {
    sqlx::query("PRAGMA analysis_limit=1000")
        .execute(db)
        .await
        .map_err(|e| e.to_string())?;
    sqlx::query("ANALYZE")
        .execute(db)
        .await
        .map_err(|e| e.to_string())?;
    Ok(Some("ANALYZE complete".to_string()))
}

pub async fn run_db_integrity_check(db: &SqlitePool) -> JobResult {
    let result: String = sqlx::query_scalar("PRAGMA integrity_check")
        .fetch_one(db)
        .await
        .map_err(|e| e.to_string())?;
    if result == "ok" {
        Ok(Some("integrity_check: ok".to_string()))
    } else {
        Err(format!("integrity_check failed: {result}"))
    }
}

pub async fn run_db_compress_old_raw_responses(db: &SqlitePool) -> JobResult {
    let result = sqlx::query(
        "UPDATE analysis SET raw_response = NULL \
         WHERE analyzed_at < strftime('%s','now','-60 days') AND raw_response IS NOT NULL",
    )
    .execute(db)
    .await
    .map_err(|e| e.to_string())?;
    Ok(Some(format!("{} rows nullified", result.rows_affected())))
}

pub async fn run_db_prune_old_webhook_deliveries(db: &SqlitePool) -> JobResult {
    sqlx::query(
        "DELETE FROM webhook_deliveries WHERE delivered_at < strftime('%s','now','-90 days')",
    )
    .execute(db)
    .await
    .map_err(|e| e.to_string())?;
    Ok(Some("webhook deliveries pruned".to_string()))
}

/// PASSIVE checkpoint: non-blocking, does not evict readers/writers. Keeps the
/// WAL file bounded without the exclusivity cost of RESTART/TRUNCATE.
pub async fn run_db_wal_checkpoint(db: &SqlitePool) -> JobResult {
    sqlx::query("PRAGMA wal_checkpoint(PASSIVE)")
        .execute(db)
        .await
        .map_err(|e| e.to_string())?;
    Ok(Some("WAL checkpoint (PASSIVE) complete".to_string()))
}

/// VACUUM must run on a dedicated connection outside the pool (SQLite limitation).
pub async fn run_db_vacuum(db_path: &str) -> JobResult {
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
    use std::str::FromStr;
    let url = format!("sqlite:{db_path}");
    let opts = SqliteConnectOptions::from_str(&url)
        .map_err(|e| e.to_string())?
        .busy_timeout(std::time::Duration::from_millis(10_000));
    let pool = SqlitePoolOptions::new()
        .max_connections(1)
        .connect_with(opts)
        .await
        .map_err(|e| e.to_string())?;
    sqlx::query("VACUUM")
        .execute(&pool)
        .await
        .map_err(|e| e.to_string())?;
    pool.close().await;
    Ok(Some("VACUUM complete".to_string()))
}
