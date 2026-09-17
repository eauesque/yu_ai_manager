# Contraintes CMA sous `numa=fake=8` sur le Pi 5

Connaissances pratiques sur l'allocation CMA sur un Raspberry Pi 5 (8 Go) lors de l'exécution de charges de travail Hailo-10H.
Décrit la limite de `cma=`, la raison pour laquelle les valeurs supérieures à 512M échouent silencieusement, et comment récupérer le CMA consommé par le pilote d'affichage.

**Public visé** : développeurs exécutant des modèles Hailo GenAI (LLM, Speech2Text) sur Raspberry Pi 5
(avec AI HAT / AI HAT+).

---

## ⚠️ Avertissement régression firmware 2026-05

**Depuis la sortie du 2026-05-13 de `raspi-firmware 1:1.20260513-1` + `pieeprom-2026-05-11`**, écrire `cma=` dans `/boot/firmware/cmdline.txt` (quelle que soit la taille) fait entièrement taire la mailbox du firmware VC (`vcgencmd ioctl_set_msg failed:-1`, `raspberrypi-clk -22`, HEVC `-517`, absence du sysfs cpufreq).

**Méthode recommandée confirmée depuis le 2026-05-16** : ne pas utiliser `cma=` dans cmdline, mais écrire `dtoverlay=cma,cma-512` dans `/boot/firmware/config.txt`. L'allocation se fait via le nœud de mémoire réservée `linux,cma` du DT, ce qui n'entre pas en conflit avec le nouveau firmware. Voir §6 et [`docs/development/investigations/pi5_firmware_cma_mailbox_regression_2026-05-16.md`](../../development/investigations/pi5_firmware_cma_mailbox_regression_2026-05-16.md) pour les détails.

La description ci-dessous (ancienne, recommandant `cma=512M` en cmdline) correspond aux résultats de vérification du 2026-04-15. Les connaissances sur la valeur plafond (512M) due aux limites de nœud NUMA restent valides, mais **l'emplacement de configuration passe de cmdline à l'argument overlay de config.txt**.

---

## TL;DR

- **L'emplacement de configuration est `dtoverlay=cma,cma-512` dans `config.txt`** (confirmé le 2026-05-16 ; `cma=` en cmdline casse la mailbox avec le nouveau firmware)
- `cma-1024` et `cma-768` **échouent silencieusement** sur Pi 5 (8 Go) — `CmaTotal` devient 0, sans panique noyau ni avertissement (limite due aux frontières de nœud NUMA ; on suppose que la même contrainte subsiste via l'overlay)
- **`cma-512` est la valeur plafond vérifiée et recommandée** (re-vérifiée le 2026-05-16 sur Pi 5 8 Go via l'overlay, `CmaTotal: 524288 kB` confirmé)
- Cause racine : le noyau Pi 5 par défaut applique `numa=fake=8`, limitant les allocations contiguës à 1 nœud NUMA (1 Go)
- **`dtoverlay=vc4-kms-v3d` + `max_framebuffers=2` consomme ~157 Mo de CMA au démarrage** — même si l'initialisation du pilote DRM échoue (vérifié le 2026-04-15)
- **`camera_auto_detect=1`** charge `pisp_be` et `videobuf2_dma_contig`, consommant du CMA supplémentaire. Désactivation recommandée pour les systèmes headless
- **Base optimisée headless** (les deux overlays désactivés) : ~98 Mo de CMA utilisés au démarrage, ~414 Mo disponibles pour les modèles Hailo
- **YOLO InferModel utilise 0 Mo de CMA** (confirmé le 2026-04-15) — seuls les modèles GenAI (LLM, Speech2Text) allouent depuis le CMA
- Chargement simultané LLM (qwen2.5-1.5b) + Whisper-base : total ~328 Mo — tient dans la base optimisée headless
- Le CMA n'est pas récupéré au redémarrage du serveur — libéré uniquement par un redémarrage complet du système (réinitialisation de l'alimentation PCIe) (bug du pilote `hailo1x_pci`, signalé à Hailo)
- Traiter le VDevice comme un **singleton à durée de vie du processus**. Interdiction d'éviction/rechargement

---

## 1. Symptômes

Si vous définissez `cma=1G` (ou `cma=768M`) dans `/boot/firmware/cmdline.txt` et redémarrez, vous obtenez :

```
$ grep CmaTotal /proc/meminfo
CmaTotal:              0 kB
```

Le système démarre normalement. Aucune panique noyau, aucun message d'erreur. La configuration CMA de `cmdline.txt` est **ignorée silencieusement**, et l'initialisation de tout ce qui dépend du CMA (NPU Hailo-10H, caméra V4L2, etc.) échoue.

**Vérifiez toujours l'allocation CMA après toute modification de `cmdline.txt` :**

```bash
grep CmaTotal /proc/meminfo
```

---

## 2. Cause racine : la frontière de nœud `numa=fake=8`

Le noyau Raspberry Pi OS par défaut pour Pi 5 applique `numa=fake=8`, divisant les 8 Go de mémoire physique en **8 nœuds NUMA virtuels de 1 Go chacun** :

```
numa=fake=8 physical memory layout (8 GB total):

┌──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┐
│ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │
│node0 │node1 │node2 │node3 │node4 │node5 │node6 │node7 │
└──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┘
```

Le CMA Linux (`cma_init_reserved_mem`) doit être alloué au démarrage comme **mémoire physique contiguë ne franchissant pas de frontière de nœud NUMA**.
Cela impose une limite stricte de 1 Go par nœud. Comme le noyau lui-même occupe de la mémoire dans le même nœud, il est impossible de réserver exactement 1 Go :

> **Le tableau ci-dessous est un relevé de mesures effectuées le 2026-04-15 selon la méthode `cmdline`.**
> Le constat sur la limite (512 Mo) liée aux frontières de nœud NUMA reste valable, mais **`cma=` en cmdline ne doit plus être utilisé aujourd'hui** (voir la régression du firmware en introduction).
> La méthode de configuration actuelle est `dtoverlay=cma,cma-512` dans `config.txt` (§6).

| Configuration `cmdline.txt` (relevé du 2026-04-15) | Résultat |
|---|---|
| `cma=1G` | Tente de consommer un nœud entier. Pas de marge pour le noyau → **échec silencieux**, CmaTotal=0 |
| `cma=768M` | Dépasse la plage contiguë fiable → **échec silencieux**, CmaTotal=0 (vérifié le 2026-04-15) |
| `cma=512M` | Moitié d'un nœud → **stabilité confirmée** ✓ (vérifié le 2026-04-15) ← recommandé à l'époque. **Utilisez désormais `dtoverlay=cma,cma-512`** |
| `cma=384M` | Non testé (512M confirmé ; 384M inutile) |
| `cma=256M` | Stable, mais serré en cas d'usage simultané LLM + Whisper |
| `cma=128M` | Stable, mais insuffisant pour Hailo GenAI (le LLM seul nécessite ~234 Mo) |

### Pourquoi l'échec est silencieux

`cma_init_reserved_mem` ne panique pas en cas d'échec d'allocation. Le noyau démarre avec `CmaTotal=0`, se comportant comme si le CMA n'avait jamais été demandé.
La valeur écrite dans `cmdline.txt` est en pratique ignorée.

---

## 3. Exigences CMA de Hailo-10H

Mesuré sur Raspberry Pi 5, AI HAT+, HailoRT 5.3.0 :

| Modèle / combinaison | Utilisation CMA | Remarque |
|---|---|---|
| LLM — qwen2.5-1.5b-chat (seul) | **~234 Mo** | Mesuré le 2026-04-15 |
| YOLO InferModel (yolov8n, configure + bindings) | **0 Mo** | Confirmé le 2026-04-15 |
| Whisper-tiny (seul) | ~70 Mo | Estimation |
| Whisper-base (seul) | ~100 Mo | Estimation |
| Whisper-small (seul) | ~150 Mo | Estimation |
| **LLM + Whisper-tiny (simultané)** | **~246 Mo** | Mesuré avec CMA 256 Mo |
| **LLM + Whisper-base (simultané)** | **~334 Mo** | Estimation. Attendu de tenir dans la base headless |

**YOLO utilise 0 Mo de CMA** : sous HailoRT 5.3.0, YOLO InferModel, `configure()` et `create_bindings()` n'allouent aucun CMA.
Les tampons DMA d'entrée/sortie sont mappés depuis des tableaux numpy pré-alloués via `set_buffer()`, et non depuis le CMA.
YOLO n'entre donc pas dans le calcul du budget CMA.

Avec CMA 512 Mo et l'optimisation headless (voir §5), les configurations suivantes devraient fonctionner :

- LLM seul (~234 Mo, ~180 Mo de marge)
- Whisper-tiny / Whisper-base seul (tient facilement)
- LLM + Whisper-base simultané (total ~334 Mo, ~80 Mo de marge)

La combinaison Whisper-small + LLM (estimée ~384 Mo) approche la limite théorique — vérifiez par une mesure réelle avant de vous y fier.

Voir [hailo_genai_concurrent_2026-04-15.md](../../development/investigations/hailo_genai_concurrent_2026-04-15.md) pour les résultats des tests de chargement simultané.

---

## 4. Le CMA n'est récupéré qu'au redémarrage complet

Le CMA alloué par HailoRT reste en mémoire jusqu'à un redémarrage complet du système.
Cela vaut que `VDevice.release()` soit appelé, que le processus serveur se termine, ou que le module noyau soit rechargé.

**Cause racine** (confirmée le 2026-04-15) : `hailo1x_pci` conserve les allocations DMA cohérentes même après la fermeture du fd du périphérique ou le rechargement du module.
Seul un redémarrage complet (réinitialisation de l'alimentation PCIe) les libère. Le bug a été signalé à Hailo.

| Phase | CmaFree (CMA 512 Mo, optimisation headless) |
|---|---|
| Démarrage | **~426 Mo** |
| Après chargement du LLM (~234 Mo) | ~192 Mo |
| Après chargement de Whisper-base (~100 Mo) | ~92 Mo |
| Après `VDevice.release()` | ~92 Mo (**non restitué**) |
| Après la fin du processus serveur | ~92 Mo (**non restitué**) |
| Après `rmmod hailo1x_pci && modprobe hailo1x_pci` | ~92 Mo (**non restitué**) |
| Après redémarrage complet du système | **~426 Mo (restauré)** |

**Implication** : la consommation de CMA s'accumule au-delà des redémarrages du serveur au sein d'une même session de démarrage.
Ne comptez pas sur un redémarrage du serveur pour récupérer le CMA. Concevez le VDevice comme un **singleton à durée de vie du processus**.
Si le CMA est épuisé, seul un redémarrage complet du système le restaurera.

---
## 5. Optimisation headless : `/boot/firmware/config.txt`

Le fichier `config.txt` par défaut de Pi OS contient deux réglages qui consomment une quantité importante de CMA, même sur un système headless (sans affichage).

### 5.1 `dtoverlay=vc4-kms-v3d` et `max_framebuffers=2`

**Effet** : le firmware Pi 5 pré-alloue des framebuffers CMA pour le pipeline d'affichage au démarrage.
Avec `max_framebuffers=2`, cela consomme ~157 Mo de CMA **avant même qu'un processus utilisateur ne s'exécute**.

Cette allocation persiste même si le pilote DRM Linux échoue ensuite à s'initialiser (par exemple : `[drm] Couldn't stop firmware display driver: -22` ou `Couldn't get core clock` dans `dmesg`).

| État de `config.txt` | CmaFree au démarrage |
|---|---|
| `dtoverlay=vc4-kms-v3d` + `max_framebuffers=2` activés (par défaut) | **~257 Mo** |
| Les deux commentés | **~305 Mo** (+~48 Mo) |

**Correctif** (mode headless / serveur) :

```ini
# /boot/firmware/config.txt
#dtoverlay=vc4-kms-v3d
#max_framebuffers=2
```

**Compromis** : `vc4-kms-v3d` est nécessaire pour l'accélération matérielle de l'affichage et la 3D (V3D).
Si le système n'est accessible que par SSH ou une interface web, il est sûr de le désactiver.

### 5.2 `camera_auto_detect=1` et `display_auto_detect=1`

**Effet** : ces overlays sondent les caméras CSI et les écrans DSI au démarrage, et chargent `pisp_be` (backend ISP du Pi) et `videobuf2_dma_contig`.
Les modules chargés et le matériel détecté pré-allouent divers CMA supplémentaires.

| État de `config.txt` | CmaFree au démarrage |
|---|---|
| `camera_auto_detect=1` + `display_auto_detect=1` | ~305 Mo (après désactivation de vc4) |
| Les deux mis à 0 | **~426 Mo** (+~121 Mo) |

**Correctif** :

```ini
camera_auto_detect=0
display_auto_detect=0
```

**Remarque** : `camera_auto_detect=0` n'affecte que les caméras CSI. Les caméras USB (UVC / `uvcvideo`) ne sont pas concernées et continuent de fonctionner normalement.

### 5.3 `config.txt` minimal recommandé pour un usage AI HAT+ headless

```ini
auto_initramfs=1
arm_64bit=1
arm_boost=1

[cm5]
dtoverlay=dwc2,dr_mode=host

[all]
dtparam=pciex1_gen=3
```

Estimation du CMA au démarrage avec cette configuration : **~98 Mo utilisés**, ~414 Mo disponibles pour les modèles Hailo.

### 5.4 Résumé du budget CMA (CMA 512 Mo, optimisation headless)

| Configuration | CmaFree | Disponible pour Hailo |
|---|---|---|
| Par défaut (vc4-kms-v3d + caméra activés) | ~257 Mo | ~257 Mo |
| vc4-kms-v3d + max_framebuffers désactivés | ~305 Mo | ~305 Mo |
| + camera/display_auto_detect=0 | **~426 Mo** | **~426 Mo** |
| Après chargement du LLM (~234 Mo) | ~192 Mo | Pour Whisper |
| Après chargement LLM + Whisper-base (~100 Mo) | ~92 Mo | (marge) |

---

## 6. Configuration recommandée

### Définir `dtoverlay=cma,cma-512` (confirmé le 2026-05-16)

```bash
# Vérifier l'état actuel du CMA
grep CmaTotal /proc/meminfo

# 1) Supprimer le cma= existant de cmdline.txt (car il casse la mailbox avec le nouveau firmware)
sudo sed -i 's/ *cma=[^ ]*//g' /boot/firmware/cmdline.txt

# 2) Ajouter dtoverlay=cma,cma-512 dans la section [all] de config.txt
sudo sed -i '/^\[all\]$/a dtoverlay=cma,cma-512' /boot/firmware/config.txt

# 3) Redémarrage à froid recommandé (débrancher/rebrancher l'alimentation)
sudo sync && sudo poweroff

# Vérifier après redémarrage (les 4 points suivants doivent tous être confirmés)
vcgencmd version                                # Réponse Broadcom requise (silence = échec)
grep CmaTotal /proc/meminfo                     # 524288 kB attendu
journalctl -b -k | grep 'linux,cma'             # doit afficher "initialized node linux,cma"
journalctl -b -k | grep '0x00030087'            # ne doit rien afficher
```

Si `OF: reserved mem: initialized node linux,cma, compatible id shared-dma-pool` apparaît dans dmesg, c'est la preuve que l'allocation s'est faite par la voie DT.
À l'inverse, si `Reserved memory: bypass linux,cma node, using cmdline CMA params instead` apparaît, cela signifie que `cma=` subsiste dans cmdline et doit être supprimé.

### Si vous activez `vc4-kms-v3d`

Si le KMS DRM d'affichage est nécessaire, il peut être intégré sous forme d'argument overlay :
```ini
dtoverlay=vc4-kms-v3d,cma-512
```
Cependant, comme indiqué en §5.1, `vc4-kms-v3d` consomme ~157 Mo de CMA ; sa désactivation est recommandée pour les usages Hailo GenAI.

### Vérifier après chaque modification du noyau / firmware / configuration

Toute modification de `/boot/firmware/cmdline.txt` ou de `config.txt`, ou toute mise à jour du noyau/firmware, peut modifier silencieusement l'état du CMA et la réponse de la mailbox.
Faites de la vérification des 4 points ci-dessus une routine après chaque redémarrage.

---

## 7. Interaction avec d'autres problèmes liés à `numa=fake=8`

`numa=fake=8` provoque au moins 2 problèmes distincts pertinents pour ce projet :

| Problème | Symptôme | Cause racine |
|---|---|---|
| Échec silencieux du CMA | `CmaTotal=0` après `cma=1G`, `cma=768M` | La frontière de nœud NUMA limite les allocations contiguës |
| Échec d'installation Node.js | L'installateur npm/node abandonne avec une erreur mémoire | La mémoire par nœud NUMA (1 Go) est faussement détectée comme la RAM totale. Signalé en amont sous [anthropics/claude-code#33864](https://github.com/anthropics/claude-code/issues/33864) |
| Drain CMA de `vc4-kms-v3d` | Consomme ~157 Mo au démarrage. Non restitué même si l'init DRM échoue | `max_framebuffers=2` fait réserver des framebuffers CMA par le firmware, avant le démarrage du pilote Linux |

L'échec silencieux et le drain vc4 proviennent tous deux de la même contrainte fondamentale (zone DMA des 4 Go bas, frontières de nœud NUMA).
En cas de défaillance inattendue liée à la mémoire, vérifiez d'abord `/proc/meminfo` et `config.txt`.

---
## 8. Liste de contrôle de diagnostic rapide

```bash
# 1. Réponse de la mailbox (vérification prioritaire avec le nouveau firmware)
vcgencmd version                     # silence = suspicion de cma= restant en cmdline

# 2. Vérifier l'allocation CMA
grep CmaTotal /proc/meminfo          # 0 kB = échec silencieux

# 3. Vérifier la voie DT vs la voie cmdline
journalctl -b -k | grep 'linux,cma'
# Attendu : "initialized node linux,cma, compatible id shared-dma-pool" (voie DT = normal)
# Anormal : "bypass linux,cma node, using cmdline CMA params instead" (cmdline persiste)

# 4. Vérifier la topologie NUMA
numactl --hardware                   # affiche le nombre de nœuds et la mémoire par nœud

# 5. Vérifier la ligne de commande actuelle et la configuration overlay
cat /boot/firmware/cmdline.txt       # vérifier l'absence de cma=
grep '^dtoverlay=cma' /boot/firmware/config.txt   # dtoverlay=cma,cma-512 doit être présent

# 6. Vérifier la disponibilité du périphérique Hailo
ls /dev/h1x-*                        # HailoRT 5.3.0: /dev/h1x-0
hailortcli fw-control identify       # vérifier que le NPU est accessible

# 7. Vérifier config.txt pour les consommateurs de CMA
grep -E 'vc4-kms-v3d|camera_auto_detect|display_auto_detect|max_framebuffers' \
  /boot/firmware/config.txt

# 8. Vérifier les modules noyau chargés (utilisateurs du CMA)
lsmod | grep -E 'vc4|v3d|pisp|videobuf2_dma'
```

---

**Environnement de vérification** : Raspberry Pi 5 8 Go, Raspberry Pi OS
(Linux 6.12.62+rpt-rpi-2712, aarch64), HailoRT 5.3.0, AI HAT+, CMA=512M
(**Re-vérifié le 2026-05-16** : Linux 6.18.29+rpt-rpi-2712 / raspi-firmware 1:1.20260513-1 / pieeprom-2026-05-11 / Hailo-10H AI HAT — 524288 kB confirmés via `dtoverlay=cma,cma-512`, réponse mailbox vérifiée)
