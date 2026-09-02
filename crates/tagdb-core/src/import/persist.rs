use crate::import::fallback_chain::ExtractedMeta;
use crate::import::prompt_parse::{parse_prompt_to_tags, PromptParseConfig, TemplateToken};
use crate::TagdbError;
use meta_extract::is_nai_source;
use serde_json::Value;
use sqlx::{QueryBuilder, Row, Sqlite, SqliteConnection};
use std::collections::{BTreeMap, HashMap};
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

const META_SOURCE: &str = "meta";
const SQLITE_BIND_LIMIT_SAFE_IDS: usize = 900;

pub async fn persist_regular_scan_result(
    conn: &mut SqliteConnection,
    file_id: i64,
    extracted: &ExtractedMeta,
    mtime: i64,
    lowercase_tags: bool,
) -> Result<(), TagdbError> {
    let meta_source = effective_meta_source(conn, file_id, &extracted.meta_source).await?;
    sqlx::query("UPDATE files SET meta_source = ? WHERE id = ?")
        .bind(&meta_source)
        .bind(file_id)
        .execute(&mut *conn)
        .await?;

    let tag_extraction_source = extracted
        .tag_source
        .as_deref()
        .or(extracted.raw_prompt.as_deref())
        .filter(|source| !source.is_empty());

    if let Some(source) = tag_extraction_source {
        let config = prompt_config_for_source(&meta_source, lowercase_tags);
        let parsed = parse_prompt_to_tags(source, &config);
        let file_tag_rows = build_meta_rows(conn, file_id, &parsed.tags, mtime).await?;
        replace_meta_tags_if_changed(conn, file_id, &file_tag_rows).await?;

        let template_id = upsert_template(
            conn,
            file_id,
            extracted.raw_prompt.as_deref(),
            extracted.raw_negative.as_deref(),
            &extracted.format,
            extracted.raw_meta_json.as_deref(),
        )
        .await?;
        replace_template_tokens(conn, template_id, &parsed.template_tokens).await?;
    } else if extracted.raw_meta_json.is_some() {
        replace_meta_tags_if_changed(conn, file_id, &[]).await?;
        let template_id = upsert_template(
            conn,
            file_id,
            None,
            extracted.raw_negative.as_deref(),
            &extracted.format,
            extracted.raw_meta_json.as_deref(),
        )
        .await?;
        replace_template_tokens(conn, template_id, &[]).await?;
    } else {
        replace_meta_tags_if_changed(conn, file_id, &[]).await?;
    }

    upsert_media_extract_state(
        conn,
        file_id,
        &meta_source,
        extracted.raw_meta_json.as_deref(),
    )
    .await?;

    Ok(())
}

pub async fn upsert_template(
    conn: &mut SqliteConnection,
    file_id: i64,
    raw_prompt: Option<&str>,
    raw_negative: Option<&str>,
    fmt: &str,
    raw_meta_json: Option<&str>,
) -> Result<i64, TagdbError> {
    let existing = sqlx::query(
        "SELECT id, raw_prompt, raw_negative, format, raw_meta_json FROM templates WHERE file_id = ?",
    )
    .bind(file_id)
    .fetch_optional(&mut *conn)
    .await?;

    if let Some(row) = existing {
        let template_id: i64 = row.get(0);
        let existing_raw_prompt: Option<String> = row.get(1);
        let existing_raw_negative: Option<String> = row.get(2);
        let existing_format: Option<String> = row.get(3);
        let existing_raw_meta_json: Option<String> = row.get(4);

        if existing_raw_prompt.as_deref() == raw_prompt
            && existing_raw_negative.as_deref() == raw_negative
            && existing_format.as_deref() == Some(fmt)
            && existing_raw_meta_json.as_deref() == raw_meta_json
        {
            return Ok(template_id);
        }
    }

    let template_id: i64 = sqlx::query_scalar(
        "INSERT INTO templates(file_id, raw_prompt, raw_negative, format, raw_meta_json)
         VALUES(?, ?, ?, ?, ?)
         ON CONFLICT(file_id) DO UPDATE SET
           raw_prompt = excluded.raw_prompt,
           raw_negative = excluded.raw_negative,
           format = excluded.format,
           raw_meta_json = excluded.raw_meta_json
         RETURNING id",
    )
    .bind(file_id)
    .bind(raw_prompt)
    .bind(raw_negative)
    .bind(fmt)
    .bind(raw_meta_json)
    .fetch_one(&mut *conn)
    .await?;

    Ok(template_id)
}

pub async fn replace_template_tokens(
    conn: &mut SqliteConnection,
    template_id: i64,
    tokens: &[TemplateToken],
) -> Result<(), TagdbError> {
    let new_rows: Vec<(String, String, i64)> = tokens
        .iter()
        .map(|token| {
            Ok((
                token.token_type.clone(),
                canonical_payload_json(&token.payload)?,
                token.position as i64,
            ))
        })
        .collect::<Result<_, serde_json::Error>>()
        .map_err(|err| sqlx::Error::Decode(Box::new(err)))?;

    let existing_rows = sqlx::query(
        "SELECT token_type, payload, position
         FROM template_tokens
         WHERE template_id = ?
         ORDER BY position",
    )
    .bind(template_id)
    .fetch_all(&mut *conn)
    .await?;

    let existing: Vec<(String, String, i64)> = existing_rows
        .into_iter()
        .map(|row| (row.get(0), row.get(1), row.get(2)))
        .collect();

    if existing == new_rows {
        return Ok(());
    }

    sqlx::query("DELETE FROM template_tokens WHERE template_id = ?")
        .bind(template_id)
        .execute(&mut *conn)
        .await?;

    for (token_type, payload, position) in new_rows {
        sqlx::query(
            "INSERT INTO template_tokens(template_id, token_type, payload, position)
             VALUES(?, ?, ?, ?)",
        )
        .bind(template_id)
        .bind(token_type)
        .bind(payload)
        .bind(position)
        .execute(&mut *conn)
        .await?;
    }

    Ok(())
}

pub async fn upsert_media_extract_state(
    conn: &mut SqliteConnection,
    file_id: i64,
    meta_source: &str,
    raw_meta_json: Option<&str>,
) -> Result<(), TagdbError> {
    if !meta_source.starts_with("media_") {
        return Ok(());
    }

    let payload = safe_load_json(raw_meta_json);
    let fingerprint = payload.get("fingerprint").and_then(Value::as_object);
    let cache_state = payload
        .get("cache_state")
        .and_then(value_to_string)
        .unwrap_or_else(|| {
            if meta_source.contains("error") {
                "error".to_string()
            } else {
                "ready".to_string()
            }
        });
    let error_code = payload.get("error_code").and_then(value_to_string);
    let error_at = payload.get("error_at").and_then(value_to_i64);
    let next_retry_after = payload.get("next_retry_after").and_then(value_to_i64);
    let meta_schema_version = payload
        .get("metadata_schema_version")
        .and_then(value_to_i64);
    let extracted_at_in = payload.get("metadata_extracted_at").and_then(value_to_i64);
    let metadata_source = payload
        .get("metadata_source")
        .and_then(value_to_string)
        .unwrap_or_else(|| "ffprobe".to_string());
    let metadata_source_version = payload
        .get("metadata_source_version")
        .and_then(value_to_string)
        .unwrap_or_default();
    let fingerprint_mtime = fingerprint
        .and_then(|fp| fp.get("mtime"))
        .and_then(value_to_i64);
    let fingerprint_size = fingerprint
        .and_then(|fp| fp.get("size"))
        .and_then(value_to_i64);
    let fingerprint_hash = fingerprint
        .and_then(|fp| fp.get("hash"))
        .and_then(value_to_string);

    let current = sqlx::query(
        "SELECT cache_state, metadata_schema_version, metadata_extracted_at,
                metadata_source, metadata_source_version,
                fingerprint_mtime, fingerprint_size, fingerprint_hash,
                error_code, error_at, error_count, next_retry_after
         FROM media_extract_state
         WHERE file_id = ?",
    )
    .bind(file_id)
    .fetch_optional(&mut *conn)
    .await?;

    let prev_error_count = current
        .as_ref()
        .and_then(|row| row.try_get::<Option<i64>, _>(10).ok().flatten())
        .unwrap_or(0);
    let error_count = if cache_state == "error" {
        prev_error_count + 1
    } else {
        0
    };
    let extracted_at = extracted_at_in.or_else(|| {
        current
            .as_ref()
            .and_then(|row| row.try_get::<Option<i64>, _>(2).ok().flatten())
    });
    let extracted_at = extracted_at.unwrap_or_else(unix_now);

    if let Some(row) = current.as_ref() {
        let same_ready = row.get::<String, _>(0) == cache_state
            && row.try_get::<Option<i64>, _>(1)? == meta_schema_version
            && row.try_get::<Option<i64>, _>(2)? == Some(extracted_at)
            && row
                .try_get::<Option<String>, _>(3)?
                .as_deref()
                .unwrap_or("")
                == metadata_source
            && row
                .try_get::<Option<String>, _>(4)?
                .as_deref()
                .unwrap_or("")
                == metadata_source_version
            && row.try_get::<Option<i64>, _>(5)? == fingerprint_mtime
            && row.try_get::<Option<i64>, _>(6)? == fingerprint_size
            && row.try_get::<Option<String>, _>(7)? == fingerprint_hash
            && row.try_get::<Option<String>, _>(8)? == error_code
            && row.try_get::<Option<i64>, _>(9)? == error_at
            && row.try_get::<Option<i64>, _>(10)? == Some(error_count)
            && row.try_get::<Option<i64>, _>(11)? == next_retry_after;

        if same_ready {
            return Ok(());
        }
    }

    let ts_now = unix_now();
    sqlx::query(
        "INSERT INTO media_extract_state(
           file_id, cache_state, metadata_schema_version, metadata_extracted_at,
           metadata_source, metadata_source_version,
           fingerprint_mtime, fingerprint_size, fingerprint_hash,
           error_code, error_at, error_count, next_retry_after, last_access_at, updated_at
         ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
         ON CONFLICT(file_id) DO UPDATE SET
           cache_state = excluded.cache_state,
           metadata_schema_version = excluded.metadata_schema_version,
           metadata_extracted_at = excluded.metadata_extracted_at,
           metadata_source = excluded.metadata_source,
           metadata_source_version = excluded.metadata_source_version,
           fingerprint_mtime = excluded.fingerprint_mtime,
           fingerprint_size = excluded.fingerprint_size,
           fingerprint_hash = excluded.fingerprint_hash,
           error_code = excluded.error_code,
           error_at = excluded.error_at,
           error_count = excluded.error_count,
           next_retry_after = excluded.next_retry_after,
           updated_at = excluded.updated_at",
    )
    .bind(file_id)
    .bind(cache_state)
    .bind(meta_schema_version)
    .bind(extracted_at)
    .bind(metadata_source)
    .bind(metadata_source_version)
    .bind(fingerprint_mtime)
    .bind(fingerprint_size)
    .bind(fingerprint_hash)
    .bind(error_code)
    .bind(error_at)
    .bind(error_count)
    .bind(next_retry_after)
    .bind(ts_now)
    .bind(ts_now)
    .execute(&mut *conn)
    .await?;

    Ok(())
}

async fn effective_meta_source(
    conn: &mut SqliteConnection,
    file_id: i64,
    meta_source: &str,
) -> Result<String, TagdbError> {
    if meta_source != "unknown" {
        return Ok(meta_source.to_string());
    }

    let path: Option<String> = sqlx::query_scalar("SELECT path FROM files WHERE id = ?")
        .bind(file_id)
        .fetch_optional(&mut *conn)
        .await?;
    let file_name = path
        .as_deref()
        .and_then(|p| Path::new(p).file_name())
        .and_then(|name| name.to_str())
        .unwrap_or_default();

    if file_name.starts_with("TA-") || file_name.to_ascii_lowercase().contains("tensor") {
        Ok("tensor_art".to_string())
    } else {
        Ok("unknown".to_string())
    }
}

fn prompt_config_for_source(meta_source: &str, lowercase_tags: bool) -> PromptParseConfig {
    let mut config = PromptParseConfig {
        lowercase_tags,
        ..PromptParseConfig::default()
    };
    if is_nai_source(meta_source) {
        config.prompt_syntax = "nai".to_string();
    }
    config
}

async fn build_meta_rows(
    conn: &mut SqliteConnection,
    file_id: i64,
    parsed_tags: &[(Option<String>, String, f64)],
    mtime: i64,
) -> Result<Vec<(i64, i64, f64, String)>, TagdbError> {
    let mut rows_map = BTreeMap::new();
    for (namespace, tag, weight) in parsed_tags {
        let first_seen_mtime = (mtime != 0).then_some(mtime);
        let tag_id = upsert_tag_conn(conn, namespace.as_deref(), tag, first_seen_mtime).await?;
        rows_map.insert(tag_id, (file_id, tag_id, *weight, META_SOURCE.to_string()));
    }
    Ok(rows_map.into_values().collect())
}

async fn replace_meta_tags_if_changed(
    conn: &mut SqliteConnection,
    file_id: i64,
    rows: &[(i64, i64, f64, String)],
) -> Result<(), TagdbError> {
    let existing_rows =
        sqlx::query("SELECT tag_id, weight FROM file_tags WHERE file_id = ? AND source = 'meta'")
            .bind(file_id)
            .fetch_all(&mut *conn)
            .await?;

    let existing_map: HashMap<i64, f64> = existing_rows
        .into_iter()
        .map(|row| (row.get(0), row.get(1)))
        .collect();
    let incoming_map: HashMap<i64, f64> = rows.iter().map(|row| (row.1, row.2)).collect();

    if existing_map == incoming_map {
        return Ok(());
    }

    if rows.is_empty() {
        clear_tags_for_file_conn(conn, file_id, META_SOURCE).await?;
        return Ok(());
    }

    if incoming_map.len() <= SQLITE_BIND_LIMIT_SAFE_IDS {
        let ids: Vec<i64> = incoming_map.keys().copied().collect();
        let mut builder: QueryBuilder<Sqlite> =
            QueryBuilder::new("DELETE FROM file_tags WHERE file_id = ");
        builder.push_bind(file_id);
        builder.push(" AND source = ");
        builder.push_bind(META_SOURCE);
        builder.push(" AND tag_id NOT IN (");
        let mut separated = builder.separated(", ");
        for id in ids {
            separated.push_bind(id);
        }
        separated.push_unseparated(")");
        builder.build().execute(&mut *conn).await?;
    } else {
        clear_tags_for_file_conn(conn, file_id, META_SOURCE).await?;
    }

    for (file_id, tag_id, weight, source) in rows {
        insert_file_tag_conn(conn, *file_id, *tag_id, *weight, source).await?;
    }

    Ok(())
}

async fn upsert_tag_conn(
    conn: &mut SqliteConnection,
    namespace: Option<&str>,
    tag: &str,
    first_seen_mtime: Option<i64>,
) -> Result<i64, TagdbError> {
    let existing: Option<(i64, Option<i64>)> =
        sqlx::query_as("SELECT id, first_seen_mtime FROM tags WHERE tag = ? AND namespace IS ?")
            .bind(tag)
            .bind(namespace)
            .fetch_optional(&mut *conn)
            .await?;

    if let Some((tag_id, existing_mtime)) = existing {
        if let Some(new_mtime) = first_seen_mtime {
            if existing_mtime.is_none_or(|old_mtime| new_mtime < old_mtime) {
                sqlx::query(
                    "UPDATE tags
                     SET first_seen_mtime = ?
                     WHERE id = ? AND (first_seen_mtime IS NULL OR first_seen_mtime > ?)",
                )
                .bind(new_mtime)
                .bind(tag_id)
                .bind(new_mtime)
                .execute(&mut *conn)
                .await?;
            }
        }
        return Ok(tag_id);
    }

    let res = sqlx::query("INSERT INTO tags(tag, namespace, first_seen_mtime) VALUES(?, ?, ?)")
        .bind(tag)
        .bind(namespace)
        .bind(first_seen_mtime)
        .execute(&mut *conn)
        .await?;
    Ok(res.last_insert_rowid())
}

async fn insert_file_tag_conn(
    conn: &mut SqliteConnection,
    file_id: i64,
    tag_id: i64,
    weight: f64,
    source: &str,
) -> Result<(), TagdbError> {
    // Matches Python's insert_file_tag: the real file_tags UNIQUE constraint
    // is (file_id, tag_id) only (no source column), so a tag can have just
    // one row per file regardless of which source wrote it. On conflict,
    // 'user' always wins (user edits are never silently reclassified);
    // otherwise the existing source is preserved rather than overwritten by
    // whichever source happens to write last (e.g. meta re-scan shouldn't
    // downgrade a wd14-sourced row).
    sqlx::query(
        "INSERT INTO file_tags(file_id, tag_id, weight, source) VALUES(?, ?, ?, ?)
         ON CONFLICT(file_id, tag_id) DO UPDATE SET weight = excluded.weight,
           source = CASE WHEN excluded.source = 'user' THEN 'user'
                         ELSE file_tags.source END
         WHERE file_tags.weight IS NOT excluded.weight
            OR (
              CASE WHEN excluded.source = 'user' THEN 'user'
                   ELSE file_tags.source END
            ) IS NOT file_tags.source",
    )
    .bind(file_id)
    .bind(tag_id)
    .bind(weight)
    .bind(source)
    .execute(&mut *conn)
    .await?;
    Ok(())
}

async fn clear_tags_for_file_conn(
    conn: &mut SqliteConnection,
    file_id: i64,
    source: &str,
) -> Result<(), TagdbError> {
    sqlx::query("DELETE FROM file_tags WHERE file_id = ? AND source = ?")
        .bind(file_id)
        .bind(source)
        .execute(&mut *conn)
        .await?;
    Ok(())
}

fn canonical_payload_json(payload: &HashMap<String, Value>) -> Result<String, serde_json::Error> {
    let sorted = payload
        .iter()
        .map(|(key, value)| (key.clone(), value.clone()))
        .collect::<BTreeMap<_, _>>();
    serde_json::to_string(&sorted)
}

fn safe_load_json(raw: Option<&str>) -> serde_json::Map<String, Value> {
    raw.and_then(|text| serde_json::from_str::<Value>(text).ok())
        .and_then(|value| value.as_object().cloned())
        .unwrap_or_default()
}

fn value_to_string(value: &Value) -> Option<String> {
    match value {
        Value::Null => None,
        Value::String(text) => Some(text.clone()),
        other => Some(other.to_string()),
    }
}

fn value_to_i64(value: &Value) -> Option<i64> {
    match value {
        Value::Number(number) => number
            .as_i64()
            .or_else(|| number.as_u64().map(|v| v as i64)),
        Value::String(text) if !text.is_empty() => text.parse::<i64>().ok(),
        Value::Bool(value) => Some(i64::from(*value)),
        _ => None,
    }
}

fn unix_now() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs() as i64)
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
    use sqlx::SqlitePool;
    use std::str::FromStr;
    use tempfile::NamedTempFile;

    async fn pool_with_persist_tables() -> (NamedTempFile, SqlitePool) {
        let f = NamedTempFile::new().unwrap();
        let path = format!("sqlite://{}", f.path().display());
        let opts = SqliteConnectOptions::from_str(&path)
            .unwrap()
            .create_if_missing(true);
        let pool = SqlitePoolOptions::new()
            .max_connections(1)
            .connect_with(opts)
            .await
            .unwrap();

        sqlx::raw_sql(
            "CREATE TABLE files(
               id INTEGER PRIMARY KEY,
               path TEXT NOT NULL UNIQUE,
               mtime INTEGER NOT NULL,
               size INTEGER NOT NULL,
               meta_source TEXT
             );
             CREATE TABLE tags(
               id INTEGER PRIMARY KEY,
               tag TEXT NOT NULL,
               namespace TEXT,
               first_seen_mtime INTEGER,
               UNIQUE(tag, namespace)
             );
             CREATE TABLE file_tags(
               file_id INTEGER NOT NULL,
               tag_id INTEGER NOT NULL,
               weight REAL NOT NULL DEFAULT 1.0,
               source TEXT NOT NULL DEFAULT 'meta',
               UNIQUE(file_id, tag_id),
               FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE,
               FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
             );
             CREATE TABLE templates(
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
             CREATE TABLE template_tokens(
               id INTEGER PRIMARY KEY,
               template_id INTEGER NOT NULL,
               token_type TEXT NOT NULL,
               payload TEXT NOT NULL,
               position INTEGER NOT NULL,
               FOREIGN KEY(template_id) REFERENCES templates(id) ON DELETE CASCADE
             );
             CREATE TABLE media_extract_state(
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
             );",
        )
        .execute(&pool)
        .await
        .unwrap();

        sqlx::query("INSERT INTO files(id, path, mtime, size) VALUES(1, '/tmp/image.png', 0, 0)")
            .execute(&pool)
            .await
            .unwrap();
        (f, pool)
    }

    #[tokio::test]
    async fn persist_replaces_only_meta_tags_and_writes_template_tokens() {
        let (_f, pool) = pool_with_persist_tables().await;
        sqlx::query("INSERT INTO tags(id, tag, namespace) VALUES(100, 'old', NULL)")
            .execute(&pool)
            .await
            .unwrap();
        sqlx::query("INSERT INTO tags(id, tag, namespace) VALUES(101, 'wd', NULL)")
            .execute(&pool)
            .await
            .unwrap();
        sqlx::query(
            "INSERT INTO file_tags(file_id, tag_id, weight, source) VALUES(1, 100, 1.0, 'meta')",
        )
        .execute(&pool)
        .await
        .unwrap();
        sqlx::query(
            "INSERT INTO file_tags(file_id, tag_id, weight, source) VALUES(1, 101, 1.0, 'wd14')",
        )
        .execute(&pool)
        .await
        .unwrap();

        let extracted = ExtractedMeta {
            meta_source: "novelai_png".to_string(),
            format: "png".to_string(),
            raw_prompt: Some("Cat, ||red|blue||".to_string()),
            raw_negative: Some("bad".to_string()),
            raw_meta_json: Some("{\"x\":1}".to_string()),
            tag_source: None,
        };
        let mut conn = pool.acquire().await.unwrap();
        persist_regular_scan_result(&mut conn, 1, &extracted, 1234, true)
            .await
            .unwrap();
        drop(conn);

        let old_meta_count: i64 = sqlx::query_scalar(
            "SELECT COUNT(*)
             FROM file_tags ft JOIN tags t ON t.id = ft.tag_id
             WHERE ft.file_id = 1 AND ft.source = 'meta' AND t.tag = 'old'",
        )
        .fetch_one(&pool)
        .await
        .unwrap();
        let wd_count: i64 = sqlx::query_scalar(
            "SELECT COUNT(*) FROM file_tags WHERE file_id = 1 AND source = 'wd14'",
        )
        .fetch_one(&pool)
        .await
        .unwrap();
        let cat_count: i64 = sqlx::query_scalar(
            "SELECT COUNT(*)
             FROM file_tags ft JOIN tags t ON t.id = ft.tag_id
             WHERE ft.file_id = 1 AND ft.source = 'meta' AND t.tag = 'cat'",
        )
        .fetch_one(&pool)
        .await
        .unwrap();
        let token_count: i64 =
            sqlx::query_scalar("SELECT COUNT(*) FROM template_tokens WHERE template_id = 1")
                .fetch_one(&pool)
                .await
                .unwrap();

        assert_eq!(old_meta_count, 0);
        assert_eq!(wd_count, 1);
        assert_eq!(cat_count, 1);
        assert_eq!(token_count, 1);
    }

    #[tokio::test]
    async fn upsert_template_and_tokens_short_circuit_when_unchanged() {
        let (_f, pool) = pool_with_persist_tables().await;
        let mut conn = pool.acquire().await.unwrap();
        let template_id = upsert_template(&mut conn, 1, Some("cat"), None, "png", Some("{}"))
            .await
            .unwrap();
        let parsed = parse_prompt_to_tags(
            "||red|blue||",
            &PromptParseConfig {
                preserve_templates: true,
                ..PromptParseConfig::default()
            },
        );
        replace_template_tokens(&mut conn, template_id, &parsed.template_tokens)
            .await
            .unwrap();
        sqlx::query("UPDATE template_tokens SET id = 99 WHERE template_id = ?")
            .bind(template_id)
            .execute(&mut *conn)
            .await
            .unwrap();

        let same_id = upsert_template(&mut conn, 1, Some("cat"), None, "png", Some("{}"))
            .await
            .unwrap();
        replace_template_tokens(&mut conn, template_id, &parsed.template_tokens)
            .await
            .unwrap();
        let token_id: i64 =
            sqlx::query_scalar("SELECT id FROM template_tokens WHERE template_id = ?")
                .bind(template_id)
                .fetch_one(&mut *conn)
                .await
                .unwrap();

        assert_eq!(same_id, template_id);
        assert_eq!(token_id, 99);
    }

    #[tokio::test]
    async fn media_extract_state_ignores_non_media_and_short_circuits_ready_rows() {
        let (_f, pool) = pool_with_persist_tables().await;
        let mut conn = pool.acquire().await.unwrap();
        upsert_media_extract_state(&mut conn, 1, "png", Some("{}"))
            .await
            .unwrap();
        let count: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM media_extract_state")
            .fetch_one(&mut *conn)
            .await
            .unwrap();
        assert_eq!(count, 0);

        let raw = r#"{
            "metadata_schema_version": "2",
            "metadata_extracted_at": "111",
            "metadata_source": "ffprobe",
            "metadata_source_version": "6.1",
            "fingerprint": {"mtime": "10", "size": "20", "hash": "abc"}
        }"#;
        upsert_media_extract_state(&mut conn, 1, "media_video", Some(raw))
            .await
            .unwrap();
        sqlx::query("UPDATE media_extract_state SET updated_at = 42 WHERE file_id = 1")
            .execute(&mut *conn)
            .await
            .unwrap();
        upsert_media_extract_state(&mut conn, 1, "media_video", Some(raw))
            .await
            .unwrap();

        let row: (String, i64, i64, String, i64) = sqlx::query_as(
            "SELECT cache_state, metadata_schema_version, metadata_extracted_at,
                    fingerprint_hash, updated_at
             FROM media_extract_state WHERE file_id = 1",
        )
        .fetch_one(&mut *conn)
        .await
        .unwrap();
        assert_eq!(row, ("ready".to_string(), 2, 111, "abc".to_string(), 42));
    }

    #[tokio::test]
    async fn media_extract_state_increments_error_count() {
        let (_f, pool) = pool_with_persist_tables().await;
        let raw = r#"{"cache_state":"error","error_code":"timeout","metadata_extracted_at":10}"#;
        let mut conn = pool.acquire().await.unwrap();
        upsert_media_extract_state(&mut conn, 1, "media_error", Some(raw))
            .await
            .unwrap();
        upsert_media_extract_state(&mut conn, 1, "media_error", Some(raw))
            .await
            .unwrap();

        let error_count: i64 =
            sqlx::query_scalar("SELECT error_count FROM media_extract_state WHERE file_id = 1")
                .fetch_one(&mut *conn)
                .await
                .unwrap();
        assert_eq!(error_count, 2);
    }

    #[tokio::test]
    async fn unknown_tensor_art_filename_updates_meta_source() {
        let (_f, pool) = pool_with_persist_tables().await;
        sqlx::query("UPDATE files SET path = '/tmp/TA-example.png' WHERE id = 1")
            .execute(&pool)
            .await
            .unwrap();
        let extracted = ExtractedMeta {
            meta_source: "unknown".to_string(),
            format: "png".to_string(),
            raw_prompt: None,
            raw_negative: None,
            raw_meta_json: None,
            tag_source: None,
        };
        let mut conn = pool.acquire().await.unwrap();
        persist_regular_scan_result(&mut conn, 1, &extracted, 0, true)
            .await
            .unwrap();
        drop(conn);

        let meta_source: String = sqlx::query_scalar("SELECT meta_source FROM files WHERE id = 1")
            .fetch_one(&pool)
            .await
            .unwrap();
        assert_eq!(meta_source, "tensor_art");
    }

    #[tokio::test]
    async fn replace_meta_tags_handles_more_than_safe_bind_limit() {
        let (_f, pool) = pool_with_persist_tables().await;
        sqlx::query("INSERT INTO tags(id, tag, namespace) VALUES(1000, 'stale', NULL)")
            .execute(&pool)
            .await
            .unwrap();
        sqlx::query(
            "INSERT INTO file_tags(file_id, tag_id, weight, source) VALUES(1, 1000, 1.0, 'meta')",
        )
        .execute(&pool)
        .await
        .unwrap();
        let prompt = (0..=SQLITE_BIND_LIMIT_SAFE_IDS)
            .map(|idx| format!("tag_{idx}"))
            .collect::<Vec<_>>()
            .join(", ");
        let extracted = ExtractedMeta {
            meta_source: "txt".to_string(),
            format: "unknown".to_string(),
            raw_prompt: Some(prompt),
            raw_negative: None,
            raw_meta_json: None,
            tag_source: None,
        };

        let mut conn = pool.acquire().await.unwrap();
        persist_regular_scan_result(&mut conn, 1, &extracted, 0, true)
            .await
            .unwrap();
        drop(conn);

        let meta_count: i64 = sqlx::query_scalar(
            "SELECT COUNT(*) FROM file_tags WHERE file_id = 1 AND source = 'meta'",
        )
        .fetch_one(&pool)
        .await
        .unwrap();
        let stale_count: i64 = sqlx::query_scalar(
            "SELECT COUNT(*)
             FROM file_tags ft JOIN tags t ON t.id = ft.tag_id
             WHERE ft.file_id = 1 AND ft.source = 'meta' AND t.tag = 'stale'",
        )
        .fetch_one(&pool)
        .await
        .unwrap();

        assert_eq!(meta_count, SQLITE_BIND_LIMIT_SAFE_IDS as i64 + 1);
        assert_eq!(stale_count, 0);
    }
}
