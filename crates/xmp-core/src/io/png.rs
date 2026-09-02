//! PNG embedded-XMP read/write, moved from
//! crates/yu-server/src/routes/sweep_common.rs (design-advisor rev1 S1:
//! this logic already satisfied PNG write requirements — raw byte
//! preservation of all other chunks, existing-XMP-chunk replacement,
//! self-contained CRC32 — so it is relocated here rather than rewritten).

use std::path::Path;
use std::sync::OnceLock;

const PNG_SIG: &[u8; 8] = b"\x89PNG\r\n\x1a\n";
const XMP_KEY: &[u8] = b"XML:com.adobe.xmp";

fn crc32_table() -> &'static [u32; 256] {
    static T: OnceLock<[u32; 256]> = OnceLock::new();
    T.get_or_init(|| {
        let mut t = [0u32; 256];
        for n in 0..256u32 {
            let mut c = n;
            for _ in 0..8 {
                c = if c & 1 != 0 {
                    0xEDB8_8320 ^ (c >> 1)
                } else {
                    c >> 1
                };
            }
            t[n as usize] = c;
        }
        t
    })
}

fn crc32(data: &[u8]) -> u32 {
    let t = crc32_table();
    let mut c = 0xFFFF_FFFFu32;
    for &b in data {
        c = t[((c ^ b as u32) & 0xFF) as usize] ^ (c >> 8);
    }
    c ^ 0xFFFF_FFFF
}

/// `None` when the payload cannot be expressed as a PNG chunk.
///
/// A chunk declares its data length in a `u32`, so `as u32` wrapped: a payload
/// past 4 GiB produced a chunk whose declared length disagreed with the bytes
/// that followed it, i.e. a silently corrupt PNG written over the user's file.
/// Refusing is the only honest answer, and the caller turns it into an error
/// rather than writing anything.
pub fn build_itxt_chunk(xmp_xml: &str) -> Option<Vec<u8>> {
    let mut payload: Vec<u8> = XMP_KEY.to_vec();
    payload.extend_from_slice(&[0u8, 0, 0, 0, 0]);
    payload.extend_from_slice(xmp_xml.as_bytes());

    let mut chunk: Vec<u8> = u32::try_from(payload.len()).ok()?.to_be_bytes().to_vec();
    chunk.extend_from_slice(b"iTXt");
    chunk.extend_from_slice(&payload);
    let crc = crc32(&chunk[4..]);
    chunk.extend_from_slice(&crc.to_be_bytes());
    Some(chunk)
}

/// Read the embedded XMP packet from a PNG's `tEXt`/`iTXt` chunk keyed
/// `XML:com.adobe.xmp`, or `None` if absent/unparseable.
pub fn read_xmp(path: &Path) -> Option<String> {
    let data = std::fs::read(path).ok()?;
    if data.len() < 8 || &data[..8] != PNG_SIG {
        return None;
    }
    let mut pos = 8usize;
    while pos + 12 <= data.len() {
        let length =
            u32::from_be_bytes([data[pos], data[pos + 1], data[pos + 2], data[pos + 3]]) as usize;
        let type_bytes = &data[pos + 4..pos + 8];
        let chunk_end = pos + 8 + length + 4;
        if chunk_end > data.len() {
            break;
        }
        let cd = &data[pos + 8..pos + 8 + length];

        match type_bytes {
            b"tEXt" => {
                if let Some(n) = cd.iter().position(|&b| b == 0) {
                    if &cd[..n] == XMP_KEY {
                        return String::from_utf8_lossy(&cd[n + 1..]).into_owned().into();
                    }
                }
            }
            b"iTXt" => {
                if let Some(n) = cd.iter().position(|&b| b == 0) {
                    if &cd[..n] == XMP_KEY && cd.len() > n + 3 && cd[n + 1] == 0 {
                        let mut i = n + 3;
                        while i < cd.len() && cd[i] != 0 {
                            i += 1;
                        }
                        i += 1;
                        while i < cd.len() && cd[i] != 0 {
                            i += 1;
                        }
                        i += 1;
                        if i <= cd.len() {
                            return String::from_utf8_lossy(&cd[i..]).into_owned().into();
                        }
                    }
                }
            }
            b"IEND" => break,
            _ => {}
        }
        pos = chunk_end;
    }
    None
}

/// Replace (or insert) the PNG's `XML:com.adobe.xmp` chunk with a new
/// `iTXt` chunk containing `xmp_xml`, preserving every other chunk's raw
/// bytes unchanged. Writes atomically via a same-directory temp file +
/// rename (spec §5.4, finding I1).
pub fn write_xmp(path: &Path, xmp_xml: &str) -> std::io::Result<()> {
    let data = std::fs::read(path)?;
    if data.len() < 8 || &data[..8] != PNG_SIG {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "not a PNG",
        ));
    }
    let Some(new_chunk) = build_itxt_chunk(xmp_xml) else {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidInput,
            "XMP packet does not fit in a PNG chunk",
        ));
    };
    let mut out: Vec<u8> = PNG_SIG.to_vec();
    let mut pos = 8usize;
    let mut inserted = false;

    while pos + 12 <= data.len() {
        let length =
            u32::from_be_bytes([data[pos], data[pos + 1], data[pos + 2], data[pos + 3]]) as usize;
        let type_bytes = &data[pos + 4..pos + 8];
        let chunk_end = pos + 8 + length + 4;
        if chunk_end > data.len() {
            break;
        }
        let cd = &data[pos + 8..pos + 8 + length];

        if type_bytes == b"tEXt" || type_bytes == b"iTXt" {
            if let Some(n) = cd.iter().position(|&b| b == 0) {
                if &cd[..n] == XMP_KEY {
                    pos = chunk_end;
                    continue;
                }
            }
        }

        if type_bytes == b"IEND" {
            out.extend_from_slice(&new_chunk);
            out.extend_from_slice(&data[pos..chunk_end]);
            inserted = true;
            break;
        }

        out.extend_from_slice(&data[pos..chunk_end]);
        pos = chunk_end;
    }

    if !inserted {
        out.extend_from_slice(&new_chunk);
        out.extend_from_slice(&0u32.to_be_bytes());
        out.extend_from_slice(b"IEND");
        out.extend_from_slice(&crc32(b"IEND").to_be_bytes());
    }

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
    std::fs::rename(&tmp_path, path)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_png_with_text(keyword: &str, text: &str) -> Vec<u8> {
        let mut out = PNG_SIG.to_vec();
        out.extend_from_slice(&13u32.to_be_bytes());
        out.extend_from_slice(b"IHDR");
        out.extend_from_slice(&[0u8; 13]);
        out.extend_from_slice(&crc32(b"IHDR\0\0\0\0\0\0\0\0\0\0\0\0\0").to_be_bytes());
        let mut chunk = keyword.as_bytes().to_vec();
        chunk.push(0);
        chunk.extend_from_slice(text.as_bytes());
        out.extend_from_slice(&(chunk.len() as u32).to_be_bytes());
        out.extend_from_slice(b"tEXt");
        out.extend_from_slice(&chunk);
        out.extend_from_slice(
            &crc32(&{
                let mut v = b"tEXt".to_vec();
                v.extend_from_slice(&chunk);
                v
            })
            .to_be_bytes(),
        );
        out.extend_from_slice(&0u32.to_be_bytes());
        out.extend_from_slice(b"IEND");
        out.extend_from_slice(&crc32(b"IEND").to_be_bytes());
        out
    }

    #[test]
    fn read_xmp_extracts_text_chunk() {
        let png = make_png_with_text("XML:com.adobe.xmp", "<xmp/>");
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("img.png");
        std::fs::write(&path, &png).unwrap();
        assert_eq!(read_xmp(&path), Some("<xmp/>".to_string()));
    }

    #[test]
    fn read_xmp_returns_none_when_absent() {
        let png = make_png_with_text("parameters", "Steps: 20");
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("img.png");
        std::fs::write(&path, &png).unwrap();
        assert_eq!(read_xmp(&path), None);
    }

    #[test]
    fn write_xmp_preserves_other_chunks_and_is_readable() {
        let png = make_png_with_text("parameters", "Steps: 20, CFG: 7");
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("img.png");
        std::fs::write(&path, &png).unwrap();

        write_xmp(&path, "<xmp>hello</xmp>").unwrap();

        assert_eq!(read_xmp(&path), Some("<xmp>hello</xmp>".to_string()));
        let written = std::fs::read(&path).unwrap();
        let needle = b"parameters\0Steps: 20, CFG: 7";
        assert!(
            written.windows(needle.len()).any(|w| w == needle),
            "parameters chunk should survive XMP write unchanged"
        );
    }

    #[test]
    fn write_xmp_replaces_existing_xmp_chunk() {
        let png = make_png_with_text("XML:com.adobe.xmp", "<old/>");
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("img.png");
        std::fs::write(&path, &png).unwrap();

        write_xmp(&path, "<new/>").unwrap();

        assert_eq!(read_xmp(&path), Some("<new/>".to_string()));
        let written = std::fs::read(&path).unwrap();
        assert!(
            !written.windows(5).any(|w| w == b"<old/"),
            "old XMP text must not remain"
        );
    }
}
