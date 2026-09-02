# Index de la documentation de développement

Liste des documents de conception interne, ressources techniques et journaux de développement.
Tous les fichiers sont stockés dans `docs/development/development_docs/`.

Vous pouvez également les lire directement avec l'outil MCP `source_read`.

---

## Conception et architecture

| Document | Contenu |
|-------------|------|
| DESIGN_PHILOSOPHY | Philosophie de conception — Principes directeurs et critères de décision du projet |
| MODULE_ORGANIZATION_GUIDELINES | Directives d'organisation des modules |
| CODE_SIZE_GUIDELINES | Directives de taille de code (critères de découpage des fichiers) |
| ENTRYPOINT_MAP | Carte des points d'entrée |
| DOCUMENT_LIFECYCLE | Politique de cycle de vie des documents |
| UI_STATE_SPEC | Spécification d'état UI (hybride Explorer/Library) |
| NOTIFICATION_PROGRESS_DESIGN | Politique de conception des notifications et indicateurs de progression |

## API et traitement par lot

| Document | Contenu |
|-------------|------|
| API_RESPONSE_GUIDELINES | Directives de format de réponse API |
| BATCH_API_STANDARD | Spécification standard API de lot |
| ERROR_HANDLING | Politique de gestion des erreurs |

## Système d'Extension

| Document | Contenu |
|-------------|------|
| EXTENSION_TRIAS_POLITICA_SPEC | Spécification du modèle de sécurité à séparation des pouvoirs |
| EXTENSION_SANDBOX_SPEC | Spécification Sandbox & Permission |
| EXTENSION_HOOKS_SPEC | Spécification Extension Hooks |
| EXTENSION_SPEC_FREEZE_PULLBACK_GENERATOR_v0_2 | Spécification Freeze & Pull-back Generator |
| CORE_TO_EXTENSION_MIGRATION_SPEC | Spécification de migration Core → Extension |

## Intégration AI et agent

| Document | Contenu |
|-------------|------|
| AGENT_INTEGRATION_DESIGN | Guide de conception d'intégration AI Agent |
| AGENT_SAFETY_GATEWAY_SPEC | Spécification AI Agent Safety Gateway |
| AI_ANALYSIS_LANGUAGE | Spécification de langue de réponse de l'analyse IA |
| MCP_DEBUG_TOOLS | Spécification des outils de débogage MCP |
| OLLAMA_VLM_INTEGRATION_PITFALLS | Pièges et solutions de l'intégration Ollama/VLM |
| OPENAI_COMPAT_API_DEVLOG | Journal de développement de l'API compatible OpenAI |
| VLM_ROUTING_OCR_SPEC | Spécification de conception VLM Model Routing & OCR |
| VISION_API_IMAGE_FORMATS | Tableau de compatibilité des formats d'images de l'API Vision |
| ai-driven-development-principles | Principes de conception du développement piloté par IA |

## Base de données et performance

| Document | Contenu |
|-------------|------|
| SQLITE_READONLY_SEPARATION | Pattern de séparation lecture/écriture SQLite |
| LARGE_SCALE_QUERY_OPTIMIZATION | Optimisation des requêtes pour grandes DB (280K fichiers) |

## Frontend et UI

| Document | Contenu |
|-------------|------|
| UI_AUDIT_GUIDE | Guide d'audit UI complet |
| UI_BUTTON_PRIORITY_GUIDELINES | Directives de priorité des boutons (méthode contrôleur GC) |
| REUSABLE_UI_WIDGETS | Guide d'intégration des widgets UI réutilisables |
| VIRTUAL_SCROLL_PITFALLS | Précautions et bugs connus du défilement virtuel |
| IMAGE_DISPLAY_OPTIMIZATION | Ressource technique d'optimisation de l'affichage d'images |
| MODAL_LOADING_OPTIMIZATION | Ressource technique d'accélération du chargement des modales détaillées |
| MODAL_MEDIA_LIFECYCLE | Gestion du cycle de vie des médias de la modale |
| CONTAINER_VIEW_PERFORMANCE | Optimisation des performances de la vue conteneur |
| BROWSER_CONNECTION_SATURATION | Disparition des résultats de recherche due à la saturation des connexions navigateur |

## Traitement vidéo

| Document | Contenu |
|-------------|------|
| VIDEO_STREAMING_ARCHITECTURE | Architecture de streaming vidéo |
| VIDEO_PERFORMANCE_OPTIMIZATION_HISTORY | Historique complet des optimisations de performance vidéo |
| VIDEO_METADATA_V2_PLAN | Plan Video Metadata v2 (brouillon) |

## Traitement des fichiers et archives

| Document | Contenu |
|-------------|------|
| NESTED_ZIP_HANDLING | Conception et pièges du traitement ZIP imbriqué |
| ZIP_SCAN_PERFORMANCE | Optimisation des performances de scan ZIP/7z |
| ENCODING_FALLBACK | Fallback d'encodage des noms de fichiers d'archive |
| SD_NAI_PROMPT_SYNTAX_SPEC | Spécification de syntaxe des prompts SD / NAI |

## Multiplateforme et infrastructure

| Document | Contenu |
|-------------|------|
| CROSS_PLATFORM_ISSUES | Guide des différences multiplateformes |
| DRAG_TO_SHARE_CROSS_PLATFORM | Compatibilité multiplateforme du drag & drop |
| ASYNC_EVENT_LOOP_BLOCKING_FIX | Correction du blocage de la boucle d'événements asyncio |
| MODULE_SAFETY | Conception de chargement sécurisé des modules |
| DOCKER_SETUP | Guide de configuration de l'environnement Docker |
| TAURI_DESKTOP_APP | Guide de développement de l'application desktop Tauri |

## Migration

| Document | Contenu |
|-------------|------|
| QUART_MIGRATION_DEVLOG | Ressource technique de migration Flask → Quart (ASGI) |
| CHATLOG_ENHANCED_SPEC | Spécification de l'amélioration des logs de chat |

## Tests et contrôle qualité

| Document | Contenu |
|-------------|------|
| FUZZ_BURN_IN_TEST | Guide de tests Fuzz / Burn-in |
| QA_HANDOFF | Document de remise pour le contrôle qualité |
| yu-ai-manager-qa-agent-prompt | Prompt système de l'agent QA |
| ACCIDENT_POINTS_AND_COMMON_LAYER_SPEED_GUIDE | Guide des points d'accidents fréquents et de vitesse des couches communes |

## Publication et traduction

| Document | Contenu |
|-------------|------|
| RELEASE_PROCEDURE | Procédure de publication |
| TRANSLATION_STYLE_GUIDE | Guide de style de traduction japonais-anglais |
