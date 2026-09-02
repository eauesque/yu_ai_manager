//! Shared image-to-disk save utility.
//! Naming conventions mirror Python bridge_save.save_images().
use base64::{engine::general_purpose::STANDARD as B64, Engine};
use chrono::Local;
use std::path::{Path, PathBuf};

/// Save decoded images to disk.
///
/// `items`: `(base64_data, seed)` pairs.
/// `naming`: `"daily_folder"` | `"date_prefix"` | `"timestamp"`.
///
/// Returns `(saved_paths, error_messages)`.
pub fn save_images_to_disk(
    items: &[(&str, i64)],
    save_folder: &str,
    image_format: &str,
    naming: &str,
) -> (Vec<String>, Vec<String>) {
    let ext = match image_format {
        "jpg" | "jpeg" => "jpg",
        "webp" => "webp",
        _ => "png",
    };
    let now = Local::now();
    let unix_ts = now.timestamp();
    let date_str = now.format("%Y-%m-%d").to_string();
    let datetime_str = now.format("%Y-%m-%d_%H%M%S").to_string();

    let root = Path::new(save_folder);
    let mut saved = Vec::with_capacity(items.len());
    let mut errors = Vec::new();

    for (idx, (b64_data, seed)) in items.iter().enumerate() {
        let bytes = match B64.decode(b64_data.trim()) {
            Ok(b) => b,
            Err(e) => {
                errors.push(format!("image {idx}: base64 decode: {e}"));
                continue;
            }
        };

        let (dest_dir, stem): (PathBuf, String) = match naming {
            "daily_folder" => (root.join(&date_str), format!("{}_{}", seed, idx)),
            "date_prefix" => (root.to_path_buf(), format!("{}_{}_{}", datetime_str, seed, idx)),
            _ /* "timestamp" */ => (root.to_path_buf(), format!("{}_{}_{}", seed, unix_ts, idx)),
        };

        if let Err(e) = std::fs::create_dir_all(&dest_dir) {
            errors.push(format!("image {idx}: mkdir '{dest_dir:?}': {e}"));
            continue;
        }

        let path = unique_path(&dest_dir, &stem, ext);
        if let Err(e) = std::fs::write(&path, &bytes) {
            errors.push(format!("image {idx}: write '{path:?}': {e}"));
            continue;
        }
        saved.push(path.to_string_lossy().into_owned());
    }

    (saved, errors)
}

fn unique_path(dir: &Path, stem: &str, ext: &str) -> PathBuf {
    let candidate = dir.join(format!("{stem}.{ext}"));
    if !candidate.exists() {
        return candidate;
    }
    let mut n = 2u32;
    loop {
        let p = dir.join(format!("{stem}_{n}.{ext}"));
        if !p.exists() {
            return p;
        }
        n += 1;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use base64::{engine::general_purpose::STANDARD as B64, Engine};
    use tempfile::TempDir;

    fn dummy_b64() -> String {
        B64.encode(b"PNG_fake_bytes")
    }

    #[test]
    fn daily_folder_structure() {
        let dir = TempDir::new().unwrap();
        let b64 = dummy_b64();
        let (saved, errs) = save_images_to_disk(
            &[(&b64, 42)],
            dir.path().to_str().unwrap(),
            "png",
            "daily_folder",
        );
        assert!(errs.is_empty(), "{errs:?}");
        let path = PathBuf::from(&saved[0]);
        let parent_name = path
            .parent()
            .unwrap()
            .file_name()
            .unwrap()
            .to_string_lossy();
        assert_eq!(
            parent_name.len(),
            10,
            "date dir should be YYYY-MM-DD: {parent_name}"
        );
        assert_eq!(path.file_name().unwrap().to_string_lossy(), "42_0.png");
    }

    #[test]
    fn date_prefix_in_root() {
        let dir = TempDir::new().unwrap();
        let b64 = dummy_b64();
        let (saved, errs) = save_images_to_disk(
            &[(&b64, 99)],
            dir.path().to_str().unwrap(),
            "png",
            "date_prefix",
        );
        assert!(errs.is_empty());
        let name = PathBuf::from(&saved[0])
            .file_name()
            .unwrap()
            .to_string_lossy()
            .into_owned();
        assert!(name.contains("_99_0.png"), "got: {name}");
        assert_eq!(PathBuf::from(&saved[0]).parent().unwrap(), dir.path());
    }

    #[test]
    fn timestamp_naming() {
        let dir = TempDir::new().unwrap();
        let b64 = dummy_b64();
        let (saved, errs) = save_images_to_disk(
            &[(&b64, 1234)],
            dir.path().to_str().unwrap(),
            "png",
            "timestamp",
        );
        assert!(errs.is_empty());
        let name = PathBuf::from(&saved[0])
            .file_name()
            .unwrap()
            .to_string_lossy()
            .into_owned();
        assert!(
            name.starts_with("1234_") && name.ends_with("_0.png"),
            "{name}"
        );
    }

    #[test]
    fn collision_avoidance() {
        let dir = TempDir::new().unwrap();
        let b64 = dummy_b64();
        let b = b64.as_str();
        let (saved, errs) = save_images_to_disk(
            &[(b, 0), (b, 0), (b, 0)],
            dir.path().to_str().unwrap(),
            "png",
            "timestamp",
        );
        assert!(errs.is_empty());
        let unique: std::collections::HashSet<_> = saved.iter().collect();
        assert_eq!(unique.len(), 3, "expected 3 unique paths, got: {saved:?}");
    }

    #[test]
    fn bad_base64_produces_error() {
        let dir = TempDir::new().unwrap();
        let (saved, errs) = save_images_to_disk(
            &[("not-valid-base64!!!", 0)],
            dir.path().to_str().unwrap(),
            "png",
            "timestamp",
        );
        assert!(saved.is_empty());
        assert!(!errs.is_empty());
    }
}
