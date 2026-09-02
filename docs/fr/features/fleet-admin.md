# Administration de flotte (Fleet Admin)

La fonctionnalité Fleet Admin de LAN Cowork permet de gérer centralement plusieurs nœuds yu-ai-manager sur le réseau.

## Vue d'ensemble

- **Collecte d'informations machines** : Centralisation des informations CPU / RAM / GPU / Disque / Version / Temps de fonctionnement de chaque nœud
- **Consultation des logs distants** : Diffusion en direct des logs de n'importe quel pair via SSE depuis l'UI du nœud central
- **Distribution des mises à jour de version** : Instruction de `git pull --ff-only` + graceful restart vers les pairs spécifiés depuis le nœud central

## Prérequis

- L'extension LAN Cowork doit être activée (`extensions["builtin-lan-cowork"].enabled = true`)
- L'appairage entre pairs doit être terminé
- Doit être cloné en tant que dépôt git (pour utiliser la fonctionnalité de mise à jour)
- `psutil>=5.9` doit être installé dans l'environnement virtuel Python

## Configuration

### Configuration du nœud chef

Ajouter ce qui suit à `config.json` :

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "fleet": {
        "chief": true,
        "allow_remote_update": true,
        "allow_update_from": [
          "<peer_id appairé>"
        ],
        "allow_log_stream_from": [
          "<peer_id appairé>"
        ],
        "allowed_branches": [
          "main"
        ],
        "timings": {
          "chief_observation_sec": 25,
          "peers_poll_interval_sec": 30,
          "heartbeat_timeout_sec": 60,
          "update_job_timeout_sec": 600,
          "postcheck_timeout_sec": 180
        }
      }
    }
  }
}
```

### Configuration des nœuds ordinaires

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "fleet": {
        "chief": false,
        "allow_remote_update": true,
        "allow_update_from": [
          "<peer_id du chef>"
        ],
        "allow_log_stream_from": [
          "<peer_id du chef>"
        ],
        "allowed_branches": [
          "main"
        ]
      }
    }
  }
}
```

## Accès à l'UI Fleet Admin

Accédez à `/ext/lan_cowork/fleet/ui` depuis le navigateur du nœud chef.

Cette URL retourne 404 sur les nœuds ordinaires.

## Fonctionnalités des onglets

### Onglet Vue d'ensemble

- Affichage en cartes de tous les nœuds (avec barres d'utilisation CPU / RAM / GPU / Disque)
- Affichage de l'état : en ligne / hors ligne / échec de récupération des informations
- Badge `[CHIEF]` sur le nœud chef
- Mise à jour automatique toutes les 30 secondes + bouton de mise à jour manuelle
- Bannière d'avertissement lors de la détection de plusieurs chefs

### Onglet Logs

- Affichage en direct des logs de n'importe quel pair via SSE (style tail -f)
- Filtre de niveau (DEBUG / INFO / WARNING / ERROR)
- Zone de recherche (filtre côté client)
- Défilement automatique ON/OFF
- Pause / Reprise

### Onglet Mises à jour

- Tableau comparatif des versions / commits git / branches
- Bouton « Pull & Restart » pour chaque nœud individuel
- Mise à jour groupée de plusieurs nœuds (dispatch)
- Affichage de la progression (precheck → fetching → pulling → restarting → online)
- Le chef est exclu des mises à jour groupées (bouton individuel uniquement)

## Sécurité

### Structure d'autorisation à deux niveaux

1. **Appairage (vérification d'identité)** : Identification de « qui » par Bearer token
2. **Allowlist (permissions)** : Autorisation explicite par opération

Être appairé ne signifie pas avoir tous les droits.

### Exemple de configuration allowlist

```json
"allow_update_from": [
  "abc123def456",
  {"peer_id": "def456abc789"}
]
```

- Les formats chaîne et `{peer_id: ...}` sont tous deux acceptables
- Le peer_id de la machine locale est automatiquement ajouté (pas de configuration nécessaire)

## Rétrogradation automatique du chef

Si plusieurs nœuds avec `chief = true` démarrent sur le même réseau, le nœud démarré en dernier est automatiquement rétrogradé (après `chief_observation_sec` secondes d'observation).

Pour redevenir chef après une rétrogradation, un redémarrage après modification de la configuration est nécessaire (pas de promotion automatique).

## Contraintes des mises à jour git

- Seul `git pull --ff-only` est utilisé (merge/rebase ne sont pas utilisés)
- En cas d'impossibilité de fast-forward, la mise à jour passe immédiatement en `failed` (l'arbre de travail n'est pas modifié)
- La mise à jour est refusée si l'arbre de travail est sale (dirty)

## Dépannage

| Symptôme | Cause | Solution |
|---|---|---|
| `/fleet/ui` retourne 404 | `chief = true` non configuré | Vérifier config.json et redémarrer |
| `/fleet/info` retourne 500 | psutil non installé | `uv pip install psutil>=5.9` |
| Erreur `git_not_available` | git absent ou PATH incorrect | Vérifier l'installation de git |
| `postcheck_online` timeout après mise à jour | Redémarrage de plus de 3 minutes | Augmenter `postcheck_timeout_sec` |
| La bannière de détection de plusieurs chefs ne disparaît pas | Ancien processus chef restant | Redémarrer l'ancien chef |

## Référence API

### Commun à tous les nœuds

| Endpoint | Description |
|---|---|
| `GET /ext/lan_cowork/fleet/info` | Informations machine (authentification Bearer requise) |
| `GET /ext/lan_cowork/fleet/logs/stream` | SSE des logs locaux (autorisation allowlist) |
| `POST /ext/lan_cowork/fleet/update` | git pull + redémarrage (autorisation allowlist) |
| `GET /ext/lan_cowork/fleet/update/status` | Consultation de l'état du job de mise à jour |

### Nœud chef uniquement

| Endpoint | Description |
|---|---|
| `GET /ext/lan_cowork/fleet/peers` | Agrégation des informations de tous les pairs |
| `GET /ext/lan_cowork/fleet/logs/stream?peer_id=X` | Relai SSE des logs d'un pair spécifié |
| `POST /ext/lan_cowork/fleet/update/dispatch` | Mise à jour groupée vers plusieurs pairs |
| `GET /ext/lan_cowork/fleet/update/dispatch/status` | Consultation de la progression du dispatch |
| `GET /ext/lan_cowork/fleet/ui` | UI de gestion Fleet |
