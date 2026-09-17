use axum::http::HeaderMap;
use serde_json::{json, Map, Value};

use crate::state::SharedState;

/// Finds every complete, brace-matched `{...}` substring in `text` — including ones nested
/// inside another — in a single O(n) left-to-right pass using a stack of open-brace positions
/// (string literals are tracked so a `{`/`}` inside a quoted value doesn't miscount, and doesn't
/// push/pop). Each `}` pops the most recently opened, still-unclosed `{` and records that span;
/// a `{` that is never closed (e.g. a stray brace in prose) is simply left on the stack and never
/// produces a span, without needing to restart or rescan any text — that earlier approach
/// (rescanning from the next character whenever a candidate turned out unterminated) was
/// correct but quadratic on adversarial input such as a long run of never-closing `{` characters
/// (Codex stop-time review, 2026-08-16, twice: first that giving up on the first non-tool-call
/// candidate missed a real one later in the text, then that the rescan fix for that was O(n²)).
/// Callers get candidates innermost-first; `parse_tool_call_with_known_names` tries each in turn
/// and simply skips ones that don't have a `"name"` key, so a spurious inner match losing to a
/// real outer (or later) one costs nothing beyond one failed lookup. Also naturally tolerates
/// field order (real Hailo-10H hardware/Qwen3-1.7B-Instruct emits `arguments` before `name`) and
/// trailing noise like a `<|im_end|>` token glued onto the closing brace, since only the exact
/// matched span is kept.
fn extract_json_objects(text: &str) -> Vec<&str> {
    let mut objects = Vec::new();
    let mut open_positions: Vec<usize> = Vec::new();
    let mut in_string = false;
    let mut escaped = false;
    for (index, &byte) in text.as_bytes().iter().enumerate() {
        if in_string {
            if escaped {
                escaped = false;
            } else if byte == b'\\' {
                escaped = true;
            } else if byte == b'"' {
                in_string = false;
            }
            continue;
        }
        match byte {
            b'"' => in_string = true,
            b'{' => open_positions.push(index),
            b'}' => {
                if let Some(start) = open_positions.pop() {
                    objects.push(&text[start..=index]);
                }
            }
            _ => {}
        }
    }
    objects
}

fn example_argument_value(info: &Value) -> Value {
    match info.get("type").and_then(Value::as_str) {
        Some("number" | "integer") => json!(1),
        Some("boolean") => json!(true),
        _ => json!("example"),
    }
}

/// One concrete worked example, built from the first tool the caller offers. Small quantized
/// models follow a demonstrated input/output pair far more reliably than a prose format
/// description alone (observed on real Hailo-10H hardware: models that ignored the format
/// description emitted the bare tool name, e.g. `list_scan_roots`, instead of the required JSON).
fn build_tool_call_example(tools: &[Value]) -> Option<String> {
    let function = tools
        .first()
        .map(|tool| tool.get("function").unwrap_or(tool))?;
    let name = function.get("name").and_then(Value::as_str)?;
    let properties = function
        .get("parameters")
        .and_then(Value::as_object)
        .and_then(|parameters| parameters.get("properties"))
        .and_then(Value::as_object);
    let arguments: Map<String, Value> = properties
        .into_iter()
        .flatten()
        .take(2)
        .map(|(name, info)| (name.clone(), example_argument_value(info)))
        .collect();
    let example = json!({"name": name, "arguments": arguments});
    Some(format!(
        "Example — to call \"{name}\", respond with exactly:\n{example}"
    ))
}

pub fn build_tool_system_prompt(tools: &[Value], user_system_prompt: &str) -> String {
    let tool_lines = tools
        .iter()
        .map(|tool| {
            let function = tool.get("function").unwrap_or(tool);
            let parameters = function.get("parameters").and_then(Value::as_object);
            let properties = parameters
                .and_then(|parameters| parameters.get("properties"))
                .and_then(Value::as_object);
            let required = parameters
                .and_then(|parameters| parameters.get("required"))
                .and_then(Value::as_array)
                .cloned()
                .unwrap_or_default();
            let name = function.get("name").and_then(Value::as_str).unwrap_or("");
            let description = function
                .get("description")
                .and_then(Value::as_str)
                .unwrap_or("");
            match properties.filter(|properties| !properties.is_empty()) {
                Some(properties) => {
                    let arguments = properties
                        .iter()
                        .map(|(name, info)| {
                            format!(
                                "    {name}: {} — {}{}",
                                info.get("type").and_then(Value::as_str).unwrap_or("string"),
                                info.get("description")
                                    .and_then(Value::as_str)
                                    .unwrap_or(""),
                                if required.iter().any(|value| value.as_str() == Some(name)) {
                                    " (required)"
                                } else {
                                    ""
                                },
                            )
                        })
                        .collect::<Vec<_>>()
                        .join("\n");
                    format!("- {name}: {description}\n  Arguments:\n{arguments}")
                }
                None => format!("- {name}: {description}. No arguments."),
            }
        })
        .collect::<Vec<_>>()
        .join("\n");
    let base = user_system_prompt.trim();
    let example = build_tool_call_example(tools)
        .map(|example| format!("\n\n{example}"))
        .unwrap_or_default();
    format!(
        "{}You have tools. To call a tool, respond with ONLY a JSON object:\n{{\"name\": \"TOOL_NAME\", \"arguments\": {{}}}}{example}\n\nIf you do NOT need a tool, respond in natural language.\n\nTools:\n{tool_lines}",
        if base.is_empty() { String::new() } else { format!("{base}\n\n") },
    )
}

/// Tool names as declared to the model, in `build_tool_system_prompt`'s order.
fn tool_names(tools: &[Value]) -> Vec<&str> {
    tools
        .iter()
        .filter_map(|tool| tool.get("function").unwrap_or(tool).get("name")?.as_str())
        .collect()
}

fn tool_call(value: Value) -> Option<(String, Map<String, Value>)> {
    let object = value.as_object()?;
    let name = object.get("name")?.as_str()?.to_string();
    if name.is_empty() {
        return None;
    }
    let arguments = match object.get("arguments") {
        None => Map::new(),
        Some(Value::String(arguments)) => serde_json::from_str(arguments).ok()?,
        Some(Value::Object(arguments)) => arguments.clone(),
        _ => return None,
    };
    Some((name, arguments))
}

/// `text` stripped of any trailing chat/instruct end-of-turn marker and surrounding
/// punctuation a small model tends to wrap a bare tool name in (`` `name` ``, `"name"`, `name.`).
fn strip_bare_name_noise(text: &str) -> &str {
    text.trim_end_matches("<|eot_id|>")
        .trim_end_matches("<|im_end|>")
        .trim_matches(|c: char| !c.is_alphanumeric() && c != '_')
}

pub fn parse_tool_call(text: &str) -> Option<(String, Map<String, Value>)> {
    parse_tool_call_with_known_names(text, &[])
}

/// Same as [`parse_tool_call`], plus a lenient last-resort fallback: if `text` is (once
/// stripped of surrounding noise) exactly one of `known_tool_names`, treat it as a zero-argument
/// call to that tool. Observed on real Hailo-10H hardware: small quantized models sometimes
/// name the tool they want to call without wrapping it in the required JSON envelope. Argument
/// validation still happens downstream in `execute_tool`, so a tool that actually needs
/// arguments simply reports them missing rather than silently misbehaving.
pub fn parse_tool_call_with_known_names(
    text: &str,
    known_tool_names: &[&str],
) -> Option<(String, Map<String, Value>)> {
    let text = text.trim();
    serde_json::from_str(text)
        .ok()
        .and_then(tool_call)
        .or_else(|| {
            // extract_json_objects() returns candidates innermost-first; a genuine tool call is
            // essentially never deeply nested, so trying outermost-first matches the common case
            // immediately. Total serde_json::from_str work is bounded by a parsing *budget*
            // (total bytes handed to it across all attempts), not a candidate *count* cap — a
            // count cap can silently discard a real match when a model emits many small SIBLING
            // (non-nested) JSON-looking fragments before or after the real one, since trying all
            // of those in full costs only O(n) total regardless of how many there are (Codex
            // stop-time review, 2026-08-16: a fixed count cap "can discard a valid tool call").
            // Only genuinely overlapping candidates from deep nesting — whose combined length is
            // the O(n²) case worth bounding — exhaust the budget quickly; disjoint sibling spans
            // can never sum past `text.len()`, so they're never truncated by it.
            let mut budget = text.len().saturating_mul(4).max(4096);
            let mut candidates = extract_json_objects(text);
            candidates.reverse();
            candidates.into_iter().find_map(|object| {
                if budget == 0 {
                    return None;
                }
                budget = budget.saturating_sub(object.len());
                serde_json::from_str(object).ok().and_then(tool_call)
            })
        })
        .or_else(|| {
            let bare = strip_bare_name_noise(text);
            known_tool_names
                .iter()
                .find(|&&name| name == bare)
                .map(|&name| (name.to_string(), Map::new()))
        })
}

/// True when `content` looks like a failed attempt at a tool call — specifically a brace-delimited
/// fragment containing the quoted `"name"` key our own format instructions ask for — rather than
/// a genuine natural-language final answer. Used to decide whether a one-shot format-correction
/// retry is worth the extra round, versus a model that legitimately chose not to call a tool.
///
/// Deliberately narrow, after two false-positive reports (Codex stop-time review, 2026-08-16):
/// - Does NOT flag content merely for mentioning a known tool name in prose (e.g. "I don't have
///   a `search` tool for that") — an exact bare tool name is instead accepted directly by
///   `parse_tool_call_with_known_names`'s lenient fallback, so it never needs this heuristic.
/// - Does NOT flag `{` and the unquoted word "name" occurring independently anywhere in the
///   text (e.g. prose using `{name}` as a template placeholder) — the quoted `"name"` key must
///   appear *inside* the same `{...}` fragment, matching the JSON shape we actually asked for.
///
/// Misclassifying either burns a retry round and hands the model a confusing "that was not a
/// valid tool call" correction for an answer that was never a call at all.
fn looks_like_attempted_tool_call(content: &str) -> bool {
    let Some(start) = content.find('{') else {
        return false;
    };
    let Some(end) = content[start..].find('}') else {
        return false;
    };
    content[start..start + end].contains("\"name\"")
}

fn truncate_result(result: &str) -> String {
    if result.chars().count() <= 1500 {
        result.to_string()
    } else {
        format!(
            "{}...(truncated)",
            result.chars().take(1500).collect::<String>()
        )
    }
}

pub async fn run_agent_prompt_based(
    state: &SharedState,
    headers: &HeaderMap,
    endpoint: &crate::routes::llm_client::Endpoint,
    message: &str,
    tools: &[Value],
    system_prompt: &str,
    max_tokens: u32,
    temperature: f64,
    max_rounds: usize,
) -> Value {
    // Native yu-infer calls clear_context() before every generation (yu-hailo-infer v0.2.0,
    // verified on hardware). `/api/llm/clear-context` is not ported for a different
    // reason than this comment used to give: the sidecar group_id design is no longer
    // outstanding -- yu-hailo-infer v0.2.0 passes `params.group_id` to
    // `VDevice::create_shared` (shim.cpp:50-71). Measured 2026-08-22: that route only
    // touches Python-process-local model state (llm_control.async_clear_llm_context),
    // and the sidecar clears context itself before every generation, so there is no
    // native target to port it to. See HAILO_RUST_MIGRATION_REMAINING_WORK.md.
    let mut messages = vec![
        json!({"role":"system", "content": build_tool_system_prompt(tools, system_prompt)}),
        json!({"role":"user", "content": message}),
    ];
    let known_tool_names = tool_names(tools);
    // Passed to chat() as native tool definitions on every round (HailoRT's own
    // chat template renders them; yu-infer clear_context()s before every
    // generation, so a fresh context — the SDK's only restriction on tools — is
    // always guaranteed here). Real Hailo-10H hardware (Qwen3-1.7B-Instruct)
    // responds to these with `<tool_call>{"name":...,"arguments":...}</tool_call>`,
    // a format `TOOL_CALL_RE` above already parses, so no new parsing was needed.
    //
    // `run_agent_prompt_based` is reachable via an explicit `mode=prompt_based`
    // for ANY category, not just the synthetic Hailo self-loopback endpoint —
    // a caller can point `llm_endpoints.<category>` at a real external
    // OpenAI-compatible server and still ask for prompt-based tool simulation.
    // Unwrapping `tools` down to HailoRT's bare `{"name":...}` shape is only
    // correct for the Hailo native path; a real OpenAI endpoint requires the
    // `{"type":"function","function":{...}}` envelope `tool_definitions()`
    // already produces, so only unwrap when the endpoint is EXACTLY this
    // server's own hailo-genai self-loopback route (Codex stop-time review,
    // 2026-08-16, twice: first an unconditional unwrap broke external
    // prompt_based endpoints, then a `base_url.contains("hailo-genai")`
    // substring check was found to still misfire on an external endpoint
    // whose URL merely contains that text — reuse the same exact-match check
    // `llm_client::chat()` already uses for the analogous auth-forwarding gate).
    let tools_value = (!tools.is_empty()).then(|| {
        if crate::routes::llm_client::is_own_loopback(state.effective_port, &endpoint.base_url) {
            json!(crate::routes::llm_client::unwrap_openai_tools(tools))
        } else {
            json!(tools)
        }
    });
    let mut steps = Vec::new();
    let mut corrected = false;
    let mut round = 0;
    // A one-shot format-correction retry (see `looks_like_attempted_tool_call`) is deliberately
    // NOT counted against `round`/`max_rounds`: it is not a tool-calling round at all, and if it
    // consumed the caller's round budget, `max_rounds=1` would let the correction request eat
    // the single allowed round and the promised retry would silently never happen (Codex
    // stop-time review, 2026-08-16).
    while round < max_rounds {
        let response = match crate::routes::llm_client::chat(
            state,
            endpoint,
            &messages,
            max_tokens,
            temperature,
            tools_value.as_ref(),
            Some(headers),
        )
        .await
        {
            Ok(response) => response,
            Err(error) => {
                tracing::warn!(%error, "prompt-based LLM agent failed");
                return json!({"content":"[LLM request failed]", "model":endpoint.model, "steps":steps, "rounds":round});
            }
        };
        let content = response.content.trim();
        if content.is_empty() {
            return json!({"content":"[Empty response from LLM]", "model":response.model, "steps":steps, "rounds":round + 1});
        }
        let Some((name, arguments)) = parse_tool_call_with_known_names(content, &known_tool_names)
        else {
            if !corrected && looks_like_attempted_tool_call(content) {
                corrected = true;
                messages.push(json!({"role":"assistant", "content":content}));
                messages.push(json!({
                    "role":"user",
                    "content":"That was not a valid tool call. Respond with ONLY the JSON object: {\"name\": \"TOOL_NAME\", \"arguments\": {}}",
                }));
                continue;
            }
            return json!({"content":content, "model":response.model, "steps":steps, "rounds":round + 1});
        };
        let result =
            crate::routes::llm_client::execute_tool(state, headers, &name, &arguments).await;
        let result = match result {
            Value::String(result) => result,
            result => result.to_string(),
        };
        let result = truncate_result(&result);
        steps.push(json!({"tool":name, "arguments":arguments, "result_preview":result.chars().take(200).collect::<String>()}));
        messages.push(json!({"role":"assistant", "content":content}));
        messages.push(json!({"role":"user", "content":format!("Tool result: {result}\n\nAnswer the original question using this data.")}));
        round += 1;
    }
    tracing::warn!(max_rounds, "prompt-based LLM agent reached maximum rounds");
    json!({"content":"[Agent reached maximum tool call rounds]", "model":endpoint.model, "steps":steps, "rounds":max_rounds})
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn extract_json_objects_respects_nesting_and_string_literals() {
        // Nested objects are recorded innermost-first (closing order): the inner
        // {"b": 1} closes before the outer {"a": {"b": 1}} does.
        assert_eq!(
            extract_json_objects(r#"prefix {"a": {"b": 1}} suffix"#),
            vec![r#"{"b": 1}"#, r#"{"a": {"b": 1}}"#]
        );
        // A brace inside a quoted string value must not be counted as nesting.
        assert_eq!(
            extract_json_objects(r#"{"a": "value with } and { inside"}"#),
            vec![r#"{"a": "value with } and { inside"}"#]
        );
        // An escaped quote inside a string must not end the string early.
        assert_eq!(
            extract_json_objects(r#"{"a": "she said \"hi\""}"#),
            vec![r#"{"a": "she said \"hi\""}"#]
        );
        assert!(extract_json_objects("no braces here").is_empty());
        assert!(extract_json_objects("{ unterminated").is_empty());
        // Multiple top-level objects are all returned, in order.
        assert_eq!(
            extract_json_objects(r#"{"a": 1} then {"b": 2}"#),
            vec![r#"{"a": 1}"#, r#"{"b": 2}"#]
        );
        // Regression (Codex stop-time review, 2026-08-16): a stray, never-closing `{` earlier in
        // the text must not stop the scan from finding a genuine, independent object after it.
        assert_eq!(
            extract_json_objects(r#"stray { brace then {"a": 1}"#),
            vec![r#"{"a": 1}"#]
        );
    }

    #[test]
    fn parses_tool_calls() {
        for text in [
            r#"{"name":"search","arguments":{"q":"x"}}"#,
            r#"<tool_call>{"name":"search","arguments":{"q":"x"}}</tool_call>"#,
            r#"Use this: {"name":"search","arguments":{"q":"x"}} thanks"#,
            r#"{"name":"search","arguments":"{\"q\":\"x\"}"}"#,
            // Real Hailo-10H hardware (Qwen3-1.7B-Instruct): "arguments" emitted
            // before "name" (reversed field order) with an end-of-turn token
            // glued directly onto the closing brace, no <tool_call> wrapper.
            r#"{"arguments": {"limit": 1, "q": "search"}, "name": "search"}<|im_end|>"#,
            // Regression (Codex stop-time review, 2026-08-16): an earlier
            // JSON-looking fragment that is NOT the tool call (no "name" key)
            // must not make extraction give up before reaching the real one.
            r#"Example: {"note": "not a call"} then {"name":"search","arguments":{"q":"x"}}"#,
        ] {
            assert_eq!(parse_tool_call(text).unwrap().0, "search");
        }
        assert!(parse_tool_call("plain prose").is_none());
    }

    #[test]
    fn builds_prompt_and_truncates_results_by_chars() {
        let prompt = build_tool_system_prompt(
            &[
                json!({"function":{"name":"search","description":"Find","parameters":{"properties":{"q":{"type":"string","description":"Query"}},"required":["q"]}}}),
                json!({"function":{"name":"status","description":"Check","parameters":{"properties":{}}}}),
            ],
            " system ",
        );
        assert!(prompt.contains("q: string — Query (required)"));
        assert!(prompt.contains("- status: Check. No arguments."));
        let result = truncate_result(&"あ".repeat(1501));
        assert!(result.ends_with("...(truncated)"));
        assert_eq!(result.chars().take(200).count(), 200);
    }

    #[test]
    fn prompt_includes_a_worked_example_for_the_first_tool() {
        let prompt = build_tool_system_prompt(
            &[
                json!({"function":{"name":"search","description":"Find","parameters":{"properties":{"q":{"type":"string","description":"Query"}},"required":["q"]}}}),
                json!({"function":{"name":"status","description":"Check"}}),
            ],
            "",
        );
        assert!(prompt.contains(r#"Example — to call "search""#));
        assert!(prompt.contains(r#""name":"search""#));
        assert!(prompt.contains(r#""q":"example""#));
        assert!(!build_tool_system_prompt(&[], "").is_empty());
    }

    #[test]
    fn lenient_parse_accepts_a_bare_known_tool_name_but_not_an_unknown_one() {
        let known = ["list_scan_roots", "search"];
        for text in [
            "list_scan_roots",
            "list_scan_roots<|eot_id|>",
            "`list_scan_roots`",
            "\"list_scan_roots\".",
            " list_scan_roots ",
        ] {
            let (name, arguments) = parse_tool_call_with_known_names(text, &known).unwrap();
            assert_eq!(name, "list_scan_roots");
            assert!(arguments.is_empty());
        }
        // Strict parsing (no known-name list) must not gain this leniency.
        assert!(parse_tool_call("list_scan_roots").is_none());
        // A word that isn't a declared tool must never match, known list or not.
        assert!(parse_tool_call_with_known_names("delete_everything", &known).is_none());
        assert!(
            parse_tool_call_with_known_names("plain prose about search tools", &known).is_none()
        );
    }

    #[test]
    fn attempted_tool_call_heuristic_distinguishes_failed_attempts_from_final_answers() {
        assert!(looks_like_attempted_tool_call(r#"{"name": "search"}"#));
        assert!(!looks_like_attempted_tool_call(
            "The capital of France is Paris."
        ));
        // Regression: a genuine final answer that merely mentions a tool by name (Codex
        // stop-time review, 2026-08-16) must not be misclassified as a failed tool-call attempt
        // — that would burn a retry round and confuse the model with a bogus correction.
        assert!(!looks_like_attempted_tool_call(
            "I don't have a `search` tool available for that request."
        ));
        assert!(!looks_like_attempted_tool_call(
            "You could use search or list_scan_roots for this, but I don't need either here."
        ));
        // An exact bare tool name is handled directly by the lenient parser fallback, not by
        // this heuristic, so it correctly reports false here.
        assert!(!looks_like_attempted_tool_call("search"));
        // Regression: prose using `{name}` as a template placeholder (unquoted, and not the
        // JSON key our format instructions ask for) is not a failed tool-call attempt either
        // (Codex stop-time review, 2026-08-16).
        assert!(!looks_like_attempted_tool_call(
            "Replace {name} with the actual value, e.g. {name}: Alice."
        ));
        assert!(!looks_like_attempted_tool_call(
            "The response schema is {\"type\": \"object\"}; it also mentions \"name\" elsewhere in this sentence."
        ));
        // A malformed-but-recognizable attempt (invalid JSON, but still a brace fragment with
        // the quoted "name" key) still triggers the retry.
        assert!(looks_like_attempted_tool_call(
            r#"{"name": "search", "oops":}"#
        ));
    }
}
