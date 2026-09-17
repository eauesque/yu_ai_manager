# Hailo Auto-Reboot Phase 0.5 — Manuel d'exploitation pour cet environnement

**Créé** : 2026-05-17 (v4.215.1)
**Environnement cible** : — Pi 5 exécutant ce dépôt
**Objectif** : Un manuel autonome permettant de démarrer, vérifier et conclure l'observation de la Phase 0.5, même si la session de chat d'origine est perdue.
**Spécification de conception** : `docs/superpowers/specs/2026-05-17-hailo-auto-reboot-design.md` (rev3 APPROVED)
**Guide général de l'opérateur** : `docs/fr/hailo/HAILO_AUTO_REBOOT_PHASE05.md` (ce document est la variante spécifique à cet environnement)

---

## 0. Prérequis et travaux déjà effectués

- L'implémentation d'observation de la Phase 0.5 a été fusionnée et poussée dans main en v4.215.1 (commit `80af4fb73` + merge `69be148c6`)
- `config.json` (racine du dépôt) contient déjà le bloc `hailo.auto_reboot`, **ajouté le 2026-05-17**
  - Paramètres recommandés : `mode = "lazy"` + `dry_run = true`
  - Sauvegarde : `config.json.bak.<horodatage>`
- **Aucun redémarrage réel ne sera déclenché** (`dry_run = true` + la conception de la Phase 0.5 enregistre uniquement les événements `would_fire`)

Vérifier config.json :

```bash
cd /home/pi/GitHub/yu_ai_manager
jq .hailo.auto_reboot config.json
# → {"mode":"lazy","dry_run":true,...} doit apparaître
```

---

## 1. Procédure de premier démarrage et d'activation

### 1.1 Redémarrage du serveur

Un redémarrage est nécessaire pour appliquer le changement de configuration. **Redémarrez en utilisant la même méthode de démarrage qu'actuellement.**

Commande de démarrage typique (à adapter à votre environnement) :

```bash
cd /home/pi/GitHub/yu_ai_manager
uv run python web_ui.py --config config.json --db data/tags.db
```

Si le service tourne sous systemd, redémarrer l'unité correspondante avec `sudo systemctl restart <unit>`.

### 1.2 Vérification dans les 30 secondes suivant le démarrage (3 points)

#### A. L'événement `boot_baseline` est-il enregistré ?

```bash
tail -n 20 /home/pi/GitHub/yu_ai_manager/logs/hailo_auto_reboot.log
```

Attendu : une ligne contenant `{"event":"boot_baseline","state":"idle","mode":"lazy","dry_run":true,"cma_free_mb":<int|null>,"hailo_runtime_version":"5.3.0",...}`.

**Dépannage si absent** :

- `logs/hailo_auto_reboot.log` n'existe pas → la boucle judge ne tourne pas (peut-être pas démarrée en mode `["full"]`, ou la variable d'environnement `TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE` est définie)
- Le fichier existe mais est vide → échec de résolution de chemin dans `core/hailo_device_core/auto_reboot_logger.py` ; vérifier les permissions du répertoire `logs/`
- `cma_free_mb: null` → échec de lecture de `/proc/meminfo` (comportement attendu sur du matériel autre que Pi, inoffensif)

#### B. L'opt-in est-il actif via la réponse `/api/system/cma` ?

Si connecté avec un PIN dans le navigateur, aucune clé API n'est requise. Utiliser curl ou exécuter dans la console DevTools du navigateur (avec session PIN active) :

```js
fetch("/ext/hailo-genai/api/system/cma").then(r => r.json()).then(j => console.log(j.cma.auto_reboot))
```

Attendu :

```json
{
  "enabled": true,
  "mode": "lazy",
  "dry_run": true,
  "state": "idle",
  "consecutive_rejects": 0
}
```

Si `enabled: false` ou `mode: "off"` → vérifier que `hailo.auto_reboot.mode` dans config.json est bien `"lazy"` et que le serveur a complètement redémarré.

#### C. Pas d'erreurs de démarrage dans `error.log` ?

```bash
tail -n 50 /home/pi/GitHub/yu_ai_manager/logs/error.log | grep -iE "hailo_auto_reboot|auto_reboot"
```

Aucune sortie signifie OK. En cas d'erreurs, voir « 8. Pièges connus » en fin de document.

---

## 2. Opérations quotidiennes pendant la période d'observation

### 2.1 Utilisation normale

**Action principale** :

- **Utiliser le chat LLM comme d'habitude** via `/ext/hailo-genai/chat` ou `/tools` (ex. Qwen3-1.7B)
- Utiliser VLM / S2T selon les besoins
- Les longues sessions (30+ minutes en continu) et les changements de modèle multiples valent également la peine d'être essayés intentionnellement pour élargir les données d'observation

Aucun test particulier n'est requis. **Plus l'utilisation est normale, plus la Phase 0.5 collecte de données** — c'est l'objectif de conception.

### 2.2 Revue hebdomadaire (une fois par semaine, ~5 minutes)

```bash
cd /home/pi/GitHub/yu_ai_manager

# Nombre d'occurrences de chaque type d'événement
jq -r '.event' logs/hailo_auto_reboot.log | sort | uniq -c

# Horodatages et CmaFree pour les événements would_fire
grep would_fire logs/hailo_auto_reboot.log | jq -r '[.ts, .cma_free_mb] | @tsv'

# Raison de drain_entered (cma ou rejects)
grep drain_entered logs/hailo_auto_reboot.log | jq -r '[.ts, .cma_free_mb, .consecutive_rejects, .reason] | @tsv' 2>/dev/null || \
  grep drain_entered logs/hailo_auto_reboot.log | head -10
```

**Points de contrôle** :

- `would_fire` apparaît 1 fois ou plus → le déploiement de la Phase 1 est justifié (vérifier si les horodatages enregistrés correspondent aux redémarrages manuels effectués)
- `prewarn_entered` se déclenche fréquemment mais ne progresse pas vers `drain_entered` → `prewarn_threshold_mb` (80 Mo) peut être trop bas ; recalibrer
- La raison de `drain_entered` est toujours `rejects` → le DRAIN est piloté par des rejets ; d'autres mesures que l'ajustement de seuil sont nécessaires

---

## 3. Fin d'observation et critères de décision pour la Phase 1

### 3.1 Période d'observation requise

**Minimum 7 jours / Recommandé 14 jours**. La période doit couvrir au moins les schémas suivants :

- Chat LLM normal
- Chat LLM long (30+ minutes en une seule session)
- Changement de modèles VLM / S2T
- Au moins un refus préalable de `acquire_genai` (CmaFree insuffisant)
- Premier chargement après un redémarrage du Pi

### 3.2 Critères numériques pour le déploiement de la Phase 1

Agrégation :

```bash
cd /home/pi/GitHub/yu_ai_manager
jq -r '.event' logs/hailo_auto_reboot.log | sort | uniq -c
```

Tableau de décision :

| Résultat d'observation | Décision Phase 1 |
|---|---|
| `would_fire` ≥ 1 | **GO** (l'automatisation du redémarrage a de la valeur) |
| `would_fire` = 0, `drain_entered` ≥ 1 | Réajuster les seuils et envisager la Phase 1 (DRAIN est atteint mais `would_fire` ne l'est pas — `fire_grace_seconds` pourrait être réduit) |
| Uniquement `prewarn_entered`, `drain_entered` = 0 | Le seuil actuel n'atteint jamais l'état « critique » → la Phase 1 peut ne pas être nécessaire selon les patterns d'utilisation |
| Tous les événements à 0 (uniquement `boot_baseline`) | L'utilisation n'épuise pas la CMA → Phase 1 non nécessaire |

### 3.3 Tâches post-observation

1. Sauvegarder les résultats agrégés dans `docs/fr/hailo/HAILO_AUTO_REBOOT_PHASE05_OBSERVATION_RESULTS.md` (nouveau fichier)
2. En cas de déploiement de la Phase 1 : passer à la Phase 1 dans la spécification rev3 §5.2 (bannière DRAIN dans l'UI + i18n) ; reconfirmer les seuils de §3.1 sur la base des données d'observation
3. Si la Phase 1 n'est pas nécessaire : définir `mode = "off"` dans config.json et archiver le journal d'observation

---

## 4. Procédure de désactivation (urgence / arrêt de l'observation)

```bash
cd /home/pi/GitHub/yu_ai_manager
jq '.hailo.auto_reboot.mode = "off"' config.json > config.json.tmp && mv config.json.tmp config.json
# Redémarrer le serveur
```

Même avec `mode = "off"`, les événements JSONL continuent d'être enregistrés (la sortie WARN vers `error.log` est supprimée). Pour désactiver complètement, utiliser la variable d'environnement :

```bash
TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE=1 uv run python web_ui.py ...
```

---

## 5. Référence des fichiers journaux (fichiers concernés)

| Fichier | Rôle |
|---|---|
| `logs/hailo_auto_reboot.log` | **Journal principal de cette fonctionnalité**. Format JSONL ; rotation à 10 Mo × 30 sauvegardes |
| `logs/hailo_cma.log` | Enregistreur d'événements CMA existant (depuis v4.214.10). Enregistre les événements de cycle de vie VDevice/modèle tels que `acquire_genai` |
| `logs/error.log` | Journal d'erreurs global de l'application. Quand `mode != "off"`, génère également des résumés WARN pour `drain_entered` / `would_fire` |

---

## 6. Emplacements du code associé (pour les investigations futures)

| Fonctionnalité | Fichier |
|---|---|
| Machine à états + RejectTracker | `core/hailo_device_core/auto_reboot.py` |
| JSONL writer | `core/hailo_device_core/auto_reboot_logger.py` |
| Point d'entrée de la boucle d'arrière-plan | `core/web/startup_background_hailo_judge.py` |
| Enregistrement des tâches en arrière-plan | `core/web/startup_background.py` (`hailo_auto_reboot_judge`) |
| Valeurs par défaut de la configuration | `core/configuration/defaults.py` (`hailo.auto_reboot`) |
| Hook acquire_genai | `core/hailo_device_core/device_manager_genai.py` |
| Extension `/api/system/cma` | `extensions/builtin_hailo_genai/hailo_genai_ext.py` |
| Tests unitaires | `tests/test_hailo_auto_reboot_judge.py`, `tests/test_hailo_auto_reboot_logger.py` |

---

## 7. Historique de révision (référence)

Cette implémentation a suivi le processus de révision complet d'AGENTS (voir le message du commit v4.215.1). Les fichiers de rapport individuels ont été écrits sous `.claude/agent-outputs/`, qui est dans `.gitignore` et n'est pas géré par git. Ils peuvent être régénérés si nécessaire.

---

## 8. Pièges connus

| Symptôme | Cause et remède |
|---|---|
| Rien n'apparaît dans `logs/hailo_auto_reboot.log` | Serveur non redémarré / `mode = "off"` encore défini / non démarré en mode `["full"]` / variable d'environnement `TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE` définie |
| `cma_free_mb: null` persiste | Fonctionne sur du matériel non Pi (ex. WSL2) ou échec de lecture de `/proc/meminfo` ; vérifier sur le matériel Pi réel |
| `hailo_runtime_version: null` | Le paquet `hailo_platform` n'est pas installé dans cet environnement ; sur un Pi 5 réel, la valeur est renseignée si HailoRT 5.3.0 est installé |
| `would_fire` n'apparaît jamais | La charge d'utilisation est trop légère ou les seuils sont trop larges ; essayer de longs chats continus / des changements de modèle et réobserver |
| Le mode `eager` est configuré mais ne fonctionne pas | En Phase 0.5, `eager` revient intentionnellement à `off` (avec un journal d'avertissement) ; prévu pour implémentation en Phase 1+ |

---

## 9. Retour arrière d'urgence

Dans le cas improbable où l'implémentation de la Phase 0.5 présenterait un problème (faible probabilité car aucun redémarrage réel n'est déclenché) :

```bash
cd /home/pi/GitHub/yu_ai_manager
# Revenir de v4.215.1 à v4.214.13 (spécification uniquement, avant l'implémentation)
git revert -m 1 69be148c6
git push
```

Ou **désactivation complète uniquement via la configuration** (recommandé) :

```bash
# Ajouter à l'environnement de démarrage et redémarrer le serveur
TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE=1 uv run python web_ui.py ...
```

---

## 10. Maintenance de ce document

- À la fin de l'observation, **ajouter le résumé de §3.3 à la fin de ce document** (nécessaire pour la décision Phase 1 dans les futures sessions de chat)
- Après le déploiement de la Phase 1, renommer ce document en `HAILO_AUTO_REBOOT_PHASE05_RUNBOOK_ARCHIVED.md` et créer un nouveau manuel pour la Phase 1
- Ce document réside dans `/home/pi/GitHub/yu_ai_manager/docs/fr/hailo/HAILO_AUTO_REBOOT_PHASE05_RUNBOOK.md` (géré par git)
