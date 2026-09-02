use crate::routes::analysis_results::ZSTD_MAGIC;

const ZSTD_LEVEL: i32 = 3;
const MIN_COMPRESS_LEN: usize = 512;

/// Port of Python `compress_text`: short UTF-8 values remain raw blobs.
pub fn compress_for_storage(text: &str) -> Option<Vec<u8>> {
    let raw = text.as_bytes();
    if raw.len() < MIN_COMPRESS_LEN {
        return Some(raw.to_vec());
    }
    Some(zstd::stream::encode_all(raw, ZSTD_LEVEL).unwrap_or_else(|_| raw.to_vec()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stores_short_values_raw_and_long_values_as_zstd() {
        assert_eq!(compress_for_storage("").unwrap(), b"");
        for len in [511usize, 512, 513] {
            let text = "a".repeat(len);
            let blob = compress_for_storage(&text).unwrap();
            assert_eq!(blob.starts_with(ZSTD_MAGIC), len >= 512);
        }
    }

    #[test]
    fn round_trips_utf8_at_python_thresholds() {
        for len in [0usize, 100, 511, 512, 513, 5000] {
            let text = "あ".repeat(len);
            let blob = compress_for_storage(&text).unwrap();
            let decoded = if blob.starts_with(ZSTD_MAGIC) {
                zstd::stream::decode_all(&blob[..]).unwrap()
            } else {
                blob
            };
            assert_eq!(String::from_utf8_lossy(&decoded), text, "len={len}");
        }
    }
}
