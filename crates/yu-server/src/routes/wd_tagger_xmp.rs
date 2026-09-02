use std::collections::BTreeMap;
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

use xmp_core::{merge_into_file, NamespaceMerge};

/// 対応形式(PNG/JPEG/WebP)の画像へWD-TaggerのXMPメタデータ(wdtag:*属性 +
/// dc:subject rdf:Bag)をマージ書込する。既存の他namespace(sweep属性等)は
/// 変更しない。best-effort: 失敗してもfalseを返すのみで例外を投げない。
pub(crate) fn write_wd_xmp(
    path: &Path,
    tag_names: &[String],
    model: &str,
    general_threshold: f32,
    character_threshold: f32,
) -> bool {
    let tagged_at = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);

    let mut wdtag_attrs = BTreeMap::new();
    wdtag_attrs.insert("model".to_string(), model.to_string());
    wdtag_attrs.insert(
        "general_threshold".to_string(),
        general_threshold.to_string(),
    );
    wdtag_attrs.insert(
        "character_threshold".to_string(),
        character_threshold.to_string(),
    );
    wdtag_attrs.insert("tag_count".to_string(), tag_names.len().to_string());
    wdtag_attrs.insert("tagged_at".to_string(), tagged_at.to_string());

    let merges = [
        NamespaceMerge {
            prefix: "wdtag".to_string(),
            attrs: Some(wdtag_attrs),
            list_items: None,
            replace_attrs: false,
        },
        NamespaceMerge {
            prefix: "dc".to_string(),
            attrs: None,
            list_items: Some((tag_names.to_vec(), "subject".to_string())),
            replace_attrs: false,
        },
    ];

    merge_into_file(path, &merges).is_ok()
}

#[cfg(test)]
mod tests {
    use super::*;
    use xmp_core::parse;

    fn write_minimal_png(path: &Path) {
        let minimal_png: &[u8] = &[
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, // signature
            0x00, 0x00, 0x00, 0x0D, b'I', b'H', b'D', b'R', 0x00, 0x00, 0x00, 0x01, 0x00, 0x00,
            0x00, 0x01, 0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4, 0x89, 0x00, 0x00, 0x00,
            0x00, b'I', b'E', b'N', b'D', 0xAE, 0x42, 0x60, 0x82,
        ];
        std::fs::write(path, minimal_png).unwrap();
    }

    #[test]
    fn write_wd_xmp_writes_and_is_readable_png() {
        let dir = std::env::temp_dir().join("wd-tagger-xmp-test");
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join(format!("test-{}.png", std::process::id()));
        write_minimal_png(&path);

        let ok = write_wd_xmp(
            &path,
            &["blue_eyes".to_string(), "smile".to_string()],
            "wd-swinv2",
            0.35,
            0.85,
        );
        assert!(ok);

        let raw = xmp_core::io::png::read_xmp(&path).unwrap();
        let data = parse(&raw);
        assert_eq!(
            data.get_attrs("wdtag").get("model"),
            Some(&"wd-swinv2".to_string())
        );
        assert_eq!(
            data.get_list("dc"),
            vec!["blue_eyes".to_string(), "smile".to_string()]
        );

        std::fs::remove_file(&path).ok();
    }

    #[test]
    fn write_wd_xmp_writes_and_is_readable_webp() {
        let dir = std::env::temp_dir().join("wd-tagger-xmp-test");
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join(format!("test-{}.webp", std::process::id()));

        // 最小限のlossless WebP(VP8L, 1x1, alpha無し)
        let mut body = Vec::new();
        body.extend_from_slice(b"VP8L");
        let vp8l_payload = [0x2F, 0, 0, 0, 0];
        body.extend_from_slice(&(vp8l_payload.len() as u32).to_le_bytes());
        body.extend_from_slice(&vp8l_payload);
        body.push(0);
        let mut data = b"RIFF".to_vec();
        data.extend_from_slice(&((4 + body.len()) as u32).to_le_bytes());
        data.extend_from_slice(b"WEBP");
        data.extend_from_slice(&body);
        std::fs::write(&path, &data).unwrap();

        let ok = write_wd_xmp(&path, &["1girl".to_string()], "wd-swinv2", 0.35, 0.85);
        assert!(ok);

        let raw = xmp_core::io::webp::read_xmp(&path).unwrap();
        let parsed = parse(&raw);
        assert_eq!(
            parsed.get_attrs("wdtag").get("model"),
            Some(&"wd-swinv2".to_string())
        );

        std::fs::remove_file(&path).ok();
    }
}
