# Configuration de Hailo-10H

Guide de configuration côté hôte pour l'utilisation de Raspberry Pi 5 + Hailo AI Hat+ (Hailo-10H NPU) avec YU AI Manager. La partie relative au matériel et au système d'exploitation ne pouvant pas être réalisée via PyPI, quelques préparations manuelles sont nécessaires.

> **Public concerné** : Uniquement si vous souhaitez activer les extensions Hailo (GenAI Chat / Semantic Search / YOLO Detect / Tagger / Whisper) sur un Raspberry Pi 5 (8 Go recommandés) équipé du matériel Hailo-10H. Dans les environnements sans matériel Hailo, aucune des opérations de cette page n'est nécessaire.

---

## 1. Prérequis

- Raspberry Pi 5 (8 Go fortement recommandés ; avec 4 Go, le chargement simultané de plusieurs modèles est difficile en raison des contraintes CMA)
- Hailo AI Hat+ (Hailo-10H)
- Raspberry Pi OS Bookworm 64-bit (aarch64)
- Python 3.13.x (fixé à `<3.14` via `requires-python` dans `pyproject.toml` ; `uv` sélectionne automatiquement la version 3.13)

---

## 2. Installation du pilote PCIe

Hailo-10H utilise le module noyau dédié `hailo1x_pci` (renommé depuis l'ancien `hailo_pci` à partir de HailoRT 5.3.0).

```bash
sudo apt update
sudo apt install hailo-all
sudo reboot
```

Vérification après le redémarrage :

```bash
lsmod | grep hailo1x
ls /dev/h1x-0
dmesg | grep -i hailo | tail -20
```

Résultats attendus :

- `hailo1x_pci` est chargé
- Le nœud de périphérique `/dev/h1x-0` existe (et non l'ancien `/dev/hailo0`)
- `dmesg` contient les lignes `Firmware loaded in NNNN ms` et `Device created at /dev/h1x-0`

> **L'absence de `/dev/hailo0` n'est pas un problème.** À partir de HailoRT 5.3.0, `/dev/h1x-0` est la valeur par défaut, et cette application reconnaît les deux (`core/llm_router/hailo_detect.py`).

---

## 3. Installation de HailoRT (côté système)

Binaire `hailortcli` et bibliothèque partagée `libhailort.so`. Ils sont inclus dans le paquet `hailo-all`, mais si vous avez besoin de la dernière version, obtenez le `.deb` depuis la Hailo Developer Zone et installez-le par-dessus la version existante.

Vérification :

```bash
hailortcli fw-control identify
```

Sortie attendue (points essentiels) :

```
Device Architecture: HAILO10H
Firmware Version: 5.3.0 (release,app)
```

---

## 4. Préparation du wheel Python (`hailort-*.whl`)

C'est la partie qui n'est pas disponible sur PyPI. **Le wheel Python Hailo pour aarch64 n'est pas non plus disponible dans la Hailo Developer Zone, il doit donc être compilé manuellement.**

### 4.1 Compilation depuis le code source

```bash
cd ~
git clone --branch v5.3.0 https://github.com/hailo-ai/hailort.git
cd hailort
./build.sh -aarch64
# À la fin de la compilation, hailort-5.3.0-cp313-cp313-linux_aarch64.whl est généré dans l'arborescence de build
```

(Consultez le README officiel de Hailo pour les détails du processus de compilation et les dépendances.)

### 4.2 Placement du wheel dans le répertoire personnel

Copiez le wheel compilé dans **l'un des emplacements suivants** ; l'application le détectera automatiquement au démarrage :

| Chemin de recherche (priorité) | Utilisation |
|---|---|
| Variable d'environnement `$HAILORT_WHEEL` | Chemin complet arbitraire (priorité maximale) |
| `$HOME/share/` | **Emplacement recommandé** |
| `$HOME/hailort/` | Lorsque l'arborescence de build est conservée à l'emplacement source |
| `$HOME/Downloads/` | Emplacement temporaire après téléchargement |
| `$HOME/` (directement) | Dernier recours |

Procédure recommandée :

```bash
mkdir -p ~/share
cp ~/hailort/hailort-5.3.0-cp313-cp313-linux_aarch64.whl ~/share/
```

### 4.3 Mécanisme d'installation automatique

Lors de l'exécution de `./start.sh`, `scripts/install_hailo.py` est lancé :

1. Vérifie si `import hailo_platform` réussit dans le venv
2. En cas d'échec uniquement : recherche un wheel **correspondant à la version Python actuelle (cp313) + architecture (aarch64)** dans les emplacements de recherche ci-dessus
3. Installe le wheel le plus récent trouvé avec `uv pip install`
4. Si aucun wheel n'est trouvé ou s'il est déjà installé : aucune action (opération silencieuse)

Par conséquent, il n'est pas nécessaire d'exécuter `uv pip install` manuellement. Il suffit de placer le wheel dans le répertoire personnel et de redémarrer `./start.sh`.

---

## 4.4 Placement des fichiers de modèle HEF

Placez les fichiers HEF (modèles compilés pour NPU) utilisés par les extensions dans `~/hailo_models/`.

| Fichier | Utilisation | Taille approximative |
|---|---|---:|
| `yolov8n.hef` | Détection d'objets YOLO | 7 Mo |
| `clip_vit_b_16_image_encoder.hef` | **Semantic Search (image CLIP)** | 76 Mo |
| `clip_vit_b_16_text_encoder.hef` | Semantic Search (texte CLIP, optionnel) | 77 Mo |
| `Whisper-{Tiny,Base,Small}.hef` | Reconnaissance vocale | 75–405 Mo |
| `Qwen3-1.7B-Instruct.hef` | LLM Chat | 2,9 Go |
| `Qwen3-VL-2B-Instruct.hef` | VLM (image+texte) | 3,2 Go |

Téléchargement direct sans authentification depuis le bucket S3 de Hailo Model Zoo (format URL) :

```
https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef
```

Exemple (encodeur d'image CLIP) :

```bash
mkdir -p ~/hailo_models
curl -L -o ~/hailo_models/clip_vit_b_16_image_encoder.hef \
  https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_image_encoder.hef
```

> **Si les fichiers HEF manquent, l'extension s'affiche comme `Non disponible`.** Par exemple, si l'état de Semantic Search indique `hailo-10h (CLIP HEF non placé)`, cela signifie que `clip_vit_b_16_image_encoder.hef` n'est pas dans `~/hailo_models/`. Pour faciliter la distinction des problèmes matériels ou de runtime Python, la réponse inclut les causes en trois niveaux : `runtime_ok` / `hardware_ok` / `hef_ok` (survolez le texte d'état pour afficher les détails).

Vous pouvez également spécifier un autre répertoire avec la variable d'environnement `HAILO_HEF_DIR`.

---

## 5. Paramètres du noyau (CMA)

Les modèles GenAI de Hailo (LLM/VLM/Whisper) nécessitent CMA (Contiguous Memory Allocator) pour le DMA.

Ajoutez à la fin de `/boot/firmware/cmdline.txt` :

```
cma=256M
```

> **Sur Pi 5 (8 Go), `cma=1G` ou `cma=512M` échouent silencieusement.** Comme le noyau par défaut applique `numa=fake=8`, le CMA doit tenir dans la limite d'un seul nœud NUMA (1 Go), et au-delà de `256M`, `CmaTotal=0` (sans panique). Détails : [`docs/ja/hailo/PI5_NUMA_CMA_CONSTRAINTS.md`](../../hailo/PI5_NUMA_CMA_CONSTRAINTS.md)

Vérification après le redémarrage :

```bash
grep CmaTotal /proc/meminfo
# CmaTotal:         262144 kB  ← 256 Mo indique un succès
```

Si la valeur est `0 kB`, vérifiez la valeur et réduisez-la si nécessaire.

---

## 6. Coexistence avec hailo-ollama (optionnel)

Si vous exécutez `hailo-ollama` (la version Hailo NPU d'Ollama) sur le même appareil :

- **HailoRT 5.3.0 et ultérieur** : Démarrez avec `HAILO_OLLAMA_VDEVICE_GROUP_ID=YU_SHARED hailo-ollama` pour partager le périphérique physique avec le côté yu_ai_manager (group_id `YU_SHARED`) ; le planificateur HailoRT effectuera le time-slicing en ROUND_ROBIN
- **Avant 5.2.0** : group_id n'est pas accepté, il faut donc arrêter `hailo-ollama` avec `systemctl stop hailo-ollama` avant de démarrer yu_ai_manager

---

## 7. Vérification du fonctionnement

Après le démarrage de `./start.sh`, la configuration est réussie si les éléments suivants sont activés dans la WebUI sous **Paramètres → Extensions** :

- `builtin_hailo_genai` (Hailo Chat / LLM / VLM / Speech2Text)
- `builtin_hailo_semantic_search` (CLIP Semantic Search)
- `builtin_hailo_yolo_detect` (Détection d'objets YOLO)

Ou directement via la CLI :

```bash
uv run python -c "
from hailo_platform import VDevice
v = VDevice()
print('VDevice OK')
v.release()
"
```

---

## 8. Dépannage

### Toutes les extensions Hailo affichent « non chargé »

→ Le wheel Python n'est peut-être pas installé. Vérifiez :

```bash
uv run python -c "import hailo_platform; print(hailo_platform.__file__)"
```

En cas de `ModuleNotFoundError` : placez le wheel dans le répertoire personnel et redémarrez `./start.sh` (§4.2).

### `hailortcli fw-control identify` échoue avec `HAILO_OPEN_FILE_FAILURE`

→ Problème avec le pilote ou le nœud de périphérique. Vérifiez si `hailo1x_pci` est chargé dans `lsmod | grep hailo1x` et si `ls /dev/h1x-0` existe. Si les deux manquent, répétez §2 et redémarrez.

### `HAILO_OUT_OF_HOST_MEMORY` lors du chargement de LLM/VLM / Pi se fige

→ CMA insuffisant. Vérifiez avec `grep CmaTotal /proc/meminfo` si 256 Mo sont disponibles (§5). Comme `VDevice.release()` ne restitue pas le CMA, un redémarrage du processus peut être nécessaire après plusieurs changements de modèles.

### `HAILO_OUT_OF_PHYSICAL_DEVICES(74)`

→ Un autre processus occupe VDevice. Identifiez le responsable avec `lsof /dev/h1x-0` (typiquement `hailo-ollama` ou un processus précédent qui ne s'est pas terminé correctement avec Ctrl+C), exécutez `kill` et redémarrez.

### Python a été mis à jour vers 3.14 et est incompatible avec le wheel

→ Ce dépôt est fixé dans `pyproject.toml` avec `requires-python = ">=3.13,<3.14"`. Le premier `uv sync` après le clone sélectionne 3.13.x. Si `.python-version = 3.14` a été défini manuellement, revenez à la version précédente.

---

## 9. Documentation associée

- [`docs/ja/hailo/README.md`](../../hailo/README.md) — Table des matières de la documentation de développement Hailo-10H
- [`docs/ja/hailo/HAILORT_5_3_0_MIGRATION.md`](../../hailo/HAILORT_5_3_0_MIGRATION.md) — Notes de migration HailoRT 5.2.0 → 5.3.0
- [`docs/ja/hailo/PI5_NUMA_CMA_CONSTRAINTS.md`](../../hailo/PI5_NUMA_CMA_CONSTRAINTS.md) — Détails des contraintes CMA du Pi 5
- [`scripts/install_hailo.py`](../../../../scripts/install_hailo.py) — Script de détection automatique du wheel
