#[cfg(test)]
mod tests {
    use std::path::Path;

    #[test]
    fn test_auto_pin_js_selectors_match_templates() {
        let manifest_dir = Path::new(env!("CARGO_MANIFEST_DIR"));
        let project_root = manifest_dir.parent().expect("Should have parent dir");

        let classic_path = project_root.join("core/web/pages_classic.py");
        let boss_path = project_root.join("core/web/pages_boss_render.py");

        let classic_src = std::fs::read_to_string(&classic_path)
            .unwrap_or_else(|_| panic!("Cannot read {:?}", classic_path));
        let boss_src = std::fs::read_to_string(&boss_path)
            .unwrap_or_else(|_| panic!("Cannot read {:?}", boss_path));

        assert!(
            classic_src.contains(r#"name="_csrf_token""#),
            "Classic template must have _csrf_token field"
        );
        assert!(
            boss_src.contains(r#"name="_csrf_token""#),
            "Boss template must have _csrf_token field"
        );
        assert!(
            classic_src.contains(r#"action="/_pin_check""#),
            "Classic template must POST to /_pin_check"
        );
        assert!(
            boss_src.contains(r#"action="/_pin_check""#),
            "Boss template must POST to /_pin_check"
        );
        assert!(
            classic_src.contains(r#"name="pin""#),
            "Classic template must have PIN input named 'pin'"
        );
        assert!(
            boss_src.contains(r#"name="pin""#),
            "Boss template must have PIN input named 'pin'"
        );
        assert!(
            classic_src.contains(r#"id="lockPin""#),
            "Classic lock template must have lockPin input for Tauri auto-unlock"
        );
        assert!(
            boss_src.contains(r#"id="lockPin""#) || boss_src.contains(r#"id='lockPin'"#),
            "Boss lock template must have lockPin input for Tauri auto-unlock"
        );

        let auth_path = project_root.join("core/web/auth_routes.py");
        let auth_src = std::fs::read_to_string(&auth_path)
            .unwrap_or_else(|_| panic!("Cannot read {:?}", auth_path));
        assert!(
            auth_src.contains("'_csrf_token'"),
            "auth_routes.py must reference '_csrf_token' field"
        );
    }

    #[test]
    fn test_auto_pin_js_in_main_runtime_rs() {
        let main_runtime_rs = include_str!("main_runtime.rs");

        assert!(
            main_runtime_rs.contains(r#"input[name="_csrf_token"]"#),
            "main_runtime.rs must query for _csrf_token input"
        );
        assert!(
            main_runtime_rs.contains(r#"form.action="/_pin_check""#),
            "main_runtime.rs auto-PIN JS must POST to /_pin_check"
        );
        assert!(
            main_runtime_rs.contains(r#"f1.name="pin""#),
            "main_runtime.rs auto-PIN JS must set field name to 'pin'"
        );
        assert!(
            main_runtime_rs.contains(r#"f2.name="_csrf_token""#),
            "main_runtime.rs auto-PIN JS must submit _csrf_token field"
        );
        assert!(
            main_runtime_rs.contains(r#"document.getElementById('lockPin')"#),
            "main_runtime.rs auto-PIN JS must detect QuickLock lockPin element"
        );
        assert!(
            main_runtime_rs.contains(r#"/api/lock/unlock"#),
            "main_runtime.rs auto-PIN JS must call /api/lock/unlock endpoint"
        );
    }

    #[test]
    fn test_close_to_tray_prevents_default() {
        let main_runtime_rs = include_str!("main_runtime.rs");
        assert!(
            main_runtime_rs.contains("CloseRequested")
                && main_runtime_rs.contains("api.prevent_close()"),
            "CloseRequested handler must call api.prevent_close() for close-to-tray"
        );
        assert!(
            main_runtime_rs.contains("window.hide()"),
            "close-to-tray must hide the window after prevent_close"
        );
    }
}
