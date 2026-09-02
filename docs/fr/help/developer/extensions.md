# Extensions

Des fonctionnalités peuvent être ajoutées à YU AI Manager via le système d'Extension.
43 Extensions intégrées sont actuellement embarquées, classées en 6 catégories.

## Liste des Extensions intégrées

### Extraction de métadonnées (metadata)

| Extension | Description |
|-----------|------|
| builtin-a1111 | Extraction des métadonnées PNG/WebP/WebM de Automatic1111 / SD WebUI |
| builtin-novelai-v3 | Extraction des métadonnées NovelAI V3 et antérieur |
| builtin-novelai-v4 | Extraction des métadonnées NovelAI V4 (support Character Prompts, Vibe Transfer) |
| builtin-comfyui | Analyse JSON de workflow ComfyUI |
| builtin-annotations | Sauvegarde, recherche et opérations en masse des annotations de fichiers |
| builtin-ratings | Système de notation par étoiles (1 à 5 étoiles) |
| builtin-tag-dictionary | Recherche, import et découpage du dictionnaire de tags Danbooru |

### Intégration Bridge (bridge)

| Extension | Description |
|-----------|------|
| builtin-sd-webui-bridge | Intégration SD WebUI / Forge (génération d'images, gestion des modèles) |
| builtin-nai-bridge | Intégration API NovelAI (génération d'images) |
| builtin-comfyui-bridge | Intégration ComfyUI (exécution de workflow) |

### Prompts (prompt)

| Extension | Description |
|-----------|------|
| builtin-prompt-library | Bibliothèque et organisation des prompts |
| builtin-prompt-syntax | Coloration syntaxique des prompts, détection d'erreurs (support NAI/SD/DP) |
| builtin-prompt-simulator | Simulateur Dynamic Prompts, calcul de poids, conversion |
| builtin-sd-nai-convert | Conversion réciproque de prompts SD ↔ NovelAI |

### IA (ai)

| Extension | Description |
|-----------|------|
| builtin-analysis | Analyse d'images IA (Claude, OpenAI, Ollama, Hailo VLM) |
| builtin-wd-tagger | Taggage automatique WD-Tagger (moteur ONNX + VLM) |
| builtin-ocr | OCR VLM — extraction de texte, analyse structurée, traduction |
| builtin-clip-search | Moteur de recherche d'images sémantique CLIP |
| builtin-clip-onnx | Backend encodeur CLIP ONNX Runtime |
| builtin-clip-coreml | Encodeur CLIP Core ML (Apple Neural Engine) |
| builtin-hailo-semantic-search | Recherche sémantique Hailo-10H |
| builtin-hailo-yolo-detect | Détection d'objets YOLO Hailo-10H |
| builtin-hailo-genai | Hailo-10H GenAI (LLM/VLM/S2T) |
| builtin-speech-to-text | Transcription vocale (Hailo NPU / CUDA / ROCm / CPU) |
| builtin-audio-analysis | Analyse audio (Whisper local / API OpenAI) |
| builtin-video-analysis | Analyse vidéo IA (multi-keyframe + Gemini) |
| builtin-inference | Détection du provider ONNX Runtime, accélération GPU |

### Bibliothèque (library)

| Extension | Description |
|-----------|------|
| builtin-favorites-manager | Gestion des favoris et collections |
| builtin-freeze-pullback | Génération vidéo Freeze & Pull-back (effet Ken Burns) |
| builtin-download | Téléchargement ZIP groupé d'images sélectionnées |
| builtin-chatlog | Importeur et visionneuse de logs de chat (Claude / ChatGPT) |
| builtin-md-viewer | Visionneuse de fichiers Markdown (recherche plein texte FTS5) |
| builtin-cross-search | Recherche croisée (MD, logs de chat, prompts, texte) |
| builtin-lan-share | Partage de collections LAN (authentification par token avec limite de temps) |
| builtin-stats | Statistiques (timeline, jalons) |
| builtin-trophy | Système de trophées et réalisations |
| builtin-export | Hooks d'export (conversion d'enregistrements lors de la sortie CSV) |

### Système (system)

| Extension | Description |
|-----------|------|
| builtin-auto-scan-watcher | Détection automatique des modifications de fichiers, mise à jour différentielle |
| builtin-mcp-client | Gestion des connexions à des serveurs MCP externes |
| builtin-backup | Sauvegarde/restauration DB, planificateur |
| builtin-sns-share | Partage SNS (Bluesky, X/Twitter) |
| builtin-webhook | Dispatcher Webhook (distribution HTTP pilotée par événements) |
| builtin-debug-check | CLI de diagnostic de débogage |
| builtin-github-integration | Surveillance GitHub Issues, triage, suivi PR/Discussion/Release |

## Gestion des Extensions

Les opérations suivantes sont disponibles depuis Settings > onglet Extensions :

- **Activer/Désactiver** : Commutation instantanée avec le bouton bascule
- **Nouvelle installation** : Installer en spécifiant l'URL d'un dépôt Git
- **Marketplace** : Recherche et installation en un clic des Extensions publiques
- **Mise à jour** : Mise à jour des Extensions basées sur Git vers la dernière version
- **Désinstallation** : Suppression des Extensions tierces

### Gestion via API

```bash
# Liste des Extensions
curl -H "Authorization: Bearer sk_xxx" \
     http://localhost:5000/api/extensions

# Activer/Désactiver
curl -X POST -H "Authorization: Bearer sk_xxx" \
     http://localhost:5000/api/extensions/builtin_wd_tagger/toggle

# Installation depuis Git
curl -X POST -H "Authorization: Bearer sk_xxx" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://github.com/user/my-extension.git"}' \
     http://localhost:5000/api/extensions/install
```

## Extension Sandbox

Les Extensions tierces sont protégées par un sandbox.

### Niveaux de confiance

| Niveau | Cible | Restrictions |
|--------|------|------|
| L0 (TRUSTED) | `builtin-*` | Aucune restriction |
| L2 (UNTRUSTED) | Autres | Restrictions DB/FS/réseau |

### 4 phases du sandbox

1. **Capability Token** : Gestion des permissions avec token signé HMAC-SHA256. Validité de 24 heures
2. **SandboxedDB / SandboxedFS** : Les Extensions avec `db:read` uniquement n'autorisent que SELECT. Accès aux fichiers contrôlé par chemin
3. **SandboxedHTTPClient / ImportGuard** : Prévention SSRF, surveillance des imports à l'exécution, détection de falsification SHA-256
4. **Isolation de processus (Linux)** : Exécution des Extensions L2 dans un processus séparé. IPC JSON-RPC 2.0 via socket Unix

### Isolation au niveau OS (optionnel)

- **Linux** : Génération automatique de profil AppArmor
- **macOS** : sandbox-exec (expérimental)
- **Windows** : Restricted Token + Job Object

## Structure des répertoires

```
extensions/builtin_<name>/
  extension.json            # Manifeste (nom, version, permissions, etc.)
  <name>_ext.py             # Point d'entrée (expose get_blueprint())
  templates/<name>/          # Templates Jinja2
  core_impl/                 # Logique métier (optionnel)
```

### Champs obligatoires de extension.json

```json
{
  "name": "my-extension",
  "version": "1.0.0",
  "entrypoint": "my_extension_ext.py",
  "has_blueprint": true,
  "category": "library"
}
```

Les catégories sont : `metadata`, `bridge`, `prompt`, `ai`, `library`, `system`.

## Extension Module API v2 (support ES Module)

Depuis v4.29.0, les Extensions peuvent être écrites avec le pattern ES Module utilisant `<script type="module">` et Import Maps.

### Activation

Ajouter `"script_type": "module"` dans `extension.json`.

### Utilisation

```html
<script nonce="{{ csp_nonce }}" type="module">
import { showToast, sseSubscribe, tr, apiFetch, escapeHtml } from 'yu-api';

// Notification toast
showToast('Sauvegardé');

// Abonnement aux événements SSE
sseSubscribe('scan.progress', (data) => {
  console.log('Progression :', data);
});

// Traduction i18n
const label = tr('my_ext.title', 'My Extension');

// Appel API (en-tête CSRF ajouté automatiquement)
const res = await apiFetch('/ext/my-extension/api/data');
const json = await res.json();
</script>
```

### Liste des API publiques

| Fonction | Description |
|---|---|
| `showToast(message, isError?)` | Afficher une notification toast |
| `sseSubscribe(eventType, handler)` | S'abonner à un événement SSE |
| `sseUnsubscribe(eventType, handler)` | Se désabonner d'un événement SSE |
| `tr(path, a?, b?)` | Résoudre une clé de traduction i18n |
| `apiFetch(path, opts?)` | Wrapper fetch avec CSRF |
| `apiUrl(path)` | Construire une URL API |
| `escapeHtml(text)` | Échapper les caractères spéciaux HTML |

### Compatibilité avec l'ancien système

Les Extensions avec `"script_type": "classic"` (valeur par défaut) peuvent continuer à utiliser les fonctions globales comme `window.showToast()`.
La réécriture des Extensions existantes n'est pas nécessaire.
