//! SQLite functions Python registers on every connection, ported.
//!
//! `core/services_core/db_state_functions.py::register_custom_functions` installs two
//! of them. Rust registered none, so every query that called one failed or -- worse --
//! matched different rows: `GET /api/tools/file-search` compares
//! `nfkc_lower(f.path) LIKE nfkc_lower(?)` in Python and plain `f.path LIKE ?` here,
//! which is why the parity run named `results[1].path`.
//!
//! This module ports `nfkc_lower` only. `REGEXP` is deliberately left out: Python's
//! is `re.search`, and Rust's `regex` crate is a different dialect (no backreferences,
//! no lookaround), so porting it means measuring the patterns actually used, not
//! assuming the engines agree. Recorded as its own item.

use std::os::raw::{c_char, c_int, c_void};
use std::ptr::NonNull;

use libsqlite3_sys::{
    sqlite3, sqlite3_context, sqlite3_create_function_v2, sqlite3_result_error,
    sqlite3_result_null, sqlite3_result_text, sqlite3_value, sqlite3_value_text,
    sqlite3_value_type, SQLITE_DETERMINISTIC, SQLITE_NULL, SQLITE_OK, SQLITE_TRANSIENT,
    SQLITE_UTF8,
};
use unicode_normalization::UnicodeNormalization;

/// `_SEARCH_NORMALIZE_TABLE` from `db_state_functions.py`, character for character.
///
/// Applied AFTER NFKC and lowercasing, in that order, because Python applies it that
/// way -- `unicodedata.normalize("NFKC", v).lower().translate(TABLE)`. NFKC does not
/// fold any of these itself (it leaves the dash variants, the wave dash and the
/// katakana middle dot alone), which is precisely why the table exists.
const NORMALIZE_TABLE: &[(char, char)] = &[
    ('\u{30fc}', '-'),        // KATAKANA-HIRAGANA PROLONGED SOUND MARK
    ('\u{2010}', '-'),        // HYPHEN
    ('\u{2011}', '-'),        // NON-BREAKING HYPHEN
    ('\u{2012}', '-'),        // FIGURE DASH
    ('\u{2013}', '-'),        // EN DASH
    ('\u{2014}', '-'),        // EM DASH
    ('\u{2015}', '-'),        // HORIZONTAL BAR
    ('\u{2212}', '-'),        // MINUS SIGN
    ('\u{301c}', '~'),        // WAVE DASH
    ('\u{30fb}', '\u{00b7}'), // KATAKANA MIDDLE DOT -> MIDDLE DOT
];

/// The Rust side of `nfkc_lower`.
///
/// Exposed so query builders can normalize the PATTERN the same way the column is
/// normalized: matching a raw pattern against a folded column is the same defect in
/// the other direction.
pub fn nfkc_lower(value: &str) -> String {
    value
        .nfkc()
        .flat_map(char::to_lowercase)
        .map(|ch| {
            NORMALIZE_TABLE
                .iter()
                .find_map(|(from, to)| (*from == ch).then_some(*to))
                .unwrap_or(ch)
        })
        .collect()
}

/// SQLite calls this with one argument; NULL in, NULL out, as Python's does.
unsafe extern "C" fn nfkc_lower_trampoline(
    ctx: *mut sqlite3_context,
    argc: c_int,
    argv: *mut *mut sqlite3_value,
) {
    if argc != 1 || argv.is_null() {
        sqlite3_result_error(ctx, c"nfkc_lower() takes exactly one argument".as_ptr(), -1);
        return;
    }
    let arg = *argv;
    if arg.is_null() || sqlite3_value_type(arg) == SQLITE_NULL {
        sqlite3_result_null(ctx);
        return;
    }
    let text = sqlite3_value_text(arg);
    if text.is_null() {
        sqlite3_result_null(ctx);
        return;
    }
    let bytes = std::ffi::CStr::from_ptr(text.cast::<c_char>()).to_bytes();
    // Invalid UTF-8 is handed back untouched rather than lossily rewritten: a path
    // this function cannot read is not a path it should silently alter.
    let Ok(input) = std::str::from_utf8(bytes) else {
        sqlite3_result_text(ctx, text.cast::<c_char>(), -1, SQLITE_TRANSIENT());
        return;
    };
    let folded = nfkc_lower(input);
    let len = c_int::try_from(folded.len()).unwrap_or(c_int::MAX);
    // SQLITE_TRANSIENT: sqlite copies the bytes, so the String may drop here.
    sqlite3_result_text(
        ctx,
        folded.as_ptr().cast::<c_char>(),
        len,
        SQLITE_TRANSIENT(),
    );
}

/// Install the functions on one connection handle.
///
/// Every serving pool has to do this -- a pool that skips it answers the same query
/// with different rows, and nothing else notices.
pub(crate) fn install(handle: NonNull<sqlite3>) -> Result<(), String> {
    // SAFETY: `handle` is sqlx's live connection handle, held for the duration of
    // this call by the LockedSqliteHandle the caller borrowed it from.
    let rc = unsafe {
        sqlite3_create_function_v2(
            handle.as_ptr(),
            c"nfkc_lower".as_ptr(),
            1,
            SQLITE_UTF8 | SQLITE_DETERMINISTIC,
            std::ptr::null_mut::<c_void>(),
            Some(nfkc_lower_trampoline),
            None,
            None,
            None,
        )
    };
    if rc == SQLITE_OK {
        Ok(())
    } else {
        Err(format!(
            "sqlite3_create_function_v2(nfkc_lower) returned {rc}"
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::nfkc_lower;

    /// Fixtures are the cases the table exists for, not ASCII that would pass under
    /// plain LOWER() -- a test built from ASCII would have called the unported plain
    /// `LIKE` correct.
    #[test]
    fn it_folds_what_python_folds() {
        // NFKC: full-width to half-width, then lowercased.
        assert_eq!(nfkc_lower("ＡＢＣ１２３"), "abc123");
        // Every dash variant in the table collapses to ASCII '-'.
        assert_eq!(nfkc_lower("a\u{30fc}b"), "a-b");
        assert_eq!(nfkc_lower("a\u{2010}b"), "a-b");
        assert_eq!(nfkc_lower("a\u{2011}b"), "a-b");
        assert_eq!(nfkc_lower("a\u{2012}b"), "a-b");
        assert_eq!(nfkc_lower("a\u{2013}b"), "a-b");
        assert_eq!(nfkc_lower("a\u{2014}b"), "a-b");
        assert_eq!(nfkc_lower("a\u{2015}b"), "a-b");
        assert_eq!(nfkc_lower("a\u{2212}b"), "a-b");
        // Wave dash and katakana middle dot have their own targets.
        assert_eq!(nfkc_lower("a\u{301c}b"), "a~b");
        assert_eq!(nfkc_lower("a\u{30fb}b"), "a\u{00b7}b");
        // Half-width katakana is composed by NFKC, not left as-is.
        assert_eq!(nfkc_lower("ｶﬂ"), "カfl");
        // Plain LOWER() would leave all of the above untouched -- pin that, so a
        // future "simplification" back to LOWER() fails here.
        assert_ne!(nfkc_lower("ＡＢＣ"), "ＡＢＣ".to_lowercase());
    }

    /// The registration, not the function: this fails if any pool stops installing
    /// it, which the two tests above cannot see (they call Rust directly).
    #[tokio::test]
    async fn sqlite_can_call_it_on_a_real_pool() {
        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join("fn.db");
        // create_if_missing(false) in `connect`, so make the file first.
        let url = format!("sqlite://{}?mode=rwc", path.display());
        let seed = sqlx::SqlitePool::connect(&url).await.expect("seed pool");
        sqlx::query("CREATE TABLE t(p TEXT)")
            .execute(&seed)
            .await
            .expect("create");
        sqlx::query("INSERT INTO t(p) VALUES ('ＡＢＣ'), ('a\u{2014}b')")
            .execute(&seed)
            .await
            .expect("insert");
        seed.close().await;

        let pool = super::super::connect(path.to_str().expect("utf8 path"))
            .await
            .expect("connect");
        let folded: Vec<String> = sqlx::query_scalar("SELECT nfkc_lower(p) FROM t ORDER BY rowid")
            .fetch_all(&pool)
            .await
            .expect("nfkc_lower is not registered on this pool");
        assert_eq!(folded, vec!["abc".to_string(), "a-b".to_string()]);

        // The point of the port: a LIKE against the folded column finds a row that
        // plain LIKE does not.
        let hit: i64 = sqlx::query_scalar(
            "SELECT COUNT(*) FROM t WHERE nfkc_lower(p) LIKE nfkc_lower('%ＡＢ%')",
        )
        .fetch_one(&pool)
        .await
        .expect("folded LIKE");
        assert_eq!(hit, 1);
        let raw: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM t WHERE p LIKE '%ab%'")
            .fetch_one(&pool)
            .await
            .expect("raw LIKE");
        assert_eq!(
            raw, 0,
            "if raw LIKE already matched, the fixture proves nothing"
        );
        pool.close().await;
    }

    #[test]
    fn it_leaves_ordinary_text_alone() {
        assert_eq!(
            nfkc_lower("/home/user/Pictures/a-b.png"),
            "/home/user/pictures/a-b.png"
        );
        assert_eq!(nfkc_lower(""), "");
    }
}
