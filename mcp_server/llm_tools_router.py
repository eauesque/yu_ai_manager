"""MCP tools for LLM Router — discovery, dispatch, health, token estimate, capabilities.

These tools run inside the MCP server process and call yu_ai_manager's
HTTP API on port 5000 (the YU_BASE_URL). They're thin wrappers — all routing
logic lives in core/llm_router/ on the yu_ai_manager side.
"""

from .llm_tools_common import as_error, as_json


def register_llm_router_tools(mcp, client):
    @mcp.tool()
    def llm_backends_list() -> str:
        """List all backends and models known to the LLM router.

        Returns physical models, alias mappings, and per-backend status. Use
        this before llm_dispatch to discover what targets are available.
        """
        models_resp = client.get("/v1/models")
        physical: list[dict] = []
        aliases: dict = {}
        for m in models_resp.get("data", []):
            meta = m.get("yu_metadata") or {}
            if meta.get("type") == "alias":
                aliases[m["id"]] = {
                    "target": meta.get("target"),
                    "available": True,
                }
            else:
                physical.append(
                    {
                        "id": m["id"],
                        "backend": m.get("owned_by"),
                        "context_window": meta.get("context_window"),
                        "size_b": meta.get("size_b"),
                        "status": meta.get("backend_status", "unknown"),
                        "slo_state": meta.get("slo_state"),
                    }
                )
        return as_json({"physical": physical, "aliases": aliases, "errors": []})

    @mcp.tool()
    def llm_dispatch(
        target: str,
        messages: list,
        system: str = "",
        max_tokens: int = 1024,
        temperature: float = 0.7,
        tools: list | None = None,
    ) -> str:
        """Dispatch an OpenAI-format chat completion to a local LLM backend.

        Args:
            target: Alias or physical model name
            messages: OpenAI-style chat messages
            system: Optional system message
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            tools: Optional OpenAI-style tools schema
        """
        if not target:
            return as_error("target is required")

        msgs = list(messages or [])
        if system:
            msgs.insert(0, {"role": "system", "content": system})

        body = {
            "model": target,
            "messages": msgs,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        if tools:
            body["tools"] = tools
        return as_json(client.post("/v1/chat/completions", body=body))

    @mcp.tool()
    def llm_backend_health(backend_alias: str) -> str:
        """Force-refresh a single backend by re-polling its /v1/models endpoint.

        Use when llm_backends_list() shows stale or warning state.
        """
        if not backend_alias:
            return as_error("backend_alias is required")
        return as_json(client.post("/v1/router/refresh", body={"backend": backend_alias}))

    @mcp.tool()
    def llm_backends_refresh_all() -> str:
        """Refresh health status of all LLM backends at once.
        Use for startup checks or periodic bulk health checks.
        """
        return as_json(client.post("/api/llm_router/refresh", {}))

    @mcp.tool()
    def llm_estimate_tokens(
        target: str,
        messages: list,
        system: str = "",
    ) -> str:
        """Estimate input token count for a target model and verify the prompt fits.

        Use BEFORE llm_dispatch to avoid wasted calls that fail with
        'context length exceeded'. Tokenizer is a tiktoken cl100k approximation.
        """
        if not target:
            return as_error("target is required")
        body = {"target": target, "messages": messages or []}
        if system:
            body["system"] = system
        return as_json(client.post("/v1/router/estimate", body=body))

    @mcp.tool()
    def llm_describe_capabilities(target: str) -> str:
        """Return human-curated capability description for a target model.

        Returns good_at / weak_at / notes / context_window / size_b. Curated
        metadata is sourced from config.json llm_router.model_metadata.
        """
        if not target:
            return as_error("target is required")
        return as_json(client.get(f"/v1/router/capabilities/{target}"))

    @mcp.tool()
    def llm_backend_disable(alias: str) -> str:
        """Disable a backend by alias, excluding it from routing.

        Args:
            alias: Backend alias (URL-encoded automatically)
        """
        from urllib.parse import quote
        encoded = quote(alias, safe="")
        return as_json(client.post(f"/api/llm_router/backends/{encoded}/disable", {}))

    @mcp.tool()
    def llm_backend_enable(alias: str) -> str:
        """Re-enable a previously disabled backend by alias.

        Args:
            alias: Backend alias (URL-encoded automatically)
        """
        from urllib.parse import quote
        encoded = quote(alias, safe="")
        return as_json(client.post(f"/api/llm_router/backends/{encoded}/enable", {}))
