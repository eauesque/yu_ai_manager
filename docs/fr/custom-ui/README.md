# Guide de l'interface utilisateur personnalisée

Guide du système d'interface utilisateur personnalisée permettant de remplacer entièrement le frontend de YU AI Manager.

## Table des matières

- [Vue d'ensemble](#vue-densemble)
- [Architecture](#architecture)
- [Guide de démarrage rapide](quickstart.md) — Procédure de création d'une UI minimale
- [Guide de conception](design-guide.md) — Conception CSS, thèmes, responsive, composants
- [Guide des templates](templates.md) — Patterns Jinja2, i18n, structure des pages
- [Fonctionnalités avancées](advanced.md) — SSE temps réel, opérations par lot, sécurité
- [Référence API](api-reference.md) — Liens vers la documentation API complète

## Vue d'ensemble

Le backend API de YU AI Manager est entièrement séparé, ce qui permet de remplacer librement le frontend.
Il suffit de placer une UI personnalisée dans le répertoire `ui/<name>/` pour l'activer.

### Ce que ce système permet

- **Remplacement complet de l'UI** : Personnaliser toutes les pages (recherche, statistiques, paramètres, etc.) avec votre propre design
- **Personnalisation du thème** : Modifier le schéma de couleurs en surchargeant simplement les variables CSS
- **Remplacement partiel** : Personnaliser uniquement les pages souhaitées et utiliser l'UI par défaut pour le reste
- **Génération d'UI par IA** : Générer automatiquement une UI en fournissant la documentation API à Claude ou ChatGPT

### Architecture

```
yu_ai_manager/
├── ui/
│   ├── default/              # UI de référence (built-in)
│   │   ├── manifest.json     # Métadonnées UI (obligatoire)
│   │   ├── templates/        # Templates HTML Jinja2
│   │   │   ├── index.html    # Page de recherche principale
│   │   │   ├── stats.html    # Tableau de bord des statistiques
│   │   │   ├── tools.html    # Page des outils
│   │   │   ├── settings.html # Page des paramètres
│   │   │   ├── story.html    # Page Your Story
│   │   │   ├── inspect.html  # Inspection des métadonnées
│   │   │   └── _nav.html     # Barre de navigation commune (include)
│   │   └── static/           # CSS, JS, images
│   │       ├── css/          # Feuilles de style
│   │       ├── dist/         # Sortie de build TypeScript
│   │       └── favicon.svg   # Favicon
│   ├── custom/               # UI personnalisée (gitignored, auto-détectée)
│   │   ├── manifest.json
│   │   ├── templates/
│   │   └── static/
│   └── my-theme/             # UI supplémentaire (nom libre)
│       ├── manifest.json
│       └── ...
├── routes/                   # Routes API côté serveur
│   ├── pages.py              # Définition du routage des pages
│   └── ...                   # Divers endpoints API
└── docs/api/                 # Documentation API
```

### Ordre de résolution des UI

Au démarrage du serveur, l'UI à utiliser est déterminée selon les priorités suivantes :

| Priorité | Condition | Comportement |
|--------|------|------|
| 1 | `"ui": "my-theme"` configuré dans `config.json` | Utilise `ui/my-theme/` spécifié |
| 2 | `manifest.json` valide présent dans `ui/custom/` | Auto-détecte et utilise `ui/custom/` |
| 3 | Aucune des conditions ci-dessus | Utilise `ui/default/` en fallback |

### manifest.json

Toutes les UI personnalisées nécessitent un `manifest.json` :

```json
{
  "name": "my-custom-ui",
  "version": "1.0.0",
  "description": "My custom UI for YU AI Manager",
  "author": "Your Name",
  "api_version": "1"
}
```

| Champ | Obligatoire | Description |
|-----------|------|------|
| `name` | Oui | Nom d'identification de l'UI (recommandé : correspondre au nom du répertoire) |
| `version` | Oui | Version sémantique |
| `description` | Non | Description de l'UI |
| `author` | Non | Nom de l'auteur |
| `api_version` | Non | Version API prise en charge (`"1"`) |
| `type` | Non | `"full"` (par défaut) ou `"theme"` |

### Distribution des fichiers statiques

Le répertoire `static/` de l'UI personnalisée est mappé sur l'URL `/static/` de Flask :

```
ui/custom/static/style.css  →  /static/style.css
ui/custom/static/js/app.js  →  /static/js/app.js
ui/custom/static/img/logo.png  →  /static/img/logo.png
```

Référence depuis HTML :
```html
<link rel="stylesheet" href="/static/style.css">
<script src="/static/js/app.js"></script>
<img src="/static/img/logo.png">
```

### API de gestion des UI

Il est possible de gérer les UI depuis l'onglet « UI » de la page Settings ou via l'API :

| Méthode | Chemin | Description |
|---------|------|------|
| GET | `/api/ui/list` | Liste des UI installées |
| POST | `/api/ui/switch` | Changer l'UI active (nécessite redémarrage) |
| POST | `/api/ui/install` | Installer une UI depuis une URL (localhost uniquement) |
| DELETE | `/api/ui/<name>/uninstall` | Désinstaller une UI (localhost uniquement) |

### Outils MCP

Les UI peuvent également être gérées via MCP (Model Context Protocol) :

- `list_uis()` — Liste des UI installées
- `switch_ui(name)` — Changer l'UI active
- `install_ui(url)` — Installer une UI depuis une URL
- `uninstall_ui(name)` — Désinstaller une UI
