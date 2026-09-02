use std::collections::HashMap;
use std::fs::File;
use std::io::{BufRead, BufReader, Cursor, Seek};
use std::path::Path;

pub fn read_exif_tags(path: &Path) -> HashMap<String, String> {
    let file = match File::open(path) {
        Ok(f) => f,
        Err(_) => return HashMap::new(),
    };
    let mut reader = BufReader::new(file);
    read_exif_tags_from_reader(&mut reader)
}

pub fn read_exif_tags_from_bytes(data: &[u8]) -> HashMap<String, String> {
    read_exif_tags_from_reader(&mut Cursor::new(data))
}

fn read_exif_tags_from_reader(reader: &mut (impl BufRead + Seek)) -> HashMap<String, String> {
    let exif_data = match exif::Reader::new().read_from_container(reader) {
        Ok(e) => e,
        Err(_) => return HashMap::new(),
    };
    exif_data
        .fields()
        .map(|field| {
            let value = if field.tag == exif::Tag::UserComment {
                match &field.value {
                    exif::Value::Undefined(bytes, _) | exif::Value::Byte(bytes) => {
                        decode_user_comment(bytes)
                    }
                    _ => field.display_value().to_string(),
                }
            } else {
                field.display_value().to_string()
            };
            (field.tag.to_string(), value)
        })
        .collect()
}

fn decode_user_comment(data: &[u8]) -> String {
    if let Some(data) = data.strip_prefix(b"UNICODE\0") {
        let units = data
            .as_chunks::<2>()
            .0
            .iter()
            .map(|&pair| u16::from_le_bytes(pair))
            .collect::<Vec<_>>();
        return String::from_utf16_lossy(&units)
            .trim_end_matches('\0')
            .to_string();
    }
    let data = data.strip_prefix(b"ASCII\0\0\0").unwrap_or(data);
    String::from_utf8_lossy(data)
        .trim_end_matches('\0')
        .to_string()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::NamedTempFile;

    #[test]
    fn test_nonexistent_returns_empty() {
        assert!(read_exif_tags(Path::new("/nonexistent/x.jpg")).is_empty());
    }

    #[test]
    fn test_non_image_returns_empty() {
        let mut f = NamedTempFile::new().unwrap();
        f.write_all(b"not an image").unwrap();
        assert!(read_exif_tags(f.path()).is_empty());
    }

    fn bridge_unicode_comment(text: &str) -> Vec<u8> {
        let mut value = b"UNICODE\0".to_vec();
        value.extend(text.encode_utf16().flat_map(u16::to_le_bytes));
        value
    }

    #[test]
    fn decode_unicode_user_comment_matches_bridge_save_round_trip() {
        let expected = r#"YU_META:{"prompt":"猫"}"#;
        let mut value = bridge_unicode_comment(expected);
        value.extend_from_slice(&[0, 0, 0, 0]);
        assert_eq!(decode_user_comment(&value), expected);
    }

    #[test]
    fn decode_ascii_user_comment() {
        assert_eq!(
            decode_user_comment(b"ASCII\0\0\0YU_META:{\"prompt\":\"cat\"}"),
            r#"YU_META:{"prompt":"cat"}"#
        );
    }

    #[test]
    fn decode_unprefixed_user_comment_lossy() {
        assert_eq!(decode_user_comment(b"plain\xfftext"), "plain\u{fffd}text");
    }

    #[test]
    fn decode_unicode_user_comment_ignores_odd_trailing_byte() {
        let mut value = bridge_unicode_comment("YU_META:{}");
        value.push(0xff);
        assert_eq!(decode_user_comment(&value), "YU_META:{}");
    }
}
