//! Shim over the upstream `yu_infer` library (eauesque/yu-hailo-infer).
//!
//! Kept byte-for-byte equivalent to the binary shipped upstream; the pinned
//! git revision in `crates/Cargo.toml` is what determines the sidecar's
//! behaviour. See `docs/superpowers/specs/2026-07-18-hailo-infer-repo-extraction-design.md`.

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt::init();
    yu_infer::run().await;
}
