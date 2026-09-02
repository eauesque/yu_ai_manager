"""Chat and agent tools for LLM MCP integration."""

from .llm_tools_common import as_error, as_json


def register_llm_agent_tools(mcp, client):
    @mcp.tool()
    def llm_chat(category: str, message: str, system_prompt: str = "", max_tokens: int = 1024, temperature: float = 0.7) -> str:
        """Send a chat message to the LLM configured for a category.

        Enables AI delegation: ask the local Ollama, remote OpenAI, or Hailo LLM.

        Args:
            category: LLM endpoint category (e.g. 'chat', 's2t_postprocess')
            message: User message to send
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": message})
        return as_json(client.post("/api/llm/chat", body={
            "category": category,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }))

    @mcp.tool()
    def llm_agent_run(category: str, message: str, system_prompt: str = "", max_rounds: int = 5, tools: str = "") -> str:
        """Run an LLM agent with tool calling against the local API.

        The LLM can call tools (search, file info, stats, etc.) to gather
        information and answer questions about the database.

        Args:
            category: LLM endpoint category (e.g. 'chat', 'hailo')
            message: User message / task for the agent
            system_prompt: Optional system prompt override
            max_rounds: Max tool-call rounds (1-8, default 5)
            tools: Tool set — 'all' includes write ops (set_tags, rate, collections), empty = read-only
        """
        if not category.strip() or not message.strip():
            return as_error("category and message are required")
        body = {
            "category": category,
            "message": message,
            "system_prompt": system_prompt,
            "max_rounds": min(max_rounds, 8),
        }
        if tools.strip():
            body["tools"] = tools.strip()
        return as_json(client.post("/api/llm/agent", body=body))

    @mcp.tool()
    def llm_agent_capabilities() -> str:
        """Get Hailo LLM agent capabilities, limitations, and delegation guidelines.

        Returns what the local 1.5B NPU agent can and cannot do, available tools,
        recommended usage patterns, and when to delegate vs keep in orchestrator.
        Read this before deciding whether to delegate a task to llm_agent_run.
        """
        return as_json(client.get("/api/llm/agent/capabilities"))
