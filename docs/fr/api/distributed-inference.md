# API d'inférence distribuée

API REST pour le registre du serveur d'inférence distribuée. Distribue les charges de travail d'indexation sémantique CLIP sur plusieurs nœuds en utilisant une stratégie de file d'attente partagée.

## Points d'accès

### GET /api/inference-servers

Retourne la liste des serveurs enregistrés et le mode de dispatch actuel.

**Réponse :**

```json
{
  "status": "ok",
  "mode": "single",
  "servers": [
    {
      "id": 1,
      "name": "Hailo Worker 1",
      "endpoint_url": "http://192.168.1.10:9090",
      "inference_types": ["clip"],
      "priority": 50,
      "enabled": true,
      "timeout": 30
    }
  ]
}
```

- `mode` : `"single"` | `"parallel"` | `"idle_first"`
- `servers` : tableau d'objets de configuration du serveur

---

### POST /api/inference-servers

Enregistrer un nouveau serveur d'inférence.

**Corps de la requête :**

| Champ | Type | Requis | Par défaut | Description |
|---|---|---|---|---|
| `name` | string | ✓ | — | Nom d'affichage |
| `endpoint_url` | string | ✓ | — | URL de base du Worker |
| `inference_types` | string[] | — | `["clip"]` | Types d'inférence supportés |
| `priority` | int | — | `50` | Priorité (valeur inférieure = priorité plus élevée) |
| `bearer_token` | string | — | — | Token d'authentification |
| `timeout` | int | — | `30` | Timeout de requête en secondes |

**Réponse :**

```json
{
  "status": "ok",
  "server": { ... }
}
```

---

### PUT /api/inference-servers/{server_id}

Mettre à jour la configuration d'un serveur existant. Accepte un corps partiel avec les mêmes champs que POST.

---

### DELETE /api/inference-servers/{server_id}

Supprimer un serveur du registre.

**Réponse :**

```json
{ "status": "ok" }
```

---

### POST /api/inference-servers/{server_id}/test

Exécuter une vérification d'intégrité sur le serveur spécifié.

**Réponse :**

```json
{
  "status": "ok",
  "server_id": 1,
  "healthy": true,
  "latency_ms": 12.5
}
```

---

### GET /api/inference-servers/health

Exécuter des vérifications d'intégrité sur tous les serveurs activés simultanément.

**Réponse :**

```json
{
  "status": "ok",
  "results": [
    { "server_id": 1, "healthy": true, "latency_ms": 12.5 },
    { "server_id": 2, "healthy": false, "error": "Connection refused" }
  ]
}
```

---

### POST /api/inference-servers/mode

Définir le mode de dispatch.

**Corps de la requête :**

| Champ | Type | Requis | Description |
|---|---|---|---|
| `mode` | string | ✓ | `"single"` \| `"parallel"` \| `"idle_first"` |

**Réponse :**

```json
{ "status": "ok", "mode": "parallel" }
```

---

## Modes de dispatch

| Mode | Description |
|---|---|
| `single` | Utiliser uniquement le serveur avec la priorité la plus élevée (valeur de priorité la plus basse) |
| `parallel` | Distribuer le travail sur tous les serveurs activés en utilisant une file d'attente partagée |
| `idle_first` | Vérifier l'intégrité en premier, puis distribuer sur les serveurs réactifs uniquement |

## Indexation sémantique distribuée

Ajouter `distributed: true` au corps de la requête `POST /api/index/start` (extension de recherche sémantique) pour activer l'indexation distribuée en utilisant les serveurs workers enregistrés.

```json
{
  "batch_size": 32,
  "distributed": true
}
```

## Configuration du serveur Worker

```bash
python deploy/hailo_tagger_server.py --port 9090
```

Points d'accès supportés :

| Chemin | Description |
|---|---|
| `GET /health` | Vérification d'intégrité |
| `POST /tag` | Inférence WD-Tagger |
| `POST /clip-encode` | Codage de vecteur CLIP |

## Outils MCP

| Outil | Description |
|---|---|
| `inference-servers-list` | Lister les serveurs et obtenir le mode actuel |
| `inference-server-add` | Enregistrer un nouveau serveur |
| `inference-server-update` | Mettre à jour la configuration du serveur |
| `inference-server-remove` | Supprimer un serveur |
| `inference-server-health` | Exécuter des vérifications d'intégrité |
| `inference-dispatch-mode-set` | Définir le mode de dispatch |
