"""Benchmark, profile, and engine OCR tools."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .ocr_job_client import OcrJobError, run_ocr_job
from .ocr_tools_common import as_json


def register_ocr_advanced_ops_tools(mcp: FastMCP, client: YuManagerClient):
    """Register advanced OCR engine and benchmark tools."""

    @mcp.tool()
    def ocr_engines() -> str:
        """List available OCR engines with their capability scores."""
        return as_json(client.get("/api/ocr/engines"))

    @mcp.tool()
    def ocr_benchmark(task: str = "ocr", server_id: str = "", benchmark_dir: str = "") -> str:
        """Run OCR benchmark to measure accuracy against test images."""
        body = {"task": task}
        if server_id:
            body["server_id"] = server_id
        if benchmark_dir:
            body["benchmark_dir"] = benchmark_dir
        # The job result carries aggregates only: per-case expected/actual
        # text would otherwise be readable through the unauthenticated
        # /api/jobs/status. The full report comes from the admin-gated
        # report endpoint.
        try:
            job = run_ocr_job(client, "/api/ocr/benchmark", body)
        except OcrJobError as exc:
            return f"Error: {exc}"
        report_id = (job.get("result") or {}).get("report_id")
        if not report_id:
            return "Error: the benchmark produced no report"
        return as_json(client.get(f"/api/ocr/benchmark/report/{report_id}", {}))

    @mcp.tool()
    def ocr_benchmark_cases(benchmark_dir: str = "") -> str:
        """List available benchmark test cases."""
        params = {}
        if benchmark_dir:
            params["dir"] = benchmark_dir
        return as_json(client.get("/api/ocr/benchmark/cases", params))

    @mcp.tool()
    def ocr_profiles() -> str:
        """List all model capability profiles."""
        return as_json(client.get("/api/ocr/profiles"))

    @mcp.tool()
    def ocr_profiles_fetch(url: str) -> str:
        """Fetch and merge community model profiles from a URL."""
        return as_json(client.post("/api/ocr/profiles/fetch", {"url": url}))

    @mcp.tool()
    def ocr_profile_update(model_prefix: str, scores: dict) -> str:
        """Manually update a model's capability scores."""
        return as_json(client.put(f"/api/ocr/profiles/{model_prefix}", {"scores": scores}))

    @mcp.tool()
    def ocr_npu_status(task: str = "ocr") -> str:
        """Check NPU availability and optimization suggestions."""
        return as_json(client.get("/api/ocr/npu", {"task": task}))
