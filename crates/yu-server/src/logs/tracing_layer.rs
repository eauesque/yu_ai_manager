use std::sync::Arc;

use tracing::Subscriber;
use tracing_subscriber::layer::Context;
use tracing_subscriber::Layer;

use super::ring::{LogRingBuffer, PartialEntry};

pub struct TracingLayer {
    ring: Arc<LogRingBuffer>,
    min_level: tracing::Level,
}

impl TracingLayer {
    pub fn new(ring: Arc<LogRingBuffer>, min_level: tracing::Level) -> Self {
        Self { ring, min_level }
    }
}

impl<S: Subscriber> Layer<S> for TracingLayer {
    fn on_event(&self, event: &tracing::Event<'_>, _ctx: Context<'_, S>) {
        let meta = event.metadata();
        if meta.level() > &self.min_level {
            return;
        }
        let level = meta.level().to_string().to_ascii_uppercase();
        let target = meta.target().to_string();
        let mut visitor = FieldVisitor::default();
        event.record(&mut visitor);
        self.ring.push(PartialEntry {
            level,
            target,
            message: visitor.message,
            fields: if visitor.fields.is_empty() {
                None
            } else {
                Some(visitor.fields)
            },
        });
    }
}

#[derive(Default)]
struct FieldVisitor {
    message: String,
    fields: serde_json::Map<String, serde_json::Value>,
}

impl tracing::field::Visit for FieldVisitor {
    fn record_str(&mut self, field: &tracing::field::Field, value: &str) {
        if field.name() == "message" {
            self.message = value.to_string();
        } else {
            self.fields
                .insert(field.name().to_string(), value.to_owned().into());
        }
    }

    fn record_debug(&mut self, field: &tracing::field::Field, value: &dyn std::fmt::Debug) {
        // tracing formats &str messages as `"..."` — strip the outer quotes.
        let raw = format!("{value:?}");
        let s = if raw.starts_with('"') && raw.ends_with('"') && raw.len() >= 2 {
            raw[1..raw.len() - 1].replace("\\\"", "\"")
        } else {
            raw
        };
        if field.name() == "message" {
            self.message = s;
        } else {
            self.fields.insert(field.name().to_string(), s.into());
        }
    }

    fn record_i64(&mut self, field: &tracing::field::Field, value: i64) {
        self.fields.insert(field.name().to_string(), value.into());
    }

    fn record_u64(&mut self, field: &tracing::field::Field, value: u64) {
        self.fields.insert(
            field.name().to_string(),
            serde_json::Value::Number(value.into()),
        );
    }

    fn record_bool(&mut self, field: &tracing::field::Field, value: bool) {
        self.fields.insert(field.name().to_string(), value.into());
    }

    fn record_f64(&mut self, field: &tracing::field::Field, value: f64) {
        if let Some(n) = serde_json::Number::from_f64(value) {
            self.fields
                .insert(field.name().to_string(), serde_json::Value::Number(n));
        }
    }
}
