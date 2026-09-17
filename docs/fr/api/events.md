# API Événements (SSE)

Livraison d'événements en temps réel via Server-Sent Events.

## GET /api/events/stream

Le flux d'événements principal. Toutes les pages partagent une seule connexion.

### Connexion

```javascript
// À partir d'un module TypeScript
import { sseSubscribe } from '../sse';
sseSubscribe('scan.complete', (data) => { ... });

// À partir d'un script en ligne de modèle
window.sseSubscribe('scan.complete', (data) => { ... });
```

**Important** : N'utilisez pas `new EventSource()` directement. `window.EventSource` est remplacé par un Proxy, donc l'utilisation directe provoque des erreurs.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `types` | string | Types d'événements à s'abonner (séparés par des virgules ; omettez pour tous les événements) |

### Limites de connexion

- Jusqu'à 10 connexions simultanées par IP
- Conscient de la visibilité : la connexion entre dans un état réduit lorsque l'onglet est caché
- Reconnexion automatique avec backoff exponentiel

## Types d'événements

### Analyse

| Événement | Données | Description |
|-----------|---------|-------------|
| `scan.progress` | `{ scanned, total, current_file }` | Progression de l'analyse |
| `scan.complete` | `{ added_count, updated_count, added_ids?, updated_ids? }` | Analyse complète |
| `config.scan_roots_changed` | `{}` | Notification de modification de la racine d'analyse |

### Favoris & Collections

| Événement | Données | Description |
|-----------|---------|-------------|
| `favorite.add` | `{ file_id, collection_id }` | Favori ajouté |
| `favorite.remove` | `{ file_id, collection_id }` | Favori supprimé |
| `collection.create` | `{ id, name }` | Collection créée |
| `collection.delete` | `{ id }` | Collection supprimée |

### Analyse IA & Marquage

| Événement | Données | Description |
|-----------|---------|-------------|
| `semantic_index.start` | `{ total }` | Indexation CLIP commencée |
| `semantic_index.progress` | `{ done, total }` | Progression de l'indexation CLIP |
| `semantic_index.complete` | `{ indexed }` | Indexation CLIP complète |
| `vlm_caption.start` | `{ total }` | Captionnage VLM commencé |
| `vlm_caption.progress` | `{ done, total }` | Progression du captionnage VLM |
| `vlm_caption.complete` | `{ processed }` | Captionnage VLM complété |
| `yolo_detect.start` | `{ total }` | Détection YOLO commencée |
| `yolo_detect.progress` | `{ done, total }` | Progression de la détection YOLO |
| `yolo_detect.complete` | `{ detected }` | Détection YOLO complétée |

### Freeze & Pull-back

| Événement | Données | Description |
|-----------|---------|-------------|
| `fpb.start` | `{ job_id }` | Travail commencé |
| `fpb.progress` | `{ job_id, frame, total }` | Progression de la trame |
| `fpb.complete` | `{ job_id, output_path }` | Travail complété |
| `fpb.error` | `{ job_id, error }` | Erreur du travail |

### Journaux de chat

| Événement | Données | Description |
|-----------|---------|-------------|
| `chatlog_reprocess.start` | `{ total }` | Retraitement IA commencé |
| `chatlog_reprocess.progress` | `{ done, total }` | Progression du retraitement IA |
| `chatlog_reprocess.complete` | `{ processed }` | Retraitement IA complété |
| `chatlog_reprocess.error` | `{ error }` | Erreur du retraitement IA |

### Planificateur

| Événement | Données | Description |
|-----------|---------|-------------|
| `scheduler.job_executed` | `{ job_id, result }` | Travail planifié complété avec succès |
| `scheduler.job_error` | `{ job_id, error }` | Échec du travail planifié |

## GET /api/logs/stream

Un flux SSE dédié pour les journaux du serveur. Il fonctionne indépendamment du flux principal.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `level` | string | Niveau de journal minimum (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

### Événements

| Événement | Données | Description |
|-----------|---------|-------------|
| `log.entry` | `{ seq, ts, level, name, message }` | Entrée du journal |

### Limites de connexion

- Jusqu'à 3 connexions simultanées par IP (séparé du flux principal)
- Intervalle de heartbeat de 15 secondes (`: heartbeat\n\n`)
