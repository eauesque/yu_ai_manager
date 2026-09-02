from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)
_LOG_PROMPTS = os.environ.get("LLM_GATEWAY_LOG_PROMPTS", "0") == "1"


@dataclass
class AuditRecord:
    request_id: str
    timestamp: datetime
    client_ip: str
    auth_key_id: str
    endpoint: str
    method: str
    status_code: int
    latency_ms: int
    model: str | None = None
    backend_id: str | None = None
    stream: bool = False
    backend_latency_ms: int | None = None
    prompt_sha256: str | None = None
    request_bytes: int | None = None
    response_bytes: int | None = None
    error_code: str | None = None
    workflow_sha256: str | None = None
    node_types: list[str] | None = None
    comfy_prompt_id: str | None = None
    prompt_full: str | None = None

    def to_json_line(self) -> str:
        d = asdict(self)
        d["timestamp"] = self.timestamp.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        if not _LOG_PROMPTS:
            d.pop("prompt_full", None)
        return json.dumps(
            {k: v for k, v in d.items() if v is not None}, ensure_ascii=False
        )


class AuditWriter:
    def __init__(self, log_dir: Path, maxsize: int = 10000) -> None:
        self._log_dir = Path(log_dir)
        self._queue: asyncio.Queue[AuditRecord] = asyncio.Queue(maxsize=maxsize)
        self._task: asyncio.Task | None = None
        self._last_date: str | None = None
        self._fh = None
        self._drop_count = 0

    async def start(self) -> None:
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._task = asyncio.create_task(self._loop(), name="gateway-audit")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        if self._fh:
            self._fh.close()

    def emit_admin(self, record: AdminAuditRecord) -> None:
        """Write an admin event to audit-admin-YYYYMMDD.jsonl (sync, fire-and-forget)."""
        try:
            date_str = record.timestamp.strftime("%Y%m%d")
            path = self._log_dir / f"audit-admin-{date_str}.jsonl"
            # Only chmod on new file creation
            is_new = not path.exists()
            with open(path, "a", encoding="utf-8") as f:  # noqa: SIM115
                with contextlib.suppress(OSError):
                    if is_new:
                        os.chmod(path, 0o600)
                f.write(record.to_json_line() + "\n")
        except OSError as exc:
            logger.warning("[gateway:audit] admin write failed: %s", exc)

    def emit(self, record: AuditRecord) -> None:
        try:
            self._queue.put_nowait(record)
        except asyncio.QueueFull:
            try:
                self._queue.get_nowait()
                self._drop_count += 1
            except asyncio.QueueEmpty:
                pass
            with contextlib.suppress(asyncio.QueueFull):
                self._queue.put_nowait(record)

    async def _loop(self) -> None:
        while True:
            try:
                rec = await self._queue.get()
                await asyncio.to_thread(self._write, rec)
            except asyncio.CancelledError:
                while not self._queue.empty():
                    try:
                        self._write(self._queue.get_nowait())
                    except asyncio.QueueEmpty:
                        break
                raise

    def _write(self, record: AuditRecord) -> None:
        date_str = record.timestamp.strftime("%Y%m%d")
        if date_str != self._last_date:
            if self._fh:
                self._fh.close()
            path = self._log_dir / f"audit-{date_str}.jsonl"
            try:
                # Only chmod on new file creation
                is_new = not path.exists()
                self._fh = open(path, "a", encoding="utf-8")  # noqa: SIM115
                if is_new:
                    with contextlib.suppress(OSError):
                        os.chmod(path, 0o600)
            except OSError as exc:
                logger.warning("[gateway:audit] open failed: %s", exc)
                self._fh = None
            self._last_date = date_str
        if self._fh:
            try:
                self._fh.write(record.to_json_line() + "\n")
                self._fh.flush()
            except OSError as exc:
                logger.warning("[gateway:audit] write failed: %s", exc)


@dataclass
class AdminAuditRecord:
    event: str
    key_id: str
    scopes: list[str]
    auth_path: str
    client_ip: str
    timestamp: datetime

    def to_json_line(self) -> str:
        d = asdict(self)
        d["timestamp"] = self.timestamp.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        return json.dumps(d, ensure_ascii=False)


_writer: AuditWriter | None = None


def init_writer(log_dir: Path, maxsize: int = 10000) -> AuditWriter:
    global _writer
    _writer = AuditWriter(log_dir, maxsize)
    return _writer


def get_writer() -> AuditWriter | None:
    return _writer
