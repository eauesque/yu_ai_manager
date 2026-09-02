/// Parse a Range header "bytes=START-END" (END is optional).
pub fn parse_range(range_header: &str, file_size: u64) -> Option<(u64, u64)> {
    let s = range_header.strip_prefix("bytes=")?;
    let parts: Vec<&str> = s.splitn(2, '-').collect();
    if parts.len() != 2 || file_size == 0 {
        return None;
    }
    let start: u64 = parts[0].parse().ok()?;
    let end: u64 = if parts[1].is_empty() {
        file_size - 1
    } else {
        parts[1].parse().ok()?
    };
    if start > end || start >= file_size {
        return None;
    }
    Some((start, end.min(file_size - 1)))
}
