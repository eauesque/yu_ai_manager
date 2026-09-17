# Notes de migration HailoRT 5.2.0 → 5.3.0

Connaissances acquises lors de la mise à niveau de HailoRT 5.2.0 vers 5.3.0 sur Raspberry Pi 5 + AI HAT 2 (Hailo-10H). Basé sur des tests d'implémentation bout en bout et une analyse directe par git diff des tags officiels `v5.2.0` / `v5.3.0`.

**Public cible** : Développeurs exécutant des inférences sur Hailo-10H NPU avec Python (`pyhailort`).

---

## TL;DR

- **Pratiquement zéro rupture de compatibilité dans les applications Python d'inférence typiques**.
  Les chiffres (688 fichiers modifiés, +12 035 / -8 987 lignes) sont importants, mais les surfaces de `VDevice`, `InferModel`, GenAI (`LLM` / `VLM` / `Speech2Text`) sont entièrement rétrocompatibles.
- La majorité des modifications sont la **suppression des API de caméra / ISP / gestion du firmware Hailo-8** et un refactoring interne. Aucun impact sur l'inférence NPU pure.
- **Les fichiers `.hef` téléchargés sous v5.2.0 se chargent sans modification sous le runtime 5.3.0.** Vérifié sur 5 modèles (YOLOv8n, CLIP ViT-B/16, Qwen2.5-1.5B, Qwen2-VL-2B, Whisper-Base).
- Le driver Linux est passé de `hailo_pci` à `hailo1x_pci`, et le nœud de périphérique de `/dev/hailort0` à **`/dev/h1x-0`**. `pyhailort` résout le nouveau nœud en interne, donc le code Python utilisant `VDevice()` **n'a pas besoin d'être modifié**. **Seul le passage de périphérique Docker nécessite une mise à jour.**
- `Speech2Text.SegmentInfo` expose les attributs `text` / `start_sec` / `end_sec` (identique à v5.2.0). `start` et `start_time` ne sont pas exposés, et le code défensif utilisant ces noms retourne silencieusement 0.0.

---

## 1. Étendue des modifications

Diff direct des tags `v5.2.0` et `v5.3.0` du dépôt HailoRT GitHub officiel :

| Étendue | Fichiers | Ajouts | Suppressions |
|---|---:|---:|---:|
| Total | 688 | +12 035 | -8 987 |
| En-têtes C++ publics (`include/hailo/`) | 27 | +205 | **-383** |
| Bindings Python (`bindings/python/`) | 35 | +306 | **-413** |
| `pyhailort.py` uniquement | 1 | +98 | **-158** |

**Les suppressions dépassent les ajouts.** C'est une version de « simplification ».
La majorité des suppressions ne concerne pas les chemins d'inférence NPU.

---

## 2. API supprimées — Caméra / ISP / Firmware Hailo-8 uniquement

`hailort/libhailort/include/hailo/device.hpp` a perdu 169 lignes et `platform.h` en a perdu 75. Tout ce qui a été supprimé concerne le contrôle de périphérique bas niveau :

- `firmware_update()` / `second_stage_update()` (mise à jour du firmware)
- `store_sensor_config()` / `store_isp_config()`
- `sensor_dump_config()` / `sensor_reset()`
- `sensor_load_and_start_config()`
- `sensor_set_i2c_bus_index()` / `sensor_set_generic_i2c_slave()`
- `sensor_get_sections_info()`
- `examine_user_config()` / `read_user_config()` / `write_user_config()` / `erase_user_config()`

Ce sont toutes des API pour les **modules caméra AI Hailo-8** (cartes SoC où le chip Hailo contrôle directement l'ISP et le capteur d'images).
Non appelées dans le flux `VDevice` → `InferModel` → `generate` typique sur Hailo-10H NPU nu.

**Impact** : Zéro pour les applications d'inférence NPU pure. Seules les applications contrôlant réellement des modules caméra Hailo-8 doivent auditer leur utilisation.

---

## 3. Changements de signatures Python

| API | v5.2.0 | v5.3.0 | Compatibilité |
|---|---|---|---|
| `Speech2Text.generate_all_segments(timeout_ms=)` | Défaut `10000` | Défaut `600000` | ✅ Défaut seulement, appels existants inchangés |
| `Speech2Text.generate_all_text(timeout_ms=)` | Identique | Identique | ✅ Identique |
| `LLM.read_all(timeout_ms=10000)` | Avec défaut | Défaut **supprimé** (obligatoire) | ⚠️ `read_all()` sans argument → `TypeError` |
| `DeviceArchitecture.__init__` | 9 arguments positionnels | +`chip_serial_number` (10) | ⚠️ Construction directe cassée |

**La correction de `read_all()` est un changement d'une ligne** :

```python
# Avant (style v5.2.0, défaut 10 secondes)
text = generator.read_all()

# Après (v5.3.0 nécessite un timeout explicite)
text = generator.read_all(timeout_ms=600000)  # 10 minutes
```

`DeviceArchitecture` est rarement construit directement dans le code utilisateur, donc son changement de signature a peu d'impact.

---

## 4. Changements de noms d'en-têtes C++ (transparents via Python)

Cassant pour les applications utilisant HailoRT directement en C++ :

- **`Speech2Text::DEFAULT_OPERATION_TIMEOUT`** (10 sec) → **`DEFAULT_GENERATE_ALL_TIMEOUT`** (10 min), renommé et prolongé
- **`LLM::DEFAULT_READ_ALL_TIMEOUT`** ajouté, également 10 min
- 4 surcharges de `generate_from_embeddings()` ajoutées à `vlm.hpp`

Ces changements de noms ne se propagent pas via les bindings Python.

---

## 5. Correction des coordonnées des boîtes englobantes NMS (changement de comportement)

Correction de la logique de post-traitement NMS dans `pyhailort.py` :

```python
# v5.2.0
y_min = numpy.ceil(bbox[0] * image_height)
x_min = numpy.ceil(bbox[1] * image_width)
bbox_width = numpy.ceil((bbox[3] - bbox[1]) * image_width)

# v5.3.0
y_min = int(max(numpy.floor(bbox[0] * image_height), 0))
x_min = int(max(numpy.floor(bbox[1] * image_width), 0))
x_max = int(min(numpy.ceil(bbox[3] * image_width), image_width))
bbox_width = x_max - x_min
```

Améliorations :
- Ajout du clipping aux limites d'image `max(0, …)` / `min(image_width, …)`
- `ceil` → `floor` (prévention du dépassement)
- Recalcul de `bbox_width` depuis `x_max - x_min` clippé

**Différence de comportement** : Sur le même modèle avec la même image, la sortie NMS peut décaler de ±1 pixel près des bords. Les applications écrivant leur propre post-traitement NMS ne sont pas affectées.

---

## 6. Nouvelles API (additives)

- **`VDevice::create_session(uint16_t port)`** — API de session d'inférence réseau (nouvelle fonctionnalité)
- **`VLM::generate_from_embeddings()`** — 4 surcharges. Accepte des embeddings d'images/vidéos précalculés comme entrée `MemoryView`. Permet de calculer les embeddings une fois et de les réutiliser pour plusieurs appels VLM.
- **`InferModel::set_nms_classes_filter_mask(vector<bool>)`** — Filtrage par classe pour la sortie NMS (sur chip)
- **`Device::query_performance_stats(sampling_period_ms)`** — Période d'échantillonnage configurable
- **`Device::get_current_limit()`** — Interroger la limite de courant
- **`DeviceArchitecture.chip_serial_number`** — Lire le numéro de série du chip

Tous sont additifs, donc le code existant n'est pas cassé.

---

## 7. Changements d'environnement

### 7.1 Nouveau driver Linux PCI

| Élément | Ancien | Nouveau |
|---|---|---|
| Module kernel | `hailo_pci` | `hailo1x_pci` |
| Nœud de périphérique | `/dev/hailort0` (ou `/dev/hailo0`) | `/dev/h1x-0` |

```bash
lsmod | grep hailo        # → hailo1x_pci
ls /dev/h1x-*             # → /dev/h1x-0
```

**`pyhailort` résout le nouveau nœud en interne**, donc le code Python utilisant `VDevice()` continue de fonctionner sans modification.
Seul le code ouvrant directement `/dev/hailo*` ou `/dev/hailort0` a besoin d'une mise à jour.

#### Passage Docker / Podman

Mettez à jour la déclaration de passage de périphérique :

```yaml
# docker-compose.yml
services:
  my-app:
    devices:
      - /dev/h1x-0:/dev/h1x-0   # était: /dev/hailort0:/dev/hailort0
```

Mettez également à jour les lignes `DeviceAllow=` de l'unité systemd et les règles udev.

### 7.2 Assouplissement des contraintes numpy

- v5.2.0 `setup.py` : `numpy<2` (fixe)
- v5.3.0 `setup.py` : `numpy` (sans limite supérieure)

Les applications précédemment fixées sur numpy 1.x peuvent maintenant passer à numpy 2.x avec la mise à niveau HailoRT.

### 7.3 Compatibilité binaire HEF

**Les fichiers `.hef` téléchargés sous v5.2.0 se chargent et s'exécutent sans modification sous le runtime 5.3.0.**
Vérifié sur 5 modèles (Raspberry Pi 5 + AI HAT 2) :

| Modèle | Fichier | Résultat |
|---|---|---|
| YOLOv8n | `yolov8n.hef` | ✅ `create_infer_model()` + `.run()` |
| Encodeur d'image CLIP ViT-B/16 | `clip_vit_b_16_image_encoder.hef` | ✅ Sortie 512 dimensions |
| Qwen2.5-1.5B Instruct | `Qwen2.5-1.5B-Instruct.hef` | ✅ `LLM.generate_all()` retourne du texte valide |
| Qwen2-VL-2B Instruct | `Qwen2-VL-2B-Instruct.hef` | ✅ `VLM.generate_all(frames=[…])` retourne du texte valide |
| Whisper-Base | `Whisper-Base.hef` | ✅ `Speech2Text.generate_all_segments()` retourne `SegmentInfo` |

### 7.4 Bucket d'URL de téléchargement HEF

La Hailo Developer Zone (`dev-public.hailo.ai`) héberge les buckets v5.2.0 et v5.3.0 en parallèle :

```
https://dev-public.hailo.ai/v5.2.0/blob/<model>.hef
https://dev-public.hailo.ai/v5.3.0/blob/<model>.hef
```

État du bucket v5.3.0 au 2026-04-06 :

| Modèle | Bucket v5.3.0 |
|---|---|
| Qwen2.5-1.5B-Instruct | ✅ 200 |
| DeepSeek-R1-Distill-Qwen-1.5B | ✅ 200 |
| Qwen2.5-Coder-1.5B-Instruct | ✅ 200 |
| Qwen2-VL-2B-Instruct | ✅ 200 |
| Whisper-Base / Whisper-Small | ✅ 200 |
| **Llama-3.2-1B-Instruct** | ❌ **404** |

→ Les applications nécessitant Llama-3.2-1B doivent pour l'instant continuer à récupérer depuis le bucket v5.2.0. Les HEF v5.2.0 se chargent correctement sous le runtime 5.3.0.

---

## 8. Noms des attributs `Speech2Text.SegmentInfo`

Dans v5.2.0 et v5.3.0, `Speech2Text.generate_all_segments()` retourne des objets `SegmentInfo` avec ces attributs publics :

```python
seg.text        # str
seg.start_sec   # float (secondes)
seg.end_sec     # float (secondes)
```

**`seg.start` et `seg.start_time` n'existent pas.** L'ancienne documentation et les exemples de code peuvent référencer ces noms, mais ils lèveront `AttributeError` ou retourneront silencieusement 0.0 si enveloppés dans du code défensif.

Pour vérifier les vrais noms d'attributs à l'exécution :

```python
from hailo_platform import VDevice
from hailo_platform.genai import Speech2Text, Speech2TextTask
import numpy as np

vd = VDevice()
s2t = Speech2Text(vd, "/path/to/Whisper-Base.hef")
audio = (np.random.default_rng(0).standard_normal(32000) * 0.01).astype("<f4")
segments = s2t.generate_all_segments(
    audio_data=audio, task=Speech2TextTask.TRANSCRIBE,
    language="en", timeout_ms=30000,
)
if segments:
    print([a for a in dir(segments[0]) if not a.startswith("_")])
    # => ['end_sec', 'start_sec', 'text']
```

---

## 9. Script de test de fumée

Script minimal pour vérifier que l'environnement fonctionne réellement après la mise à niveau vers 5.3.0 :

```python
"""Test de fumée HailoRT 5.3.0 — VDevice / InferModel / LLM / Speech2Text."""
import numpy as np
from hailo_platform import VDevice

# 1. Créer VDevice
params = VDevice.create_params()
params.group_id = "SMOKE_TEST"
vd = VDevice(params)
print("1. VDevice OK")

# 2. Chemin InferModel (YOLOv8n ou tout HEF existant)
im = vd.create_infer_model("/path/to/yolov8n.hef")
conf = im.configure()
inp = im.inputs[0]
bindings = conf.create_bindings()
bindings.input().set_buffer(np.zeros(tuple(inp.shape), dtype=np.uint8))
for o in im.outputs:
    fmt = str(getattr(o.format, "type", "")).lower()
    dtype = np.float32 if "float" in fmt else np.uint8
    bindings.output(o.name).set_buffer(np.zeros(tuple(o.shape), dtype=dtype))
conf.run([bindings], timeout=10000)
print("2. InferModel (YOLO) OK")
del conf, im

vd.release()
del vd

# 3. Chemin GenAI LLM
from hailo_platform.genai import LLM
params = VDevice.create_params(); params.group_id = "SMOKE_TEST"
vd = VDevice(params)
llm = LLM(vd, "/path/to/Qwen2.5-1.5B-Instruct.hef")
text = llm.generate_all(
    prompt=[{"role": "user", "content": "Say hi in one word."}],
    temperature=0.1, max_generated_tokens=16,
)
print(f"3. LLM OK: {text!r}")
llm.release(); vd.release()

# 4. Chemin Speech2Text
from hailo_platform.genai import Speech2Text, Speech2TextTask
params = VDevice.create_params(); params.group_id = "SMOKE_TEST"
vd = VDevice(params)
s2t = Speech2Text(vd, "/path/to/Whisper-Base.hef")
audio = (np.random.default_rng(0).standard_normal(32000) * 0.01).astype("<f4")
segments = s2t.generate_all_segments(
    audio_data=audio, task=Speech2TextTask.TRANSCRIBE,
    language="en", timeout_ms=30000,
)
print(f"4. Speech2Text OK: {len(segments)} segments")
if segments:
    seg = segments[0]
    print(f"   attrs: text={seg.text!r} start_sec={seg.start_sec} end_sec={seg.end_sec}")
s2t.release(); vd.release()

print("\nAll smoke tests passed.")
```

---

## 10. Liste de contrôle de mise à niveau

Points à auditer dans votre code avant ou pendant la mise à niveau 5.2.0 → 5.3.0 :

- [ ] `VDevice()` / `create_infer_model()` / `InferModel.configure()` — **Aucun changement nécessaire**
- [ ] Constructeurs `LLM(vd, path)` / `VLM(vd, path)` / `Speech2Text(vd, path)` — **Aucun changement nécessaire**
- [ ] Arguments mot-clé de `LLM.generate()` / `.generate_all()` / `VLM.generate(frames=…)` / `.generate_all()` — **Aucun changement nécessaire**
- [ ] `Speech2Text.generate_all_segments(audio_data=, task=, language=, timeout_ms=)` — **Aucun changement nécessaire** (si `timeout_ms` est passé explicitement)
- [ ] Vérifier si `LLM.read_all()` est appelé sans argument `timeout_ms` → ajouter un timeout explicite si c'est le cas
- [ ] Vérifier si `DeviceArchitecture` est construit directement → ajouter `chip_serial_number` si c'est le cas
- [ ] Rechercher les ouvertures directes de `/dev/hailo*` ou `/dev/hailort0` → remplacer par `/dev/h1x-0` (ou mieux, passer par pyhailort)
- [ ] Mettre à jour la section `devices:` Docker / Podman vers `/dev/h1x-0`
- [ ] Mettre à jour les lignes `DeviceAllow=` d'unité systemd et les règles udev
- [ ] Rechercher les accès aux attributs `SegmentInfo` avec `.start` ou `.start_time` → passer à `.start_sec` / `.end_sec`
- [ ] Si numpy était fixé sur 1.x (à cause de `numpy<2` de v5.2.0), la fixation peut maintenant être retirée
- [ ] **Pas besoin de re-télécharger** les fichiers `.hef` existants
- [ ] Si des URLs de téléchargement HEF avec le bucket `v5.2.0` sont codées en dur, les passer à `v5.3.0` (garder `v5.2.0` pour Llama-3.2-1B)
- [ ] Si vous dépendez du post-traitement NMS intégré de pyhailort, noter que les boîtes englobantes proches des bords d'image peuvent décaler de ±1 pixel

---

## 11. Commandes utilisées pour l'investigation

En supposant que le dépôt HailoRT officiel est cloné :

```bash
cd ~/hailort

# Taille globale du diff
git diff --stat v5.2.0 v5.3.0 | tail

# Diff des en-têtes C++ publics
git diff --stat v5.2.0 v5.3.0 -- 'hailort/libhailort/include/hailo/'

# Diff des bindings Python
git diff --stat v5.2.0 v5.3.0 -- 'hailort/libhailort/bindings/python/'

# Diff complet de pyhailort.py
git diff v5.2.0 v5.3.0 -- \
  'hailort/libhailort/bindings/python/platform/hailo_platform/pyhailort/pyhailort.py'
```

---

## 12. Conclusion

Le titre « 688 fichiers modifiés » est très éloigné de l'impact réel.
Pour une application d'inférence Hailo-10H NPU typique :

- **Les API d'inférence NPU core (`VDevice` / `InferModel` / GenAI) sont entièrement rétrocompatibles**
- Toutes les API supprimées concernent les surfaces de caméra / capteur / ISP / gestion du firmware Hailo-8, sans aucun rapport avec l'usage NPU uniquement
- **Tous les fichiers `.hef` existants se chargent sans re-téléchargement**
- Le seul changement obligatoire au niveau environnement est de mettre à jour le passage de périphérique Docker vers `/dev/h1x-0`

Principales améliorations de qualité de vie après mise à niveau :
- Les timeouts par défaut sont considérablement étendus (10 sec → 10 min), réduisant les faux timeouts lors des générations longues
- `FormatType.FLOAT32` est maintenant disponible (v5.2.0 nécessitait une quantification/déquantification manuelle)
- Correction du bug de clipping des coordonnées NMS
- Chemin de mise à niveau numpy 2.x ouvert
- `VLM.generate_from_embeddings()` permet de réutiliser les embeddings d'images précalculés pour plusieurs appels VLM
