"""Second half of migration 56 CREATE TABLE payload."""

TABLES_SQL_B = """
CREATE TABLE IF NOT EXISTS chat_decisions (
    id              INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    message_id      INTEGER,
    decision_text   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_decisions_conv ON chat_decisions(conversation_id);

CREATE TABLE IF NOT EXISTS chat_entities (
    id              INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    message_id      INTEGER,
    entity_type     TEXT NOT NULL,
    entity_value    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_entities_type_value ON chat_entities(entity_type, entity_value);
CREATE INDEX IF NOT EXISTS idx_chat_entities_conv ON chat_entities(conversation_id);

CREATE TABLE IF NOT EXISTS chat_topics (
    id              INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    topic           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_topics_topic ON chat_topics(topic);

CREATE TABLE IF NOT EXISTS file_ocr_results (
    id              INTEGER PRIMARY KEY,
    file_id         INTEGER NOT NULL,
    engine          TEXT NOT NULL,
    task            TEXT NOT NULL DEFAULT 'ocr',
    regions_json    TEXT,
    full_text       TEXT,
    structured_json TEXT,
    language        TEXT DEFAULT '',
    created_at      INTEGER NOT NULL,
    FOREIGN KEY (file_id) REFERENCES files(id),
    UNIQUE(file_id, engine, task)
);
CREATE INDEX IF NOT EXISTS idx_ocr_file_id ON file_ocr_results(file_id);

CREATE TABLE IF NOT EXISTS file_translations (
    id                       INTEGER PRIMARY KEY,
    ocr_result_id            INTEGER NOT NULL,
    target_lang              TEXT NOT NULL,
    translated_text          TEXT,
    region_translations_json TEXT,
    engine                   TEXT DEFAULT '',
    created_at               INTEGER NOT NULL,
    FOREIGN KEY (ocr_result_id) REFERENCES file_ocr_results(id),
    UNIQUE(ocr_result_id, target_lang)
);

CREATE TABLE IF NOT EXISTS trophies (
    id             INTEGER PRIMARY KEY,
    trophy_type    TEXT NOT NULL UNIQUE,
    title          TEXT NOT NULL,
    tier           TEXT NOT NULL DEFAULT 'gold',
    category       TEXT NOT NULL DEFAULT 'milestone',
    achieved_month TEXT,
    achieved_at    INTEGER NOT NULL,
    metadata       TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS monthly_stats_cache (
    month      TEXT NOT NULL,
    stat_key   TEXT NOT NULL,
    stat_value TEXT NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (month, stat_key)
);

CREATE TABLE IF NOT EXISTS agent_action_journal (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id       TEXT NOT NULL,
    timestamp        TEXT NOT NULL,
    tool_name        TEXT NOT NULL,
    params_json      TEXT NOT NULL DEFAULT '{}',
    result_summary   TEXT,
    status           TEXT NOT NULL DEFAULT 'success',
    duration_ms      INTEGER DEFAULT 0,
    caller_info      TEXT DEFAULT '',
    affected_count   INTEGER DEFAULT 0,
    reversible       INTEGER DEFAULT 0,
    undo_params_json TEXT,
    undone           INTEGER DEFAULT 0,
    undone_at        TEXT
);
CREATE INDEX IF NOT EXISTS idx_agent_journal_session ON agent_action_journal(session_id);
CREATE INDEX IF NOT EXISTS idx_agent_journal_time ON agent_action_journal(timestamp);

CREATE TABLE IF NOT EXISTS audit_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp        TEXT NOT NULL,
    event_type       TEXT NOT NULL,
    source           TEXT NOT NULL,
    target           TEXT,
    severity         TEXT NOT NULL,
    reported_to      TEXT NOT NULL,
    detail_json      TEXT,
    user_acknowledged INTEGER DEFAULT 0,
    acknowledged_at  TEXT,
    prev_hash        TEXT DEFAULT '',
    entry_hash       TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_audit_log_event_type ON audit_log(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_log_severity ON audit_log(severity);

CREATE TABLE IF NOT EXISTS bluesky_notification_queue (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    notification_type    TEXT NOT NULL,
    author_handle        TEXT NOT NULL,
    author_display_name  TEXT,
    uri                  TEXT NOT NULL,
    cid                  TEXT,
    subject_uri          TEXT,
    text                 TEXT,
    indexed_at           TEXT,
    fetched_at           TEXT,
    status               TEXT DEFAULT 'pending',
    triage_result        TEXT DEFAULT 'pending',
    auto_response_sent   INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_bsky_queue_status ON bluesky_notification_queue(status);

CREATE TABLE IF NOT EXISTS github_issue_queue (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    repo         TEXT NOT NULL,
    issue_number INTEGER NOT NULL,
    title        TEXT,
    body         TEXT,
    created_at   TEXT,
    fetched_at   TEXT,
    status       TEXT DEFAULT 'pending',
    triage_result TEXT DEFAULT 'pending'
);
CREATE INDEX IF NOT EXISTS idx_github_queue_status ON github_issue_queue(status);

CREATE TABLE IF NOT EXISTS file_hailo_tags (
    id         INTEGER PRIMARY KEY,
    file_id    INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    tag_name   TEXT NOT NULL,
    confidence REAL NOT NULL,
    source     TEXT NOT NULL DEFAULT 'hailo_remote',
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    UNIQUE(file_id, tag_name)
);
CREATE INDEX IF NOT EXISTS idx_file_hailo_tags_file_id ON file_hailo_tags(file_id);
CREATE INDEX IF NOT EXISTS idx_file_hailo_tags_tag_name ON file_hailo_tags(tag_name);
"""
