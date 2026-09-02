pub fn generate_infer_auth_token() -> String {
    auth_core::generate_token()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn generates_64_char_hex_token() {
        let token = generate_infer_auth_token();
        assert_eq!(token.len(), 64);
        assert!(token.chars().all(|c| c.is_ascii_hexdigit()));
    }

    #[test]
    fn generates_distinct_tokens() {
        let a = generate_infer_auth_token();
        let b = generate_infer_auth_token();
        assert_ne!(a, b);
    }
}
