use crate::models::{MetaResult, PngTextChunks};
use crate::{a1111, comfyui, novelai_v3, novelai_v4, tensor_art};

/// Which format parsers a scan is allowed to run.
///
/// Backs the `extract_a1111` / `extract_comfyui` settings, which had a UI
/// toggle and a config key but nothing reading them -- in either
/// implementation. Default is everything on, so callers that do not care are
/// unaffected.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ParserToggles {
    pub a1111: bool,
    pub comfyui: bool,
}

impl Default for ParserToggles {
    fn default() -> Self {
        Self {
            a1111: true,
            comfyui: true,
        }
    }
}

/// Detect image metadata format and extract positive/negative prompts.
/// Priority: NovelAI v4 → NovelAI v3 → A1111 → TensorArt → ComfyUI.
pub fn parse_metadata(chunks: &PngTextChunks) -> MetaResult {
    parse_metadata_with(chunks, ParserToggles::default())
}

/// `parse_metadata`, with the A1111 and ComfyUI parsers individually
/// skippable. A disabled parser is passed over, not failed: the chain
/// continues to the next format, and an image only that parser recognizes
/// comes back as `unknown`.
///
/// NovelAI and TensorArt have no toggle of their own -- neither Python's
/// settings schema nor its UI offers one -- so they always run.
pub fn parse_metadata_with(chunks: &PngTextChunks, toggles: ParserToggles) -> MetaResult {
    if let Some(r) = novelai_v4::parse_novelai_v4(chunks) {
        return r;
    }
    if let Some(r) = novelai_v3::parse_novelai_v3(chunks) {
        return r;
    }
    if toggles.a1111 {
        if let Some(r) = a1111::parse_a1111(chunks) {
            return r;
        }
    }
    if let Some(r) = tensor_art::parse_tensor_art(chunks) {
        return r;
    }
    if toggles.comfyui {
        if let Some(r) = comfyui::parse_comfyui(chunks) {
            return r;
        }
    }
    MetaResult::unknown()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_chunks(key: &str, val: &str) -> PngTextChunks {
        let mut c = PngTextChunks::default();
        c.entries.insert(key.into(), val.into());
        c
    }

    #[test]
    fn empty_is_unknown() {
        let r = parse_metadata(&PngTextChunks::default());
        assert_eq!(r.format, "unknown");
    }

    #[test]
    fn dispatches_a1111() {
        let c = make_chunks("parameters", "a cat\nSteps: 10");
        assert_eq!(parse_metadata(&c).format, "a1111");
    }

    #[test]
    fn dispatches_nai_v3() {
        let j = r#"{"prompt":"a fox","uc":"bad"}"#;
        assert_eq!(parse_metadata(&make_chunks("Comment", j)).format, "nai_v3");
    }

    #[test]
    fn dispatches_nai_v4() {
        let j = r#"{"v4_prompt":{"caption":{"base_caption":"x"}}}"#;
        assert_eq!(parse_metadata(&make_chunks("Comment", j)).format, "nai_v4");
    }

    #[test]
    fn tensor_art_precedes_comfyui_like_python() {
        let mut chunks = make_chunks(
            "generation_data",
            r#"{"prompt":"tensor art prompt","negativePrompt":"bad"}"#,
        );
        chunks.entries.insert(
            "prompt".into(),
            r#"{"1":{"class_type":"KSampler","inputs":{}}}"#.into(),
        );
        assert_eq!(parse_metadata(&chunks).format, "tensor_art");
    }
}
