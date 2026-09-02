"""OCR type definitions: OcrRegion, OcrResult, OcrEngine ABC."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class OcrRegion:
    """OCR detected region."""
    region_id: int = 0
    bbox: list[int] = field(default_factory=list)  # [x, y, w, h]
    text: str = ""
    confidence: float = 0.0
    direction: str = "horizontal"  # horizontal | vertical
    label: str = ""  # heading, body, table, speech_bubble, sfx, etc.

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OcrResult:
    """Unified schema for OCR results."""
    id: int | None = None  # DB primary key (file_ocr_results.id)
    file_id: int | None = None
    engine: str = ""
    task: str = "ocr"  # ocr | ocr_document | ocr_manga
    regions: list[OcrRegion] = field(default_factory=list)
    full_text: str = ""
    language: str = ""
    # Document structure (for ocr_document)
    headings: list[str] = field(default_factory=list)
    tables: list[dict] = field(default_factory=list)
    page_layout: str = ""
    # Meta
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = {
            "file_id": self.file_id,
            "engine": self.engine,
            "task": self.task,
            "regions": [r.to_dict() for r in self.regions],
            "full_text": self.full_text,
            "language": self.language,
        }
        if self.task == "ocr_document":
            d["headings"] = self.headings
            d["tables"] = self.tables
            d["page_layout"] = self.page_layout
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class OcrEngine(ABC):
    """Abstract interface for OCR engines."""

    @abstractmethod
    def extract_text(self, image_path: Path, task: str = "ocr",
                     language: str = "auto") -> OcrResult:
        pass

    @abstractmethod
    def get_name(self) -> str:
        pass

    def supports_task(self, task: str) -> bool:
        return task in ("ocr",)
