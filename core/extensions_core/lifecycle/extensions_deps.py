"""Extension dependency graph and topological sort."""

from __future__ import annotations

import logging

from core.extensions_core.extensions_defs_dataclasses import ExtensionManifest

logger = logging.getLogger(__name__)


class DependencyError(Exception):
    """Dependency error (circular dependency, etc.)."""

    pass


def build_dependency_graph(
    manifests: dict[str, ExtensionManifest],
) -> dict[str, set[str]]:
    """Build a dependency graph from manifests.

    Returns:
        {ext_name: set(dependency ext_name)}
    """
    graph: dict[str, set[str]] = {}
    for name, manifest in manifests.items():
        deps: set[str] = set()
        ext_deps = getattr(manifest, "dependencies", None)
        if ext_deps and isinstance(ext_deps, dict):
            ext_reqs = ext_deps.get("extensions", {})
            if isinstance(ext_reqs, dict):
                deps = set(ext_reqs.keys())
        graph[name] = deps
    return graph


def topological_sort(graph: dict[str, set[str]]) -> list[str]:
    """Topological sort (Kahn's algorithm).

    Returns a load order where dependencies are loaded first.
    Raises DependencyError if circular dependencies are detected.
    """
    # Calculate in-degree (number of dependencies) for each node
    # Ignore dependencies on nodes outside the graph
    in_deg: dict[str, int] = {}
    for node in graph:
        in_deg[node] = len(graph[node] & set(graph.keys()))

    # Enqueue nodes with in-degree 0 (no dependencies = can be loaded first)
    queue = sorted([n for n, d in in_deg.items() if d == 0])
    result: list[str] = []

    while queue:
        node = queue.pop(0)
        result.append(node)
        # Decrease in-degree of nodes that depend on this node
        for other, deps in graph.items():
            if node in deps and other not in result and other not in queue:
                in_deg[other] -= 1
                if in_deg[other] == 0:
                    queue.append(other)
                    queue.sort()

    if len(result) != len(graph):
        missing = set(graph.keys()) - set(result)
        raise DependencyError(f"Circular dependency detected: {missing}")

    return result


def validate_dependencies(
    manifests: dict[str, ExtensionManifest],
    host_version: str = "0.0.0",
) -> list[tuple[str, str]]:
    """Validate dependencies.

    Returns:
        [(ext_name, error_message), ...] list of unsatisfied dependencies
    """
    from .extensions_deps_version import version_satisfies

    errors: list[tuple[str, str]] = []

    for name, manifest in manifests.items():
        deps = getattr(manifest, "dependencies", None)
        if not deps or not isinstance(deps, dict):
            continue

        # Validate host version
        host_req = deps.get("host")
        if host_req and not version_satisfies(host_version, host_req):
            errors.append(
                (name, f"Requires host {host_req}, current: {host_version}")
            )

        # Validate inter-extension dependencies
        ext_reqs = deps.get("extensions", {})
        if isinstance(ext_reqs, dict):
            for dep_name, dep_ver in ext_reqs.items():
                if dep_name not in manifests:
                    errors.append(
                        (name, f"Missing dependency: {dep_name}")
                    )
                elif dep_ver and not version_satisfies(
                    manifests[dep_name].version, dep_ver
                ):
                    errors.append(
                        (
                            name,
                            f"Dependency {dep_name} requires {dep_ver}, "
                            f"found {manifests[dep_name].version}",
                        )
                    )

    return errors


def resolve_load_order(
    manifests: dict[str, ExtensionManifest],
    host_version: str = "0.0.0",
) -> list[str]:
    """Validate dependencies and resolve load order.

    Returns all extension names even if none have dependencies.
    Raises DependencyError on failure.
    """
    # Validate dependencies
    errors = validate_dependencies(manifests, host_version)
    if errors:
        for ext_name, msg in errors:
            logger.warning("[Extension] Dependency error for %s: %s", ext_name, msg)

    # Build graph and sort
    graph = build_dependency_graph(manifests)
    return topological_sort(graph)
