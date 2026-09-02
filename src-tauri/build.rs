fn main() {
    // Ensure bundle.zip exists so Tauri config validation passes.
    // The real zip is created by prepare-tauri-bundle.py before cargo tauri build.
    let bundle_zip = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("bundle.zip");
    if !bundle_zip.exists() {
        // Write a minimal valid zip (empty archive) as a placeholder.
        // 22 bytes = ZIP end-of-central-directory record with no entries.
        let empty_zip: &[u8] = &[
            0x50, 0x4B, 0x05, 0x06, // End of central dir signature
            0x00, 0x00, // Disk number
            0x00, 0x00, // Disk with central dir
            0x00, 0x00, // Entries on disk
            0x00, 0x00, // Total entries
            0x00, 0x00, 0x00, 0x00, // Central dir size
            0x00, 0x00, 0x00, 0x00, // Central dir offset
            0x00, 0x00, // Comment length
        ];
        std::fs::write(&bundle_zip, empty_zip).ok();
    }

    // Ensure yu-server.exe exists so Tauri config validation passes.
    // The real binary is copied here by scripts/prepare-tauri-bundle.py's
    // stage_yu_server() before `cargo tauri build`. This placeholder is not a
    // valid executable (no PE/ELF header): if it is ever the file that ships,
    // find_yu_server_bin() still finds it, but spawning it fails immediately,
    // which is exactly the Err path main.rs already degrades from -- see
    // yu_server.rs's `fallback_tests::a_placeholder_binary_is_recoverable_not_fatal`.
    // Its content must stay byte-identical to PLACEHOLDER_MARKER in
    // scripts/prepare-tauri-bundle.py, which refuses to ship this marker.
    let yu_server_bin = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("yu-server.exe");
    if !yu_server_bin.exists() {
        let placeholder: &[u8] = b"YU_AI_MANAGER_PLACEHOLDER_NOT_A_REAL_BINARY\n";
        std::fs::write(&yu_server_bin, placeholder).ok();
        println!("cargo:warning=yu-server.exe placeholder written -- run scripts/prepare-tauri-bundle.py before releasing, or the installer ships a non-executable stub");
    }

    tauri_build::build()
}
