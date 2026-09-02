#[cfg(test)]
mod tests {
    use super::super::*;
    use std::path::{Path, PathBuf};
    use std::time::SystemTime;

    #[test]
    fn test_editor_config_roundtrip() {
        let cfg = EditorConfig {
            path: r"C:\Program Files\GIMP 3\bin\gimp.exe".to_string(),
        };
        let serialized = serde_json::to_string(&cfg).unwrap();
        assert!(serialized.contains("gimp.exe"));
        let parsed: EditorConfig = serde_json::from_str(&serialized).unwrap();
        assert_eq!(parsed.path, cfg.path);
    }

    #[test]
    fn test_editor_config_default_empty() {
        let parsed: EditorConfig = serde_json::from_str("{}").unwrap();
        assert_eq!(parsed.path, "");
    }

    #[test]
    fn test_editor_config_unknown_field_tolerated() {
        let parsed: EditorConfig =
            serde_json::from_str(r#"{"path":"/usr/bin/gimp","auto_rescan":true}"#).unwrap();
        assert_eq!(parsed.path, "/usr/bin/gimp");
    }

    #[test]
    fn test_monitored_editor_files_dedupes() {
        let monitor = MonitoredEditorFiles::new();
        let p = PathBuf::from("/tmp/example.png");
        assert!(monitor.try_acquire(&p));
        assert!(!monitor.try_acquire(&p));
        monitor.release(&p);
        assert!(monitor.try_acquire(&p));
    }

    #[test]
    fn test_monitored_editor_files_different_paths_independent() {
        let monitor = MonitoredEditorFiles::new();
        assert!(monitor.try_acquire(Path::new("/tmp/a.png")));
        assert!(monitor.try_acquire(Path::new("/tmp/b.png")));
    }

    #[test]
    fn test_file_mtime_missing_returns_epoch() {
        let t = file_mtime(Path::new(
            "O:/yu_ai_manager/src-tauri/does_not_exist_12345.tmp",
        ));
        assert_eq!(t, SystemTime::UNIX_EPOCH);
    }

    #[test]
    fn test_file_mtime_real_file_is_after_epoch() {
        let t = file_mtime(Path::new("src/main.rs"));
        assert!(t > SystemTime::UNIX_EPOCH);
    }

    #[test]
    fn test_editor_closed_payload_serializes_flat() {
        let payload = EditorClosedPayload {
            path: "/tmp/x.png".into(),
            changed: true,
        };
        let js = serde_json::to_string(&payload).unwrap();
        assert!(js.contains("\"path\":\"/tmp/x.png\""));
        assert!(js.contains("\"changed\":true"));
    }
}
