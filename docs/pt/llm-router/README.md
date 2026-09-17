# LLM Router

> Versão alvo: v4.55.0 ou posterior

## O que é LLM Router

LLM Router é um **proxy LLM compatível com OpenAI** integrado ao yu_ai_manager.  
Agrupa múltiplos backends LLM locais como Ollama, LM Studio e llama.cpp,  
e os fornece como um **único endpoint** para clientes como Claude Code, Continue e Open WebUI.

```
Cliente (Claude Code / Continue, etc.)
          │  (API compatível com OpenAI)
          ▼
    yu_ai_manager
    ┌─────────────────────────────────────────┐
    │           LLM Router                   │
    │                                         │
    │  alias: "claude-opus-4-7" ──► large    │
    │  alias: "local-coder" ──► ollama-mac/…│
    │                                         │
    │  [BackendCatalog]                       │
    │   ollama-mac  ─── 192.168.1.10:11434   │
    │   ollama-pi5  ─── 192.168.1.20:11434   │
    │   mdns-win01  ─── Backends detectados automaticamente por mDNS (alias: "mdns-<prefix>") │
    └─────────────────────────────────────────┘
```

### Capacidades

| Recurso | Recurso |
|---|---|
| **Agrupamento de múltiplos backends** | Registre qualquer número de instâncias Ollama na LAN |
| **Abstração com alias** | Oculte nomes de modelos reais com `"model": "fast"` |
| **Descoberta automática mDNS** | Registre automaticamente nós yu_ai_manager na mesma LAN sem configuração |
| **Integração com Claude Code** | Implemente `/v1/messages` compatível com Anthropic. Nenhum proxy adicional necessário |
| **Controle dinâmico ativar/desativar** | Alterne backends imediatamente da WebUI. Nenhum reinício necessário |
| **Roteamento baseado em categoria** | Selecione automaticamente modelos ideais via backends virtuais `large` / `fast` / `vision` |

---

## Arquitetura

```
Cliente (Claude Code / Continue, etc.)
    │
    │ POST /v1/chat/completions
    │ POST /v1/messages          ← Anthropic compatible
    │ GET  /v1/models
    ▼
BackendCatalog  ─── Resolução de alias ──► Backend + nome do modelo
    │
    ├─ Backends registrados manualmente (escritos em config.json)
    └─ Backends detectados automaticamente por mDNS (alias: "mdns-<prefix>")
```

**Fluxo de solicitação:**

1. Cliente solicita com `"model": "claude-opus-4-7"`
2. Router resolve `"claude-opus-4-7"` → `"large"` na tabela `aliases`
3. Selecione um backend válido da categoria `large`
4. {trans["flow_step_4"]}
5. {trans["flow_step_5"]}

---

## Índice de documentação

| Recurso | Recurso |
|---|---|
| [Configuração](setup.md) | Como escrever config.json, integração com Claude Code/Continue, configuração mDNS |
| [WebUI](webui.md) | Como operar o painel de controle `/llm-router` |
| [Descoberta automática Hailo](hailo-auto-discovery.md) | Registro automático de pares com Hailo NPU |
| [Tratamento de pares inacessíveis](mdns-peer-unreachable.md) | Solução de problemas quando pares descobertos por mDNS se tornam `unreachable` |

---

## Gateway Diferença do Gateway

| | LLM Router | Gateway |
|---|---|---|
| **Escopo** | Apenas LLM (Ollama, etc.) | SD WebUI, ComfyUI, Ollama juntos |
| **Limite de autenticação** | Local pode ser contornado. api_key necessário fora da LAN | Autenticação Bearer baseada em escopo para todos os backends |
| **Endpoints** | `/v1/*` (compatível com OpenAI/Anthropic) | `/v1/*`, `/sd/*`, `/comfy/*` |
| **Caso de uso principal** | Backend para ferramentas de codificação de IA | Exponha ferramentas de geração com segurança para clientes externos |

Ambos os recursos operam independentemente. Se você usar apenas LLM, LLM Router é suficiente.

---

## Relacionamento com LAN Cowork

Quando [LAN Cowork](../lan-cowork/README.md) está ativado,  
pares na mesma LAN são descobertos automaticamente via mDNS e registrados automaticamente  
em LLM Router com aliases como `mdns-<node_id[:8]>`.  
Um ambiente LLM multi-nó é configurado sem configuração.
