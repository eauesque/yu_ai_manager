"""3a: Auto benchmark -- automatically measure OCR engine accuracy.

Runs OCR on bundled test sets (data/ocr_benchmarks/) or user-specified images
and calculates match rate against expected text.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .types import OcrEngine

logger = logging.getLogger(__name__)

# Bundled benchmark image directory
_BENCHMARK_DIR = Path(__file__).resolve().parent.parent / "benchmarks"


@dataclass
class BenchmarkCase:
    """Benchmark test case."""
    image_path: str
    expected_text: str
    task: str = "ocr"
    language: str = "auto"
    tags: list[str] = field(default_factory=list)  # e.g. ["cjk", "handwritten"]


@dataclass
class BenchmarkResult:
    """Result of a single benchmark case."""
    case_name: str
    task: str
    expected_text: str
    actual_text: str
    similarity: float  # 0.0 - 1.0
    char_accuracy: float  # Character-level match rate
    elapsed_ms: int
    engine: str
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BenchmarkSummary:
    """Overall benchmark summary."""
    engine: str
    total_cases: int
    avg_similarity: float
    avg_char_accuracy: float
    avg_elapsed_ms: float
    results: list[BenchmarkResult] = field(default_factory=list)
    task_scores: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["results"] = [r.to_dict() for r in self.results]
        return d


def _validate_benchmark_dir(benchmark_dir: str) -> Path:
    """Validate benchmark_dir path and return a safe Path.

    パストラバーサルを防止するため、以下を検証:
    - '..' コンポーネントを含まないこと
    - 実在するディレクトリであること
    - null バイトを含まないこと
    """
    if "\x00" in benchmark_dir:
        raise ValueError("Invalid benchmark_dir: null byte detected")
    root = _BENCHMARK_DIR.resolve()
    bdir = Path(benchmark_dir).resolve()
    # Re-check '..' in normalized path (already resolved, but for safety)
    if ".." in Path(benchmark_dir).parts:
        raise ValueError(
            f"Invalid benchmark_dir: '..' traversal not allowed: {benchmark_dir}"
        )
    if not bdir.is_dir():
        raise ValueError(
            f"Invalid benchmark_dir: not an existing directory: {benchmark_dir}"
        )
    try:
        bdir.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"Invalid benchmark_dir: must be inside benchmark root: {root}"
        ) from exc
    return bdir


def _contain_under(root: Path, relative_path: str) -> Path:
    """Resolve each relative path component without allowing symlink escape."""
    if "\x00" in relative_path:
        raise ValueError("Invalid benchmark entry")
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Invalid benchmark entry")
    resolved_root = root.resolve()
    candidate = resolved_root
    for part in relative.parts:
        if part in ("", "."):
            continue
        candidate = (candidate / part).resolve(strict=False)
        try:
            candidate.relative_to(resolved_root)
        except ValueError as exc:
            raise ValueError("Invalid benchmark entry") from exc
    return candidate


def load_benchmark_set(
    benchmark_dir: str | None = None,
) -> list[BenchmarkCase]:
    """Load a benchmark set.

    Reads manifest.json in benchmark_dir or
    auto-detects image + .txt pairs.
    """
    bdir = _validate_benchmark_dir(benchmark_dir) if benchmark_dir else _BENCHMARK_DIR
    if not bdir.exists():
        return []

    manifest = bdir / "manifest.json"
    if manifest.exists():
        return _load_from_manifest(manifest, bdir)

    # Auto-detect: image file + matching .txt
    return _auto_detect_cases(bdir)


def _load_from_manifest(
    manifest: Path, base_dir: Path,
) -> list[BenchmarkCase]:
    """Load cases from manifest.json."""
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to load benchmark manifest: %s", exc)
        return []

    cases = []
    for item in data.get("cases", []):
        try:
            img = _contain_under(base_dir, item["image"])
        except (KeyError, TypeError, ValueError):
            logger.warning("Invalid benchmark image entry")
            continue
        if not img.exists():
            logger.warning("Benchmark image not found: %s", item["image"])
            continue
        cases.append(BenchmarkCase(
            image_path=str(img),
            expected_text=item.get("expected_text", ""),
            task=item.get("task", "ocr"),
            language=item.get("language", "auto"),
            tags=item.get("tags", []),
        ))
    return cases


def _auto_detect_cases(bdir: Path) -> list[BenchmarkCase]:
    """auto-detects image + .txt pairs."""
    IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    cases = []
    for img in sorted(bdir.iterdir()):
        if img.suffix.lower() not in IMAGE_EXTS:
            continue
        try:
            txt = _contain_under(bdir, img.with_suffix(".txt").name)
        except ValueError:
            logger.warning("Invalid benchmark text entry")
            continue
        if not txt.exists():
            continue
        expected = txt.read_text(encoding="utf-8").strip()
        # Infer task from filename
        task = "ocr"
        name_lower = img.stem.lower()
        if "manga" in name_lower or "comic" in name_lower:
            task = "ocr_manga"
        elif "doc" in name_lower or "invoice" in name_lower:
            task = "ocr_document"
        cases.append(BenchmarkCase(
            image_path=str(img),
            expected_text=expected,
            task=task,
        ))
    return cases


def run_benchmark(
    engine: OcrEngine,
    cases: list[BenchmarkCase] | None = None,
    benchmark_dir: str | None = None,
) -> BenchmarkSummary:
    """Run a benchmark.

    Args:
        engine: テスト対象の OCR エンジン
        cases: テストケース (None なら同梱セットを使用)
        benchmark_dir: カスタムベンチマークディレクトリ

    Returns:
        BenchmarkSummary
    """
    if cases is None:
        cases = load_benchmark_set(benchmark_dir)

    if not cases:
        return BenchmarkSummary(
            engine=engine.get_name(),
            total_cases=0,
            avg_similarity=0.0,
            avg_char_accuracy=0.0,
            avg_elapsed_ms=0.0,
        )

    results: list[BenchmarkResult] = []
    task_scores: dict[str, list[float]] = {}

    for case in cases:
        r = _run_single_case(engine, case)
        results.append(r)
        task_scores.setdefault(r.task, []).append(r.similarity)

    # Calculate summary
    valid = [r for r in results if not r.error]
    avg_sim = sum(r.similarity for r in valid) / len(valid) if valid else 0.0
    avg_acc = sum(r.char_accuracy for r in valid) / len(valid) if valid else 0.0
    avg_ms = sum(r.elapsed_ms for r in valid) / len(valid) if valid else 0.0

    return BenchmarkSummary(
        engine=engine.get_name(),
        total_cases=len(cases),
        avg_similarity=round(avg_sim, 4),
        avg_char_accuracy=round(avg_acc, 4),
        avg_elapsed_ms=round(avg_ms, 1),
        results=results,
        task_scores={
            k: round(sum(v) / len(v), 4) for k, v in task_scores.items()
        },
    )


def _run_single_case(
    engine: OcrEngine, case: BenchmarkCase,
) -> BenchmarkResult:
    """Run a single case."""
    case_name = Path(case.image_path).stem
    t0 = time.monotonic()

    try:
        result = engine.extract_text(
            Path(case.image_path),
            task=case.task,
            language=case.language,
        )
        elapsed = int((time.monotonic() - t0) * 1000)
        actual = result.full_text.strip()
    except Exception as exc:
        elapsed = int((time.monotonic() - t0) * 1000)
        return BenchmarkResult(
            case_name=case_name,
            task=case.task,
            expected_text=case.expected_text,
            actual_text="",
            similarity=0.0,
            char_accuracy=0.0,
            elapsed_ms=elapsed,
            engine=engine.get_name(),
            error=str(exc),
        )

    sim = _text_similarity(case.expected_text, actual)
    char_acc = _char_accuracy(case.expected_text, actual)

    return BenchmarkResult(
        case_name=case_name,
        task=case.task,
        expected_text=case.expected_text,
        actual_text=actual,
        similarity=round(sim, 4),
        char_accuracy=round(char_acc, 4),
        elapsed_ms=elapsed,
        engine=engine.get_name(),
    )


def _text_similarity(expected: str, actual: str) -> float:
    """SequenceMatcher-based text similarity (0.0-1.0)."""
    if not expected and not actual:
        return 1.0
    if not expected or not actual:
        return 0.0
    return SequenceMatcher(None, expected, actual).ratio()


def _char_accuracy(expected: str, actual: str) -> float:
    """Character-level match rate (correct chars / expected chars)."""
    if not expected:
        return 1.0 if not actual else 0.0
    # Position-independent character count
    exp_set = list(expected)
    act_set = list(actual)
    matched = 0
    used = [False] * len(act_set)
    for c in exp_set:
        for i, a in enumerate(act_set):
            if not used[i] and a == c:
                matched += 1
                used[i] = True
                break
    return matched / len(exp_set) if exp_set else 0.0
