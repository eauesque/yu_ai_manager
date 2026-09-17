"""Search stats seed and trigger SQL."""

SEARCH_STATS_TRIGGER_SQL = """
INSERT OR IGNORE INTO search_stats(key, value, updated_at)
VALUES ('active_tagged_files', 0, strftime('%s','now'));
INSERT OR IGNORE INTO search_stats(key, value, updated_at)
VALUES ('active_files', 0, strftime('%s','now'));

CREATE TRIGGER IF NOT EXISTS trg_file_tags_ai_search_stats
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

CREATE TRIGGER IF NOT EXISTS trg_file_tags_ad_search_stats
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

CREATE TRIGGER IF NOT EXISTS trg_files_ai_search_stats
AFTER INSERT ON files
BEGIN
  UPDATE search_stats
  SET value = value + CASE WHEN NEW.is_deleted=0 THEN 1 ELSE 0 END,
      updated_at = strftime('%s','now')
  WHERE key='active_files';
END;

CREATE TRIGGER IF NOT EXISTS trg_files_au_deleted_search_stats
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

CREATE TRIGGER IF NOT EXISTS trg_files_ad_search_stats
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
"""
