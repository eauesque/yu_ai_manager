# Gateway — Guide des limites d'authentification LAN

> Version cible : Gateway Phase 1 (v4.75.0+) / Support Gradio ajouté (v4.255.11+)

## Qu'est-ce que Gateway ?

Gateway est un reverse proxy qui protège l'accès aux **outils backend sans authentification**
tels que SD WebUI, ComfyUI, Ollama et les applications Gradio via un **Bearer token + modèle de scope**.

```
Clients externes / Machines du LAN
    │
    │  Authorization: Bearer <api_key>
    ▼
 yu_ai_manager  (/v1/*, /sd/*, /comfy/*, /gradio/<name>/*)
 ┌────────────────────────────────────────────────────────┐
 │                      Gateway                          │
 │       vérification du scope ──► sélection du backend │
 └────────────────────────────────────────────────────────┘
    │          │            │            │
    ▼          ▼            ▼            ▼
 Ollama    SD WebUI     ComfyUI      Gradio
 :11434     :7860         :8188        :7861
```

### Différences avec LLM Router

| | Gateway | LLM Router |
|---|---|---|
| **Cible** | SD WebUI, ComfyUI, Ollama, Gradio ensemble | LLM (Ollama) uniquement |
| **Auth** | Bearer basé sur les scopes requis | Le loopback peut contourner |
| **Routes proxy** | `/sd/*`, `/comfy/*`, `/v1/*`, `/gradio/<name>/*` | Uniquement `/v1/*` |
| **Usage principal** | Exposer les outils de génération en externe / sur LAN en sécurité | Backend pour les outils de codage IA |

Les deux peuvent être activés sur la même machine.

---

## Installation

### 1. Créer la première clé API (CLI)

```bash
uv run python -m core.gateway.cli create-key --id admin-local --scopes "*"
```

Exemple de sortie :
```
id:      admin-local
secret:  gw_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
(Ce secret n'est affiché qu'une seule fois. Copiez-le maintenant.)
```

### 2. Ajouter à config.json

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

> Utilisez la valeur chiffrée au format `enc:v2:...` générée par la CLI pour le champ `secret_enc`.  
> N'écrivez pas les secrets en clair directement dans `config.json`.

### 3. Redémarrer et vérifier

```bash
GW_HOST=<IP LAN de cette machine>
GW_PORT=5000
BEARER=<api-key-secret>

# 401 sans authentification
curl -i http://$GW_HOST:$GW_PORT/v1/models

# 200 avec le Bearer correct
curl http://$GW_HOST:$GW_PORT/v1/models \
  -H "Authorization: Bearer $BEARER"

# Capacités des backends
curl http://$GW_HOST:$GW_PORT/v1/router/capabilities \
  -H "Authorization: Bearer $BEARER"

# Liste des services du nœud
curl http://$GW_HOST:$GW_PORT/v1/node/services \
  -H "Authorization: Bearer $BEARER"
```

---

## WebUI (page /gateway)

Tableau de bord de gestion accessible via `/gateway`.

### Liste des backends

Affiche le statut des backends enregistrés.

| Colonne | Description |
|---|---|
| **Type** | Type de backend (`ollama`, `sd_webui`, `comfyui`, `gradio`) |
| **Port** | Numéro de port de destination du proxy |
| **État** | `online` / `offline` / `unknown` |
| **Actions** | Probe (test de connectivité), paramètres |

### Scan automatique des backends

Cliquez sur le bouton Scan pour détecter automatiquement les outils en cours d'exécution  
sur les ports locaux courants (7860, 8188, 11434, 7861, etc.) et proposer leur enregistrement.

### Gestion des clés API

Vous pouvez également ajouter et révoquer des clés API depuis la WebUI (nécessite une clé avec le scope `*`).

---

## Référence des scopes

| Scope | Points de terminaison autorisés |
|---|---|
| `llm:chat` | `POST /v1/chat/completions` |
| `llm:messages` | `POST /v1/messages` (compatible Anthropic) |
| `llm:models` | `GET /v1/models` |
| `sd:generate` | `POST /sd/sdapi/v1/txt2img` etc. |
| `sd:query` | `GET /sd/sdapi/v1/samplers` etc. |
| `sd:admin` | `POST /sd/sdapi/v1/options` etc. |
| `comfy:generate` | `POST /comfy/api/prompt` etc. |
| `comfy:query` | `GET /comfy/api/queue` etc. |
| `memory:read` | `GET /agentmemory/memories` etc. (lecture) |
| `memory:write` | `POST /agentmemory/observe` etc. (écriture) |
| `memory:admin` | `POST /agentmemory/migrate` etc. (admin) |
| `ollama:proxy` | `GET/POST /ollama/<name>/*` (API native Ollama + compatible OpenAI, transparence totale) |
| `gradio:proxy` | `GET/POST /gradio/<name>/*` (transparence totale) |
| `gateway:admin` | Gestion des clés API et modifications de config (accordé automatiquement au loopback) |
| `node:status` | `GET /v1/node/services` |
| `*` | Tous les scopes (admin uniquement) |

### Exemples de clés par cas d'usage

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

Un proxy transparent pour l'API Ollama complète — native (`/api/*`) et compatible OpenAI (`/v1/*`) —  
séparé du `/v1/*` du LLM Router. Pointez `OLLAMA_HOST` vers Gateway pour ajouter l'authentification.

### URL du proxy

```
/ollama/<backend_name>/<subpath>  →  base_url enregistrée/<subpath>
```

### Exemple de configuration

```json
"backends": {
  "ollama": {"type": "ollama", "base_url": "http://127.0.0.1:11434"}
}
```

### Configuration du client (`OLLAMA_HOST`)

```bash
export OLLAMA_HOST=http://<gateway-host>:5000/ollama/ollama
# Toutes les commandes ollama suivantes passent par Gateway
ollama list
ollama run llama3.3:70b
```

> Les clients qui ne peuvent pas transmettre de Bearer token peuvent utiliser `allow_loopback_bypass: true` via loopback,  
> ou une clé avec le scope `*` comme solution de contournement.

### Transfert de fichiers volumineux

Les blobs de modèles (`/api/blobs/*`) sont streamés sans timeout (autres chemins : 300 s).  
Les pulls et pushes de modèles de plusieurs Go fonctionnent sans problème.

---

## Proxy Gradio

Permet l'accès aux WebUI basées sur Gradio (ex. Irodori-TTS) via Gateway avec authentification Bearer.  
Implémentation minimale : transparence totale avec seulement une limite de 50 MiB sur le corps (pas de liste blanche d'endpoints).

### URL du proxy

```
/gradio/<backend_name>/<subpath>  →  base_url enregistrée/<subpath>
```

`<backend_name>` doit correspondre à une clé dans la section `backends` de `config.json`.

### Exemple de configuration

```json
"backends": {
  "irodori-tts": {"type": "gradio", "base_url": "http://127.0.0.1:7861"}
}
```

### Vérification

```bash
GW=http://localhost:5000
KEY=<api-key-secret>

# Racine de l'application Gradio
curl -H "Authorization: Bearer $KEY" "$GW/gradio/irodori-tts/"

# predict Gradio 3.x
curl -H "Authorization: Bearer $KEY" \
  -X POST "$GW/gradio/irodori-tts/run/predict" \
  -H "Content-Type: application/json" \
  -d '{"data": ["Hello"], "fn_index": 0}'
```

### Limitations

- WebSocket (`/queue/join`) non supporté — HTTP uniquement
- Les streams SSE Gradio 4.x (`GET /call/{api_name}/{event_id}`) sont entièrement bufferisés,  
  ce qui peut causer des timeouts pour les générations longues (vidéo, etc.)

---

## Proxy Agent Memory (agentmemory)

Gateway fournit également un proxy pour `@agentmemory/mcp` et d'autres clients agentmemory  
pour un accès sécurisé sur LAN.

### Points de terminaison

```
/agentmemory/livez       → Aucune authentification requise (health check)
/agentmemory/health      → Nécessite le scope memory:read
/agentmemory/memories    → memory:read
/agentmemory/observe     → memory:write
/agentmemory/migrate     → memory:admin
...（pour la liste complète, voir l'API officielle agentmemory）
```

### Même machine

Avec `allow_loopback_bypass: true`, les requêtes loopback (127.0.0.1) contournent entièrement l'auth.  
Aucune modification de la configuration MCP n'est nécessaire.

### Machine distante (LAN)

`@agentmemory/mcp` lit la variable d'environnement `AGENTMEMORY_SECRET`  
et l'envoie comme `Authorization: Bearer <secret>` en amont.

**Exemple de mise à jour de la config MCP (`claude_desktop_config.json` / `.mcp.json`) :**

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

Scopes requis (à spécifier lors de la création de la clé) :

```json
"scopes": ["memory:read", "memory:write"]
```

Ajouter `memory:admin` si les endpoints de migration ou de gouvernance sont nécessaires.

### Vérification

```bash
GW=http://<gateway-host>:5000
KEY=<api-key-secret>

# Aucune authentification requise (livez)
curl $GW/agentmemory/livez

# Récupérer les memories avec Bearer
curl -H "Authorization: Bearer $KEY" "$GW/agentmemory/memories?limit=3"

# L'auth Basic fonctionne aussi (compatible client SD)
curl -u "user:$KEY" "$GW/agentmemory/health"
```

---

## Modes d'authentification

| Mode | Comportement |
|---|---|
| `api_key` | Bearer token requis (`allow_loopback_bypass: true` exempte uniquement le loopback) |
| `loopback` | Pas d'auth depuis loopback (127.0.0.1). Le LAN requiert l'équivalent `api_key` |
| `none` | Pas d'auth (développement/test uniquement, pas en production) |

Avec `allow_loopback_bypass: true`, les outils sur la même machine  
(comme Claude Code CLI) peuvent passer par Gateway sans clé API.

---

## Health Probe

Avec `health_probe.enabled: true`, les backends sont sondés automatiquement  
à l'intervalle configuré.

```json
"health_probe": {
  "enabled": true,
  "interval_seconds": 10
}
```

Les backends hors ligne sont signalés comme `"status": "offline"`  
dans la réponse `/v1/router/capabilities`.

---

## Problèmes courants

| Symptôme | Cause / Solution |
|---|---|
| Toutes les requêtes renvoient 401 | `allow_loopback_bypass` est `false`, donc le loopback nécessite aussi une clé. Ou la valeur Bearer est incorrecte |
| Le proxy SD WebUI renvoie 404 | Port incorrect dans `sd_webui.base_url` (défaut : 7860). Lancer Probe depuis `/gateway` |
| WebSocket ComfyUI ne se connecte pas | Vérifier que `ws_url` est configuré (`ws://127.0.0.1:8188/ws`) |
| Le proxy Gradio renvoie 404 | `<backend_name>` doit correspondre à la clé dans les backends `config.json`. `"type": "gradio"` également requis |
| Stream SSE Gradio timeout | Limitation du buffer complet pour les générations longues (vidéo, etc.). Les tâches courtes (TTS, etc.) ne sont pas affectées |
| 403 pour scopes insuffisants | Les scopes de la clé API sont insuffisants. Utiliser une clé avec le scope `*` pour ajouter de nouvelles clés |
| Restreindre à des modèles spécifiques via `allowed_models` | Spécifier comme tableau : `"allowed_models": ["qwen2.5:7b", "llama3.3:70b"]` |

---

## Non-objectifs (périmètre Phase 1)

- Démarrage/arrêt/redémarrage des backends (utiliser SSH + systemctl)
- `/v1/responses` (facade compatible Codex) — Phase 2+
- Équilibrage de charge sur plusieurs instances Gateway — utiliser l'inférence distribuée LAN Cowork

---

## Documentation associée

- [Référence API Gateway](../api/gateway.md) — Détails des endpoints `/api/gateway/*`
- [Configuration LLM Router](../llm-router/setup.md) — Proxy léger LLM uniquement
- [Vue d'ensemble LAN Cowork](../lan-cowork/README.md) — Coordination multi-nœuds

## Gestion des clés API via WebUI

Depuis l'onglet **« Clés API Gateway »** de la page Paramètres, créez, listez et supprimez des clés.  
Un lien est également disponible sur la [page Gateway](/gateway).

### Créer une clé API

1. Saisir un **Label** (exemple : `Claude Desktop`) — l'ID est auto-généré en slug (exemple : `claude-desktop`)
2. Sélectionner les **scopes** via les badges (au moins un requis)
3. Lors de la sélection de `*` (accès complet), cocher la case de confirmation
4. Cliquer sur **Créer** et copier le secret — **jamais affiché à nouveau après avoir quitté cet écran**

### Notes

- La dernière clé avec le scope `*` ne peut pas être supprimée (empêche le verrouillage Bearer)
- Créer d'abord une autre clé `*` avant de supprimer l'ancienne

### Utilisation

```bash
curl -H "Authorization: Bearer <secret>" http://localhost:5000/v1/chat/completions ...
```
