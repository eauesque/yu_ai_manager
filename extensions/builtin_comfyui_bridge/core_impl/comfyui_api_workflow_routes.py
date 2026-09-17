"""Workflow import and upload routes for the ComfyUI bridge."""

from core.infra_core.api_errors import api_error, api_success
from core.infra_core.api_request import require_json_dict


def register_workflow_routes(
    bp,
    *,
    make_client,
    read_upload_bytes_limited_fn,
    validate_image_filename_fn,
    max_image_upload_bytes: int,
) -> None:
    @bp.route("/api/extract-workflow", methods=["POST"])
    async def api_extract_workflow():
        from quart import request

        from .comfyui_image_workflow import extract_workflow_from_image

        files = await request.files
        image_file = files.get("image")
        if not image_file:
            return api_error("image file is required", 400)

        filename = image_file.filename or "unknown.png"
        try:
            validate_image_filename_fn(filename)
            image_bytes = read_upload_bytes_limited_fn(
                image_file,
                max_bytes=max_image_upload_bytes,
            )
        except ValueError as exc:
            return api_error(str(exc), 413 if "exceeds" in str(exc) else 400)
        result = extract_workflow_from_image(image_bytes, filename)

        if result["ok"]:
            if result["format"] == "api":
                from .comfyui_workflow_import import extract_simple_params

                result["simple_params"] = extract_simple_params(result["workflow"])
            return api_success(result)
        return api_error(result.get("error", "Extraction failed"), 422)

    @bp.route("/api/parse-workflow-params", methods=["POST"])
    async def api_parse_workflow_params():
        from quart import request

        from .comfyui_workflow_import import extract_simple_params

        data, err = await require_json_dict(request)
        if err:
            return api_error(err[0]["error"], err[1])

        simple_params = extract_simple_params(data)
        if not simple_params:
            return api_error(
                "ワークフローから Simple モードのパラメータを抽出できませんでした",
                422,
            )
        return api_success({"simple_params": simple_params})

    @bp.route("/api/upload-controlnet-image", methods=["POST"])
    async def api_upload_controlnet_image():
        from quart import request

        files = await request.files
        image_file = files.get("image")
        if not image_file:
            return api_error("image file is required", 400)

        filename = image_file.filename or "controlnet_input.png"
        try:
            validate_image_filename_fn(filename)
            image_bytes = read_upload_bytes_limited_fn(
                image_file,
                max_bytes=max_image_upload_bytes,
            )
        except ValueError as exc:
            return api_error(str(exc), 413 if "exceeds" in str(exc) else 400)
        client = make_client()
        try:
            stored_name = client.upload_image(image_bytes, filename)
            return api_success({"name": stored_name})
        except Exception as exc:
            return api_error(f"Upload failed: {exc}", 502)

    @bp.route("/api/check-workflow-from-file", methods=["POST"])
    async def api_check_workflow_from_file():
        from pathlib import Path

        from quart import request

        from core.infra_core.blocking_tasks import run_long_blocking_sync
        from core.services_core.db_api import get_readonly_db

        from .comfyui_image_workflow import (
            check_model_nodes,
            extract_gen_params_from_image,
            extract_workflow_from_image,
        )

        data, err = await require_json_dict(request)
        if err:
            return api_error(err[0]["error"], err[1])

        file_id = data.get("file_id")
        if not isinstance(file_id, int):
            return api_error("file_id (int) is required", 400)

        con = get_readonly_db()
        row = con.execute(
            "SELECT path FROM files WHERE id=? AND is_deleted=0",
            (file_id,),
        ).fetchone()
        if not row:
            return api_error("ファイルが見つかりません", 404)

        file_path = Path(row[0])
        if not file_path.is_file():
            return api_error("ファイルが見つかりません", 404)

        suffix = file_path.suffix.lower().lstrip(".")
        if suffix not in {"png", "jpg", "jpeg", "webp"}:
            return api_error("対応していないファイル形式です", 400)

        max_file_bytes = 32 * 1024 * 1024
        if file_path.stat().st_size > max_file_bytes:
            return api_error("ファイルサイズが大きすぎます", 413)

        def _blocking_check():
            try:
                image_bytes = file_path.read_bytes()
                gen_params = extract_gen_params_from_image(image_bytes, file_path.name)
                result = extract_workflow_from_image(image_bytes, file_path.name)
                if not result["ok"]:
                    return {"status": "ok"}
                if result.get("format") == "editor":
                    return {"status": "ok"}
                return check_model_nodes(result["workflow"], gen_params)
            except Exception as exc:
                import logging as _logging
                _logging.getLogger(__name__).warning(
                    "check-workflow-from-file: unexpected error for %s: %s",
                    file_path.name, exc,
                )
                return {"status": "ok"}

        check_result = await run_long_blocking_sync(_blocking_check)
        return api_success(data=check_result)

    @bp.route("/api/queue-workflow-from-file", methods=["POST"])
    async def api_queue_workflow_from_file():
        import uuid
        from pathlib import Path

        from quart import request

        from core.bridge_core import BridgeConnectionError, BridgeHTTPError
        from core.infra_core.blocking_tasks import run_long_blocking_sync
        from core.services_core.db_api import get_readonly_db

        from .comfyui_image_workflow import (
            check_model_nodes,
            extract_gen_params_from_image,
            extract_workflow_from_image,
            migrate_clip_types,
            supplement_model_nodes,
        )

        data, err = await require_json_dict(request)
        if err:
            return api_error(err[0]["error"], err[1])

        file_id = data.get("file_id")
        if not isinstance(file_id, int):
            return api_error("file_id (int) is required", 400)

        supplement = bool(data.get("supplement", False))

        con = get_readonly_db()
        row = con.execute(
            "SELECT path FROM files WHERE id=? AND is_deleted=0",
            (file_id,),
        ).fetchone()
        if not row:
            return api_error("ファイルが見つかりません", 404)

        file_path = Path(row[0])
        if not file_path.is_file():
            return api_error("ファイルが見つかりません", 404)

        suffix = file_path.suffix.lower().lstrip(".")
        if suffix not in {"png", "jpg", "jpeg", "webp"}:
            return api_error("対応していないファイル形式です", 400)

        max_file_bytes = 32 * 1024 * 1024
        if file_path.stat().st_size > max_file_bytes:
            return api_error("ファイルサイズが大きすぎます", 413)

        def _blocking_work():
            image_bytes = file_path.read_bytes()
            result = extract_workflow_from_image(image_bytes, file_path.name)
            if not result["ok"]:
                return ("error", 422, "ワークフロー情報が見つかりません")
            if result.get("format") == "editor":
                return (
                    "error",
                    422,
                    "Editor format workflow はキュー投入に対応していません",
                )

            workflow = result["workflow"]
            supplement_applied: dict = {}

            if supplement:
                gen_params = extract_gen_params_from_image(image_bytes, file_path.name)
                if not gen_params:
                    return ("error", 400, "バックアップ情報が見つかりません")
                workflow, supplement_applied = supplement_model_nodes(workflow, gen_params)
                post_check = check_model_nodes(workflow, None)
                if post_check.get("status") != "ok":
                    return (
                        "error",
                        400,
                        "補完後もモデルノードが未設定のままです。ComfyUI 側で手動設定してください。",
                    )

            # Correct stale clip_type values from old images (e.g. "wan" → "qwen_image"
            # for Anima/QWEN3 models). Applied unconditionally so old images re-queue
            # correctly without regenerating them.
            workflow = migrate_clip_types(workflow)

            client = make_client()
            client_id = str(uuid.uuid4())
            queue_result = client.queue_prompt(workflow, client_id)
            prompt_id = (
                queue_result.get("prompt_id")
                if isinstance(queue_result, dict)
                else None
            )
            return ("ok", prompt_id, client.api_url, supplement_applied)

        try:
            work_result = await run_long_blocking_sync(_blocking_work)
        except BridgeConnectionError:
            return api_error("ComfyUI への接続に失敗しました", 502)
        except BridgeHTTPError as exc:
            detail = exc.body.strip()[:300] if exc.body else ""
            msg = f"ComfyUI エラー: HTTP {exc.status}"
            if detail:
                msg += f" — {detail}"
            return api_error(msg, 502)
        except Exception as exc:
            return api_error(f"ComfyUI エラー: {exc}", 502)

        if work_result[0] == "error":
            _, status_code, message = work_result
            return api_error(message, status_code)

        _, prompt_id, comfyui_url, supplement_applied = work_result
        response_payload: dict = {"prompt_id": prompt_id, "comfyui_url": comfyui_url}
        if supplement and supplement_applied:
            response_payload["supplemented"] = True
            response_payload["supplement_applied"] = supplement_applied
        return api_success(data=response_payload)
