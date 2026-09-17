use serde::Serialize;
use serde_json::Value;
use std::time::{Duration, SystemTime};
use tokio_util::sync::CancellationToken;

/// Runtime state of a single job (not serialized directly).
#[derive(Clone, Debug)]
pub struct Job {
    pub job_id: String,
    pub label: String,
    pub running: bool,
    pub phase: Option<String>,
    pub current: Option<u64>,
    pub total: Option<u64>,
    pub percent: Option<f64>,
    pub message: Option<String>,
    pub detail: Option<String>,
    pub error: Option<String>,
    pub result: Option<Value>,
    pub started_at: SystemTime,
    pub finished_at: Option<SystemTime>,
    pub cancel_token: CancellationToken,
}

/// Serialisable snapshot — matches Python `Job.to_dict()` (jobs_model.py:67-83).
/// `started_at` / `finished_at` are intentionally absent (internal state only).
/// `result` is omitted when `None`.
#[derive(Serialize)]
pub struct JobDict {
    pub job_id: String,
    pub label: String,
    pub running: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub phase: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub current: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub total: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub percent: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub detail: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
    pub elapsed_seconds: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<Value>,
}

#[derive(serde::Serialize)]
pub struct StatusResult {
    pub has_active: bool,
    pub active: Vec<JobDict>,
    pub recent: Vec<JobDict>,
}

impl Job {
    pub fn to_dict(&self) -> JobDict {
        // Mirrors Python: elapsed = (finished_at or time.time()) - started_at
        // For finished jobs this is fixed; for running jobs it grows.
        let elapsed = self
            .finished_at
            .and_then(|fin| fin.duration_since(self.started_at).ok())
            .unwrap_or_else(|| self.started_at.elapsed().unwrap_or(Duration::ZERO));
        JobDict {
            job_id: self.job_id.clone(),
            label: self.label.clone(),
            running: self.running,
            phase: self.phase.clone(),
            current: self.current,
            total: self.total,
            percent: self.percent,
            message: self.message.clone(),
            detail: self.detail.clone(),
            error: self.error.clone(),
            elapsed_seconds: (elapsed.as_secs_f64() * 10.0).round() / 10.0,
            result: self.result.clone(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn make_job(running: bool, result: Option<Value>) -> Job {
        Job {
            job_id: "job-1".into(),
            label: "Test Job".into(),
            running,
            phase: None,
            current: None,
            total: None,
            percent: None,
            message: None,
            detail: None,
            error: None,
            result,
            started_at: SystemTime::now(),
            finished_at: if !running {
                Some(SystemTime::now())
            } else {
                None
            },
            cancel_token: CancellationToken::new(),
        }
    }

    #[test]
    fn test_to_dict_no_started_at() {
        let d = serde_json::to_value(make_job(true, None).to_dict()).unwrap();
        assert!(
            d.get("started_at").is_none(),
            "started_at must not appear in JSON"
        );
        assert!(
            d.get("finished_at").is_none(),
            "finished_at must not appear in JSON"
        );
    }

    #[test]
    fn test_to_dict_result_absent_when_none() {
        let d = serde_json::to_value(make_job(false, None).to_dict()).unwrap();
        assert!(d.get("result").is_none(), "result must be absent when None");
    }

    #[test]
    fn test_to_dict_result_present_when_some() {
        let d =
            serde_json::to_value(make_job(false, Some(json!({"files": 10}))).to_dict()).unwrap();
        assert_eq!(d["result"]["files"], 10);
    }

    #[test]
    fn test_to_dict_elapsed_seconds_present() {
        let d = serde_json::to_value(make_job(true, None).to_dict()).unwrap();
        assert!(
            d["elapsed_seconds"].is_f64() || d["elapsed_seconds"].is_number(),
            "elapsed_seconds must be a number"
        );
    }

    #[test]
    fn test_to_dict_elapsed_fixed_when_finished() {
        use std::time::Duration;
        let started = SystemTime::now() - Duration::from_secs(5);
        let finished = started + Duration::from_secs(3);
        let job = Job {
            job_id: "j".into(),
            label: "l".into(),
            running: false,
            phase: None,
            current: None,
            total: None,
            percent: None,
            message: None,
            detail: None,
            error: None,
            result: None,
            started_at: started,
            finished_at: Some(finished),
            cancel_token: CancellationToken::new(),
        };
        let d1 = job.to_dict();
        // elapsed should be finished_at - started_at ≈ 3.0, not 5.0
        assert!(
            (d1.elapsed_seconds - 3.0).abs() < 0.2,
            "elapsed for finished job must equal finished_at - started_at, got {}",
            d1.elapsed_seconds
        );
    }

    #[test]
    fn test_to_dict_optional_fields_absent_by_default() {
        let d = serde_json::to_value(make_job(true, None).to_dict()).unwrap();
        for field in &[
            "phase", "current", "total", "percent", "message", "detail", "error",
        ] {
            assert!(d.get(field).is_none(), "{field} must be absent when None");
        }
    }

    #[test]
    fn test_to_dict_required_fields_always_present() {
        let d = serde_json::to_value(make_job(true, None).to_dict()).unwrap();
        for field in &["job_id", "label", "running", "elapsed_seconds"] {
            assert!(d.get(field).is_some(), "{field} must always be present");
        }
    }
}
