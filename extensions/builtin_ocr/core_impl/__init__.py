"""builtin-ocr: VLM OCR text extraction, structured document analysis, translation, export, and benchmarking."""

from .bbox_detect import detect_bboxes
from .benchmark import BenchmarkSummary, load_benchmark_set, run_benchmark
from .export import EXPORT_FORMATS, export_ocr, export_ocr_batch
from .manga_ocr_engine import (
    MangaOcrEngine,
    clear_manga_ocr_cache,
    is_manga_ocr_available,
)
from .npu_offload import NpuStatus, detect_npu, suggest_npu_optimization
from .overlay import generate_overlay
from .pdf_ocr import is_pdf_file, ocr_pdf, ocr_pdf_to_result
from .profiles import get_model_profile, list_profiles, load_profiles
from .router import OcrRouter, resolve_ocr_engine
from .store import (
    delete_ocr_result,
    ensure_ocr_tables,
    get_all_ocr_results,
    get_ocr_result,
    save_ocr_result,
)
from .translation import (
    TranslationResult,
    get_translation,
    get_translations_for_file,
    save_translation,
    translate_ocr_result,
    translate_text,
)
from .types import OcrEngine, OcrRegion, OcrResult
from .video_ocr import is_video_file, ocr_video, ocr_video_to_result
from .vlm_ocr_engine import VlmOcrEngine

__all__ = [
    "OcrRegion", "OcrResult", "OcrEngine",
    "ensure_ocr_tables", "save_ocr_result", "get_ocr_result",
    "get_all_ocr_results", "delete_ocr_result",
    "VlmOcrEngine", "OcrRouter", "resolve_ocr_engine",
    "export_ocr", "export_ocr_batch", "EXPORT_FORMATS",
    "MangaOcrEngine", "is_manga_ocr_available", "clear_manga_ocr_cache",
    "TranslationResult",
    "translate_text", "translate_ocr_result",
    "save_translation", "get_translation", "get_translations_for_file",
    "generate_overlay",
    "run_benchmark", "load_benchmark_set", "BenchmarkSummary",
    "load_profiles", "list_profiles", "get_model_profile",
    "ocr_video", "ocr_video_to_result", "is_video_file",
    "ocr_pdf", "ocr_pdf_to_result", "is_pdf_file",
    "detect_bboxes",
    "detect_npu", "suggest_npu_optimization", "NpuStatus",
]
