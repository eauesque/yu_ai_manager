"""WD-Tagger XMP reader (thin wrapper over core.tools.xmp)."""

from __future__ import annotations

import logging

from core.tools.xmp import read_namespaces
from core.tools.xmp.io import read_xmp_packet
from core.tools.xmp.packet import parse

logger = logging.getLogger(__name__)


def read_xmp_from_file(image_path: str) -> str | None:
    """Return the raw XMP XML packet stored in *image_path* (or ``None``)."""
    return read_xmp_packet(image_path)


def parse_xmp_dc_subject(xmp_xml: str) -> list[str]:
    """Extract ``dc:subject`` tag list from *xmp_xml*."""
    return parse(xmp_xml).get_list("dc")


def parse_xmp_wdtag_metadata(xmp_xml: str) -> dict[str, str]:
    """Extract ``wdtag:*`` namespace attributes from *xmp_xml*."""
    return parse(xmp_xml).get_attrs("wdtag")


def get_xmp_info(image_path: str) -> dict:
    """Combined view: raw packet + parsed dc:subject + wdtag attrs."""
    raw = read_xmp_packet(image_path)
    if not raw:
        return {"raw_xml": None, "dc_subject": [], "wdtag": {}}
    data = read_namespaces(image_path)
    return {
        "raw_xml": raw,
        "dc_subject": data.get_list("dc"),
        "wdtag": data.get_attrs("wdtag"),
    }
