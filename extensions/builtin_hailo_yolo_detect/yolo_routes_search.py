"""YOLO detection result and search routes.

Separated from hailo_yolo_detect.py to keep each module under 300 lines.
"""

import json

from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def register_result_routes(bp):
    """Register detection result, search, clear, model, and label routes."""
    from quart import jsonify, request


    _EXT_NAME = "builtin-hailo-yolo-detect"


    # -- Detection Results --

    @bp.route("/api/detect/results/<int:file_id>")
    async def api_detect_results(file_id):
        """Get detection results for a single file."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        # Import from relocated annotations extension
        from importlib import import_module
        _ann_mod = import_module("extensions.builtin_annotations.core_impl")
        get_annotations_for_file = _ann_mod.get_annotations_for_file

        annotations = get_annotations_for_file(file_id, key="detections")
        # Filter to YOLO sources only
        yolo_annotations = [
            a for a in annotations if ":yolo" in a["source"]
        ]
        if not yolo_annotations:
            return jsonify({"status": "ok", "detections": [], "source": None})

        ann = yolo_annotations[0]
        try:
            detections = json.loads(ann["value"])
        except (json.JSONDecodeError, TypeError):
            detections = []

        return jsonify({
            "status": "ok",
            "detections": detections,
            "source": ann["source"],
            "confidence": ann.get("confidence"),
        })

    @bp.route("/api/detect/search")
    async def api_detect_search():
        """Search for files containing a detected class.

        Query params:
            class_name: COCO class name (e.g. "person")
            min_confidence: minimum confidence (default 0.0)
            limit: max results (default 50, max 200)
            offset: pagination offset
        """
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err

        class_name = request.args.get("class_name", "").strip().lower()
        if not class_name:
            return jsonify({
                "status": "error",
                "message": "class_name parameter is required",
            }), 400

        min_conf = float(request.args.get("min_confidence", 0.0))
        limit = min(int(request.args.get("limit") or 50), 200)
        offset = int(request.args.get("offset") or 0)

        from core.services_core.db_api import get_readonly_db
        con = get_readonly_db()
        # Search annotations where value JSON contains the class name
        search_pattern = f'%"class_name": "{class_name}"%'
        # Also try without space after colon (compact JSON)
        search_pattern_compact = f'%"class_name":"{class_name}"%'

        rows = con.execute(
            "SELECT a.file_id, a.value, a.source, a.confidence, "
            "  f.path "
            "FROM file_annotations a "
            "JOIN files f ON a.file_id = f.id "
            "WHERE f.is_deleted = 0 "
            "  AND a.key = 'detections' "
            "  AND a.source LIKE '%:yolo%' "
            "  AND (a.value LIKE ? OR a.value LIKE ?) "
            "ORDER BY a.confidence DESC "
            "LIMIT ? OFFSET ?",
            (search_pattern, search_pattern_compact, limit + offset, 0),
        ).fetchall()

        results = []
        for row in rows:
            file_id, value_str, source, avg_conf, filepath = row
            import os.path
            filename = os.path.basename(filepath)
            try:
                detections = json.loads(value_str)
            except (json.JSONDecodeError, TypeError):
                continue

            # Filter detections to the requested class + confidence
            matching = [
                d for d in detections
                if d.get("class_name", "").lower() == class_name
                and d.get("confidence", 0) >= min_conf
            ]
            if not matching:
                continue

            best = max(matching, key=lambda d: d["confidence"])
            results.append({
                "file_id": file_id,
                "filepath": filepath,
                "filename": filename,
                "source": source,
                "detection": best,
                "match_count": len(matching),
            })

        # Apply offset/limit after filtering
        paged = results[offset:offset + limit]

        return jsonify({
            "status": "ok",
            "results": paged,
            "total": len(results),
            "class_name": class_name,
            "min_confidence": min_conf,
            "limit": limit,
            "offset": offset,
        })

    # -- Clear Results --

    @bp.route("/api/detect/clear", methods=["POST"])
    async def api_detect_clear():
        """Delete all YOLO detection annotations."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.services_core.db_async import run_db_sync
        from core.services_core.yolo_detection_service import (
            clear_yolo_detection_annotations,
        )

        total_deleted = await run_db_sync(clear_yolo_detection_annotations)

        return jsonify({"status": "ok", "deleted": total_deleted})

    # -- Model Management --

    @bp.route("/api/model/status")
    async def api_model_status():
        """Check availability of all YOLO HEF models."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from .core_impl.model_download import get_model_status
        return jsonify({"status": "ok", "models": get_model_status()})

    @bp.route("/api/model/download", methods=["POST"])
    async def api_model_download():
        """Download a YOLO HEF model."""
        from .core_impl.model_download import (
            YOLO_MODELS,
            download_hef,
        )

        data = await request.get_json(silent=True) or {}
        model_name = data.get("model", "yolov8n")

        if model_name not in YOLO_MODELS:
            return jsonify({
                "status": "error",
                "message": f"Unknown model: {model_name}",
                "available": list(YOLO_MODELS.keys()),
            }), 400

        try:
            path = download_hef(model_name)
            return jsonify({
                "status": "ok",
                "model": model_name,
                "path": str(path),
            })
        except Exception as exc:
            return jsonify({
                "status": "error",
                "message": f"Download failed: {type(exc).__name__}: {exc}",
            }), 500

    # -- COCO Labels --

    @bp.route("/api/labels")
    async def api_labels():
        """Return all COCO class labels for autocomplete."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from .core_impl.yolo_labels import get_all_labels
        return jsonify({"status": "ok", "labels": get_all_labels()})
