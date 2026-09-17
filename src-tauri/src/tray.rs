// System tray management and desktop notification injection.

use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::Manager;

/// Build and register the tray icon, menu, and event handlers.
///
/// Menu items (minimum viable for v1):
///   - Show Window  → brings the hidden window back to the foreground
///   - Hide Window  → sends the window to the tray without touching Flask
///   - ---
///   - Quit         → kills Flask and exits the app cleanly
///
/// Left-clicking the tray icon toggles the window visibility.
///
/// Notifications are driven from the WebView side (see `NOTIFICATION_JS`) to
/// avoid a Rust-side SSE client. This keeps tray v1 scope-minimal and lets the
/// existing session-cookie auth flow handle stream access transparently.
pub fn build_system_tray(app: &tauri::AppHandle) -> tauri::Result<()> {
    let show_item = MenuItem::with_id(app, "tray_show", "Show Window", true, None::<&str>)?;
    let hide_item = MenuItem::with_id(app, "tray_hide", "Hide Window", true, None::<&str>)?;
    let sep = PredefinedMenuItem::separator(app)?;
    let quit_item = MenuItem::with_id(app, "tray_quit", "Quit", true, None::<&str>)?;

    let menu = Menu::with_items(app, &[&show_item, &hide_item, &sep, &quit_item])?;

    let _tray = TrayIconBuilder::with_id("yu-ai-manager-tray")
        .icon(app.default_window_icon().cloned().ok_or_else(|| {
            tauri::Error::Anyhow(anyhow::anyhow!("default window icon unavailable for tray"))
        })?)
        .tooltip("YU AI Manager")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app: &tauri::AppHandle, event: tauri::menu::MenuEvent| {
            match event.id.as_ref() {
                "tray_show" => {
                    if let Some(window) = app.get_webview_window("main") {
                        let _ = window.show();
                        let _ = window.unminimize();
                        let _ = window.set_focus();
                    }
                }
                "tray_hide" => {
                    if let Some(window) = app.get_webview_window("main") {
                        let _ = window.hide();
                    }
                }
                "tray_quit" => {
                    // Kill Flask child before app exit so the port is freed.
                    if let Some(state) = app.try_state::<crate::flask::FlaskProcess>() {
                        if let Ok(mut guard) = state.0.lock() {
                            if let Some(mut child) = guard.take() {
                                let _ = child.kill();
                                let _ = child.wait();
                            }
                        }
                    }
                    app.exit(0);
                }
                _ => {}
            }
        })
        .on_tray_icon_event(
            |tray: &tauri::tray::TrayIcon, event: tauri::tray::TrayIconEvent| {
                if let TrayIconEvent::Click {
                    button: MouseButton::Left,
                    button_state: MouseButtonState::Up,
                    ..
                } = event
                {
                    let app = tray.app_handle();
                    if let Some(window) = app.get_webview_window("main") {
                        // Toggle: if visible & focused, hide; otherwise show + focus.
                        let is_visible = window.is_visible().unwrap_or(false);
                        if is_visible {
                            let _ = window.hide();
                        } else {
                            let _ = window.show();
                            let _ = window.unminimize();
                            let _ = window.set_focus();
                        }
                    }
                }
            },
        )
        .build(app)?;

    Ok(())
}

/// JavaScript injected into the WebView after Flask auto-login to subscribe to
/// SSE and raise OS notifications for scan/generation completion events.
///
/// Implementation notes:
///   - Waits for login by polling every 500 ms until the PIN form is gone
///   - Uses the Web Notification API; WebView2 / WKWebView forward this to the
///     host OS natively, so no tauri-plugin-notification is required for v1
///   - Guards against duplicate EventSource connections across navigations via
///     `window.__YU_DESKTOP_NOTIFY_SUBSCRIBED__`
///   - Filters on `types=scan.complete,generation.complete` — the router side
///     will drop anything else, so the main-frame handler only sees the two
///     completion events we care about
///   - Notifications are suppressed when the document is visible so the user
///     isn't spammed with duplicates of what they can already see on screen
pub const NOTIFICATION_JS: &str = r#"(function(){
    if (window.__YU_DESKTOP_NOTIFY_SUBSCRIBED__) return;
    function hasPinForm(){
        return !!document.querySelector('input[name="_csrf_token"],input[name="csrf_token"]');
    }
    function hasLockScreen(){ return !!document.getElementById('lockPin'); }
    var waitTries = 0;
    var waitIv = setInterval(function(){
        waitTries++;
        if (hasPinForm() || hasLockScreen()){
            if (waitTries > 60) clearInterval(waitIv);
            return;
        }
        clearInterval(waitIv);
        subscribe();
    }, 500);

    function subscribe(){
        if (window.__YU_DESKTOP_NOTIFY_SUBSCRIBED__) return;
        if (!('Notification' in window)) return;
        window.__YU_DESKTOP_NOTIFY_SUBSCRIBED__ = true;
        var grant = function(){
            try {
                var es = new EventSource('/api/events/stream?types=scan.complete,generation.complete');
                es.onmessage = function(ev){
                    if (document.visibilityState === 'visible') return;
                    var payload = {};
                    try { payload = JSON.parse(ev.data || '{}'); } catch(e){}
                    var type = payload.type || '';
                    var title = 'YU AI Manager';
                    var body = '';
                    if (type === 'scan.complete'){
                        title = 'Scan complete';
                        var added = payload.added || payload.new_files || 0;
                        var updated = payload.updated || 0;
                        body = 'Scan finished (' + added + ' new, ' + updated + ' updated).';
                    } else if (type === 'generation.complete'){
                        title = 'Generation complete';
                        var bridge = payload.bridge || payload.source || 'bridge';
                        body = bridge + ' finished generating an image.';
                    } else {
                        return;
                    }
                    try { new Notification(title, { body: body, silent: false }); } catch(e){}
                };
                es.onerror = function(){
                    // EventSource auto-reconnects; swallow transient errors silently.
                };
            } catch(e){}
        };
        if (Notification.permission === 'granted'){
            grant();
        } else if (Notification.permission !== 'denied'){
            Notification.requestPermission().then(function(p){ if (p === 'granted') grant(); });
        }
    }
})();"#;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tray_menu_item_ids_match_handlers() {
        let tray_rs = include_str!("tray.rs");
        for id in ["tray_show", "tray_hide", "tray_quit"] {
            assert!(
                tray_rs.contains(&format!("\"{}\"", id)),
                "tray.rs must reference tray menu id '{}'",
                id
            );
        }
        // Router arms exist for each id
        assert!(tray_rs.contains("\"tray_show\" =>"));
        assert!(tray_rs.contains("\"tray_hide\" =>"));
        assert!(tray_rs.contains("\"tray_quit\" =>"));
    }

    #[test]
    fn test_notification_js_shape() {
        let js = NOTIFICATION_JS;
        assert!(
            js.contains("__YU_DESKTOP_NOTIFY_SUBSCRIBED__"),
            "notification JS must guard against duplicate subscription"
        );
        assert!(js.contains("/api/events/stream"));
        assert!(js.contains("scan.complete"));
        assert!(js.contains("generation.complete"));
        assert!(
            js.contains("document.visibilityState"),
            "notification JS should suppress when the document is visible"
        );
        assert!(js.contains("Notification.permission"));
        assert!(js.contains("new Notification("));
    }
}
