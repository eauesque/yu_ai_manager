# API Analyse

API pour l'analyse de fichiers et la gestion des racines d'analyse.

## Contrôle d'analyse

### POST /api/scan/start

Démarrer une analyse.

### Requête

```json
{
  "root_indices": [0, 1],
  "force": false
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `root_indices` | int[] | Indices des racines à analyser (omettez pour toutes les racines) |
| `force` | bool | Ré-analyser les fichiers existants |

### Réponse

```json
{
  "ok": true,
  "message": "Scan started"
}
```

### GET /api/scan/status

Récupérer la progression de l'analyse.

### Réponse

```json
{
  "scanning": true,
  "progress": 45,
  "total": 1500,
  "current_file": "/images/output/00042.png",
  "errors": 0,
  "started_at": 1709500000
}
```

### POST /api/scan/cancel

Annuler une analyse en cours.

### GET /api/scan/interrupted

Récupérer les informations sur une analyse interrompue.

### POST /api/scan/resume

Reprendre une analyse interrompue.

### POST /api/scan/dismiss

Abandonner l'état d'analyse interrompue.

## CLI du travailleur d'analyse

Depuis v3.27.0, les analyses s'exécutent dans un processus séparé (travailleur).
Le travailleur peut être contrôlé directement depuis la CLI en plus de l'API WebUI.

```bash
# Démarrer une analyse
python -m core.scan.scan_worker start --db ./tags.db --root /path/to/images [--scan-zips] [--force] [--resume]

# Arrêter une analyse (SIGTERM -> arrêt gracieux)
python -m core.scan.scan_worker stop

# Vérifier le statut
python -m core.scan.scan_worker status
```

### Fichiers IPC

| Fichier | Contenu |
|---------|---------|
| `/tmp/yu-scan/worker.pid` | PID du travailleur |
| `/tmp/yu-scan/progress.json` | Progression (JSON : running, phase, current, total, percent, message, detail, error) |

La WebUI scrute ce fichier de progression et transmet les données via `GET /api/scan/status` et événements SSE (`scan.progress`, `scan.complete`).

## Erreurs d'analyse

### GET /api/scan-errors

Liste des erreurs qui se sont produites lors de l'analyse.

| Paramètre | Type | Description |
|-----------|------|-------------|
| `type` | string | Filtre de type d'erreur |
| `resolved` | bool | Uniquement les erreurs résolues |
| `limit` | int | Nombre de résultats |

### POST /api/scan-errors/<id>/resolve

Marquer une erreur comme résolue.

### POST /api/scan-errors/clear

Supprimer toutes les erreurs résolues à la fois.

## Gestion des racines d'analyse

### GET /api/scan-roots

Lister les racines d'analyse enregistrées.

### Réponse

```json
{
  "roots": [
    {
      "path": "O:\\webui\\outputs",
      "enabled": true,
      "file_count": 15000
    }
  ]
}
```

### POST /api/scan-roots

Ajouter une racine d'analyse.

```json
{
  "path": "O:\\webui\\outputs"
}
```

### PUT /api/scan-roots/<index>

Mettre à jour une racine d'analyse (changer le chemin, basculer activé/désactivé).

### DELETE /api/scan-roots/<index>

Supprimer une racine d'analyse.

## Remplissage rétroactif des hachages

### POST /api/hash-backfill/start

Démarrer le calcul des hachages en arrière-plan pour les fichiers existants.

### GET /api/hash-backfill/status

Récupérer la progression.

### POST /api/hash-backfill/cancel

Annuler le calcul.

## Travaux en arrière-plan

### GET /api/jobs/status

Statut de tous les travaux en arrière-plan. Utilisé pour l'affichage de la bannière UI.

```json
{
  "jobs": [
    {
      "type": "scan",
      "status": "running",
      "progress": 45,
      "total": 1500
    }
  ]
}
```
