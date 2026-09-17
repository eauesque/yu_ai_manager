"""Schema SQL for media analysis and extraction tables."""

BASE_SCHEMA_SQL_MEDIA = """
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
CREATE INDEX IF NOT EXISTS idx_analysis_style ON analysis(style) WHERE style IS NOT NULL AND style != '';

CREATE TABLE IF NOT EXISTS scan_errors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    path            TEXT NOT NULL,
    error_type      TEXT NOT NULL,
    error_detail    TEXT,
    encodings_tried TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    resolved        INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_scan_errors_type ON scan_errors(error_type);
CREATE INDEX IF NOT EXISTS idx_scan_errors_resolved ON scan_errors(resolved);
CREATE INDEX IF NOT EXISTS idx_scan_errors_path ON scan_errors(path);

CREATE TABLE IF NOT EXISTS file_annotations (
    id         INTEGER PRIMARY KEY,
    file_id    INTEGER NOT NULL,
    source     TEXT NOT NULL,
    key        TEXT NOT NULL,
    value      BLOB NOT NULL,
    confidence REAL,
    created_at INTEGER NOT NULL,
    UNIQUE(file_id, source, key),
    FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_file_annotations_file_id ON file_annotations(file_id);
CREATE INDEX IF NOT EXISTS idx_file_annotations_source ON file_annotations(source);
CREATE INDEX IF NOT EXISTS idx_annotations_key ON file_annotations(key);
-- Added in migration 63 (YOLO count_detected multi-source IN-list seek).
-- Mirrored here so fresh DBs match migrated schemas.
CREATE INDEX IF NOT EXISTS idx_file_annotations_source_key ON file_annotations(source, key);

CREATE TABLE IF NOT EXISTS file_ratings (
  file_id    INTEGER PRIMARY KEY,
  rating     INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
  rated_at   INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_file_ratings_rating ON file_ratings(rating);
CREATE INDEX IF NOT EXISTS idx_file_ratings_file_id ON file_ratings(file_id);
CREATE INDEX IF NOT EXISTS idx_file_ratings_rating_file ON file_ratings(rating, file_id);

CREATE TABLE IF NOT EXISTS wd_tag_dict (
    id                  INTEGER PRIMARY KEY,
    tag_name            TEXT NOT NULL UNIQUE,
    tag_name_normalized TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wd_tag_dict_normalized ON wd_tag_dict(tag_name_normalized);
CREATE TABLE IF NOT EXISTS wd_model_dict (id INTEGER PRIMARY KEY, model TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS wd_category_dict (id INTEGER PRIMARY KEY, category TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS file_wd_tags (
    id          INTEGER PRIMARY KEY,
    file_id     INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    tag_id      INTEGER NOT NULL REFERENCES wd_tag_dict(id),
    confidence_milli INTEGER NOT NULL CHECK(confidence_milli BETWEEN 0 AND 1000),
    category_id INTEGER NOT NULL REFERENCES wd_category_dict(id),
    model_id    INTEGER NOT NULL REFERENCES wd_model_dict(id),
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    UNIQUE(file_id, tag_id, model_id)
);
CREATE INDEX IF NOT EXISTS idx_fwt_tag_id ON file_wd_tags(tag_id);
CREATE INDEX IF NOT EXISTS idx_fwt_model_file ON file_wd_tags(model_id, file_id);

CREATE TABLE IF NOT EXISTS kv_state (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

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
CREATE INDEX IF NOT EXISTS idx_ocr_task ON file_ocr_results(task);

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
CREATE INDEX IF NOT EXISTS idx_translations_ocr_result ON file_translations(ocr_result_id);

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

CREATE TABLE IF NOT EXISTS image_ai_annotations (
    id INTEGER PRIMARY KEY,
    image_id INTEGER NOT NULL,
    task TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL DEFAULT '',
    result_json TEXT NOT NULL,
    confidence REAL,
    status TEXT NOT NULL DEFAULT 'done',
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    FOREIGN KEY(image_id) REFERENCES files(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_image_ai_annotations_image_id
    ON image_ai_annotations(image_id);
CREATE INDEX IF NOT EXISTS idx_image_ai_annotations_task_model
    ON image_ai_annotations(task, model_name, model_version);

CREATE TABLE IF NOT EXISTS image_embeddings (
    image_id INTEGER NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL DEFAULT '',
    dim INTEGER NOT NULL,
    vector_blob BLOB NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (image_id, model_name, model_version),
    FOREIGN KEY(image_id) REFERENCES files(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS prompt_trend_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    engine       TEXT NOT NULL,
    analyzed_at  INTEGER NOT NULL,
    prompt_count INTEGER NOT NULL DEFAULT 0,
    result_json  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_prompt_trend_engine ON prompt_trend_history(engine);
CREATE INDEX IF NOT EXISTS idx_pth_analyzed_at ON prompt_trend_history(analyzed_at DESC);
"""
