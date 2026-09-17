from enum import StrEnum


class Scope(StrEnum):
    LLM_CHAT       = "llm:chat"
    LLM_MESSAGES   = "llm:messages"
    LLM_MODELS     = "llm:models"
    SD_GENERATE    = "sd:generate"
    SD_QUERY       = "sd:query"
    SD_ADMIN       = "sd:admin"
    COMFY_GENERATE = "comfy:generate"
    COMFY_QUERY    = "comfy:query"
    NODE_STATUS    = "node:status"
    MEMORY_READ    = "memory:read"
    MEMORY_WRITE   = "memory:write"
    MEMORY_ADMIN   = "memory:admin"
    OLLAMA_PROXY   = "ollama:proxy"
    GRADIO_PROXY   = "gradio:proxy"
    HEADROOM_READ  = "headroom:read"
    HEADROOM_ADMIN = "headroom:admin"
    GATEWAY_ADMIN  = "gateway:admin"
    WILDCARD       = "*"
