/// Returns the PIN input page HTML.
/// `error`: error message shown to user (empty = hidden)
/// `next_url`: redirect destination after successful auth
pub fn pin_page(error: &str, next_url: &str) -> String {
    let error_html = if error.is_empty() {
        String::new()
    } else {
        format!(r#"<p class="error">{}</p>"#, html_escape(error))
    };
    let next_attr = html_escape(next_url);
    format!(
        r#"<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PIN 認証</title>
<style>
body{{font-family:sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;background:#f5f5f5}}
.box{{background:#fff;padding:2rem;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.1);width:320px}}
h1{{font-size:1.2rem;margin:0 0 1rem}}
input[type=password]{{width:100%;padding:.5rem;font-size:1rem;border:1px solid #ccc;border-radius:4px;box-sizing:border-box}}
button{{width:100%;margin-top:.75rem;padding:.6rem;font-size:1rem;background:#333;color:#fff;border:none;border-radius:4px;cursor:pointer}}
.error{{color:#c00;font-size:.9rem;margin:.5rem 0 0}}
</style>
</head>
<body>
<div class="box">
<h1>PIN 認証</h1>
<form method="post" action="/_pin_check">
<input type="hidden" name="next" value="{next_attr}">
<input type="password" name="pin" placeholder="PIN を入力" autofocus autocomplete="current-password">
<button type="submit">認証</button>
{error_html}
</form>
</div>
</body>
</html>"#
    )
}

/// Returns the lock screen HTML.
pub fn lock_page() -> &'static str {
    r#"<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ロック中</title>
<style>
body{font-family:sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;background:#1a1a1a;color:#eee}
.box{text-align:center;padding:2rem}
h1{font-size:2rem;margin:0 0 .5rem}
p{color:#aaa}
</style>
</head>
<body>
<div class="box">
<h1>&#x1F512; ロック中</h1>
<p>管理者が画面をロックしています。</p>
</div>
</body>
</html>"#
}

pub(crate) fn html_escape(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#39;")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pin_page_contains_form() {
        let html = pin_page("", "/");
        assert!(html.contains(r#"action="/_pin_check""#));
        assert!(html.contains(r#"type="password""#));
    }

    #[test]
    fn pin_page_shows_error() {
        let html = pin_page("PINが違います", "/");
        assert!(html.contains("PINが違います"));
    }

    #[test]
    fn pin_page_escapes_xss() {
        let html = pin_page("<script>alert(1)</script>", "/");
        assert!(!html.contains("<script>"));
        assert!(html.contains("&lt;script&gt;"));
    }

    #[test]
    fn pin_page_next_url_escaped() {
        let html = pin_page("", r#"/path?a=1&b="2""#);
        assert!(!html.contains(r#"b="2""#));
        assert!(html.contains("b=&quot;2&quot;"));
    }

    #[test]
    fn lock_page_contains_lock() {
        assert!(lock_page().contains("ロック中"));
    }
}
