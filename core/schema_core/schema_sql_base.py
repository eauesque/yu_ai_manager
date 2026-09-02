"""Base schema SQL for core file and metadata tables."""

from core.schema_core.schema_sql_search_stats import SEARCH_STATS_TRIGGER_SQL

BASE_SCHEMA_SQL_BASE = """
CREATE TABLE IF NOT EXISTS schema_version (
  version INTEGER PRIMARY KEY,
  applied_at INTEGER NOT NULL,
  description TEXT
);

CREATE TABLE IF NOT EXISTS files (
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

CREATE TABLE IF NOT EXISTS tags (
  id INTEGER PRIMARY KEY,
  tag TEXT NOT NULL,
  namespace TEXT,
  first_seen_mtime INTEGER,
  UNIQUE(tag, namespace)
);

CREATE TABLE IF NOT EXISTS file_tags (
  file_id INTEGER NOT NULL,
  tag_id INTEGER NOT NULL,
  weight REAL NOT NULL DEFAULT 1.0,
  source TEXT NOT NULL DEFAULT 'meta',
  UNIQUE(file_id, tag_id),
  FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE,
  FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS templates (
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

CREATE TABLE IF NOT EXISTS template_tokens (
  id INTEGER PRIMARY KEY,
  template_id INTEGER NOT NULL,
  token_type TEXT NOT NULL,
  payload TEXT NOT NULL,
  position INTEGER NOT NULL,
  FOREIGN KEY(template_id) REFERENCES templates(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS media_extract_state (
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

CREATE TABLE IF NOT EXISTS cache_entry (
  cache_key TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  path TEXT NOT NULL,
  file_id INTEGER,
  size_bytes INTEGER NOT NULL DEFAULT 0,
  last_access_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS clip_eligible_files (
  file_id INTEGER PRIMARY KEY,
  FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS file_tag_counts (
  file_id INTEGER PRIMARY KEY,
  tag_count INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS search_stats (
  key TEXT PRIMARY KEY,
  value INTEGER NOT NULL DEFAULT 0,
  updated_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tags_tag_lower ON tags(LOWER(tag));
CREATE INDEX IF NOT EXISTS idx_file_tags_tag_id ON file_tags(tag_id);
CREATE INDEX IF NOT EXISTS idx_files_deleted_mtime ON files(is_deleted, mtime DESC);
CREATE INDEX IF NOT EXISTS idx_files_deleted_source ON files(is_deleted, meta_source);
CREATE INDEX IF NOT EXISTS idx_file_tags_file_tag ON file_tags(file_id, tag_id);
CREATE INDEX IF NOT EXISTS idx_file_tags_source ON file_tags(source);
CREATE INDEX IF NOT EXISTS idx_file_tags_tagid_fileid ON file_tags(tag_id, file_id);
CREATE INDEX IF NOT EXISTS idx_media_extract_cache_state ON media_extract_state(cache_state);
CREATE INDEX IF NOT EXISTS idx_media_extract_next_retry ON media_extract_state(next_retry_after);
CREATE INDEX IF NOT EXISTS idx_media_extract_last_access ON media_extract_state(last_access_at);
CREATE INDEX IF NOT EXISTS idx_cache_entry_kind_last_access ON cache_entry(kind, last_access_at);
CREATE INDEX IF NOT EXISTS idx_file_tag_counts_tag_count ON file_tag_counts(tag_count);

CREATE TABLE IF NOT EXISTS collections (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  query_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_collections_sort ON collections(sort_order);

CREATE TABLE IF NOT EXISTS favorites (
  file_id INTEGER NOT NULL,
  collection_id INTEGER NOT NULL DEFAULT 1,
  added_at INTEGER NOT NULL,
  PRIMARY KEY (file_id, collection_id),
  FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE,
  FOREIGN KEY(collection_id) REFERENCES collections(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_favorites_coll_file ON favorites(collection_id, file_id);

CREATE INDEX IF NOT EXISTS idx_files_hash ON files(hash) WHERE hash IS NOT NULL AND hash != '';
CREATE INDEX IF NOT EXISTS idx_files_width ON files(width) WHERE width IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_files_height ON files(height) WHERE height IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);
CREATE INDEX IF NOT EXISTS idx_files_size ON files(size) WHERE is_deleted=0 AND size > 1024;
CREATE INDEX IF NOT EXISTS idx_files_mtime_active ON files(mtime) WHERE is_deleted = 0;
CREATE INDEX IF NOT EXISTS idx_templates_model_name ON templates(model_name) WHERE model_name IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_templates_file_id ON templates(file_id);
CREATE INDEX IF NOT EXISTS idx_files_deleted_parser_version ON files(is_deleted, parser_version);
CREATE INDEX IF NOT EXISTS idx_files_deleted_path ON files(is_deleted, path);
CREATE INDEX IF NOT EXISTS idx_files_has_sweep ON files(id) WHERE has_sweep=1;
-- idx_files_deleted_ext is created by migration 50 (requires file_ext generated column)

CREATE TABLE IF NOT EXISTS db_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sweeps (
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
CREATE INDEX IF NOT EXISTS idx_sweeps_created_at ON sweeps(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sweeps_bridge ON sweeps(bridge);
CREATE INDEX IF NOT EXISTS idx_sweeps_checkpoint ON sweeps(checkpoint) WHERE checkpoint IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sweeps_sampler ON sweeps(sampler) WHERE sampler IS NOT NULL;

CREATE TABLE IF NOT EXISTS sweep_axes (
  sweep_id TEXT NOT NULL,
  axis_index INTEGER NOT NULL,
  param TEXT NOT NULL,
  total INTEGER NOT NULL,
  PRIMARY KEY (sweep_id, axis_index),
  FOREIGN KEY (sweep_id) REFERENCES sweeps(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_sweep_axes_param ON sweep_axes(param);

CREATE TABLE IF NOT EXISTS deferred_maintenance_jobs (
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
CREATE INDEX IF NOT EXISTS idx_deferred_jobs_status
  ON deferred_maintenance_jobs(status, updated_at);

CREATE TABLE IF NOT EXISTS extension_schema_versions (
  extension_name  TEXT NOT NULL,
  version         INTEGER NOT NULL,
  applied_at      INTEGER NOT NULL,
  description     TEXT DEFAULT '',
  PRIMARY KEY (extension_name, version)
);
""" + SEARCH_STATS_TRIGGER_SQL
