//! WebP embedded-XMP read/write via hand-rolled RIFF chunk splice (no
//! libwebp-sys FFI; see spec section 1.1 for why). Read logic mirrors the
//! existing crates/yu-server/src/routes/wd_tagger.rs::read_webp_xmp
//! (Tier-1). Write logic is new (spec section 3.1).

use std::fs;
use std::path::Path;

/// Extract (width, height, has_alpha) from a VP8 (lossy) keyframe.
fn extract_vp8_dims(payload: &[u8]) -> Result<(u32, u32, bool), WebpXmpError> {
    if payload.len() < 10 {
        return Err(WebpXmpError::InvalidWebp);
    }
    if payload[3] != 0x9d || payload[4] != 0x01 || payload[5] != 0x2a {
        return Err(WebpXmpError::InvalidWebp);
    }
    let width = (u16::from_le_bytes([payload[6], payload[7]]) & 0x3fff) as u32;
    let height = (u16::from_le_bytes([payload[8], payload[9]]) & 0x3fff) as u32;
    Ok((width, height, false))
}

/// Extract (width, height, has_alpha) from a VP8L (lossless) bitstream header.
fn extract_vp8l_dims(payload: &[u8]) -> Result<(u32, u32, bool), WebpXmpError> {
    if payload.len() < 5 || payload[0] != 0x2f {
        return Err(WebpXmpError::InvalidWebp);
    }
    let bits = u32::from_le_bytes([payload[1], payload[2], payload[3], payload[4]]);
    let width = 1 + (bits & 0x3fff);
    let height = 1 + ((bits >> 14) & 0x3fff);
    let has_alpha = ((bits >> 28) & 1) == 1;
    Ok((width, height, has_alpha))
}

fn build_vp8x_payload(width: u32, height: u32, has_alpha: bool) -> Vec<u8> {
    let mut payload = vec![0u8; 10];
    payload[0] = 0x04 | if has_alpha { 0x10 } else { 0 };
    let w_minus1 = width.saturating_sub(1) & 0x00ff_ffff;
    let h_minus1 = height.saturating_sub(1) & 0x00ff_ffff;
    payload[4] = (w_minus1 & 0xff) as u8;
    payload[5] = ((w_minus1 >> 8) & 0xff) as u8;
    payload[6] = ((w_minus1 >> 16) & 0xff) as u8;
    payload[7] = (h_minus1 & 0xff) as u8;
    payload[8] = ((h_minus1 >> 8) & 0xff) as u8;
    payload[9] = ((h_minus1 >> 16) & 0xff) as u8;
    payload
}

#[derive(Debug, thiserror::Error)]
pub enum WebpXmpError {
    #[error("io error: {0}")]
    Io(#[from] std::io::Error),
    #[error("not a valid WebP file")]
    InvalidWebp,
    #[error("animated WebP is not supported for XMP write")]
    Animated,
    #[error("resulting WebP file would exceed the 4GiB RIFF size limit")]
    TooLarge,
}

struct WebpChunk {
    fourcc: [u8; 4],
    /// Byte range of this chunk's payload (excluding the 8-byte fourcc+size
    /// header and any trailing pad byte) within the original file buffer.
    data_range: (usize, usize),
}

fn parse_chunks(data: &[u8], validate_riff_size: bool) -> Result<Vec<WebpChunk>, WebpXmpError> {
    if data.len() < 12 || &data[0..4] != b"RIFF" || &data[8..12] != b"WEBP" {
        return Err(WebpXmpError::InvalidWebp);
    }

    let riff_size = u32::from_le_bytes([data[4], data[5], data[6], data[7]]) as usize;
    let riff_end = riff_size.checked_add(8);
    if validate_riff_size && riff_end.is_none_or(|total| total > data.len()) {
        return Err(WebpXmpError::InvalidWebp);
    }

    let end = if validate_riff_size {
        riff_end.unwrap()
    } else {
        data.len()
    };
    let mut pos = 12usize;
    let mut chunks = Vec::new();
    while pos < end {
        if pos + 8 > end {
            return Err(WebpXmpError::InvalidWebp);
        }
        let fourcc = [data[pos], data[pos + 1], data[pos + 2], data[pos + 3]];
        let size = u32::from_le_bytes([data[pos + 4], data[pos + 5], data[pos + 6], data[pos + 7]])
            as usize;
        let start = pos + 8;
        let payload_end = start.checked_add(size).ok_or(WebpXmpError::InvalidWebp)?;
        let next = payload_end
            .checked_add(size % 2)
            .ok_or(WebpXmpError::InvalidWebp)?;
        if next > end {
            return Err(WebpXmpError::InvalidWebp);
        }
        chunks.push(WebpChunk {
            fourcc,
            data_range: (start, payload_end),
        });
        pos = next;
    }
    Ok(chunks)
}

fn is_animated(chunks: &[WebpChunk]) -> bool {
    chunks
        .iter()
        .any(|c| &c.fourcc == b"ANIM" || &c.fourcc == b"ANMF")
}

pub fn read_xmp(path: &Path) -> Option<String> {
    let data = fs::read(path).ok()?;
    let chunks = parse_chunks(&data, false).ok()?;
    let chunk = chunks.iter().find(|c| &c.fourcc == b"XMP ")?;
    Some(String::from_utf8_lossy(&data[chunk.data_range.0..chunk.data_range.1]).into_owned())
}

fn push_chunk(out: &mut Vec<u8>, fourcc: &[u8; 4], payload: &[u8]) -> Result<(), WebpXmpError> {
    let size = u32::try_from(payload.len()).map_err(|_| WebpXmpError::TooLarge)?;
    out.extend_from_slice(fourcc);
    out.extend_from_slice(&size.to_le_bytes());
    out.extend_from_slice(payload);
    if payload.len() % 2 == 1 {
        out.push(0);
    }
    Ok(())
}

/// Replace (or insert) a WebP's `XMP ` chunk, preserving every other chunk's
/// raw bytes unchanged. If no `VP8X` chunk exists yet (simple-format WebP),
/// one is synthesized (see Task 3 / spec §3.1 steps 5-6). Writes atomically
/// via a same-directory temp file + rename (spec §3.1 step 9).
pub fn write_xmp(path: &Path, xmp_xml: &str) -> Result<(), WebpXmpError> {
    let data = fs::read(path)?;
    let chunks = parse_chunks(&data, true)?;
    if is_animated(&chunks) {
        return Err(WebpXmpError::Animated);
    }

    let has_vp8x = chunks.iter().any(|c| &c.fourcc == b"VP8X");
    if !has_vp8x {
        let vp8 = chunks.iter().find(|c| &c.fourcc == b"VP8 ");
        let vp8l = chunks.iter().find(|c| &c.fourcc == b"VP8L");
        let (width, height, mut has_alpha) = match (vp8, vp8l) {
            (Some(c), None) => {
                let (s, e) = c.data_range;
                extract_vp8_dims(&data[s..e])?
            }
            (None, Some(c)) => {
                let (s, e) = c.data_range;
                extract_vp8l_dims(&data[s..e])?
            }
            _ => return Err(WebpXmpError::InvalidWebp),
        };
        has_alpha |= chunks.iter().any(|c| &c.fourcc == b"ALPH");

        let mut out = b"RIFF\0\0\0\0WEBP".to_vec();
        push_chunk(
            &mut out,
            b"VP8X",
            &build_vp8x_payload(width, height, has_alpha),
        )?;
        push_chunk(&mut out, b"XMP ", xmp_xml.as_bytes())?;
        for chunk in &chunks {
            if &chunk.fourcc == b"XMP " {
                continue;
            }
            let payload = &data[chunk.data_range.0..chunk.data_range.1];
            let raw_start = chunk.data_range.0 - 8;
            let raw_end = chunk.data_range.1 + payload.len() % 2;
            out.extend_from_slice(&data[raw_start..raw_end]);
        }

        let riff_size = u32::try_from(out.len() - 8).map_err(|_| WebpXmpError::TooLarge)?;
        out[4..8].copy_from_slice(&riff_size.to_le_bytes());
        let parent = path.parent().unwrap_or(Path::new("."));
        let mut tmp = tempfile::NamedTempFile::new_in(parent)?;
        use std::io::Write;
        tmp.write_all(&out)?;
        let tmp_path = tmp.path().to_owned();
        let file = tmp.as_file_mut();
        file.sync_all()?;
        tmp.keep().map_err(|e| e.error)?;
        fs::rename(&tmp_path, path)?;
        return Ok(());
    }

    let mut out = b"RIFF\0\0\0\0WEBP".to_vec();
    let mut inserted = false;
    for chunk in &chunks {
        let payload = &data[chunk.data_range.0..chunk.data_range.1];
        let raw_start = chunk.data_range.0 - 8;
        let raw_end = chunk.data_range.1 + payload.len() % 2;

        if &chunk.fourcc == b"XMP " {
            continue;
        }

        if &chunk.fourcc == b"VP8X" {
            if payload.len() != 10 {
                return Err(WebpXmpError::InvalidWebp);
            }
            let mut vp8x = payload.to_vec();
            vp8x[0] |= 0x04;
            push_chunk(&mut out, b"VP8X", &vp8x)?;
            push_chunk(&mut out, b"XMP ", xmp_xml.as_bytes())?;
            inserted = true;
        } else {
            out.extend_from_slice(&data[raw_start..raw_end]);
        }
    }

    if !inserted {
        return Err(WebpXmpError::InvalidWebp);
    }
    let riff_size = u32::try_from(out.len() - 8).map_err(|_| WebpXmpError::TooLarge)?;
    out[4..8].copy_from_slice(&riff_size.to_le_bytes());

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
    fs::rename(&tmp_path, path)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn minimal_webp(chunks: &[(&[u8; 4], &[u8])]) -> Vec<u8> {
        let mut body = Vec::new();
        for (fourcc, payload) in chunks {
            body.extend_from_slice(*fourcc);
            body.extend_from_slice(&(payload.len() as u32).to_le_bytes());
            body.extend_from_slice(payload);
            if payload.len() % 2 == 1 {
                body.push(0);
            }
        }
        let mut out = b"RIFF".to_vec();
        out.extend_from_slice(&((4 + body.len()) as u32).to_le_bytes());
        out.extend_from_slice(b"WEBP");
        out.extend_from_slice(&body);
        out
    }

    fn vp8x(flags: u8) -> [u8; 10] {
        [flags, 0, 0, 0, 1, 0, 0, 1, 0, 0]
    }

    fn chunk_payload<'a>(data: &'a [u8], fourcc: &[u8; 4]) -> Option<&'a [u8]> {
        let chunks = parse_chunks(data, true).unwrap();
        let chunk = chunks.iter().find(|c| &c.fourcc == fourcc)?;
        Some(&data[chunk.data_range.0..chunk.data_range.1])
    }

    fn chunk_count(data: &[u8], fourcc: &[u8; 4]) -> usize {
        parse_chunks(data, true)
            .unwrap()
            .iter()
            .filter(|c| &c.fourcc == fourcc)
            .count()
    }

    #[test]
    fn extract_vp8_dims_reads_width_height() {
        let payload: [u8; 10] = [0, 0, 0, 0x9d, 0x01, 0x2a, 100, 0, 200, 0];
        let (w, h, alpha) = extract_vp8_dims(&payload).unwrap();
        assert_eq!((w, h, alpha), (100, 200, false));
    }

    #[test]
    fn extract_vp8_dims_rejects_bad_start_code() {
        let payload: [u8; 10] = [0, 0, 0, 0xFF, 0xFF, 0xFF, 100, 0, 200, 0];
        assert!(matches!(
            extract_vp8_dims(&payload),
            Err(WebpXmpError::InvalidWebp)
        ));
    }

    #[test]
    fn extract_vp8_dims_rejects_too_short_payload() {
        let payload: [u8; 5] = [0, 0, 0, 0x9d, 0x01];
        assert!(matches!(
            extract_vp8_dims(&payload),
            Err(WebpXmpError::InvalidWebp)
        ));
    }

    #[test]
    fn extract_vp8l_dims_reads_width_height_and_alpha() {
        let bits: u32 = 9 | (19 << 14) | (1 << 28);
        let mut payload = vec![0x2F];
        payload.extend_from_slice(&bits.to_le_bytes());
        let (w, h, alpha) = extract_vp8l_dims(&payload).unwrap();
        assert_eq!((w, h, alpha), (10, 20, true));
    }

    #[test]
    fn extract_vp8l_dims_rejects_bad_signature() {
        let payload = [0x00, 0, 0, 0, 0];
        assert!(matches!(
            extract_vp8l_dims(&payload),
            Err(WebpXmpError::InvalidWebp)
        ));
    }

    #[test]
    fn write_xmp_promotes_simple_vp8l_to_extended() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("simple.webp");
        let bits: u32 = 9 | (19 << 14);
        let mut vp8l_payload = vec![0x2F];
        vp8l_payload.extend_from_slice(&bits.to_le_bytes());
        vp8l_payload.extend_from_slice(b"fake-pixel-data");
        fs::write(&path, minimal_webp(&[(b"VP8L", &vp8l_payload)])).unwrap();

        write_xmp(&path, "<xmp>promoted</xmp>").unwrap();

        assert_eq!(read_xmp(&path), Some("<xmp>promoted</xmp>".to_string()));
        let written = fs::read(&path).unwrap();
        let chunks = parse_chunks(&written, false).unwrap();
        assert_eq!(chunks[0].fourcc, *b"VP8X");
        let vp8x = &chunks[0];
        let flags = written[vp8x.data_range.0];
        assert_eq!(flags & 0x04, 0x04);
        assert_eq!(flags & 0x10, 0);
        assert_eq!(written[vp8x.data_range.0 + 4], 9);
        assert_eq!(written[vp8x.data_range.0 + 7], 19);
        let vp8l = chunks.iter().find(|c| &c.fourcc == b"VP8L").unwrap();
        assert_eq!(&written[vp8l.data_range.0..vp8l.data_range.1], vp8l_payload);
    }

    #[test]
    fn write_xmp_promotes_simple_vp8l_with_alpha() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("alpha.webp");
        let bits: u32 = 9 | (19 << 14) | (1 << 28);
        let mut vp8l_payload = vec![0x2F];
        vp8l_payload.extend_from_slice(&bits.to_le_bytes());
        fs::write(&path, minimal_webp(&[(b"VP8L", &vp8l_payload)])).unwrap();

        write_xmp(&path, "<xmp/>").unwrap();

        let written = fs::read(&path).unwrap();
        let chunks = parse_chunks(&written, false).unwrap();
        let vp8x = chunks.iter().find(|c| &c.fourcc == b"VP8X").unwrap();
        assert_eq!(written[vp8x.data_range.0] & 0x10, 0x10);
    }

    #[test]
    fn write_xmp_promotes_simple_vp8_and_propagates_alph_chunk() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("vp8_alph.webp");
        let vp8_payload: [u8; 10] = [0, 0, 0, 0x9d, 0x01, 0x2a, 10, 0, 20, 0];
        fs::write(
            &path,
            minimal_webp(&[(b"ALPH", b"fake-alpha-plane"), (b"VP8 ", &vp8_payload)]),
        )
        .unwrap();

        write_xmp(&path, "<xmp/>").unwrap();

        let written = fs::read(&path).unwrap();
        let chunks = parse_chunks(&written, false).unwrap();
        let vp8x = chunks.iter().find(|c| &c.fourcc == b"VP8X").unwrap();
        assert_eq!(written[vp8x.data_range.0] & 0x10, 0x10);
        assert_eq!(written[vp8x.data_range.0 + 4], 9);
        assert_eq!(written[vp8x.data_range.0 + 7], 19);
    }

    #[test]
    fn write_xmp_rejects_webp_with_neither_vp8_nor_vp8l() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("empty.webp");
        fs::write(
            &path,
            minimal_webp(&[(b"ICCP", b"icc-only-no-image-chunk")]),
        )
        .unwrap();
        assert!(matches!(
            write_xmp(&path, "<xmp/>"),
            Err(WebpXmpError::InvalidWebp)
        ));
    }

    #[test]
    fn read_xmp_extracts_chunk() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("img.webp");
        let data = minimal_webp(&[(b"XMP ", b"<xmp>hello</xmp>")]);
        fs::write(&path, &data).unwrap();
        assert_eq!(read_xmp(&path), Some("<xmp>hello</xmp>".to_string()));
    }

    #[test]
    fn read_xmp_returns_none_without_xmp_chunk() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("plain.webp");
        let data = minimal_webp(&[(b"VP8L", &[0x2F, 0, 0, 0, 0])]);
        fs::write(&path, &data).unwrap();
        assert_eq!(read_xmp(&path), None);
    }

    #[test]
    fn read_xmp_returns_none_for_non_webp() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("not.webp");
        fs::write(&path, b"not a riff file at all").unwrap();
        assert_eq!(read_xmp(&path), None);
    }

    #[test]
    fn read_xmp_odd_length_chunk_padding_is_skipped_correctly() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("img.webp");
        let data = minimal_webp(&[(b"XMP ", b"odd"), (b"VP8L", &[0x2F, 0, 0, 0, 0])]);
        fs::write(&path, &data).unwrap();
        assert_eq!(read_xmp(&path), Some("odd".to_string()));
    }

    #[test]
    fn is_animated_detects_anim_chunk() {
        let data = minimal_webp(&[(b"ANIM", &[0, 0, 0, 0, 0, 0])]);
        let chunks = parse_chunks(&data, false).unwrap();
        assert!(is_animated(&chunks));
    }

    #[test]
    fn is_animated_detects_anmf_chunk() {
        let data = minimal_webp(&[(b"ANMF", &[0u8; 16])]);
        let chunks = parse_chunks(&data, false).unwrap();
        assert!(is_animated(&chunks));
    }

    #[test]
    fn is_animated_false_for_static_webp() {
        let data = minimal_webp(&[(b"VP8L", &[0x2F, 0, 0, 0, 0])]);
        let chunks = parse_chunks(&data, false).unwrap();
        assert!(!is_animated(&chunks));
    }

    #[test]
    fn parse_chunks_write_mode_rejects_declared_size_larger_than_file() {
        let mut data = minimal_webp(&[(b"VP8L", &[0x2F, 0, 0, 0, 0])]);
        let bogus_size = 9_999_999u32;
        data[4..8].copy_from_slice(&bogus_size.to_le_bytes());
        let result = parse_chunks(&data, true);
        assert!(matches!(result, Err(WebpXmpError::InvalidWebp)));
    }

    #[test]
    fn parse_chunks_read_mode_tolerates_declared_size_mismatch() {
        let mut data = minimal_webp(&[(b"XMP ", b"hi")]);
        let bogus_size = 9_999_999u32;
        data[4..8].copy_from_slice(&bogus_size.to_le_bytes());
        let chunks = parse_chunks(&data, false).unwrap();
        assert_eq!(chunks.len(), 1);
        assert_eq!(&chunks[0].fourcc, b"XMP ");
    }

    #[test]
    fn parse_chunks_rejects_truncated_chunk() {
        let mut data = minimal_webp(&[(b"XMP ", b"hello")]);
        data.truncate(data.len() - 3);
        let result = parse_chunks(&data, false);
        assert!(matches!(result, Err(WebpXmpError::InvalidWebp)));
    }

    #[test]
    fn write_xmp_sets_flag_and_adds_chunk_on_extended_webp() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("extended.webp");
        let vp8x = vp8x(0);
        fs::write(&path, minimal_webp(&[(b"VP8X", &vp8x)])).unwrap();

        write_xmp(&path, "<xmp>hello</xmp>").unwrap();

        let data = fs::read(&path).unwrap();
        assert_eq!(
            chunk_payload(&data, b"XMP "),
            Some(&b"<xmp>hello</xmp>"[..])
        );
        assert_eq!(chunk_payload(&data, b"VP8X").unwrap()[0] & 0x04, 0x04);
        assert_eq!(
            u32::from_le_bytes(data[4..8].try_into().unwrap()) as usize,
            data.len() - 8
        );
    }

    #[test]
    fn write_xmp_preserves_iccp_and_exif_chunks() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("metadata.webp");
        let vp8x = vp8x(0x28);
        fs::write(
            &path,
            minimal_webp(&[(b"VP8X", &vp8x), (b"ICCP", b"icc"), (b"EXIF", b"exif")]),
        )
        .unwrap();

        write_xmp(&path, "<xmp/>").unwrap();

        let data = fs::read(&path).unwrap();
        assert_eq!(chunk_payload(&data, b"ICCP"), Some(&b"icc"[..]));
        assert_eq!(chunk_payload(&data, b"EXIF"), Some(&b"exif"[..]));
        assert_eq!(chunk_payload(&data, b"VP8X").unwrap()[0] & 0x2c, 0x2c);
    }

    #[test]
    fn write_xmp_replaces_existing_xmp_chunk() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("replace.webp");
        let vp8x = vp8x(0x04);
        fs::write(
            &path,
            minimal_webp(&[(b"VP8X", &vp8x), (b"XMP ", b"<old/>")]),
        )
        .unwrap();

        write_xmp(&path, "<new/>").unwrap();

        let data = fs::read(&path).unwrap();
        assert_eq!(chunk_count(&data, b"XMP "), 1);
        assert_eq!(chunk_payload(&data, b"XMP "), Some(&b"<new/>"[..]));
    }

    #[test]
    fn write_xmp_rejects_animated_webp() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("animated.webp");
        let vp8x = vp8x(0x02);
        fs::write(&path, minimal_webp(&[(b"VP8X", &vp8x), (b"ANIM", &[0; 6])])).unwrap();

        let result = write_xmp(&path, "<xmp/>");

        assert!(matches!(result, Err(WebpXmpError::Animated)));
    }

    #[test]
    fn write_xmp_rejects_invalid_webp() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("invalid.webp");
        fs::write(&path, b"not webp").unwrap();

        let result = write_xmp(&path, "<xmp/>");

        assert!(matches!(result, Err(WebpXmpError::InvalidWebp)));
    }
}
