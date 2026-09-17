# YU AI Manager

Interface Web de gestion des métadonnées pour les images générées par IA.

## Aperçu

YU AI Manager est un outil WebUI qui extrait, recherche et gère les métadonnées intégrées dans les images générées par IA (prompts, modèles, graines, etc.).

**Voici ce que vous pouvez faire :**

- Analyser intégralement des dossiers ou des archives ZIP pour enregistrer automatiquement les images
- Recherche et filtrage transversaux par prompts, tags, noms de modèles, valeurs de graines, etc.
- Envoyer instantanément les images préférées vers SD / ComfyUI / NovelAI pour les régénérer
- Taguer automatiquement avec WD-Tagger, analyser le contenu avec Ollama/OpenAI
- Accéder via code QR à partir d'autres appareils sur le LAN (smartphones, etc.)

**Sources supportées** : Stable Diffusion (A1111/Forge), NovelAI V3/V4, ComfyUI

## Environnement d'exécution

- Windows / Linux / macOS

> **Aucune installation manuelle requise.** `start.sh` / `start.bat` amorce automatiquement tous les outils nécessaires sous le répertoire du projet (sans accès en écriture système ni privilèges d'administrateur).

## Configuration et démarrage

```bash
git clone https://github.com/eauesque/yu_ai_manager.git
cd yu_ai_manager

# Windows
start.bat

# macOS / Linux
./start.sh
```

Configuration automatique au premier démarrage :

| Outil | Source |
| --- | --- |
| `uv` | Téléchargement automatique vers `./bin/uv` |
| Python 3.11+ | Installation automatique par `uv` |
| Node.js 22 LTS | Optionnel — vérifier le téléchargement vers `./bin/node/` (environ 30 Mo) |
| pnpm | Activé automatiquement via `corepack` une fois Node.js installé |
| ffmpeg | Optionnel — Windows/macOS : vérifier le téléchargement vers `./bin/ffmpeg/` (environ 80 Mo), Linux : les instructions des commandes `apt`/`dnf`/`pacman` de la distro s'affichent |

Définir `YU_AUTO_INSTALL=1` pour ignorer les invites et installer complètement automatiquement dans les environnements non-interactifs (CI, etc.). ffmpeg est exclusivement réservé aux fonctionnalités étendues comme l'analyse vidéo, la S2T et l'OCR, il n'est pas nécessaire pour lancer l'application principale.

À partir de la deuxième exécution, la réinstallation et la reconstruction ne se font que si les dépendances ou les sources TypeScript sont mises à jour.

Vous pouvez définir des paramètres persistants en entrant `--db`, `--port`, `--lan`, `--pin`, etc. dans `launch-args.txt`.

## Fonctionnalités principales

### Analyse et enregistrement
- Extraction automatique des métadonnées PNG / WebP / JPEG
- Analyse transparente des archives ZIP / 7z sans extraction
- Ajout de fichiers par glisser-déposer

### Recherche et consultation
- Recherche textuelle complète sur les prompts, tags, noms de modèles, valeurs de graines
- Recherche par expression régulière, filtres à conditions multiples
- Recherche d'images similaires par pHash, recherche sémantique par CLIP

### Organisation et gestion
- Favoris, notation en étoiles (1 à 5), notes (annotations)
- Collections (groupement)
- Tableau de bord statistiques, rapports mensuels, système de trophées

### Intégration d'outils de génération (Bridge)
- Envoi instantané de prompts vers SD WebUI / Forge / ComfyUI / NovelAI
- Support de l'envoi via presse-papiers

### Assistance IA
- Taggage automatique avec WD-Tagger
- Analyse du contenu des images à l'aide d'Ollama / OpenAI
- Conversion voix-texte (S2T)

### Réseau et partage
- Mode de partage LAN (accès depuis smartphone via code QR)
- Serveur MCP (contrôle par agents IA)
- Gestion Fleet (gestion centralisée de plusieurs instances)

### Personnalisation
- Système d'interface utilisateur personnalisée et d'extensions
- Support des thèmes (clair / sombre)
- Application de bureau Tauri (démarrage sans navigateur)

## Support multilingue

English / 日本語 / 繁體中文 / 简体中文 / 한국어

## Documentation

- [Guide de démarrage rapide](docs/ja/help/user/quickstart.md)
- [Cas d'utilisation](docs/ja/help/user/use-cases.md)
- [Référence API](docs/ja/api/README.md)
- [Réglage des performances](docs/ja/help/user/performance-tuning.md)
- [Déploiement](docs/ja/help/user/deployment.md)
- [Développement d'extensions](docs/ja/plugin-development/getting-started.md)
- [Interface utilisateur personnalisée](docs/ja/custom-ui/README.md)
- [Référence des outils MCP](docs/ja/api/MCP_TOOLS_REFERENCE.md)
- [Liste complète de la documentation](docs/ja/README.md)

## Développement et personnalisation

Voir [DEVELOPMENT.ja.md](DEVELOPMENT.ja.md) ([English](DEVELOPMENT.en.md))

## Besoin d'aide ? Demandez à une IA

### En cas de démarrage impossible

Ouvrez ce dossier de projet dans un agent IA comme Claude Code Desktop, puis dites :

> Le script `start.bat` (ou `start.sh`) s'arrête. Pouvez-vous m'aider ?

> **Remarque** : Avec Claude Code Desktop, vous devez spécifier le dossier du projet avant de commencer la conversation.

### Problèmes après démarrage, configuration, utilisation

**Étape 1 — Obtenir le contexte**

Ouvrez la page d'aide (`/help`) et appuyez sur le bouton **« Copier le contexte IA »**.
Il utilise la session du navigateur authentifié pour récupérer via `GET /api/ai-context` et copier le JSON dans le presse-papiers (fonctionne même dans les environnements LAN http://).

> **Remarque (si vous avez une clé API)** : Si vous avez une clé API avec la portée admin, vous pouvez appeler directement `GET /api/ai-context` avec l'en-tête `Authorization: Bearer <key>`.

**Étape 2 — Le passer à l'IA**

Collez le JSON que vous avez copié dans le chat IA, puis tapez votre question :

> 〔JSON collé〕
> Compte tenu de cela, veuillez résoudre 〔description du problème〕.

`/api/ai-context` contient la version actuelle, les fonctionnalités activées, les indices de configuration, la liste des API et les règles CSRF, fournissant à l'IA toutes les informations nécessaires pour vous assister avec précision.

## FAQ

[docs/ja/FAQ.md](docs/ja/FAQ.md) ([English](docs/en/FAQ.md))

## Signalement de bugs

[GitHub Issues](https://github.com/eauesque/yu_ai_manager/issues)

## Licence

MIT License — [LICENSE](LICENSE) / [Traduction en langage courant](docs/ja/LICENSE.md) ([English](docs/en/LICENSE.md))
