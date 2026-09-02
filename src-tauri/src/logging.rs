// Logging utilities for YU AI Manager Tauri wrapper.

use std::fs::OpenOptions;
use std::io::Write;
use std::path::Path;

/// Append a message to the log file (Unix: 0o600 permissions)
pub fn log_to_file(log_path: &Path, msg: &str) {
    let mut opts = OpenOptions::new();
    opts.create(true).append(true);

    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        opts.mode(0o600);
    }

    if let Ok(mut f) = opts.open(log_path) {
        let now = chrono_lite_now();
        let _ = writeln!(f, "[{}] {}", now, msg);
    }
}

/// Simple timestamp (no external crate)
pub fn chrono_lite_now() -> String {
    use std::time::SystemTime;
    let d = SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .unwrap_or_default();
    let secs = d.as_secs();
    let h = (secs % 86400) / 3600;
    let m = (secs % 3600) / 60;
    let s = secs % 60;
    format!("{:02}:{:02}:{:02}", h, m, s)
}

/// Show a Windows MessageBox (used for both warnings and errors)
#[cfg(windows)]
pub fn show_message_box(title: &str, message: &str, is_error: bool) {
    use windows::core::PCWSTR;
    use windows::Win32::UI::WindowsAndMessaging::{
        MessageBoxW, MB_ICONERROR, MB_ICONWARNING, MB_OK,
    };
    fn to_wide(s: &str) -> Vec<u16> {
        s.encode_utf16().chain(std::iter::once(0)).collect()
    }
    let title_w = to_wide(title);
    let msg_w = to_wide(message);
    let icon = if is_error {
        MB_ICONERROR
    } else {
        MB_ICONWARNING
    };
    unsafe {
        MessageBoxW(
            None,
            PCWSTR(msg_w.as_ptr()),
            PCWSTR(title_w.as_ptr()),
            MB_OK | icon,
        );
    }
}

#[cfg(not(windows))]
pub fn show_message_box(_title: &str, message: &str, _is_error: bool) {
    eprintln!("[dialog] {}", message);
}

pub fn show_error_and_exit(title: &str, message: &str, log_path: &Path) -> ! {
    log_to_file(log_path, &format!("FATAL: {}", message));
    show_message_box(title, message, true);
    std::process::exit(1);
}

/// Helper macro for logging to file + stderr output.
/// `#[macro_export]` puts this at the crate root so all modules can use `log!`.
#[macro_export]
macro_rules! log {
    ($log_path:expr, $($arg:tt)*) => {{
        let msg = format!($($arg)*);
        eprintln!("[tauri] {}", msg);
        $crate::logging::log_to_file($log_path, &msg);
    }};
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_log_to_file_creates_and_appends() {
        let dir = std::env::temp_dir().join("yu_tauri_test_log");
        let _ = std::fs::create_dir_all(&dir);
        let log_path = dir.join("test.log");
        let _ = std::fs::remove_file(&log_path);

        log_to_file(&log_path, "first line");
        log_to_file(&log_path, "second line");

        let content = std::fs::read_to_string(&log_path).unwrap();
        assert!(content.contains("first line"));
        assert!(content.contains("second line"));
        let _ = std::fs::remove_file(&log_path);
    }

    #[test]
    fn test_chrono_lite_now_format() {
        let ts = chrono_lite_now();
        // Format should be HH:MM:SS
        assert_eq!(ts.len(), 8, "timestamp must be 8 chars (HH:MM:SS)");
        assert_eq!(&ts[2..3], ":", "first colon at position 2");
        assert_eq!(&ts[5..6], ":", "second colon at position 5");
    }
}
