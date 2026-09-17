"""Tagger framework base types and ABC."""

from __future__ import annotations

import abc
import logging
import zipfile

from .profile_types import ProfileFile, TaggerProfile, UnsupportedProfileVersion
from .profile_validation import SUPPORTED_PROFILE_VERSIONS
from .tag_result import TagPrediction, TagResult

logger = logging.getLogger(__name__)

__all__ = [
    "ProfileFile",
    "SUPPORTED_PROFILE_VERSIONS",
    "TagPrediction",
    "TagResult",
    "TaggerAdapter",
    "TaggerProfile",
    "UnsupportedProfileVersion",
]


class TaggerAdapter(abc.ABC):
    """Base class for all tagger adapter families."""

    @abc.abstractmethod
    def tag_image(self, image_path: str) -> TagResult:
        """Run inference on a single image."""

    def tag_images_batch(
        self,
        filepaths: list[str],
        batch_size: int = 8,
    ) -> list[TagResult | None]:
        """Default implementation: sequential tag_image calls."""
        _ = batch_size
        results: list[TagResult | None] = []
        for fp in filepaths:
            try:
                results.append(self.tag_image(fp))
            except FileNotFoundError:
                logger.info("tag_image skipped (file gone): %s", fp)
                results.append(None)
            except zipfile.BadZipFile as exc:
                logger.warning("tag_image skipped (bad zip): %s: %s", fp, exc)
                results.append(None)
            except Exception as exc:
                logger.warning("tag_image failed for %s: %s", fp, exc, exc_info=True)
                results.append(None)
        return results

    @abc.abstractmethod
    def get_profile(self) -> TaggerProfile:
        """Return the profile this adapter is bound to."""

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Check if the adapter is ready to use."""

    def get_name(self) -> str:
        """Human-readable engine name."""
        return self.get_profile().display_name
