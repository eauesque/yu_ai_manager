//! Namespace URI registry (mirrors Python core/tools/xmp/registry.py).
//! `wdtag` and `sweep` are the two namespaces this application writes.

const REGISTRY: &[(&str, &str)] = &[
    ("wdtag", "http://ns.yu-ai-manager/wdtag/1.0/"),
    ("sweep", "http://ns.yu-ai-manager/sweep/1.0/"),
    ("dc", "http://purl.org/dc/elements/1.1/"),
];

pub const RDF_NS: &str = "http://www.w3.org/1999/02/22-rdf-syntax-ns#";

/// Look up the URI for a known prefix (wdtag/sweep/dc). Returns `None` for
/// unregistered prefixes — callers fall back to synthetic `ns{n}` prefixes
/// (see `packet::parse`'s unknown-namespace handling).
pub fn uri_for(prefix: &str) -> Option<&'static str> {
    REGISTRY.iter().find(|(p, _)| *p == prefix).map(|(_, u)| *u)
}

/// Reverse lookup: URI to its registered prefix.
pub fn prefix_for(uri: &str) -> Option<&'static str> {
    REGISTRY.iter().find(|(_, u)| *u == uri).map(|(p, _)| *p)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn uri_for_returns_registered_namespace() {
        assert_eq!(uri_for("wdtag"), Some("http://ns.yu-ai-manager/wdtag/1.0/"));
        assert_eq!(uri_for("sweep"), Some("http://ns.yu-ai-manager/sweep/1.0/"));
    }

    #[test]
    fn uri_for_returns_none_for_unknown_prefix() {
        assert_eq!(uri_for("nope"), None);
    }

    #[test]
    fn prefix_for_is_the_reverse_of_uri_for() {
        assert_eq!(
            prefix_for("http://ns.yu-ai-manager/wdtag/1.0/"),
            Some("wdtag")
        );
        assert_eq!(prefix_for("http://example.com/unknown/"), None);
    }
}
