"""Benchmark MCP tools for Hailo GenAI extension."""

import json
import time
import urllib.request

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient

_PFX = "/ext/hailo-genai"


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _bench_hailo(
    client: YuManagerClient,
    prompt: str,
    runs: int,
    max_tokens: int,
    temperature: float,
    model: str,
):
    results = []
    for i in range(runs):
        client.post(f"{_PFX}/api/llm/clear-context", {})
        url = client.base_url + f"{_PFX}/v1/chat/completions"
        payload = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }).encode()
        headers = client._headers()
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "text/event-stream"
        req = urllib.request.Request(url, data=payload, headers=headers)
        token_count = 0
        ttft = 0.0
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices", [])
                    if choices and choices[0].get("delta", {}).get("content"):
                        if token_count == 0:
                            ttft = time.perf_counter() - start
                        token_count += 1
        except Exception as e:
            return {"error": f"Hailo API error: {e}"}

        elapsed = time.perf_counter() - start
        tps = token_count / elapsed if elapsed > 0 else 0
        results.append({
            "run": i + 1,
            "tokens": token_count,
            "total_time": round(elapsed, 3),
            "ttft": round(ttft, 3),
            "tokens_per_sec": round(tps, 2),
        })
    return {
        "target": "hailo",
        "model": model,
        "prompt": prompt[:80],
        "runs": runs,
        "avg_tokens_per_sec": round(sum(r["tokens_per_sec"] for r in results) / len(results), 2),
        "min_tokens_per_sec": round(min(r["tokens_per_sec"] for r in results), 2),
        "max_tokens_per_sec": round(max(r["tokens_per_sec"] for r in results), 2),
        "avg_ttft": round(sum(r["ttft"] for r in results) / len(results), 3),
        "avg_total_time": round(sum(r["total_time"] for r in results) / len(results), 3),
        "detail": results,
    }


def _bench_ollama(
    prompt: str,
    runs: int,
    max_tokens: int,
    ollama_model: str,
    ollama_url: str,
):
    results = []
    for _ in range(runs):
        url = f"{ollama_url}/api/generate"
        payload = json.dumps({
            "model": ollama_model,
            "prompt": prompt,
            "options": {"num_predict": max_tokens, "temperature": 0.7},
            "stream": True,
        }).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        token_count = 0
        ttft = 0.0
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if chunk.get("response"):
                        if token_count == 0:
                            ttft = time.perf_counter() - start
                        token_count += 1
                    if chunk.get("done"):
                        eval_count = chunk.get("eval_count")
                        if eval_count:
                            token_count = eval_count
                        break
        except Exception as e:
            return {"error": f"Ollama error: {e}"}

        elapsed = time.perf_counter() - start
        tps = token_count / elapsed if elapsed > 0 else 0
        results.append({
            "tokens": token_count,
            "total_time": round(elapsed, 3),
            "ttft": round(ttft, 3),
            "tokens_per_sec": round(tps, 2),
        })
    return results


def register_hailo_genai_benchmark_tools(mcp: FastMCP, client: YuManagerClient):
    """Register benchmark Hailo GenAI tools on the MCP server."""

    @mcp.tool()
    def hailo_benchmark(
        prompt: str = "Explain the concept of neural networks in simple terms.",
        runs: int = 3,
        max_tokens: int = 256,
        temperature: float = 0.7,
        model: str = "qwen2.5-1.5b-chat",
    ) -> str:
        """Benchmark Hailo-10H LLM inference speed."""
        result = _bench_hailo(client, prompt, runs, max_tokens, temperature, model)
        return _json(result)

    @mcp.tool()
    def hailo_benchmark_compare(
        prompt: str = "Explain the concept of neural networks in simple terms.",
        runs: int = 3,
        max_tokens: int = 256,
        hailo_model: str = "qwen2.5-1.5b-chat",
        ollama_model: str = "qwen2.5:1.5b",
        ollama_url: str = "http://localhost:11434",
    ) -> str:
        """Benchmark Hailo-10H vs Ollama (CPU) with the same prompt."""
        hailo_raw = _bench_hailo(client, prompt, runs, max_tokens, 0.7, hailo_model)
        if "error" in hailo_raw:
            return _json(hailo_raw)

        ollama_results = _bench_ollama(prompt, runs, max_tokens, ollama_model, ollama_url)
        if isinstance(ollama_results, dict) and "error" in ollama_results:
            return _json({"hailo": hailo_raw, "ollama": ollama_results})

        ollama_avg_tps = round(sum(r["tokens_per_sec"] for r in ollama_results) / len(ollama_results), 2) if ollama_results else 0
        ollama_avg_ttft = round(sum(r["ttft"] for r in ollama_results) / len(ollama_results), 3) if ollama_results else 0
        speedup = round(hailo_raw["avg_tokens_per_sec"] / ollama_avg_tps, 2) if ollama_avg_tps > 0 else 0

        return _json({
            "hailo": {
                "model": hailo_model,
                "avg_tokens_per_sec": hailo_raw["avg_tokens_per_sec"],
                "avg_ttft": hailo_raw["avg_ttft"],
            },
            "ollama": {
                "model": ollama_model,
                "avg_tokens_per_sec": ollama_avg_tps,
                "avg_ttft": ollama_avg_ttft,
            },
            "comparison": {
                "speedup": speedup,
                "summary": f"Hailo-10H is {speedup}x {'faster' if speedup > 1 else 'slower'} than CPU (Ollama)",
            },
        })
