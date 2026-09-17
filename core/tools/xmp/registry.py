"""Namespace prefix ↔ URI registry shared across the XMP layer.

Prefixes registered here are recognized by :mod:`core.tools.xmp.packet` when
parsing existing XMP and emitted as ``xmlns:<prefix>="<uri>"`` declarations
when serializing. Unknown prefixes encountered while parsing existing files
are preserved verbatim (their URIs are stored on the parsed :class:`XmpData`
instance) so round-trips do not drop third-party namespaces.
"""

from __future__ import annotations

RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
DC_NS = "http://purl.org/dc/elements/1.1/"
X_NS = "adobe:ns:meta/"

_REGISTRY: dict[str, str] = {
    "rdf": RDF_NS,
    "dc": DC_NS,
}


def register_namespace(prefix: str, uri: str) -> None:
    """Register a prefix → URI mapping for parse/serialize."""
    if not prefix or not uri:
        raise ValueError("prefix and uri must be non-empty")
    _REGISTRY[prefix] = uri


def uri_for(prefix: str) -> str | None:
    return _REGISTRY.get(prefix)


def prefix_for(uri: str) -> str | None:
    for p, u in _REGISTRY.items():
        if u == uri:
            return p
    return None


def all_namespaces() -> dict[str, str]:
    return dict(_REGISTRY)


# Built-in tagdb namespaces. WD-Tagger has been writing the wdtag namespace
# since v4.x; sweep is new in v4.139.x and is owned by Sweep runs across the
# image-generation bridges.
register_namespace("wdtag", "http://ns.yu-ai-manager/wdtag/1.0/")
register_namespace("sweep", "http://ns.yu-ai-manager/sweep/1.0/")
