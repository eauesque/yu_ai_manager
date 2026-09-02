# Backend mDNS permanece como 'inacessível'

Causas, diagnóstico e resolução para o caso em que um backend adicionado por
descoberta automática mDNS do LLM Router permaneça no estado
«inacessível (unreachable)» sem se recuperar.

---

## Visão geral da estrutura

```
MdnsService (zeroconf layer)
  └─ on_peer_added / on_peer_updated / on_peer_removed
       └─ LlmRouterMdnsBridge
            ├─ _verify()       ← Verificação HTTP via /api/mdns/identity
            ├─ _apply_peer_to_catalog()  ← Registro no BackendCatalog
            ├─ _enter_cooldown() / _in_cooldown()  ← Limite de tentativas após falha
            └─ retry_pending_peers()  ← Varredura a cada 60 s (a partir de v4.91.15)
```

**Fluxo importante**:

1. zeroconf detecta um peer → `on_peer_added` é chamado
2. `_verify()` chama `/api/mdns/identity` e valida `node_id` e `product`
3. Sucesso → `_apply_peer_to_catalog()` adiciona o backend ao catálogo
4. Falha → entra em cooldown de 60 s; eventos do mesmo `node_id` são ignorados
5. **A partir de v4.91.15**: uma tarefa de varredura a cada 60 s tenta novamente os peers pendentes após expirar o cooldown

---

## Padrões frequentes de «inacessível»

### Padrão A — Primeiro verify falha → silêncio por cooldown

**Sintoma**: O backend aparece no LLM Router mas com status=unreachable.  
**Causa**:
- O servidor HTTP do nó remoto ainda não estava pronto logo após o início
- A própria porta tinha mudado e o peer referenciava um TXT antigo (bug de override `--port` antes de v4.91.14: corrigido em 35a3679a)

**Comportamento (antes de v4.91.14)**: Após expirar o cooldown (60 s) aguarda-se o próximo evento `on_peer_updated`; se não disparar, a recuperação nunca acontece.

**Comportamento (a partir de v4.91.15)**: Após expirar o cooldown, o próximo tick da varredura (no máximo 60 s depois) tenta automaticamente de novo → em caso de sucesso, o catálogo é atualizado.

---

### Padrão B — zeroconf não dispara `ServiceStateChange.Updated`

**Sintoma**: O peer foi reiniciado mas o LLM Router mantém o estado antigo.  
**Causa**: Dependendo do estado de cache do zeroconf, a alteração de um TXT pode não disparar o evento `Updated` (comportamento conhecido da biblioteca zeroconf).  
**Resolução**: A tarefa de varredura de v4.91.15 detecta isso em menos de 60 s.

---

### Padrão C — Porta do nó remoto difere do valor anunciado

**Sintoma**: curl chega ao peer mas os timeouts de verify continuam.  
**Causa**: O flag `--port` é usado na CLI mas `server.port` em config.json contém o valor antigo → porta errada anunciada no TXT mDNS.  
**Correção**: Resolvido em v4.91.14 (35a3679a): `config["server"]["port"]` é sobrescrito com a porta efetiva. Se algum script de inicialização antigo modifica config.json diretamente, verificar também esse arquivo.

---

### Padrão D — Não registrado em trusted_peer_registry

**Sintoma**: O LLM Router mostra «ready» mas o proxy para `/ext/<name>/v1/*` retorna 403.  
**Causa**: O verify foi bem-sucedido e o peer está no catálogo, mas o processo reiniciou antes de chamar `_apply_peer_to_catalog()`, ou `service_kind != "yu"` fez o registro no registry ser ignorado (peers bare Ollama não são registrados por design).  
**Verificação**:
```bash
curl -s http://127.0.0.1:PORT/api/mdns/peers | python3 -m json.tool | grep -E 'node_id|trusted'
```

---

## Passos de diagnóstico

### 1. Verificar o estado atual do peer

```bash
# Lista de peers conhecidos
curl -s http://127.0.0.1:PORT/api/mdns/peers | python3 -m json.tool

# Lista de backends do LLM Router (entradas mDNS têm alias com prefixo "mdns-")
curl -s http://127.0.0.1:PORT/api/llm_router/status | python3 -m json.tool
```

### 2. Verificar se o nó remoto alcança o próprio endpoint identity

No nó remoto:
```bash
curl -v http://<próprio-IP-LAN>:<PORT>/api/mdns/identity
```

Resposta esperada:
```json
{"product": "yu_ai_manager", "node_id": "...", "version": "..."}
```

Em caso de falha:
- Problema de firewall ou roteamento
- A porta real difere da anunciada (verificar se `--port` é usado na inicialização)

### 3. Verificar a porta anunciada

```bash
# O log de inicialização mostra "web_port"
grep -i "web_port\|mdns.*port\|effective_port" logs/app.log | tail -20

# Ou via API de settings
curl -s http://127.0.0.1:PORT/api/server/info | python3 -m json.tool | grep port
```

### 4. Verificar o estado do cooldown

GUI: **LLM Router** > cartão do backend > Detalhes mostra `last_error` e `last_seen_at`.
Se o erro for «identity verification failed», o peer é acessível mas o conteúdo não corresponde (conflito node_id / product). Se for «timeout», HTTP não chega ao peer.

### 5. Verificar os logs da varredura

```bash
grep "\[mdns\] sweep" logs/app.log
```

`sweep re-verified peer <8chars>` indica que a varredura efetuou a recuperação.

---

## Recuperação manual

Para não aguardar o próximo tick da varredura:

### Método 1: Reiniciar o nó remoto

Ao reiniciar, zeroconf dispara `ServiceStateChange.Removed` + `Added` →
`on_peer_removed` limpa o cooldown → `on_peer_added` realiza a verificação imediatamente.

### Método 2: Reiniciar o serviço mDNS pela interface de configurações

**Configurações** > **LLM Router** > botão **Reiniciar mDNS** (se disponível).

### Método 3: Reiniciar a aplicação

O cooldown existe apenas em memória. Um reinício reseta todos os cooldowns
e verifica novamente todos os peers logo após a inicialização.

---

## Pontos de prevenção

| Verificação | Método |
|---|---|
| Com `--port`, `server.port` em config.json corresponde? | Verificar config.json |
| O firewall permite tráfego de entrada em `PORT`? | `sudo ufw status` / Preferências macOS |
| Em ambiente multi-NIC, o bind está na interface LAN correta? | `mdns.bind_address` em config.json |
| Está usando v4.91.15 ou superior (com tarefa de varredura)? | `curl .../api/server/info` |

---

## Arquivos relacionados

| Arquivo | Função |
|---|---|
| `core/llm_router/mdns_integration.py` | `LlmRouterMdnsBridge`, cooldown, retry_pending_peers |
| `core/web/runtime_mdns.py` | Iniciar/parar a tarefa de varredura |
| `core/mdns/service.py` | Wrapper zeroconf, `list_peers()` |
| `core/web/trusted_peer_registry.py` | Autenticação cross-node para `/ext/*` |
