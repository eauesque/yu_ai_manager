use std::path::{Path, PathBuf};
use std::process::Command;

/// Detect the Python executable (venv preferred)
pub fn find_python(project_root: &Path) -> Result<PathBuf, String> {
    let candidates: Vec<PathBuf> = if cfg!(target_os = "windows") {
        vec![
            project_root.join("python").join("python.exe"),
            project_root.join("venv/Scripts/python.exe"),
            project_root.join("venv\\Scripts\\python.exe"),
        ]
    } else {
        vec![
            project_root.join("python/bin/python3"),
            project_root.join("venv/bin/python"),
        ]
    };

    for candidate in &candidates {
        if candidate.exists() {
            return Ok(candidate.clone());
        }
    }

    let system_python = if cfg!(target_os = "windows") {
        "python"
    } else {
        "python3"
    };

    let check = Command::new(system_python).arg("--version").output();

    match check {
        Ok(output) if output.status.success() => Ok(PathBuf::from(system_python)),
        _ => Err(format!(
            "Python が見つかりません。\n\n\
             venv が必要です。以下のコマンドで作成してください:\n\n\
             python -m venv venv\n\
             venv\\Scripts\\activate  (Windows)\n\
             uv pip install -r requirements.txt\n\n\
             検索したパス:\n{}",
            candidates
                .iter()
                .map(|p| format!("  - {}", p.display()))
                .collect::<Vec<_>>()
                .join("\n")
        )),
    }
}

/// Generate a random 16-character hex PIN using cryptographic randomness.
pub fn generate_random_pin() -> String {
    let mut buf = [0u8; 8];
    getrandom::getrandom(&mut buf).expect("getrandom failed");
    buf.iter().map(|b| format!("{:02x}", b)).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_generate_random_pin_length() {
        let pin = generate_random_pin();
        assert_eq!(pin.len(), 16, "PIN should be 16 hex chars: {}", pin);
    }

    #[test]
    fn test_generate_random_pin_hex_format() {
        let pin = generate_random_pin();
        assert!(
            pin.chars().all(|c| c.is_ascii_hexdigit()),
            "PIN should be hex: {}",
            pin
        );
    }

    #[test]
    fn test_generate_random_pin_uniqueness() {
        let pins: Vec<String> = (0..100).map(|_| generate_random_pin()).collect();
        let mut unique = pins.clone();
        unique.sort();
        unique.dedup();
        assert!(
            unique.len() > 90,
            "Expected mostly unique PINs, got {} unique out of 100",
            unique.len()
        );
    }

    #[test]
    fn test_find_python_with_real_project_root() {
        let manifest_dir = Path::new(env!("CARGO_MANIFEST_DIR"));
        if let Some(project_root) = manifest_dir.parent() {
            let result = find_python(project_root);
            match result {
                Ok(python_path) => {
                    let path_str = python_path.to_string_lossy().to_lowercase();
                    assert!(
                        path_str.contains("python"),
                        "Python path should contain 'python': {:?}",
                        python_path
                    );
                }
                Err(e) => {
                    assert!(e.contains("Python"), "Error should mention Python: {}", e);
                    assert!(e.contains("venv"), "Error should mention venv: {}", e);
                }
            }
        }
    }

    #[test]
    fn test_find_python_nonexistent_root() {
        let fake_root = Path::new("/nonexistent/path/to/project");
        let result = find_python(fake_root);
        match result {
            Ok(p) => {
                let s = p.to_string_lossy().to_lowercase();
                assert!(s.contains("python"));
            }
            Err(e) => {
                assert!(e.contains("Python"), "Error should mention Python");
            }
        }
    }

    #[test]
    fn test_generate_random_pin_crypto_quality() {
        let pins: Vec<String> = (0..50).map(|_| generate_random_pin()).collect();
        let mut unique = pins.clone();
        unique.sort();
        unique.dedup();
        assert_eq!(
            unique.len(),
            50,
            "All 50 crypto PINs should be unique, got {} unique",
            unique.len()
        );
    }
}
