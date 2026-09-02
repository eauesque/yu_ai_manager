"""SQL scripts for legacy tagdb schema initialization."""

BASE_SCHEMA_SQL = """
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
  is_deleted INTEGER NOT NULL DEFAULT 0,
  meta_source TEXT,
  width INTEGER,
  height INTEGER,
  not_modified INTEGER NOT NULL DEFAULT 0,
  parser_version INTEGER NOT NULL DEFAULT 1,
  is_zip_member INTEGER NOT NULL DEFAULT 0,
  extracted_from_zip TEXT,
  extracted_from_internal TEXT,
  extraction_date INTEGER,
  extracted_to_file_id INTEGER,
  FOREIGN KEY (extracted_to_file_id) REFERENCES files(id)
);

CREATE TABLE IF NOT EXISTS tags (
  id INTEGER PRIMARY KEY,
  tag TEXT NOT NULL,
  namespace TEXT,
  UNIQUE(tag, namespace)
);

CREATE TABLE IF NOT EXISTS file_tags (
  file_id INTEGER NOT NULL,
  tag_id INTEGER NOT NULL,
  weight REAL NOT NULL DEFAULT 1.0,
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

CREATE INDEX IF NOT EXISTS idx_tags_tag_lower ON tags(LOWER(tag));
CREATE INDEX IF NOT EXISTS idx_file_tags_tag_id ON file_tags(tag_id);
CREATE INDEX IF NOT EXISTS idx_files_deleted_mtime ON files(is_deleted, mtime DESC);
CREATE INDEX IF NOT EXISTS idx_files_deleted_source ON files(is_deleted, meta_source);
CREATE INDEX IF NOT EXISTS idx_file_tags_file_tag ON file_tags(file_id, tag_id);
CREATE INDEX IF NOT EXISTS idx_media_extract_cache_state ON media_extract_state(cache_state);
CREATE INDEX IF NOT EXISTS idx_media_extract_next_retry ON media_extract_state(next_retry_after);
CREATE INDEX IF NOT EXISTS idx_media_extract_last_access ON media_extract_state(last_access_at);
CREATE INDEX IF NOT EXISTS idx_cache_entry_kind_last_access ON cache_entry(kind, last_access_at);
CREATE INDEX IF NOT EXISTS idx_files_hash ON files(hash) WHERE hash IS NOT NULL AND hash != '';
CREATE INDEX IF NOT EXISTS idx_templates_model_name ON templates(model_name) WHERE model_name IS NOT NULL;
"""

FTS_SCHEMA_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS templates_fts
USING fts5(raw_prompt, content='templates', content_rowid='id');

CREATE TRIGGER IF NOT EXISTS templates_ai AFTER INSERT ON templates BEGIN
  INSERT INTO templates_fts(rowid, raw_prompt) VALUES (new.id, new.raw_prompt);
END;
CREATE TRIGGER IF NOT EXISTS templates_ad AFTER DELETE ON templates BEGIN
  INSERT INTO templates_fts(templates_fts, rowid, raw_prompt) VALUES ('delete', old.id, old.raw_prompt);
END;
CREATE TRIGGER IF NOT EXISTS templates_au AFTER UPDATE ON templates BEGIN
  INSERT INTO templates_fts(templates_fts, rowid, raw_prompt) VALUES ('delete', old.id, old.raw_prompt);
  INSERT INTO templates_fts(rowid, raw_prompt) VALUES (new.id, new.raw_prompt);
END;
"""
