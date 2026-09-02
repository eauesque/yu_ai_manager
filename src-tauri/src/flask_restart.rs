use std::path::PathBuf;
use std::process::Child;
use std::sync::Mutex;
use std::time::Duration;

use tauri::Manager;

use super::{generate_random_pin, start_flask, wait_for_server};

pub struct FlaskProcess(pub Mutex<Option<Child>>);

pub struct FlaskStartupParams {
    pub project_root: PathBuf,
    pub python: PathBuf,
    pub port: u16,
    pub log_path: PathBuf,
}

/// One-time token for authenticating IPC restart commands.
pub struct RestartToken(pub String);

#[tauri::command]
pub async fn restart_flask_server(
    app: tauri::AppHandle,
    window: tauri::WebviewWindow,
    token: String,
) -> Result<String, String> {
    let expected = app.state::<RestartToken>();
    if token != expected.0 {
        return Err("Invalid restart token".into());
    }
    let params = app.state::<FlaskStartupParams>();
    let flask_state = app.state::<FlaskProcess>();

    if let Ok(mut guard) = flask_state.0.lock() {
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            let _ = child.wait();
            crate::logging::log_to_file(&params.log_path, "Flask process killed for restart");
        }
    }

    std::thread::sleep(Duration::from_millis(500));

    let new_pin = generate_random_pin();
    crate::logging::log_to_file(&params.log_path, "New auto-PIN generated for restart");

    let child = start_flask(
        &params.project_root,
        &params.python,
        params.port,
        &new_pin,
        &params.log_path,
    )
    .map_err(|e| format!("Flask restart failed: {}", e))?;

    crate::logging::log_to_file(
        &params.log_path,
        &format!("Flask restarted (PID: {})", child.id()),
    );

    if let Ok(mut guard) = flask_state.0.lock() {
        *guard = Some(child);
    }

    if !wait_for_server(params.port, Duration::from_secs(60)) {
        return Err("Flask server did not start within 60 seconds".into());
    }
    crate::logging::log_to_file(&params.log_path, "Flask server confirmed after restart");

    let url_str = format!("http://127.0.0.1:{}", params.port);
    let url: tauri::Url = url_str
        .parse()
        .map_err(|e| format!("URL parse error: {}", e))?;
    window
        .navigate(url)
        .map_err(|e| format!("Navigate error: {}", e))?;

    let pin_js = format!(
        r#"(function(){{
            var pin={};
            var misses=0;
            var iv=setInterval(function(){{
                var lockEl=document.getElementById('lockPin');
                if(lockEl){{
                    misses=0;
                    clearInterval(iv);
                    function doUnlock(){{
                        document.removeEventListener('click',doUnlock);
                        document.removeEventListener('keydown',doUnlock);
                        fetch('/api/lock/unlock',{{
                            method:'POST',
                            headers:{{'Content-Type':'application/json','X-Requested-With':'XMLHttpRequest'}},
                            body:JSON.stringify({{pin:pin}})
                        }}).then(function(r){{if(r.ok)window.location.reload();}});
                    }}
                    document.addEventListener('click',doUnlock);
                    document.addEventListener('keydown',doUnlock);
                    return;
                }}
                var csrfEl=document.querySelector('input[name="_csrf_token"],input[name="csrf_token"]');
                if(!csrfEl){{
                    misses++;
                    if(misses>6)clearInterval(iv);
                    return;
                }}
                misses=0;
                clearInterval(iv);
                var form=document.createElement("form");
                form.method="POST";
                form.action="/_pin_check";
                form.style.display="none";
                var f1=document.createElement("input");f1.name="pin";f1.value=pin;form.appendChild(f1);
                var f2=document.createElement("input");f2.name="_csrf_token";f2.value=csrfEl.value;form.appendChild(f2);
                document.body.appendChild(form);
                form.submit();
            }},500);
        }})();"#,
        serde_json::to_string(&new_pin).map_err(|e| format!("PIN encode error: {}", e))?
    );
    std::thread::sleep(Duration::from_millis(1500));
    let _ = window.eval(&pin_js);

    Ok("Restart complete".into())
}
