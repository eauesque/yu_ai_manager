pub mod history;
pub mod jobs;

use std::{
    collections::HashMap,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex,
    },
};

use serde_json::{json, Value};
use tokio_cron_scheduler::{Job, JobScheduler};
use uuid::Uuid;

use crate::{
    ext_config, scheduler::history::record_execution, sse::event::SseEvent, state::AppState,
};

pub struct JobMeta {
    pub job_id: String,
    pub name: String,
    /// Display repr matching Python's str(trigger), e.g. "cron[hour='18', minute='30']"
    pub trigger_repr: String,
    pub paused: bool,
    pub running: Arc<AtomicBool>,
    pub uuid: Uuid,
}

pub struct SchedulerState {
    pub scheduler: JobScheduler,
    pub registry: Arc<Mutex<HashMap<String, JobMeta>>>,
}

struct JobDef {
    job_id: &'static str,
    name: &'static str,
    /// 6-field cron in UTC: "sec min hour dom month dow"
    cron: &'static str,
    trigger_repr: &'static str,
}

#[derive(Clone)]
struct ResolvedJob {
    job_id: &'static str,
    name: &'static str,
    cron: String,
    trigger_repr: String,
}

static JOBS: &[JobDef] = &[
    JobDef {
        job_id: "db_analyze",
        name: "DB 統計更新",
        cron: "0 30 18 * * *",
        trigger_repr: "cron[hour='18', minute='30']",
    },
    JobDef {
        job_id: "db_vacuum",
        name: "DB 圧縮",
        cron: "0 0 19 * * 6",
        trigger_repr: "cron[day_of_week='sat', hour='19']",
    },
    JobDef {
        job_id: "db_integrity_check",
        name: "DB 整合性確認",
        cron: "0 0 17 * * *",
        trigger_repr: "cron[hour='17']",
    },
    JobDef {
        job_id: "db_compress_old_raw_responses",
        name: "raw_response 削除",
        cron: "0 0 18 * * *",
        trigger_repr: "cron[hour='18']",
    },
    JobDef {
        job_id: "db_prune_old_webhook_deliveries",
        name: "webhook 履歴削除",
        cron: "0 0 18 * * 0",
        trigger_repr: "cron[day_of_week='sun', hour='18']",
    },
    JobDef {
        job_id: "db_wal_checkpoint",
        name: "WAL チェックポイント",
        cron: "0 0 * * * *",
        trigger_repr: "cron[minute='0']",
    },
];

fn default_resolved_job(def: &JobDef) -> ResolvedJob {
    ResolvedJob {
        job_id: def.job_id,
        name: def.name,
        cron: def.cron.to_string(),
        trigger_repr: def.trigger_repr.to_string(),
    }
}

fn fallback_with_warning(def: &JobDef, msg: &str) -> Option<ResolvedJob> {
    tracing::warn!("[scheduler] {}", msg);
    Some(default_resolved_job(def))
}

fn cron_field(cron: &str, idx: usize, default: u64) -> u64 {
    cron.split_whitespace()
        .nth(idx)
        .and_then(|s| s.parse().ok())
        .unwrap_or(default)
}

fn cron_dow(day_of_week: &str) -> Option<u8> {
    match day_of_week.to_ascii_lowercase().as_str() {
        "sun" => Some(0),
        "mon" => Some(1),
        "tue" => Some(2),
        "wed" => Some(3),
        "thu" => Some(4),
        "fri" => Some(5),
        "sat" => Some(6),
        _ => None,
    }
}

fn cron_dow_name(dow: &str) -> Option<&'static str> {
    match dow {
        "0" => Some("sun"),
        "1" => Some("mon"),
        "2" => Some("tue"),
        "3" => Some("wed"),
        "4" => Some("thu"),
        "5" => Some("fri"),
        "6" => Some("sat"),
        _ => None,
    }
}

fn config_u64(value: Option<&Value>) -> Option<u64> {
    value.and_then(|value| {
        value
            .as_u64()
            .or_else(|| value.as_str().and_then(|s| s.parse().ok()))
    })
}

fn trigger_repr(day_of_week: Option<&str>, hour: Option<u64>, minute: Option<u64>) -> String {
    let mut parts = Vec::new();
    if let Some(day_of_week) = day_of_week {
        parts.push(format!("day_of_week='{day_of_week}'"));
    }
    if let Some(hour) = hour {
        parts.push(format!("hour='{hour}'"));
    }
    if let Some(minute) = minute {
        parts.push(format!("minute='{minute}'"));
    }
    format!("cron[{}]", parts.join(", "))
}

fn resolve_job(def: &JobDef, app_config: &Value) -> Option<ResolvedJob> {
    if !matches!(def.job_id, "db_vacuum" | "db_integrity_check") {
        return Some(default_resolved_job(def));
    }

    let Some(job_config) = app_config
        .get("scheduler")
        .and_then(|v| v.get("jobs"))
        .and_then(|v| v.get(def.job_id))
    else {
        return Some(default_resolved_job(def));
    };

    if job_config.get("enabled").and_then(Value::as_bool) == Some(false) {
        return None;
    }

    let Some(trigger_value) = job_config.get("trigger") else {
        return Some(default_resolved_job(def));
    };
    let Some(trigger) = trigger_value.as_object() else {
        return fallback_with_warning(
            def,
            &format!(
                "unsupported trigger for {}, using default schedule",
                def.job_id
            ),
        );
    };

    if trigger
        .get("type")
        .and_then(Value::as_str)
        .unwrap_or("cron")
        != "cron"
    {
        return fallback_with_warning(
            def,
            &format!(
                "unsupported trigger type for {}, using default schedule",
                def.job_id
            ),
        );
    }

    let config_hour = config_u64(trigger.get("hour"));
    let config_minute = config_u64(trigger.get("minute"));
    let hour = config_hour.unwrap_or_else(|| cron_field(def.cron, 2, 0));
    let minute = config_minute.unwrap_or_else(|| cron_field(def.cron, 1, 0));
    let default_dow = def.cron.split_whitespace().nth(5).unwrap_or("*");
    let (dow, day_of_week_repr) = match trigger.get("day_of_week") {
        Some(Value::String(day)) => match cron_dow(day) {
            Some(dow) => (dow.to_string(), Some(day.to_ascii_lowercase())),
            None => {
                return fallback_with_warning(
                    def,
                    &format!(
                        "unsupported day_of_week for {}, using default schedule",
                        def.job_id
                    ),
                );
            }
        },
        Some(Value::Number(number)) => match number.as_u64() {
            Some(n) if n <= 6 => {
                // APScheduler numbers weekdays from Monday; cron starts at Sunday.
                let cron_dow = (n + 1) % 7;
                (
                    cron_dow.to_string(),
                    cron_dow_name(&cron_dow.to_string()).map(str::to_string),
                )
            }
            _ => {
                return fallback_with_warning(
                    def,
                    &format!(
                        "unsupported day_of_week for {}, using default schedule",
                        def.job_id
                    ),
                );
            }
        },
        Some(_) => {
            return fallback_with_warning(
                def,
                &format!(
                    "unsupported day_of_week for {}, using default schedule",
                    def.job_id
                ),
            );
        }
        None => (
            default_dow.to_string(),
            cron_dow_name(default_dow).map(str::to_string),
        ),
    };

    Some(ResolvedJob {
        job_id: def.job_id,
        name: def.name,
        cron: format!("0 {minute} {hour} * * {dow}"),
        trigger_repr: trigger_repr(day_of_week_repr.as_deref(), Some(hour), Some(minute)),
    })
}

fn emit_event(state: &Arc<AppState>, event_type: &str, data: serde_json::Value) {
    let ts = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64();
    state.sse_hub.send(SseEvent {
        event_type: event_type.to_string(),
        timestamp: ts,
        data,
        source: "scheduler".to_string(),
    });
}

pub async fn start_scheduler(shared: &Arc<AppState>) {
    let scheduler = match JobScheduler::new().await {
        Ok(s) => s,
        Err(e) => {
            tracing::error!("[scheduler] failed to create scheduler: {e}");
            return;
        }
    };

    let registry: Arc<Mutex<HashMap<String, JobMeta>>> = Arc::new(Mutex::new(HashMap::new()));
    let app_config = match ext_config::read_config(&shared.config.config_path) {
        Ok(config) => config,
        Err(error) => {
            tracing::warn!("[scheduler] failed to read config, using default schedules: {error}");
            json!({})
        }
    };
    let mut started_jobs = 0usize;

    for def in JOBS {
        let Some(def) = resolve_job(def, &app_config) else {
            tracing::info!("[scheduler] job disabled: {}", def.job_id);
            continue;
        };
        let running = Arc::new(AtomicBool::new(false));
        let weak = Arc::downgrade(shared);
        let running_clone = Arc::clone(&running);
        let job_id = def.job_id;

        let job = match Job::new_async(def.cron.as_str(), move |_uuid, _lock| {
            let weak = weak.clone();
            let running = running_clone.clone();
            Box::pin(async move {
                if running
                    .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
                    .is_err()
                {
                    if let Some(state) = weak.upgrade() {
                        emit_event(
                            &state,
                            "scheduler.job_skipped",
                            json!({"job_id": job_id, "reason": "already_running"}),
                        );
                    }
                    return;
                }
                let Some(state) = weak.upgrade() else {
                    running.store(false, Ordering::SeqCst);
                    return;
                };

                let result = run_job(job_id, &state).await;
                let (success, error, summary) = match &result {
                    Ok(s) => (true, None, s.clone()),
                    Err(e) => (false, Some(e.clone()), None),
                };

                let _ = record_execution(
                    &state.db,
                    job_id,
                    success,
                    error.as_deref(),
                    summary.as_deref(),
                )
                .await;

                if success {
                    emit_event(
                        &state,
                        "scheduler.job_executed",
                        json!({"job_id": job_id, "success": true, "result_summary": summary}),
                    );
                } else {
                    emit_event(
                        &state,
                        "scheduler.job_error",
                        json!({"job_id": job_id, "error": error}),
                    );
                    tracing::error!("[scheduler] {} failed: {:?}", job_id, error);
                }

                running.store(false, Ordering::SeqCst);
            })
        }) {
            Ok(j) => j,
            Err(e) => {
                tracing::error!("[scheduler] failed to create job {}: {e}", def.job_id);
                continue;
            }
        };

        let uuid = match scheduler.add(job).await {
            Ok(u) => u,
            Err(e) => {
                tracing::error!("[scheduler] failed to add job {}: {e}", def.job_id);
                continue;
            }
        };

        registry.lock().unwrap().insert(
            def.job_id.to_string(),
            JobMeta {
                job_id: def.job_id.to_string(),
                name: def.name.to_string(),
                trigger_repr: def.trigger_repr,
                paused: false,
                running,
                uuid,
            },
        );
        started_jobs += 1;
    }

    if let Err(e) = scheduler.start().await {
        tracing::error!("[scheduler] failed to start: {e}");
        return;
    }

    tracing::info!("[scheduler] started {} jobs", started_jobs);

    shared
        .scheduler_state
        .set(Arc::new(SchedulerState {
            scheduler,
            registry,
        }))
        .ok();
}

async fn run_job(job_id: &str, state: &AppState) -> jobs::JobResult {
    match job_id {
        "db_analyze" => jobs::run_db_analyze(&state.db).await,
        "db_vacuum" => jobs::run_db_vacuum(&state.config.db_path).await,
        "db_integrity_check" => jobs::run_db_integrity_check(&state.db_read).await,
        "db_compress_old_raw_responses" => jobs::run_db_compress_old_raw_responses(&state.db).await,
        "db_prune_old_webhook_deliveries" => {
            jobs::run_db_prune_old_webhook_deliveries(&state.db).await
        }
        "db_wal_checkpoint" => jobs::run_db_wal_checkpoint(&state.db).await,
        other => Err(format!("unknown job: {other}")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn resolve_job_maps_sunday_to_cron_zero_and_rebuilds_repr() {
        let def = JOBS
            .iter()
            .find(|job| job.job_id == "db_vacuum")
            .expect("db_vacuum job");
        let config = json!({
            "scheduler": {
                "jobs": {
                    "db_vacuum": {
                        "trigger": {
                            "type": "cron",
                            "day_of_week": "sun",
                            "hour": 3,
                            "minute": 0
                        }
                    }
                }
            }
        });

        let job = resolve_job(def, &config).expect("enabled job");

        assert_eq!(job.cron, "0 0 3 * * 0");
        assert_eq!(
            job.trigger_repr,
            "cron[day_of_week='sun', hour='3', minute='0']"
        );
    }

    #[test]
    fn resolve_job_repr_uses_fallback_hour_and_minute() {
        let def = JOBS
            .iter()
            .find(|job| job.job_id == "db_vacuum")
            .expect("db_vacuum job");
        let config = json!({
            "scheduler": {
                "jobs": {
                    "db_vacuum": {
                        "trigger": {
                            "type": "cron",
                            "day_of_week": "sun"
                        }
                    }
                }
            }
        });

        let job = resolve_job(def, &config).expect("enabled job");

        assert_eq!(job.cron, "0 0 19 * * 0");
        assert_eq!(
            job.trigger_repr,
            "cron[day_of_week='sun', hour='19', minute='0']"
        );
    }

    #[test]
    fn resolve_job_wal_checkpoint_uses_hourly_default_and_ignores_config() {
        let def = JOBS
            .iter()
            .find(|job| job.job_id == "db_wal_checkpoint")
            .expect("db_wal_checkpoint job");
        let config = json!({
            "scheduler": {
                "jobs": {
                    "db_wal_checkpoint": {
                        "enabled": false
                    }
                }
            }
        });

        let job = resolve_job(def, &config).expect("job is not config-overridable");

        assert_eq!(job.cron, "0 0 * * * *");
        assert_eq!(job.trigger_repr, "cron[minute='0']");
    }

    #[test]
    fn resolve_job_matches_defaults_without_config() {
        let config = json!({});

        for def in JOBS {
            let job = resolve_job(def, &config).expect("enabled job");
            let default = default_resolved_job(def);

            assert_eq!(job.job_id, default.job_id);
            assert_eq!(job.name, default.name);
            assert_eq!(job.cron, default.cron);
            assert_eq!(job.trigger_repr, default.trigger_repr);
        }
    }

    #[test]
    fn resolve_job_skips_disabled_job() {
        let def = JOBS
            .iter()
            .find(|job| job.job_id == "db_vacuum")
            .expect("db_vacuum job");
        let config = json!({
            "scheduler": {
                "jobs": {
                    "db_vacuum": {
                        "enabled": false
                    }
                }
            }
        });

        assert!(resolve_job(def, &config).is_none());
    }

    #[test]
    fn resolve_job_falls_back_for_non_cron_trigger() {
        let def = JOBS
            .iter()
            .find(|job| job.job_id == "db_vacuum")
            .expect("db_vacuum job");
        let config = json!({
            "scheduler": {
                "jobs": {
                    "db_vacuum": {
                        "trigger": {
                            "type": "interval",
                            "seconds": 30
                        }
                    }
                }
            }
        });

        let job = resolve_job(def, &config).expect("enabled job");
        let default = default_resolved_job(def);

        assert_eq!(job.cron, default.cron);
        assert_eq!(job.trigger_repr, default.trigger_repr);
    }

    #[test]
    fn resolve_job_maps_numeric_apscheduler_dow_to_cron_dow() {
        let def = JOBS
            .iter()
            .find(|job| job.job_id == "db_vacuum")
            .expect("db_vacuum job");
        let config = json!({
            "scheduler": {
                "jobs": {
                    "db_vacuum": {
                        "trigger": {
                            "type": "cron",
                            "day_of_week": 0
                        }
                    }
                }
            }
        });

        let job = resolve_job(def, &config).expect("enabled job");

        assert_eq!(job.cron, "0 0 19 * * 1");
        assert_eq!(
            job.trigger_repr,
            "cron[day_of_week='mon', hour='19', minute='0']"
        );
    }
}
