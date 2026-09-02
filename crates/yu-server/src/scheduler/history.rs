use sqlx::SqlitePool;
use std::collections::HashMap;

#[derive(Debug, Clone, serde::Serialize)]
pub struct HistoryRecord {
    pub job_id: String,
    pub timestamp: f64,
    pub duration_ms: i64,
    pub success: bool,
    pub error: Option<String>,
    pub result_summary: Option<String>,
}

impl<'r> sqlx::FromRow<'r, sqlx::sqlite::SqliteRow> for HistoryRecord {
    fn from_row(row: &'r sqlx::sqlite::SqliteRow) -> Result<Self, sqlx::Error> {
        use sqlx::Row;
        Ok(Self {
            job_id: row.try_get("job_id")?,
            timestamp: row.try_get("timestamp")?,
            duration_ms: row.try_get("duration_ms")?,
            success: row.try_get::<i64, _>("success")? != 0,
            error: row.try_get("error")?,
            result_summary: row.try_get("result_summary")?,
        })
    }
}

pub async fn record_execution(
    db: &SqlitePool,
    job_id: &str,
    success: bool,
    error: Option<&str>,
    result_summary: Option<&str>,
) -> Result<(), sqlx::Error> {
    let ts = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64();
    sqlx::query(
        "INSERT INTO scheduler_history (job_id, timestamp, duration_ms, success, error, result_summary) \
         VALUES (?, ?, 0, ?, ?, ?)",
    )
    .bind(job_id)
    .bind(ts)
    .bind(if success { 1i64 } else { 0i64 })
    .bind(error)
    .bind(result_summary)
    .execute(db)
    .await?;
    Ok(())
}

pub async fn get_recent_history(
    db: &SqlitePool,
    limit: i64,
) -> Result<Vec<HistoryRecord>, sqlx::Error> {
    let rows = sqlx::query_as::<_, HistoryRecord>(
        "SELECT job_id, timestamp, duration_ms, success, error, result_summary \
         FROM scheduler_history \
         ORDER BY timestamp DESC \
         LIMIT ?",
    )
    .bind(limit)
    .fetch_all(db)
    .await?;
    Ok(rows)
}

/// Most recent record per job_id, keyed by job_id.
pub async fn get_last_for_jobs(
    db: &SqlitePool,
    job_ids: &[&str],
) -> Result<HashMap<String, HistoryRecord>, sqlx::Error> {
    if job_ids.is_empty() {
        return Ok(HashMap::new());
    }
    let placeholders = job_ids.iter().map(|_| "?").collect::<Vec<_>>().join(", ");
    let sql = format!(
        "SELECT job_id, timestamp, duration_ms, success, error, result_summary \
         FROM scheduler_history \
         WHERE job_id IN ({placeholders}) \
         GROUP BY job_id \
         HAVING timestamp = MAX(timestamp)"
    );
    let mut q = sqlx::query_as::<_, HistoryRecord>(&sql);
    for id in job_ids {
        q = q.bind(*id);
    }
    let rows: Vec<HistoryRecord> = q.fetch_all(db).await?;
    Ok(rows.into_iter().map(|r| (r.job_id.clone(), r)).collect())
}
