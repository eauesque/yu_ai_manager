use std::collections::HashMap;

#[derive(Debug, Default)]
pub struct MetaResult {
    pub positive: Option<String>,
    pub negative: Option<String>,
    pub format: String,
    pub raw_meta: Option<String>,
    pub params: HashMap<String, String>,
}

impl MetaResult {
    pub fn unknown() -> Self {
        Self {
            format: "unknown".into(),
            ..Default::default()
        }
    }
}

#[derive(Debug, Default)]
pub struct PngTextChunks {
    pub entries: HashMap<String, String>,
    pub compressed_itxt_keywords: Vec<String>,
}
