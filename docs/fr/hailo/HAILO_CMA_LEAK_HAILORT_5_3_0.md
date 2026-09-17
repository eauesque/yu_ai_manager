# Fuite CMA dans HailoRT 5.3.0 — Diagnostic confirmé et contraintes opérationnelles

> **Note de correction** : ce document consigne un diagnostic de fuite CMA fondé sur une ancienne mesure. Les anciennes conclusions selon lesquelles la CMA n'est pas récupérée après `release()`, qu'elle fuit en continu pendant l'inférence à environ 14 Mo/min, et que seul un redémarrage complet du Pi permettrait une récupération fiable, sont retirées. Le jugement final, issu du nouvel essai sur HailoRT/driver 5.4.0, a été corrigé au §8 de [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md). Ne pas se référer aux anciennes conclusions de ce document comme jugement opérationnel actuel.

**Créé** : 2026-05-17 (découvert et consigné dans la v4.214.11)
**Portée concernée** : Raspberry Pi 5 + Hailo-10H + `hailort==5.3.0` (chemin `hailo_platform.genai`)
**Symptôme** : Une fois un LLM chargé, la CMA n'est pratiquement pas récupérée même après l'appel à `VDevice.release()` / `LLM.release()`. De plus, la CMA continue de fuir continuellement pendant l'inférence. Aucun moyen de récupération n'existe en dehors d'un redémarrage du Pi.
**Statut** : Confirmé comme contrainte structurelle côté pilote. Des solutions de contournement sont à l'étude.

---

## 1. Fondement du diagnostic confirmé

À l'aide de l'enregistreur d'événements CMA introduit dans la `v4.214.10` (`logs/hailo_cma.log`, `core/hailo_device_core/device_helpers.py::log_hailo_cma_event`), la séquence suivante a été mesurée le 2026-05-17.

### 1-1. Journal d'observation (brut)

`logs/hailo_cma.log` :

```text
2026-05-17T14:05:13+0900 event=vdevice_create_pre  cma_free_mb=392 pid=3237
2026-05-17T14:05:14+0900 event=vdevice_create_post cma_free_mb=393 pid=3237
2026-05-17T14:05:14+0900 event=acquire_pre  cma_free_mb=393 pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
2026-05-17T14:06:25+0900 event=acquire_post cma_free_mb=108 pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
        ↓ 6 minutes d'utilisation en chat (environ 5 à 10 messages d'inférence)
2026-05-17T14:12:36+0900 event=release_pre  cma_free_mb=24  pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
2026-05-17T14:12:36+0900 event=release_post cma_free_mb=25  pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
```

### 1-2. Interprétation

| Phase | Différence CmaFree | Signification |
|---|---|---|
| `vdevice_create_pre` → `vdevice_create_post` | **+1 Mo (≈ 0)** | La création de VDevice elle-même consomme à peine de CMA |
| `acquire_pre` → `acquire_post` (chargement de Qwen3-1.7B-Instruct) | **−285 Mo** | 1 LLM consomme 285 Mo |
| `acquire_post` → `release_pre` (6 minutes d'inférence) | **−84 Mo / 6 min ≒ −14 Mo/min** | **Fuite continue pendant l'inférence également** |
| `release_pre` → `release_post` (déchargement du LLM) | **+1 Mo** | **`release()` ne rend effectivement pas de CMA** |

### 1-3. Comparaison avec l'hypothèse précédente

Ceci est un résultat de mesure qui contredit partiellement l'hypothèse initiale du §7 de `SQLCIPHER_MMAP_CORRUPTION.md` créé le 2026-05-16 et l'hypothèse de l'ancien document selon laquelle « la stratégie de rétention du VDevice (notre `_maybe_reset_vdevice` vide) amplifie la fuite ». Puisque la création du VDevice = 0 Mo / release = 0 Mo, **changer la stratégie de rétention (= changer `_maybe_reset_vdevice` pour qu'il se réinitialise à chaque fois) n'aurait aucun effet**.

---

## 2. Contraintes structurelles

D'après les résultats mesurés, HailoRT 5.3.0 (build communautaire, API `hailo_platform.genai`) présente trois problèmes coexistants :

1. **`VDevice.release()` / `release()` du modèle GenAI ne récupère pas la CMA de l'hôte** (confirmé par mesure)
   - Au sein d'un processus unique, le pilote PCIe (`hailo1x_pci`) continue de conserver les régions DMA, et aucune opération équivalente à `munmap` ne se produit
2. **Fuite CMA continue pendant l'inférence (~14 Mo/min)** (confirmé par mesure)
   - Observation d'aujourd'hui : 84 Mo perdus en 6 minutes d'utilisation de Qwen3-1.7B-Instruct
   - Un chemin séparé indépendant du chargement/déchargement. L'épuisement survient même sans déchargement
3. **Aucune méthode confirmée autre qu'un redémarrage du Pi pour récupérer la CMA de manière fiable** (mesure + rapports de la communauté)
   - Même le redémarrage du processus serveur (équivalent à `systemctl restart yu-ai-manager`) est incomplet car `hailo1x_pci` conserve le DMA jusqu'au cycle d'alimentation PCIe. Une récupération complète nécessite `sudo reboot` du Pi (mesuré dans ce dépôt)
   - Plusieurs rapports indépendants existent dans la communauté Hailo : <https://community.hailo.ai/t/hailo-10h-on-rpi5-undocumented-api-findings-dfc-conversion-failures-with-transformer-based-models-swinv2-vit-convnext/18979> et <https://community.hailo.ai/t/hailo-10h-throughput-degrades-irreversibly-within-minutes-of-continuous-use-125-41-fps-only-host-reboot-recovers/19218> (indique explicitement que `VDevice.release()` / sortie de processus / rechargement du pilote ne récupère pas, seul le redémarrage de l'hôte le fait)
   - Ceci est déjà documenté pour les utilisateurs dans le message d'erreur de rejet préalable de `acquire_genai` (`core/hailo_device_core/device_manager_genai.py::acquire_genai`, "a full system reboot is required")

### 2-1. « Tuer un processus enfant rend-il la CMA ? » : **Réfuté par mesure** (2026-05-17 Phase 0 PoC)

La version précédente (rev1) concluait théoriquement que « le noyau Linux récupère les pages DMA lors du teardown de `mm_struct`, de sorte que tuer un processus enfant récupère complètement la CMA », mais **la mesure avec Phase 0 PoC (`tools/diag_hailo_cma_reclaim.py`) a confirmé indépendamment deux fois que tuer un processus enfant récupère à peine la CMA**.

**Résultats de mesure (2e passage, version stricte)** :

| Point de mesure | CmaFree | Δ |
|---|---:|---:|
| Ligne de base (avant le démarrage du PoC) | 503 Mo | — |
| Après création de VDevice | 372 Mo | **-131 Mo** (la construction de VDevice consomme de la CMA dans le processus enfant à démarrage à froid) |
| Après chargement du LLM | 372 Mo | 0 Mo (le LLM est contenu dans le pool DMA de VDevice, pas de nouvelle consommation) |
| Après SIGTERM + join | 378 Mo | +6 Mo |
| **Après 30 secondes d'attente** | **380 Mo** | **Seulement +8 Mo récupérés au total** |

Face à une récupération attendue de ≥250 Mo, la valeur mesurée n'était que de +8 Mo (+1 Mo lors de la première mesure accidentelle). Cela est au niveau du jitter système — **aucune récupération significative de CMA ne s'est produite**.

**Diagnostic confirmé** :

- Le pilote `hailo1x_pci` gère le pool DMA dans l'**état global interne du pilote** et non dans le `mm_struct` du processus utilisateur (estimé)
- Pas de récupération par `process exit`, `kill` ou `module unload` (cohérent avec les rapports de la communauté)
- **La seule méthode de récupération confirmée est `sudo reboot` du Pi (= cycle d'alimentation PCIe)** ← c'est le fait mesuré indiqué dans §2 ligne 3

Rapport détaillé : `docs/superpowers/specs/codex-reviews/2026-05-17-hailo-subprocess-isolation-phase0-poc-result.md`

Suite à ces résultats, `docs/superpowers/specs/2026-05-17-hailo-subprocess-isolation-design.md` est marqué **REJECTED**, et l'approche d'atténuation par isolation de subprocess est abandonnée. L'approche de redémarrage automatique du §4 (D) est adoptée comme alternative.

---

## 3. Implications opérationnelles

### 3-1. « 1 modèle par redémarrage du Pi » est effectivement la limite

- Avec Pi 5 (limite CMA 512 Mo, ne peut pas être augmentée selon les spécifications du Pi) + LLM Qwen3 (285 Mo) :
    - CmaFree immédiatement après le redémarrage ≒ 480 Mo
    - Après chargement de 1 LLM → CmaFree ≒ 190 Mo
    - Après quelques dizaines de minutes d'inférence → CmaFree ≒ 50 Mo ou moins
    - **Charger un deuxième modèle est définitivement impossible** (nécessite 250+ Mo mais le reste est insuffisant, et release ne le rend pas)

### 3-2. L'utilisation simultanée de LLM + VLM / LLM + S2T n'est pas possible

- Les cas d'utilisation qui alternent entre VLM (basé sur llava, ~300 Mo), S2T (whisper-small, ~175 Mo) et LLM sont impossibles en raison des contraintes ci-dessus, à moins de suivre la procédure **charger → redémarrer → charger**.
- **L'UX multimodèle telle que « joindre une image pendant la conversation pour passer à un autre modèle » ou « transcrire l'audio de conversation » n'est structurellement pas réalisable avec HailoRT 5.3.0**.

### 3-3. Les longues sessions d'inférence continue sont difficiles

- La fuite de 14 Mo/min signifie que même en partant de 200 Mo de CmaFree, la moitié est perdue en 14 minutes et presque tout est épuisé en 30 minutes.
- Les sessions de chat dépassant 30 minutes ne peuvent pas être stabilisées sans un redémarrage du Pi entre les deux.

---

## 4. Contre-mesures possibles

Listées avec priorité et effort :

| Option | Effet | Effort | Effets secondaires / Risques |
|---|---|---|---|
| ~~(A) Isoler les opérations Hailo dans un subprocess et tuer périodiquement pour que le noyau récupère la CMA~~ | ❌ **REJECTED** (réfuté par Phase 0 PoC, reproduit deux fois). La récupération après kill n'était que de +8 Mo au total — hypothèse invalidée | — | Non retenu |
| **(B) Mettre à jour `_CMA_ESTIMATES_MB` avec des valeurs mesurées + marge** | Améliore la précision du rejet préalable (réduit les tentatives de chargement faux positifs) | ✅ Applicable immédiatement, 1 ligne | Les cas qui fonctionnaient à peine avec une hypothèse de 250 Mo seront rejetés, mais ils échouaient déjà |
| **(C) Bannière UI quand `CmaFree < 80 Mo` / WARN dans error.log quand `< 30 Mo`** | Les utilisateurs peuvent comprendre la situation et sont invités à redémarrer le Pi | Moyen | Risque de fatigue des avertissements / notifications excessives |
| **(D) Détecter `CmaFree < 30 Mo` et envoyer SIGTERM au superviseur** | Récupération automatique (bien qu'un redémarrage complet du Pi soit nécessaire, via `systemctl reboot`) | Moyen | Nécessite des permissions superviseur / interruption de session pendant d'autres travaux |
| **(E) Attendre la correction de HailoRT + documenter clairement les contraintes** | Coût 0 | 0 | Dépend du cycle de publication de Hailo (plusieurs mois+) |
| **(F) Soumettre une demande de correction au bug tracker / forum de Hailo** | Accélère potentiellement le calendrier de correction | Petit | La vitesse de réponse dépend du contrat de support et de l'état de la communauté |

Politique à court terme (mise en œuvre dans v4.214.11) : **Appliquer (B) + ce document (point de départ pour E et F)**.
Politique à moyen terme (spec séparée) : Envisager dans l'ordre de **(C) avertissement UI → (A) isolation de subprocess**.
Long terme : Surveiller les versions de HailoRT et mettre à jour ce document pour supprimer les contraintes lors de la correction.

---

## 5. Documents / Code connexes

- `core/hailo_device_core/device_manager_genai.py::acquire_genai` — La vérification préalable de CmaFree + le message d'erreur destiné à l'utilisateur expose explicitement cette contrainte
- `core/hailo_device_core/device_helpers.py::_CMA_ESTIMATES_MB` — Estimations des besoins en CMA par modèle (qwen augmenté de 250 → 300 dans v4.214.11)
- `core/hailo_device_core/device_helpers.py::log_hailu_cma_event` — Instrumentation de mesure introduite dans v4.214.10. Les données de mesure dans ce document en proviennent
- `core/hailo_device_core/device_manager_state.py::_maybe_reset_vdevice` — Conception qui conserve VDevice pendant la durée de vie du processus (fonction vide). Cette mesure confirme que le modifier pour le réinitialiser ne contribuerait pas à la récupération de CMA
- `docs/ja/hailo/HAILO_AUTO_REBOOT_PHASE05.md` — Guide de l'opérateur pour la phase d'observation 0.5. Procédure pour collecter uniquement les journaux `would_fire` avec `mode=lazy` + `dry_run=true`
- `docs/ja/hailo/PI5_NUMA_CMA_CONSTRAINTS.md` — Limite totale de CMA du Pi5 et consommation de base de chaque pilote (camera / KMS / Hailo / HEVC)
- `docs/ja/hailo/HAILORT_5_3_0_MIGRATION.md` — Contexte de la migration vers HailoRT 5.3.0 et différences connues

---

## 6. Étapes de reproduction (pour les rapports de problèmes Hailo)

Étapes de reproduction minimales pour les rapports de bugs externes :

```bash
# 1. Confirmer la ligne de base immédiatement après le redémarrage du Pi
grep CmaFree /proc/meminfo
# CmaFree: ~480000 kB

# 2. Démarrer le serveur + charger le 1er LLM (p.ex., envoyer 1 message via GenAI dans /tools)
# 1 requête vers /api/llm/generate ou /api/chat/send

# 3. Vérifier CmaFree
grep CmaFree /proc/meminfo
# CmaFree: ~100 Mo (-280 Mo)

# 4. Décharger le modèle
curl -X POST http://127.0.0.1:5000/ext/hailo-genai/api/model/unload -d '{"model":"llm"}'

# 5. Vérifier CmaFree
grep CmaFree /proc/meminfo
# CmaFree: ~100 Mo (non retourné ← bug)

# 6. Tentative de rechargement du même / d'un autre modèle → rejeté pour CMA insuffisante
```

Comportement attendu : À l'étape 5, CmaFree devrait revenir à une valeur proche de la ligne de base de l'étape 1 (>400 Mo).
Comportement réel : Seulement environ +1 Mo rendu, rechargement impossible.
