# Il backend mDNS rimane in stato 'irraggiungibile'

Cause, diagnosi e risoluzione per il caso in cui un backend aggiunto tramite
il rilevamento automatico mDNS del LLM Router rimanga nello stato
«irraggiungibile (unreachable)» senza recuperarsi.

---

## Panoramica della struttura

```
MdnsService (zeroconf layer)
  └─ on_peer_added / on_peer_updated / on_peer_removed
       └─ LlmRouterMdnsBridge
            ├─ _verify()       ← Verifica HTTP tramite /api/mdns/identity
            ├─ _apply_peer_to_catalog()  ← Registrazione in BackendCatalog
            ├─ _enter_cooldown() / _in_cooldown()  ← Limite di tentativi dopo errore
            └─ retry_pending_peers()  ← Sweep ogni 60 s (da v4.91.15)
```

**Flusso importante**:

1. zeroconf rileva un peer → viene chiamato `on_peer_added`
2. `_verify()` chiama `/api/mdns/identity` e valida `node_id` e `product`
3. Successo → `_apply_peer_to_catalog()` aggiunge il backend al catalogo
4. Fallimento → entra in cooldown di 60 s; gli eventi per lo stesso `node_id` vengono ignorati
5. **Da v4.91.15**: un task di sweep ogni 60 s riprova i peer in attesa dopo la scadenza del cooldown

---

## Scenari frequenti di «irraggiungibile»

### Scenario A — Primo verify fallisce → silenzio per cooldown

**Sintomo**: Il backend appare nel LLM Router ma con status=unreachable.  
**Causa**:
- Il server HTTP del nodo remoto non era ancora pronto subito dopo l'avvio
- La propria porta era cambiata e il peer faceva riferimento a un TXT obsoleto (bug di override `--port` prima di v4.91.14: corretto in 35a3679a)

**Comportamento (prima di v4.91.14)**: Dopo la scadenza del cooldown (60 s) si attende il prossimo evento `on_peer_updated`; se non si verifica, il ripristino non avviene mai.

**Comportamento (da v4.91.15)**: Dopo la scadenza del cooldown, il prossimo tick dello sweep (al massimo 60 s dopo) riprova automaticamente → in caso di successo il catalogo viene aggiornato.

---

### Scenario B — zeroconf non genera `ServiceStateChange.Updated`

**Sintomo**: Il peer è stato riavviato ma il LLM Router mantiene lo stato precedente.  
**Causa**: In base allo stato della cache zeroconf, il cambiamento di un TXT potrebbe non generare l'evento `Updated` (comportamento noto della libreria zeroconf).  
**Soluzione**: Il task di sweep di v4.91.15 lo rileva entro 60 s.

---

### Scenario C — La porta del nodo remoto differisce dal valore pubblicizzato

**Sintomo**: curl raggiunge il peer ma i timeout di verify continuano.  
**Causa**: Il flag `--port` viene usato da CLI ma `server.port` in config.json contiene il valore precedente → viene pubblicizzata la porta errata nel TXT mDNS.  
**Correzione**: Risolto in v4.91.14 (35a3679a): `config["server"]["port"]` viene sovrascritto con la porta effettiva. Se un vecchio script di avvio modifica direttamente config.json, verificare anche quel file.

---

### Scenario D — Non registrato in trusted_peer_registry

**Sintomo**: Il LLM Router mostra «ready» ma il proxy verso `/ext/<name>/v1/*` restituisce 403.  
**Causa**: Il verify è riuscito e il peer è nel catalogo, ma il processo è stato riavviato prima della chiamata a `_apply_peer_to_catalog()`, oppure `service_kind != "yu"` ha fatto saltare la registrazione nel registry (i peer bare Ollama non vengono registrati per progetto).  
**Verifica**:
```bash
curl -s http://127.0.0.1:PORT/api/mdns/peers | python3 -m json.tool | grep -E 'node_id|trusted'
```

---

## Passi di diagnosi

### 1. Verificare lo stato attuale del peer

```bash
# Elenco dei peer conosciuti
curl -s http://127.0.0.1:PORT/api/mdns/peers | python3 -m json.tool

# Elenco dei backend del LLM Router (le voci mDNS hanno alias con prefisso "mdns-")
curl -s http://127.0.0.1:PORT/api/llm_router/status | python3 -m json.tool
```

### 2. Verificare che il nodo remoto raggiunga il proprio endpoint identity

Dal nodo remoto:
```bash
curl -v http://<proprio-IP-LAN>:<PORT>/api/mdns/identity
```

Risposta attesa:
```json
{"product": "yu_ai_manager", "node_id": "...", "version": "..."}
```

In caso di fallimento:
- Problema di firewall o routing
- La porta reale differisce da quella pubblicizzata (verificare se viene usato `--port` all'avvio)

### 3. Verificare la porta pubblicizzata

```bash
# Il log di avvio mostra "web_port"
grep -i "web_port\|mdns.*port\|effective_port" logs/app.log | tail -20

# Oppure tramite l'API settings
curl -s http://127.0.0.1:PORT/api/server/info | python3 -m json.tool | grep port
```

### 4. Verificare lo stato del cooldown

GUI: **LLM Router** > scheda backend > Dettagli mostra `last_error` e `last_seen_at`.
Se l'errore è «identity verification failed», il peer è raggiungibile ma il contenuto non corrisponde (conflitto node_id / product). Se è «timeout», HTTP non raggiunge il peer.

### 5. Verificare i log dello sweep

```bash
grep "\[mdns\] sweep" logs/app.log
```

`sweep re-verified peer <8chars>` indica che lo sweep ha effettuato il ripristino.

---

## Ripristino manuale

Per non attendere il prossimo tick dello sweep:

### Metodo 1: Riavviare il nodo remoto

Al riavvio, zeroconf genera `ServiceStateChange.Removed` + `Added` →
`on_peer_removed` azzera il cooldown → `on_peer_added` esegue immediatamente una nuova verifica.

### Metodo 2: Riavviare il servizio mDNS dall'interfaccia delle impostazioni

**Impostazioni** > **LLM Router** > pulsante **Riavvia mDNS** (se disponibile).

### Metodo 3: Riavviare l'applicazione

Il cooldown esiste solo in memoria. Un riavvio azzera tutti i cooldown
e riverifica tutti i peer subito dopo l'avvio.

---

## Punti di prevenzione

| Controllo | Metodo |
|---|---|
| Con `--port`, `server.port` in config.json corrisponde? | Controllare config.json |
| Il firewall consente il traffico in ingresso su `PORT`? | `sudo ufw status` / Preferenze macOS |
| In ambiente multi-NIC, il bind è sull'interfaccia LAN corretta? | `mdns.bind_address` in config.json |
| Si utilizza v4.91.15 o superiore (con task di sweep)? | `curl .../api/server/info` |

---

## File correlati

| File | Ruolo |
|---|---|
| `core/llm_router/mdns_integration.py` | `LlmRouterMdnsBridge`, cooldown, retry_pending_peers |
| `core/web/runtime_mdns.py` | Avvio/arresto del task di sweep |
| `core/mdns/service.py` | Wrapper zeroconf, `list_peers()` |
| `core/web/trusted_peer_registry.py` | Autenticazione cross-node per `/ext/*` |
