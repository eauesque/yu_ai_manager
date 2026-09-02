# Intégration MCP

YU AI Manager est équipé d'un serveur MCP (Model Context Protocol) intégré,
permettant une opération directe depuis des clients IA comme Claude Desktop, Claude Code et Cline.
Plus de 137 outils sont disponibles, couvrant toutes les fonctionnalités de la gestion d'images à l'analyse IA.

## Clients MCP supportés

| Client | Méthode de connexion | Remarques |
|-------------|---------|------|
| Claude Desktop | stdio / HTTP | Client recommandé |
| Claude Code | stdio | Environnement CLI |
| Cline (VS Code) | stdio | Extension VS Code |
| Open WebUI | HTTP/SSE | Basé sur le Web |

## Connexion locale (stdio)

Connexion depuis Claude Desktop / Claude Code sur la même machine :

1. Créer une clé API dans l'onglet Settings > API Keys
2. Ajouter ce qui suit au fichier de configuration du client

### Claude Desktop

`claude_desktop_config.json` :

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://localhost:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

### Claude Code

`.mcp.json` :

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://localhost:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

## Connexion LAN (HTTP/SSE)

Connexion depuis une autre machine sur le LAN :

1. Activer l'accès LAN dans YU AI Manager
2. Créer une clé API
3. Copier la configuration de connexion depuis « MCP Connection Snippet » dans l'onglet Settings > API Keys

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "type": "http",
      "url": "http://192.168.x.x:5000/mcp",
      "headers": {
        "Authorization": "Bearer sk_your_api_key_here"
      }
    }
  }
}
```

## Outils disponibles (par catégorie)

### Recherche et gestion d'images

| Outil | Description |
|--------|------|
| `search_images` | Recherche filtrée par tags, dates, notes, etc. |
| `get_image_detail` | Récupérer les métadonnées détaillées d'une image |
| `get_library_stats` | Statistiques de la bibliothèque (nombre de fichiers, distribution des tags, etc.) |
| `find_similar` | Détection d'images similaires par hash perceptuel |
| `rate_images` | Définition en masse des notes par étoiles |
| `set_tags` | Ajout/suppression de tags |
| `set_annotations` | Définition d'annotations |
| `get_annotations` | Récupération d'annotations |

### Collections

| Outil | Description |
|--------|------|
| `list_collections` | Liste des collections |
| `create_collection` | Créer une collection |
| `add_to_collection` | Ajouter une image à une collection |
| `remove_from_collection` | Supprimer une image d'une collection |
| `delete_collection` | Supprimer une collection |

### Scan

| Outil | Description |
|--------|------|
| `trigger_scan` | Exécuter un scan |
| `get_scan_status` | Vérifier la progression du scan |
| `list_scan_roots` | Liste des racines de scan |
| `add_scan_root` | Ajouter une racine de scan |
| `scan_directory` | Scanner un répertoire spécifique |

### Analyse IA

| Outil | Description |
|--------|------|
| `analyze_image` | Analyse IA d'une image (individuelle) |
| `analyze_batch` | Analyse IA en lot |
| `wd_tagger_tag_file` | Inférence WD-Tagger (individuelle) |
| `wd_tagger_batch` | Inférence WD-Tagger en lot |
| `semantic_search` | Recherche sémantique CLIP |
| `s2t_transcribe_video` | Transcription vocale |

### Intégration Bridge

| Outil | Description |
|--------|------|
| `sd_generate` | Génération d'images avec SD WebUI |
| `sd_list_models` | Liste des modèles SD WebUI |
| `comfyui_generate` | Génération d'images avec ComfyUI |
| `comfyui_generate_json` | Exécution de workflow JSON ComfyUI |

### Bibliothèque de prompts

| Outil | Description |
|--------|------|
| `create_prompt` | Créer un prompt |
| `search_prompts` | Rechercher des prompts |
| `get_prompt` | Récupérer un prompt |
| `update_prompt` | Mettre à jour un prompt |

### Paramètres

| Outil | Description |
|--------|------|
| `settings_get_schema` | Récupérer le schéma de paramètres |
| `settings_get` | Récupérer une valeur de paramètre |
| `settings_set` | Mettre à jour une valeur de paramètre |
| `secrets_status` | Vérifier l'état de la clé de chiffrement |

### Mécanismes de sécurité agent

| Outil | Description |
|--------|------|
| `agent_kill` / `agent_resume` | Contrôle du Kill Switch |
| `agent_status` | Statut des mécanismes de sécurité |
| `agent_journal` | Recherche dans le journal des opérations |
| `agent_undo` | Annuler une opération |
| `agent_circuit_breaker_status` | État du Circuit Breaker |
| `agent_budget_status` | État du budget tracker |
| `agent_scope_set` | Définir la portée |
| `agent_anomaly_status` | Statut de détection des anomalies |

### Autres

| Outil | Description |
|--------|------|
| `find_duplicates` | Détection de fichiers dupliqués |
| `search_chat_logs` | Recherche dans les logs de chat |
| `search_md_files` | Recherche dans les fichiers Markdown |
| `help_search` | Recherche dans la documentation d'aide |
| `share_to_bluesky` | Publication sur Bluesky |
| `list_trophies` | Liste des trophées |
| `get_monthly_report` | Rapport mensuel |

## Variables d'environnement

| Variable | Description | Défaut |
|------|------|----------|
| `YU_BASE_URL` | URL du serveur | `http://localhost:5000` |
| `YU_API_KEY` | Clé API | (obligatoire) |
| `YU_DEBUG_MODE` | Activer les outils de débogage | `0` |

Définir `YU_DEBUG_MODE=1` ajoute des outils dédiés au débogage comme les requêtes directes DB et les vérifications de santé.

## Dépannage

### Connexion impossible

1. Vérifier que YU AI Manager est démarré
2. Vérifier que la clé API est correcte (avec préfixe `sk_`)
3. Vérifier que `YU_BASE_URL` est correct
4. En cas de connexion LAN, vérifier que l'accès LAN est activé

### Outil introuvable

- Si une Extension est désactivée, ses outils ne sont plus disponibles
- Vérifier l'état d'activation avec `list_extensions`

### Timeout

- La recherche dans les grandes bibliothèques et les opérations en lot peuvent prendre du temps
- Limiter le nombre de résultats avec le paramètre `limit`
