"""Error handler registration for the Quart app factory."""

from __future__ import annotations

import json
import logging
import time
import traceback

from quart import Quart, g, render_template, request
from werkzeug.exceptions import HTTPException

from core.infra_core.api_errors import api_error
from core.infra_core.debug_log import dlog

logger = logging.getLogger(__name__)
from core.web.error_bundle import (
    build_bug_report_url,
    build_error_bundle,
    encode_error_bundle_gzip_base64,
)

_HTTP_STATUS_I18N_JA = {
    400: "不正なリクエストです",
    403: "アクセスが拒否されました",
    404: "ページが見つかりません",
    405: "許可されていないメソッドです",
    408: "リクエストがタイムアウトしました",
    413: "リクエストが大きすぎます",
    429: "リクエストが多すぎます。しばらく待ってからお試しください",
    500: "サーバー内部エラーが発生しました",
    502: "不正なゲートウェイです",
    503: "サービスが一時的に利用できません",
}

_ERROR_I18N = {
    "ja": {
        "qr_label": "エラー情報（スマホで撮影して共有できます）",
        "qr_label_bug": "バグ報告（QRを撮影してGitHub Issueを送れます）",
        "copy_bundle": "Bundle JSONをコピー",
        "download_bundle": "Bundleをダウンロード",
        "back_home": "トップに戻る",
        "back_prev": "前のページ",
        "detail_label": "詳細",
        "internal_error": "サーバー内部エラーが発生しました",
        "title_prefix": "エラー",
    },
    "en": {
        "qr_label": "Error info (scan with phone to share)",
        "qr_label_bug": "Bug report (scan to submit a GitHub Issue)",
        "copy_bundle": "Copy Bundle JSON",
        "download_bundle": "Download Bundle",
        "back_home": "Back to Home",
        "back_prev": "Previous Page",
        "detail_label": "Detail",
        "internal_error": "Internal server error",
        "title_prefix": "Error",
    },
}

# Bug report relay page on GitHub Pages
_BUGREPORT_URL = "https://eauesque.github.io/yu_ai_manager/bugreport.html"


def _append_unhandled_traceback(exc: BaseException) -> None:
    """Append a 500 traceback to ``logs/error.log`` (best-effort).

    `app.logger.exception` only writes to stderr, which is unreachable when the
    server is started from a detached shell. Persisting to a log file makes
    LAN-reported 500s diagnosable without enabling ``TAGDB_DEBUG``.
    """
    try:
        from core.paths import log_path
        path = log_path("error.log")
        path.parent.mkdir(parents=True, exist_ok=True)
        rid = getattr(g, "request_id", "-")
        header = (
            f"\n===== {time.strftime('%Y-%m-%dT%H:%M:%S%z')} "
            f"request_id={rid} path={request.path} =====\n"
        )
        with path.open("a", encoding="utf-8") as fh:
            fh.write(header)
            traceback.print_exception(type(exc), exc, exc.__traceback__, file=fh)
    except Exception:
        logger.warning("web startup step failed", exc_info=True)


def detect_lang() -> str:
    """Detect preferred language from Accept-Language header."""
    accept = request.headers.get("Accept-Language", "")
    return "ja" if "ja" in accept else "en"


async def render_error_page(
    status_code: int,
    message: str,
    detail: str = "",
    exc: Exception | None = None,
):
    """Render error page with QR diagnostic code.

    If ``exc`` is provided (unhandled exception), generates a Type 3 Bug
    Report QR whose payload is a URL to the GitHub Pages relay page.
    Otherwise generates a lightweight Type 2 Error Diagnostic QR.
    """
    from core.search_api.server_info import APP_VERSION

    lang = detect_lang()
    i18n = _ERROR_I18N.get(lang, _ERROR_I18N["en"])
    bundle_json = ""
    bundle_download_b64 = ""
    bundle_download_name = ""

    if exc is not None:
        bundle = await build_error_bundle(exc)
        qr_data, _ = build_bug_report_url(bundle, _BUGREPORT_URL)
        bundle_json = json.dumps(bundle, ensure_ascii=False, indent=2)
        bundle_download_b64 = encode_error_bundle_gzip_base64(bundle)
        bundle_download_name = f"{bundle.get('error_id', 'error-bundle')}.json.gz"
        qr_label = i18n["qr_label_bug"]
    else:
        # Type 2 — Error Diagnostic: QR encodes compact JSON
        qr_data = {
            "s": status_code,
            "p": request.path[:80],
            "v": APP_VERSION,
        }
        qr_label = i18n["qr_label"]

    try:
        return await render_template(
            "error.html",
            status_code=status_code,
            message=message,
            detail=detail,
            qr_data=qr_data,
            qr_label=qr_label,
            bundle_json=bundle_json,
            bundle_download_b64=bundle_download_b64,
            bundle_download_name=bundle_download_name,
            copy_bundle_label=i18n["copy_bundle"],
            download_bundle_label=i18n["download_bundle"],
            back_home=i18n["back_home"],
            back_prev=i18n["back_prev"],
            detail_label=i18n["detail_label"],
            title_prefix=i18n["title_prefix"],
            html_lang=lang,
        ), status_code
    except Exception:
        return f"{status_code} {message}", status_code


def register_error_handlers(app: Quart) -> None:
    """Register API/HTML fallback error handlers."""

    @app.errorhandler(HTTPException)
    async def handle_http_error(e: HTTPException):
        if request.path.startswith("/api/"):
            dlog(
                "web",
                "request.http_error",
                request_id=getattr(g, "request_id", "-"),
                status=e.code or 500,
                path=request.path,
                description=e.description,
            )
            return api_error(
                e.description or "HTTP error",
                status=e.code or 500,
                code=f"http_{e.code or 500}",
            )
        code = e.code or 500
        lang = detect_lang()
        if lang == "ja" and code in _HTTP_STATUS_I18N_JA:
            msg = _HTTP_STATUS_I18N_JA[code]
        else:
            msg = e.description or "HTTP error"
        # Type 2 QR — no exc
        return await render_error_page(code, msg)

    @app.errorhandler(Exception)
    async def handle_unexpected_error(e: Exception):
        app.logger.exception("Unhandled exception on %s", request.path)
        # Always persist tracebacks (independent of TAGDB_DEBUG) so 500s reported
        # from the LAN can be diagnosed after the fact.
        _append_unhandled_traceback(e)
        dlog(
            "web",
            "request.unhandled_exception",
            request_id=getattr(g, "request_id", "-"),
            path=request.path,
            exc_type=type(e).__name__,
            detail=str(e),
        )
        lang = detect_lang()
        i18n = _ERROR_I18N.get(lang, _ERROR_I18N["en"])
        msg = i18n["internal_error"]
        if request.path.startswith("/api/"):
            return api_error(
                msg,
                status=500,
                code="internal_error",
                detail=str(e)[:200] if app.debug else None,
            )
        detail = str(e)[:200] if app.debug else ""
        # Type 3 QR — pass exc for bug report relay URL
        return await render_error_page(500, msg, detail, exc=e)
