// Project root detection for YU AI Manager Tauri wrapper.
//
// 4-stage detection:
//   Stage 0: bundle/ dir next to exe (NSIS installed / self-contained build)
//   Stage 1: near exe (portable or dev build)
//   Stage 1.5: build-time CARGO_MANIFEST_DIR
//   Stage 2: saved config (%APPDATA%/yu-ai-manager/project_root.json)
//   Stage 3: folder selection dialog

use std::io;
use std::path::{Path, PathBuf};

/// Stage 0: bundle/ directory near the exe (self-contained NSIS installer)
///
/// Checks locations in priority order:
///   1. exe_dir/bundle/      — already extracted, or dev build
///   2. exe_dir/bundle.zip   — NSIS install (first run: extract zip, then use bundle/)
///   3. exe_dir/resources/bundle/ — legacy Tauri path (kept for compatibility)
pub fn detect_bundled_project_root() -> Option<PathBuf> {
    let exe_path = std::env::current_exe().ok()?;
    let exe_dir = exe_path.parent()?;

    // 1. bundle/ already extracted (subsequent runs or dev build)
    let bundle_dir = exe_dir.join("bundle");
    if bundle_dir.join("web_ui.py").exists() {
        return Some(bundle_dir);
    }

    // 2. bundle.zip present (NSIS installer first run — extract in-place)
    let bundle_zip = exe_dir.join("bundle.zip");
    if bundle_zip.exists() {
        eprintln!("[INFO] First run: extracting bundle.zip...");
        match extract_bundle_zip(&bundle_zip, exe_dir) {
            Ok(()) => {
                if bundle_dir.join("web_ui.py").exists() {
                    // Remove zip after successful extraction to reclaim ~450 MB
                    let _ = std::fs::remove_file(&bundle_zip);
                    eprintln!("[INFO] bundle.zip extracted and removed.");
                    return Some(bundle_dir);
                }
                eprintln!("[WARN] bundle.zip extracted but web_ui.py not found.");
            }
            Err(e) => {
                eprintln!("[ERROR] Failed to extract bundle.zip: {}", e);
            }
        }
    }

    // 3. resources/bundle/ (legacy path — kept for compatibility)
    let resources_bundle = exe_dir.join("resources").join("bundle");
    if resources_bundle.join("web_ui.py").exists() {
        return Some(resources_bundle);
    }

    None
}

/// Extract bundle.zip into dest_dir, preserving internal directory structure.
/// Entries in the zip are expected to start with "bundle/" so that the result
/// is dest_dir/bundle/python/python.exe etc.
fn extract_bundle_zip(zip_path: &Path, dest_dir: &Path) -> Result<(), String> {
    let file =
        std::fs::File::open(zip_path).map_err(|e| format!("Cannot open bundle.zip: {}", e))?;
    let mut archive =
        zip::ZipArchive::new(file).map_err(|e| format!("Cannot read bundle.zip: {}", e))?;

    for i in 0..archive.len() {
        let mut entry = archive
            .by_index(i)
            .map_err(|e| format!("Zip entry {} error: {}", i, e))?;

        // Use mangled_name() to avoid path traversal
        let out_path = dest_dir.join(entry.mangled_name());

        if entry.is_dir() {
            std::fs::create_dir_all(&out_path)
                .map_err(|e| format!("Cannot create dir {:?}: {}", out_path, e))?;
        } else {
            if let Some(parent) = out_path.parent() {
                std::fs::create_dir_all(parent)
                    .map_err(|e| format!("Cannot create parent dir {:?}: {}", parent, e))?;
            }
            let mut out_file = std::fs::File::create(&out_path)
                .map_err(|e| format!("Cannot create file {:?}: {}", out_path, e))?;
            io::copy(&mut entry, &mut out_file)
                .map_err(|e| format!("Cannot write file {:?}: {}", out_path, e))?;
        }
    }

    Ok(())
}

/// Stage 1: Detect web_ui.py near the exe
pub fn detect_project_root_near_exe() -> Option<PathBuf> {
    let exe_path = std::env::current_exe().ok()?;
    let exe_dir = exe_path.parent()?;

    // Same directory as exe (portable build)
    if exe_dir.join("web_ui.py").exists() {
        return Some(exe_dir.to_path_buf());
    }

    // Development: src-tauri/target/release/ -> 3 levels up
    if let Some(ancestor) = exe_dir.ancestors().nth(3) {
        if ancestor.join("web_ui.py").exists() {
            return Some(ancestor.to_path_buf());
        }
    }

    None
}

/// Stage 1.5: Check the project root from build time.
pub fn detect_project_root_build_time() -> Option<PathBuf> {
    let manifest_dir = Path::new(env!("CARGO_MANIFEST_DIR"));
    let project_root = manifest_dir.parent()?;
    if project_root.join("web_ui.py").exists() {
        Some(project_root.to_path_buf())
    } else {
        None
    }
}

/// Stage 3: Ask for the project root via a folder selection dialog (with retry)
pub fn ask_project_root_via_dialog(log_path: &Path) -> Result<PathBuf, String> {
    loop {
        let folder = rfd::FileDialog::new()
            .set_title("YU AI Manager - web_ui.py のあるプロジェクトフォルダを選択")
            .pick_folder();

        match folder {
            Some(path) if path.join("web_ui.py").exists() => {
                crate::app_dirs::save_project_root(&path);
                log!(
                    log_path,
                    "プロジェクトルートをダイアログで選択: {}",
                    path.display()
                );
                return Ok(path);
            }
            Some(path) => {
                crate::logging::show_message_box(
                    "YU AI Manager",
                    &format!(
                        "選択したフォルダに web_ui.py が見つかりません。\n\n\
                         選択: {}\n\n\
                         YU AI Manager のプロジェクトフォルダ\n\
                         (web_ui.py が含まれるディレクトリ) を選択してください。",
                        path.display()
                    ),
                    false,
                );
            }
            None => {
                return Err("プロジェクトフォルダが選択されませんでした。\n\n\
                     YU AI Manager を起動するには、web_ui.py のある\n\
                     プロジェクトフォルダを選択する必要があります。"
                    .to_string());
            }
        }
    }
}

/// Detect the project root in 4 stages.
pub fn resolve_project_root(log_path: &Path) -> Result<PathBuf, String> {
    // Stage 0: Bundled version (self-contained NSIS installer)
    if let Some(root) = detect_bundled_project_root() {
        log!(
            log_path,
            "プロジェクトルート (バンドル版): {}",
            root.display()
        );
        return Ok(root);
    }

    // Stage 1: Near the exe
    if let Some(root) = detect_project_root_near_exe() {
        log!(log_path, "プロジェクトルート (exe近傍): {}", root.display());
        return Ok(root);
    }
    log!(
        log_path,
        "exe 近傍に web_ui.py が見つからないため、ビルド時パスを確認..."
    );

    // Stage 1.5: Build-time path
    if let Some(root) = detect_project_root_build_time() {
        log!(
            log_path,
            "プロジェクトルート (ビルド時パス): {}",
            root.display()
        );
        crate::app_dirs::save_project_root(&root);
        return Ok(root);
    }
    log!(log_path, "ビルド時パスにもなし。保存設定を確認...");

    // Stage 2: Saved config
    if let Some(root) = crate::app_dirs::load_saved_project_root() {
        log!(
            log_path,
            "保存設定からプロジェクトルートを復元: {}",
            root.display()
        );
        return Ok(root);
    }
    log!(log_path, "保存設定なし。フォルダ選択ダイアログを表示...");

    // Stage 3: Folder selection dialog
    ask_project_root_via_dialog(log_path)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_detect_project_root_near_exe_without_web_ui() {
        // If web_ui.py doesn't exist near the exe, returns None
        // (in test context the exe is in target/debug/deps/ without web_ui.py)
        // This just verifies it doesn't panic.
        let _ = detect_project_root_near_exe();
    }

    #[test]
    fn test_detect_bundled_project_root_without_bundle() {
        // Without a bundle/ directory containing web_ui.py, returns None
        let result = detect_bundled_project_root();
        // In a development build, bundle/ dir shouldn't exist next to exe
        // Accept both None and Some (if dev environment happens to have it)
        let _ = result;
    }

    #[test]
    fn test_detect_bundled_project_root_returns_none_in_test_env() {
        // In the test environment neither exe_dir/bundle/ nor exe_dir/resources/bundle/
        // contains web_ui.py, so the function must return None (not panic).
        // This verifies both paths are checked without triggering a false positive.
        let result = detect_bundled_project_root();
        assert!(
            result.is_none(),
            "detect_bundled_project_root should return None in test env \
             (no bundle/ or resources/bundle/ next to test exe)"
        );
    }

    #[test]
    fn test_detect_project_root_build_time() {
        // In development, CARGO_MANIFEST_DIR/../web_ui.py exists
        let result = detect_project_root_build_time();
        let manifest_dir = Path::new(env!("CARGO_MANIFEST_DIR"));
        let expected_root = manifest_dir.parent().unwrap();
        if expected_root.join("web_ui.py").exists() {
            assert_eq!(result.unwrap(), expected_root);
        } else {
            assert!(result.is_none());
        }
    }
}
