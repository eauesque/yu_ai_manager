use rand::TryRngCore;
use subtle::ConstantTimeEq;

/// Generates a 256-bit process-trust token (hex-encoded, 64 chars).
/// Intended for in-memory-only process-to-process auth (e.g. yu-server
/// <-> yu-infer); callers must not persist the result to disk.
pub fn generate_token() -> String {
    let mut bytes = [0u8; 32];
    rand::rngs::OsRng
        .try_fill_bytes(&mut bytes)
        .expect("OS random token generation failed");
    hex::encode(bytes)
}

/// Constant-time comparison of a candidate token against the expected token.
pub fn verify_token(candidate: &str, expected: &str) -> bool {
    candidate.as_bytes().ct_eq(expected.as_bytes()).into()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn generates_64_char_hex_token() {
        let token = generate_token();
        assert_eq!(token.len(), 64);
        assert!(token.chars().all(|c| c.is_ascii_hexdigit()));
    }

    #[test]
    fn generates_distinct_tokens() {
        assert_ne!(generate_token(), generate_token());
    }

    #[test]
    fn verify_token_accepts_matching_tokens() {
        assert!(verify_token("abc123", "abc123"));
    }

    #[test]
    fn verify_token_rejects_mismatched_tokens() {
        assert!(!verify_token("abc123", "xyz789"));
    }
}
