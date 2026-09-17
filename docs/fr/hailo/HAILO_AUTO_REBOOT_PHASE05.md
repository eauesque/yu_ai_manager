# Guide d'exploitation Hailo Auto-Reboot Phase 0.5

**Créé** : 2026-05-17 (v4.215.0)
**Cible** : Exploitation d'observation de fuite CMA sur Raspberry Pi 5 + Hailo-10H + HailoRT 5.3.0
**Statut** : Phase d'observation. Aucun redémarrage réel n'est effectué ; seuls les événements `would_fire` sont enregistrés.

---

## 1. Objectif de la Phase 0.5

La Phase 0.5 est la phase d'observation de la conception du redémarrage automatique contre les fuites CMA dans HailoRT 5.3.0 + `hailo1x_pci`.

Dans cette phase, la machine à états calcule les états suivants :

| État | Condition |
|---|---|
| `idle` | État normal |
| `prewarn` | `CmaFree < 80 Mo` persiste pendant 180 secondes |
| `draining` | `CmaFree < 30 Mo` persiste pendant 60 secondes, ou le pré-rejet de `acquire_genai` survient 3 fois consécutives |
| `would_fire` | 120 secondes écoulées depuis `draining` |

Important : Dans la Phase 0.5, même si `would_fire` est atteint, le Pi N'EST PAS redémarré. L'événement est uniquement enregistré en JSON Lines dans `logs/hailo_auto_reboot.log`.

---

## 2. Pourquoi la valeur par défaut est `mode = "off"`

La valeur par défaut de `hailo.auto_reboot.mode` est `"off"`. Comme le redémarrage automatique peut interrompre le travail de l'opérateur, l'observation n'est démarrée que dans les environnements où l'opérateur a explicitement choisi d'y participer (opt-in).

La configuration recommandée pour la Phase 0.5 est la suivante :

```json
{
  "hailo": {
    "auto_reboot": {
      "mode": "lazy",
      "dry_run": true,
      "prewarn_threshold_mb": 80,
      "prewarn_duration_seconds": 180,
      "drain_threshold_mb": 30,
      "drain_duration_seconds": 60,
      "drain_consecutive_rejects": 3,
      "fire_grace_seconds": 120,
      "poll_interval_seconds": 30
    }
  }
}
```

`dry_run = true` est une condition préalable à la Phase 0.5. Le chemin de redémarrage réel est géré à partir de la Phase 4.

### 2.1 Procédure d'opt-in

La configuration de démarrage priorise le fichier spécifié via `--config` ou `TAGDB_CONFIG`. Si non spécifié, elle lit `config.json` à la racine du dépôt, puis `tagdb_config.json`.

Exemple :

```bash
cd <repo>
cp config.json config.json.bak.$(date +%Y%m%d-%H%M%S)
```

Ajoutez les paramètres suivants à `<repo>/config.json` ou au fichier JSON spécifié via `--config` / `TAGDB_CONFIG` en exploitation :

```json
{
  "hailo": {
    "auto_reboot": {
      "mode": "lazy",
      "dry_run": true,
      "poll_interval_seconds": 30
    }
  }
}
```

Redémarrez le serveur pour appliquer la configuration. Conservez les arguments que vous utilisez réellement selon votre méthode de démarrage.

```bash
uv run python web_ui.py --config config.json --db data/tags.db
```

Si vous exploitez avec systemd, redémarrez l'unité correspondante :

```bash
sudo systemctl restart yu-ai-manager.service
```

### 2.2 Procédure de désactivation

Remettez `hailo.auto_reboot.mode` à `"off"` dans la même configuration et redémarrez le serveur.

```json
{
  "hailo": {
    "auto_reboot": {
      "mode": "off",
      "dry_run": true
    }
  }
}
```

Avec `mode = "off"`, les événements d'observation en JSON Lines sont conservés, mais aucun résumé WARN n'est émis dans `error.log`.

---

## 3. Comment lire les journaux

Les journaux d'observation sont écrits dans le fichier suivant :

```text
logs/hailo_auto_reboot.log
```

Le format est JSON Lines. Les principaux événements sont les suivants :

| Événement | Signification |
|---|---|
| `boot_baseline` | Point de départ de l'observation au démarrage |
| `prewarn_entered` | Condition PREWARN satisfaite |
| `drain_entered` | Condition DRAIN satisfaite |
| `would_fire` | Point qui deviendrait un déclencheur de redémarrage en Phase 1+ |
| `drain_cleared` | CMA récupéré et DRAIN effacé |

Exemple :

```json
{"event":"would_fire","cma_free_mb":18,"mode":"lazy","dry_run":true,"state":"would_fire","hailo_runtime_version":"5.3.0"}
```

Exemples de commandes de vérification :

```bash
tail -F logs/hailo_auto_reboot.log | jq -r '[.ts, .event, .cma_free_mb, .state] | @tsv'
```

```bash
grep would_fire logs/hailo_auto_reboot.log
grep drain_entered logs/hailo_auto_reboot.log
```

Si `would_fire` se produit fréquemment, cela indique qu'avec les seuils actuels, un redémarrage du Pi sera très probablement nécessaire en exploitation réelle. À l'inverse, si seul `prewarn_entered` apparaît sans progresser vers `drain_entered`, les seuils ou les délais de grâce peuvent être réajustés avant la Phase 1.

---

## 4. Procédure de vérification de l'API

Vérifiez `/api/system/cma` avec la clé API d'administration.

```bash
curl -H "X-API-Key: <admin-key>" \
  http://<host>:<port>/ext/hailo-genai/api/system/cma
```

Examinez `cma.auto_reboot.enabled`, `cma.auto_reboot.mode`, `cma.auto_reboot.state` et `cma.auto_reboot.consecutive_rejects` dans la réponse.

```json
{
  "cma": {
    "auto_reboot": {
      "enabled": true,
      "mode": "lazy",
      "state": "idle",
      "consecutive_rejects": 0
    }
  }
}
```

---

## 5. Période d'observation

L'objectif est de 1 à 2 semaines. Assurez-vous que la période couvre au minimum les modèles suivants :

- Utilisation normale du chat LLM
- Utilisation prolongée du chat
- Opérations provoquant des échecs de chargement du modèle Hailo GenAI ou des pré-rejets
- Premier chargement après redémarrage du Pi

L'observation est considérée comme complète lorsque les données de fréquence pour `prewarn_entered` / `drain_entered` / `would_fire` sur 1 à 2 semaines peuvent être agrégées. Après l'observation, examinez le nombre d'occurrences de `would_fire`, la raison de `drain_entered` (`cma` / `rejects`) et le taux de diminution de `CmaFree` pour finaliser les seuils avant de déployer la Phase 1.

Exemple d'agrégation :

```bash
jq -r '.event' logs/hailo_auto_reboot.log | sort | uniq -c
```

---

## 6. Documents connexes

- `docs/superpowers/specs/2026-05-17-hailo-auto-reboot-design.md`
- `docs/ja/hailo/HAILO_CMA_LEAK_HAILORT_5_3_0.md`
- `logs/hailo_cma.log` (`core/hailo_device_core/device_helpers.py::log_hailo_cma_event`)
- `logs/hailo_auto_reboot.log` (`core/hailo_device_core/auto_reboot_logger.py`)
