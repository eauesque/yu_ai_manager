//! Periodic and event-driven backups.
//!
//! Port of `extensions/builtin_backup/core_impl/scheduler.py` and
//! `event_handler.py`, plus the start-up gating in
//! `core/web/runtime_subsystems.py::init_backup_system`.
//!
//! The scan-complete trigger subscribes to the SSE hub rather than calling
//! into `scan_manager`: `scan.complete` is already broadcast there, so the
//! scan path needs no edit and the coupling stays one-way.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

use serde_json::Value;

use crate::state::{AppState, SharedState};

/// Whether the periodic timer is running.
///
/// `status` reports this, so it must reflect reality rather than a constant:
/// reporting a scheduler that is not there is the same class of fabricated
/// state the 503 stubs were introduced to stop.
static SCHEDULER_RUNNING: AtomicBool = AtomicBool::new(false);

pub fn scheduler_running() -> bool {
    SCHEDULER_RUNNING.load(Ordering::SeqCst)
}

/// Whether the backup subsystem should run at all.
///
/// Mirrors `runtime_subsystems.py`: the subsystem is registered for the
/// `full` profile only, with a `TAGDB_ENABLE_BACKUP` override, and then
/// `init_backup_system` additionally requires `backup.enabled`.
pub fn subsystem_enabled(server_mode: &str, config: &Value) -> bool {
    if let Ok(flag) = std::env::var("TAGDB_ENABLE_BACKUP") {
        // Python's SubsystemDef override wins over the profile list.
        return matches!(flag.trim(), "1" | "true" | "True" | "yes" | "on");
    }
    if server_mode != "full" {
        return false;
    }
    config
        .get("backup")
        .and_then(|b| b.get("enabled"))
        .and_then(Value::as_bool)
        .unwrap_or(true)
}

/// Interval between periodic backups, in hours. Zero or less disables them.
pub fn periodic_interval_hours(config: &Value) -> f64 {
    config
        .get("backup")
        .and_then(|b| b.get("periodic_interval_hours"))
        .and_then(Value::as_f64)
        .unwrap_or(24.0)
}

/// Whether a scan-complete event should trigger a backup.
pub fn backup_on_scan_complete(config: &Value) -> bool {
    config
        .get("backup")
        .and_then(|b| b.get("backup_on_scan_complete"))
        .and_then(Value::as_bool)
        .unwrap_or(true)
}

/// Start the periodic timer and the scan-complete subscriber.
///
/// Both are spawned only when the subsystem is enabled, so a `gateway` or
/// `server` profile — or `backup.enabled: false` — leaves no task behind and
/// `status` honestly reports `scheduler_running: false`.
pub fn start(state: &SharedState) {
    let config = crate::config_io::load(&state.config.config_path);
    if !subsystem_enabled(&state.config.server_mode, &config) {
        tracing::info!("[BACKUP] Backup system disabled");
        return;
    }

    spawn_scan_complete_listener(state.clone());

    let interval = periodic_interval_hours(&config);
    if interval <= 0.0 {
        tracing::info!("[BACKUP] Periodic backup disabled");
        return;
    }
    SCHEDULER_RUNNING.store(true, Ordering::SeqCst);
    let scheduled = state.clone();
    tokio::spawn(async move {
        let period = std::time::Duration::from_secs_f64(interval * 3600.0);
        loop {
            tokio::time::sleep(period).await;
            run_if_outside_cooldown(&scheduled, "scheduled").await;
        }
    });
    tracing::info!("[BACKUP] Scheduler started (every {interval} hours)");
}

/// Take a backup unless one was taken recently.
///
/// The cooldown is re-read from disk on every tick: a user who widens it in
/// settings should not have to restart the server for the change to take.
async fn run_if_outside_cooldown(state: &Arc<AppState>, reason: &str) {
    let config = crate::config_io::load(&state.config.config_path);
    let now = chrono::Local::now().timestamp() as f64;
    if super::is_within_cooldown(&config, now) {
        tracing::debug!("[BACKUP] {reason} backup skipped (within cooldown)");
        return;
    }
    match super::routes::create_backup(state, reason).await {
        Ok(payload) => tracing::info!(
            "[BACKUP] {reason} backup: {}",
            payload
                .get("filename")
                .and_then(|v| v.as_str())
                .unwrap_or("")
        ),
        Err(message) => tracing::warn!("[BACKUP] {reason} backup failed: {message}"),
    }
}

/// Subscribe to `scan.complete` and back up when one arrives.
fn spawn_scan_complete_listener(state: SharedState) {
    let mut events = state.sse_hub.subscribe();
    tokio::spawn(async move {
        loop {
            match events.recv().await {
                Ok(event) => {
                    if event.event_type != "scan.complete" {
                        continue;
                    }
                    let config = crate::config_io::load(&state.config.config_path);
                    if !backup_on_scan_complete(&config) {
                        continue;
                    }
                    run_if_outside_cooldown(&state, "scan_complete").await;
                }
                // A lagging receiver must not kill the listener: dropping
                // events is acceptable here (the next scan will fire another),
                // but silently stopping would mean backups quietly cease.
                Err(tokio::sync::broadcast::error::RecvError::Lagged(n)) => {
                    tracing::warn!("[BACKUP] scan listener lagged past {n} events");
                }
                Err(tokio::sync::broadcast::error::RecvError::Closed) => break,
            }
        }
    });
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    #[test]
    fn the_subsystem_is_full_profile_only() {
        // Python registers it for ["full"]; a gateway or server node must not
        // start taking backups of a database it may not even own.
        let on = json!({"backup": {"enabled": true}});
        assert!(subsystem_enabled("full", &on));
        assert!(!subsystem_enabled("gateway", &on));
        assert!(!subsystem_enabled("server", &on));
    }

    #[test]
    fn backup_enabled_false_disables_the_subsystem_on_the_full_profile() {
        assert!(!subsystem_enabled(
            "full",
            &json!({"backup": {"enabled": false}})
        ));
    }

    #[test]
    fn the_subsystem_defaults_to_enabled_when_unconfigured() {
        // Python's default is True. Defaulting to False here would silently
        // switch off backups for every user who never touched the setting.
        assert!(subsystem_enabled("full", &json!({})));
        assert!(subsystem_enabled("full", &json!({"backup": {}})));
    }

    #[test]
    fn the_periodic_interval_defaults_to_twenty_four_hours() {
        assert_eq!(periodic_interval_hours(&json!({})), 24.0);
        assert_eq!(
            periodic_interval_hours(&json!({"backup": {"periodic_interval_hours": 6}})),
            6.0
        );
    }

    #[test]
    fn a_zero_interval_is_kept_rather_than_treated_as_unset() {
        // Zero means "no periodic backups". Falling back to the default here
        // would restart a timer the user switched off.
        assert_eq!(
            periodic_interval_hours(&json!({"backup": {"periodic_interval_hours": 0}})),
            0.0
        );
    }

    #[test]
    fn the_scan_complete_trigger_defaults_to_on() {
        assert!(backup_on_scan_complete(&json!({})));
        assert!(!backup_on_scan_complete(
            &json!({"backup": {"backup_on_scan_complete": false}})
        ));
    }

    #[test]
    fn cooldown_is_not_in_effect_before_the_first_backup() {
        // A fresh process has no recorded backup; reporting "within cooldown"
        // would block the first backup forever.
        assert!(!super::super::is_within_cooldown_at(
            None,
            &json!({}),
            1_000_000.0
        ));
    }

    #[test]
    fn cooldown_uses_the_configured_minutes() {
        let config = json!({"backup": {"cooldown_minutes": 5}});
        let last = Some(1_000_000.0);
        assert!(super::super::is_within_cooldown_at(
            last,
            &config,
            1_000_000.0 + 299.0
        ));
        assert!(!super::super::is_within_cooldown_at(
            last,
            &config,
            1_000_000.0 + 301.0
        ));
    }

    #[test]
    fn cooldown_defaults_to_five_minutes() {
        // Python's default. The fabricated stub this port replaces claimed 60,
        // which would have suppressed eleven backups out of every twelve.
        let last = Some(0.0);
        assert!(super::super::is_within_cooldown_at(last, &json!({}), 299.0));
        assert!(!super::super::is_within_cooldown_at(
            last,
            &json!({}),
            301.0
        ));
    }
}
