//! Deterministic, un-wired Hailo YOLO detection rule engine.

use bytes::Bytes;
use chrono::{Datelike, NaiveDateTime, Timelike};
use futures_util::future::join_all;
use indexmap::IndexMap;
use infer_core::yolo_postprocess::Detection;
use serde::{
    de::{self, Visitor},
    Deserialize, Deserializer, Serialize,
};
use serde_json::{Map, Value};
use std::{
    collections::{HashSet, VecDeque},
    future::Future,
    pin::Pin,
    sync::{Arc, Mutex},
    time::Duration,
};
use tokio::sync::{oneshot, Notify};

const EVALUATE_QUEUE_CAPACITY: usize = 8;

fn default_enabled() -> bool {
    true
}

fn deserialize_string_or_default<'de, D>(deserializer: D) -> Result<String, D::Error>
where
    D: Deserializer<'de>,
{
    Ok(Option::<String>::deserialize(deserializer)?.unwrap_or_default())
}

fn deserialize_map_or_default<'de, D>(deserializer: D) -> Result<Map<String, Value>, D::Error>
where
    D: Deserializer<'de>,
{
    Ok(Option::<Map<String, Value>>::deserialize(deserializer)?.unwrap_or_default())
}

fn deserialize_cooldown<'de, D>(deserializer: D) -> Result<i64, D::Error>
where
    D: Deserializer<'de>,
{
    struct CooldownVisitor;

    impl Visitor<'_> for CooldownVisitor {
        type Value = i64;

        fn expecting(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
            formatter.write_str("an integer or an integer-valued finite float in i64 range")
        }

        fn visit_i64<E>(self, value: i64) -> Result<Self::Value, E> {
            Ok(value)
        }

        fn visit_u64<E>(self, value: u64) -> Result<Self::Value, E>
        where
            E: de::Error,
        {
            i64::try_from(value).map_err(|_| E::custom("cooldown_sec is outside i64 range"))
        }

        // The three conditions below are exactly the checked-cast preconditions:
        // finite, integral, and inside `i64`'s range. Every value that reaches
        // the cast converts exactly; everything else is rejected as an error.
        #[allow(clippy::cast_possible_truncation)]
        fn visit_f64<E>(self, value: f64) -> Result<Self::Value, E>
        where
            E: de::Error,
        {
            if value.is_finite()
                && value.fract() == 0.0
                && (-9_223_372_036_854_775_808.0..9_223_372_036_854_775_808.0).contains(&value)
            {
                Ok(value as i64)
            } else {
                Err(E::custom("cooldown_sec must be a finite i64 integer"))
            }
        }
    }

    deserializer.deserialize_any(CooldownVisitor)
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub(crate) struct DetectionRule {
    pub(crate) id: String,
    #[serde(default, deserialize_with = "deserialize_string_or_default")]
    pub(crate) name: String,
    #[serde(default = "default_enabled")]
    pub(crate) enabled: bool,
    #[serde(default, deserialize_with = "deserialize_map_or_default")]
    pub(crate) conditions: Map<String, Value>,
    #[serde(default, deserialize_with = "deserialize_cooldown")]
    pub(crate) cooldown_sec: i64,
    #[serde(default)]
    pub(crate) actions: Vec<Value>,
    #[serde(skip)]
    last_triggered: Option<Duration>,
}

impl DetectionRule {
    fn check_class(&self, detection: &Value) -> bool {
        let Some(classes) = self.conditions.get("classes").and_then(Value::as_array) else {
            return true;
        };
        classes.is_empty()
            || classes.iter().any(|class| {
                class.as_str() == detection.get("class").and_then(Value::as_str).or(Some(""))
            })
    }

    fn check_confidence(&self, detection: &Value) -> bool {
        let Some(minimum) = self
            .conditions
            .get("min_confidence")
            .and_then(Value::as_f64)
        else {
            return true;
        };
        detection
            .get("confidence")
            .and_then(Value::as_f64)
            .unwrap_or(0.0)
            >= minimum
    }

    fn check_source(&self, source_id: &str) -> bool {
        let Some(sources) = self.conditions.get("sources").and_then(Value::as_array) else {
            return true;
        };
        sources.is_empty()
            || sources
                .iter()
                .any(|source| source.as_str() == Some(source_id))
    }

    fn check_schedule(&self, now: NaiveDateTime) -> bool {
        let Some(schedule) = self.conditions.get("schedule") else {
            return true;
        };
        let Some(schedule) = schedule.as_object() else {
            return schedule.is_null();
        };
        if schedule.is_empty() {
            return true;
        }

        if let Some(days) = schedule.get("days").and_then(Value::as_array) {
            if !days.is_empty()
                && !days.iter().any(|day| {
                    day.as_str().and_then(day_index) == Some(now.weekday().num_days_from_monday())
                })
            {
                return false;
            }
        }

        let Some(start) = schedule.get("start").and_then(Value::as_str) else {
            return true;
        };
        let Some(end) = schedule.get("end").and_then(Value::as_str) else {
            return true;
        };
        if start.is_empty() || end.is_empty() {
            return true;
        }
        let Some(start) = minutes(start) else {
            return false;
        };
        let Some(end) = minutes(end) else {
            return false;
        };
        let current = now.hour() * 60 + now.minute();
        if start <= end {
            start <= current && current < end
        } else {
            current >= start || current < end
        }
    }

    fn check_cooldown(&self, elapsed: Duration) -> bool {
        self.cooldown_sec <= 0
            || self.last_triggered.is_none_or(|last| {
                elapsed.checked_sub(last).is_some_and(|since| {
                    // `cooldown_sec <= 0` returned earlier, so this cannot wrap.
                    since >= Duration::from_secs(u64::try_from(self.cooldown_sec).unwrap_or(0))
                })
            })
    }

    pub(crate) fn matches(
        &mut self,
        source_id: &str,
        detections: &[Value],
        now: NaiveDateTime,
        elapsed: Duration,
    ) -> Vec<Value> {
        if !self.enabled
            || !self.check_cooldown(elapsed)
            || !self.check_source(source_id)
            || !self.check_schedule(now)
        {
            return Vec::new();
        }

        let matched: Vec<_> = detections
            .iter()
            .filter(|detection| self.check_class(detection) && self.check_confidence(detection))
            .cloned()
            .collect();
        if !matched.is_empty() {
            self.last_triggered = Some(elapsed);
        }
        matched
    }

    pub(crate) fn to_dict(&self) -> Map<String, Value> {
        serde_json::to_value(self)
            .expect("DetectionRule is serializable")
            .as_object()
            .expect("DetectionRule serializes as an object")
            .clone()
    }
}

fn day_index(day: &str) -> Option<u32> {
    Some(match day {
        "mon" => 0,
        "tue" => 1,
        "wed" => 2,
        "thu" => 3,
        "fri" => 4,
        "sat" => 5,
        "sun" => 6,
        _ => return None,
    })
}

fn minutes(value: &str) -> Option<u32> {
    let (hour, minute) = value.split_once(':')?;
    Some(hour.parse::<u32>().ok()? * 60 + minute.parse::<u32>().ok()?)
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub(crate) struct RuleMatch {
    pub(crate) rule: DetectionRule,
    pub(crate) detections: Vec<Value>,
}

#[derive(Default)]
pub(crate) struct RuleEngine {
    rules: IndexMap<String, DetectionRule>,
}

impl RuleEngine {
    pub(crate) fn add_rule(&mut self, rule: DetectionRule) -> DetectionRule {
        self.rules.insert(rule.id.clone(), rule.clone());
        rule
    }

    pub(crate) fn remove_rule(&mut self, rule_id: &str) -> bool {
        self.rules.shift_remove(rule_id).is_some()
    }

    pub(crate) fn update_rule(&mut self, rule_id: &str, mut rule: DetectionRule) -> DetectionRule {
        rule.id = rule_id.to_string();
        if let Some(old) = self.rules.get(rule_id) {
            rule.last_triggered = old.last_triggered;
        }
        self.rules.insert(rule_id.to_string(), rule.clone());
        rule
    }

    pub(crate) fn get_rule(&self, rule_id: &str) -> Option<&DetectionRule> {
        self.rules.get(rule_id)
    }

    pub(crate) fn list_rules(&self) -> Vec<DetectionRule> {
        self.rules.values().cloned().collect()
    }

    pub(crate) fn evaluate(
        &mut self,
        source_id: &str,
        detections: &[Value],
        now: NaiveDateTime,
        elapsed: Duration,
    ) -> Vec<RuleMatch> {
        if detections.is_empty() {
            return Vec::new();
        }
        self.rules
            .values_mut()
            .filter_map(|rule| {
                let matched = rule.matches(source_id, detections, now, elapsed);
                (!matched.is_empty()).then(|| RuleMatch {
                    rule: rule.clone(),
                    detections: matched,
                })
            })
            .collect()
    }

    pub(crate) fn load_rules(&mut self, rules: Vec<DetectionRule>) {
        self.rules = rules
            .into_iter()
            .map(|rule| (rule.id.clone(), rule))
            .collect();
    }

    pub(crate) fn export_rules(&self) -> Vec<DetectionRule> {
        self.list_rules()
    }
}

#[derive(Clone, Debug, PartialEq)]
pub(crate) struct TriggerFrame {
    pub(crate) bytes: Bytes,
    pub(crate) width: u32,
    pub(crate) height: u32,
}

#[derive(Clone, Debug, PartialEq)]
pub(crate) struct ActionBatch {
    pub(crate) source_id: String,
    pub(crate) rule: DetectionRule,
    pub(crate) actions: Vec<Value>,
    pub(crate) detections: Vec<Value>,
    pub(crate) trigger_frame: TriggerFrame,
}

type ActionFuture = Pin<Box<dyn Future<Output = ()> + Send>>;
type ActionExecutor = Arc<dyn Fn(ActionBatch) -> ActionFuture + Send + Sync>;

struct EvaluateRequest {
    source_id: String,
    detections: Vec<Value>,
    trigger_frame: TriggerFrame,
    now: NaiveDateTime,
    elapsed: Duration,
    reply: oneshot::Sender<Vec<RuleMatch>>,
}

enum RuleCommand {
    Evaluate(EvaluateRequest),
    Add {
        rule: DetectionRule,
        reply: oneshot::Sender<DetectionRule>,
    },
    Update {
        rule_id: String,
        rule: DetectionRule,
        reply: oneshot::Sender<DetectionRule>,
    },
    Remove {
        rule_id: String,
        reply: oneshot::Sender<bool>,
    },
    Get {
        rule_id: String,
        reply: oneshot::Sender<Option<DetectionRule>>,
    },
    List {
        reply: oneshot::Sender<Vec<DetectionRule>>,
    },
}

#[derive(Default)]
struct RuleMailboxState {
    commands: VecDeque<RuleCommand>,
    pending_evaluations: usize,
}

#[derive(Default)]
struct RuleMailbox {
    state: Mutex<RuleMailboxState>,
    notify: Notify,
}

impl RuleMailbox {
    fn push(&self, command: RuleCommand) {
        let mut state = self.state.lock().expect("rule mailbox lock poisoned");
        if let RuleCommand::Evaluate(request) = &command {
            if state.pending_evaluations == EVALUATE_QUEUE_CAPACITY {
                let mut sources = HashSet::new();
                for index in (0..state.commands.len()).rev() {
                    if let RuleCommand::Evaluate(pending) = &state.commands[index] {
                        if !sources.insert(pending.source_id.clone()) {
                            state.commands.remove(index);
                            state.pending_evaluations -= 1;
                        }
                    }
                }
                let replace = state.commands.iter().position(|pending| {
                    matches!(pending, RuleCommand::Evaluate(pending) if pending.source_id == request.source_id)
                });
                let remove = replace.or_else(|| {
                    (state.pending_evaluations == EVALUATE_QUEUE_CAPACITY).then(|| {
                        state
                            .commands
                            .iter()
                            .position(|pending| matches!(pending, RuleCommand::Evaluate(_)))
                            .expect("a full evaluate queue contains an evaluation")
                    })
                });
                if let Some(index) = remove {
                    state.commands.remove(index);
                    state.pending_evaluations -= 1;
                }
            }
            state.pending_evaluations += 1;
        }
        state.commands.push_back(command);
        drop(state);
        self.notify.notify_one();
    }

    async fn pop(&self) -> RuleCommand {
        loop {
            let notified = self.notify.notified();
            let command = {
                let mut state = self.state.lock().expect("rule mailbox lock poisoned");
                let command = state.commands.pop_front();
                if matches!(command, Some(RuleCommand::Evaluate(_))) {
                    state.pending_evaluations -= 1;
                }
                command
            };
            if let Some(command) = command {
                return command;
            }
            notified.await;
        }
    }

    #[cfg(test)]
    fn pending_evaluations(&self) -> usize {
        self.state
            .lock()
            .expect("rule mailbox lock poisoned")
            .pending_evaluations
    }
}

#[derive(Clone)]
pub(crate) struct RuleHandle {
    mailbox: Arc<RuleMailbox>,
}

impl RuleHandle {
    pub(crate) fn evaluate(
        &self,
        source_id: String,
        detections: &[Detection],
        trigger_frame: TriggerFrame,
        now: NaiveDateTime,
        elapsed: Duration,
    ) -> oneshot::Receiver<Vec<RuleMatch>> {
        self.evaluate_rule_input(
            source_id,
            detections.iter().map(rule_input).collect(),
            trigger_frame,
            now,
            elapsed,
        )
    }

    fn evaluate_rule_input(
        &self,
        source_id: String,
        detections: Vec<Value>,
        trigger_frame: TriggerFrame,
        now: NaiveDateTime,
        elapsed: Duration,
    ) -> oneshot::Receiver<Vec<RuleMatch>> {
        let (reply, result) = oneshot::channel();
        self.mailbox.push(RuleCommand::Evaluate(EvaluateRequest {
            source_id,
            detections,
            trigger_frame,
            now,
            elapsed,
            reply,
        }));
        result
    }

    pub(crate) fn add_rule(&self, rule: DetectionRule) -> oneshot::Receiver<DetectionRule> {
        let (reply, result) = oneshot::channel();
        self.mailbox.push(RuleCommand::Add { rule, reply });
        result
    }

    pub(crate) fn update_rule(
        &self,
        rule_id: String,
        rule: DetectionRule,
    ) -> oneshot::Receiver<DetectionRule> {
        let (reply, result) = oneshot::channel();
        self.mailbox.push(RuleCommand::Update {
            rule_id,
            rule,
            reply,
        });
        result
    }

    pub(crate) fn remove_rule(&self, rule_id: String) -> oneshot::Receiver<bool> {
        let (reply, result) = oneshot::channel();
        self.mailbox.push(RuleCommand::Remove { rule_id, reply });
        result
    }

    pub(crate) fn get_rule(&self, rule_id: String) -> oneshot::Receiver<Option<DetectionRule>> {
        let (reply, result) = oneshot::channel();
        self.mailbox.push(RuleCommand::Get { rule_id, reply });
        result
    }

    pub(crate) fn list_rules(&self) -> oneshot::Receiver<Vec<DetectionRule>> {
        let (reply, result) = oneshot::channel();
        self.mailbox.push(RuleCommand::List { reply });
        result
    }

    #[cfg(test)]
    fn pending_evaluations(&self) -> usize {
        self.mailbox.pending_evaluations()
    }
}

pub(crate) struct RuleTask {
    engine: RuleEngine,
    mailbox: Arc<RuleMailbox>,
    action: ActionExecutor,
}

impl RuleTask {
    pub(crate) fn spawn(rules: Vec<DetectionRule>) -> RuleHandle {
        Self::spawn_with(rules, |_| async {})
    }

    pub(crate) fn spawn_with<F, Fut>(rules: Vec<DetectionRule>, action: F) -> RuleHandle
    where
        F: Fn(ActionBatch) -> Fut + Send + Sync + 'static,
        Fut: Future<Output = ()> + Send + 'static,
    {
        let (handle, task) = Self::new(rules, action);
        tokio::spawn(task.run());
        handle
    }

    fn new<F, Fut>(rules: Vec<DetectionRule>, action: F) -> (RuleHandle, Self)
    where
        F: Fn(ActionBatch) -> Fut + Send + Sync + 'static,
        Fut: Future<Output = ()> + Send + 'static,
    {
        let mailbox = Arc::new(RuleMailbox::default());
        let mut engine = RuleEngine::default();
        engine.load_rules(rules);
        (
            RuleHandle {
                mailbox: Arc::clone(&mailbox),
            },
            Self {
                engine,
                mailbox,
                action: Arc::new(move |batch| Box::pin(action(batch))),
            },
        )
    }

    async fn run(mut self) {
        loop {
            match self.mailbox.pop().await {
                RuleCommand::Evaluate(request) => {
                    let matches = self.engine.evaluate(
                        &request.source_id,
                        &request.detections,
                        request.now,
                        request.elapsed,
                    );
                    for matched in &matches {
                        let batch = ActionBatch {
                            source_id: request.source_id.clone(),
                            rule: matched.rule.clone(),
                            actions: matched.rule.actions.clone(),
                            detections: matched.detections.clone(),
                            trigger_frame: request.trigger_frame.clone(),
                        };
                        tokio::spawn((self.action)(batch));
                    }
                    let _ = request.reply.send(matches);
                }
                RuleCommand::Add { rule, reply } => {
                    let _ = reply.send(self.engine.add_rule(rule));
                }
                RuleCommand::Update {
                    rule_id,
                    rule,
                    reply,
                } => {
                    let _ = reply.send(self.engine.update_rule(&rule_id, rule));
                }
                RuleCommand::Remove { rule_id, reply } => {
                    let _ = reply.send(self.engine.remove_rule(&rule_id));
                }
                RuleCommand::Get { rule_id, reply } => {
                    let _ = reply.send(self.engine.get_rule(&rule_id).cloned());
                }
                RuleCommand::List { reply } => {
                    let _ = reply.send(self.engine.list_rules());
                }
            }
        }
    }
}

fn rule_input(detection: &Detection) -> Value {
    let mut value = serde_json::to_value(detection)
        .expect("Detection is serializable")
        .as_object()
        .expect("Detection serializes as an object")
        .clone();
    value.insert(
        "class".to_string(),
        Value::String(detection.class_name.clone()),
    );
    Value::Object(value)
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub(crate) struct StreamSourceConfig {
    pub(crate) id: String,
    pub(crate) url: String,
    #[serde(default, deserialize_with = "deserialize_string_or_default")]
    pub(crate) name: String,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq, Serialize)]
pub(crate) struct StreamConfig {
    #[serde(default)]
    pub(crate) sources: Vec<StreamSourceConfig>,
    #[serde(default)]
    pub(crate) rules: Vec<DetectionRule>,
}

pub(crate) async fn execute_actions<S, SnapshotFuture, R, RunFuture>(
    rule: &DetectionRule,
    mut snapshot: S,
    run: R,
) -> Vec<Value>
where
    S: FnMut(Value) -> SnapshotFuture,
    SnapshotFuture: Future<Output = Result<Value, String>>,
    R: Fn(Value, Option<Value>) -> RunFuture,
    RunFuture: Future<Output = Result<Value, String>>,
{
    let mut results = Vec::new();
    let mut snapshot_result = None;
    let mut deferred = Vec::new();

    for action in &rule.actions {
        if action.get("type").and_then(Value::as_str) == Some("snapshot") {
            match snapshot(action.clone()).await {
                Ok(result) => {
                    snapshot_result = Some(result.clone());
                    results.push(result);
                }
                Err(error) => results.push(serde_json::json!({
                    "type": "snapshot",
                    "status": "error",
                    "error": error,
                })),
            }
        } else {
            deferred.push(action.clone());
        }
    }

    let futures = deferred.into_iter().map(|action| {
        let action_type = action
            .get("type")
            .and_then(Value::as_str)
            .unwrap_or("unknown")
            .to_string();
        let future = run(action, snapshot_result.clone());
        async move { (action_type, future.await) }
    });
    for (action_type, outcome) in join_all(futures).await {
        results.push(outcome.unwrap_or_else(|error| {
            serde_json::json!({
                "type": action_type,
                "status": "error",
                "error": error,
            })
        }));
    }
    results
}

/// Deliberate differences from the frozen golden fixture. Lives in
/// `rules/golden_overrides.rs`; test-only.
#[cfg(test)]
mod golden_overrides;

#[cfg(test)]
mod tests {
    use std::sync::atomic::{AtomicUsize, Ordering};

    use tokio::time::timeout;

    use super::super::run_bounded_test;
    use super::*;

    const TEST_TIMEOUT: Duration = Duration::from_secs(3);

    fn rule(value: Value) -> DetectionRule {
        serde_json::from_value(value).unwrap()
    }

    fn timestamp(value: &str) -> NaiveDateTime {
        NaiveDateTime::parse_from_str(value, "%Y-%m-%dT%H:%M:%S").unwrap()
    }

    fn frame(marker: u8) -> TriggerFrame {
        TriggerFrame {
            bytes: Bytes::from(vec![marker; 3]),
            width: 1,
            height: 1,
        }
    }

    fn detection(class_name: &str, confidence: f64) -> Detection {
        Detection {
            class_id: 0,
            class_name: class_name.to_string(),
            confidence,
            bbox: [0.1, 0.2, 0.8, 0.9],
        }
    }

    use super::golden_overrides::Overrides;

    /// Every expected value the golden tests compare against gets an id, so a
    /// deliberate change can name exactly one of them in the overrides file.
    /// Ids are collected per test and checked against the overrides, which is
    /// what makes a stale entry fail instead of silently overriding nothing.
    fn golden_ids(vectors: &Value) -> Vec<String> {
        let mut ids = Vec::new();
        for case in vectors["rule_cases"].as_array().unwrap() {
            let label = case["label"].as_str().unwrap();
            ids.push(format!("rule_cases/{label}/serialized_rule"));
            for index in 0..case["steps"].as_array().unwrap().len() {
                ids.push(format!("rule_cases/{label}/steps/{index}/expected"));
            }
        }
        for case in vectors["engine_cases"].as_array().unwrap() {
            let label = case["label"].as_str().unwrap();
            ids.push(format!("engine_cases/{label}/expected"));
        }
        for key in [
            "expected_get",
            "expected_list",
            "removed_beta",
            "removed_missing",
        ] {
            ids.push(format!("crud_case/{key}"));
        }
        ids.push("action_case/expected".to_string());
        ids
    }

    #[test]
    fn python_rule_vectors_match() {
        let vectors: Value = serde_json::from_str(include_str!(
            "../../../tests/fixtures/yolo_rule_vectors.json"
        ))
        .unwrap();
        let overrides = Overrides::load();
        overrides.assert_every_override_was_used(&golden_ids(&vectors));
        for case in vectors["rule_cases"].as_array().unwrap() {
            let label = case["label"].as_str().unwrap();
            let mut rust_rule = rule(case["rule"].clone());
            assert_eq!(
                Value::Object(rust_rule.to_dict()),
                overrides.expected(
                    &format!("rule_cases/{label}/serialized_rule"),
                    &case["serialized_rule"]
                ),
                "{label}"
            );
            for (index, step) in case["steps"].as_array().unwrap().iter().enumerate() {
                let detections = step["detections"].as_array().unwrap();
                let actual = rust_rule.matches(
                    step["source_id"].as_str().unwrap(),
                    detections,
                    timestamp(step["now"].as_str().unwrap()),
                    Duration::from_secs_f64(step["monotonic"].as_f64().unwrap()),
                );
                assert_eq!(
                    serde_json::to_value(actual).unwrap(),
                    overrides.expected(
                        &format!("rule_cases/{label}/steps/{index}/expected"),
                        &step["expected"]
                    ),
                    "{label}"
                );
            }
        }
    }

    #[test]
    fn python_rule_engine_vectors_match() {
        let vectors: Value = serde_json::from_str(include_str!(
            "../../../tests/fixtures/yolo_rule_vectors.json"
        ))
        .unwrap();
        for case in vectors["engine_cases"].as_array().unwrap() {
            let mut engine = RuleEngine::default();
            engine.load_rules(
                case["rules"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .cloned()
                    .map(rule)
                    .collect(),
            );
            let actual = engine.evaluate(
                case["source_id"].as_str().unwrap(),
                case["detections"].as_array().unwrap(),
                timestamp(case["now"].as_str().unwrap()),
                Duration::from_secs_f64(case["monotonic"].as_f64().unwrap()),
            );
            let label = case["label"].as_str().unwrap();
            assert_eq!(
                serde_json::to_value(actual).unwrap(),
                Overrides::load()
                    .expected(&format!("engine_cases/{label}/expected"), &case["expected"]),
                "{label}"
            );
        }
    }

    #[test]
    fn golden_engine_vectors_match_through_rule_task() {
        run_bounded_test(TEST_TIMEOUT, async {
            let vectors: Value = serde_json::from_str(include_str!(
                "../../../tests/fixtures/yolo_rule_vectors.json"
            ))
            .unwrap();
            for case in vectors["engine_cases"].as_array().unwrap() {
                let rules = case["rules"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .cloned()
                    .map(rule)
                    .collect();
                let handle = RuleTask::spawn(rules);
                let actual = handle
                    .evaluate_rule_input(
                        case["source_id"].as_str().unwrap().to_string(),
                        case["detections"].as_array().unwrap().clone(),
                        frame(1),
                        timestamp(case["now"].as_str().unwrap()),
                        Duration::from_secs_f64(case["monotonic"].as_f64().unwrap()),
                    )
                    .await
                    .unwrap();
                assert_eq!(serde_json::to_value(actual).unwrap(), case["expected"]);
            }
        });
    }

    #[test]
    fn production_detection_mapping_is_an_expected_python_rust_difference() {
        run_bounded_test(TEST_TIMEOUT, async {
            let class_rule = rule(serde_json::json!({
                "id": "person",
                "conditions": {"classes": ["person"]},
                "actions": [{"type": "snapshot"}]
            }));
            let detection = detection("person", 0.75);
            let raw = serde_json::to_value(&detection).unwrap();
            assert!(raw.get("class").is_none());

            let mut python_shape = RuleEngine::default();
            python_shape.add_rule(class_rule.clone());
            assert!(python_shape
                .evaluate(
                    "cam",
                    &[raw],
                    timestamp("2026-08-12T12:00:00"),
                    Duration::ZERO,
                )
                .is_empty());

            let handle = RuleTask::spawn(vec![class_rule]);
            let matched = handle
                .evaluate(
                    "cam".to_string(),
                    &[detection],
                    frame(7),
                    timestamp("2026-08-12T12:00:00"),
                    Duration::ZERO,
                )
                .await
                .unwrap();
            assert_eq!(matched.len(), 1);
            assert_eq!(
                matched[0].detections,
                vec![serde_json::json!({
                    "class_id": 0,
                    "class_name": "person",
                    "class": "person",
                    "confidence": 0.75,
                    "bbox": [0.1, 0.2, 0.8, 0.9]
                })]
            );
        });
    }

    #[test]
    fn one_engine_applies_positive_cooldown_across_sources_from_first_match() {
        run_bounded_test(TEST_TIMEOUT, async {
            let handle = RuleTask::spawn(vec![rule(serde_json::json!({
                "id": "shared", "cooldown_sec": 10
            }))]);
            let now = timestamp("2026-08-12T12:00:00");
            let person = [detection("person", 0.9)];
            let first = handle
                .evaluate("cam-a".to_string(), &person, frame(1), now, Duration::ZERO)
                .await
                .unwrap();
            let suppressed = handle
                .evaluate(
                    "cam-b".to_string(),
                    &person,
                    frame(2),
                    now,
                    Duration::from_secs(9),
                )
                .await
                .unwrap();
            let boundary = handle
                .evaluate(
                    "cam-b".to_string(),
                    &person,
                    frame(3),
                    now,
                    Duration::from_secs(10),
                )
                .await
                .unwrap();
            assert_eq!(first.len(), 1);
            assert!(suppressed.is_empty());
            assert_eq!(boundary.len(), 1);
        });
    }

    #[test]
    fn crud_and_evaluate_follow_one_command_order() {
        run_bounded_test(TEST_TIMEOUT, async {
            let (handle, task) = RuleTask::new(Vec::new(), |_| async {});
            let added = handle.add_rule(rule(serde_json::json!({
                "id": "animal", "conditions": {"classes": ["person"]}
            })));
            let first = handle.evaluate(
                "cam-a".to_string(),
                &[detection("person", 0.9)],
                frame(1),
                timestamp("2026-08-12T12:00:00"),
                Duration::ZERO,
            );
            let updated = handle.update_rule(
                "animal".to_string(),
                rule(serde_json::json!({
                    "id": "ignored", "conditions": {"classes": ["cat"]}
                })),
            );
            let second = handle.evaluate(
                "cam-b".to_string(),
                &[detection("person", 0.9)],
                frame(2),
                timestamp("2026-08-12T12:00:00"),
                Duration::from_secs(1),
            );
            let removed = handle.remove_rule("animal".to_string());
            let listed = handle.list_rules();
            tokio::spawn(task.run());

            assert_eq!(added.await.unwrap().id, "animal");
            assert_eq!(first.await.unwrap().len(), 1);
            assert_eq!(updated.await.unwrap().id, "animal");
            assert!(second.await.unwrap().is_empty());
            assert!(removed.await.unwrap());
            assert!(listed.await.unwrap().is_empty());
        });
    }

    #[test]
    fn full_evaluate_queue_keeps_only_each_sources_latest_request() {
        run_bounded_test(TEST_TIMEOUT, async {
            let (handle, task) =
                RuleTask::new(vec![rule(serde_json::json!({"id": "all"}))], |_| async {});
            let now = timestamp("2026-08-12T12:00:00");
            let mut old = Vec::new();
            let mut latest = Vec::new();
            for value in 0..EVALUATE_QUEUE_CAPACITY {
                old.push(handle.evaluate(
                    "cam-0".to_string(),
                    &[detection("person", value as f64)],
                    frame(value as u8),
                    now,
                    Duration::ZERO,
                ));
                assert!(handle.pending_evaluations() <= EVALUATE_QUEUE_CAPACITY);
            }
            latest.push(handle.evaluate(
                "cam-0".to_string(),
                &[detection("person", 100.0)],
                frame(100),
                now,
                Duration::from_secs(1),
            ));
            assert_eq!(handle.pending_evaluations(), 1);
            for source in 1..EVALUATE_QUEUE_CAPACITY {
                old.push(handle.evaluate(
                    format!("cam-{source}"),
                    &[detection("person", source as f64)],
                    frame(source as u8),
                    now,
                    Duration::ZERO,
                ));
            }
            assert_eq!(handle.pending_evaluations(), EVALUATE_QUEUE_CAPACITY);
            for source in 1..EVALUATE_QUEUE_CAPACITY {
                latest.push(handle.evaluate(
                    format!("cam-{source}"),
                    &[detection("person", 100.0 + source as f64)],
                    frame(100 + source as u8),
                    now,
                    Duration::from_secs(1),
                ));
                assert!(handle.pending_evaluations() <= EVALUATE_QUEUE_CAPACITY);
            }
            assert_eq!(handle.pending_evaluations(), EVALUATE_QUEUE_CAPACITY);
            tokio::spawn(task.run());

            for result in old {
                assert!(result.await.is_err());
            }
            for (source, result) in latest.into_iter().enumerate() {
                let matched = result.await.unwrap();
                assert_eq!(matched.len(), 1);
                assert_eq!(
                    matched[0].detections[0]["confidence"],
                    serde_json::json!(100.0 + source as f64)
                );
            }
        });
    }

    #[test]
    fn slow_action_future_does_not_block_evaluation_or_crud() {
        run_bounded_test(TEST_TIMEOUT, async {
            let release = Arc::new(Notify::new());
            let started = Arc::new(AtomicUsize::new(0));
            let (batch_tx, mut batch_rx) = tokio::sync::mpsc::unbounded_channel();
            let (handle, task) = RuleTask::new(
                vec![rule(serde_json::json!({
                    "id": "slow", "actions": [{"type": "snapshot"}]
                }))],
                {
                    let release = Arc::clone(&release);
                    let started = Arc::clone(&started);
                    move |batch| {
                        let release = Arc::clone(&release);
                        let batch_tx = batch_tx.clone();
                        let started = Arc::clone(&started);
                        async move {
                            started.fetch_add(1, Ordering::SeqCst);
                            batch_tx.send(batch).unwrap();
                            release.notified().await;
                        }
                    }
                },
            );
            tokio::spawn(task.run());
            let first = handle.evaluate(
                "cam".to_string(),
                &[detection("person", 0.9)],
                frame(9),
                timestamp("2026-08-12T12:00:00"),
                Duration::ZERO,
            );
            assert_eq!(first.await.unwrap().len(), 1);
            let batch = timeout(Duration::from_millis(500), batch_rx.recv())
                .await
                .expect("action did not start")
                .unwrap();
            assert_eq!(batch.source_id, "cam");
            assert_eq!(batch.rule.id, "slow");
            assert_eq!(batch.actions, vec![serde_json::json!({"type": "snapshot"})]);
            assert_eq!(batch.trigger_frame, frame(9));
            assert_eq!(started.load(Ordering::SeqCst), 1);

            let update = handle.update_rule(
                "slow".to_string(),
                rule(serde_json::json!({"id": "slow", "enabled": false})),
            );
            let second = handle.evaluate(
                "cam".to_string(),
                &[detection("person", 0.9)],
                frame(10),
                timestamp("2026-08-12T12:00:01"),
                Duration::from_secs(1),
            );
            timeout(Duration::from_millis(500), update)
                .await
                .expect("CRUD waited for the action future")
                .unwrap();
            assert!(timeout(Duration::from_millis(500), second)
                .await
                .expect("evaluation waited for the action future")
                .unwrap()
                .is_empty());
            release.notify_waiters();
        });
    }

    #[test]
    fn rule_engine_crud_matches_python_vector() {
        let vectors: Value = serde_json::from_str(include_str!(
            "../../../tests/fixtures/yolo_rule_vectors.json"
        ))
        .unwrap();
        let case = &vectors["crud_case"];
        let mut engine = RuleEngine::default();
        engine.add_rule(rule(case["add"][0].clone()));
        engine.add_rule(rule(case["add"][1].clone()));
        engine.update_rule("alpha", rule(case["update"].clone()));
        let overrides = Overrides::load();
        assert_eq!(
            serde_json::to_value(engine.get_rule("alpha")).unwrap(),
            overrides.expected("crud_case/expected_get", &case["expected_get"])
        );
        assert_eq!(
            serde_json::to_value(engine.list_rules()).unwrap(),
            overrides.expected("crud_case/expected_list", &case["expected_list"])
        );
        assert_eq!(
            engine.remove_rule("beta"),
            overrides.expected("crud_case/removed_beta", &case["removed_beta"])
        );
        assert_eq!(
            engine.remove_rule("missing"),
            overrides.expected("crud_case/removed_missing", &case["removed_missing"])
        );
        engine.load_rules(
            case["load"]
                .as_array()
                .unwrap()
                .iter()
                .cloned()
                .map(rule)
                .collect(),
        );
        assert_eq!(
            serde_json::to_value(engine.export_rules()).unwrap(),
            case["expected_export"]
        );
    }

    #[test]
    fn stream_config_matches_persisted_schema() {
        let value = serde_json::json!({
            "sources": [{"id": "cam", "url": "rtsp://camera", "name": "Door"}],
            "rules": [{"id": "person"}],
        });
        let config: StreamConfig = serde_json::from_value(value.clone()).unwrap();
        assert_eq!(
            serde_json::to_value(config).unwrap(),
            serde_json::json!({
                "sources": [{"id": "cam", "url": "rtsp://camera", "name": "Door"}],
                "rules": [{
                    "id": "person", "name": "", "enabled": true, "conditions": {},
                    "cooldown_sec": 0, "actions": []
                }],
            })
        );
    }

    #[test]
    fn persisted_rules_deserialize_nulls_and_integral_cooldowns() {
        for cooldown in [serde_json::json!(5), serde_json::json!(5.0)] {
            let config: StreamConfig = serde_json::from_value(serde_json::json!({
                "sources": [{"id": "cam", "url": "rtsp://camera", "name": null}],
                "rules": [{
                    "id": "person", "name": null, "conditions": null,
                    "cooldown_sec": cooldown, "unknown": true
                }]
            }))
            .unwrap();
            assert_eq!(config.sources[0].name, "");
            assert_eq!(config.rules[0].name, "");
            assert!(config.rules[0].conditions.is_empty());
            assert_eq!(config.rules[0].cooldown_sec, 5);
        }
    }

    #[test]
    fn persisted_rules_reject_invalid_cooldowns() {
        for cooldown in [
            serde_json::json!(5.5),
            serde_json::json!(u64::MAX),
            serde_json::json!(9_223_372_036_854_775_808.0_f64),
        ] {
            assert!(serde_json::from_value::<DetectionRule>(serde_json::json!({
                "id": "person", "cooldown_sec": cooldown
            }))
            .is_err());
        }

        for cooldown in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            let result: Result<i64, serde::de::value::Error> =
                deserialize_cooldown(serde::de::value::F64Deserializer::new(cooldown));
            assert!(result.is_err());
        }
    }

    #[tokio::test]
    async fn python_action_vector_matches() {
        let vectors: Value = serde_json::from_str(include_str!(
            "../../../tests/fixtures/yolo_rule_vectors.json"
        ))
        .unwrap();
        let case = &vectors["action_case"];
        let rust_rule = rule(case["rule"].clone());
        let actual = execute_actions(
            &rust_rule,
            |action| async move {
                Ok(serde_json::json!({
                    "type": "snapshot",
                    "status": "ok",
                    "name": action["name"],
                }))
            },
            |action, snapshot| async move {
                if action["fail"].as_bool().unwrap_or(false) {
                    return Err("planned failure".to_string());
                }
                Ok(serde_json::json!({
                    "type": action["type"],
                    "status": "ok",
                    "snapshot_name": snapshot.as_ref().map_or(Value::Null, |value| value["name"].clone()),
                }))
            },
        )
        .await;
        assert_eq!(
            serde_json::to_value(actual).unwrap(),
            Overrides::load().expected("action_case/expected", &case["expected"])
        );
    }
}
