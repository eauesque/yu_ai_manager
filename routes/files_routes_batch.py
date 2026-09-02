import asyncio
import base64
from collections.abc import AsyncIterator

from quart import Response, jsonify, request

from core.files_core.response_types import FileBytes, FileError, FilePath
from core.files_core.thumbnail import serve_thumbnail
from core.infra_core.api_errors import api_result
from core.infra_core.api_request import require_json_dict


async def thumbnails_batch():
    data, err = await require_json_dict(request)
    if err:
        return api_result(err[0], err[1])
    ids = data.get("ids", [])
    if not isinstance(ids, list):
        return api_result({"error": "ids must be array"}, 400)
    ids = [int(x) for x in ids[:50] if isinstance(x, (int, float)) and x > 0]
    want_multipart = "multipart/mixed" in request.headers.get("Accept", "")

    # serve_thumbnail itself submits the generator to the heavy-io pool and
    # blocks waiting on the future (singleflight pattern). Running the OUTER
    # serve_thumbnail call on the same heavy-io pool deadlocks: 50 outer
    # waits saturate the 8-16 worker pool, leaving zero workers free for the
    # inner _generate submissions, which then time out after 10s. So dispatch
    # the outer waits via ``asyncio.to_thread`` (default loop executor) —
    # those threads are cheap blockers, while the actual disk-IO + PIL work
    # still runs on the heavy-io pool via the inner submit.
    async def _one(fid: int):
        try:
            return await asyncio.to_thread(serve_thumbnail, fid)
        except Exception:
            return None

    raw_results = await asyncio.gather(*[_one(fid) for fid in ids])
    result_items: list[tuple[int, FileBytes | FilePath]] = []
    for file_id, result in zip(ids, raw_results, strict=False):
        if result is None or isinstance(result, FileError):
            continue
        if isinstance(result, (FilePath, FileBytes)):
            result_items.append((file_id, result))

    if want_multipart:
        boundary = "thumb-batch-boundary"
        return Response(
            _iter_multipart(result_items, boundary),
            content_type=f"multipart/mixed; boundary={boundary}",
        )

    thumbnails = {}
    for file_id, result in result_items:
        if isinstance(result, FilePath):
            try:
                img_bytes = result.path.read_bytes()
            except OSError:
                continue
            mime = result.mime_type
        else:
            img_bytes = result.data
            mime = result.mime_type
        thumbnails[str(file_id)] = f"data:{mime};base64,{base64.b64encode(img_bytes).decode('ascii')}"
    return jsonify({"thumbnails": thumbnails})


async def _iter_multipart(items: list[tuple[int, FileBytes | FilePath]], boundary: str) -> AsyncIterator[bytes]:
    for file_id, result in items:
        if isinstance(result, FileBytes):
            yield (
                f"--{boundary}\r\n"
                f"Content-Type: {result.mime_type}\r\n"
                f"X-File-Id: {file_id}\r\n"
                f"Content-Length: {len(result.data)}\r\n\r\n"
            ).encode("ascii")
            yield result.data
            yield b"\r\n"
            continue

        try:
            size = result.size if result.size is not None else result.path.stat().st_size
        except OSError:
            continue
        yield (
            f"--{boundary}\r\n"
            f"Content-Type: {result.mime_type}\r\n"
            f"X-File-Id: {file_id}\r\n"
            f"Content-Length: {size}\r\n\r\n"
        ).encode("ascii")
        try:
            with result.path.open("rb") as fh:
                while True:
                    chunk = await asyncio.to_thread(fh.read, 64 * 1024)
                    if not chunk:
                        break
                    yield chunk
        except OSError:
            continue
        yield b"\r\n"
    yield f"--{boundary}--\r\n".encode("ascii")


async def thumbnails_warmup():
    from core.files_core.thumbnail_batch_warmup_core import start_warmup_background

    data, err = await require_json_dict(request)
    if err:
        return api_result(err[0], err[1])
    file_ids = data.get("file_ids", [])
    if not isinstance(file_ids, list) or not file_ids:
        return api_result({"error": "file_ids required"}, 400)
    if len(file_ids) > 2000:
        file_ids = file_ids[:2000]
    file_ids = [int(x) for x in file_ids if isinstance(x, (int, float)) and x > 0]
    started = start_warmup_background(file_ids)
    return jsonify({"ok": True, "started": started, "count": len(file_ids)}), 202
