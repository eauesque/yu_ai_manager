"""First half of migration 56 CREATE TABLE payload."""

TABLES_SQL_A = """
CREATE TABLE IF NOT EXISTS collections (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  query_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_collections_sort ON collections(sort_order);

CREATE TABLE IF NOT EXISTS analysis (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL,
    engine TEXT NOT NULL,
    analyzed_at INTEGER NOT NULL,
    tags_json TEXT,
    quality_score REAL,
    quality_notes BLOB,
    style TEXT,
    composition TEXT,
    mood TEXT,
    color_palette_json TEXT,
    prompt_suggestion BLOB,
    raw_response BLOB,
    description TEXT,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
    UNIQUE(file_id, engine)
);
CREATE INDEX IF NOT EXISTS idx_analysis_file_id ON analysis(file_id);
CREATE INDEX IF NOT EXISTS idx_analysis_engine ON analysis(engine);
CREATE INDEX IF NOT EXISTS idx_analysis_analyzed_at ON analysis(analyzed_at);

CREATE TABLE IF NOT EXISTS scan_errors (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    path         TEXT NOT NULL,
    error_type   TEXT NOT NULL,
    error_detail TEXT,
    encodings_tried TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    resolved     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_scan_errors_type ON scan_errors(error_type);
CREATE INDEX IF NOT EXISTS idx_scan_errors_resolved ON scan_errors(resolved);
CREATE INDEX IF NOT EXISTS idx_scan_errors_path ON scan_errors(path);

CREATE TABLE IF NOT EXISTS file_annotations (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    key TEXT NOT NULL,
    value BLOB NOT NULL,
    confidence REAL,
    created_at INTEGER NOT NULL,
    UNIQUE(file_id, source, key),
    FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_file_annotations_file_id ON file_annotations(file_id);
CREATE INDEX IF NOT EXISTS idx_file_annotations_source ON file_annotations(source);

CREATE TABLE IF NOT EXISTS file_ratings (
  file_id    INTEGER PRIMARY KEY,
  rating     INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
  rated_at   INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS file_wd_tags (
    id         INTEGER PRIMARY KEY,
    file_id    INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    tag_name   TEXT NOT NULL,
    confidence REAL NOT NULL,
    category   TEXT NOT NULL DEFAULT 'general',
    model      TEXT NOT NULL,
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    UNIQUE(file_id, tag_name, model)
);
CREATE INDEX IF NOT EXISTS idx_file_wd_tags_file_id ON file_wd_tags(file_id);

CREATE TABLE IF NOT EXISTS file_keyframes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id      INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    keyframe_idx INTEGER NOT NULL,
    timestamp_ms INTEGER NOT NULL DEFAULT 0,
    vector       BLOB,
    wd_tags_json TEXT,
    model        TEXT NOT NULL DEFAULT '',
    created_at   INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    UNIQUE(file_id, keyframe_idx, model)
);
CREATE INDEX IF NOT EXISTS idx_file_keyframes_file_id ON file_keyframes(file_id);

CREATE TABLE IF NOT EXISTS prompt_trend_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    engine       TEXT NOT NULL,
    analyzed_at  INTEGER NOT NULL,
    prompt_count INTEGER NOT NULL DEFAULT 0,
    result_json  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_prompt_trend_engine ON prompt_trend_history(engine);

CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    webhook_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status_code INTEGER,
    response_body TEXT,
    attempt INTEGER NOT NULL DEFAULT 1,
    success INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at INTEGER NOT NULL,
    delivered_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_webhook_id ON webhook_deliveries(webhook_id);
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_created_at ON webhook_deliveries(created_at);

CREATE TABLE IF NOT EXISTS tag_dictionary (
    id         INTEGER PRIMARY KEY,
    tag_name   TEXT NOT NULL UNIQUE COLLATE NOCASE,
    category   INTEGER NOT NULL DEFAULT 0,
    post_count INTEGER NOT NULL DEFAULT 0,
    aliases    TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_tag_dict_name ON tag_dictionary(tag_name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_tag_dict_post_count ON tag_dictionary(post_count DESC);

CREATE TABLE IF NOT EXISTS md_files (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    path       TEXT    NOT NULL UNIQUE,
    mtime      REAL    NOT NULL DEFAULT 0,
    size       INTEGER NOT NULL DEFAULT 0,
    title      TEXT    NOT NULL DEFAULT '',
    content    TEXT    NOT NULL DEFAULT '',
    is_deleted INTEGER NOT NULL DEFAULT 0,
    indexed_at INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_md_files_path ON md_files(path);

CREATE TABLE IF NOT EXISTS chat_conversations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source              TEXT    NOT NULL,
    external_id         TEXT,
    title               TEXT    NOT NULL DEFAULT '',
    model               TEXT    NOT NULL DEFAULT '',
    created_at          INTEGER NOT NULL DEFAULT 0,
    updated_at          INTEGER NOT NULL DEFAULT 0,
    message_count       INTEGER NOT NULL DEFAULT 0,
    imported_at         INTEGER NOT NULL DEFAULT 0,
    summary             TEXT,
    ai_processed_at     INTEGER,
    ai_model            TEXT,
    language            TEXT DEFAULT '',
    language_confidence REAL DEFAULT 0.0
);
CREATE INDEX IF NOT EXISTS idx_chat_conv_source ON chat_conversations(source);
CREATE INDEX IF NOT EXISTS idx_chat_conv_external_id ON chat_conversations(external_id);

CREATE TABLE IF NOT EXISTS chat_messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    role            TEXT    NOT NULL,
    content         TEXT    NOT NULL DEFAULT '',
    created_at      INTEGER NOT NULL DEFAULT 0,
    seq             INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_chat_msg_conv_id ON chat_messages(conversation_id);
"""
