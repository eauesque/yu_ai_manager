from __future__ import annotations

from core.gateway.scopes import Scope

SD_ALLOWED_ENDPOINTS: dict[tuple[str, str], Scope] = {
    ("POST", "/sdapi/v1/txt2img"):             Scope.SD_GENERATE,
    ("POST", "/sdapi/v1/img2img"):             Scope.SD_GENERATE,
    ("POST", "/sdapi/v1/extra-single-image"):  Scope.SD_GENERATE,
    ("POST", "/sdapi/v1/interrupt"):           Scope.SD_GENERATE,
    ("GET",  "/sdapi/v1/samplers"):            Scope.SD_QUERY,
    ("GET",  "/sdapi/v1/sd-models"):           Scope.SD_QUERY,
    ("GET",  "/sdapi/v1/loras"):               Scope.SD_QUERY,
    ("GET",  "/sdapi/v1/embeddings"):          Scope.SD_QUERY,
    ("GET",  "/sdapi/v1/upscalers"):           Scope.SD_QUERY,
    ("GET",  "/sdapi/v1/sd-vae"):              Scope.SD_QUERY,
    ("GET",  "/sdapi/v1/progress"):            Scope.SD_QUERY,
    ("GET",  "/sdapi/v1/scripts"):             Scope.SD_QUERY,
    ("GET",  "/sdapi/v1/script-info"):         Scope.SD_QUERY,
    ("GET",  "/sdapi/v1/cmd-flags"):           Scope.SD_QUERY,
    ("GET",  "/sdapi/v1/options"):             Scope.SD_ADMIN,
    ("POST", "/sdapi/v1/options"):             Scope.SD_ADMIN,
    ("POST", "/sdapi/v1/refresh-checkpoints"): Scope.SD_ADMIN,
    ("POST", "/sdapi/v1/refresh-vae"):         Scope.SD_ADMIN,
    ("POST", "/sdapi/v1/refresh-loras"):       Scope.SD_ADMIN,
    ("POST", "/sdapi/v1/reload-checkpoint"):   Scope.SD_ADMIN,
}

_REQ_STRIP = frozenset({
    "authorization", "x-api-key", "cookie", "host",
    "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto", "user-agent",
    "connection", "keep-alive", "te", "trailers", "transfer-encoding", "upgrade",
    "proxy-authenticate", "proxy-authorization",
})
_RESP_STRIP = frozenset({
    "server", "set-cookie",
    "connection", "keep-alive", "te", "trailers", "transfer-encoding", "upgrade",
    "proxy-authenticate", "proxy-authorization",
})


def get_sd_scope(method: str, path: str) -> Scope | None:
    return SD_ALLOWED_ENDPOINTS.get((method.upper(), path))


def filter_request_headers(headers: dict, client_ip: str) -> dict:
    out = {k: v for k, v in headers.items() if k.lower() not in _REQ_STRIP}
    out["X-Forwarded-For"] = client_ip
    return out


def filter_response_headers(headers: dict) -> dict:
    return {k: v for k, v in headers.items() if k.lower() not in _RESP_STRIP}
