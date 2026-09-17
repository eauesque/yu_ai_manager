# Guide d'intégration MCP — Utiliser YU AI Manager à partir d'un LLM

YU AI Manager a un serveur **MCP (Model Context Protocol)** intégré qui permet aux applications LLM d'utiliser la bibliothèque d'images en langage naturel.

Il n'y a pas d'interface de chat intégrée dans cette application.
Pour interagir avec elle en utilisant le langage naturel, connectez-vous à partir de votre client MCP compatible préféré.

---

## Qu'est-ce que MCP ?

MCP (Model Context Protocol) est un protocole standard qui permet aux applications LLM d'accéder aux outils externes et sources de données.
YU AI Manager agit comme serveur MCP, et les clients LLM (tels que Claude Desktop) se connectent à lui, traduisant les instructions en langage naturel en opérations API.

```
┌─────────────────┐      MCP (stdio)       ┌─────────────────────┐
│  LLM Client     │ <--------------------> │  YU AI Manager      │
│  (Claude Desktop │                        │  MCP Server         │
│   / Open WebUI   │                        │  (python -m         │
│   / Cline etc.)  │                        │   mcp_server)       │
└─────────────────┘                        └────────┬────────────┘
                                                     │ HTTP API
                                                     v
                                           ┌─────────────────────┐
                                           │  YU AI Manager      │
                                           │  Web Server          │
                                           │  (localhost:5000)    │
                                           └─────────────────────┘
```

## Clients MCP pris en charge

Ce qui suit sont des clients MCP-compatibles représentatifs. Les étapes de configuration sont similaires pour tous.

| Client | Fournisseur | Fonctionnalités |
|---|---|---|
| **Claude Desktop** | Anthropic | Accès direct à Claude. Support MCP natif |
| **Claude Code** | Anthropic | Client basé sur terminal pour les développeurs |
| **Cline** | VS Code Extension | Intégration d'éditeur. Support multi-LLM |
| **Open WebUI** | Open Source | Autohébergé. Peut être combiné avec des LLM locaux tels que Ollama |

Note : Le nombre de clients MCP-compatibles croît rapidement.
Tout client qui supporte le transport stdio devrait pouvoir se connecter.

## Configuration

### 1. Démarrer YU AI Manager

Le serveur MCP fonctionne via l'API du serveur Web, donc YU AI Manager doit d'abord être en cours d'exécution.

```bash
python web_ui.py --db ./tags.db --port 5000
```

### 2. Émettre une clé API (Recommandé)

L'émission d'une clé API permet au serveur MCP de contourner l'authentification PIN lors de l'utilisation du partage LAN ou de l'authentification PIN.

Les clés API peuvent être émises depuis Paramètres -> Clés API.

Une clé API n'est pas nécessaire lors de l'exécution sans PIN (`config_test.json`).

### 3. Ajouter les paramètres de connexion à votre client MCP

#### Claude Desktop

Éditer `claude_desktop_config.json` :

**Windows** : `%APPDATA%\Claude\claude_desktop_config.json`
**macOS** : `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "C:/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://127.0.0.1:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

#### Claude Code

Ajouter les paramètres à `.mcp.json` à la racine du projet, ou utiliser la commande `claude mcp add` :

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://127.0.0.1:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

#### Cline (VS Code)

Entrer les mêmes informations via les paramètres MCP de Cline.

#### Variables d'environnement

| Variable | Requise | Défaut | Description |
|---|---|---|---|
| `YU_BASE_URL` | - | `http://localhost:5000` | URL du serveur Web |
| `YU_API_KEY` | - | Aucune | Clé API (requise dans les environnements PIN) |
| `YU_DEBUG_MODE` | - | `0` | Définir à `1` pour ajouter des outils de débogage |

## Exemples d'utilisation

Une fois connecté, vous pouvez utiliser la bibliothèque d'images en donnant des instructions en langage naturel au LLM.

### Recherche et navigation

```
"Montrez-moi les 20 images les plus récentes de filles aux yeux bleus"
"Filtrer pour uniquement les images générées avec NovelAI"
"Montrez-moi les statistiques des images scannées la semaine dernière"
```

### Organiser et classer

```
"Donnez à ces 10 images une note de 5 étoiles"
"Ajouter les images marquées 'paysage' à la 'Collection de paysages'"
"Lister toutes les images avec une note de 3 ou moins"
```

### Analyse et annotation

```
"Évaluer la qualité des images récemment ajoutées et enregistrer les annotations"
"Montrez-moi toutes les annotations pour l'image ID 12345"
"Rechercher les annotations avec la source agent:claude"
```

### Opérations de scan

```
"Scanner les nouvelles images"
"Vérifier la progression du scan"
"Montrez-moi les erreurs de scan"
```

## Outils disponibles

Le serveur MCP expose les outils suivants au LLM :

### Recherche et navigation (4 outils)

| Nom de l'outil | Description |
|---|---|
| `search_images` | Rechercher des images par tags, date, format, note, etc. |
| `get_image_detail` | Récupérer toutes les métadonnées d'une image |
| `get_library_stats` | Statistiques de la bibliothèque (nombre de fichiers, nombre de tags, distribution des sources, etc.) |
| `find_similar` | Rechercher des images similaires à l'aide du hash perceptif |

### Collections (4 outils)

| Nom de l'outil | Description |
|---|---|
| `list_collections` | Lister les collections |
| `create_collection` | Créer une collection |
| `delete_collection` | Supprimer une collection |
| `add_to_collection` / `remove_from_collection` | Ajouter/supprimer des images |

### Tags et notes (2 outils)

| Nom de l'outil | Description |
|---|---|
| `rate_images` | Définir les étoiles pour plusieurs images à la fois |
| `set_tags` | Ajouter/supprimer des tags pour plusieurs images à la fois |

### Annotations (4 outils)

| Nom de l'outil | Description |
|---|---|
| `set_annotations` | Enregistrer les résultats d'analyse IA sous forme d'annotations |
| `get_annotations` | Récupérer les annotations d'une image |
| `search_annotations` | Rechercher les annotations dans la source, la clé et la confiance |
| `delete_annotations` | Supprimer les annotations |

### Scan (3 outils)

| Nom de l'outil | Description |
|---|---|
| `trigger_scan` | Démarrer un scan |
| `get_scan_status` | Vérifier la progression du scan |
| `get_scan_errors` | Lister les erreurs de scan |

### Autre

Les outils pour la gestion de la bibliothèque de prompts, de la sauvegarde et du client MCP sont également inclus.

## FAQ

### Q : N'y a-t-il pas de fonction de chat dans l'application ?

R : Non. YU AI Manager se spécialise dans la gestion des métadonnées d'image, et l'interface IA conversationnelle est déléguée aux clients MCP-compatibles. Vous pouvez effectuer toutes les opérations via le langage naturel en exécutant Claude Desktop ou un client similaire à côté.

### Q : Quel LLM dois-je utiliser ?

R : N'importe quel LLM fonctionne, tant que le client MCP le supporte.
Pour une gestion fiable des arguments de l'outil, les grands modèles comme la classe Claude ou GPT-4 tendent à fonctionner le plus régulièrement.

### Q : Puis-je utiliser un LLM local ?

R : Oui, les LLM locaux fonctionnent avec des combinaisons telles que Open WebUI + Ollama, à condition qu'ils supportent MCP. Cependant, la précision de l'appel d'outil dépend des capacités du modèle.

### Q : YU AI Manager a-t-il également une fonction client MCP ?

R : L'extension `MCP Client` (sur la page Outils) connecte YU AI Manager à **d'autres serveurs MCP**. Ce guide décrit la direction opposée : LLM externe -> YU AI Manager.
