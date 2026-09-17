"""Generate compatibility golden manifest from the Python server."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from typing import Any

import httpx
import yaml
from compat_normalize import normalize_content_type, normalize_json_body
from verify_rust_compat import python_pin_login

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INVENTORY = ROOT / "docs/development/rust-migration-inventory.yaml"
DEFAULT_MANIFEST = ROOT / "tests/compat_goldens/manifest.yaml"
DEFAULT_INPUTS = ROOT / "tests/compat_goldens/inputs.yaml"


def load_parameterless_get_routes(inventory_path: Path = DEFAULT_INVENTORY) -> list[str]:
    """Load GET routes without Flask path parameters from the route inventory."""
    with inventory_path.open(encoding="utf-8") as f:
        inventory = yaml.safe_load(f)

    paths: list[str] = []
    for route in inventory.get("routes", []):
        path = route.get("path", "")
        methods = route.get("methods", [])
        if "GET" in methods and "<" not in path:
            paths.append(path)
    return paths


async def capture_route(client: httpx.AsyncClient, path: str) -> dict[str, Any]:
    """Capture a single route without reading SSE bodies."""
    try:
        async with client.stream("GET", path) as response:
            content_type = normalize_content_type(response.headers.get("content-type", ""))
            entry: dict[str, Any] = {
                "path": path,
                "method": "GET",
                "status": response.status_code,
                "content_type": content_type,
                "body": None,
            }
            if content_type == "text/event-stream":
                entry["skip"] = "sse"
                return entry

            await response.aread()
    except httpx.TimeoutException as exc:
        return {"path": path, "method": "GET", "status": None, "content_type": "", "body": None, "skip": "error", "error": f"timeout: {exc}"}
    except httpx.HTTPError as exc:
        return {"path": path, "method": "GET", "status": None, "content_type": "", "body": None, "skip": "error", "error": str(exc)}

    if content_type == "application/json":
        entry["body"] = normalize_json_body(response.json())
    return entry


async def capture_non_get_route(client: httpx.AsyncClient, ep: dict[str, Any]) -> dict[str, Any]:
    """Capture a non-GET route from the Python oracle."""
    method = ep["method"]
    path = ep["path"]
    body = ep.get("body")
    try:
        kwargs: dict[str, Any] = {}
        if body:
            kwargs["json"] = body
        if ep.get("headers"):
            kwargs["headers"] = ep["headers"]
        resp = await client.request(method, path, timeout=10.0, **kwargs)
        content_type = normalize_content_type(resp.headers.get("content-type", ""))
        entry: dict[str, Any] = {
            "path": path,
            "method": method,
            "status": resp.status_code,
            "content_type": content_type,
            "body": None,
            "note": ep.get("note", ""),
        }
        if content_type == "application/json":
            entry["body"] = normalize_json_body(resp.json())
        return entry
    except httpx.HTTPError as exc:
        return {
            "path": path,
            "method": method,
            "status": None,
            "content_type": "",
            "body": None,
            "skip": "error",
            "error": str(exc),
        }


async def generate_manifest(
    python_base: str,
    pin: str | None,
    inputs_path: Path | None = None,
    path_vars: dict[str, int | str] | None = None,
) -> list[dict[str, Any]]:
    cookies = await python_pin_login(python_base, pin) if pin else {}
    timeout = httpx.Timeout(15.0, connect=15.0, read=15.0, write=15.0, pool=15.0)
    async with httpx.AsyncClient(
        base_url=python_base,
        timeout=timeout,
        headers={"X-Requested-With": "XMLHttpRequest"},
        cookies=cookies,
    ) as client:
        entries = [await capture_route(client, path) for path in load_parameterless_get_routes()]
        if inputs_path and inputs_path.exists() and path_vars:
            from verify_rust_compat import load_inputs_endpoints

            for ep in load_inputs_endpoints(inputs_path, path_vars):
                entries.append(await capture_non_get_route(client, ep))
        return entries


def write_manifest(entries: list[dict[str, Any]], path: Path = DEFAULT_MANIFEST) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(entries, f, allow_unicode=True, sort_keys=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Rust/Python compatibility goldens")
    parser.add_argument("--python", default="http://127.0.0.1:5000", help="Python server base URL")
    parser.add_argument("--pin", default=os.environ.get("YU_TEST_PIN"), help="Python PIN")
    parser.add_argument("--output", default=str(DEFAULT_MANIFEST), help="Manifest output path")
    parser.add_argument("--inputs", default=str(DEFAULT_INPUTS), help="inputs.yaml path")
    parser.add_argument(
        "--path-vars-db",
        default=None,
        help="Seeded DB for resolving inputs.yaml variables.",
    )
    args = parser.parse_args()

    path_vars: dict[str, int | str] | None = None
    if args.path_vars_db:
        from parity_seed_helper import seed_ids_from_existing_db

        path_vars = seed_ids_from_existing_db(Path(args.path_vars_db))
    entries = asyncio.run(
        generate_manifest(
            args.python,
            args.pin,
            Path(args.inputs) if args.inputs else None,
            path_vars,
        )
    )
    output = Path(args.output)
    write_manifest(entries, output)

    captured = sum(1 for entry in entries if not entry.get("skip"))
    sse = sum(1 for entry in entries if entry.get("skip") == "sse")
    errored = sum(1 for entry in entries if entry.get("skip") == "error")
    print(f"Captured {captured} goldens / skipped {sse} SSE / errored {errored}")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
