//! JPEG embedded-XMP read/write via APP1 segment byte-splice.
//! Read logic moved from crates/yu-server/src/routes/wd_tagger.rs::read_jpeg_xmp
//! (Tier-1). Write logic is new (spec §3.1, §5.4).

use std::path::Path;

const JPEG_XMP_NS: &[u8] = b"http://ns.adobe.com/xap/1.0/\0";

#[derive(Debug, thiserror::Error)]
pub enum JpegXmpError {
    #[error("io error: {0}")]
    Io(#[from] std::io::Error),
    #[error("not a valid JPEG file")]
    InvalidJpeg,
    #[error("XMP packet too large for a single APP1 segment ({0} bytes, max 65533)")]
    TooLarge(usize),
}

pub fn read_xmp(path: &Path) -> Option<String> {
    let data = std::fs::read(path).ok()?;
    read_xmp_from_bytes(&data)
}

fn read_xmp_from_bytes(data: &[u8]) -> Option<String> {
    if data.len() < 2 || data[0..2] != [0xFF, 0xD8] {
        return None;
    }
    let mut pos = 2usize;
    while pos + 1 < data.len() {
        if data[pos] != 0xFF {
            break;
        }
        let marker = data[pos + 1];
        if marker == 0xDA {
            break;
        }
        if marker == 0x00 || marker == 0xFF {
            pos += 1;
            continue;
        }
        if pos + 3 >= data.len() {
            break;
        }
        let seg_len = u16::from_be_bytes([data[pos + 2], data[pos + 3]]) as usize;
        let seg_end = pos + 2 + seg_len;
        if seg_end > data.len() {
            break;
        }
        if marker == 0xE1 {
            let payload = &data[pos + 4..seg_end];
            if payload.starts_with(JPEG_XMP_NS) {
                return Some(String::from_utf8_lossy(&payload[JPEG_XMP_NS.len()..]).into_owned());
            }
        }
        pos = seg_end;
    }
    None
}

fn strip_xmp_app1(data: &[u8]) -> Vec<u8> {
    let mut pos = 2usize;
    while pos + 1 < data.len() {
        if data[pos] != 0xFF {
            break;
        }
        let marker = data[pos + 1];
        if marker == 0xDA {
            break;
        }
        if marker == 0x00 || marker == 0xFF {
            pos += 1;
            continue;
        }
        if pos + 3 >= data.len() {
            break;
        }
        let seg_len = u16::from_be_bytes([data[pos + 2], data[pos + 3]]) as usize;
        let seg_end = pos + 2 + seg_len;
        if seg_end > data.len() {
            break;
        }
        if marker == 0xE1 {
            let payload = &data[pos + 4..seg_end];
            if payload.starts_with(JPEG_XMP_NS) {
                let mut out = data[..pos].to_vec();
                out.extend_from_slice(&data[seg_end..]);
                return out;
            }
        }
        pos = seg_end;
    }
    data.to_vec()
}

pub fn write_xmp(path: &Path, xmp_xml: &str) -> Result<(), JpegXmpError> {
    let data = std::fs::read(path)?;
    if data.len() < 2 || data[0..2] != [0xFF, 0xD8] {
        return Err(JpegXmpError::InvalidJpeg);
    }
    let stripped = strip_xmp_app1(&data);

    let mut app1_payload = JPEG_XMP_NS.to_vec();
    app1_payload.extend_from_slice(xmp_xml.as_bytes());
    let seg_len = app1_payload.len() + 2;
    let seg_len_u16 =
        u16::try_from(seg_len).map_err(|_| JpegXmpError::TooLarge(app1_payload.len()))?;

    let mut out = Vec::with_capacity(stripped.len() + seg_len + 4);
    out.extend_from_slice(&stripped[..2]);
    out.push(0xFF);
    out.push(0xE1);
    out.extend_from_slice(&seg_len_u16.to_be_bytes());
    out.extend_from_slice(&app1_payload);
    out.extend_from_slice(&stripped[2..]);

    let dir = path.parent().unwrap_or(Path::new("."));
    let tmp = tempfile::Builder::new()
        .prefix(".xmp_")
        .suffix(".tmp")
        .tempfile_in(dir)?;
    let (mut file, tmp_path) = tmp.keep().map_err(|e| e.error)?;
    {
        use std::io::Write;
        file.write_all(&out)?;
    }
    std::fs::rename(&tmp_path, path)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn minimal_jpeg() -> Vec<u8> {
        vec![0xFF, 0xD8, 0xFF, 0xDA]
    }

    #[test]
    fn read_xmp_returns_none_for_plain_jpeg() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("plain.jpg");
        std::fs::write(&path, minimal_jpeg()).unwrap();
        assert_eq!(read_xmp(&path), None);
    }

    #[test]
    fn write_then_read_round_trips() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("img.jpg");
        std::fs::write(&path, minimal_jpeg()).unwrap();

        write_xmp(&path, "<xmp>hello</xmp>").unwrap();

        assert_eq!(read_xmp(&path), Some("<xmp>hello</xmp>".to_string()));
    }

    #[test]
    fn write_replaces_existing_xmp_segment() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("img.jpg");
        std::fs::write(&path, minimal_jpeg()).unwrap();
        write_xmp(&path, "<old/>").unwrap();

        write_xmp(&path, "<new/>").unwrap();

        assert_eq!(read_xmp(&path), Some("<new/>".to_string()));
    }

    #[test]
    fn write_preserves_other_app_segments() {
        let mut data = vec![0xFF, 0xD8];
        data.push(0xFF);
        data.push(0xE0);
        let app0_payload = b"JFIF-marker-data";
        let seg_len = (app0_payload.len() + 2) as u16;
        data.extend_from_slice(&seg_len.to_be_bytes());
        data.extend_from_slice(app0_payload);
        data.push(0xFF);
        data.push(0xDA);

        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("img.jpg");
        std::fs::write(&path, &data).unwrap();

        write_xmp(&path, "<xmp/>").unwrap();

        let written = std::fs::read(&path).unwrap();
        assert!(
            written
                .windows(app0_payload.len())
                .any(|w| w == app0_payload),
            "APP0/JFIF segment must survive XMP write unchanged"
        );
    }

    #[test]
    fn write_errors_when_xmp_packet_exceeds_app1_capacity() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("img.jpg");
        std::fs::write(&path, minimal_jpeg()).unwrap();

        let huge_xmp = "x".repeat(65600);
        let result = write_xmp(&path, &huge_xmp);
        assert!(matches!(result, Err(JpegXmpError::TooLarge(_))));

        assert_eq!(read_xmp(&path), None);
    }
}
