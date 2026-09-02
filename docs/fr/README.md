# Documentation Hub

Utilisez ce fichier comme « point d'entrée de la documentation (hub officiel) ».

**Dernière mise à jour** : 2026-05-13

## Important

- Project README : `../../README.fr.md`
- Changelog : `../../CHANGELOG.fr.md`
- Master TODO (single source of truth) : `../../TODO.md`

## Development Guidelines

Les directives de développement sont situées dans `development/development_docs/` en tant que fichiers individuels.

- **[TODO Rules](TODO_RULES.md)** — Règles de rédaction des TODO (P0/P1/P2/P3 + catégorie obligatoire)

### Documents principaux (`development/development_docs/`)

| Document | Contenu |
|---|---|
| [CODE_SIZE_GUIDELINES](development/development_docs/CODE_SIZE_GUIDELINES.md) | Envisager une division à 300 lignes, diviser obligatoirement à 500 lignes |
| [MODULE_ORGANIZATION_GUIDELINES](development/development_docs/MODULE_ORGANIZATION_GUIDELINES.md) | Répertoire par unité de feature, 100-250 lignes idéal |
| [MODULE_SAFETY](development/development_docs/MODULE_SAFETY.md) | Modèle de défense en trois couches (validation statique/analyse/runtime) |
| [ERROR_HANDLING](development/development_docs/ERROR_HANDLING.md) | Unifié `api_error()`, `{ok, error, code, detail, hint}` |
| [API_RESPONSE_GUIDELINES](development/development_docs/API_RESPONSE_GUIDELINES.md) | `api_success()` / `api_error()` / `api_result()` |
| [ENTRYPOINT_MAP](development/development_docs/ENTRYPOINT_MAP.md) | Liste des points d'entrée de tous les modules |
| [ACCIDENT_POINTS](development/development_docs/ACCIDENT_POINTS_AND_COMMON_LAYER_SPEED_GUIDE.md) | Stratégies de prévention des 6 points d'accident |
| [UI_BUTTON_PRIORITY_GUIDELINES](development/development_docs/UI_BUTTON_PRIORITY_GUIDELINES.md) | Conception des boutons Tier A/B/C |
| [UI_STATE_SPEC](development/development_docs/UI_STATE_SPEC.md) | Motif hybride Explorer/Library |
| [DOCUMENT_LIFECYCLE](development/development_docs/DOCUMENT_LIFECYCLE.md) | Règles de placement des documents |
| [FUZZ_BURN_IN_TEST](development/development_docs/FUZZ_BURN_IN_TEST.md) | Tests de fuzzing et burn-in pour API + UI |

### Autres documents de développement

| Document | Contenu |
|---|---|
| [ai-driven-development-principles](development/development_docs/ai-driven-development-principles.md) | Principes de conception du développement piloté par l'IA |
| [BATCH_API_STANDARD](development/development_docs/BATCH_API_STANDARD.md) | Convention d'opérations par lot |
| [EXTENSION_HOOKS_SPEC](development/development_docs/EXTENSION_HOOKS_SPEC.md) | Cycle de vie des hooks d'extension |
| [REUSABLE_UI_WIDGETS](development/development_docs/REUSABLE_UI_WIDGETS.md) | Liste des widgets UI réutilisables |
| [SD_NAI_PROMPT_SYNTAX_SPEC](development/development_docs/SD_NAI_PROMPT_SYNTAX_SPEC.md) | Spécification de syntaxe des prompts SD/NAI |
| [ENCODING_FALLBACK](development/development_docs/ENCODING_FALLBACK.md) | Encodage des noms de fichiers d'archive |
| [VISION_API_IMAGE_FORMATS](development/development_docs/VISION_API_IMAGE_FORMATS.md) | Tableau de compatibilité des formats d'image Vision API |
| [QA_HANDOFF](development/development_docs/QA_HANDOFF.md) | Résultats des cycles d'assurance qualité et problèmes restants |

### Journaux de développement et spécifications

| Document | Contenu |
|---|---|
| [HAILO_SEMANTIC_SEARCH_DEVLOG](development/development_docs/HAILO_SEMANTIC_SEARCH_DEVLOG.md) | Journal de développement Hailo-10H CLIP |
| [CLIP_ONNX_DEVLOG](development/development_docs/CLIP_ONNX_DEVLOG.md) | Journal de développement CLIP ONNX multi-backend |
| [HAILO_DEVICE_CONTROL](development/development_docs/HAILO_DEVICE_CONTROL.md) | Contrôle des périphériques Hailo |
| [CHATLOG_ENHANCED_SPEC](development/development_docs/CHATLOG_ENHANCED_SPEC.md) | Spécification améliorée du journal de chat |
| [TAURI_DESKTOP_APP](development/development_docs/TAURI_DESKTOP_APP.md) | Intégration de l'application de bureau Tauri |
| [EXTENSION_SPEC_FREEZE_PULLBACK_GENERATOR](development/development_docs/EXTENSION_SPEC_FREEZE_PULLBACK_GENERATOR_v0_2.md) | Spécification d'extension Freeze & Pull-back |
| [VIDEO_METADATA_V2_PLAN](development/development_docs/VIDEO_METADATA_V2_PLAN.md) | Plan des métadonnées vidéo v2 (Brouillon) |

## Import Paths

Tous les imports utilisent directement les chemins de modules réels. Les mécanismes d'alias ont été supprimés.

**Exemples de chemins principaux :**
- `core.services_core.db_api` — Accès à la base de données (ancien `core.db`)
- `core.configuration.api` — Gestion de la configuration (ancien `core.config`)
- `core.extensions_core.runtime` — Runtime d'extension (ancien `core.extensions`)
- Les nouvelles features sont ajoutées directement au répertoire `core/<feature>_core/`

## Troubleshooting & Operations

- Playbook de débogage : [`troubleshooting/debug-playbook.md`](troubleshooting/debug-playbook.md)
- Erreurs courantes (héritage) : [`troubleshooting/common-errors.md`](troubleshooting/common-errors.md)
- Pièges d'encodage CJK / 2 octets : [`troubleshooting/cjk-2byte-encoding-pitfalls.md`](troubleshooting/cjk-2byte-encoding-pitfalls.md)
- Erreur d'analyse des crochets échappés : [`troubleshooting/escaped-brackets-parse-error.md`](troubleshooting/escaped-brackets-parse-error.md)

## Features

| Document | Statut | Contenu |
|---|---|---|
| [Guide d'intégration MCP](features/mcp-integration-guide.md) | Actuel | Contrôler YU AI Manager à partir d'une LLM |
| [NovelAI V4](features/novelai-v4.md) | Actuel | Format de prompt NovelAI V4 et support des négatifs par personnage |
| [Recherche sémantique Hailo](features/hailo-semantic-search.md) | Implémenté → Migration vers ONNX | Instructions d'implémentation Hailo-10H CLIP |
| [Génération automatique de tags Danbooru](features/danbooru-tag-gen-spec.md) | Implémenté (v2.77.0) | WD-Tagger + approche VLM à deux étapes |
| [Gestion des textes et journaux de chat](features/text-chatlog-management-spec.md) | Actuel | Importation de Chatlog et recherche FTS |
| [Protocole QR v1](features/qr-protocol-v1.md) | Actuel | Code QR pour partage sur LAN |
| [Benchmark de recherche avec expressions régulières](features/regex-search-benchmark.md) | Actuel | Performance des expressions régulières |
| [Compatibilité des navigateurs](features/browser-compatibility.md) | Actuel | Liste des navigateurs pris en charge |

## API Reference

- [Aperçu de l'API (Authentification · CSRF · Limitation de débit)](api/README.md)
- [API de recherche](api/search.md)
- [API de fichiers](api/files.md)
- [API de scan](api/scan.md)
- [Événements SSE](api/events.md)
- [Variables CSS de thème](api/theming.md)

## Custom UI / Plugin Development

- [Guide Custom UI](custom-ui/README.md) — Développement d'interface utilisateur personnalisée (démarrage rapide, conception, modèles, avancé)
- [Guide de développement de plugins](plugin-development/getting-started.md) — Introduction au développement d'extensions
- [Référence du manifeste](plugin-development/manifest-reference.md) — Spécification de extension.json

## Installation

- FFmpeg : [`installation/ffmpeg.md`](installation/ffmpeg.md)
- Docker : [`development/development_docs/DOCKER_SETUP.md`](development/development_docs/DOCKER_SETUP.md)

## Historical Docs

Les documents suivants sont d'anciens memos d'implémentation / enregistrements de correctifs rapides (situés dans `archive/docs_history/`).

- `DEBUG_INSTRUCTIONS_v2.5.4.md` — Manuel de débogage de l'époque v2.5.4
- `DARK_MODE_TAGS_IMPROVEMENT.md` — Proposition d'amélioration des tags en mode sombre (implémentée)
- `EXTENSION_DRAFT.md` — Brouillon initial du système d'extension (successeur dans plugin-development/)
