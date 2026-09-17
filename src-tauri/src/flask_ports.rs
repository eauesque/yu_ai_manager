use std::net::TcpListener;
use std::time::{Duration, Instant};

pub fn find_free_port() -> Result<u16, String> {
    let listener = TcpListener::bind("127.0.0.1:0")
        .map_err(|e| format!("空きポートの確保に失敗しました: {}", e))?;
    let port = listener
        .local_addr()
        .map_err(|e| format!("ポートアドレスの取得に失敗しました: {}", e))?
        .port();
    Ok(port)
}

/// Wait for the Flask server to start (up to timeout)
pub fn wait_for_server(port: u16, timeout: Duration) -> bool {
    let start = Instant::now();
    while start.elapsed() < timeout {
        if TcpListener::bind(("127.0.0.1", port)).is_err() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(300));
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_find_free_port_returns_valid_port() {
        let port = find_free_port().expect("Should find a free port");
        assert!(port > 0, "Port should be > 0");
        assert!(port > 1024, "Port should be unprivileged (> 1024)");
    }

    #[test]
    fn test_find_free_port_unique() {
        let p1 = find_free_port().unwrap();
        let _p2 = find_free_port().unwrap();
        let _listener = TcpListener::bind(("127.0.0.1", p1)).ok();
        let p3 = find_free_port().unwrap();
        assert_ne!(p1, p3, "Should return different port when first is bound");
    }

    #[test]
    fn test_wait_for_server_immediate_available() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        let result = wait_for_server(port, Duration::from_secs(2));
        assert!(result, "Should detect server on bound port");
        drop(listener);
    }

    #[test]
    fn test_wait_for_server_timeout() {
        let port = find_free_port().unwrap();
        let start = Instant::now();
        let result = wait_for_server(port, Duration::from_millis(600));
        assert!(!result, "Should timeout on free port");
        assert!(
            start.elapsed() >= Duration::from_millis(500),
            "Should have waited before timing out"
        );
    }
}
