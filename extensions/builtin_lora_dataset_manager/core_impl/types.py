"""Data types for LoRA Dataset Manager."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LoraProject:
    id: int = 0
    name: str = ""
    concept: str = ""
    repeat: int = 10
    base_model: str = "sdxl"
    model_scope: str = "active"
    tag_exclude: list[str] = field(default_factory=list)
    tag_preset: str = ""
    search_query: str = ""
    file_ids: list[int] = field(default_factory=list)
    created_at: int = 0
    updated_at: int = 0


@dataclass
class ExportResult:
    project_id: int = 0
    output_dir: str = ""
    image_count: int = 0
    skipped_count: int = 0
    empty_caption_count: int = 0
    errors: list[str] = field(default_factory=list)
