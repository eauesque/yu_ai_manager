# API: /api/mdns (Descoberta de Pares)

> Versão alvo: v4.64.0 e posterior (Extensões Hailo: v4.66.0 e posterior)

API para nós yu_ai_manager em uma LAN se descobrirem mutuamente via mDNS (`_yu-ai._tcp.local.`). Há dois endpoints.

---

## GET /api/mdns/identity

### Visão Geral

Um endpoint de auto-introdução para um nó. Outros nós chamam isso durante verificação de par para confirmar que as informações anunciadas via mDNS pertencem a uma instância genuína do yu_ai_manager.

### Autenticação

**Bypass de autenticação (não obrigatório).** A autenticação é intencionalmente omitida, pois este endpoint é usado para verificação mútua de pares. A resposta contém apenas informações já disponíveis publicamente via mDNS. Nenhuma informação secreta ou sensível é incluída.

### Resposta

```json
{
  "product": "yu_ai_manager",
  "node_id": "a1b2c3d4-...",
  "version": "4.66.0",
  "capabilities": ["hailo"],
  "hailo_ollama_url": "http://192.168.1.10:11434"
}
```

| Campo | Tipo | Descrição |
|---|---|---|
| `product` | string | Sempre `"yu_ai_manager"` |
| `node_id` | string | UUID único do nó |
| `version` | string | Versão da aplicação (lida do arquivo VERSION) |
| `capabilities` | string[] | Lista de capacidades disponíveis. Atualmente apenas `"hailo"` |
| `hailo_ollama_url` | string (opcional) | URL de acesso LAN para Hailo-Ollama. Não incluído se o IP LAN não puder ser determinado |

**Condição para `capabilities` incluir `"hailo"`:** O backend `"hailo-local"` é registrado no catálogo do LLM Router.

**Condição para `hailo_ollama_url` ser incluído:** O backend `"hailo-ollama-local"` é registrado no catálogo e um IP LAN pode ser determinado. Endereços loopback (`127.0.0.1`, etc.) são reescritos para o IP LAN.

---

## GET /api/mdns/peers

### Visão Geral

Retorna uma lista de pares LAN descobertos por este nó. Destinado para verificação do status do subsistema mDNS e depuração.

### Autenticação

**Bypass de autenticação (não obrigatório).** A resposta contém apenas informações já transmitidas na LAN via mDNS.

### Resposta (Normal)

```json
{
  "running": true,
  "status": "browsing",
  "self_node_id": "a1b2c3d4-...",
  "peers": [
    {
      "node_id": "e5f6a7b8-...",
      "hostname": "raspberrypi.local",
      "version": "4.66.0",
      "llm_base_url": "http://192.168.1.20:11434",
      "llm_provider": "ollama",
      "capabilities": ["hailo"],
      "web_port": 5000,
      "addresses": ["192.168.1.20"],
      "hailo_ollama_url": "http://192.168.1.20:11434",
      "first_seen": 1712600000.0,
      "last_seen": 1712603600.0
    }
  ]
}
```

| Campo | Tipo | Descrição |
|---|---|---|
| `running` | bool | Se o subsistema mDNS está em execução |
| `status` | string | String de status do subsistema |
| `self_node_id` | string | node_id deste nó |
| `peers` | object[] | Lista de pares descobertos (veja tabela abaixo) |

**Elementos de peers:**

| Campo | Tipo | Descrição |
|---|---|---|
| `node_id` | string | UUID único do par |
| `hostname` | string | Nome de host mDNS |
| `version` | string | Versão da aplicação do par |
| `llm_base_url` | string \| null | URL do endpoint LLM do par |
| `llm_provider` | string \| null | Nome do provedor LLM (ex: `"ollama"`) |
| `capabilities` | string[] | Lista de capacidades do par |
| `web_port` | int \| null | Porta WebUI do par |
| `addresses` | string[] | Endereços IP LAN do par |
| `hailo_ollama_url` | string \| null | URL Hailo-Ollama do par |
| `first_seen` | float \| null | Hora da primeira descoberta (Unix timestamp) |
| `last_seen` | float \| null | Hora da última verificação (Unix timestamp) |

### Resposta (mDNS Não Inicializado)

```json
{
  "running": false,
  "reason": "mdns subsystem not initialised (disabled or init failed)",
  "peers": []
}
```

Quando `running: false`, mDNS está desabilitado ou a inicialização falhou. Verifique a configuração e logs de inicialização.

---

## Modo de Debug

Inicie yu com a variável de ambiente `TAGDB_DEBUG_TRUSTED_PEERS=1` para incluir campos adicionais na resposta `/api/mdns/peers`.

```json
{
  "running": true,
  "peers": [...],
  "trusted_ips": ["192.168.1.20", "192.168.1.30"],
  "bridge": {
    "managed_aliases": ["ollama-192.168.1.20"],
    "config_aliases": ["my-nas"],
    "cooldown_seconds_remaining": {
      "e5f6a7b8": 12.3
    }
  }
}
```

| Campo | Descrição |
|---|---|
| `trusted_ips` | Lista de IPs registrados no registro de IP confiável |
| `bridge.managed_aliases` | Lista de aliases gerenciados pela ponte mDNS |
| `bridge.config_aliases` | Lista de aliases definidos estaticamente em config |
| `bridge.cooldown_seconds_remaining` | Segundos restantes de cooldown chaveados pelos primeiros 8 caracteres de node_id |

**Aviso:** `trusted_ips` poderia servir como uma lista de alvo de ataque, então não é exposto por padrão. Não defina `TAGDB_DEBUG_TRUSTED_PEERS=1` em ambientes de produção.

---

## Fluxo de Descoberta mDNS

```
Outro nó inicia
    │
    ▼
Anuncia mDNS _yu-ai._tcp.local.
    │
    ▼
LlmRouterMdnsBridge recebe on_peer_added()
    │
    ▼
Verificação HTTP via GET /api/mdns/identity
    │
    ├─ Sucesso → Registrar em PeerRegistry / BackendCatalog
    └─ Falha → Tentar novamente após cooldown
```

---

## Arquivos Relacionados

- `routes/mdns_identity.py` -- Implementação de endpoint
- `core/mdns/` -- Utilitários de serviço / endereço mDNS
- `core/llm_router/state.py` -- BackendCatalog
- `core/web/trusted_peer_registry.py` -- Registro de IP confiável
- `docs/pt/mesh-inference/overview.md` -- Arquitetura geral de mesh inference
