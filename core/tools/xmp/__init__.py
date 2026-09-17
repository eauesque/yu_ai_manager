"""Generic XMP metadata layer with namespace-level merge.

Replaces the WD-Tagger-only XMP writer (which whole-packet-replaced) with a
read/merge/write pipeline so multiple subsystems (WD-Tagger, Sweep, future
extensions) can each own a namespace without trampling each other.

Public API::

    from core.tools.xmp import (
        register_namespace,
        read_namespaces,
        merge_into_file,
    )

    register_namespace("myext", "http://ns.yu-ai-manager/myext/1.0/")
    merge_into_file("foo.png", prefix="myext", attrs={"version": "1"})

The default registry already includes ``dc``, ``wdtag``, and ``sweep``.
"""

from __future__ import annotations

from core.tools.xmp.io import read_xmp_packet, write_xmp_packet
from core.tools.xmp.merge import merge_into_file, read_namespaces
from core.tools.xmp.packet import XmpData, parse, serialize
from core.tools.xmp.registry import (
    DC_NS,
    RDF_NS,
    all_namespaces,
    register_namespace,
    uri_for,
)

__all__ = [
    "DC_NS",
    "RDF_NS",
    "XmpData",
    "all_namespaces",
    "merge_into_file",
    "parse",
    "read_namespaces",
    "read_xmp_packet",
    "register_namespace",
    "serialize",
    "uri_for",
    "write_xmp_packet",
]
