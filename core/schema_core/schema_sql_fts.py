"""FTS schema SQL for prompt search tables."""

FTS_SCHEMA_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS templates_fts
USING fts5(
    raw_prompt,
    raw_negative,
    char_positive,
    char_negative,
    content='templates',
    content_rowid='id',
    tokenize='trigram'
);

CREATE TRIGGER IF NOT EXISTS templates_ai AFTER INSERT ON templates BEGIN
  INSERT INTO templates_fts(rowid, raw_prompt, raw_negative, char_positive, char_negative)
  VALUES (new.id, new.raw_prompt, new.raw_negative, new.char_positive, new.char_negative);
END;
CREATE TRIGGER IF NOT EXISTS templates_ad AFTER DELETE ON templates BEGIN
  INSERT INTO templates_fts(templates_fts, rowid, raw_prompt, raw_negative, char_positive, char_negative)
  VALUES ('delete', old.id, old.raw_prompt, old.raw_negative, old.char_positive, old.char_negative);
END;
CREATE TRIGGER IF NOT EXISTS templates_au AFTER UPDATE ON templates BEGIN
  INSERT INTO templates_fts(templates_fts, rowid, raw_prompt, raw_negative, char_positive, char_negative)
  VALUES ('delete', old.id, old.raw_prompt, old.raw_negative, old.char_positive, old.char_negative);
  INSERT INTO templates_fts(rowid, raw_prompt, raw_negative, char_positive, char_negative)
  VALUES (new.id, new.raw_prompt, new.raw_negative, new.char_positive, new.char_negative);
END;

CREATE VIRTUAL TABLE IF NOT EXISTS md_files_fts
USING fts5(
    title, content,
    content=md_files, content_rowid=id
);

CREATE TRIGGER IF NOT EXISTS md_files_fts_ai
AFTER INSERT ON md_files BEGIN
  INSERT INTO md_files_fts(rowid, title, content)
  VALUES (new.id, new.title, new.content);
END;
CREATE TRIGGER IF NOT EXISTS md_files_fts_au
AFTER UPDATE ON md_files BEGIN
  INSERT INTO md_files_fts(md_files_fts, rowid, title, content)
  VALUES ('delete', old.id, old.title, old.content);
  INSERT INTO md_files_fts(rowid, title, content)
  VALUES (new.id, new.title, new.content);
END;
CREATE TRIGGER IF NOT EXISTS md_files_fts_ad
AFTER DELETE ON md_files BEGIN
  INSERT INTO md_files_fts(md_files_fts, rowid, title, content)
  VALUES ('delete', old.id, old.title, old.content);
END;

CREATE VIRTUAL TABLE IF NOT EXISTS chat_messages_fts
USING fts5(
    content,
    content=chat_messages, content_rowid=id,
    tokenize='unicode61'
);

CREATE TRIGGER IF NOT EXISTS chat_msg_fts_ai
AFTER INSERT ON chat_messages BEGIN
  INSERT INTO chat_messages_fts(rowid, content)
  VALUES (new.id, new.content);
END;
CREATE TRIGGER IF NOT EXISTS chat_msg_fts_au
AFTER UPDATE ON chat_messages BEGIN
  INSERT INTO chat_messages_fts(chat_messages_fts, rowid, content)
  VALUES ('delete', old.id, old.content);
  INSERT INTO chat_messages_fts(rowid, content)
  VALUES (new.id, new.content);
END;
CREATE TRIGGER IF NOT EXISTS chat_msg_fts_ad
AFTER DELETE ON chat_messages BEGIN
  INSERT INTO chat_messages_fts(chat_messages_fts, rowid, content)
  VALUES ('delete', old.id, old.content);
END;

CREATE VIRTUAL TABLE IF NOT EXISTS files_path_fts
USING fts5(
    path,
    content='files',
    content_rowid='id',
    tokenize='trigram'
);

CREATE TRIGGER IF NOT EXISTS files_path_fts_ai
AFTER INSERT ON files BEGIN
  INSERT INTO files_path_fts(rowid, path) VALUES (new.id, new.path);
END;
CREATE TRIGGER IF NOT EXISTS files_path_fts_ad
AFTER DELETE ON files BEGIN
  INSERT INTO files_path_fts(files_path_fts, rowid, path)
  VALUES ('delete', old.id, old.path);
END;
CREATE TRIGGER IF NOT EXISTS files_path_fts_au
AFTER UPDATE OF path ON files BEGIN
  INSERT INTO files_path_fts(files_path_fts, rowid, path)
  VALUES ('delete', old.id, old.path);
  INSERT INTO files_path_fts(rowid, path) VALUES (new.id, new.path);
END;

CREATE VIRTUAL TABLE IF NOT EXISTS ocr_text_fts
USING fts5(
    full_text,
    content='file_ocr_results',
    content_rowid='id',
    tokenize="unicode61"
);

CREATE TRIGGER IF NOT EXISTS ocr_fts_ai
AFTER INSERT ON file_ocr_results BEGIN
  INSERT INTO ocr_text_fts(rowid, full_text)
  VALUES (new.id, new.full_text);
END;
CREATE TRIGGER IF NOT EXISTS ocr_fts_ad
AFTER DELETE ON file_ocr_results BEGIN
  INSERT INTO ocr_text_fts(ocr_text_fts, rowid, full_text)
  VALUES ('delete', old.id, old.full_text);
END;
CREATE TRIGGER IF NOT EXISTS ocr_fts_au
AFTER UPDATE OF full_text ON file_ocr_results BEGIN
  INSERT INTO ocr_text_fts(ocr_text_fts, rowid, full_text)
  VALUES ('delete', old.id, old.full_text);
  INSERT INTO ocr_text_fts(rowid, full_text)
  VALUES (new.id, new.full_text);
END;
"""
