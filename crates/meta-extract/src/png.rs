use crate::models::PngTextChunks;
use std::path::Path;

const PNG_SIG: &[u8; 8] = b"\x89PNG\r\n\x1a\n";

pub fn read_png_text_chunks(path: &Path) -> PngTextChunks {
    match std::fs::read(path) {
        Ok(data) => parse_png_text_chunks(&data),
        Err(_) => PngTextChunks::default(),
    }
}

pub fn parse_png_text_chunks(data: &[u8]) -> PngTextChunks {
    let mut result = PngTextChunks::default();
    if data.len() < 8 || &data[..8] != PNG_SIG {
        return result;
    }
    let mut pos = 8usize;
    while pos + 12 <= data.len() {
        let length =
            u32::from_be_bytes([data[pos], data[pos + 1], data[pos + 2], data[pos + 3]]) as usize;
        let chunk_type = &data[pos + 4..pos + 8];
        let end = pos + 8 + length;
        if end + 4 > data.len() {
            break;
        }
        let chunk_data = &data[pos + 8..end];
        match chunk_type {
            b"tEXt" => {
                if let Some((k, v)) = parse_text(chunk_data) {
                    result.entries.insert(k, v);
                }
            }
            b"iTXt" => {
                if let Some((keyword, text)) = parse_itxt(chunk_data) {
                    if let Some(text) = text {
                        result.entries.insert(keyword, text);
                    } else {
                        result.compressed_itxt_keywords.push(keyword);
                    }
                }
            }
            b"IEND" => break,
            _ => {}
        }
        pos = end + 4; // CRC をスキップ
    }
    result
}

fn parse_text(data: &[u8]) -> Option<(String, String)> {
    let sep = data.iter().position(|&b| b == 0)?;
    let keyword = String::from_utf8(data[..sep].to_vec()).ok()?;
    let text = String::from_utf8_lossy(&data[sep + 1..]).into_owned();
    Some((keyword, text))
}

fn parse_itxt(data: &[u8]) -> Option<(String, Option<String>)> {
    let sep = data.iter().position(|&b| b == 0)?;
    let keyword = String::from_utf8(data[..sep].to_vec()).ok()?;
    if data.len() < sep + 3 {
        return None;
    }
    let compression_flag = data[sep + 1];
    let mut i = sep + 3;
    while i < data.len() && data[i] != 0 {
        i += 1;
    }
    i += 1; // language
    while i < data.len() && data[i] != 0 {
        i += 1;
    }
    i += 1; // translated keyword
    if i > data.len() {
        return None;
    }
    if compression_flag != 0 {
        return Some((keyword, None));
    }
    Some((
        keyword,
        Some(String::from_utf8_lossy(&data[i..]).into_owned()),
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_png_with_text(keyword: &str, text: &str) -> Vec<u8> {
        let mut out = PNG_SIG.to_vec();
        // IHDR（ダミー）
        out.extend_from_slice(&13u32.to_be_bytes());
        out.extend_from_slice(b"IHDR");
        out.extend_from_slice(&[0u8; 13]);
        out.extend_from_slice(&0u32.to_be_bytes());
        // tEXt
        let mut chunk = keyword.as_bytes().to_vec();
        chunk.push(0);
        chunk.extend_from_slice(text.as_bytes());
        out.extend_from_slice(&(chunk.len() as u32).to_be_bytes());
        out.extend_from_slice(b"tEXt");
        out.extend_from_slice(&chunk);
        out.extend_from_slice(&0u32.to_be_bytes());
        // IEND
        out.extend_from_slice(&0u32.to_be_bytes());
        out.extend_from_slice(b"IEND");
        out.extend_from_slice(&0u32.to_be_bytes());
        out
    }

    #[test]
    fn test_parameters_chunk() {
        let png = make_png_with_text("parameters", "Steps: 20, CFG: 7");
        let chunks = parse_png_text_chunks(&png);
        assert_eq!(
            chunks.entries.get("parameters").map(|s| s.as_str()),
            Some("Steps: 20, CFG: 7")
        );
    }

    #[test]
    fn test_non_png_returns_empty() {
        let chunks = parse_png_text_chunks(b"NOTPNG\x00\x01");
        assert!(chunks.entries.is_empty());
    }

    #[test]
    fn test_no_text_chunk() {
        let mut data = PNG_SIG.to_vec();
        data.extend_from_slice(&0u32.to_be_bytes());
        data.extend_from_slice(b"IEND");
        data.extend_from_slice(&0u32.to_be_bytes());
        assert!(parse_png_text_chunks(&data).entries.is_empty());
    }
}
