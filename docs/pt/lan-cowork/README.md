# LAN Cowork

> Versão alvo: v4.55.0 em diante (autenticação PIN disponível a partir de v4.92.0)

## O que é LAN Cowork?

LAN Cowork é uma funcionalidade de extensão que permite a coordenação entre múltiplos nós yu_ai_manager em uma rede.  
Cada máquina funciona de forma independente, permitindo distribuir processamento pesado ou gerenciar coletivamente como uma Fleet.

```
┌──────────────┐    Descoberta mDNS   ┌──────────────┐
│  Windows PC  │◄──────────────────────►│   Mac Mini   │
│ (GPU ativo)  │   Emparelhamento PIN │ (Controle)   │
│              │◄──────────────────────►│              │
│  Inferência  │                      │  Gerenciamento
│ distribuída  │                      │    Fleet     │
│(tagger, etc) │                      │              │
└──────────────┘                      └──────────────┘
        ▲                                     ▲
        └─────────────────────────────────────┘
                      ▼
              ┌──────────────┐
              │ Raspberry Pi │
              │ (Hailo NPU)  │
              └──────────────┘
```

---

## Visão geral de recursos

| Recurso | Descrição |
|---|---|
| **Descoberta automática mDNS** | Descobrir automaticamente nós na mesma LAN sem configuração |
| **Emparelhamento PIN** | Autenticação PIN aprovada por administrador para emissão de tokens entre pares |
| **Inferência distribuída** | Processamento paralelo de tagger, CLIP, YOLO e Whisper em múltiplos nós |
| **Distribuição de geração** | Delegar trabalhos SD WebUI / ComfyUI para nós LAN |
| **Gerenciamento de Fleet** | Gerenciar centralmente logs e atualizações de versão em todos os nós |
| **Retransmissão de eventos de par** | Transmitir eventos de outros nós para seu próprio SSE |
| **Roteamento LLM** | Registrar automaticamente pares descobertos no LLM Router |

---

## Etapas de configuração

### 1. Ativar

Adicionar a `config.json`:

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "enabled": true,
      "peer_name": "my-desktop"
    }
  }
}
```

> **Nota**: Esta página indicava anteriormente a chave de ativação no nível superior como `{"lan_cowork": {...}}`, mas nenhuma implementação lê uma chave nesse local. A seção `extensions` acima é o local correto.

> **O padrão depende do backend:** o backend Python (híbrido) trata uma chave ausente como **ativada**, enquanto o servidor Rust independente fica **desativado** sem ativação explícita. Para saber o que realmente acontece na rede depois de ativar, consulte [Comportamento de rede](network-behavior.md).

Após reinicialização:
- Escutar outros nós em UDP 19850
- Começar a anunciar _yu-ai._tcp.local. via mDNS

### 2. Emparelhar nós

Para conectar do Nó A ao Nó B:

1. **WebUI do Nó A** → `Configurações` → `LAN Cowork` → Adicionar URL do Nó B
2. Nó A envia `POST /api/lan/pair/request`
3. **WebUI do Nó B** → `/lan-cowork/peers` → Aprovar na aba "Aprovação pendente"
4. PIN de 6 dígitos é enviado para Nó A (via SSE)
5. Nó A insere PIN → Obter token Bearer (válido por 30 dias)

> **Aviso**: Emparelhamento é unidirecional. Realize tanto A→B quanto B→A.

Consulte [Autenticação PIN entre pares e Emparelhamento de token](peer-auth.md) para detalhes.

### 3. Verificar operação

```bash
# Lista de pares descobertos (do Nó A)
curl http://localhost:5000/api/mdns/peers

# Pares reconhecidos por LAN Cowork
curl http://localhost:5000/api/lan/peers
```

---

## Configuração específica de recurso

### Inferência distribuída

A inferência distribuída fica disponível automaticamente após o emparelhamento.

- `Configurações` → `LAN Cowork` → Ativar tipos de inferência (tagger/CLIP/YOLO/Whisper) para cada nó
- Ou configurar individualmente via matriz na página `/mesh-inference`

Detalhes: [Configuração de inferência distribuída](../mesh-inference/setup.md)

### Gerenciamento de Fleet

Configurar um nó "chefe" para gerenciar outros nós:

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "fleet": {
        "chief": true,
        "allow_remote_update": true,
        "allow_update_from": [
          "<paired peer_id>"
        ]
      }
    }
  }
}
```

Detalhes: [Gerenciamento de Fleet](../features/fleet-admin.md)

### Distribuição de geração (Delegação de trabalhos SD / ComfyUI)

Distribuir automaticamente trabalhos de geração para nós equipados com GPU. Disponível via registro de backend de arquivo de configuração ou descoberta automática mDNS.  
Se o Nó B estiver executando SD WebUI / ComfyUI, ficará disponível imediatamente após a configuração.

---

## Requisitos de rede

| Porta / Protocolo | Propósito | Obrigatório |
|---|---|---|
| UDP 5353 | mDNS (descoberta de nós) | Apenas mesma LAN L2 |
| UDP 19850 | Descoberta LAN Cowork | Apenas mesma LAN L2 |
| TCP 5000 (padrão) | API, emparelhamento, inferência | Entre pares |

- mDNS não funciona além de roteadores ou VPNs (use IP fixo ou nome de host `.local`)
- Certifique-se de que UDP 5353 e TCP 5000 estão abertos na LAN no seu firewall

---

## Índice de documentação

| Documento | Conteúdo |
|---|---|
| [Autenticação PIN entre pares](peer-auth.md) | Fluxo de emparelhamento, gerenciamento de token, configuração de segurança |
| [Configuração de inferência distribuída](../mesh-inference/setup.md) | Etapas para paralelizar inferência em múltiplos nós |
| [Matriz de inferência distribuída](../mesh-inference/toggle.md) | Ativar/desativar por par e por tipo via WebUI |
| [Arquitetura de inferência distribuída](../mesh-inference/overview.md) | Design interno, roubo de trabalho, persistência |
| [Gerenciamento de Fleet](../features/fleet-admin.md) | Gerenciamento centralizado de logs remotos e atualizações de versão |
| [API de par mDNS](../api/mdns-peers.md) | Detalhes dos endpoints `/api/mdns/*` |

---

## Segurança

- mDNS não possui autenticação. **Use apenas em LANs domésticas ou redes confiáveis**
- Em Wi-Fi público ou LANs compartidas, desabilite com `"mdns": {"enabled": false}`
- Comunicação entre pares é protegida por tokens Bearer do emparelhamento PIN (armazenado como hash scrypt)
- `ip_check_mode: strict` permite apenas o IP do qual o token foi emitido (padrão)
