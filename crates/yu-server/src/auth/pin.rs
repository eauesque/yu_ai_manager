use hmac::{Hmac, Mac};
use pbkdf2::pbkdf2_hmac;
use sha2::Sha256;

/// Port of Python hash_pin: PBKDF2-HMAC-SHA256 with 600_000 iterations.
pub fn hash_pin(pin: &str, secret: &str) -> String {
    let salt = format!("{}:pin", secret);
    let mut out = [0u8; 32];
    pbkdf2_hmac::<Sha256>(pin.as_bytes(), salt.as_bytes(), 600_000, &mut out);
    hex::encode(out)
}

/// Port of Python make_token: HMAC-SHA256.
pub fn make_token(pin: &str, secret: &str) -> String {
    type HmacSha256 = Hmac<Sha256>;
    let mut mac =
        HmacSha256::new_from_slice(secret.as_bytes()).expect("HMAC accepts any key length");
    mac.update(pin.as_bytes());
    hex::encode(mac.finalize().into_bytes())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hash_pin_deterministic() {
        let a = hash_pin("1234", "mysecret");
        let b = hash_pin("1234", "mysecret");
        assert_eq!(a, b);
        assert_eq!(a.len(), 64);
    }

    #[test]
    fn hash_pin_different_secrets() {
        let a = hash_pin("1234", "secret1");
        let b = hash_pin("1234", "secret2");
        assert_ne!(a, b);
    }

    #[test]
    fn hash_pin_different_pins() {
        let a = hash_pin("1234", "secret");
        let b = hash_pin("5678", "secret");
        assert_ne!(a, b);
    }

    #[test]
    fn make_token_deterministic() {
        let a = make_token("1234", "mysecret");
        let b = make_token("1234", "mysecret");
        assert_eq!(a, b);
        assert_eq!(a.len(), 64);
    }

    #[test]
    fn make_token_differs_from_hash_pin() {
        let h = hash_pin("1234", "secret");
        let t = make_token("1234", "secret");
        assert_ne!(h, t);
    }
}
