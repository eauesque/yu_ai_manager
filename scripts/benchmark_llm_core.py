"""Core benchmark logic for LLM backend comparisons."""

import json
import logging
import statistics
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

DEFAULT_PROMPTS = [
    "Explain the concept of neural networks in simple terms.",
    "Write a short poem about the ocean.",
    "What are the main differences between Python and Rust?",
]

DEFAULT_HAILO_URL = "http://localhost:5000"
DEFAULT_OLLAMA_URL = "http://localhost:11434"


@dataclass
class RunResult:
    """Result of a single benchmark run."""
    target: str
    model: str
    prompt: str
    token_count: int
    total_time: float
    ttft: float
    tokens_per_sec: float
    output_preview: str


@dataclass
class BenchmarkSummary:
    """Aggregated results across multiple runs."""
    target: str
    model: str
    runs: int
    avg_tokens_per_sec: float
    min_tokens_per_sec: float
    max_tokens_per_sec: float
    avg_ttft: float
    avg_total_time: float
    avg_token_count: float
    results: list = field(default_factory=list)


def benchmark_hailo_stream(
    base_url: str,
    model: str,
    prompt: str,
    max_tokens: int = 256,
    temperature: float = 0.7,
) -> RunResult:
    """Benchmark Hailo GenAI via OpenAI-compatible streaming API."""
    url = f"{base_url}/ext/hailo-genai/v1/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
    }).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
    )
    token_count = 0
    ttft = 0.0
    full_text = ""
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices", [])
                if not choices:
                    continue
                content = choices[0].get("delta", {}).get("content", "")
                if content:
                    if token_count == 0:
                        ttft = time.perf_counter() - start
                    token_count += 1
                    full_text += content
    except urllib.error.URLError as e:
        raise ConnectionError(f"Hailo API unreachable at {base_url}: {e}") from e

    total_time = time.perf_counter() - start
    tps = token_count / total_time if total_time > 0 else 0
    return RunResult("hailo", model, prompt, token_count, round(total_time, 3), round(ttft, 3), round(tps, 2), full_text[:100])


def benchmark_ollama_stream(
    base_url: str,
    model: str,
    prompt: str,
    max_tokens: int = 256,
    temperature: float = 0.7,
) -> RunResult:
    """Benchmark Ollama via its native streaming API."""
    url = f"{base_url}/api/generate"
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "options": {"num_predict": max_tokens, "temperature": temperature},
        "stream": True,
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    token_count = 0
    ttft = 0.0
    full_text = ""
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
                token_text = chunk.get("response", "")
                if token_text:
                    if token_count == 0:
                        ttft = time.perf_counter() - start
                    token_count += 1
                    full_text += token_text
                if chunk.get("done"):
                    eval_count = chunk.get("eval_count")
                    if eval_count:
                        token_count = eval_count
                    break
    except urllib.error.URLError as e:
        raise ConnectionError(f"Ollama API unreachable at {base_url}: {e}") from e

    total_time = time.perf_counter() - start
    tps = token_count / total_time if total_time > 0 else 0
    return RunResult("ollama", model, prompt, token_count, round(total_time, 3), round(ttft, 3), round(tps, 2), full_text[:100])


def clear_hailo_context(base_url: str) -> None:
    """Clear Hailo LLM context between benchmark runs."""
    url = f"{base_url}/ext/hailo-genai/api/llm/clear-context"
    req = urllib.request.Request(url, method="POST", headers={"X-Requested-With": "XMLHttpRequest"})
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception:
        logger.debug("step failed", exc_info=True)


def run_benchmark(
    target: str,
    model: str,
    prompts: list,
    runs: int = 3,
    max_tokens: int = 256,
    temperature: float = 0.7,
    hailo_url: str = DEFAULT_HAILO_URL,
    ollama_url: str = DEFAULT_OLLAMA_URL,
) -> BenchmarkSummary:
    """Run benchmark and return aggregated results."""
    results = []
    for run_idx in range(runs):
        for prompt in prompts:
            print(f"  Run {run_idx + 1}/{runs}: {prompt[:50]}...", flush=True)
            if target == "hailo":
                clear_hailo_context(hailo_url)
                result = benchmark_hailo_stream(hailo_url, model, prompt, max_tokens, temperature)
            else:
                result = benchmark_ollama_stream(ollama_url, model, prompt, max_tokens, temperature)
            results.append(result)
            print(f"    -> {result.token_count} tokens, {result.tokens_per_sec} tok/s, TTFT {result.ttft}s")

    tps_list = [r.tokens_per_sec for r in results]
    return BenchmarkSummary(
        target=target,
        model=model,
        runs=runs,
        avg_tokens_per_sec=round(statistics.mean(tps_list), 2),
        min_tokens_per_sec=round(min(tps_list), 2),
        max_tokens_per_sec=round(max(tps_list), 2),
        avg_ttft=round(statistics.mean(r.ttft for r in results), 3),
        avg_total_time=round(statistics.mean(r.total_time for r in results), 3),
        avg_token_count=round(statistics.mean(r.token_count for r in results), 1),
        results=results,
    )


def summary_to_dict(summary: BenchmarkSummary) -> dict:
    """Convert summary to JSON-serializable dict."""
    return {
        "target": summary.target,
        "model": summary.model,
        "runs": summary.runs,
        "avg_tokens_per_sec": summary.avg_tokens_per_sec,
        "min_tokens_per_sec": summary.min_tokens_per_sec,
        "max_tokens_per_sec": summary.max_tokens_per_sec,
        "avg_ttft": summary.avg_ttft,
        "avg_total_time": summary.avg_total_time,
        "avg_token_count": summary.avg_token_count,
    }
