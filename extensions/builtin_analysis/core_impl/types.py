import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class AnalysisResult:
    """Unified schema for analysis results."""

    def __init__(self):
        self.tags: list[str] = []
        self.quality_score: float = 0.0
        self.quality_notes: str = ""
        self.description: str = ""
        self.style: str = ""
        self.composition: str = ""
        self.mood: str = ""
        self.color_palette: list[str] = []
        self.prompt_suggestion: str = ""
        self.raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "tags": self.tags,
            "quality_score": self.quality_score,
            "quality_notes": self.quality_notes,
            "description": self.description,
            "style": self.style,
            "composition": self.composition,
            "mood": self.mood,
            "color_palette": self.color_palette,
            "prompt_suggestion": self.prompt_suggestion,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class AnalysisEngine(ABC):
    """Abstract interface for analysis engines."""

    @abstractmethod
    def analyze_image(self, image_path: Path, existing_tags: list[str] | None = None,
                      existing_prompt: str | None = None, mode: str = "full",
                      format_json: bool = False,
                      json_schema: dict | None = None) -> AnalysisResult:
        pass

    @abstractmethod
    def analyze_prompt_trends(self, prompts: list[dict]) -> dict[str, Any]:
        pass

    @abstractmethod
    def get_name(self) -> str:
        pass
