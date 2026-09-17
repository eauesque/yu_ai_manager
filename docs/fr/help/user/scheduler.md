# Planificateur de Tâches

## Vue d'ensemble

Le planificateur de tâches est une fonctionnalité qui exécute automatiquement des tâches périodiques comme la maintenance de base de données ou le polling de services externes. Un planificateur en arrière-plan basé sur APScheduler gère les jobs avec des déclencheurs cron / interval.

Depuis la page planificateur du WebUI (`/scheduler`), vous pouvez consulter la liste des jobs, ajouter, supprimer, mettre en pause ou exécuter immédiatement.

## Configuration

Le planificateur est activé par défaut. Contrôlable via `scheduler.enabled` dans `config.json` :

```json
{
  "scheduler": {
    "enabled": true,
    "jobs": {
      "db_vacuum": { "enabled": true, "trigger": "cron", "day_of_week": "sun", "hour": 3, "minute": 0 },
      "db_integrity_check": { "enabled": true, "trigger": "cron", "hour": 4, "minute": 0 },
      "thumbnail_cleanup": { "enabled": true, "trigger": "cron", "hour": 5, "minute": 0 }
    }
  }
}
```

Les jobs décrits dans `config.json` sont enregistrés automatiquement au démarrage du serveur. Les jobs ajoutés depuis le WebUI ne sont valides que pour la session serveur (disparaissent au redémarrage).

## Liste des Jobs Intégrés

### Maintenance de la Base de Données

| ID du job | Description | Fréquence recommandée |
|-----------|------|---------|
| `db_vacuum` | Exécuter SQLite VACUUM pour récupérer l'espace inutilisé | 1 fois/semaine |
| `db_integrity_check` | Vérifier l'intégrité de la base avec `PRAGMA integrity_check` | Quotidien |
| `db_backup` | Créer une sauvegarde de la base (via builtin-backup extension) | Quotidien |

### Gestion du Cache et des Index

| ID du job | Description | Fréquence recommandée |
|-----------|------|---------|
| `thumbnail_cleanup` | Supprimer les fichiers de cache de miniatures expirés | Quotidien |
| `prune_unused_tags` | Supprimer les enregistrements de tags orphelins non liés à des fichiers | 1 fois/semaine à mois |
| `refresh_monthly_stats` | Mettre à jour le cache pré-calculé des statistiques mensuelles | Quotidien |
| `rebuild_groups_index` | Reconstruire le cache d'index de groupe dossier/archive | 1 fois/semaine |

### Intégration de Services Externes

| ID du job | Description | Fréquence recommandée |
|-----------|------|---------|
| `github_issue_poll` | Interroger l'API GitHub et récupérer les nouveaux Issues dans la file locale | 5 min à 1 h |
| `bsky_notification_poll` | Interroger l'API Bluesky pour récupérer les nouvelles notifications | 5 min à 1 h |

## Configuration des Déclencheurs

### Déclencheur cron

S'exécute à des horaires, jours de semaine ou dates précis. Méthode de spécification similaire à Unix cron.

| Paramètre | Exemple de valeur | Description |
|-----------|--------|------|
| `hour` | `3`, `*/6`, `1,13` | Heure (0-23). `*` pour toutes les heures |
| `minute` | `0`, `30`, `0,30` | Minute (0-59). `*` pour chaque minute |
| `day` | `1`, `15`, `1,15` | Jour (1-31). `*` pour chaque jour |
| `day_of_week` | `sun`, `mon-fri`, `0-4` | Jour de la semaine. `*` pour chaque jour |

**Exemple** : exécuter le 1er et le 15 de chaque mois à 2h30 du matin

```json
{ "trigger": "cron", "day": "1,15", "hour": 2, "minute": 30 }
```

### Déclencheur interval

S'exécute répétitivement à intervalle fixe.

| Paramètre | Exemple de valeur | Description |
|-----------|--------|------|
| `hours` | `2` | Intervalle en heures |
| `minutes` | `30` | Intervalle en minutes |

**Exemple** : s'exécuter toutes les 30 minutes

```json
{ "trigger": "interval", "minutes": 30 }
```

## Utilisation du WebUI

### Liste des Jobs

À l'ouverture de la page du planificateur, la liste des jobs enregistrés s'affiche. Vous pouvez vérifier l'état (activé/en pause), les paramètres de déclencheur et la prochaine exécution.

### Ajouter un Job

1. Cliquer sur **Ajouter un job**
2. Saisir l'ID du job (nom unique)
3. Sélectionner la fonction à exécuter dans la liste déroulante
4. Sélectionner le type de déclencheur (cron / interval)
5. Saisir les paramètres de planification (spécification wildcard possible avec `*`)
6. Cliquer sur **Ajouter**

### Opérations sur un Job

- **Exécuter maintenant** : exécute le job une fois immédiatement, hors planification
- **Pause / Reprendre** : arrête/reprend temporairement l'exécution périodique du job
- **Supprimer** : supprime complètement le job (les jobs de config.json sont restaurés au prochain démarrage)

### Historique d'Exécution

L'historique récent d'exécution (jusqu'à 50 entrées) s'affiche en bas de la page. Vous pouvez vérifier le statut succès/échec et les messages de résultat. La fin d'exécution d'un job est mise à jour en temps réel via SSE.

## Outils MCP

Vous pouvez contrôler le planificateur depuis les clients MCP (Claude Desktop, etc.) :

| Outil | Description |
|--------|------|
| `get_scheduler_status` | Obtenir l'état de fonctionnement du planificateur |
| `list_scheduled_jobs` | Obtenir la liste des jobs enregistrés |
| `trigger_scheduled_job` | Exécuter un job immédiatement |
| `pause_scheduled_job` | Mettre un job en pause |
| `resume_scheduled_job` | Reprendre un job |
| `get_scheduler_history` | Obtenir l'historique d'exécution |

## Astuces

- Les **jobs de polling externe** (`github_issue_poll`, `bsky_notification_poll`) conviennent mieux au déclencheur interval. Avec cron à horaire fixe, l'intervalle de polling peut être trop large
- **`db_vacuum`** acquiert un verrou d'écriture, il est recommandé de le configurer la nuit quand l'accès est faible
- **`db_backup`** respecte le paramètre de cooldown de l'extension builtin-backup. Même configuré avec un intervalle court, il saute pendant la période de cooldown
- **L'historique d'exécution est conservé en mémoire** (max 100 entrées). L'historique est effacé au redémarrage du serveur
