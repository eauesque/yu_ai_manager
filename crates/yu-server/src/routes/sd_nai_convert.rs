use axum::{
    extract::rejection::JsonRejection,
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};

use crate::sd_nai::{convert_nai_to_sd, convert_sd_to_nai};

const MAX_PROMPT_CHARS: usize = 8192;

pub async fn sd_to_nai(body: Result<Json<Value>, JsonRejection>) -> Response {
    let data = json_or_empty(body);
    let (prompt, negative, options) = match validate_prompt_pair(&data) {
        Ok(value) => value,
        Err(response) => return response,
    };
    let strip_lora = option_value(&options, "strip_lora", true);
    let strip_embedding = option_value(&options, "strip_embedding", true);
    let emphasis = option_value(&options, "convert_emphasis", true);

    Json(json!({
        "prompt": convert_sd_to_nai(prompt, py_truthy(&strip_lora), py_truthy(&strip_embedding), py_truthy(&emphasis)),
        "negative": convert_sd_to_nai(negative, py_truthy(&strip_lora), py_truthy(&strip_embedding), py_truthy(&emphasis)),
        "direction": "sd_to_nai",
        "options": {
            "strip_lora": strip_lora,
            "strip_embedding": strip_embedding,
            "convert_emphasis": emphasis,
        },
    }))
    .into_response()
}

pub async fn nai_to_sd(body: Result<Json<Value>, JsonRejection>) -> Response {
    let data = json_or_empty(body);
    let (prompt, negative, options) = match validate_prompt_pair(&data) {
        Ok(value) => value,
        Err(response) => return response,
    };
    let emphasis = option_value(&options, "convert_emphasis", true);

    Json(json!({
        "prompt": convert_nai_to_sd(prompt, py_truthy(&emphasis)),
        "negative": convert_nai_to_sd(negative, py_truthy(&emphasis)),
        "direction": "nai_to_sd",
        "options": {
            "convert_emphasis": emphasis,
        },
    }))
    .into_response()
}

pub async fn batch(body: Result<Json<Value>, JsonRejection>) -> Response {
    let data = json_or_empty(body);
    let items = data
        .get("items")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let direction = data
        .get("direction")
        .and_then(Value::as_str)
        .unwrap_or("sd_to_nai");
    let options = data
        .get("options")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default();

    if items.is_empty() {
        return json_status(
            json!({"error": "No items provided"}),
            StatusCode::BAD_REQUEST,
        );
    }
    if items.len() > 100 {
        return json_status(
            json!({"error": "Max 100 items per batch"}),
            StatusCode::BAD_REQUEST,
        );
    }
    if direction != "sd_to_nai" && direction != "nai_to_sd" {
        return json_status(
            json!({"error": "Invalid direction: must be 'sd_to_nai' or 'nai_to_sd'"}),
            StatusCode::BAD_REQUEST,
        );
    }

    let mut results = Vec::new();
    for item in items {
        let prompt = if let Some(object) = item.as_object() {
            object
                .get("prompt")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string()
        } else {
            py_str(&item)
        };
        if prompt.chars().count() > MAX_PROMPT_CHARS {
            return json_status(
                json!({"error": format!("Item prompt too long (max {MAX_PROMPT_CHARS} chars)")}),
                StatusCode::BAD_REQUEST,
            );
        }
        let converted = if direction == "sd_to_nai" {
            convert_sd_to_nai(
                &prompt,
                py_truthy(&option_value(&options, "strip_lora", true)),
                py_truthy(&option_value(&options, "strip_embedding", true)),
                py_truthy(&option_value(&options, "convert_emphasis", true)),
            )
        } else {
            convert_nai_to_sd(
                &prompt,
                py_truthy(&option_value(&options, "convert_emphasis", true)),
            )
        };
        results.push(json!({"original": prompt, "converted": converted}));
    }

    Json(json!({"results": results, "direction": direction, "count": results.len()}))
        .into_response()
}

fn validate_prompt_pair(
    data: &Value,
) -> Result<(&str, &str, serde_json::Map<String, Value>), Response> {
    let Some(object) = data.as_object() else {
        return Ok(("", "", serde_json::Map::new()));
    };
    let prompt = object.get("prompt").filter(|value| !value.is_null());
    let negative = object.get("negative").filter(|value| !value.is_null());
    let prompt = match prompt {
        Some(Value::String(value)) => value.as_str(),
        Some(_) => {
            return Err(json_status(
                json!({"error": "prompt must be a string", "code": "invalid_prompt"}),
                StatusCode::BAD_REQUEST,
            ))
        }
        None => "",
    };
    let negative = match negative {
        Some(Value::String(value)) => value.as_str(),
        Some(_) => {
            return Err(json_status(
                json!({"error": "negative must be a string", "code": "invalid_negative"}),
                StatusCode::BAD_REQUEST,
            ))
        }
        None => "",
    };
    if prompt.chars().count() > MAX_PROMPT_CHARS || negative.chars().count() > MAX_PROMPT_CHARS {
        return Err(json_status(
            json!({"error": format!("Prompt too long (max {MAX_PROMPT_CHARS} chars)"), "code": "prompt_too_long"}),
            StatusCode::BAD_REQUEST,
        ));
    }
    let options = object
        .get("options")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default();
    Ok((prompt, negative, options))
}

fn json_or_empty(body: Result<Json<Value>, JsonRejection>) -> Value {
    match body {
        Ok(Json(value)) if value.is_object() => value,
        _ => json!({}),
    }
}

fn option_value(options: &serde_json::Map<String, Value>, key: &str, default: bool) -> Value {
    options.get(key).cloned().unwrap_or(Value::Bool(default))
}

fn py_truthy(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::Bool(value) => *value,
        Value::Number(value) => value.as_f64() != Some(0.0),
        Value::String(value) => !value.is_empty(),
        Value::Array(value) => !value.is_empty(),
        Value::Object(value) => !value.is_empty(),
    }
}

fn py_str(value: &Value) -> String {
    match value {
        Value::Null => "None".to_string(),
        Value::Bool(true) => "True".to_string(),
        Value::Bool(false) => "False".to_string(),
        Value::Number(value) => value.to_string(),
        Value::String(value) => value.clone(),
        Value::Array(_) | Value::Object(_) => value.to_string(),
    }
}

fn json_status(payload: Value, status: StatusCode) -> Response {
    (status, Json(payload)).into_response()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn py_truthiness_matches_handler_needs() {
        assert!(!py_truthy(&Value::Null));
        assert!(!py_truthy(&json!(0)));
        assert!(!py_truthy(&json!("")));
        assert!(py_truthy(&json!("false")));
    }
}
