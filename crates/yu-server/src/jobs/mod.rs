pub mod model;

use std::{
    collections::HashMap,
    sync::Mutex,
    time::{Duration, SystemTime},
};

use model::{Job, StatusResult};
use serde_json::Value;
use tokio_util::sync::CancellationToken;

const HISTORY_TTL_SECS: u64 = 60;

pub struct JobManager {
    jobs: Mutex<HashMap<String, Job>>,
}

pub struct RunHandle {
    pub run_id: String,
    pub token: CancellationToken,
}

#[allow(clippy::large_enum_variant)]
// JobDict is the larger variant, but it is produced only on the busy path and
// moved once into the 409 response. Boxing it would allocate on every rejected
// submit to save a few words on the hot path that does not carry it.
pub enum StartOutcome {
    Started(RunHandle),
    Busy(model::JobDict),
}

impl JobManager {
    pub fn new() -> Self {
        Self {
            jobs: Mutex::new(HashMap::new()),
        }
    }

    /// Create a new running job and return its cancellation token.
    pub fn start(&self, job_id: impl Into<String>, label: impl Into<String>) -> CancellationToken {
        let token = CancellationToken::new();
        let job = Job {
            job_id: job_id.into(),
            label: label.into(),
            running: true,
            phase: None,
            current: None,
            total: None,
            percent: None,
            message: None,
            detail: None,
            error: None,
            result: None,
            started_at: SystemTime::now(),
            finished_at: None,
            cancel_token: token.clone(),
        };
        let id = job.job_id.clone();
        self.jobs.lock().unwrap().insert(id, job);
        token
    }

    /// Create a new running job only when no job with this id is running.
    /// Returns the cancellation token for the new job, or `None` if one is
    /// already running.
    pub fn start_if_idle(
        &self,
        job_id: impl Into<String>,
        label: impl Into<String>,
    ) -> Option<CancellationToken> {
        let token = CancellationToken::new();
        let job = Job {
            job_id: job_id.into(),
            label: label.into(),
            running: true,
            phase: None,
            current: None,
            total: None,
            percent: None,
            message: None,
            detail: None,
            error: None,
            result: None,
            started_at: SystemTime::now(),
            finished_at: None,
            cancel_token: token.clone(),
        };
        let id = job.job_id.clone();
        let mut jobs = self.jobs.lock().unwrap();
        if jobs.get(&id).map(|job| job.running).unwrap_or(false) {
            return None;
        }
        jobs.insert(id, job);
        Some(token)
    }

    /// Start `job_id`, or hand back a snapshot of the job already running under
    /// it. Both branches are decided under one lock: a later `get_job` would be
    /// non-atomic and could observe a job that finished in between.
    pub fn start_or_current(
        &self,
        job_id: impl Into<String>,
        label: impl Into<String>,
        run_id: impl Into<String>,
    ) -> StartOutcome {
        let id = job_id.into();
        let token = CancellationToken::new();
        let mut jobs = self.jobs.lock().unwrap();
        if let Some(existing) = jobs.get(&id) {
            if existing.running {
                return StartOutcome::Busy(existing.to_dict());
            }
        }
        let run_id = run_id.into();
        jobs.insert(
            id.clone(),
            Job {
                job_id: id,
                label: label.into(),
                running: true,
                phase: None,
                current: None,
                total: None,
                percent: None,
                message: None,
                // `detail` carries the run_id: JobDict omits started_at, so a poller
                // has no other way to tell one run from the next under a fixed job_id.
                detail: Some(run_id.clone()),
                error: None,
                result: None,
                started_at: SystemTime::now(),
                finished_at: None,
                cancel_token: token.clone(),
            },
        );
        StartOutcome::Started(RunHandle { run_id, token })
    }

    /// Finish `job_id` only if `run_id` is still the current run. Returns
    /// whether it wrote. A late run must never overwrite a newer one.
    pub fn finish_run(
        &self,
        job_id: &str,
        run_id: &str,
        result: Option<Value>,
        error: Option<String>,
    ) -> bool {
        let mut jobs = self.jobs.lock().unwrap();
        let Some(j) = jobs.get_mut(job_id) else {
            return false;
        };
        if j.detail.as_deref() != Some(run_id) {
            return false;
        }
        j.running = false;
        j.phase = Some(if error.is_some() { "error" } else { "complete" }.into());
        j.finished_at = Some(SystemTime::now());
        j.result = result;
        j.error = error;
        true
    }

    pub fn finish(&self, job_id: &str, result: Option<Value>, error: Option<String>) {
        if let Some(j) = self.jobs.lock().unwrap().get_mut(job_id) {
            j.running = false;
            j.phase = Some(if error.is_some() { "error" } else { "complete" }.into());
            j.finished_at = Some(SystemTime::now());
            j.result = result;
            j.error = error;
        }
    }

    pub fn finish_cancelled(&self, job_id: &str, result: Option<Value>) {
        if let Some(j) = self.jobs.lock().unwrap().get_mut(job_id) {
            j.running = false;
            j.phase = Some("cancelled".into());
            j.finished_at = Some(SystemTime::now());
            j.result = result;
            j.error = None;
        }
    }

    pub fn update_progress(&self, job_id: &str, current: u64, total: u64, message: Option<String>) {
        if let Some(j) = self.jobs.lock().unwrap().get_mut(job_id) {
            j.current = Some(current);
            j.total = Some(total);
            j.percent = if total > 0 {
                Some(current as f64 / total as f64 * 100.0)
            } else {
                None
            };
            j.message = message;
        }
    }

    pub fn set_phase(&self, job_id: &str, phase: impl Into<String>) {
        if let Some(j) = self.jobs.lock().unwrap().get_mut(job_id) {
            j.phase = Some(phase.into());
        }
    }

    pub fn get_job(&self, job_id: &str) -> Option<model::JobDict> {
        self.prune_history();
        self.jobs.lock().unwrap().get(job_id).map(|j| j.to_dict())
    }

    pub fn is_running(&self, job_id: &str) -> bool {
        self.jobs
            .lock()
            .unwrap()
            .get(job_id)
            .map(|j| j.running)
            .unwrap_or(false)
    }

    /// Cancel a running job. Returns true if the job existed and was running.
    pub fn cancel_job(&self, job_id: &str) -> bool {
        if let Some(j) = self.jobs.lock().unwrap().get(job_id) {
            if j.running {
                j.cancel_token.cancel();
                return true;
            }
        }
        false
    }

    pub fn get_status(&self) -> StatusResult {
        self.prune_history();
        let guard = self.jobs.lock().unwrap();
        let active: Vec<_> = guard
            .values()
            .filter(|j| j.running)
            .map(|j| j.to_dict())
            .collect();
        let recent: Vec<_> = guard
            .values()
            .filter(|j| !j.running)
            .map(|j| j.to_dict())
            .collect();
        StatusResult {
            has_active: !active.is_empty(),
            active,
            recent,
        }
    }

    fn prune_history(&self) {
        let cutoff = Duration::from_secs(HISTORY_TTL_SECS);
        self.jobs.lock().unwrap().retain(|_, j| {
            j.running
                || j.finished_at
                    .map(|t| t.elapsed().unwrap_or(Duration::ZERO) < cutoff)
                    .unwrap_or(true)
        });
    }
}

impl Default for JobManager {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_job_start_and_get() {
        let mgr = JobManager::new();
        mgr.start("j1", "My Job");
        let d = mgr.get_job("j1").expect("job must exist");
        assert_eq!(d.job_id, "j1");
        assert_eq!(d.label, "My Job");
        assert!(d.running);
    }

    #[test]
    fn test_start_if_idle_registers_job_when_idle() {
        let mgr = JobManager::new();

        let token = mgr
            .start_if_idle("j1", "My Job")
            .expect("idle job should start");

        assert!(!token.is_cancelled());
        let d = mgr.get_job("j1").expect("job must exist");
        assert_eq!(d.job_id, "j1");
        assert_eq!(d.label, "My Job");
        assert!(d.running);
    }

    #[test]
    fn test_start_if_idle_does_not_overwrite_running_job() {
        let mgr = JobManager::new();
        let original_token = mgr.start("j1", "Original Job");
        mgr.set_phase("j1", "indexing");

        assert!(mgr.start_if_idle("j1", "Replacement Job").is_none());
        assert!(!original_token.is_cancelled());
        let d = mgr.get_job("j1").expect("existing job must remain");
        assert_eq!(d.label, "Original Job");
        assert_eq!(d.phase.as_deref(), Some("indexing"));
        assert!(d.running);
    }

    #[test]
    fn start_or_current_returns_busy_snapshot_atomically() {
        let m = JobManager::new();
        let StartOutcome::Started(h) = m.start_or_current("ocr", "ocr.batch", "run-A") else {
            panic!("first start must succeed");
        };
        assert_eq!(h.run_id, "run-A");
        m.set_phase("ocr", "analyzing");
        match m.start_or_current("ocr", "ocr.pdf", "run-B") {
            StartOutcome::Busy(dict) => {
                assert_eq!(dict.job_id, "ocr");
                assert_eq!(
                    dict.label, "ocr.batch",
                    "must describe the incumbent, not the caller"
                );
                assert!(dict.running);
                assert_eq!(dict.phase.as_deref(), Some("analyzing"));
                assert_eq!(
                    dict.detail.as_deref(),
                    Some("run-A"),
                    "the incumbent's run_id"
                );
            }
            StartOutcome::Started(_) => panic!("second start must not succeed"),
        }
    }

    #[test]
    fn start_or_current_starts_again_once_finished() {
        let m = JobManager::new();
        let StartOutcome::Started(_) = m.start_or_current("ocr", "a", "run-A") else {
            panic!()
        };
        m.finish("ocr", None, None);
        assert!(matches!(
            m.start_or_current("ocr", "b", "run-B"),
            StartOutcome::Started(_)
        ));
    }

    #[test]
    fn finish_run_distinguishes_runs_that_share_a_label() {
        // The realistic case: two submissions of the same route carry the same
        // label ("ocr.single") and differ only by run_id. An implementation
        // that compares the wrong field (label instead of detail) still passes
        // `finish_run_refuses_to_write_into_a_newer_run`, because there the
        // labels differ too — it rejects for the wrong reason. Here the label
        // is identical, so only a real run_id comparison can tell them apart.
        let m = JobManager::new();
        let StartOutcome::Started(_) = m.start_or_current("ocr", "ocr.single", "run-A") else {
            panic!()
        };
        m.finish("ocr", None, None);
        let StartOutcome::Started(_) = m.start_or_current("ocr", "ocr.single", "run-B") else {
            panic!()
        };

        assert!(
            !m.finish_run("ocr", "run-A", Some(serde_json::json!({"from": "A"})), None),
            "a stale run must not write even when the labels match"
        );
        let dict = m.get_job("ocr").expect("job present");
        assert!(dict.running, "run B must still be running");
        assert!(dict.result.is_none(), "A's result must not surface as B's");
    }

    #[test]
    fn finish_run_refuses_to_write_into_a_newer_run() {
        // The failure this whole mechanism exists to prevent: run A finishing late
        // and publishing its result as run B's. Without the run_id check this
        // assertion fails and B silently carries A's output.
        let m = JobManager::new();
        let StartOutcome::Started(_) = m.start_or_current("ocr", "a", "run-A") else {
            panic!()
        };
        m.finish("ocr", None, None);
        let StartOutcome::Started(_) = m.start_or_current("ocr", "b", "run-B") else {
            panic!()
        };

        let wrote = m.finish_run("ocr", "run-A", Some(serde_json::json!({"from": "A"})), None);
        assert!(!wrote, "a stale run must not write");
        let dict = m.get_job("ocr").expect("job present");
        assert!(dict.running, "run B must still be running");
        assert_eq!(dict.detail.as_deref(), Some("run-B"));
    }

    #[test]
    fn finish_run_writes_for_the_current_run() {
        let m = JobManager::new();
        let StartOutcome::Started(h) = m.start_or_current("ocr", "a", "run-A") else {
            panic!()
        };
        assert!(m.finish_run("ocr", &h.run_id, Some(serde_json::json!({"ok": 1})), None));
        assert!(!m.is_running("ocr"));
    }

    #[test]
    fn test_job_finish_sets_running_false() {
        let mgr = JobManager::new();
        mgr.start("j2", "Finish Test");
        mgr.finish("j2", Some(json!({"ok": true})), None);
        let d = mgr.get_job("j2").unwrap();
        assert!(!d.running);
        assert_eq!(d.phase.unwrap(), "complete");
        assert_eq!(d.result.unwrap()["ok"], true);
    }

    #[test]
    fn test_job_finish_cancelled_sets_cancelled_phase() {
        let mgr = JobManager::new();
        mgr.start("j2-cancelled", "Cancelled Test");
        mgr.finish_cancelled("j2-cancelled", Some(json!({"ok": true})));

        let d = mgr.get_job("j2-cancelled").unwrap();
        assert!(!d.running);
        assert_eq!(d.phase.as_deref(), Some("cancelled"));
        assert!(d.error.is_none());
        assert_eq!(d.result.unwrap()["ok"], true);
    }

    #[test]
    fn test_job_finish_with_error() {
        let mgr = JobManager::new();
        mgr.start("j3", "Error Test");
        mgr.finish("j3", None, Some("something broke".into()));
        let d = mgr.get_job("j3").unwrap();
        assert!(!d.running);
        assert_eq!(d.phase.unwrap(), "error");
        assert_eq!(d.error.unwrap(), "something broke");
    }

    #[test]
    fn test_job_cancel() {
        let mgr = JobManager::new();
        let token = mgr.start("j4", "Cancel Test");
        assert!(!token.is_cancelled());
        assert!(mgr.cancel_job("j4"));
        assert!(token.is_cancelled());
    }

    #[test]
    fn test_job_cancel_nonexistent_returns_false() {
        let mgr = JobManager::new();
        assert!(!mgr.cancel_job("does-not-exist"));
    }

    #[test]
    fn test_job_is_running() {
        let mgr = JobManager::new();
        mgr.start("j5", "Running Check");
        assert!(mgr.is_running("j5"));
        mgr.finish("j5", None, None);
        assert!(!mgr.is_running("j5"));
        assert!(!mgr.is_running("unknown"));
    }

    #[test]
    fn test_job_update_progress() {
        let mgr = JobManager::new();
        mgr.start("j6", "Progress");
        mgr.update_progress("j6", 50, 100, Some("halfway".into()));
        let d = mgr.get_job("j6").unwrap();
        assert_eq!(d.current.unwrap(), 50);
        assert_eq!(d.total.unwrap(), 100);
        assert!((d.percent.unwrap() - 50.0).abs() < 0.001);
        assert_eq!(d.message.unwrap(), "halfway");
    }

    #[test]
    fn test_get_status_active_vs_recent() {
        let mgr = JobManager::new();
        mgr.start("active1", "Active");
        mgr.start("done1", "Done");
        mgr.finish("done1", None, None);
        let status = mgr.get_status();
        assert!(status.has_active);
        assert_eq!(status.active.len(), 1);
        assert_eq!(status.active[0].job_id, "active1");
        assert_eq!(status.recent.len(), 1);
        assert_eq!(status.recent[0].job_id, "done1");
    }

    #[test]
    fn test_get_job_unknown_returns_none() {
        let mgr = JobManager::new();
        assert!(mgr.get_job("never-started").is_none());
    }

    #[test]
    fn test_set_phase() {
        let mgr = JobManager::new();
        mgr.start("j7", "Phase Test");
        mgr.set_phase("j7", "indexing");
        let d = mgr.get_job("j7").unwrap();
        assert_eq!(d.phase.unwrap(), "indexing");
    }
}
