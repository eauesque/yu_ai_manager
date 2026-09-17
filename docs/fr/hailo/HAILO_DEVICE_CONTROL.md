# Contrôle du périphérique Hailo-10H

## Vue d'ensemble

Le NPU Hailo-10H peut **exécuter plusieurs modèles simultanément**.
Le planificateur ROUND_ROBIN intégré partage automatiquement l'accès matériel entre les modèles en time-slicing.

Dans yu_ai_manager, un seul VDevice partagé est maintenu, et CLIP, YOLO, LLM, VLM et Speech2Text peuvent être chargés et inférer simultanément. Le partage avec des processus externes (hailo-ollama) est géré avec `group_id`.

## Architecture

```
┌─────────────────────────────────────────────┐
│              Shared VDevice                  │
│         (group_id = YU_SHARED)               │
│                                              │
│  ┌─────────┐ ┌─────────┐ ┌───────────────┐  │
│  │  CLIP   │ │  YOLO   │ │  LLM (GenAI)  │  │
│  │InferMdl │ │InferMdl │ │  VLM / S2T    │  │
│  └─────────┘ └─────────┘ └───────────────┘  │
│                                              │
│     HailoRT ROUND_ROBIN Scheduler            │
└─────────────────────────────────────────────┘
```

- L'API InferModel (CLIP, YOLO) et l'API GenAI (LLM, VLM, S2T) coexistent sur le même VDevice
- Tous les modèles doivent être créés sur la **même instance VDevice** (ne fonctionne pas avec des instances séparées)

## Comparaison des 2 modes

| | Python SDK (Hailo VLM) | hailo-ollama-vlm (compatible OpenAI) |
|---|---|---|
| Gestion du périphérique | device_manager de yu | Serveur C++ externe |
| Coexistence avec recherche CLIP | Oui (fonctionnement simultané) | Oui (partage group_id, v5.3.0+) |
| Vitesse d'inférence | Identique | Identique |
| Surcharge | ~15ms | ~200-400ms (base64+HTTP) |
| Clients multiples | Non | Oui |
| Thread Flask | Bloqué pendant l'inférence | Attente HTTP uniquement |

## Partage VDevice (group_id)

### Partage intra-processus

Géré automatiquement par `device_manager.py`. Tous les modèles partagent le même VDevice.

Le group_id peut être modifié via une variable d'environnement :
```bash
export HAILO_VDEVICE_GROUP_ID=MY_GROUP
```

Par défaut : `YU_SHARED`

### Coexistence avec hailo-ollama (v5.3.0+)

hailo-ollama v5.3.0 et ultérieur supporte la variable d'environnement `HAILO_OLLAMA_VDEVICE_GROUP_ID`.
En définissant le même group_id que yu_ai_manager, les deux processus peuvent partager le périphérique :

```bash
# Côté yu_ai_manager
export HAILO_VDEVICE_GROUP_ID=SHARED

# Côté hailo-ollama
HAILO_OLLAMA_VDEVICE_GROUP_ID=SHARED hailo-ollama
```

**Note** : group_id fonctionne dans yu_ai_manager avec HailoRT 5.2.0 et ultérieur.
hailo-ollama n'accepte group_id qu'avec v5.3.0 et ultérieur.

## API device_manager

### Obtention d'un modèle

```python
from core.hailo_device_core.device_manager import acquire_device, acquire_genai

# InferModel (CLIP, YOLO)
infer_model, configured, quant_params = acquire_device("clip", "/path/to.hef")

# GenAI (LLM, VLM, S2T)
llm = acquire_genai("llm", "/path/to.hef", lambda vd, p: LLM(vd, p))
```

- Même propriétaire + même HEF → réutilisation de la session existante
- Même propriétaire + HEF différent → libération de l'ancien modèle et création du nouveau
- Propriétaire différent → **coexistence** (l'ancien modèle n'est pas libéré)

### Libération d'un modèle

```python
from core.hailo_device_core.device_manager import release_device, shutdown_all

release_device("clip")   # Libération de CLIP uniquement, les autres continuent
shutdown_all()            # Libération de tous les modèles + VDevice (à la fin du processus)
```

### Vérification de l'état

```python
from core.hailo_device_core.device_manager import (
    get_active_owners, is_model_active,
    is_hailo_available, is_genai_available,
)

get_active_owners()       # ["clip", "yolo", "llm"]
is_model_active("clip")   # True
```

## Dépannage

### Erreur de création VDevice

**Symptôme** : `HAILO_OUT_OF_PHYSICAL_DEVICES(74)` ou `Failed to create VDevice`

**Cause** : Un autre processus occupe le périphérique avec un group_id différent

**Solution** :
1. Vérifier si hailo-ollama est en cours d'exécution :
   ```bash
   ps aux | grep hailo-ollama
   ```
2. Aligner les group_id ou l'arrêter :
   ```bash
   sudo systemctl stop hailo-ollama
   ```

### Le périphérique n'est pas libéré

**Solution** :
1. Redémarrer le processus yu
2. Vérifier les processus zombies :
   ```bash
   sudo lsof /dev/hailo* 2>/dev/null
   kill <PID>
   ```
3. Réinitialiser le driver Hailo :
   ```bash
   sudo systemctl restart hailort.service
   ```

## Guide d'utilisation des API

| Structure du modèle | API recommandée | Raison |
|---|---|---|
| Simple (1 entrée, YOLO, etc.) | `InferModel` | Fonctionne avec `create_infer_model()` + `configure()` |
| Complexe (2+ entrées, Whisper, etc.) | `GenAI SDK` | InferModel retourne `INVALID_ARGUMENT` |
| Encodeur CLIP | `InferModel` | Pas de problème avec 1 entrée 1 sortie |
| LLM (qwen2.5, etc.) | `GenAI SDK` | Nécessite un décodage autorégressif |

## Historique

- **v4.61.0** : Migration vers la méthode VDevice partagé. Abandon de l'acquire/release exclusif, support du fonctionnement simultané CLIP + YOLO + LLM.
- **v4.60.1** : Unification de tous les consommateurs via device_manager (méthode exclusive).
- **Avant v4.60.0** : Chaque consommateur appelait VDevice() individuellement, provoquant fréquemment des erreurs de conflit.
