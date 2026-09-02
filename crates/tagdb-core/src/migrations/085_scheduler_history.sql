CREATE TABLE IF NOT EXISTS scheduler_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          TEXT    NOT NULL,
    timestamp       REAL    NOT NULL,
    duration_ms     INTEGER NOT NULL DEFAULT 0,
    success         INTEGER NOT NULL,
    error           TEXT,
    result_summary  TEXT
);
CREATE INDEX IF NOT EXISTS idx_scheduler_history_job_ts
    ON scheduler_history(job_id, timestamp DESC);
