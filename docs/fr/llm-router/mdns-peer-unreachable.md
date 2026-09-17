# Le backend mDNS reste bloqué à l'état « inaccessible »

Causes, diagnostic et résolution pour le cas où un backend ajouté par la
découverte automatique mDNS du LLM Router reste à l'état
« inaccessible (unreachable) » sans se rétablir.

---

## Vue d'ensemble de la structure

```
MdnsService (zeroconf layer)
  └─ on_peer_added / on_peer_updated / on_peer_removed
       └─ LlmRouterMdnsBridge
            ├─ _verify()       ← Vérification HTTP via /api/mdns/identity
            ├─ _apply_peer_to_catalog()  ← Enregistrement dans BackendCatalog
            ├─ _enter_cooldown() / _in_cooldown()  ← Limite de tentatives après échec
            └─ retry_pending_peers()  ← Balayage toutes les 60 s (depuis v4.91.15)
```

**Flux important** :

1. zeroconf détecte un pair → `on_peer_added` est appelé
2. `_verify()` appelle `/api/mdns/identity` et valide `node_id` et `product`
3. Succès → `_apply_peer_to_catalog()` ajoute le backend au catalogue
4. Échec → entrée en cooldown de 60 s ; les événements pour le même `node_id` sont ignorés
5. **Depuis v4.91.15** : une tâche de balayage toutes les 60 s réessaie les pairs en attente après expiration du cooldown

---

## Principaux scénarios menant à l'état « inaccessible »

### Scénario A — Premier verify échoue → silence par cooldown

**Symptôme** : Le backend apparaît dans le LLM Router mais avec status=unreachable.  
**Cause** :
- Le serveur HTTP du nœud distant n'était pas encore prêt juste après le démarrage
- Le port avait changé et le pair référençait un ancien enregistrement TXT (bug d'override `--port` avant v4.91.14 : corrigé dans 35a3679a)

**Comportement (avant v4.91.14)** : Après expiration du cooldown (60 s), on attend le prochain événement `on_peer_updated` ; s'il ne se déclenche pas, la récupération n'a jamais lieu.

**Comportement (depuis v4.91.15)** : Après expiration du cooldown, le prochain tick du balayage (au plus 60 s plus tard) relance automatiquement la vérification → en cas de succès, le catalogue est mis à jour.

---

### Scénario B — zeroconf ne déclenche pas `ServiceStateChange.Updated`

**Symptôme** : Le pair a redémarré mais le LLM Router conserve l'ancien statut.  
**Cause** : Selon l'état du cache zeroconf, l'événement `Updated` peut ne pas se déclencher lors d'un changement de TXT (comportement connu de la bibliothèque zeroconf).  
**Résolution** : La tâche de balayage de v4.91.15 le détecte en moins de 60 s.

---

### Scénario C — Le port du nœud distant diffère de la valeur annoncée

**Symptôme** : curl atteint le pair mais les timeouts de verify se répètent.  
**Cause** : Le flag `--port` est utilisé en CLI mais `server.port` dans config.json contient l'ancienne valeur → mauvais port annoncé dans le TXT mDNS.  
**Correction** : Résolu dans v4.91.14 (35a3679a) : `config["server"]["port"]` est écrasé par le port effectif. Si un ancien script de démarrage modifie directement config.json, vérifier aussi ce fichier.

---

### Scénario D — Non enregistré dans trusted_peer_registry

**Symptôme** : Le LLM Router affiche « ready » mais le proxy vers `/ext/<name>/v1/*` renvoie 403.  
**Cause** : Le verify a réussi et le pair est dans le catalogue, mais le processus a redémarré avant l'appel à `_apply_peer_to_catalog()`, ou `service_kind != "yu"` a fait sauter l'enregistrement dans le registry (les pairs bare Ollama ne sont pas enregistrés par conception).  
**Vérification** :
```bash
curl -s http://127.0.0.1:PORT/api/mdns/peers | python3 -m json.tool | grep -E 'node_id|trusted'
```

---

## Étapes de diagnostic

### 1. Vérifier l'état actuel du pair

```bash
# Liste des pairs connus
curl -s http://127.0.0.1:PORT/api/mdns/peers | python3 -m json.tool

# Liste des backends du LLM Router (les entrées mDNS ont un alias préfixé "mdns-")
curl -s http://127.0.0.1:PORT/api/llm_router/status | python3 -m json.tool
```

### 2. Vérifier que le nœud distant atteint le propre endpoint identity

Depuis le nœud distant :
```bash
curl -v http://<propre-IP-LAN>:<PORT>/api/mdns/identity
```

Réponse attendue :
```json
{"product": "yu_ai_manager", "node_id": "...", "version": "..."}
```

En cas d'échec :
- Problème de pare-feu ou de routage
- Le port réel diffère du port annoncé (vérifier si `--port` est utilisé au démarrage)

### 3. Vérifier le port annoncé

```bash
# Le log de démarrage affiche "web_port"
grep -i "web_port\|mdns.*port\|effective_port" logs/app.log | tail -20

# Ou via l'API settings
curl -s http://127.0.0.1:PORT/api/server/info | python3 -m json.tool | grep port
```

### 4. Vérifier l'état du cooldown

GUI : **LLM Router** > carte du backend > Détails affiche `last_error` et `last_seen_at`.
Si l'erreur est « identity verification failed », le pair est accessible mais le contenu ne correspond pas (conflit node_id / product). Si c'est « timeout », HTTP n'atteint pas le pair.

### 5. Vérifier les logs du balayage

```bash
grep "\[mdns\] sweep" logs/app.log
```

`sweep re-verified peer <8chars>` indique que le balayage a effectué la récupération.

---

## Récupération manuelle

Pour ne pas attendre le prochain tick du balayage :

### Méthode 1 : Redémarrer le nœud distant

Au redémarrage, zeroconf déclenche `ServiceStateChange.Removed` + `Added` →
`on_peer_removed` efface le cooldown → `on_peer_added` effectue immédiatement une nouvelle vérification.

### Méthode 2 : Redémarrer le service mDNS depuis l'interface des paramètres

**Paramètres** > **LLM Router** > bouton **Redémarrer mDNS** (si disponible).

### Méthode 3 : Redémarrer l'application

Le cooldown n'existe qu'en mémoire. Un redémarrage réinitialise tous les cooldowns
et vérifie à nouveau tous les pairs juste après le démarrage.

---

## Points de prévention

| Vérification | Méthode |
|---|---|
| Avec `--port`, `server.port` dans config.json correspond-il ? | Vérifier config.json |
| Le pare-feu autorise-t-il le trafic entrant sur `PORT` ? | `sudo ufw status` / Préférences macOS |
| En environnement multi-NIC, bind sur la bonne interface LAN ? | `mdns.bind_address` dans config.json |
| Version v4.91.15 ou supérieure utilisée (tâche de balayage incluse) ? | `curl .../api/server/info` |

---

## Fichiers associés

| Fichier | Rôle |
|---|---|
| `core/llm_router/mdns_integration.py` | `LlmRouterMdnsBridge`, cooldown, retry_pending_peers |
| `core/web/runtime_mdns.py` | Démarrage/arrêt de la tâche de balayage |
| `core/mdns/service.py` | Wrapper zeroconf, `list_peers()` |
| `core/web/trusted_peer_registry.py` | Authentification cross-node pour `/ext/*` |
