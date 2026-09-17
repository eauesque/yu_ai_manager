"""WD-Tagger XMP writer (thin wrapper over core.tools.xmp).

Historically this module owned the PNG/JPEG/WebP XMP write logic and
*replaced* the entire XMP packet on every write — which destroyed any other
namespace (Sweep, future extensions) that another subsystem had previously
written. The actual byte-pushing now lives in :mod:`core.tools.xmp.io` and
the namespace-aware merge happens in :mod:`core.tools.xmp.merge`.

``write_xmp_to_file`` keeps its old signature (raw XMP XML in) but routes
through the merge layer: it parses the incoming packet, iterates each
namespace's attrs and list items, and merges them into whatever XMP is
already on the file. WD-Tagger writes via ``build_xmp_packet`` which only
emits the ``wdtag`` and ``dc`` namespaces, so any pre-existing ``sweep:*``
attrs survive the round-trip.
"""

from __future__ import annotations

import logging

from core.tools.xmp import merge_into_file
from core.tools.xmp.packet import parse

logger = logging.getLogger(__name__)


def write_xmp_to_file(image_path: str, xmp_xml: str) -> bool:
    """Merge the namespaces from *xmp_xml* into *image_path*'s XMP packet."""
    parsed = parse(xmp_xml)
    if not parsed.attrs and not parsed.list_items:
        logger.warning("write_xmp_to_file got an empty/unparseable packet")
        return False

    ok = True
    for prefix, attrs in parsed.attrs.items():
        if not merge_into_file(image_path, prefix=prefix, attrs=attrs):
            ok = False
    for prefix, items in parsed.list_items.items():
        elem = parsed.list_element_name.get(prefix, "items")
        if not merge_into_file(
            image_path, prefix=prefix,
            list_items=items, list_element_name=elem,
        ):
            ok = False
    return ok
