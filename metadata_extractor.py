"""Metadata extractor compatibility facade."""

from core.tools.metadata.extractor import extract_metadata, main

__all__ = ["extract_metadata", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
