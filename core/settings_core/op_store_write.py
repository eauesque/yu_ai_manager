"""1Password CLI write operations: vault listing and secret push.

Provides list_vaults() and push_secrets_to_op() for writing secrets
to 1Password items via the op CLI.
"""

from __future__ import annotations

import json as _json
import logging
import re
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

_OP_TIMEOUT = 10  # subprocess timeout (seconds)

# ── Input Validation ───────────────────────────────────────────

_DANGEROUS_CHARS_RE = re.compile(r"[;|&`$\\<>\"'\n\r\x00]")


def _validate_name(value: str, label: str) -> str | None:
    """Validate vault_name / item_title.

    Rejects dangerous characters as a defense-in-depth measure
    (subprocess list form already prevents shell injection).
    Unicode (e.g. Japanese) is allowed.
    Returns error message string if invalid, None if OK.
    """
    if not value or not value.strip():
        return f"{label} が空です"
    if len(value) > 200:
        return f"{label} が長すぎます (200 文字以内)"
    if _DANGEROUS_CHARS_RE.search(value):
        return f"{label} に使用できない文字が含まれています"
    return None


def _key_to_field_name(key: str) -> str:
    """Convert dotted key notation to op field name.

    Example: "server.pin" -> "server_pin"
             "sns.bluesky.app_password" -> "sns_bluesky_app_password"
    """
    return key.replace(".", "_")


def _parse_op_error(stderr: str) -> str:
    """Generate user-friendly message from op CLI stderr."""
    lower = stderr.lower()
    if "not signed in" in lower or "sign in" in lower:
        return "1Password にサインインされていません。op signin を実行してください"
    if "could not be found" in lower:
        return "指定されたアイテムまたは vault が見つかりません"
    if "not authorized" in lower or "permission" in lower:
        return "1Password のアクセス権限がありません"
    if "more than one item" in lower:
        return "同名のアイテムが複数存在します。vault を確認してください"
    # Return as-is
    return stderr.strip() if stderr.strip() else "不明なエラーが発生しました"


# ── Vault Listing ───────────────────────────────────────────────


def list_vaults() -> list:
    """List vaults via op vault list.

    Returns:
        [{"id": "...", "name": "..."}, ...] or empty list on error.
    """
    from .op_store import is_available

    if not is_available():
        logger.warning("op CLI が見つかりません")
        return []

    try:
        result = subprocess.run(
            ["op", "vault", "list", "--format", "json"],
            capture_output=True, text=True,
            timeout=_OP_TIMEOUT,
        )
        if result.returncode != 0:
            logger.warning("op vault list 失敗: %s", result.stderr.strip())
            return []

        vaults = _json.loads(result.stdout)
        return [{"id": v.get("id", ""), "name": v.get("name", "")} for v in vaults]

    except subprocess.TimeoutExpired:
        logger.warning("op vault list タイムアウト (%ds)", _OP_TIMEOUT)
        return []
    except (FileNotFoundError, Exception) as e:
        logger.warning("op vault list エラー: %s", e)
        return []


# ── Batch Secret Write ─────────────────────────────────────


def push_secrets_to_op(
    vault_name: str,
    item_title: str,
    secrets: dict[str, str],
) -> dict[str, Any]:
    """Write secrets to 1Password in batch and return op:// URIs.

    Args:
        vault_name: Target vault name.
        item_title: Item title.
        secrets: {"server.pin": "1234", ...} key -> plaintext map.

    Returns:
        {"success": bool, "message": str, "uris": {"server.pin": "op://...", ...}}
    """
    from .op_store import is_available

    # Validation
    err = _validate_name(vault_name, "Vault 名")
    if err:
        return {"success": False, "message": err, "uris": {}}

    err = _validate_name(item_title, "アイテムタイトル")
    if err:
        return {"success": False, "message": err, "uris": {}}

    if not secrets:
        return {"success": False, "message": "書き込むシークレットがありません", "uris": {}}

    if not is_available():
        return {"success": False, "message": "op CLI が見つかりません", "uris": {}}

    # Build field assignments for op CLI
    # Use JSON template via stdin to avoid exposing secrets in process args
    key_to_field = {}
    fields_list = []
    for key, value in secrets.items():
        field_name = _key_to_field_name(key)
        key_to_field[key] = field_name
        fields_list.append({
            "id": field_name,
            "type": "CONCEALED",
            "value": value,
        })

    # Check if item exists
    item_exists = False
    try:
        check = subprocess.run(
            ["op", "item", "get", item_title, "--vault", vault_name, "--format", "json"],
            capture_output=True, text=True,
            timeout=_OP_TIMEOUT,
        )
        if check.returncode == 0:
            item_exists = True
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "op item get タイムアウト", "uris": {}}
    except Exception as e:
        logger.debug("op item get check error (will try create): %s", e)

    try:
        # Build JSON template and pass via stdin to avoid
        # exposing secrets in process argument list (visible via ps)
        template = {
            "title": item_title,
            "vault": {"name": vault_name},
            "category": "SECURE_NOTE",
            "fields": fields_list,
        }
        template_json = _json.dumps(template, ensure_ascii=False)

        if item_exists:
            cmd = [
                "op", "item", "edit", item_title,
                "--vault", vault_name,
                "--format", "json",
            ]
            logger.info(
                "1Password item update: vault=%s, title=%s, fields=%d",
                vault_name, item_title, len(secrets),
            )
        else:
            cmd = [
                "op", "item", "create",
                "--format", "json",
            ]
            logger.info(
                "1Password item create: vault=%s, title=%s, fields=%d",
                vault_name, item_title, len(secrets),
            )

        result = subprocess.run(
            cmd,
            input=template_json,
            capture_output=True, text=True,
            timeout=_OP_TIMEOUT,
        )
        # Clear sensitive data from memory
        template_json = ""
        template.clear()
        fields_list.clear()

        if result.returncode != 0:
            msg = _parse_op_error(result.stderr)
            return {"success": False, "message": msg, "uris": {}}

        # Success: build op:// URIs
        uris = {}
        for key, field_name in key_to_field.items():
            uris[key] = f"op://{vault_name}/{item_title}/{field_name}"

        action = "更新" if item_exists else "作成"
        return {
            "success": True,
            "message": f"{len(secrets)} 件のシークレットを 1Password に{action}しました",
            "uris": uris,
        }

    except subprocess.TimeoutExpired:
        action = "edit" if item_exists else "create"
        return {
            "success": False,
            "message": f"op item {action} タイムアウト ({_OP_TIMEOUT}秒)",
            "uris": {},
        }
    except Exception as e:
        return {"success": False, "message": f"予期しないエラー: {e}", "uris": {}}
