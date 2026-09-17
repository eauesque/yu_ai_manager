//! Database backup subsystem — pure logic layer.
//!
//! Port of `extensions/builtin_backup/core_impl/` (Python). This module holds
//! only the parts that have no side effects: directory resolution, filename
//! construction and validation, retention selection, and the metadata sidecar
//! mapping. The I/O layers (SQLite online backup, route handlers, scheduler)
//! build on top of these.
//!
//! Splitting them out is deliberate. The bug class this port is most likely to
//! reproduce is a dropped mapping layer — internal representation to persisted
//! representation — and that layer cannot be exercised through a route test
//! without a real database. Here it is a pure function with a unit test.
//!
//! Named `db_backup` rather than `backup` on purpose: `.gitignore` carries an
//! unanchored `backup/` rule, which matches a directory of that name at any
//! depth. That rule is right — it covers the runtime backup directory this very
//! module resolves — so the source module steps aside instead of being carved
//! out with a negation nobody would remember to keep.

use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use serde_json::Value;

pub mod ffi;
pub mod routes;
pub mod scheduler;

/// Epoch seconds of the last successful backup, as `f64` bits, or zero when
/// there has not been one in this process.
///
/// The bit pattern is stored rather than a rounded integer: Python keeps a
/// `time.time()` float, and converting through `u64` would both lose the
/// sub-second part and require a float→int cast whose truncation and
/// sign-loss behaviour has to be reasoned about at every call. `f64::to_bits`
/// round-trips exactly and cannot misbehave.
///
/// Process memory, not persisted — Python keeps a module global and loses it
/// on restart too, so `status` reporting `last_backup_time: null` after a
/// restart is the correct answer, not a gap to be "fixed".
static LAST_BACKUP_TIME: AtomicU64 = AtomicU64::new(0);

/// Record a successful backup, in epoch seconds.
///
/// Negative and non-finite inputs collapse to "never". A clock reporting a
/// pre-epoch instant, or a NaN, must not become a *later* time than now: that
/// would hold the cooldown on permanently and silently stop every subsequent
/// backup.
pub fn set_last_backup_time(epoch_seconds: f64) {
    let stored = if epoch_seconds.is_finite() && epoch_seconds > 0.0 {
        epoch_seconds
    } else {
        0.0
    };
    LAST_BACKUP_TIME.store(stored.to_bits(), Ordering::SeqCst);
}

/// Epoch seconds of the last backup this process took, if any.
pub fn last_backup_time() -> Option<f64> {
    match LAST_BACKUP_TIME.load(Ordering::SeqCst) {
        0 => None,
        bits => Some(f64::from_bits(bits)),
    }
}

/// Whether a backup was taken recently enough to skip the next one.
///
/// Mirrors `is_within_cooldown`: with no recorded backup the answer is false,
/// *not* true — a fresh process must be allowed to back up immediately.
///
/// `last` is a parameter rather than a read of the global so the decision can
/// be tested without mutating process-wide state; tests that shared the global
/// would race each other under the default parallel runner.
pub fn is_within_cooldown_at(last: Option<f64>, config: &Value, now_epoch: f64) -> bool {
    let Some(last) = last else {
        return false;
    };
    let minutes = config
        .get("backup")
        .and_then(|b| b.get("cooldown_minutes"))
        .and_then(Value::as_f64)
        .unwrap_or(5.0);
    (now_epoch - last) < minutes * 60.0
}

/// `is_within_cooldown_at` against this process's recorded last backup.
pub fn is_within_cooldown(config: &Value, now_epoch: f64) -> bool {
    is_within_cooldown_at(last_backup_time(), config, now_epoch)
}

/// Filename prefix Python writes. Both `list` and the validators key off it.
pub const PREFIX: &str = "yu_ai_manager_";
/// Filename suffix for the backup itself.
pub const SUFFIX: &str = ".db";
/// Sidecar suffix, appended to the full backup filename (not replacing `.db`).
pub const META_SUFFIX: &str = ".meta.json";

/// Why a caller-supplied backup filename was rejected.
///
/// Each variant maps to one Python error string; they are kept distinct
/// because the three checks must each be able to reject on their own. A single
/// merged "invalid filename" would let a change to one check hide behind
/// another.
#[derive(Debug, PartialEq, Eq)]
pub enum FilenameError {
    /// Python: `filename is required` (400)
    Empty,
    /// Python: `Invalid filename` (400) — path traversal attempt.
    Traversal,
    /// Python: `Invalid backup filename format` (400)
    Format,
}

impl FilenameError {
    /// The exact message Python returns, so the two implementations agree.
    pub fn message(&self) -> &'static str {
        match self {
            FilenameError::Empty => "filename is required",
            FilenameError::Traversal => "Invalid filename",
            FilenameError::Format => "Invalid backup filename format",
        }
    }
}

/// Validate a caller-supplied backup filename.
///
/// Mirrors the guard sequence in `backup_ops.py::restore_backup` /
/// `delete_backup`. The order matters: an empty name is reported as missing
/// input, not as a bad format.
pub fn validate_backup_filename(name: &str) -> Result<(), FilenameError> {
    if name.is_empty() {
        return Err(FilenameError::Empty);
    }
    if name.contains('/') || name.contains('\\') || name.contains("..") {
        return Err(FilenameError::Traversal);
    }
    if !name.starts_with(PREFIX) || !name.ends_with(SUFFIX) {
        return Err(FilenameError::Format);
    }
    Ok(())
}

/// Path of the metadata sidecar for a backup.
///
/// Python uses `Path.with_suffix(_SUFFIX + _META_SUFFIX)`, which replaces the
/// final `.db` — the result is `<stem>.db.meta.json`. Appending to the full
/// name gives the same string only because the name always ends in `.db`;
/// this function keeps that reasoning in one place.
pub fn meta_path(backup: &Path) -> PathBuf {
    let mut name = backup
        .file_stem()
        .map(|s| s.to_string_lossy().into_owned())
        .unwrap_or_default();
    name.push_str(SUFFIX);
    name.push_str(META_SUFFIX);
    backup.with_file_name(name)
}

/// Resolve the directory backups live in.
///
/// Precedence mirrors `backup_utils.py::_resolve_backup_dir`:
/// explicit argument, then `backup.backup_dir` from config, then a `backup`
/// directory beside the database. Creating the directory is the caller's job —
/// this stays pure so the precedence can be tested without touching the disk.
pub fn resolve_backup_dir(explicit: Option<&str>, config: &Value, db_path: &Path) -> PathBuf {
    if let Some(dir) = explicit.filter(|d| !d.is_empty()) {
        return PathBuf::from(dir);
    }
    let configured = config
        .get("backup")
        .and_then(|b| b.get("backup_dir"))
        .and_then(Value::as_str)
        .unwrap_or("");
    if !configured.is_empty() {
        return PathBuf::from(configured);
    }
    db_path
        .parent()
        .unwrap_or_else(|| Path::new("."))
        .join("backup")
}

/// Choose which backups retention should delete.
///
/// Python sorts by name ascending and pops from the front until at most
/// `max_generations` remain; the returned vector preserves that order so the
/// caller deletes oldest first. A non-positive `max_generations` disables
/// retention entirely — matching Python, where `max_gen <= 0` returns early.
///
/// `names` is taken by value-slice rather than reading the directory so the
/// boundary (exactly `max_generations` present) can be tested directly.
pub fn retention_victims(names: &[String], max_generations: i64) -> Vec<String> {
    if max_generations <= 0 {
        return Vec::new();
    }
    let mut kept: Vec<&String> = names
        .iter()
        .filter(|n| n.starts_with(PREFIX) && n.ends_with(SUFFIX) && !n.ends_with(META_SUFFIX))
        .collect();
    kept.sort();
    // Compare in `i64` rather than casting the limit to `usize`: on a 32-bit
    // target `max_generations as usize` would truncate a large configured
    // value, and a negative one — already excluded above, but not by the cast
    // — would wrap to an enormous limit. Either way retention would silently
    // stop deleting, which is the failure that fills a disk.
    let keep = max_generations.min(i64::try_from(kept.len()).unwrap_or(i64::MAX));
    let excess = kept
        .len()
        .saturating_sub(usize::try_from(keep).unwrap_or(0));
    kept.into_iter().take(excess).cloned().collect()
}

// `GET /api/tools/backup/list` and its row mapping deliberately do NOT live
// here. That endpoint is being ported in the `worktree-rust-backup-read-endpoints`
// branch (`routes/backup_read.rs`); duplicating the row shape in two places is
// how one copy silently rots. This module owns only what the write path needs.
// The sidecar `list` reads is produced by `BackupMeta` below, so the two sides
// meet at one serialised shape rather than at two structs.

/// Build the filename for a new backup.
///
/// Python stamps `datetime.now(tz=UTC).astimezone()` — UTC converted back to
/// the machine's local zone — so the digits are **local time**, not UTC. The
/// caller passes the instant so this stays testable; production hands it
/// `Local::now()`.
pub fn make_filename(now: chrono::DateTime<chrono::Local>) -> String {
    format!("{PREFIX}{}{SUFFIX}", now.format("%Y%m%d_%H%M%S"))
}

/// The metadata sidecar written beside each backup.
///
/// `created_at` is deliberately **naive** — no UTC offset. Python builds it
/// with a bare `datetime.now().isoformat()` and carries a comment saying the
/// string is handed straight to the user, so an aware `isoformat()` would
/// append an offset the UI has never shown. Making it aware here would be a
/// silent wire-format change.
#[derive(Debug, PartialEq, serde::Serialize)]
pub struct BackupMeta {
    pub reason: String,
    pub created_at: String,
    pub created_epoch: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub schema_version: Option<i64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub source_db_path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub source_db_size: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub source_db_mtime_ns: Option<i128>,
}

/// Render the naive local timestamp Python's `datetime.now().isoformat()` produces.
///
/// Split out because this single formatting choice is the whole of the
/// aware/naive contract, and a test on it fails loudly if someone "fixes" the
/// missing offset. The fractional part follows Python too: `isoformat()` emits
/// microseconds only when they are non-zero, and omits the field entirely at
/// exactly zero.
pub fn naive_created_at(now: chrono::DateTime<chrono::Local>) -> String {
    use chrono::Timelike;
    let naive = now.naive_local();
    let micros = naive.nanosecond() / 1_000;
    if micros == 0 {
        naive.format("%Y-%m-%dT%H:%M:%S").to_string()
    } else {
        naive.format("%Y-%m-%dT%H:%M:%S%.6f").to_string()
    }
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    /// Serialises the two tests that touch `LAST_BACKUP_TIME`.
    ///
    /// The rest of this module is pure precisely so its tests need no such
    /// coordination; these two exercise the process-wide store itself, and
    /// without the lock they would race under the default parallel runner —
    /// intermittently, which is the worst way for a test to be wrong.
    fn global_clock_lock() -> std::sync::MutexGuard<'static, ()> {
        static CLOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());
        CLOCK
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
    }

    #[test]
    fn an_empty_name_is_missing_input_not_a_bad_format() {
        // The three guards must stay distinguishable: merging them would let a
        // change to one hide behind another.
        assert_eq!(validate_backup_filename(""), Err(FilenameError::Empty));
    }

    #[test]
    fn traversal_is_rejected_before_the_format_check() {
        // `../etc/passwd` fails the format check too, so a test that only
        // asserted "rejected" would pass with the traversal guard deleted.
        for name in [
            "../evil.db",
            "sub/dir.db",
            "a\\b.db",
            "yu_ai_manager_../x.db",
        ] {
            assert_eq!(
                validate_backup_filename(name),
                Err(FilenameError::Traversal),
                "{name} should be rejected as traversal"
            );
        }
    }

    #[test]
    fn the_format_check_requires_both_prefix_and_suffix() {
        // Each half tested on its own; a name failing only one still reaches
        // this guard, so disabling either half is detectable.
        assert_eq!(
            validate_backup_filename("other_20260101_000000.db"),
            Err(FilenameError::Format),
            "missing prefix"
        );
        assert_eq!(
            validate_backup_filename("yu_ai_manager_20260101_000000.sqlite"),
            Err(FilenameError::Format),
            "missing suffix"
        );
        assert!(validate_backup_filename("yu_ai_manager_20260101_000000.db").is_ok());
    }

    #[test]
    fn error_messages_match_python_verbatim() {
        assert_eq!(FilenameError::Empty.message(), "filename is required");
        assert_eq!(FilenameError::Traversal.message(), "Invalid filename");
        assert_eq!(
            FilenameError::Format.message(),
            "Invalid backup filename format"
        );
    }

    #[test]
    fn the_sidecar_sits_beside_the_backup_as_db_meta_json() {
        assert_eq!(
            meta_path(Path::new("/b/yu_ai_manager_20260101_000000.db")),
            PathBuf::from("/b/yu_ai_manager_20260101_000000.db.meta.json")
        );
    }

    #[test]
    fn backup_dir_precedence_is_argument_then_config_then_beside_the_db() {
        let with_cfg = json!({"backup": {"backup_dir": "/from/config"}});
        let no_cfg = json!({"backup": {"backup_dir": ""}});
        let db = Path::new("/data/tags.db");

        // Argument wins over a configured directory.
        assert_eq!(
            resolve_backup_dir(Some("/from/arg"), &with_cfg, db),
            PathBuf::from("/from/arg")
        );
        // Config wins over the fallback.
        assert_eq!(
            resolve_backup_dir(None, &with_cfg, db),
            PathBuf::from("/from/config")
        );
        // Fallback is a `backup` directory beside the database.
        assert_eq!(
            resolve_backup_dir(None, &no_cfg, db),
            PathBuf::from("/data/backup")
        );
        // An empty argument is not a choice; it falls through to config.
        assert_eq!(
            resolve_backup_dir(Some(""), &with_cfg, db),
            PathBuf::from("/from/config")
        );
        // A config with no backup section at all still resolves.
        assert_eq!(
            resolve_backup_dir(None, &json!({}), db),
            PathBuf::from("/data/backup")
        );
    }

    fn names(n: usize) -> Vec<String> {
        (1..=n)
            .map(|i| format!("{PREFIX}2026010{i}_000000{SUFFIX}"))
            .collect()
    }

    #[test]
    fn retention_deletes_oldest_first_and_keeps_max_generations() {
        let victims = retention_victims(&names(7), 5);
        assert_eq!(
            victims,
            vec![
                format!("{PREFIX}20260101_000000{SUFFIX}"),
                format!("{PREFIX}20260102_000000{SUFFIX}"),
            ],
            "the two oldest go, in oldest-first order"
        );
    }

    #[test]
    fn retention_at_exactly_max_generations_deletes_nothing() {
        // The boundary: `>` vs `>=` in the loop condition is only visible here.
        assert!(retention_victims(&names(5), 5).is_empty());
        assert_eq!(retention_victims(&names(6), 5).len(), 1);
    }

    #[test]
    fn a_non_positive_max_generations_disables_retention() {
        assert!(retention_victims(&names(9), 0).is_empty());
        assert!(retention_victims(&names(9), -1).is_empty());
    }

    #[test]
    fn an_absurdly_large_max_generations_deletes_nothing() {
        // Guards the `i64 -> usize` narrowing: a cast that truncated on a
        // 32-bit target could turn a huge limit into a small one and start
        // deleting backups the user asked to keep.
        assert!(retention_victims(&names(9), i64::MAX).is_empty());
    }

    #[test]
    fn a_non_finite_or_negative_backup_time_reads_as_never() {
        // A pre-epoch or NaN clock reading must not wrap into a huge positive
        // time: that would hold the cooldown on forever and stop all backups.
        let _serialised = global_clock_lock();
        for value in [-1.0_f64, f64::NAN, f64::NEG_INFINITY] {
            set_last_backup_time(value);
            assert_eq!(last_backup_time(), None, "{value} must read as never");
        }
        set_last_backup_time(0.0);
    }

    #[test]
    fn the_backup_time_round_trips_with_its_sub_second_part() {
        // Python stores a `time.time()` float. Rounding to whole seconds would
        // make a backup taken 0.4s ago read as taken now, which shifts the
        // cooldown boundary by up to a second in the permissive direction.
        let _serialised = global_clock_lock();
        set_last_backup_time(1_700_000_000.25);
        assert_eq!(last_backup_time(), Some(1_700_000_000.25));
        set_last_backup_time(0.0);
    }

    #[test]
    fn retention_ignores_sidecars_and_foreign_files() {
        let mut all = names(6);
        all.push(format!("{PREFIX}20260101_000000{SUFFIX}{META_SUFFIX}"));
        all.push("unrelated.db".to_string());
        let victims = retention_victims(&all, 5);
        assert_eq!(
            victims,
            vec![format!("{PREFIX}20260101_000000{SUFFIX}")],
            "sidecars and foreign files must not count toward the generation cap"
        );
    }

    fn at(
        y: i32,
        mo: u32,
        d: u32,
        h: u32,
        mi: u32,
        s: u32,
        micro: u32,
    ) -> chrono::DateTime<chrono::Local> {
        use chrono::{TimeZone, Timelike};
        chrono::Local
            .with_ymd_and_hms(y, mo, d, h, mi, s)
            .unwrap()
            .with_nanosecond(micro * 1_000)
            .unwrap()
    }

    #[test]
    fn the_backup_filename_stamps_local_time_not_utc() {
        // Built from a local-zone instant: the digits must be the local clock.
        // Formatting the UTC instant instead would shift these by the offset.
        let name = make_filename(at(2026, 9, 4, 22, 7, 5, 0));
        assert_eq!(name, "yu_ai_manager_20260904_220705.db");
        // And the result must satisfy the validator the restore path applies.
        assert!(validate_backup_filename(&name).is_ok());
    }

    #[test]
    fn created_at_is_naive_and_carries_no_utc_offset() {
        // The contract: Python hands this string straight to the UI. An aware
        // `isoformat()` would append `+09:00` and change the wire format.
        let stamped = naive_created_at(at(2026, 9, 4, 22, 7, 5, 123_456));
        assert_eq!(stamped, "2026-09-04T22:07:05.123456");
        assert!(
            !stamped.contains('+') && !stamped.ends_with('Z'),
            "created_at must not carry an offset: {stamped}"
        );
    }

    #[test]
    fn created_at_omits_microseconds_at_exactly_zero() {
        // Python's isoformat drops the fractional field entirely when
        // microsecond == 0; always emitting `.000000` would diverge.
        assert_eq!(
            naive_created_at(at(2026, 9, 4, 22, 7, 5, 0)),
            "2026-09-04T22:07:05"
        );
    }

    #[test]
    fn meta_omits_absent_optional_fields_rather_than_writing_null() {
        // Python only sets `schema_version` / `source_db_*` when it could read
        // them; a null would be a different sidecar shape.
        let meta = BackupMeta {
            reason: "manual".into(),
            created_at: "2026-09-04T22:07:05".into(),
            created_epoch: 1.0,
            schema_version: None,
            source_db_path: None,
            source_db_size: None,
            source_db_mtime_ns: None,
        };
        let value = serde_json::to_value(&meta).unwrap();
        let object = value.as_object().unwrap();
        let mut keys: Vec<&str> = object.keys().map(String::as_str).collect();
        keys.sort_unstable();
        assert_eq!(keys, ["created_at", "created_epoch", "reason"]);
    }

    #[test]
    fn a_populated_meta_carries_every_python_key() {
        let meta = BackupMeta {
            reason: "scheduled".into(),
            created_at: "2026-09-04T22:07:05".into(),
            created_epoch: 2.5,
            schema_version: Some(7),
            source_db_path: Some("/data/tags.db".into()),
            source_db_size: Some(4096),
            source_db_mtime_ns: Some(1_700_000_000_000_000_000),
        };
        let value = serde_json::to_value(&meta).unwrap();
        let object = value.as_object().unwrap();
        let mut keys: Vec<&str> = object.keys().map(String::as_str).collect();
        keys.sort_unstable();
        assert_eq!(
            keys,
            [
                "created_at",
                "created_epoch",
                "reason",
                "schema_version",
                "source_db_mtime_ns",
                "source_db_path",
                "source_db_size",
            ],
            "renaming any sidecar key silently breaks `list`"
        );
    }
}
