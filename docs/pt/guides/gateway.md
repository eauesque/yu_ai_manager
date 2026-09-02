# Gateway — Guia de Limite de Autenticação LAN

> Versão alvo: Gateway Phase 1 (v4.75.0+) / Suporte a Gradio adicionado (v4.255.11+)

## O que é Gateway?

Gateway é um reverse proxy que protege o acesso a **ferramentas backend sem autenticação**
como SD WebUI, ComfyUI, Ollama e aplicações Gradio através de **Bearer token + modelo de scope**.

```
Clientes externos / Máquinas na LAN
    │
    │  Authorization: Bearer <api_key>
    ▼
 yu_ai_manager  (/v1/*, /sd/*, /comfy/*, /gradio/<name>/*)
 ┌────────────────────────────────────────────────────────┐
 │                      Gateway                          │
 │       verificação de scope ──► seleção de backend    │
 └────────────────────────────────────────────────────────┘
    │          │            │            │
    ▼          ▼            ▼            ▼
 Ollama    SD WebUI     ComfyUI      Gradio
 :11434     :7860         :8188        :7861
```

### Diferenças do LLM Router

| | Gateway | LLM Router |
|---|---|---|
| **Alvo** | SD WebUI, ComfyUI, Ollama, Gradio juntos | Apenas LLM (Ollama) |
| **Auth** | Bearer baseado em scope obrigatório | Loopback pode contornar |
| **Rotas proxy** | `/sd/*`, `/comfy/*`, `/v1/*`, `/gradio/<name>/*` | Apenas `/v1/*` |
| **Uso principal** | Expor ferramentas de geração externamente / na LAN com segurança | Backend para ferramentas de codificação IA |

Ambos podem ser ativados na mesma máquina.

---

## Configuração

### 1. Criar a primeira chave API (CLI)

```bash
uv run python -m core.gateway.cli create-key --id admin-local --scopes "*"
```

Exemplo de saída:
```
id:      admin-local
secret:  gw_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
(Este secret é exibido apenas uma vez. Copie agora.)
```

### 2. Adicionar ao config.json

```json
{
  "gateway": {
    "auth": {
      "mode": "api_key",
      "allow_loopback_bypass": true,
      "api_keys": [
        {
          "id": "admin-local",
          "secret_enc": "enc:v2:...",
          "scopes": ["*"],
          "allowed_models": null
        }
      ]
    },
    "backends": {
      "ollama":       {"type": "ollama",   "base_url": "http://127.0.0.1:11434"},
      "sd_webui":     {"type": "sd_webui", "base_url": "http://127.0.0.1:7860"},
      "comfyui":      {"type": "comfyui",  "base_url": "http://127.0.0.1:8188", "ws_url": "ws://127.0.0.1:8188/ws"},
      "irodori-tts":  {"type": "gradio",   "base_url": "http://127.0.0.1:7861"}
    },
    "health_probe": {"enabled": true, "interval_seconds": 10}
  }
}
```

> Use o valor criptografado no formato `enc:v2:...` gerado pela CLI para o campo `secret_enc`.  
> Não escreva secrets em texto puro diretamente no `config.json`.

### 3. Reiniciar e verificar

```bash
GW_HOST=<IP LAN desta máquina>
GW_PORT=5000
BEARER=<api-key-secret>

# 401 sem autenticação
curl -i http://$GW_HOST:$GW_PORT/v1/models

# 200 com Bearer correto
curl http://$GW_HOST:$GW_PORT/v1/models \
  -H "Authorization: Bearer $BEARER"

# Capacidades dos backends
curl http://$GW_HOST:$GW_PORT/v1/router/capabilities \
  -H "Authorization: Bearer $BEARER"

# Lista de serviços do nó
curl http://$GW_HOST:$GW_PORT/v1/node/services \
  -H "Authorization: Bearer $BEARER"
```

---

## WebUI (página /gateway)

Painel de gerenciamento acessível em `/gateway`.

### Lista de backends

Exibe o status dos backends registrados.

| Coluna | Descrição |
|---|---|
| **Tipo** | Tipo de backend (`ollama`, `sd_webui`, `comfyui`, `gradio`) |
| **Porta** | Número de porta de destino do proxy |
| **Estado** | `online` / `offline` / `unknown` |
| **Ações** | Probe (teste de conectividade), configurações |

### Scan automático de backends

Clique no botão Scan para detectar automaticamente ferramentas em execução  
nas portas locais comuns (7860, 8188, 11434, 7861, etc.) e propor registro.

### Gerenciamento de chaves API

Você também pode adicionar e revogar chaves API pela WebUI (requer uma chave com scope `*`).

---

## Referência de scopes

| Scope | Endpoints permitidos |
|---|---|
| `llm:chat` | `POST /v1/chat/completions` |
| `llm:messages` | `POST /v1/messages` (compatível Anthropic) |
| `llm:models` | `GET /v1/models` |
| `sd:generate` | `POST /sd/sdapi/v1/txt2img` etc. |
| `sd:query` | `GET /sd/sdapi/v1/samplers` etc. |
| `sd:admin` | `POST /sd/sdapi/v1/options` etc. |
| `comfy:generate` | `POST /comfy/api/prompt` etc. |
| `comfy:query` | `GET /comfy/api/queue` etc. |
| `memory:read` | `GET /agentmemory/memories` etc. (leitura) |
| `memory:write` | `POST /agentmemory/observe` etc. (escrita) |
| `memory:admin` | `POST /agentmemory/migrate` etc. (admin) |
| `ollama:proxy` | `GET/POST /ollama/<name>/*` (API nativa Ollama + compatível OpenAI, totalmente transparente) |
| `gradio:proxy` | `GET/POST /gradio/<name>/*` (totalmente transparente) |
| `gateway:admin` | Gerenciamento de chaves API e alterações de config (concedido automaticamente ao loopback) |
| `node:status` | `GET /v1/node/services` |
| `*` | Todos os scopes (apenas admin) |

### Exemplos de chaves por caso de uso

```json
"api_keys": [
  {
    "id": "claude-code",
    "secret_enc": "enc:v2:...",
    "scopes": ["llm:chat", "llm:messages", "llm:models"],
    "allowed_models": null
  },
  {
    "id": "comfy-client",
    "secret_enc": "enc:v2:...",
    "scopes": ["comfy:generate", "comfy:query"],
    "allowed_models": null
  }
]
```

---

## Proxy Ollama

Um proxy transparente para a API Ollama completa — nativa (`/api/*`) e compatível com OpenAI (`/v1/*`) —  
separado do `/v1/*` do LLM Router. Aponte `OLLAMA_HOST` para Gateway para adicionar autenticação.

### URL do proxy

```
/ollama/<backend_name>/<subpath>  →  base_url registrada/<subpath>
```

### Exemplo de configuração

```json
"backends": {
  "ollama": {"type": "ollama", "base_url": "http://127.0.0.1:11434"}
}
```

### Configuração do cliente (`OLLAMA_HOST`)

```bash
export OLLAMA_HOST=http://<gateway-host>:5000/ollama/ollama
# Todos os comandos ollama subsequentes passam pelo Gateway
ollama list
ollama run llama3.3:70b
```

> Clientes que não podem passar um Bearer token podem usar `allow_loopback_bypass: true` via loopback,  
> ou uma chave com scope `*` como solução alternativa.

### Transferência de arquivos grandes

Blobs de modelos (`/api/blobs/*`) são transmitidos em streaming sem timeout (outros caminhos: 300 s).  
Pulls e pushes de modelos de vários GB funcionam sem problemas.

---

## Proxy Gradio

Permite acesso a WebUIs baseadas em Gradio (ex. Irodori-TTS) via Gateway com autenticação Bearer.  
Implementação mínima: totalmente transparente com apenas limite de 50 MiB no corpo (sem lista branca de endpoints).

### URL do proxy

```
/gradio/<backend_name>/<subpath>  →  base_url registrada/<subpath>
```

`<backend_name>` deve corresponder a uma chave na seção `backends` do `config.json`.

### Exemplo de configuração

```json
"backends": {
  "irodori-tts": {"type": "gradio", "base_url": "http://127.0.0.1:7861"}
}
```

### Verificação

```bash
GW=http://localhost:5000
KEY=<api-key-secret>

# Raiz da aplicação Gradio
curl -H "Authorization: Bearer $KEY" "$GW/gradio/irodori-tts/"

# predict Gradio 3.x
curl -H "Authorization: Bearer $KEY" \
  -X POST "$GW/gradio/irodori-tts/run/predict" \
  -H "Content-Type: application/json" \
  -d '{"data": ["Hello"], "fn_index": 0}'
```

### Limitações

- WebSocket (`/queue/join`) não suportado — apenas HTTP
- Streams SSE Gradio 4.x (`GET /call/{api_name}/{event_id}`) são totalmente bufferizados,  
  o que pode causar timeouts para gerações longas (vídeo, etc.)

---

## Proxy Agent Memory (agentmemory)

Gateway também fornece um proxy para `@agentmemory/mcp` e outros clientes agentmemory  
para acesso seguro via LAN.

### Endpoints

```
/agentmemory/livez       → Nenhuma autenticação necessária (health check)
/agentmemory/health      → Requer scope memory:read
/agentmemory/memories    → memory:read
/agentmemory/observe     → memory:write
/agentmemory/migrate     → memory:admin
...（para lista completa, ver API oficial agentmemory）
```

### Mesma máquina

Com `allow_loopback_bypass: true`, requisições loopback (127.0.0.1) ignoram completamente a auth.  
Nenhuma alteração na configuração MCP é necessária.

### Máquina remota (LAN)

`@agentmemory/mcp` lê a variável de ambiente `AGENTMEMORY_SECRET`  
e a envia como `Authorization: Bearer <secret>` upstream.

**Exemplo de atualização da config MCP (`claude_desktop_config.json` / `.mcp.json`):**

```json
{
  "agentmemory": {
    "command": "npx",
    "args": ["-y", "@agentmemory/mcp"],
    "env": {
      "AGENTMEMORY_URL": "http://<gateway-host>:5000/agentmemory",
      "AGENTMEMORY_SECRET": "<api-key-secret>"
    }
  }
}
```

Scopes necessários (especificar ao criar a chave):

```json
"scopes": ["memory:read", "memory:write"]
```

Adicionar `memory:admin` se endpoints de migração ou governança forem necessários.

### Verificação

```bash
GW=http://<gateway-host>:5000
KEY=<api-key-secret>

# Nenhuma autenticação necessária (livez)
curl $GW/agentmemory/livez

# Obter memories com Bearer
curl -H "Authorization: Bearer $KEY" "$GW/agentmemory/memories?limit=3"

# Auth Basic também funciona (compatível com cliente SD)
curl -u "user:$KEY" "$GW/agentmemory/health"
```

---

## Modos de autenticação

| Modo | Comportamento |
|---|---|
| `api_key` | Bearer token obrigatório (`allow_loopback_bypass: true` isenta apenas loopback) |
| `loopback` | Sem auth do loopback (127.0.0.1). LAN requer equivalente a `api_key` |
| `none` | Sem auth (apenas desenvolvimento/teste, não produção) |

Com `allow_loopback_bypass: true`, ferramentas na mesma máquina  
(como Claude Code CLI) podem passar pelo Gateway sem chaves API.

---

## Health Probe

Com `health_probe.enabled: true`, os backends são sondados automaticamente  
no intervalo configurado.

```json
"health_probe": {
  "enabled": true,
  "interval_seconds": 10
}
```

Backends offline são reportados como `"status": "offline"`  
na resposta `/v1/router/capabilities`.

---

## Problemas comuns

| Sintoma | Causa / Solução |
|---|---|
| Todas as requisições retornam 401 | `allow_loopback_bypass` é `false`, então loopback também requer chave. Ou valor Bearer está incorreto |
| Proxy SD WebUI retorna 404 | Porta incorreta em `sd_webui.base_url` (padrão: 7860). Executar Probe em `/gateway` |
| WebSocket ComfyUI não conecta | Verificar se `ws_url` está configurado (`ws://127.0.0.1:8188/ws`) |
| Proxy Gradio retorna 404 | `<backend_name>` deve corresponder à chave nos backends do `config.json`. `"type": "gradio"` também necessário |
| Stream SSE Gradio timeout | Limitação de buffer completo para gerações longas (vídeo, etc.). Tarefas curtas (TTS, etc.) não são afetadas |
| 403 por scopes insuficientes | Scopes da chave API são insuficientes. Usar chave com scope `*` para adicionar novas chaves via gerenciamento de chaves API |
| Restringir a modelos específicos via `allowed_models` | Especificar como array: `"allowed_models": ["qwen2.5:7b", "llama3.3:70b"]` |

---

## Não-objetivos (escopo Phase 1)

- Start/stop/restart de backends (usar SSH + systemctl)
- `/v1/responses` (facade compatível Codex) — Phase 2+
- Balanceamento de carga em múltiplas instâncias Gateway — usar inferência distribuída LAN Cowork

---

## Documentação relacionada

- [Referência da API Gateway](../api/gateway.md) — Detalhes dos endpoints `/api/gateway/*`
- [Configuração do LLM Router](../llm-router/setup.md) — Proxy leve apenas para LLM
- [Visão geral de LAN Cowork](../lan-cowork/README.md) — Coordenação multinó

## Gerenciamento de chaves API via WebUI

Na página Configurações, aba **"Chaves API Gateway"**, crie, liste e exclua chaves.  
Um link também está disponível na [página Gateway](/gateway).

### Criar uma chave API

1. Inserir um **Label** (exemplo: `Claude Desktop`) — ID é gerado automaticamente como slug (exemplo: `claude-desktop`)
2. Selecionar **scopes** via badges (pelo menos um obrigatório)
3. Ao selecionar `*` (acesso completo), marcar a caixa de confirmação
4. Clicar em **Criar** e copiar o secret — **nunca mais exibido após sair desta tela**

### Notas

- A última chave com scope `*` não pode ser excluída (impede bloqueio de Bearer)
- Criar outra chave `*` primeiro antes de excluir a antiga

### Uso

```bash
curl -H "Authorization: Bearer <secret>" http://localhost:5000/v1/chat/completions ...
```
