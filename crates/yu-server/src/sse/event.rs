use serde::{Deserialize, Serialize};
use serde_json::Value;

/// SSE event — matches Python `Event.to_dict()` wire format.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SseEvent {
    #[serde(rename = "type")]
    pub event_type: String,
    pub timestamp: f64,
    pub data: Value,
    pub source: String,
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_event_round_trip() {
        let ev = SseEvent {
            event_type: "scan.progress".into(),
            timestamp: 1000.5,
            data: json!({"pct": 42}),
            source: "scanner".into(),
        };
        let serialized = serde_json::to_string(&ev).unwrap();
        let decoded: SseEvent = serde_json::from_str(&serialized).unwrap();
        assert_eq!(decoded.event_type, "scan.progress");
        assert_eq!(decoded.timestamp, 1000.5);
        assert_eq!(decoded.data["pct"], 42);
        assert_eq!(decoded.source, "scanner");
    }

    #[test]
    fn test_event_type_field_renamed() {
        let ev = SseEvent {
            event_type: "job.done".into(),
            timestamp: 0.0,
            data: json!(null),
            source: "".into(),
        };
        let v: serde_json::Value = serde_json::to_value(&ev).unwrap();
        assert!(v.get("type").is_some(), "field must be renamed to 'type'");
        assert!(
            v.get("event_type").is_none(),
            "'event_type' must not appear in output"
        );
    }
}
