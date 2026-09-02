//! Build the inference recipe the sidecar needs from a tagger profile.
//!
//! The profile registry lives here, so the parsing lives here too. The sidecar
//! receives the already-resolved recipe rather than re-reading the profile
//! from disk — one rule, one reader, one language.
//!
//! The one decision this module makes rather than copies is the threshold
//! table, because Python resolves it differently per adapter family:
//! `WdAdapter` uses the thresholds the user configured, while
//! `GenericOnnxAdapter` goes through `ThresholdTable`, which reads the
//! profile's own `default_thresholds` and ignores the configured ones.

use serde_json::{json, Map, Value};

/// Build the wire profile for `profile`, or `None` when this profile
/// describes something the sidecar cannot reproduce.
///
/// Returning `None` is meaningful: the caller must fall back to the Python
/// implementation rather than run the model with an approximate recipe.
pub(crate) fn wire_profile(profile: &Value, general_thr: f32, character_thr: f32) -> Option<Value> {
    // A remote-hosted or non-ONNX backend has no local weights to run.
    if profile.get("backend").and_then(Value::as_str) != Some("onnx") {
        return None;
    }

    let model_file = required_onnx_file(profile)?;
    let preprocess = profile.get("preprocess_spec")?.as_object()?.clone();
    let tag_source = resolve_tag_source(profile)?;
    let thresholds = resolve_thresholds(profile, general_thr, character_thr);

    let mut out = Map::new();
    out.insert("model_file".into(), json!(model_file));
    out.insert("preprocess_spec".into(), Value::Object(preprocess));
    out.insert("tag_source".into(), tag_source);
    out.insert(
        "output_spec".into(),
        profile.get("output_spec").cloned().unwrap_or(json!({})),
    );
    out.insert("default_thresholds".into(), Value::Object(thresholds));
    out.insert(
        "categories_mode".into(),
        profile
            .get("categories_mode")
            .cloned()
            .unwrap_or_else(|| json!("from_tag_source")),
    );
    out.insert(
        "supports_categories".into(),
        profile
            .get("supports_categories")
            .cloned()
            .unwrap_or_else(|| json!([])),
    );
    Some(Value::Object(out))
}

/// The first required `.onnx` entry in `files[]`, matching how
/// `engine_factory._build_onnx_adapter_via_framework` picks the weights.
fn required_onnx_file(profile: &Value) -> Option<String> {
    profile
        .get("files")?
        .as_array()?
        .iter()
        .filter(|f| f.get("required").and_then(Value::as_bool).unwrap_or(true))
        .filter_map(|f| f.get("name").and_then(Value::as_str))
        .find(|name| name.ends_with(".onnx"))
        .map(str::to_string)
}

/// v2 profiles carry `tag_source` directly; v1 profiles carry `tag_csv_spec`
/// and are upgraded the same way `v1_tag_csv_spec_to_tag_source` does.
fn resolve_tag_source(profile: &Value) -> Option<Value> {
    if let Some(ts) = profile.get("tag_source").and_then(Value::as_object) {
        return Some(Value::Object(ts.clone()));
    }
    let spec = profile.get("tag_csv_spec")?.as_object()?;
    Some(json!({
        "type": "csv",
        "file": "selected_tags.csv",
        "delimiter": spec.get("delimiter").cloned().unwrap_or_else(|| json!(",")),
        "name_col": spec.get("name_col").cloned().unwrap_or_else(|| json!("name")),
        "category_col": spec.get("category_col").cloned().unwrap_or_else(|| json!("category")),
        "category_map": spec.get("category_map").cloned().unwrap_or_else(|| json!({})),
    }))
}

/// Resolve the per-category threshold table the way Python does.
///
/// For the `wd` family the user's configured general/character thresholds win
/// — `WdAdapter._build_result` reads them straight off the config. Every other
/// family goes through `ThresholdTable.from_profile`, which reads the
/// profile's `default_thresholds` and never sees the configured values.
fn resolve_thresholds(profile: &Value, general_thr: f32, character_thr: f32) -> Map<String, Value> {
    if profile.get("adapter_family").and_then(Value::as_str) == Some("wd") {
        let mut map = Map::new();
        map.insert("general".into(), json!(general_thr));
        map.insert("character".into(), json!(character_thr));
        map.insert("rating".into(), json!(0.0));
        return map;
    }
    profile
        .get("default_thresholds")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn wd_v1() -> Value {
        json!({
            "profile_version": "1",
            "id": "wd_vit_v3",
            "model_id": "SmilingWolf/wd-vit-tagger-v3",
            "adapter_family": "wd",
            "backend": "onnx",
            "files": [
                {"name": "model.onnx", "required": true},
                {"name": "selected_tags.csv", "required": true}
            ],
            "preprocess_spec": {
                "input_size": 448, "resize_strategy": "longest_side_pad",
                "pad_color": [255, 255, 255], "channel_order": "BGR",
                "dtype": "float32", "scale": 1.0, "mean": null, "std": null,
                "layout": "NHWC"
            },
            "tag_csv_spec": {
                "delimiter": ",", "name_col": "name", "category_col": "category",
                "category_map": {"0": "general", "4": "character", "9": "rating"}
            },
            "default_thresholds": {"general": 0.35, "character": 0.85, "rating": 0.0},
            "supports_categories": ["general", "character", "rating"]
        })
    }

    fn camie_v2() -> Value {
        json!({
            "profile_version": "2",
            "id": "camie_tagger_v2",
            "model_id": "Camais03/camie-tagger-v2",
            "adapter_family": "camie",
            "backend": "onnx",
            "files": [
                {"name": "camie-tagger-v2.onnx", "required": true},
                {"name": "camie-tagger-v2-metadata.json", "required": true}
            ],
            "preprocess_spec": {"input_size": 512, "layout": "NCHW"},
            "tag_source": {
                "type": "json_dict", "file": "camie-tagger-v2-metadata.json",
                "container_key": "dataset_info.tag_mapping",
                "idx_to_tag_key": "idx_to_tag",
                "tag_to_category_key": "tag_to_category"
            },
            "output_spec": {"output_key": "refined_predictions", "activation": "sigmoid"},
            "default_thresholds": {
                "general": 0.55, "character": 0.85, "rating": 0.0, "meta": 0.7
            },
            "categories_mode": "from_tag_source",
            "supports_categories": ["general", "rating", "meta", "character"]
        })
    }

    #[test]
    fn a_v1_profile_is_upgraded_to_a_csv_tag_source() {
        let wire = wire_profile(&wd_v1(), 0.35, 0.85).expect("wd v1 is supported");
        assert_eq!(wire["model_file"], json!("model.onnx"));
        assert_eq!(wire["tag_source"]["type"], json!("csv"));
        assert_eq!(wire["tag_source"]["file"], json!("selected_tags.csv"));
        assert_eq!(
            wire["tag_source"]["category_map"]["4"],
            json!("character"),
            "the v1 category map must survive the upgrade"
        );
        assert_eq!(wire["output_spec"], json!({}));
    }

    /// `f32` widened into JSON is not the decimal literal you wrote
    /// (`0.11f32` serializes as `0.10999999940395355`), and the sidecar
    /// narrows it straight back to `f32`. Compare numerically.
    fn approx(value: &Value, expected: f32) -> bool {
        value
            .as_f64()
            .is_some_and(|v| (v as f32 - expected).abs() < 1e-6)
    }

    #[test]
    fn the_wd_family_takes_the_configured_thresholds_not_the_profile_defaults() {
        // WdAdapter reads them off the config; sending the profile's 0.35/0.85
        // instead would make the user's slider do nothing.
        let wire = wire_profile(&wd_v1(), 0.11, 0.22).expect("supported");
        assert!(approx(&wire["default_thresholds"]["general"], 0.11));
        assert!(approx(&wire["default_thresholds"]["character"], 0.22));
        assert!(approx(&wire["default_thresholds"]["rating"], 0.0));
    }

    #[test]
    fn other_families_take_the_profile_defaults_and_ignore_the_configured_ones() {
        // GenericOnnxAdapter goes through ThresholdTable, which never sees the
        // configured values. Passing them through would silently retune camie.
        let wire = wire_profile(&camie_v2(), 0.11, 0.22).expect("supported");
        assert_eq!(wire["default_thresholds"]["general"], json!(0.55));
        assert_eq!(wire["default_thresholds"]["character"], json!(0.85));
        assert_eq!(wire["default_thresholds"]["meta"], json!(0.7));
    }

    #[test]
    fn a_v2_profile_passes_its_tag_source_and_output_spec_through_verbatim() {
        let wire = wire_profile(&camie_v2(), 0.35, 0.85).expect("supported");
        assert_eq!(wire["model_file"], json!("camie-tagger-v2.onnx"));
        assert_eq!(
            wire["tag_source"]["container_key"],
            json!("dataset_info.tag_mapping")
        );
        assert_eq!(
            wire["output_spec"]["output_key"],
            json!("refined_predictions")
        );
        assert_eq!(wire["output_spec"]["activation"], json!("sigmoid"));
        assert_eq!(wire["preprocess_spec"]["layout"], json!("NCHW"));
        assert_eq!(
            wire["supports_categories"],
            json!(["general", "rating", "meta", "character"])
        );
    }

    #[test]
    fn a_non_onnx_backend_yields_no_wire_profile() {
        let mut profile = camie_v2();
        profile["backend"] = json!("vlm");
        assert!(
            wire_profile(&profile, 0.35, 0.85).is_none(),
            "a non-ONNX backend has no local weights; the caller must fall back"
        );
    }

    #[test]
    fn a_profile_without_a_required_onnx_yields_no_wire_profile() {
        let mut profile = camie_v2();
        profile["files"] = json!([
            {"name": "camie-tagger-v2.onnx", "required": false},
            {"name": "camie-tagger-v2-metadata.json", "required": true}
        ]);
        assert!(wire_profile(&profile, 0.35, 0.85).is_none());
    }

    #[test]
    fn the_first_required_onnx_wins_over_a_later_one() {
        let mut profile = camie_v2();
        profile["files"] = json!([
            {"name": "primary.onnx", "required": true},
            {"name": "secondary.onnx", "required": true},
            {"name": "camie-tagger-v2-metadata.json", "required": true}
        ]);
        let wire = wire_profile(&profile, 0.35, 0.85).expect("supported");
        assert_eq!(wire["model_file"], json!("primary.onnx"));
    }

    #[test]
    fn the_shipped_profiles_all_produce_a_wire_profile_the_sidecar_accepts() {
        // Deserializing through the sidecar's own type is the point: a field
        // renamed on either side turns into a compile-free, silent fallback to
        // Python otherwise.
        for (label, profile) in [("wd_vit_v3", wd_v1()), ("camie_tagger_v2", camie_v2())] {
            let wire = wire_profile(&profile, 0.35, 0.85)
                .unwrap_or_else(|| panic!("{label} must produce a wire profile"));
            let spec: infer_core::WdProfileSpec = serde_json::from_value(wire)
                .unwrap_or_else(|e| panic!("{label} must deserialize sidecar-side: {e}"));
            spec.validate()
                .unwrap_or_else(|e| panic!("{label} must pass sidecar validation: {e}"));
        }
    }
}
