use axum::{
    extract::Request,
    http::{HeaderName, HeaderValue},
    middleware::Next,
    response::Response,
};

use crate::routes::lan_cowork_host::FleetUiNonce;

/// Per-request CSP nonce, inserted by `layer` middleware and extracted by page handlers.
#[derive(Clone)]
pub struct CspNonce(pub String);

fn gen_nonce() -> String {
    use rand::RngCore;
    let mut bytes = [0u8; 16];
    rand::rng().fill_bytes(&mut bytes);
    bytes.iter().fold(String::with_capacity(32), |mut s, b| {
        use std::fmt::Write;
        let _ = write!(s, "{b:02x}");
        s
    })
}

/// Middleware: generate CSP nonce, inject into request extensions, add security headers to response.
pub async fn layer(mut request: Request, next: Next) -> Response {
    let nonce = gen_nonce();
    request.extensions_mut().insert(CspNonce(nonce.clone()));
    // LAN Cowork's Fleet Admin UI extracts the identical nonce through its own
    // neutral extension type, so `routes::lan_cowork_fleet_ui` never names
    // this module's `CspNonce` (S4a decoupling; see `FleetUiNonce`'s doc).
    request.extensions_mut().insert(FleetUiNonce(nonce.clone()));

    let mut response = next.run(request).await;
    let h = response.headers_mut();

    h.insert(
        HeaderName::from_static("x-content-type-options"),
        HeaderValue::from_static("nosniff"),
    );
    h.insert(
        HeaderName::from_static("x-frame-options"),
        HeaderValue::from_static("DENY"),
    );
    let csp = format!(
        "default-src 'self'; \
         script-src 'strict-dynamic' 'nonce-{nonce}' 'self'; \
         style-src 'self' 'unsafe-inline'; \
         img-src 'self' data: blob:; \
         connect-src 'self'; \
         font-src 'self'; \
         object-src 'none'; \
         base-uri 'self'; \
         form-action 'self'; \
         frame-ancestors 'none'"
    );
    if let Ok(v) = HeaderValue::from_str(&csp) {
        h.insert(HeaderName::from_static("content-security-policy"), v);
    }
    response
}
