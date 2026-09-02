-- GENERATED FILE -- do not edit by hand.
--
-- Generator: scripts/internal/gen_rust_genesis_sql.py
-- Source:    core/schema_core/schema_init.py::init_db(enable_fts=True)
-- Schema:    v88 (core/schema_core/schema_constants.py)
--
-- This is what Python creates for a brand-new database. It is emitted by
-- running init_db and reading back sqlite_master, so the indexes init_db
-- creates from Python code (not from the SQL constants) are included --
-- idx_files_deleted_ext and idx_tags_first_seen_mtime appear nowhere in
-- BASE_SCHEMA_SQL and a concatenating generator would drop both.
--
-- NOT IDEMPOTENT: SQLite strips IF NOT EXISTS when it stores a CREATE in
-- sqlite_master, so these statements assume an empty database. That is the
-- only way genesis runs -- the caller claims the file with an exclusive
-- create and skips genesis entirely if it already exists.
--
-- Regenerate with:
--   uv run python scripts/internal/gen_rust_genesis_sql.py
-- scripts/pre_push_check.py fails if this file drifts from the generator.

-- table: schema_version
CREATE TABLE schema_version (
  version INTEGER PRIMARY KEY,
  applied_at INTEGER NOT NULL,
  description TEXT
);

-- table: files
CREATE TABLE files (
  id INTEGER PRIMARY KEY,
  path TEXT NOT NULL UNIQUE,
  mtime INTEGER NOT NULL,
  size INTEGER NOT NULL,
  hash TEXT,
  phash TEXT,
  is_deleted INTEGER NOT NULL DEFAULT 0,
  meta_source TEXT,
  not_modified INTEGER NOT NULL DEFAULT 0,
  parser_version INTEGER NOT NULL DEFAULT 1,
  is_zip_member INTEGER NOT NULL DEFAULT 0,
  extracted_from_zip TEXT,
  extracted_from_internal TEXT,
  extraction_date INTEGER,
  extracted_to_file_id INTEGER,
  width INTEGER,
  height INTEGER,
  imported_from_peer TEXT,
  has_sweep INTEGER NOT NULL DEFAULT 0,
  file_ext TEXT GENERATED ALWAYS AS (
    CASE
        WHEN path LIKE '%.png' THEN '.png'
        WHEN path LIKE '%.jpg' THEN '.jpg'
        WHEN path LIKE '%.jpeg' THEN '.jpeg'
        WHEN path LIKE '%.webp' THEN '.webp'
        WHEN path LIKE '%.gif' THEN '.gif'
        WHEN path LIKE '%.bmp' THEN '.bmp'
        WHEN path LIKE '%.tif' THEN '.tif'
        WHEN path LIKE '%.tiff' THEN '.tiff'
        WHEN path LIKE '%.avif' THEN '.avif'
        WHEN path LIKE '%.heif' THEN '.heif'
        WHEN path LIKE '%.heic' THEN '.heic'
        WHEN path LIKE '%.jxl' THEN '.jxl'
        WHEN path LIKE '%.svg' THEN '.svg'
        WHEN path LIKE '%.webm' THEN '.webm'
        WHEN path LIKE '%.mp4' THEN '.mp4'
        WHEN path LIKE '%.mov' THEN '.mov'
        WHEN path LIKE '%.m4v' THEN '.m4v'
        WHEN path LIKE '%.avi' THEN '.avi'
        WHEN path LIKE '%.mkv' THEN '.mkv'
        WHEN path LIKE '%.ogv' THEN '.ogv'
        WHEN path LIKE '%.ts' THEN '.ts'
        WHEN path LIKE '%.m2ts' THEN '.m2ts'
        WHEN path LIKE '%.mp3' THEN '.mp3'
        WHEN path LIKE '%.wav' THEN '.wav'
        WHEN path LIKE '%.ogg' THEN '.ogg'
        WHEN path LIKE '%.opus' THEN '.opus'
        WHEN path LIKE '%.m4a' THEN '.m4a'
        WHEN path LIKE '%.aac' THEN '.aac'
        WHEN path LIKE '%.flac' THEN '.flac'
    END
  ) STORED,
  FOREIGN KEY (extracted_to_file_id) REFERENCES files(id)
);

-- table: tags
CREATE TABLE tags (
  id INTEGER PRIMARY KEY,
  tag TEXT NOT NULL,
  namespace TEXT,
  first_seen_mtime INTEGER,
  UNIQUE(tag, namespace)
);

-- table: file_tags
CREATE TABLE file_tags (
  file_id INTEGER NOT NULL,
  tag_id INTEGER NOT NULL,
  weight REAL NOT NULL DEFAULT 1.0,
  source TEXT NOT NULL DEFAULT 'meta',
  UNIQUE(file_id, tag_id),
  FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE,
  FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

-- table: templates
CREATE TABLE templates (
  id INTEGER PRIMARY KEY,
  file_id INTEGER NOT NULL UNIQUE,
  raw_prompt TEXT,
  raw_negative TEXT,
  format TEXT,
  raw_meta_json TEXT,
  model_name TEXT,
  model_hash TEXT,
  char_positive TEXT DEFAULT '',
  char_negative TEXT DEFAULT '',
  prompt_lang TEXT DEFAULT '',
  prompt_lang_confidence REAL DEFAULT 0.0,
  FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
);

-- table: template_tokens
CREATE TABLE template_tokens (
  id INTEGER PRIMARY KEY,
  template_id INTEGER NOT NULL,
  token_type TEXT NOT NULL,
  payload TEXT NOT NULL,
  position INTEGER NOT NULL,
  FOREIGN KEY(template_id) REFERENCES templates(id) ON DELETE CASCADE
);

-- table: media_extract_state
CREATE TABLE media_extract_state (
  file_id INTEGER PRIMARY KEY,
  cache_state TEXT NOT NULL DEFAULT 'none',
  metadata_schema_version INTEGER,
  metadata_extracted_at INTEGER,
  metadata_source TEXT,
  metadata_source_version TEXT,
  fingerprint_mtime INTEGER,
  fingerprint_size INTEGER,
  fingerprint_hash TEXT,
  error_code TEXT,
  error_at INTEGER,
  error_count INTEGER NOT NULL DEFAULT 0,
  next_retry_after INTEGER,
  last_access_at INTEGER,
  updated_at INTEGER NOT NULL,
  FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
);

-- table: cache_entry
CREATE TABLE cache_entry (
  cache_key TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  path TEXT NOT NULL,
  file_id INTEGER,
  size_bytes INTEGER NOT NULL DEFAULT 0,
  last_access_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE SET NULL
);

-- table: clip_eligible_files
CREATE TABLE clip_eligible_files (
  file_id INTEGER PRIMARY KEY,
  FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
);

-- table: file_tag_counts
CREATE TABLE file_tag_counts (
  file_id INTEGER PRIMARY KEY,
  tag_count INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
);

-- table: search_stats
CREATE TABLE search_stats (
  key TEXT PRIMARY KEY,
  value INTEGER NOT NULL DEFAULT 0,
  updated_at INTEGER NOT NULL
);

-- index: idx_tags_tag_lower
CREATE INDEX idx_tags_tag_lower ON tags(LOWER(tag));

-- index: idx_file_tags_tag_id
CREATE INDEX idx_file_tags_tag_id ON file_tags(tag_id);

-- index: idx_files_deleted_mtime
CREATE INDEX idx_files_deleted_mtime ON files(is_deleted, mtime DESC);

-- index: idx_files_deleted_source
CREATE INDEX idx_files_deleted_source ON files(is_deleted, meta_source);

-- index: idx_file_tags_file_tag
CREATE INDEX idx_file_tags_file_tag ON file_tags(file_id, tag_id);

-- index: idx_file_tags_source
CREATE INDEX idx_file_tags_source ON file_tags(source);

-- index: idx_file_tags_tagid_fileid
CREATE INDEX idx_file_tags_tagid_fileid ON file_tags(tag_id, file_id);

-- index: idx_media_extract_cache_state
CREATE INDEX idx_media_extract_cache_state ON media_extract_state(cache_state);

-- index: idx_media_extract_next_retry
CREATE INDEX idx_media_extract_next_retry ON media_extract_state(next_retry_after);

-- index: idx_media_extract_last_access
CREATE INDEX idx_media_extract_last_access ON media_extract_state(last_access_at);

-- index: idx_cache_entry_kind_last_access
CREATE INDEX idx_cache_entry_kind_last_access ON cache_entry(kind, last_access_at);

-- index: idx_file_tag_counts_tag_count
CREATE INDEX idx_file_tag_counts_tag_count ON file_tag_counts(tag_count);

-- table: collections
CREATE TABLE collections (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  query_json TEXT
);

-- index: idx_collections_sort
CREATE INDEX idx_collections_sort ON collections(sort_order);

-- table: favorites
CREATE TABLE favorites (
  file_id INTEGER NOT NULL,
  collection_id INTEGER NOT NULL DEFAULT 1,
  added_at INTEGER NOT NULL,
  PRIMARY KEY (file_id, collection_id),
  FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE,
  FOREIGN KEY(collection_id) REFERENCES collections(id) ON DELETE CASCADE
);

-- index: idx_favorites_coll_file
CREATE INDEX idx_favorites_coll_file ON favorites(collection_id, file_id);

-- index: idx_files_hash
CREATE INDEX idx_files_hash ON files(hash) WHERE hash IS NOT NULL AND hash != '';

-- index: idx_files_width
CREATE INDEX idx_files_width ON files(width) WHERE width IS NOT NULL;

-- index: idx_files_height
CREATE INDEX idx_files_height ON files(height) WHERE height IS NOT NULL;

-- index: idx_files_path
CREATE INDEX idx_files_path ON files(path);

-- index: idx_files_size
CREATE INDEX idx_files_size ON files(size) WHERE is_deleted=0 AND size > 1024;

-- index: idx_files_mtime_active
CREATE INDEX idx_files_mtime_active ON files(mtime) WHERE is_deleted = 0;

-- index: idx_templates_model_name
CREATE INDEX idx_templates_model_name ON templates(model_name) WHERE model_name IS NOT NULL;

-- index: idx_templates_file_id
CREATE INDEX idx_templates_file_id ON templates(file_id);

-- index: idx_files_deleted_parser_version
CREATE INDEX idx_files_deleted_parser_version ON files(is_deleted, parser_version);

-- index: idx_files_deleted_path
CREATE INDEX idx_files_deleted_path ON files(is_deleted, path);

-- index: idx_files_has_sweep
CREATE INDEX idx_files_has_sweep ON files(id) WHERE has_sweep=1;

-- table: db_meta
CREATE TABLE db_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);

-- table: sweeps
CREATE TABLE sweeps (
  id TEXT PRIMARY KEY,
  bridge TEXT NOT NULL,
  base_seed INTEGER,
  created_at INTEGER NOT NULL,
  prompt_template TEXT,
  negative_template TEXT,
  checkpoint TEXT,
  vae TEXT,
  sampler TEXT,
  width INTEGER,
  height INTEGER,
  steps INTEGER,
  cfg REAL,
  axis_count INTEGER NOT NULL DEFAULT 0,
  first_file_id INTEGER,
  last_file_id INTEGER,
  file_count INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'completed',
  updated_at INTEGER NOT NULL,
  FOREIGN KEY (first_file_id) REFERENCES files(id) ON DELETE SET NULL,
  FOREIGN KEY (last_file_id) REFERENCES files(id) ON DELETE SET NULL
);

-- index: idx_sweeps_created_at
CREATE INDEX idx_sweeps_created_at ON sweeps(created_at DESC);

-- index: idx_sweeps_bridge
CREATE INDEX idx_sweeps_bridge ON sweeps(bridge);

-- index: idx_sweeps_checkpoint
CREATE INDEX idx_sweeps_checkpoint ON sweeps(checkpoint) WHERE checkpoint IS NOT NULL;

-- index: idx_sweeps_sampler
CREATE INDEX idx_sweeps_sampler ON sweeps(sampler) WHERE sampler IS NOT NULL;

-- table: sweep_axes
CREATE TABLE sweep_axes (
  sweep_id TEXT NOT NULL,
  axis_index INTEGER NOT NULL,
  param TEXT NOT NULL,
  total INTEGER NOT NULL,
  PRIMARY KEY (sweep_id, axis_index),
  FOREIGN KEY (sweep_id) REFERENCES sweeps(id) ON DELETE CASCADE
);

-- index: idx_sweep_axes_param
CREATE INDEX idx_sweep_axes_param ON sweep_axes(param);

-- table: deferred_maintenance_jobs
CREATE TABLE deferred_maintenance_jobs (
  id INTEGER PRIMARY KEY,
  job_key TEXT NOT NULL UNIQUE,
  task TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  error_message TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

-- index: idx_deferred_jobs_status
CREATE INDEX idx_deferred_jobs_status
  ON deferred_maintenance_jobs(status, updated_at);

-- table: extension_schema_versions
CREATE TABLE extension_schema_versions (
  extension_name  TEXT NOT NULL,
  version         INTEGER NOT NULL,
  applied_at      INTEGER NOT NULL,
  description     TEXT DEFAULT '',
  PRIMARY KEY (extension_name, version)
);

-- trigger: trg_file_tags_ai_search_stats
CREATE TRIGGER trg_file_tags_ai_search_stats
AFTER INSERT ON file_tags
BEGIN
  UPDATE search_stats
  SET value = value + 1, updated_at = strftime('%s','now')
  WHERE key='active_tagged_files'
    AND COALESCE((SELECT is_deleted FROM files WHERE id=NEW.file_id), 1)=0
    AND COALESCE((SELECT tag_count FROM file_tag_counts WHERE file_id=NEW.file_id), 0)=0;

  INSERT INTO file_tag_counts(file_id, tag_count)
  VALUES (NEW.file_id, 1)
  ON CONFLICT(file_id) DO UPDATE SET tag_count = tag_count + 1;
END;

-- trigger: trg_file_tags_ad_search_stats
CREATE TRIGGER trg_file_tags_ad_search_stats
AFTER DELETE ON file_tags
BEGIN
  UPDATE search_stats
  SET value = value - 1, updated_at = strftime('%s','now')
  WHERE key='active_tagged_files'
    AND COALESCE((SELECT is_deleted FROM files WHERE id=OLD.file_id), 1)=0
    AND COALESCE((SELECT tag_count FROM file_tag_counts WHERE file_id=OLD.file_id), 0)=1;

  UPDATE file_tag_counts
  SET tag_count = tag_count - 1
  WHERE file_id=OLD.file_id;

  DELETE FROM file_tag_counts
  WHERE file_id=OLD.file_id AND tag_count <= 0;
END;

-- trigger: trg_files_ai_search_stats
CREATE TRIGGER trg_files_ai_search_stats
AFTER INSERT ON files
BEGIN
  UPDATE search_stats
  SET value = value + CASE WHEN NEW.is_deleted=0 THEN 1 ELSE 0 END,
      updated_at = strftime('%s','now')
  WHERE key='active_files';
END;

-- trigger: trg_files_au_deleted_search_stats
CREATE TRIGGER trg_files_au_deleted_search_stats
AFTER UPDATE OF is_deleted ON files
WHEN OLD.is_deleted != NEW.is_deleted
BEGIN
  UPDATE search_stats
  SET value = value + CASE WHEN NEW.is_deleted=0 THEN 1 ELSE -1 END,
      updated_at = strftime('%s','now')
  WHERE key='active_files';

  UPDATE search_stats
  SET value = value + CASE WHEN NEW.is_deleted=0 THEN 1 ELSE -1 END,
      updated_at = strftime('%s','now')
  WHERE key='active_tagged_files'
    AND COALESCE((SELECT tag_count FROM file_tag_counts WHERE file_id=NEW.id), 0) > 0;
END;

-- trigger: trg_files_ad_search_stats
CREATE TRIGGER trg_files_ad_search_stats
AFTER DELETE ON files
BEGIN
  UPDATE search_stats
  SET value = value - CASE WHEN OLD.is_deleted=0 THEN 1 ELSE 0 END,
      updated_at = strftime('%s','now')
  WHERE key='active_files';

  UPDATE search_stats
  SET value = value - CASE
      WHEN OLD.is_deleted=0
       AND COALESCE((SELECT tag_count FROM file_tag_counts WHERE file_id=OLD.id), 0) > 0
      THEN 1 ELSE 0 END,
      updated_at = strftime('%s','now')
  WHERE key='active_tagged_files';

  DELETE FROM file_tag_counts WHERE file_id=OLD.id;
END;

-- table: analysis
CREATE TABLE analysis (
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

-- index: idx_analysis_file_id
CREATE INDEX idx_analysis_file_id ON analysis(file_id);

-- index: idx_analysis_engine
CREATE INDEX idx_analysis_engine ON analysis(engine);

-- index: idx_analysis_analyzed_at
CREATE INDEX idx_analysis_analyzed_at ON analysis(analyzed_at);

-- index: idx_analysis_style
CREATE INDEX idx_analysis_style ON analysis(style) WHERE style IS NOT NULL AND style != '';

-- table: scan_errors
CREATE TABLE scan_errors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    path            TEXT NOT NULL,
    error_type      TEXT NOT NULL,
    error_detail    TEXT,
    encodings_tried TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    resolved        INTEGER NOT NULL DEFAULT 0
);

-- index: idx_scan_errors_type
CREATE INDEX idx_scan_errors_type ON scan_errors(error_type);

-- index: idx_scan_errors_resolved
CREATE INDEX idx_scan_errors_resolved ON scan_errors(resolved);

-- index: idx_scan_errors_path
CREATE INDEX idx_scan_errors_path ON scan_errors(path);

-- table: file_annotations
CREATE TABLE file_annotations (
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

-- index: idx_file_annotations_file_id
CREATE INDEX idx_file_annotations_file_id ON file_annotations(file_id);

-- index: idx_file_annotations_source
CREATE INDEX idx_file_annotations_source ON file_annotations(source);

-- index: idx_annotations_key
CREATE INDEX idx_annotations_key ON file_annotations(key);

-- index: idx_file_annotations_source_key
CREATE INDEX idx_file_annotations_source_key ON file_annotations(source, key);

-- table: file_ratings
CREATE TABLE file_ratings (
  file_id    INTEGER PRIMARY KEY,
  rating     INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
  rated_at   INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
);

-- index: idx_file_ratings_rating
CREATE INDEX idx_file_ratings_rating ON file_ratings(rating);

-- index: idx_file_ratings_file_id
CREATE INDEX idx_file_ratings_file_id ON file_ratings(file_id);

-- index: idx_file_ratings_rating_file
CREATE INDEX idx_file_ratings_rating_file ON file_ratings(rating, file_id);

-- table: wd_tag_dict
CREATE TABLE wd_tag_dict (
    id                  INTEGER PRIMARY KEY,
    tag_name            TEXT NOT NULL UNIQUE,
    tag_name_normalized TEXT NOT NULL
);

-- index: idx_wd_tag_dict_normalized
CREATE INDEX idx_wd_tag_dict_normalized ON wd_tag_dict(tag_name_normalized);

-- table: wd_model_dict
CREATE TABLE wd_model_dict (id INTEGER PRIMARY KEY, model TEXT NOT NULL UNIQUE);

-- table: wd_category_dict
CREATE TABLE wd_category_dict (id INTEGER PRIMARY KEY, category TEXT NOT NULL UNIQUE);

-- table: file_wd_tags
CREATE TABLE file_wd_tags (
    id          INTEGER PRIMARY KEY,
    file_id     INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    tag_id      INTEGER NOT NULL REFERENCES wd_tag_dict(id),
    confidence_milli INTEGER NOT NULL CHECK(confidence_milli BETWEEN 0 AND 1000),
    category_id INTEGER NOT NULL REFERENCES wd_category_dict(id),
    model_id    INTEGER NOT NULL REFERENCES wd_model_dict(id),
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    UNIQUE(file_id, tag_id, model_id)
);

-- index: idx_fwt_tag_id
CREATE INDEX idx_fwt_tag_id ON file_wd_tags(tag_id);

-- index: idx_fwt_model_file
CREATE INDEX idx_fwt_model_file ON file_wd_tags(model_id, file_id);

-- table: kv_state
CREATE TABLE kv_state (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

-- table: file_keyframes
CREATE TABLE file_keyframes (
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

-- index: idx_file_keyframes_file_id
CREATE INDEX idx_file_keyframes_file_id ON file_keyframes(file_id);

-- table: file_ocr_results
CREATE TABLE file_ocr_results (
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

-- index: idx_ocr_file_id
CREATE INDEX idx_ocr_file_id ON file_ocr_results(file_id);

-- index: idx_ocr_task
CREATE INDEX idx_ocr_task ON file_ocr_results(task);

-- table: file_translations
CREATE TABLE file_translations (
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

-- index: idx_translations_ocr_result
CREATE INDEX idx_translations_ocr_result ON file_translations(ocr_result_id);

-- table: file_hailo_tags
CREATE TABLE file_hailo_tags (
    id         INTEGER PRIMARY KEY,
    file_id    INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    tag_name   TEXT NOT NULL,
    confidence REAL NOT NULL,
    source     TEXT NOT NULL DEFAULT 'hailo_remote',
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    UNIQUE(file_id, tag_name)
);

-- index: idx_file_hailo_tags_file_id
CREATE INDEX idx_file_hailo_tags_file_id ON file_hailo_tags(file_id);

-- index: idx_file_hailo_tags_tag_name
CREATE INDEX idx_file_hailo_tags_tag_name ON file_hailo_tags(tag_name);

-- table: image_ai_annotations
CREATE TABLE image_ai_annotations (
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

-- index: idx_image_ai_annotations_image_id
CREATE INDEX idx_image_ai_annotations_image_id
    ON image_ai_annotations(image_id);

-- index: idx_image_ai_annotations_task_model
CREATE INDEX idx_image_ai_annotations_task_model
    ON image_ai_annotations(task, model_name, model_version);

-- table: image_embeddings
CREATE TABLE image_embeddings (
    image_id INTEGER NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL DEFAULT '',
    dim INTEGER NOT NULL,
    vector_blob BLOB NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (image_id, model_name, model_version),
    FOREIGN KEY(image_id) REFERENCES files(id) ON DELETE CASCADE
);

-- table: prompt_trend_history
CREATE TABLE prompt_trend_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    engine       TEXT NOT NULL,
    analyzed_at  INTEGER NOT NULL,
    prompt_count INTEGER NOT NULL DEFAULT 0,
    result_json  TEXT NOT NULL
);

-- index: idx_prompt_trend_engine
CREATE INDEX idx_prompt_trend_engine ON prompt_trend_history(engine);

-- index: idx_pth_analyzed_at
CREATE INDEX idx_pth_analyzed_at ON prompt_trend_history(analyzed_at DESC);

-- table: webhook_deliveries
CREATE TABLE webhook_deliveries (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    webhook_id   TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status_code  INTEGER,
    response_body TEXT,
    attempt      INTEGER NOT NULL DEFAULT 1,
    success      INTEGER NOT NULL DEFAULT 0,
    error        TEXT,
    created_at   INTEGER NOT NULL,
    delivered_at INTEGER
);

-- index: idx_webhook_deliveries_webhook_id
CREATE INDEX idx_webhook_deliveries_webhook_id ON webhook_deliveries(webhook_id);

-- index: idx_webhook_deliveries_created_at
CREATE INDEX idx_webhook_deliveries_created_at ON webhook_deliveries(created_at);

-- table: tag_dictionary
CREATE TABLE tag_dictionary (
    id         INTEGER PRIMARY KEY,
    tag_name   TEXT NOT NULL UNIQUE COLLATE NOCASE,
    category   INTEGER NOT NULL DEFAULT 0,
    post_count INTEGER NOT NULL DEFAULT 0,
    aliases    TEXT DEFAULT ''
);

-- index: idx_tag_dict_name
CREATE INDEX idx_tag_dict_name ON tag_dictionary(tag_name COLLATE NOCASE);

-- index: idx_tag_dict_post_count
CREATE INDEX idx_tag_dict_post_count ON tag_dictionary(post_count DESC);

-- table: trophies
CREATE TABLE trophies (
    id             INTEGER PRIMARY KEY,
    trophy_type    TEXT NOT NULL UNIQUE,
    title          TEXT NOT NULL,
    tier           TEXT NOT NULL DEFAULT 'gold',
    category       TEXT NOT NULL DEFAULT 'milestone',
    achieved_month TEXT,
    achieved_at    INTEGER NOT NULL,
    metadata       TEXT DEFAULT '{}'
);

-- index: idx_trophies_category
CREATE INDEX idx_trophies_category ON trophies(category);

-- table: monthly_stats_cache
CREATE TABLE monthly_stats_cache (
    month      TEXT NOT NULL,
    stat_key   TEXT NOT NULL,
    stat_value TEXT NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (month, stat_key)
);

-- table: md_files
CREATE TABLE md_files (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    path       TEXT    NOT NULL UNIQUE,
    mtime      REAL    NOT NULL DEFAULT 0,
    size       INTEGER NOT NULL DEFAULT 0,
    title      TEXT    NOT NULL DEFAULT '',
    content    TEXT    NOT NULL DEFAULT '',
    is_deleted INTEGER NOT NULL DEFAULT 0,
    indexed_at INTEGER NOT NULL DEFAULT 0
);

-- index: idx_md_files_path
CREATE INDEX idx_md_files_path ON md_files(path);

-- index: idx_md_files_is_deleted
CREATE INDEX idx_md_files_is_deleted ON md_files(is_deleted);

-- table: chat_conversations
CREATE TABLE chat_conversations (
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

-- index: idx_chat_conv_source
CREATE INDEX idx_chat_conv_source ON chat_conversations(source);

-- index: idx_chat_conv_external_id
CREATE INDEX idx_chat_conv_external_id ON chat_conversations(external_id);

-- index: uq_chat_conv_source_extid
CREATE UNIQUE INDEX uq_chat_conv_source_extid ON chat_conversations(source, external_id);

-- table: chat_messages
CREATE TABLE chat_messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    role            TEXT    NOT NULL,
    content         TEXT    NOT NULL DEFAULT '',
    created_at      INTEGER NOT NULL DEFAULT 0,
    seq             INTEGER NOT NULL DEFAULT 0
);

-- index: idx_chat_msg_conv_id
CREATE INDEX idx_chat_msg_conv_id ON chat_messages(conversation_id);

-- table: chat_decisions
CREATE TABLE chat_decisions (
    id              INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    message_id      INTEGER,
    decision_text   TEXT NOT NULL
);

-- index: idx_chat_decisions_conv
CREATE INDEX idx_chat_decisions_conv ON chat_decisions(conversation_id);

-- table: chat_entities
CREATE TABLE chat_entities (
    id              INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    message_id      INTEGER,
    entity_type     TEXT NOT NULL,
    entity_value    TEXT NOT NULL
);

-- index: idx_chat_entities_type_value
CREATE INDEX idx_chat_entities_type_value ON chat_entities(entity_type, entity_value);

-- index: idx_chat_entities_conv
CREATE INDEX idx_chat_entities_conv ON chat_entities(conversation_id);

-- table: chat_topics
CREATE TABLE chat_topics (
    id              INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    topic           TEXT NOT NULL
);

-- index: idx_chat_topics_topic
CREATE INDEX idx_chat_topics_topic ON chat_topics(topic);

-- table: agent_action_journal
CREATE TABLE agent_action_journal (
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

-- index: idx_agent_journal_session
CREATE INDEX idx_agent_journal_session ON agent_action_journal(session_id);

-- index: idx_agent_journal_time
CREATE INDEX idx_agent_journal_time ON agent_action_journal(timestamp);

-- index: idx_agent_journal_tool
CREATE INDEX idx_agent_journal_tool ON agent_action_journal(tool_name);

-- table: audit_log
CREATE TABLE audit_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp         TEXT NOT NULL,
    event_type        TEXT NOT NULL,
    source            TEXT NOT NULL,
    target            TEXT,
    severity          TEXT NOT NULL,
    reported_to       TEXT NOT NULL,
    detail_json       TEXT,
    user_acknowledged INTEGER DEFAULT 0,
    acknowledged_at   TEXT,
    prev_hash         TEXT DEFAULT '',
    entry_hash        TEXT DEFAULT ''
);

-- index: idx_audit_log_event_type
CREATE INDEX idx_audit_log_event_type ON audit_log(event_type);

-- index: idx_audit_log_severity
CREATE INDEX idx_audit_log_severity ON audit_log(severity);

-- index: idx_audit_log_timestamp
CREATE INDEX idx_audit_log_timestamp ON audit_log(timestamp);

-- table: agent_session_scopes
CREATE TABLE agent_session_scopes (
    session_id  TEXT PRIMARY KEY,
    preset      TEXT NOT NULL DEFAULT 'organizer',
    name        TEXT NOT NULL DEFAULT '',
    denied_json TEXT NOT NULL DEFAULT '[]',
    created_at  TEXT NOT NULL,
    expires_at  TEXT
);

-- table: agent_auto_approve_rules
CREATE TABLE agent_auto_approve_rules (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tool            TEXT NOT NULL,
    conditions_json TEXT NOT NULL DEFAULT '{}',
    approved_at     TEXT NOT NULL,
    approved_by     TEXT NOT NULL DEFAULT 'user'
);

-- table: gateway_status_transitions
CREATE TABLE gateway_status_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    backend_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    from_state TEXT NOT NULL
        CHECK (from_state IN ('running','stopped','unknown')),
    to_state TEXT NOT NULL
        CHECK (to_state IN ('running','stopped')),
    last_request_id TEXT,
    metadata TEXT
);

-- index: idx_status_backend_time
CREATE INDEX idx_status_backend_time
    ON gateway_status_transitions(backend_id, timestamp DESC);

-- table: bluesky_notification_queue
CREATE TABLE bluesky_notification_queue (
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

-- index: idx_bsky_queue_status
CREATE INDEX idx_bsky_queue_status ON bluesky_notification_queue(status);

-- index: idx_bsky_queue_uri
CREATE UNIQUE INDEX idx_bsky_queue_uri ON bluesky_notification_queue(uri);

-- index: idx_bsky_queue_type
CREATE INDEX idx_bsky_queue_type ON bluesky_notification_queue(notification_type);

-- table: github_issue_queue
CREATE TABLE github_issue_queue (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    repo          TEXT NOT NULL,
    issue_number  INTEGER NOT NULL,
    title         TEXT,
    body          TEXT,
    created_at    TEXT,
    fetched_at    TEXT,
    status        TEXT DEFAULT 'pending',
    triage_result TEXT DEFAULT 'pending'
);

-- index: idx_github_queue_status
CREATE INDEX idx_github_queue_status ON github_issue_queue(status);

-- index: idx_github_queue_repo_issue
CREATE UNIQUE INDEX idx_github_queue_repo_issue ON github_issue_queue(repo, issue_number);

-- table: import_session
CREATE TABLE import_session (
    id                 TEXT PRIMARY KEY,
    peer_id            TEXT NOT NULL,
    peer_name          TEXT NOT NULL,
    mode               TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'pending',
    last_seen_rowid    INTEGER,
    snapshot_max_rowid INTEGER,
    total_files        INTEGER,
    done_files         INTEGER NOT NULL DEFAULT 0,
    import_folder      TEXT NOT NULL,
    options            TEXT NOT NULL DEFAULT '{"include_favorites":false,"merge_metadata":false}',
    created_at         INTEGER NOT NULL,
    updated_at         INTEGER NOT NULL
);

-- table: import_file_id_map
CREATE TABLE import_file_id_map (
    session_id     TEXT NOT NULL REFERENCES import_session(id) ON DELETE CASCADE,
    remote_peer_id TEXT NOT NULL,
    remote_file_id INTEGER NOT NULL,
    local_file_id  INTEGER NOT NULL,
    status         TEXT NOT NULL DEFAULT 'done',
    PRIMARY KEY (session_id, remote_peer_id, remote_file_id)
);

-- table: import_collection_id_map
CREATE TABLE import_collection_id_map (
    session_id           TEXT NOT NULL REFERENCES import_session(id) ON DELETE CASCADE,
    remote_peer_id       TEXT NOT NULL,
    remote_collection_id INTEGER NOT NULL,
    local_collection_id  INTEGER NOT NULL,
    PRIMARY KEY (session_id, remote_peer_id, remote_collection_id)
);

-- table: peer_pairing_requests
CREATE TABLE peer_pairing_requests (
    request_id      TEXT PRIMARY KEY,
    peer_id         TEXT NOT NULL,
    host            TEXT NOT NULL,
    port            INTEGER NOT NULL,
    pin_hash        TEXT,
    pin_expires_at  INTEGER,
    verify_attempts INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL,
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL,
    pubkey          BLOB,
    x25519_pk       BLOB,
    commit_hash     BLOB,
    sas             TEXT,
    source_ip       TEXT
);

-- index: idx_pairing_status
CREATE INDEX idx_pairing_status ON peer_pairing_requests(status, updated_at);

-- index: idx_pairing_peer_id
CREATE INDEX idx_pairing_peer_id ON peer_pairing_requests(peer_id, status);

-- table: peer_tokens
CREATE TABLE peer_tokens (
    peer_id    TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL,
    issued_at  INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    revoked_at INTEGER,
    source     TEXT NOT NULL DEFAULT 'pairing',
    note       TEXT
);

-- index: idx_peer_tokens_expires
CREATE INDEX idx_peer_tokens_expires ON peer_tokens(expires_at) WHERE revoked_at IS NULL;

-- table: peers
CREATE TABLE peers (
    peer_id           TEXT PRIMARY KEY,
    name              TEXT,
    api_host          TEXT,
    api_port          INTEGER,
    token             TEXT,
    token_expires_at  INTEGER,
    token_issued_at   INTEGER,
    pubkey            BLOB,
    x25519_pk         BLOB,
    created_at        INTEGER NOT NULL,
    updated_at        INTEGER NOT NULL,
    last_reached_at   INTEGER,
    last_attempted_at INTEGER,
    -- Added by migration 86. Kept last so that a table created here and a table
    -- created by migration 86's ALTER end up with the same column order.
    inference_types   TEXT NOT NULL DEFAULT '[]'
);

-- table: peer_inference_disabled
CREATE TABLE peer_inference_disabled (
    peer_id        TEXT NOT NULL,
    inference_type TEXT NOT NULL,
    PRIMARY KEY (peer_id, inference_type)
);

-- table: lan_cowork_identity
CREATE TABLE lan_cowork_identity (
    key   TEXT PRIMARY KEY,
    value BLOB NOT NULL
);

-- table: agent_circuit_breaker_state
CREATE TABLE agent_circuit_breaker_state (
    process_id    TEXT PRIMARY KEY,
    state         TEXT NOT NULL DEFAULT 'CLOSED',
    open_reason   TEXT NOT NULL DEFAULT '',
    failure_count INTEGER NOT NULL DEFAULT 0,
    last_updated  TEXT NOT NULL
);

-- table: agent_budget_usage
CREATE TABLE agent_budget_usage (
    session_id       TEXT NOT NULL,
    process_id       TEXT NOT NULL,
    used_total       INTEGER NOT NULL DEFAULT 0,
    used_write       INTEGER NOT NULL DEFAULT 0,
    used_destructive INTEGER NOT NULL DEFAULT 0,
    last_updated     TEXT NOT NULL,
    PRIMARY KEY (session_id, process_id)
);

-- table: wd_tag_stats_cache
CREATE TABLE wd_tag_stats_cache (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    stats_json  TEXT    NOT NULL DEFAULT '{}',
    computed_at INTEGER NOT NULL DEFAULT 0
);

-- index: idx_files_deleted_ext
CREATE INDEX idx_files_deleted_ext ON files(is_deleted, file_ext) WHERE file_ext IS NOT NULL;

-- index: idx_tags_first_seen_mtime
CREATE INDEX idx_tags_first_seen_mtime ON tags(first_seen_mtime) WHERE first_seen_mtime IS NOT NULL;

-- table: templates_fts
CREATE VIRTUAL TABLE templates_fts
USING fts5(
    raw_prompt,
    raw_negative,
    char_positive,
    char_negative,
    content='templates',
    content_rowid='id',
    tokenize='trigram'
);

-- trigger: templates_ai
CREATE TRIGGER templates_ai AFTER INSERT ON templates BEGIN
  INSERT INTO templates_fts(rowid, raw_prompt, raw_negative, char_positive, char_negative)
  VALUES (new.id, new.raw_prompt, new.raw_negative, new.char_positive, new.char_negative);
END;

-- trigger: templates_ad
CREATE TRIGGER templates_ad AFTER DELETE ON templates BEGIN
  INSERT INTO templates_fts(templates_fts, rowid, raw_prompt, raw_negative, char_positive, char_negative)
  VALUES ('delete', old.id, old.raw_prompt, old.raw_negative, old.char_positive, old.char_negative);
END;

-- trigger: templates_au
CREATE TRIGGER templates_au AFTER UPDATE ON templates BEGIN
  INSERT INTO templates_fts(templates_fts, rowid, raw_prompt, raw_negative, char_positive, char_negative)
  VALUES ('delete', old.id, old.raw_prompt, old.raw_negative, old.char_positive, old.char_negative);
  INSERT INTO templates_fts(rowid, raw_prompt, raw_negative, char_positive, char_negative)
  VALUES (new.id, new.raw_prompt, new.raw_negative, new.char_positive, new.char_negative);
END;

-- table: md_files_fts
CREATE VIRTUAL TABLE md_files_fts
USING fts5(
    title, content,
    content=md_files, content_rowid=id
);

-- table: chat_messages_fts
CREATE VIRTUAL TABLE chat_messages_fts
USING fts5(
    content,
    content=chat_messages, content_rowid=id,
    tokenize='unicode61'
);

-- trigger: chat_msg_fts_ai
CREATE TRIGGER chat_msg_fts_ai
AFTER INSERT ON chat_messages BEGIN
  INSERT INTO chat_messages_fts(rowid, content)
  VALUES (new.id, new.content);
END;

-- trigger: chat_msg_fts_au
CREATE TRIGGER chat_msg_fts_au
AFTER UPDATE ON chat_messages BEGIN
  INSERT INTO chat_messages_fts(chat_messages_fts, rowid, content)
  VALUES ('delete', old.id, old.content);
  INSERT INTO chat_messages_fts(rowid, content)
  VALUES (new.id, new.content);
END;

-- trigger: chat_msg_fts_ad
CREATE TRIGGER chat_msg_fts_ad
AFTER DELETE ON chat_messages BEGIN
  INSERT INTO chat_messages_fts(chat_messages_fts, rowid, content)
  VALUES ('delete', old.id, old.content);
END;

-- table: files_path_fts
CREATE VIRTUAL TABLE files_path_fts
USING fts5(
    path,
    content='files',
    content_rowid='id',
    tokenize='trigram'
);

-- table: ocr_text_fts
CREATE VIRTUAL TABLE ocr_text_fts
USING fts5(
    full_text,
    content='file_ocr_results',
    content_rowid='id',
    tokenize="unicode61"
);

-- trigger: ocr_fts_ai
CREATE TRIGGER ocr_fts_ai
AFTER INSERT ON file_ocr_results BEGIN
  INSERT INTO ocr_text_fts(rowid, full_text)
  VALUES (new.id, new.full_text);
END;

-- trigger: ocr_fts_ad
CREATE TRIGGER ocr_fts_ad
AFTER DELETE ON file_ocr_results BEGIN
  INSERT INTO ocr_text_fts(ocr_text_fts, rowid, full_text)
  VALUES ('delete', old.id, old.full_text);
END;

-- trigger: ocr_fts_au
CREATE TRIGGER ocr_fts_au
AFTER UPDATE OF full_text ON file_ocr_results BEGIN
  INSERT INTO ocr_text_fts(ocr_text_fts, rowid, full_text)
  VALUES ('delete', old.id, old.full_text);
  INSERT INTO ocr_text_fts(rowid, full_text)
  VALUES (new.id, new.full_text);
END;

-- seed rows (from BASE_SCHEMA_SQL; not recoverable from sqlite_master)
-- idx_files_deleted_ext is created by migration 50 (requires file_ext generated column)

CREATE TABLE IF NOT EXISTS db_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);
INSERT OR IGNORE INTO search_stats(key, value, updated_at)
VALUES ('active_tagged_files', 0, strftime('%s','now'));
INSERT OR IGNORE INTO search_stats(key, value, updated_at)
VALUES ('active_files', 0, strftime('%s','now'));
-- Added in migration 63 (YOLO count_detected multi-source IN-list seek).
-- Mirrored here so fresh DBs match migrated schemas.
CREATE INDEX IF NOT EXISTS idx_file_annotations_source_key ON file_annotations(source, key);
-- Added by migration 86 alongside peers.inference_types. Disabled types live in
-- their own table because mDNS re-discovery may replace a peer row without
-- re-enabling a type the user turned off.
CREATE TABLE IF NOT EXISTS peer_inference_disabled (
    peer_id        TEXT NOT NULL,
    inference_type TEXT NOT NULL,
    PRIMARY KEY (peer_id, inference_type)
);
