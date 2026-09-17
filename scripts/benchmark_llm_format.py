"""Formatting helpers for LLM benchmark output."""

from benchmark_llm_core import BenchmarkSummary


def format_summary(summary: BenchmarkSummary) -> str:
    """Format a benchmark summary as a readable string."""
    lines = [
        f"=== {summary.target.upper()} Benchmark: {summary.model} ===",
        f"  Runs:           {summary.runs} x {len(summary.results) // summary.runs} prompts = {len(summary.results)} total",
        f"  Avg tokens/sec: {summary.avg_tokens_per_sec}",
        f"  Min tokens/sec: {summary.min_tokens_per_sec}",
        f"  Max tokens/sec: {summary.max_tokens_per_sec}",
        f"  Avg TTFT:       {summary.avg_ttft}s",
        f"  Avg total time: {summary.avg_total_time}s",
        f"  Avg tokens:     {summary.avg_token_count}",
    ]
    return "\n".join(lines)


def format_comparison(hailo: BenchmarkSummary, ollama: BenchmarkSummary) -> str:
    """Format a side-by-side comparison."""
    speedup = hailo.avg_tokens_per_sec / ollama.avg_tokens_per_sec if ollama.avg_tokens_per_sec > 0 else 0
    ttft_ratio = ollama.avg_ttft / hailo.avg_ttft if hailo.avg_ttft > 0 else 0
    lines = [
        "",
        "=== COMPARISON ===",
        f"  {'Metric':<20} {'Hailo-10H':>12} {'Ollama (CPU)':>12} {'Ratio':>8}",
        f"  {'-' * 20} {'-' * 12} {'-' * 12} {'-' * 8}",
        f"  {'Tokens/sec':<20} {hailo.avg_tokens_per_sec:>12.2f} {ollama.avg_tokens_per_sec:>12.2f} {speedup:>7.1f}x",
        f"  {'TTFT (s)':<20} {hailo.avg_ttft:>12.3f} {ollama.avg_ttft:>12.3f} {ttft_ratio:>7.1f}x",
        f"  {'Total time (s)':<20} {hailo.avg_total_time:>12.3f} {ollama.avg_total_time:>12.3f}",
        f"  {'Avg tokens':<20} {hailo.avg_token_count:>12.1f} {ollama.avg_token_count:>12.1f}",
        "",
        f"  Hailo-10H is {speedup:.1f}x {'faster' if speedup > 1 else 'slower'} than CPU inference",
    ]
    return "\n".join(lines)
