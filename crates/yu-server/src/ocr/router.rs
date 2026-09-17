#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn router_holes_are_pinned() {
        assert_eq!(
            score_for("registry.local/qwen2.5vl:q4", "ocr", &Default::default()),
            80
        );
        assert_eq!(score_for("", "ocr", &Default::default()), 50);
        assert_eq!(
            score_for("llama3.2-vision", "nsfw", &Default::default()),
            50
        );
        let servers = vec![
            srv("low", "llama3.2-vision", true),
            srv("high", "openbmb/minicpm-v4.5", true),
        ];
        assert_eq!(
            select(&servers, "ocr", None, &Default::default())
                .unwrap()
                .id,
            "high"
        );
    }

    #[test]
    fn disabled_explicit_and_ties_are_pinned() {
        let servers = vec![
            srv("disabled", "openbmb/minicpm-v4.5", false),
            srv("first", "qwen2.5vl", true),
            srv("second", "qwen2.5vl", true),
        ];
        assert_eq!(
            select(&servers, "ocr", None, &Default::default())
                .unwrap()
                .id,
            "first"
        );
        assert_eq!(
            select(&servers, "ocr", Some("second"), &Default::default())
                .unwrap()
                .id,
            "second"
        );
    }

    #[test]
    fn profiles_fall_through_and_report_failures() {
        let mut local = serde_json::Map::new();
        local.insert("llama3.2-vision".into(), serde_json::json!({"ocr": 99}));
        assert_eq!(score_for("llama3.2-vision", "ocr", &local), 99);
        let servers = vec![
            srv("best", "openbmb/minicpm-v4.5", true),
            srv("ok", "llama3.2-vision", true),
        ];
        let resolver = |id: &str| {
            if id == "best" {
                Err("connection refused".to_owned())
            } else {
                Ok(())
            }
        };
        assert_eq!(
            select_with_resolver(&servers, "ocr", None, &Default::default(), &resolver)
                .unwrap()
                .id,
            "ok"
        );
        let err = select_with_resolver(&servers[..1], "ocr", None, &Default::default(), &resolver)
            .unwrap_err();
        assert!(err.contains("connection refused"));
    }

    #[test]
    fn ties_keep_registry_order() {
        // Behavioural, not a source scan. An earlier version of this test read
        // its own file with include_str! and grepped for "sort_by" — that
        // reports "caught" when the source is rewritten but never exercises
        // the sort, so any reordering bug that keeps the spelling slips past.
        //
        // Two interleaved score groups, large enough that the sort has real
        // work to do: an all-equal slice is short-circuited by pdqsort and
        // would not distinguish a stable sort from an unstable one.
        //
        // Within each score group the registry order must survive, because
        // that order is what decides which server a request actually reaches.
        let servers: Vec<_> = (0..64)
            .map(|i| {
                let model = if i % 2 == 0 {
                    "openbmb/minicpm-v4.5" // ocr = 97
                } else {
                    "llama3.2-vision" // ocr = 70
                };
                srv(&format!("s{i:02}"), model, true)
            })
            .collect();
        let order: Vec<_> = ranked(&servers, "ocr", &Default::default())
            .into_iter()
            .map(|s| s.id.clone())
            .collect();
        let mut expected: Vec<_> = (0..64).step_by(2).map(|i| format!("s{i:02}")).collect();
        expected.extend((1..64).step_by(2).map(|i| format!("s{i:02}")));
        assert_eq!(
            order, expected,
            "higher scores first, and registry order preserved inside each score group"
        );
    }

    #[test]
    fn higher_scores_come_first() {
        // The consolidated selection test uses servers that all score the same,
        // so it cannot see the ordering at all. Pin it separately: reversing
        // the comparator must be caught here and nowhere else.
        let servers = vec![
            srv("low", "llama3.2-vision", true),       // ocr = 70
            srv("high", "openbmb/minicpm-v4.5", true), // ocr = 97
            srv("mid", "qwen2.5vl", true),             // ocr = 80
        ];
        let order: Vec<_> = ranked(&servers, "ocr", &Default::default())
            .into_iter()
            .map(|s| s.id.clone())
            .collect();
        assert_eq!(order, vec!["high", "mid", "low"], "descending by score");
    }

    #[test]
    fn ranking_excludes_disabled_servers_before_scoring() {
        // The disabled server has the highest score, so a missing `enabled`
        // filter would put it first.
        let servers = vec![
            srv("off", "openbmb/minicpm-v4.5", false),
            srv("on", "llama3.2-vision", true),
        ];
        let order: Vec<_> = ranked(&servers, "ocr", &Default::default())
            .into_iter()
            .map(|s| s.id.clone())
            .collect();
        assert_eq!(
            order,
            vec!["on"],
            "a disabled server must not be ranked at all"
        );
    }

    #[test]
    fn unknown_model_scores_fifty() {
        assert_eq!(score_for("totally-unknown", "ocr", &Default::default()), 50);
    }

    #[test]
    fn empty_model_tag_scores_fifty() {
        assert_eq!(score_for("", "ocr", &Default::default()), 50);
    }

    #[test]
    fn missing_task_scores_fifty() {
        assert_eq!(
            score_for("llama3.2-vision", "nsfw", &Default::default()),
            50
        );
    }

    #[test]
    fn empty_registry_is_an_error() {
        assert!(!select(&[], "ocr", None, &Default::default())
            .unwrap_err()
            .is_empty());
    }

    #[test]
    fn manga_selection_reports_vlm_kind() {
        assert_eq!(
            select(
                &[srv("a", "openbmb/minicpm-v4.5", true)],
                "ocr_manga",
                None,
                &Default::default()
            )
            .unwrap()
            .engine_kind,
            "vlm"
        );
    }

    fn srv(id: &str, model: &str, enabled: bool) -> OcrServer {
        OcrServer {
            id: id.into(),
            name: id.into(),
            model: model.into(),
            enabled,
            engine_kind: "vlm".into(),
        }
    }
}
use serde_json::{Map, Value};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OcrServer {
    pub id: String,
    pub name: String,
    pub model: String,
    pub enabled: bool,
    pub engine_kind: String,
}

const PROFILE_ORDER: [&str; 6] = [
    "openbmb/minicpm-v4.5",
    "openbmb/minicpm-o4.5",
    "huihui_ai/qwen2.5-vl-abliterated",
    "huihui_ai/qwen3-vl-abliterated",
    "qwen2.5vl",
    "llama3.2-vision",
];

const BUILTIN_SCORES: [(&str, &[(&str, i64)]); 6] = [
    (
        "openbmb/minicpm-v4.5",
        &[
            ("ocr", 97),
            ("ocr_document", 90),
            ("ocr_manga", 70),
            ("caption", 95),
            ("tag", 93),
            ("nsfw", 60),
        ],
    ),
    (
        "openbmb/minicpm-o4.5",
        &[
            ("ocr", 95),
            ("ocr_document", 92),
            ("ocr_manga", 65),
            ("caption", 93),
            ("tag", 90),
        ],
    ),
    (
        "huihui_ai/qwen2.5-vl-abliterated",
        &[
            ("ocr", 80),
            ("ocr_document", 75),
            ("ocr_manga", 50),
            ("caption", 85),
            ("tag", 85),
            ("nsfw", 95),
        ],
    ),
    (
        "huihui_ai/qwen3-vl-abliterated",
        &[
            ("ocr", 85),
            ("ocr_document", 80),
            ("ocr_manga", 55),
            ("caption", 88),
            ("tag", 88),
            ("nsfw", 95),
        ],
    ),
    (
        "qwen2.5vl",
        &[
            ("ocr", 80),
            ("ocr_document", 78),
            ("ocr_manga", 50),
            ("caption", 85),
            ("tag", 85),
        ],
    ),
    (
        "llama3.2-vision",
        &[
            ("ocr", 70),
            ("ocr_document", 65),
            ("ocr_manga", 30),
            ("caption", 80),
            ("tag", 78),
        ],
    ),
];

pub fn score_for(model_tag: &str, task: &str, profiles: &Map<String, Value>) -> i64 {
    if model_tag.is_empty() {
        return 50;
    }
    let tag = model_tag.to_ascii_lowercase();
    for prefix in PROFILE_ORDER {
        if tag.contains(&prefix.to_ascii_lowercase()) {
            if let Some(scores) = profiles.get(prefix).and_then(Value::as_object) {
                return scores.get(task).and_then(Value::as_i64).unwrap_or(50);
            }
        }
    }
    for (prefix, scores) in BUILTIN_SCORES {
        if tag.contains(&prefix.to_ascii_lowercase()) {
            return scores
                .iter()
                .find(|(name, _)| *name == task)
                .map(|(_, score)| *score)
                .unwrap_or(50);
        }
    }
    50
}

pub fn select(
    servers: &[OcrServer],
    task: &str,
    server_id: Option<&str>,
    profiles: &Map<String, Value>,
) -> Result<OcrServer, String> {
    select_with_resolver(servers, task, server_id, profiles, &|_| Ok(()))
}

pub fn select_with_resolver(
    servers: &[OcrServer],
    task: &str,
    server_id: Option<&str>,
    profiles: &Map<String, Value>,
    resolver: &dyn Fn(&str) -> Result<(), String>,
) -> Result<OcrServer, String> {
    if let Some(id) = server_id {
        let server = servers
            .iter()
            .find(|server| server.id == id)
            .ok_or_else(|| format!("unknown server: {id}"))?;
        resolver(&server.id)?;
        return Ok(server.clone());
    }
    let scored = ranked(servers, task, profiles);
    if scored.is_empty() {
        return Err("no registered AI servers".to_owned());
    }
    let mut errors = Vec::new();
    for server in scored {
        match resolver(&server.id) {
            Ok(()) => return Ok(server.clone()),
            Err(error) => errors.push(format!("{}: {error}", server.name)),
        }
    }
    Err(format!("no available servers: {}", errors.join("; ")))
}

/// Enabled servers, best task score first, ties in registry order.
///
/// Split out so tests can observe the ordering directly. `sort_by` is stable
/// and `sort_unstable_by` is not: with equal scores the latter may reorder,
/// which would change which server a user's OCR request actually reaches.
fn ranked<'a>(
    servers: &'a [OcrServer],
    task: &str,
    profiles: &serde_json::Map<String, serde_json::Value>,
) -> Vec<&'a OcrServer> {
    let mut scored: Vec<_> = servers.iter().filter(|server| server.enabled).collect();
    scored.sort_by(|left, right| {
        score_for(&right.model, task, profiles).cmp(&score_for(&left.model, task, profiles))
    });
    scored
}
