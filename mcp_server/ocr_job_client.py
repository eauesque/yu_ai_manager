"""Submit-and-poll helper for the OCR job routes.

The five OCR execution routes answer 202 with a ``run_id`` and do the work in a
job whose id is fixed to ``"ocr"``. Matching on ``job_id`` alone cannot tell one
submission from the next, so every wait here is scoped to the ``run_id`` the
submit returned; the server carries it in ``JobDict.detail`` (the dict
deliberately omits ``started_at``, leaving ``detail`` as the only run identity a
client can see).
"""

from __future__ import annotations

import time
from typing import Any

# A VLM pass over a long PDF is slow; the cap exists so a wedged job cannot hang
# an MCP tool call forever.
_DEFAULT_TIMEOUT_S = 30 * 60
_POLL_INTERVAL_S = 1.0


class OcrJobError(RuntimeError):
    """The job was refused, failed, or was taken over by another run."""


def submit_ocr_job(client: Any, path: str, body: dict) -> str:
    """POST to an OCR route and return the ``run_id``.

    Raises ``OcrJobError`` carrying the server's own message so the caller can
    report *why* it was refused rather than a bare status code.
    """
    response = client.post(path, body)
    if not isinstance(response, dict):
        raise OcrJobError(f"unexpected response from {path}: {response!r}")

    run_id = response.get("run_id")
    if isinstance(run_id, str) and run_id:
        return run_id

    # A 409 body describes the job already holding the slot, not this request.
    if response.get("running") is True and response.get("label"):
        raise OcrJobError(f"{response['label']} is already running")
    error = response.get("error") or response.get("message")
    raise OcrJobError(str(error) if error else f"unexpected response from {path}: {response!r}")


def wait_for_ocr_run(
    client: Any,
    run_id: str,
    *,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
    interval_s: float = _POLL_INTERVAL_S,
    sleep=time.sleep,
    now=time.monotonic,
) -> dict:
    """Block until the run identified by ``run_id`` finishes, and return it."""
    deadline = now() + timeout_s
    while True:
        job = client.get("/api/jobs/ocr", {})
        if not isinstance(job, dict):
            raise OcrJobError(f"unexpected job response: {job!r}")

        # HISTORY_TTL_SECS is 60: a finished entry disappears a minute later,
        # and start_or_current overwrites it when the next job starts. Either
        # way, our result is gone — we must not report success we never saw.
        if job.get("error") == "job not found" or job.get("ok") is False:
            raise OcrJobError("the OCR job is gone; its result was not observed")
        if job.get("detail") != run_id:
            raise OcrJobError("another OCR run replaced this one")

        if not job.get("running"):
            if job.get("error"):
                raise OcrJobError(str(job["error"]))
            return job

        if now() >= deadline:
            raise OcrJobError("timed out waiting for the OCR job")
        sleep(interval_s)


def run_ocr_job(client: Any, path: str, body: dict, **kwargs) -> dict:
    """Submit and wait. Returns the finished job."""
    return wait_for_ocr_run(client, submit_ocr_job(client, path, body), **kwargs)
