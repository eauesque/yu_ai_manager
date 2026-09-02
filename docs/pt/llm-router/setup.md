# Setup do LLM Router

## Adicionando a config.json

```json
{
  "llm_router": {
    "enabled": true,
    "auth": {
      "mode": "loopback",
      "api_key": "",
      "allow_loopback_bypass": true
    },
    "backends": [
      {
        "alias": "ollama-local",
        "base_url": "http://localhost:11434/v1",
        "type": "ollama",
        "auto_discover": true
      }
    ],
    "aliases": {
      "local-fast": "ollama-local/qwen2.5:7b",
      "local-coder": "ollama-local/qwen2.5-coder:32b"
    }
  }
}
```

## Integração com Claude Code

```bash
ANTHROPIC_BASE_URL=http://localhost:5000/v1 claude
```

Ao fazer solicitações, especifique um alias ou nome físico no campo `model`:
- `local-fast` (alias)
- `ollama-local/qwen2.5:7b` (nome físico)

## Integração com Continue (VSCode)

`config.json`:
```json
{
  "models": [
    {
      "title": "Local Coder",
      "provider": "openai",
      "apiBase": "http://localhost:5000/v1",
      "model": "local-coder",
      "apiKey": "dummy"
    }
  ]
}
```

## Auto-descoberta de Nós -- Suporte a Nomes de Host `.local` (Home LAN)

Ao executar múltiplas máquinas em uma home LAN (ex. Mac mini + Pi5 + máquina GPU Windows), você pode usar nomes de host `.local` em vez de endereços IP em `base_url`. Desta forma, **a configuração continua funcionando mesmo se DHCP reatribuir endereços IP**. Nenhuma implementação adicional é necessária no lado yu_ai_manager -- `httpx` resolve nomes automaticamente através do resolver do sistema operacional (Bonjour / Avahi / mDNSResponder).

```json
{
  "llm_router": {
    "enabled": true,
    "backends": [
      { "alias": "ollama-mac", "base_url": "http://mac-mini.local:11434/v1", "type": "ollama" },
      { "alias": "ollama-pi5", "base_url": "http://pi5.local:11434/v1",      "type": "ollama" },
      { "alias": "ollama-win", "base_url": "http://gpu-rig.local:11434/v1",  "type": "ollama" }
    ],
    "aliases": {
      "local-fast":  "ollama-mac/qwen2.5:7b",
      "local-coder": "ollama-pi5/qwen2.5-coder:32b",
      "local-big":   "ollama-win/llama3.3:70b"
    }
  }
}
```

Exemplo: [`config.example.local-hostname.json`](../../../config.example.local-hostname.json)

### Requisitos

| SO | Obrigatório |
|---|---|
| macOS | Bonjour (integrado, nenhuma instalação adicional necessária) |
| Linux | `avahi-daemon` (`sudo apt install avahi-daemon` / `sudo systemctl enable --now avahi-daemon`) |
| Windows 10/11 | mDNSResponder (Win10 1803 e posteriores podem resolver `.local` nativamente. Se não funcionar, instale Bonjour Print Services) |

### Verificação

```bash
# Teste se a resolução funciona
python -c "import socket; print(socket.gethostbyname('mac-mini.local'))"
# → Se retornar 192.168.x.x, está funcionando
```

### Cross-subnet / Corporate LAN / VPN

mDNS funciona via multicast L2, portanto **não pode alcançar roteadores, VPNs ou VLANs isoladas em redes corporativas**. Nestes ambientes, especifique endereços IP diretamente como antes:

```json
"backends": [
  { "alias": "remote-gpu", "base_url": "http://10.20.30.40:11434/v1", "type": "ollama" },
  { "alias": "tailscale-mac", "base_url": "http://100.x.x.x:11434/v1", "type": "ollama" }
]
```

Se você precisar de um reflector mDNS em um ambiente segmentado por VLAN, consulte seu administrador de LAN. yu_ai_manager não fornece um reflector ou proxy mDNS.

### Limitações Conhecidas

- **A resolução mDNS no Windows pode ser ocasionalmente lenta** (~1 segundo): É recomendado definir o backend `timeout` para 3 segundos ou mais
- **O sufixo `.local` é obrigatório**: Usar apenas `mac-mini` retornará a NetBIOS / DNS, então sempre escreva `mac-mini.local`
- **Ollama não publiciza via mDNS**: Apenas resolução de nome de host é usada; a porta (11434) deve ser especificada manualmente. Para Ollama colocado com yu, v4.71.0 adiciona um advertiser `_ollama._tcp.local.` no lado yu. Para nós Ollama puros bare (sem yu), veja "Tratamento de Nós Ollama Puros Bare (sem yu)" abaixo para a política

## Variáveis de Ambiente

| Variável | Comportamento |
|---|---|
| `TAGDB_DISABLE_LLM_ROUTER` | Defina como `1` para desabilitar todo o Router |
| `TAGDB_DISABLE_LLM_ROUTER_REFRESH` | Defina como `1` para desabilitar o ciclo de atualização de 5 minutos |
| `TAGDB_LLM_ROUTER_AUTH_MODE` | Sobrescrever com `none`/`loopback`/`api_key` |

## Documentação Multilingue

Seguindo as `docs/ reading rules` em CLAUDE.md, as versões `en/zh-tw/zh-cn/ko` são sincronizadas com base na fonte `ja/` (como uma tarefa separada após implementação; veja TODO.md).

## Auto-descoberta de Nós (Phase B -- v4.64.0 e posteriores)

Nós yu_ai_manager na mesma LAN se descobrem automaticamente via mDNS (`_yu-ai._tcp.local.`). Mesmo sem escrever manualmente backends em `config.json`, nós descobertos são registrados automaticamente no `BackendCatalog` com aliases `mdns-<prefix>`.

### Como Funciona

1. Na inicialização, `core/mdns/` publiciza `_yu-ai._tcp.local.`
2. Ele se inscreve em registros TXT de outros nós e verifica se as chaves obrigatórias (version/node_id/llm_base_url) estão presentes
3. Para nós com uma versão principal correspondente, envia uma GET HTTP para `http://<addr>:<web_port>/api/mdns/identity` para confirmar que product/node_id/version correspondem
4. Nós verificados são registrados no LLM Router como `BackendInfo(alias="mdns-<node_id[:8]>")`
5. A partir daí, o ciclo de sonda existente lida com atualizações periódicas

### Pré-requisitos

- O responder mDNS do sistema operacional deve estar em execução (macOS: Bonjour, Linux: Avahi, Windows: mDNSResponder)
- Nós devem estar na mesma sub-rede L2 (para cenários cross-router / VPN, use a configuração manual da Phase A)
- UDP 5353 deve ser permitido através do firewall local
- **Ollama deve estar exposto à LAN** -- Ollama se associa a `127.0.0.1:11434` por padrão, portanto não é acessível por outros nós na LAN. Defina a variável de ambiente `OLLAMA_HOST=0.0.0.0:11434` antes de iniciar Ollama (macOS: `launchctl setenv OLLAMA_HOST "0.0.0.0:11434"`, Linux: unidade systemd / `.bashrc`, Windows: variáveis de ambiente do sistema). Se não estiver definido, yu_ai_manager determinará que é apenas localhost e não publicizará `llm_base_url` (um aviso aparecerá no log de inicialização)

### Auto-descoberta de Ollama

Se não houver entrada localhost em `llm_router.backends` em `config.json`, yu_ai_manager procura por Ollama na inicialização na seguinte ordem:

1. `http://<LAN_IP>:11434/api/tags` -- Ollama acessível da LAN
2. `http://localhost:11434/api/tags` -- Mesmo se detectado, a publicidade LAN não é realizada (o aviso anterior é exibido)

Se uma resposta 200 for retornada do IP da LAN, é automaticamente incluída como `llm_base_url` no registro TXT. Isto é destinado à participação de configuração zero de nós colocados com Ollama via mDNS. Portas não padrão (11435, etc.) ou lmstudio / llamacpp ainda requerem entradas explícitas em `config.json`.

### Tratamento de Nós Ollama Puros Bare (sem yu) (política)

Nós Ollama puros bare onde `yu_ai_manager` **não** está em execução (ex. o Mac de um membro da família que tem apenas Ollama instalado, ou um contêiner Ollama em um NAS) **não são cobertos por auto-descoberta**. O próprio Ollama não possui nenhum recurso que publicize `_ollama._tcp.local.` oficialmente, portanto não há forma estrutural de detectá-los.

Para usar tais nós do LLM Router, configure-os **manualmente** via um de:

```json
{
  "llm_router": {
    "backends": [
      { "alias": "ollama-nas",    "base_url": "http://nas.local:11434/v1",     "type": "ollama" },
      { "alias": "ollama-family", "base_url": "http://192.168.1.42:11434/v1", "type": "ollama" }
    ]
  }
}
```

- Se seu ambiente suporta nomes de host `.local` (veja "Auto-descoberta de Nós -- Suporte a Nomes de Host `.local`" acima), prefira isso
- Caso contrário, hard-code o endereço IP fixo

#### Por que a auto-descoberta não é tentada

Ao projetar isto (2026-04-11), as seguintes três opções foram comparadas e a opção (c) orientação de configuração manual foi escolhida:

| Opção | Descrição | Decisão |
|---|---|---|
| (a) Varredura de toda a LAN `:11434` na inicialização | Sonda de força bruta de todos os hosts na sub-rede | **Rejeitada** -- carga de rede pesada, disruptiva em LAN corporativas / grandes, pode ser confundida com port scanning, contradiz a filosofia edge-first |
| (b) Daemon advertiser externo de Ollama | Forneça um advertiser leve fornecido por yu que é executado junto com cada host Ollama | **Rejeitada** -- requer um processo residente adicional, equivalente a instalar `yu_ai_manager`. Derrota o ponto de "puro bare" |
| (c) Configuração manual de backend via IP fixo / `.local` | Entradas escritas à mão em `config.json` | **Escolhida** -- implementação zero adicional, comportamento explícito, evita arrastar usuários para varreduras não intencionais |

Se Ollama upstream posteriormente publicizar `_ollama._tcp.local.` oficialmente, ou adicionar um mecanismo oficial de descoberta de serviço, revisitaremos isto como Phase D naquele momento.

### Desabilitação

Você pode desabilitar a auto-descoberta em ambientes onde não é necessária (isolamento Docker, LAN corporativa, CI, etc.):

- Adicione `"mdns": {"enabled": false}` a `config.json`
- Ou defina a variável de ambiente `YU_AI_MDNS_DISABLED=1`

### Comportamentos Conhecidos

- **Ambientes multi-homed (Wi-Fi + Ethernet)**: Com a configuração padrão (`bind_address: null`), a publicidade ocorre em ambas as interfaces e `PeerInfo.addresses` conterá múltiplos IPs. Para restringir a uma única interface, especifique `"bind_address": "192.168.x.y"`.
- **Colisão de alias**: Se um backend em `config.json` usar um alias no formato `mdns-xxxxxxxx`, a configuração manual tem prioridade e a entrada descoberta via mDNS é ignorada.
- **Cross-subnet**: mDNS funciona apenas dentro do domínio de broadcast L2 por padrão. Para operação cross-subnet, use a abordagem de nome de host `.local` da Phase A.
- **Segurança**: mDNS em si não possui autenticação. É projetado para ambientes confiáveis como home LANs. A desabilitação é recomendada em Wi-Fi público ou redes compartilhadas grandes. A verificação `/api/mdns/identity` previne identificação incorreta acidental de nós ou mistura de versões mais antigas incompatíveis.
