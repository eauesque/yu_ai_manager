# API : /api/llm_router (Admin)

Points d'accès d'administration pour les opérations de gestion du LLM Router. Protégés par l'authentification de session WebUI standard (PIN/session), et complètement séparés de la surface compatible OpenAI `/v1/*`.

> **Note** : Ce sont des points d'accès d'administration et ils sont distincts des points d'accès d'inférence tels que `/v1/chat/completions`.

---

## Format de réponse commun

Tous les points d'accès utilisent le wrapper `api_result`. En cas de succès, le corps est imbriqué sous la clé `data`.

```json
{
  "status": "ok",
  "data": { ... }
}
```

En cas d'erreur :

```json
{
  "status": "error",
  "error": "Description de l'erreur"
}
```

---

## GET /api/llm_router/status

Un instantané pour rendre l'intégralité du tableau de bord en une seule requête. Retourne toutes les informations du backend et la carte d'alias.

### Requête

```
GET /api/llm_router/status
```

Pas de paramètres.

### Réponse `200 OK`

```json
{
  "status": "ok",
  "data": {
    "router": {
      "version": "1.0.0",
      "alias_count": 2
    },
    "backends": [
      {
        "alias": "ollama-mac",
        "base_url": "http://192.168.1.10:11434",
        "source": "static",
        "status": "ready",
        "slo_state": null,
        "disabled": false,
        "model_count": 3,
        "models": [
          {
            "name": "qwen2.5:7b",
            "context_window": 32768,
            "size_b": 7.6
          },
          {
            "name": "llama3.2:3b",
            "context_window": 128000,
            "size_b": 3.2
          }
        ],
        "last_seen": "2026-04-09T12:34:56.789123",
        "last_error": null
      },
      {
        "alias": "mdns-pi5-hailo",
        "base_url": "http://192.168.1.20:8080",
        "source": "mdns",
        "status": "unreachable",
        "slo_state": "unknown",
        "disabled": false,
        "model_count": 0,
        "models": [],
        "last_seen": null,
        "last_error": "Connection refused"
      }
    ],
    "aliases": {
      "default-llm": "ollama-mac/qwen2.5:7b",
      "fast-chat": "ollama-mac/llama3.2:3b"
    }
  }
}
```

### Descriptions des champs

**`router`**

| Champ | Type | Description |
|---|---|---|
| `version` | string | Version du schéma du Router (actuellement `"1.0.0"`) |
| `alias_count` | int | Nombre d'alias définis |

**`backends[]`**

| Champ | Type | Description |
|---|---|---|
| `alias` | string | Identifiant unique du backend |
| `base_url` | string | URL de base du point d'accès compatible OpenAI |
| `source` | string | `"static"` (fichier config) ou `"mdns"` (découvert automatiquement) |
| `status` | string | `"ready"` / `"unreachable"` / `"unknown"` |
| `slo_state` | string \| null | `"vision_idle"` / `"vision_active"` / `"unknown"` / `null` |
| `disabled` | bool | `true` si exclu du routage |
| `model_count` | int | Nombre de modèles exposés |
| `models[]` | array | Liste des modèles (`name`, `context_window`, `size_b`) |
| `last_seen` | string \| null | Dernière vérification de connectivité réussie (ISO 8601) |
| `last_error` | string \| null | Dernier message d'erreur |

**`aliases`**

Une carte de noms d'alias logiques vers les ID de modèle physiques (`backend-alias/model-name`).

---

## POST /api/llm_router/refresh

Force une sonde sur tous les backends ou un backend spécifié, en mettant à jour `status` et la liste des modèles.

### Requête

**Pour actualiser tous les backends (pas de corps) :**

```
POST /api/llm_router/refresh
Content-Type: application/json

{}
```

Un corps vide sans en-tête Content-Type est également accepté.

**Pour actualiser un seul backend spécifique :**

```json
{
  "alias": "ollama-mac"
}
```

### Réponse `200 OK`

```json
{
  "status": "ok",
  "data": {
    "refreshed": [
      {
        "alias": "ollama-mac",
        "status": "ready",
        "model_count": 3,
        "disabled": false,
        "last_error": null
      },
      {
        "alias": "mdns-pi5-hailo",
        "status": "unreachable",
        "model_count": 0,
        "disabled": false,
        "last_error": "Connection refused"
      }
    ]
  }
}
```

Le tableau `refreshed` contient uniquement les résultats de mise à jour légers (utilisez `/status` pour les détails complets).

### Erreur `404 Not Found`

Quand un `alias` est spécifié mais n'existe pas :

```json
{
  "status": "error",
  "error": "unknown backend: nonexistent-alias"
}
```

### Notes

- Les sondes sont exécutées de manière synchrone (la réponse est retournée après la fin)
- Les sondes sont également exécutées pour les backends avec `disabled: true` (le statut est toujours mis à jour)
- Les backends découverts via mDNS sont inclus

---

## POST /api/llm_router/backends/`<alias>`/disable

Désactive le backend spécifié. Les backends désactivés sont exclus du routage et l'état est persisté vers `data/llm_router_state.json`.

### Requête

```
POST /api/llm_router/backends/ollama-mac/disable
```

Aucun corps requis.

### Réponse `200 OK`

```json
{
  "status": "ok",
  "data": {
    "alias": "ollama-mac",
    "disabled": true
  }
}
```

### Erreur `404 Not Found`

```json
{
  "status": "error",
  "error": "unknown backend: nonexistent-alias"
}
```

### Erreur `500 Internal Server Error`

Quand la persistance sur le disque échoue (erreur de permission, disque plein, etc.). L'état en mémoire est annulé.

```json
{
  "status": "error",
  "error": "failed to persist disabled state"
}
```

### Mécanisme de persistance

1. Définir le drapeau `disabled` sur `true` dans le catalogue en mémoire
2. Écrire atomiquement vers `data/llm_router_state.json` (via fichier `.tmp` et `os.replace`)
3. Si l'écriture échoue, l'étape 1 est annulée et un `500` est retourné

L'état désactivé est préservé lors des redémarrages d'application. Si un backend découvert via mDNS a été désactivé avant le démarrage, l'état désactivé est automatiquement appliqué après la découverte.

---

## POST /api/llm_router/backends/`<alias>`/enable

Active le backend spécifié. L'inverse de `disable`.

### Requête

```
POST /api/llm_router/backends/ollama-mac/enable
```

Aucun corps requis.

### Réponse `200 OK`

```json
{
  "status": "ok",
  "data": {
    "alias": "ollama-mac",
    "disabled": false
  }
}
```

### Erreurs

Identiques au point d'accès `disable` (`404` / `500`). Persisté avec `disabled: false`.

---

## Résumé des points d'accès

| Méthode | Chemin | Description |
|---|---|---|
| `GET` | `/api/llm_router/status` | Obtenir un instantané de tous les backends et alias |
| `POST` | `/api/llm_router/refresh` | Forcer une sonde sur tous les backends ou backend individuel |
| `POST` | `/api/llm_router/backends/<alias>/disable` | Désactiver un backend (persisté) |
| `POST` | `/api/llm_router/backends/<alias>/enable` | Activer un backend (persisté) |

## Documentation connexe

- [Guide WebUI LLM Router](../llm-router/webui.md)
- [Configuration LLM Router](../llm-router/setup.md)
