"""LLM Inference Benchmark CLI."""

import argparse
import json

from benchmark_llm_core import DEFAULT_HAILO_URL, DEFAULT_OLLAMA_URL, DEFAULT_PROMPTS, run_benchmark, summary_to_dict
from benchmark_llm_format import format_comparison, format_summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LLM Inference Benchmark -- Hailo-10H vs Ollama",
    )
    parser.add_argument("--target", choices=["hailo", "ollama", "both"], default="both", help="Which backend to benchmark (default: both)")
    parser.add_argument("--hailo-model", default="qwen2.5-1.5b-chat", help="Hailo model name (default: qwen2.5-1.5b-chat)")
    parser.add_argument("--ollama-model", default="qwen2.5:1.5b", help="Ollama model name (default: qwen2.5:1.5b)")
    parser.add_argument("--prompt", nargs="*", help="Custom prompt(s). If not specified, uses built-in set")
    parser.add_argument("--runs", type=int, default=3, help="Number of benchmark runs per prompt (default: 3)")
    parser.add_argument("--max-tokens", type=int, default=256, help="Max tokens to generate (default: 256)")
    parser.add_argument("--temperature", type=float, default=0.7, help="Temperature (default: 0.7)")
    parser.add_argument("--hailo-url", default=DEFAULT_HAILO_URL, help=f"Hailo GenAI base URL (default: {DEFAULT_HAILO_URL})")
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL, help=f"Ollama base URL (default: {DEFAULT_OLLAMA_URL})")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    prompts = args.prompt if args.prompt else DEFAULT_PROMPTS

    print("\nLLM Inference Benchmark")
    print(f"  Target:     {args.target}")
    print(f"  Runs:       {args.runs}")
    print(f"  Max tokens: {args.max_tokens}")
    print(f"  Prompts:    {len(prompts)}")
    print()

    hailo_summary = None
    ollama_summary = None

    if args.target in ("hailo", "both"):
        print(f"[HAILO] Benchmarking {args.hailo_model}...")
        try:
            hailo_summary = run_benchmark(
                "hailo",
                args.hailo_model,
                prompts,
                args.runs,
                args.max_tokens,
                args.temperature,
                args.hailo_url,
                args.ollama_url,
            )
            print(format_summary(hailo_summary))
        except ConnectionError as e:
            print(f"[ERROR] {e}")
        print()

    if args.target in ("ollama", "both"):
        print(f"[OLLAMA] Benchmarking {args.ollama_model}...")
        try:
            ollama_summary = run_benchmark(
                "ollama",
                args.ollama_model,
                prompts,
                args.runs,
                args.max_tokens,
                args.temperature,
                args.hailo_url,
                args.ollama_url,
            )
            print(format_summary(ollama_summary))
        except ConnectionError as e:
            print(f"[ERROR] {e}")
        print()

    if hailo_summary and ollama_summary:
        print(format_comparison(hailo_summary, ollama_summary))

    if args.json:
        output = {}
        if hailo_summary:
            output["hailo"] = summary_to_dict(hailo_summary)
        if ollama_summary:
            output["ollama"] = summary_to_dict(ollama_summary)
        if hailo_summary and ollama_summary:
            speedup = hailo_summary.avg_tokens_per_sec / ollama_summary.avg_tokens_per_sec if ollama_summary.avg_tokens_per_sec > 0 else 0
            output["comparison"] = {"speedup": round(speedup, 2)}
        print("\n" + json.dumps(output, indent=2))

    print()


if __name__ == "__main__":
    main()
