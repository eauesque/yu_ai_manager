# Descoberta Automática de Hailo LLM

**Versão suportada**: v4.66.0 e posteriores

## Visão Geral

yu_ai_manager pode descobrir e usar automaticamente endpoints LLM em execução no Hailo NPU do Pi5 sem editar `config.json`. Basta conectar um Pi5 à LAN e outros nós yu_ai_manager podem chamar Hailo LLM.

## Dois Tipos de Endpoint

| Endpoint | Descrição | Padrão de URL Padrão |
|---|---|---|
| **yu extension Hailo LLM** | LLM compatível com OpenAI fornecido pela extensão integrada `builtin-hailo-genai` em yu_ai_manager | `http://<host>:<yu-port>/ext/hailo-genai/v1/` |
| **hailo-ollama** | LLM compatível com OpenAI fornecido pelo binário externo `/usr/bin/hailo-ollama` (porta padrão `:8000`) | `http://<host>:8000/v1/` |

Ambos podem ser executados simultaneamente e ambos são registrados automaticamente. Com HailoRT 5.3.0+ e `HAILO_OLLAMA_VDEVICE_GROUP_ID=YU_SHARED` configurado, o agendador HailoRT compartilha o dispositivo físico via round-robin, portanto não há conflito ao usar ambos simultaneamente.

## Registração Automática Local (Phase A)

Na inicialização, yu_ai_manager detecta independentemente os dois endpoints a seguir:

1. **yu extension**: Se `hailo_platform.genai.LLM` for importável e `/dev/hailo0` ou `/dev/h1x-0` existir, será registrado automaticamente como backend `hailo-local` no catálogo
   (v4.66.1 adicionou suporte para Raspberry Pi 5 + AI HAT + HailoRT 5.3.0 que expõe o dispositivo como `/dev/h1x-0`)
2. **hailo-ollama**: Uma sonda HTTP é enviada para `localhost:8000/v1/models` (timeout de 2 segundos). Se uma resposta 200 for recebida, será registrada automaticamente como backend `hailo-ollama-local`

Se um backend com o mesmo alias já existir em `llm_router.backends` em `config.json`, essa configuração tem prioridade (não será sobrescrita).

## Publicidade mDNS (Phase B)

Com base nos resultados da detecção da Phase A, yu_ai_manager publiciza as capacidades Hailo para outros nós via registros TXT mDNS:

- `capabilities=llm,hailo` -- Indica que a extensão yu está disponível
- `hailo_ollama_url=http://192.168.1.10:8000/v1/` -- Incluído apenas se hailo-ollama estiver em execução (reescrito para um IP acessível pela LAN)

Quando outros nós yu_ai_manager recebem isso via mDNS, executam verificação de identidade através do endpoint `/api/mdns/identity` e, em seguida, registram automaticamente backends adicionais com os seguintes aliases:

- `mdns-<node_id[:8]>-hailo` -- yu extension Hailo LLM (quando `capabilities` inclui `hailo`, a URL é derivada de `web_port` do peer + endereços)
- `mdns-<node_id[:8]>-hailo-ollama` -- hailo-ollama externo (quando `hailo_ollama_url` é publicizado, a URL do registro TXT é usada como está)

## Configuração

Habilitado por padrão. Você pode desabilitá-lo em `config.json` da seguinte maneira:

```json
{
  "llm_router": {
    "hailo_ollama": {
      "enabled": false,
      "port": 8000
    }
  }
}
```

- **`enabled`**: Defina como `false` para desabilitar completamente a detecção automática de hailo-ollama. A detecção da extensão yu é controlada separadamente (determinada automaticamente pela disponibilidade da extensão)
- **`port`**: Número da porta para hailo-ollama (padrão 8000). Valores fora do intervalo 1--65535 voltam ao padrão com um aviso de log

## Notas de Segurança

**hailo-ollama não possui autenticação**. Quando publicizado via mDNS, **qualquer nó na LAN pode consumir livremente os recursos de inferência do hailo-ollama**.

| Endpoint | Autenticação | Exposição Efetiva da LAN |
|---|---|---|
| yu extension (`/ext/hailo-genai/v1/`) | Cadeia de autenticação web de yu (PIN/sessão/chave API) | Apenas clientes autenticados com yu |
| hailo-ollama (`hailo_ollama_url`) | **Nenhuma** | **Todos os nós na LAN** |

Para ambientes diferentes de LANs domésticas ou VLANs confiáveis (por exemplo, Wi-Fi público), desabilite a auto-publicidade com `hailo_ollama.enabled: false`.

## Aparência no WebUI do LLM Router

Backends registrados automaticamente são exibidos no dashboard `/llm-router` (v4.65.0):

- `hailo-local` / `hailo-ollama-local` -- Detectados localmente (origem: badge `static`)
- `mdns-<id>-hailo` / `mdns-<id>-hailo-ollama` -- Descobertos via mDNS (origem: badge `mdns`)

Todos podem ser desabilitados temporariamente via o comando Disable. O estado desabilitado é persistente em `data/llm_router_state.json` e retido após reinicializações (implementado em v4.65.0).

## Segurança de Falsos Positivos

A detecção da Phase A tem dois mecanismos de segurança:

1. **Evitação de auto-sonda**: Se `hailo_ollama.port` estiver definido com o mesmo valor da porta web de yu, a sonda é completamente ignorada (evita que yu se identifique erroneamente como hailo-ollama)
2. **Prioridade de backend existente**: Se um backend com o mesmo `localhost:<port>/v1` já estiver registrado em `config.json`, a sonda é ignorada para respeitar a intenção do usuário

## Itens TODO Restantes

- (P3) Traduções multi-idioma (`en`, `zh-tw`, `zh-cn`, `ko`) -- planejadas para serem abordadas junto com o backlog de tradução do WebUI do LLM Router v4.65.0
- (P3) Testes de integração do Pi5 -- Equivalente de 16 itens do Playwright em uma configuração de 2 nós
- (P3) Suporte IPv6 -- Atualmente `_pick_lan_ip` retorna apenas IPv4
- (P3) Suporte para múltiplos dispositivos Hailo -- Assume um alias fixo `hailo-local`. Design com sufixo de índice a ser considerado para casos como múltiplos dongles USB
- (P3) `BackendCatalog.remove_backend()` -- Atualmente `_mark_unreachable` apenas atualiza o status e não remove do catálogo

## Documentação Relacionada

- [Setup do LLM Router](./setup.md)
- Design spec: `docs/superpowers/specs/2026-04-08-hailo-auto-discovery-design.md`
- Plano de implementação: `docs/superpowers/plans/2026-04-08-hailo-auto-discovery.md`

## v4.66.2 -- Autenticação de Peer Confiável (Corrigindo um Buraco Real de Autenticação de Dispositivo)

Na descoberta automática de Hailo de v4.66.0, a extensão `/ext/hailo-genai/*` de yu estava atrás da cadeia de autenticação web. Quando o driver do LLM Router (que não possui token Bearer nem sessão) tentava sondar/enviar, o middleware de autenticação retornava HTML honeypot, causando falhas de análise JSON e o backend ficava preso como `unreachable`.

### Como Funciona

- Um novo `TrustedPeerRegistry` semeia `127.0.0.1` / `::1` no tempo de inicialização
- Quando `LlmRouterMdnsBridge` verifica com sucesso um peer (GET HTTP em `/api/mdns/identity` + confirmação de correspondência de node_id), todos os endereços publicizados desse peer são adicionados ao registro
- `auth_chain.check_trusted_peer` ignora autenticação PIN ao receber uma solicitação para caminhos `/ext/<name>/v1/*` se remote_addr estiver no registro
- Os caminhos de autenticação de chave API / sessão / cookie existentes permanecem inalterados

### Relação com Quick Lock

- **loopback** (auto-sonda de yu): Sempre passa, mesmo durante quick_lock
- **peer IP**: As solicitações são rejeitadas durante quick_lock (`check_quick_lock` retorna 503). Isso significa que peers também respeitam o estado "usuário bloqueou intencionalmente"

Isso permite que os seguintes cenários funcionem conforme esperado:

- Auto-sonda `hailo-local` de pi2 (`http://localhost:5000/ext/hailo-genai/v1/models`)
- Envio cross-node de Windows para `mdns-<id>-hailo` de pi2 (`http://192.168.50.4:5000/ext/hailo-genai/v1/chat/completions`)

### Configuração

Nenhuma alteração no arquivo de configuração é necessária. Mesmo em ambientes em que mDNS está desabilitado, a semeadura de loopback ainda funciona, portanto a correção de auto-sonda está disponível incondicionalmente.

### Depuração

Defina a variável de ambiente `TAGDB_DEBUG_TRUSTED_PEERS=1` antes de iniciar yu para adicionar um campo `trusted_ips` à resposta `/api/mdns/peers`. Não defina isso em produção (a lista de confiança é essencialmente uma "lista de alvo de ataque" e não deve ser exposta em endpoints não autenticados).

### Limite de Segurança

Operando sob a suposição de "LAN confiável" (mesmo pressuposto da Phase B de v4.64.0). A proteção contra nós maliciosos com acesso físico à LAN está fora do escopo -- use o toggle Disable no WebUI `/llm-router` ou quick_lock para tais casos.

Veja `docs/superpowers/specs/2026-04-09-trusted-peer-auth-design.md` para detalhes.
