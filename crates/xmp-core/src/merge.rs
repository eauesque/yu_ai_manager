//! Single-write multi-namespace XMP merge: read target file's existing
//! XMP packet, apply one or more namespace merges, write back in one
//! read-modify-write (spec §3.3).

use std::collections::{BTreeMap, HashMap};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use crate::io::{jpeg, png, webp};
use crate::packet::{parse, serialize, XmpData};

#[derive(Debug, thiserror::Error)]
pub enum XmpError {
    #[error("unsupported image format for XMP write")]
    UnsupportedFormat,
    #[error("io error: {0}")]
    Io(#[from] std::io::Error),
    #[error("jpeg xmp error: {0}")]
    Jpeg(#[from] jpeg::JpegXmpError),
    #[error("webp xmp error: {0}")]
    Webp(#[from] webp::WebpXmpError),
}

/// One namespace's contribution to a merge.
pub struct NamespaceMerge {
    pub prefix: String,
    pub attrs: Option<BTreeMap<String, String>>,
    pub list_items: Option<(Vec<String>, String)>,
    pub replace_attrs: bool,
}

static LOCK_REGISTRY: std::sync::OnceLock<Mutex<HashMap<PathBuf, Arc<Mutex<()>>>>> =
    std::sync::OnceLock::new();

fn path_lock(canonical: &Path) -> Arc<Mutex<()>> {
    let registry = LOCK_REGISTRY.get_or_init(|| Mutex::new(HashMap::new()));
    let mut guard = registry.lock().unwrap();
    let lock = guard
        .entry(canonical.to_path_buf())
        .or_insert_with(|| Arc::new(Mutex::new(())))
        .clone();
    guard.retain(|_, v| Arc::strong_count(v) > 1);
    lock
}

fn extension(path: &Path) -> Option<String> {
    path.extension()
        .and_then(|e| e.to_str())
        .map(|s| s.to_ascii_lowercase())
}

fn dispatch_read(path: &Path) -> Option<String> {
    match extension(path).as_deref() {
        Some("png") => png::read_xmp(path),
        Some("jpg") | Some("jpeg") => jpeg::read_xmp(path),
        Some("webp") => webp::read_xmp(path),
        _ => None,
    }
}

fn dispatch_write(path: &Path, xmp_xml: &str) -> Result<(), XmpError> {
    match extension(path).as_deref() {
        Some("png") => png::write_xmp(path, xmp_xml).map_err(XmpError::Io),
        Some("jpg") | Some("jpeg") => jpeg::write_xmp(path, xmp_xml).map_err(XmpError::Jpeg),
        Some("webp") => webp::write_xmp(path, xmp_xml).map_err(XmpError::Webp),
        _ => Err(XmpError::UnsupportedFormat),
    }
}

/// Merge `merges` into the XMP packet embedded in `path`, in one
/// read-modify-write.
pub fn merge_into_file(path: &Path, merges: &[NamespaceMerge]) -> Result<(), XmpError> {
    let canonical = std::fs::canonicalize(path).unwrap_or_else(|_| path.to_path_buf());
    let lock = path_lock(&canonical);
    let _guard = lock.lock().unwrap();

    let existing = dispatch_read(path);
    let mut data: XmpData = existing.as_deref().map(parse).unwrap_or_default();

    for m in merges {
        if let Some(attrs) = &m.attrs {
            if m.replace_attrs {
                data.attrs.insert(m.prefix.clone(), attrs.clone());
            } else {
                data.attrs
                    .entry(m.prefix.clone())
                    .or_default()
                    .extend(attrs.clone());
            }
        }
        if let Some((items, elem_name)) = &m.list_items {
            data.list_items.insert(m.prefix.clone(), items.clone());
            data.list_element_name
                .insert(m.prefix.clone(), elem_name.clone());
        }
    }

    let xml = serialize(&data);
    dispatch_write(path, &xml)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeMap;

    fn make_test_png(dir: &Path, name: &str) -> PathBuf {
        let mut data = b"\x89PNG\r\n\x1a\n".to_vec();
        data.extend_from_slice(&13u32.to_be_bytes());
        data.extend_from_slice(b"IHDR");
        data.extend_from_slice(&[0u8; 13]);
        data.extend_from_slice(&0u32.to_be_bytes());
        data.extend_from_slice(&0u32.to_be_bytes());
        data.extend_from_slice(b"IEND");
        data.extend_from_slice(&0u32.to_be_bytes());
        let path = dir.join(name);
        std::fs::write(&path, &data).unwrap();
        path
    }

    fn attr_merge(prefix: &str, key: &str, value: &str, replace_attrs: bool) -> NamespaceMerge {
        NamespaceMerge {
            prefix: prefix.to_string(),
            attrs: Some(BTreeMap::from([(key.to_string(), value.to_string())])),
            list_items: None,
            replace_attrs,
        }
    }

    #[test]
    fn merge_into_file_writes_attrs_and_list_in_one_call() {
        let dir = tempfile::tempdir().unwrap();
        let path = make_test_png(dir.path(), "img.png");

        let merges = vec![
            attr_merge("wdtag", "model", "m", false),
            NamespaceMerge {
                prefix: "dc".to_string(),
                attrs: None,
                list_items: Some((vec!["1girl".to_string()], "subject".to_string())),
                replace_attrs: false,
            },
        ];
        merge_into_file(&path, &merges).unwrap();

        let raw = png::read_xmp(&path).unwrap();
        let data = parse(&raw);
        assert_eq!(data.get_attrs("wdtag").get("model"), Some(&"m".to_string()));
        assert_eq!(data.get_list("dc"), vec!["1girl".to_string()]);
    }

    #[test]
    fn merge_into_file_preserves_other_namespaces() {
        let dir = tempfile::tempdir().unwrap();
        let path = make_test_png(dir.path(), "img.png");

        merge_into_file(&path, &[attr_merge("sweep", "id", "abc", true)]).unwrap();
        merge_into_file(&path, &[attr_merge("wdtag", "model", "m", false)]).unwrap();

        let raw = png::read_xmp(&path).unwrap();
        let data = parse(&raw);
        assert_eq!(data.get_attrs("sweep").get("id"), Some(&"abc".to_string()));
        assert_eq!(data.get_attrs("wdtag").get("model"), Some(&"m".to_string()));
    }

    #[test]
    fn merge_into_file_both_orders_preserve_both_namespaces() {
        let dir = tempfile::tempdir().unwrap();
        let path = make_test_png(dir.path(), "img.png");

        merge_into_file(&path, &[attr_merge("wdtag", "model", "m", false)]).unwrap();
        merge_into_file(&path, &[attr_merge("sweep", "id", "abc", true)]).unwrap();

        let data = parse(&png::read_xmp(&path).unwrap());
        assert_eq!(data.get_attrs("wdtag").get("model"), Some(&"m".to_string()));
        assert_eq!(data.get_attrs("sweep").get("id"), Some(&"abc".to_string()));
    }

    #[test]
    fn merge_into_file_unsupported_extension_returns_error() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("img.gif");
        std::fs::write(&path, b"not really a gif").unwrap();
        let result = merge_into_file(&path, &[]);
        assert!(matches!(result, Err(XmpError::UnsupportedFormat)));
    }

    #[test]
    fn merge_into_file_matches_uppercase_extension() {
        let dir = tempfile::tempdir().unwrap();
        let path = make_test_png(dir.path(), "IMG.PNG");

        let result = merge_into_file(&path, &[attr_merge("wdtag", "model", "m", false)]);

        assert!(result.is_ok());
    }

    #[test]
    fn merge_into_file_dispatches_webp_extension() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("img.webp");

        let mut body = Vec::new();
        body.extend_from_slice(b"VP8L");
        let vp8l_payload = [0x2F, 0, 0, 0, 0]; // 1x1, no alpha
        body.extend_from_slice(&(vp8l_payload.len() as u32).to_le_bytes());
        body.extend_from_slice(&vp8l_payload);
        body.push(0);

        let mut data = b"RIFF".to_vec();
        data.extend_from_slice(&((4 + body.len()) as u32).to_le_bytes());
        data.extend_from_slice(b"WEBP");
        data.extend_from_slice(&body);
        std::fs::write(&path, &data).unwrap();

        let result = merge_into_file(
            &path,
            &[NamespaceMerge {
                prefix: "wdtag".to_string(),
                attrs: Some(BTreeMap::from([("model".to_string(), "m".to_string())])),
                list_items: None,
                replace_attrs: false,
            }],
        );

        assert!(result.is_ok(), "{result:?}");
        let raw = crate::io::webp::read_xmp(&path).unwrap();
        let parsed = crate::packet::parse(&raw);
        assert_eq!(
            parsed.get_attrs("wdtag").get("model"),
            Some(&"m".to_string())
        );
    }
}
