# Correction et vérification du diagnostic « CMA non libérée » — HailoRT / driver 5.4.0

Créé : 2026-08-16 / Dernière mise à jour : 2026-08-17 / Version correspondante : yu_ai_manager 4.623.1

Enregistrement de la vérification d'hypothèse et de l'essai A/B entre la version vanilla officielle et la version corrigée `FOLL_LONGTERM` de `hailo-ai/hailort-drivers` v5.4.0 (publiée le 2026-08-16, GPL-2.0, code source publié), portant sur l'événement précédemment diagnostiqué comme « CMA non libérée » (voir `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md`), qui a permis de corriger une évaluation erronée côté mesure.

---

## 1. Conclusion

**Contre-essai final du 2026-08-17 (4ᵉ essai) : le `VERDICT: FAIL` obtenu jusqu'au 3ᵉ essai résultait d'une évaluation erronée fondée sur la seule quantité de récupération absolue de `CmaFree` après le premier chargement du HEF, utilisée comme critère de diagnostic de fuite. En comparant en A/B la version vanilla officielle 5.4.0 et la version corrigée `FOLL_LONGTERM`, tous les essais ont réussi : chargements successifs depuis un `CmaFree` bas, libération et rechargement au sein d'un même processus, 20 générations, et répétition complète des essais depuis un état de `CmaFree` encore plus bas. Aucune augmentation ou diminution monotone n'a été observée sur la RSS ni sur `CmaFree` pendant la génération, et aucun échec d'allocation CMA n'a été enregistré. La baisse initiale de `CmaFree` correspond à l'augmentation du cache de pages due au HEF de plusieurs Go, et `MemAvailable` s'est maintenu à environ 7 Go. Dans les conditions testées ici — Pi 5 + Hailo-10H + HailoRT/driver 5.4.0, modèle unique, périphérique unique, répétitions de courte durée — aucune fuite CMA n'a été reproduite en pratique, et la correction `FOLL_LONGTERM` n'apporte elle-même aucune amélioration mesurable. Le fonctionnement continu de longue durée, l'utilisation simultanée de plusieurs modèles, le Hailo-8 et le fonctionnement sous IOMMU n'ont pas été testés et sortent du champ d'application de cette conclusion.**

### 1.1 Évolution de l'évaluation

| Essai | Date | Évaluation à ce moment | Base de la mise à jour / correction |
|---|---|---|---|
| 1ᵉʳ | 2026-08-16 | Évaluation impossible | Le fait de passer uniquement le driver en 5.4.0 a entraîné un rejet de l'API par le contrôle de correspondance exacte avec la library 5.3.0 (§3) |
| 2ᵉ | 2026-08-17 | Seuls des essais limités achevés | driver / library / firmware alignés en 5.4.0, la répétition `run2` s'est stabilisée en plateau, mais la reproduction directe via pyhailort n'avait pas encore été effectuée (§4) |
| 3ᵉ | 2026-08-17 | `FAIL` provisoire (ultérieurement reconnu comme erroné) | Ancien résultat de diagnostic fondé uniquement sur la quantité de récupération absolue de `CmaFree` après le premier chargement du HEF. Une mesure ponctuelle ne permettait pas de distinguer la perte de mémoire réelle de l'utilisation du cache de pages (§5, §7) |
| 4ᵉ | 2026-08-17 | Aucune fuite reproduite en pratique | Essai A/B vanilla / `FOLL_LONGTERM`, répétitions à CMA bas, rechargement au sein d'un même processus, 20 générations, mesure de la RSS, de `MemAvailable` et des échecs d'allocation, corrigeant le 3ᵉ essai (§8) |

---

## 2. Diff des sources v5.3.0 → v5.4.0 (`hailo-ai/hailort-drivers`)

Diff de tous les fichiers entre les deux tags via l'API GitHub. Étant donné un unique commit squashé, le message de commit n'apporte aucune information ; la vérification s'est faite sur le diff des fichiers réels. **La logique elle-même** d'allocation et de libération de la CMA (paire `dma_alloc_coherent`/`dma_free_coherent`) n'a pas changé ; les modifications ci-dessous relèvent essentiellement du refactoring et de correctifs défensifs :

| Fichier | Contenu de la modification |
|---|---|
| `linux/utils/compact.h` → `compat.h` | Renommage du fichier de la couche de compatibilité kernel |
| `linux/vdma/memory.c` | Ajout d'un contrôle NULL dans `hailo_desc_list_release()`, remise à NULL du pointeur après libération (correctif défensif de **prévention de double libération**) |
| `linux/vdma/vdma.h` | Suppression du champ redondant `kernel_address` de `hailo_descriptors_list_buffer` (fusionné dans `desc_list.descs`) |
| `common/vdma_common.c` | Réécriture de la détection de fin de transfert DMA, passant d'un calcul direct sur `hw_num_proc` à une comparaison `num_proc`/`num_avail` (possible correction de bug dans le suivi de fin de transfert) |
| `linux/vdma/monitor.c` | `del_timer_sync` → `timer_delete_sync` (alignement sur le nouveau nom d'API kernel) |
| `common/pcie_common.c` | Suppression du champ md5 du protocole de contrôle FW, renforcement du contrôle de corruption des logs SCU, passant des seuls 4 premiers octets à la vérification complète des 5 premiers mots |

Le libellé des messages d'erreur a également changé (texte explicatif long → raccourci en `out of CMA memory.`), mais le flux de contrôle d'allocation et de libération reste identique. **Ce diff seul ne révèle aucune modification correspondant à l'hypothèse formulée à l'époque (non-libération de la CMA lors du rechargement de modèle)**.

---

## 3. Travail de remplacement sur matériel réel et points de blocage (2026-08-16, 1ᵉʳ essai)

Tentative de remplacement par une compilation manuelle vers v5.4.0, sur un Raspberry Pi 5 + Hailo-10H où `hailo1x_pci 5.3.0` (géré par dkms) était en fonctionnement.

### 3.1 `make install` ne dépend pas de `all`

La cible `install` du `linux/pcie/Makefile` ne fait que `modules_install`, et se termine sans avertissement même en l'absence de tout artefact de build (`.ko`) — plus précisément, un avertissement sur l'absence de `System.map` apparaît, mais rien n'indique que la cause est l'absence de compilation.

```makefile
install:
	$(Q)$(MAKE) -C $(KERNEL_DIR) M=$(PWD) INSTALL_MOD_DIR=kernel/drivers/misc modules_install
	$(Q)$(DEPMOD) -a

all: $(TARGET_DIR) print-versions
	$(Q)$(MAKE)  -C $(KERNEL_DIR) M=$(PWD) $(GDB_FLAG) $(USER_FLAGS) modules
	$(Q)cp $(DRIVER_NAME_NO_EXT)* $(TARGET_DIR)
```

**Exécuter impérativement dans l'ordre `make all && sudo make install`.**

### 3.2 Les en-têtes kernel de Raspberry Pi n'incluent pas `System.map`

Lors de l'exécution de `modules_install`, l'avertissement suivant apparaît et `depmod` est silencieusement ignoré :

```
Warning: modules_install: missing 'System.map' file. Skipping depmod.
```

Car `/usr/src/linux-headers-<kernelver>/System.map` n'existe pas. `/boot/System.map-<kernelver>` existe, donc une copie résout le problème :

```bash
sudo cp /boot/System.map-$(uname -r) /usr/src/linux-headers-$(uname -r)/System.map
sudo depmod -a
```

Sans cela, `modprobe` ne peut pas résoudre le `.ko` nouvellement installé et renvoie `FATAL: Module hailo1x_pci not found` (alors même que le fichier `.ko` existe bien dans `/lib/modules/<kernelver>/kernel/drivers/misc/`).

### 3.3 Les règles udev ne sont pas prises en compte immédiatement sans reload/trigger

`/lib/udev/rules.d/51-hailo-pcie-udev.rules` :

```
SUBSYSTEM=="hailo1x", MODE="0666"
```

Immédiatement après le remplacement du module, `/dev/h1x-0` devient `crw-------` (réservé root). Résolu comme suit :

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hailo1x
```

### 3.4 Une incompatibilité de version entre driver et library est fatale

En exécutant `hailortcli` alors que seul le driver kernel avait été passé en 5.4.0 :

```
dmesg: Mismatch Driver version pcie driver 5:4:0 pci_ep driver 5:3:0
dmesg: hailo_soc_get_driver_info has failed with err -22

hailortcli: [HailoRT] [error] CHECK failed - Driver version (5.4.0) is different from library version (5.3.0)
hailortcli: [HailoRT] [error] Driver version mismatch, status HAILO_INVALID_DRIVER_VERSION(76)
```

La library HailoRT exige une **correspondance exacte** avec le driver kernel : mettre à niveau un seul des deux composants entraîne le rejet immédiat de tous les appels d'API. Une vérification vanilla du driver seul est donc impossible ; le paquet userspace `hailort` (SDK principal) doit être mis à niveau simultanément.

- `apt-cache policy hailort` → candidat 5.3.0 (à la date du jour, la 5.4.0 n'est pas encore distribuée via apt officiel)
- `gh api repos/hailo-ai/hailort/releases` → le tag `v5.4.0` existe mais `assets` est vide (pas de deb précompilé, source uniquement)

En somme, **une vérification effective de la 5.4.0 sur le terrain nécessite soit l'installation de HailoRT via un deb, soit une compilation complète depuis les sources**. La compilation complète implique une compilation C++ CMake + bindings Python de grande ampleur, avec le risque d'entraîner des paquets dépendants tels que `hailo-tappas` et `python3-hailort` ; elle a donc été reportée lors du 1ᵉʳ essai, en attendant la distribution officielle du deb.

---

## 4. Journal de la compilation maison (2026-08-17, 2ᵉ essai)

Procédure et points de blocage lors de la compilation maison depuis les sources GitHub (driver : GPL-2.0, `hailort` principal : MIT) et de son déploiement sur le système, sans attendre la distribution apt/deb officielle.

### 4.1 Environnement de compilation

- Installation de `checkinstall` (`sudo apt-get install -y checkinstall`). Mais l'étape de compression `xz` du module kernel entrait en conflit avec `installwatch` (le mécanisme de suivi de fichiers de checkinstall basé sur LD_PRELOAD), et l'exécution de `make install` via checkinstall échouait systématiquement avec `xz: ... aucun fichier ou dossier de ce type`. **Ne pas utiliser checkinstall pour l'empaquetage des modules kernel : utiliser dkms (pour le driver lui-même) ou un simple `make install` (pour la library userspace)**
- Libération de mémoire avant compilation : arrêt temporaire des processus `headroom mcp serve` en doublon et de `rust-analyzer` (libérant près de 1 Go au total). La mémoire du Pi étant de 7,9 Gi, environ 3,8 Gi disponibles ont pu être maintenus pendant la compilation

### 4.2 Compilation de `hailort` (library userspace)

```bash
git clone --branch v5.4.0 --depth 1 https://github.com/hailo-ai/hailort.git
cd hailort/build   # créer d'abord le répertoire
cmake .. -DCMAKE_BUILD_TYPE=Release   # récupération automatique des dépendances externes (protobuf/spdlog/eigen etc.) via FetchContent, environ 4 minutes
cmake --build . -j2   # limité à -j2 (pour éviter la saturation mémoire), environ 15 minutes
sudo make install     # déployé dans /usr/local/{include,lib,bin} ; peut coexister avec la version apt (5.3.0, sous /usr)
```

Toutes les valeurs `option()` par défaut désactivent les composants lourds (GStreamer, tests, serveur, intégration Ollama, etc.), ce qui a donné une compilation relativement légère : seuls `libhailort.so`, `hailortcli` et `libhailopp` ont été construits.

**Remarque** : les artefacts de `make install` sont placés sous `/usr/local` et n'écrasent pas la version apt (sous `/usr`, 5.3.0). Lors de la vérification du fonctionnement, il faut préciser explicitement le chemin, par exemple `LD_LIBRARY_PATH=/usr/local/lib /usr/local/bin/hailortcli ...`.

### 4.3 Remplacement du driver (module kernel) et mise à jour du firmware

Le driver lui-même a été compilé et installé via dkms (même procédure que celle de restauration de l'annexe A, avec `-v 5.4.0`), puis rechargé via `rmmod`/`modprobe`. À ce stade, `hailortcli` renvoyait `HAILO_DRIVER_OPERATION_FAILED(36)` / dmesg indiquait `Mismatch Driver version pcie driver 5:4:0 pci_ep driver 5:3:0`, révélant que **le firmware embarqué sur le périphérique (côté SoC, pci_ep) devait lui aussi être mis à niveau vers 5.4.0 séparément**.

```bash
# Récupération du firmware depuis le S3 officiel (via le script fourni dans le dépôt driver)
bash hailort-drivers/download_firmware_hailo10h.sh
# Sauvegarde du firmware existant avant remplacement par la nouvelle version
sudo cp -r /lib/firmware/hailo/hailo10h /lib/firmware/hailo/hailo10h.backup-5.3.0
sudo cp <répertoire décompressé>/hailo10h_fw_5.4.0/* /lib/firmware/hailo/hailo10h/
sudo chown -R root:root /lib/firmware/hailo/hailo10h/
```

Un rechargement du module a alors été tenté (`rmmod`/`modprobe`, avec `support_soft_reset=1`), mais dmesg a continué de renvoyer systématiquement `SOC Firmware batch was already loaded`. En examinant les sources du driver, il s'est avéré que `load_soc_firmware()` (le chemin de chargement du firmware SoC pour le Hailo-10H) ne comporte aucun traitement de reset logiciel via `support_soft_reset` (ce traitement n'existe que dans `load_nnc_firmware()` pour le Hailo-8), et l'opération est inconditionnellement ignorée tant que `hailo_pcie_is_firmware_loaded()` renvoie true. Autrement dit, **l'état du firmware sur le SoC ne peut pas être modifié par un rechargement du module ; un cycle d'alimentation réel du matériel est indispensable**.

Après le redémarrage, dmesg a enregistré l'écriture du lot de firmware (`customer_certificate.bin`, `scu_fw.bin`, `u-boot-*.dtb.signed`, `u-boot-spl.bin`, `fitImage`, `image-fs`, dans cet ordre, 4064 ms) → `SOC Firmware Batch loaded successfully`, et `hailortcli fw-control identify` a répondu normalement avec `Firmware Version: 5.4.0 (release,app)`.

### 4.4 Vérification simplifiée du comportement CMA et ses limites

Avec `hailortcli run2` (resnet_v1_18.hef, petit modèle fourni avec le paquet `hailo_tutorials`), un load/run/exit ponctuel puis 8 exécutions consécutives ont été observées pour l'évolution de `CmaFree` (`/proc/meminfo`) :

| Exécution | CmaFree (kB) |
|---|---|
| ligne de base (juste après redémarrage) | 170464 |
| itération 1 | 134864 |
| itération 2 | 134144 |
| itérations 3 à 8 | 133744 (aucun changement, plateau) |

Un plateau a été atteint en quelques itérations, et aucune fuite supplémentaire n'a été observée jusqu'à la 8ᵉ. Toutefois, il s'agit d'un simple load/run/exit via CLI (chaque lancement dans un processus distinct), qui diffère des deux fuites connues rapportées dans `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md` — (a) non-libération lors de `VDevice.release()`/rechargement de modèle **au sein d'un même processus**, (b) fuite continue pendant l'exécution de `generate_stream()` (inférence LLM). Ce résultat ne constitue donc pas la preuve d'une « résolution ».

Le repro principal (`tools/diag_hailo_cma_reclaim.py` et le script décrit dans le document forum-followup) charge un LLM GenAI via le binding Python `hailo_platform` (pyhailort) et n'a donc pas pu être exécuté tel quel dans l'environnement 5.4.0 :

```
$ hailo_platform présent dans .venv est lié statiquement à libhailort.so.5.3.0 (confirmé via ldd)
$ Lors de la construction de VDevice(), un mismatch driver(5.4.0)/library(5.3.0) devrait produire la même HAILO_INVALID_DRIVER_VERSION
```

À ce stade, la recompilation de pyhailort (binding Python) depuis les sources 5.4.0 et son remplacement dans `.venv` n'avaient pas encore été entrepris, mais cela a été réalisé lors du 3ᵉ essai (§5).

---

## 5. Recompilation de pyhailort et nouvelle exécution du repro (2026-08-17, 3ᵉ essai)

Cette section consigne l'évaluation provisoire au moment du 3ᵉ essai. La méthode d'évaluation et la conclusion ont été corrigées par l'essai A/B du 4ᵉ essai (§8).

### 5.1 Compilation de pyhailort (binding Python)

`hailort/libhailort/bindings/python/platform/` du dépôt principal `hailort` est la source du paquet pip pyhailort (`pyproject.toml`, basé sur scikit-build-core + pybind11). Compilation en liant explicitement le libhailort 5.4.0 déjà déployé dans `/usr/local` en §4.2 :

```bash
cd hailort/libhailort/bindings/python/platform
CMAKE_ARGS="-DLIBHAILORT_PATH=/usr/local/lib/libhailort.so.5.4.0 -DHAILORT_INCLUDE_DIR=/usr/local/include" \
  <venv>/bin/python -m pip install .
```

`scikit-build-core`/`pybind11` ont été récupérés automatiquement depuis PyPI au sein de l'isolation de build, et le paquet `hailort` de `.venv` a été remplacé du wheel 5.3.0 vers 5.4.0. `ldd` a confirmé que `_pyhailort*.so` est bien lié à `/usr/local/lib/libhailort.so.5.4.0`, et le construct/release de `VDevice()` seul a également fonctionné normalement.

### 5.2 Nouvelle exécution du repro existant (`tools/diag_hailo_cma_reclaim.py`)

Avec le même script de repro, les mêmes critères de jugement et le même HEF (`~/hailo_models/Qwen3-1.7B-Instruct.hef`) que ceux de 2026-05, une nouvelle mesure a été effectuée dans le même environnement, avec `hailo_platform` de `.venv` remplacé en 5.4.0 :

```bash
uv run python tools/diag_hailo_cma_reclaim.py --signal terminate
```

Résultats (`logs/hailo_cma_reclaim_poc.json`) :

| Événement | CmaFree (Mo) |
|---|---|
| baseline_before_spawn | 159 |
| after_vdevice_created / after_llm_loaded | 22 (consommation de 137 Mo) |
| immédiatement après le kill du processus enfant (`terminate`) | 23 |
| post_wait +5s | 26 |
| post_wait +10s | 28 |
| post_wait +15s | 29 |
| post_wait +20s à +30s | **0** (nouvelle baisse d'environ 28,5 Mo depuis 29 Mo, `CmaFree` restant collé autour de 512 kB même plusieurs minutes après) |

Cette nouvelle baisse de 29 Mo vers environ 512 kB n'a pas pu être confirmée comme liée à une contention avec d'autres processus au même moment, mais cette seule mesure ne permet pas d'en identifier la cause ; elle reste consignée comme observation non résolue. L'utilisation du cache de pages après le premier chargement (§8.4) seule ne peut pas expliquer cette évolution intermédiaire, et aucun essai répété avec collecte simultanée de la RSS, de `MemAvailable` et des échecs d'allocation n'a été effectué lors de cette exécution ; elle n'est donc pas utilisée comme base de l'évaluation finale de §8.

Cependant, cette plage autour de 512 kB correspond à la même bande que les 464→1 648 kB observés lors de l'essai `FOLL_LONGTERM` de §8.3, et 20 générations, une libération et un rechargement ont réussi depuis cet état. Le processus menant à cette valeur basse reste inexpliqué, mais il a été confirmé sur matériel réel que **cette plage de `CmaFree` en elle-même ne signifie pas immédiatement un état dangereux ou une impossibilité de chargement**.

Texte brut produit par l'ancien outil de diagnostic (évaluation provisoire au moment du 3ᵉ essai ; évaluation finale corrigée en §8) :

```
VERDICT: FAIL — only -22 MB recovered after kill+wait. spec hypothesis invalid → pivot to auto-reboot alternatives
```

Ce qui a été établi lors de cet essai est uniquement que `CmaFree` ne s'est pas rétabli selon l'ancien critère après le premier chargement du HEF. Ni la perte de mémoire disponible après la fin du processus, ni l'absence de correction de la fuite en v5.4.0 n'ont été démontrées. Le 3ᵉ essai avait interprété cela provisoirement comme une non-libération ; cette interprétation et cette méthode d'évaluation ont été corrigées en §8.

---

## 6. Crash kernel pendant le 3ᵉ essai et restauration du code de débogage CMA (2026-08-17)

### 6.1 Événement et cause candidate

Pour examiner le chemin de libération de la CMA, l'inclusion `linux/mm.h` et un code de mesure appelant `virt_to_page()` / `page_count()` juste avant `dma_free_coherent()` avaient été ajoutés dans `linux/vdma/memory.c` des sources DKMS locales. Le chargement d'un module incluant cette modification a provoqué un blocage lors de l'utilisation de Hailo, rendant le démarrage impossible ; le chargement automatique est donc désormais bloqué via `module_blacklist=hailo1x_pci,hailo_pci` dans `/boot/firmware/cmdline.txt`.

Convertir directement en page via `virt_to_page()` l'adresse virtuelle CPU renvoyée par `dma_alloc_coherent()` ne fait pas partie du contrat de l'API DMA. Le format de mapping de l'adresse renvoyée est laissé à la discrétion de l'allocateur ; le `page_count()` obtenu de cette manière n'est donc pas un moyen fiable d'observer le nombre de références CMA, et peut produire des références de page invalides. Le code de mesure s'exécutait sur les deux chemins de libération : descriptor list et continuous buffer.

L'heure d'ajout était 10:15:36, et le build DKMS concerné a débuté à 10:15:39 ; on peut donc déduire que le module ayant bloqué le système incluait ce code. Aucune trace de pile juste avant le crash n'a pu être récupérée, ce qui empêche une identification stricte de la cause, mais il s'agit du seul changement de code d'exécution local absent de la version vanilla v5.4.0, et il constitue donc la cause candidate la plus probable.

### 6.2 État restauré

Les 7 lignes suivantes (inclusion de `linux/mm.h`, et les deux logs `virt_to_page()` / `page_count()`) ont été retirées, et le DKMS a été recompilé jusqu'à `depmod` inclus.

- Kernel : `6.18.39+rpt-rpi-2712`
- Module recompilé : `/lib/modules/6.18.39+rpt-rpi-2712/updates/dkms/hailo1x_pci.ko.xz`
- Le module ci-dessus est bien enregistré dans `modules.dep`
- La blacklist est maintenue ; le module recompilé n'a pas encore été chargé

La prochaine étape consiste à s'assurer d'un chemin de récupération (par exemple console série) avant de retirer la blacklist, puis à confirmer le premier chargement au prochain redémarrage. Pour l'enquête sur le problème de non-libération de la CMA lui-même, il ne faut pas réintroduire de mesure convertissant l'adresse renvoyée par l'API DMA en page interne ; il convient plutôt d'observer le registre de tampons interne du driver, la taille des allocations, et le nombre d'appels à `dma_free_coherent()`.

**Complément (2026-08-17, plus tard)** : après avoir préparé une sauvegarde de `cmdline.txt` (`cmdline.txt.bak-blacklisted`), la blacklist a été retirée et un redémarrage a été effectué, confirmant un démarrage normal (console série `console=serial0,115200` également configurée, garantissant un chemin de récupération). L'enquête s'est poursuivie ensuite avec l'instrumentation sûre de §7 (sans inspection de pages brutes, se limitant à la journalisation des compteurs et tailles existants).

---

## 7. Formation et exclusion d'hypothèses causales — vérification et réfutation de `FOLL_LONGTERM` (2026-08-17)

Cette section consigne la formation d'hypothèses causales à partir du 3ᵉ essai, ainsi que les candidats causaux exclus par expérimentation. Le rôle de cette section est le tri des candidats ; l'évaluation finale de la présence ou non de fuite CMA dépend de l'essai A/B du 4ᵉ essai (§8).

Suite au crash de §6, l'enquête s'est poursuivie avec une instrumentation sûre évitant tout accès direct à l'intérieur des pages via `virt_to_page()` etc. (limitée à la journalisation via `dev_err()` ; aucune inspection ni conversion de pointeurs bruts).

### 7.1 Contenu de l'instrumentation

Des logs affichant les compteurs atomiques existants (`controller->desc_cma_in_use` / `controller->cma_in_use`) et la taille des allocations (sans jamais accéder à l'intérieur des pages) ont été ajoutés aux emplacements suivants dans `linux/vdma/memory.c` / `linux/vdma/ioctl.c` / `linux/vdma/vdma.c` :

- `hailo_desc_list_create`/`hailo_desc_list_release` (alloc/free de la descriptor list)
- `hailo_vdma_continuous_buffer_alloc`/`hailo_vdma_continuous_buffer_free` (alloc/free du continuous buffer)
- `hailo_desc_list_release_ioctl`/`hailo_vdma_continuous_buffer_free_ioctl` (chemins ioctl de libération explicite)
- `hailo_vdma_buffer_map`/`hailo_vdma_buffer_destroy` (chemin de mapping/unmapping DMA des buffers userspace ; `buffer_type`/`is_mmio`/`is_dmabuf` également affichés)
- `hailo_vdma_file_context_finalize` (nettoyage global lors du fops_release, compteurs affichés à l'ENTER/EXIT)

### 7.2 Résultats observés

En partant d'un état juste après redémarrage (`CmaFree` ≈ 451 Mo), `tools/diag_hailo_cma_reclaim.py --signal terminate` a été exécuté, et l'ensemble des logs récupérés et agrégés via `sudo dmesg | grep CMA_DBG`.

- **`CmaFree` de `/proc/meminfo`** : 451 Mo → 195 Mo (**consommation de 256 Mo**) → après kill + 30 secondes d'attente, toujours 204 Mo (**247 Mo en dessous de la ligne de base**)
- **`desc_cma_in_use` du driver lui-même (descriptor list, via `dma_alloc_coherent`)** : au maximum 2 à 4 Mo environ. Revenu de manière certaine à 0 au moment de l'EXIT de `file_context_finalize`
- **`cma_in_use` (continuous buffer, via `dma_alloc_coherent`)** : constamment à 0 pendant cette session (le continuous buffer n'a jamais été utilisé)
- **Mapping DMA de buffers userspace (`hailo_vdma_buffer_map`, `buffer_type=0`=`HAILO_DMA_USER_PTR_BUFFER`, `is_mmio=0`, `is_dmabuf=0`)** : appelé 621 fois, dont **342 fois pour une taille de 8 Mo (`0x800000`)** (soit un total de 2,7 Go d'appels de mapping ; il semble que le même buffer de staging hôte soit réutilisé dans le pipeline). `hailo_vdma_buffer_destroy` a été appelé 628 fois, correspondant presque un pour un à `buffer_map` ; **aucune rupture n'est constatée dans le registre de mapping propre au driver** (`dma_unmap_sg` est correctement appelé)
- **SWIOTLB (`/sys/kernel/debug/swiotlb/`)** : `io_tlb_used_hiwater=0`. Le tampon de rebond n'a jamais été utilisé
- Le périphérique Hailo n'est pas sous IOMMU (`/sys/bus/pci/devices/0001:01:00.0/iommu_group` absent)

À ce stade, plutôt que les allocations propres du driver via `dma_alloc_coherent()` (desc list, continuous buffer), c'est le chemin de `hailo_vdma_buffer_map()`, qui gère le mapping DMA de mémoire déjà allouée par l'espace utilisateur (`HAILO_DMA_USER_PTR_BUFFER`), qui a été interprété comme candidat causal à la baisse de CMA. Sur ce chemin, le driver ne procède à aucune nouvelle allocation CMA ; il se contente de fixer (pin) des pages utilisateur existantes pour les rendre accessibles en DMA.

### 7.3 Hypothèse causale : `FOLL_LONGTERM` non spécifié dans `get_user_pages()`

En examinant `prepare_sg_table()` (appelé au sein de `hailo_vdma_buffer_map()`) dans `linux/vdma/memory.c` :

```c
pinned_pages = compat_get_user_pages(user_address, npages, FOLL_WRITE | FOLL_FORCE, pages);
```

`compat_get_user_pages` (le kernel utilisé ici, 6.18.39, relevant de `LINUX_VERSION_CODE >= KERNEL_VERSION(6, 5, 0)`) n'est qu'un simple alias de `get_user_pages()`, et **le flag `FOLL_LONGTERM` n'y est pas spécifié**. Côté libération (`clear_sg_table()`), le `put_page()` correspondant est également appelé ; le code reste ainsi sur l'ancienne API `get_user_pages()`/`put_page()` plutôt que sur la nouvelle famille `pin_user_pages()`/`unpin_user_pages()`.

Selon les bonnes pratiques documentées du kernel Linux (`Documentation/core-api/pin_user_pages.rst`), un code retenant une référence de page sur une longue durée, comme un transfert DMA, **devrait utiliser `pin_user_pages()` avec le flag `FOLL_LONGTERM`**. Sans `FOLL_LONGTERM`, si une page utilisateur se trouvant par hasard dans une région CMA est fixée via `get_user_pages()`, la propriété de « pouvoir être déplacée en cas de besoin » (migratable), propre à la CMA, se trouve invalidée durablement. L'allocateur CMA migre normalement de telles pages hors de la région CMA avant une fixation de longue durée, mais ce mécanisme de migration ne se déclenche pas sur un chemin n'utilisant pas `FOLL_LONGTERM` : **pendant toute la durée de la fixation, cette quantité est effectivement perdue pour la région CMA, et même après libération (`put_page()`), elle n'est pas immédiatement reconnue comme espace libre CMA** (une migration/compaction supplémentaire est nécessaire).

Cette hypothèse était cohérente avec la mesure ponctuelle du 3ᵉ essai (§7.2) :
- Les compteurs CMA propres au driver sont sans rapport (`get_user_pages` ne passe pas par `dma_alloc_coherent`)
- Le nombre d'appels map/destroy est correctement équilibré (`put_page()` lui-même est bien appelé ; le problème résiderait dans un « retour » vers la CMA lent/incomplet après libération)
- Le chargement d'un grand LLM comme Qwen3-1.7B-Instruct provoque l'allocation et le mapping DMA d'un grand nombre de buffers de 8 Mo en mémoire hôte, et le problème se manifesterait si une partie de ceux-ci incluait des pages de la région CMA
- Cela est également cohérent avec la récupération lente et partielle de `CmaFree` après kill (environ +15 à 30 Mo en 30 secondes, puis augmentation graduelle sur plusieurs minutes) (le `put_page()` lui-même est bien appelé de manière certaine à la fin du processus, mais un traitement supplémentaire semblerait nécessaire pour la récupération en tant qu'espace libre CMA)

### 7.4 Implémentation et vérification sur matériel réel du correctif candidat → réfutation (2026-08-17, suite)

`prepare_sg_table()` a été effectivement remplacé, passant de `get_user_pages(FOLL_WRITE | FOLL_FORCE)` + `put_page()` à `pin_user_pages(FOLL_WRITE | FOLL_FORCE | FOLL_LONGTERM)` + `unpin_user_page()`, avec ajout de l'inclusion `<linux/mm.h>`, puis compilation, réenregistrement dkms et chargement sur matériel réel menés jusqu'au bout (les symboles `pin_user_pages`/`unpin_user_page` ont été confirmés correctement résolus via `modprobe --dump-modversions`).

En partant d'un état de `CmaFree` élevé juste après redémarrage (453 Mo), résultats du même repro :

| | Avant correctif (n=plusieurs runs) | Après correctif (n=1) |
|---|---|---|
| baseline | 436 à 451 Mo | 453 Mo |
| after_llm_loaded | 173 à 195 Mo (consommation de 256 à 263 Mo) | 180 Mo (consommation de 273 Mo) |
| after_post_wait | 188 à 204 Mo (récupération de 9 à 15 Mo) | 190 Mo (**récupération de 10 Mo**) |
| `VERDICT` selon l'ancien critère | `FAIL` | **`FAIL` (sans changement)** |

> Ce tableau présente un nombre de runs et une méthode d'agrégation asymétriques ; il ne s'agit pas d'une comparaison A/B rigoureuse. Le jugement A/B repose sur les résultats de §8, obtenus par répétition dans les mêmes conditions.

En vérifiant `CMA_DBG buffer_map` via `dmesg`, il a été confirmé qu'après correctif également, les mêmes buffers de taille 0x800000 (8 Mo) étaient correctement mappés via `pin_user_pages` (aucun échec de pin ni avertissement kernel), le chemin de code lui-même s'exécutant comme prévu. Une compaction forcée via `echo 1 > /proc/sys/vm/compact_memory` n'a eu aucun effet non plus. `MemAvailable` est resté sain à 7,1 Go, confirmant que ce n'était pas une pénurie mémoire globale du système, mais uniquement la comptabilité spécifique de `CmaFree` qui ne récupérait pas — comme avant le correctif.

**Conclusion : l'hypothèse de l'absence de `FOLL_LONGTERM` a été réfutée par l'expérimentation.** Le remplacement de `get_user_pages()` par `pin_user_pages()`+`FOLL_LONGTERM` constitue une amélioration légitime conforme aux bonnes pratiques documentées de l'API DMA du kernel Linux, mais ne s'est pas révélé être la cause directe du symptôme de non-libération CMA observé dans cette session. L'hypothèse elle-même reste théoriquement cohérente (l'interaction entre le mécanisme de migration CMA et la fixation de longue durée est un type de problème connu et réel), et demeure valable comme remarque de qualité de code, mais **elle ne constitue pas, à elle seule, la cause profonde expliquant le résultat mesuré ici**.

### 7.5 Candidats causaux exclus (l'évaluation finale se trouve en §8)

Les éléments suivants sont des candidats causaux clairement **exclus** par l'expérimentation. Cette liste est un résultat utile de vérification d'hypothèses, mais ne constitue pas en elle-même le jugement de présence de fuite.

- Allocations propres du driver via `dma_alloc_coherent()` (desc list, continuous buffer) — seulement quelques Mo, revient correctement à 0
- Incohérence des appels map/destroy du mapping SG — équilibrée
- Tampon de rebond SWIOTLB — jamais utilisé (`io_tlb_used_hiwater=0`)
- Absence de `FOLL_LONGTERM` dans `get_user_pages()` — correctif implémenté et vérifié sur matériel réel, sans amélioration

Le fait resté acquis jusqu'au 3ᵉ essai était que `CmaFree` seul baissait après le premier chargement, alors que `MemAvailable` restait sain. Cela avait alors été interprété comme une non-libération, mais un essai unique ne permet pas de distinguer « perte de mémoire disponible » et « conversion de pages CMA movable en cache de pages ». Le 4ᵉ essai a repris les essais depuis un `CmaFree` bas et mesuré la faisabilité réelle du chargement, la baisse nette lors des répétitions, la RSS et les échecs d'allocation CMA pour corriger l'évaluation.

---

## 8. 4ᵉ essai : contre-essai A/B vanilla / `FOLL_LONGTERM` et confirmation de l'évaluation erronée (2026-08-17)

### 8.1 Objets de comparaison

- Version corrigée `FOLL_LONGTERM` : `pin_user_pages(FOLL_LONGTERM)` / `unpin_user_page()`, `srcversion=C84A00ABB326748A1832CE1` au chargement
- Version vanilla officielle 5.4.0 : tag `v5.4.0`, commit `b6dd17c609504e648eb516ff4a867167edf56f3c`, `get_user_pages()` / `put_page()`, `srcversion=A260C39C9F2C06DD4FB072E` au chargement
- Kernel : `6.18.39+rpt-rpi-2712`
- HEF : `Qwen3-1.7B-Instruct.hef` (2 880 748 478 octets)

### 8.2 Deux chargements consécutifs dans des processus indépendants

| Driver | Essai | baseline | chargé | après exit | variation par rapport à la baseline | Chargement |
|---|---:|---:|---:|---:|---:|---|
| `FOLL_LONGTERM` | 1 | 338 Mo | 34 Mo | 25 Mo | **-313 Mo (baisse)** | réussi |
| `FOLL_LONGTERM` | 2 | 5 Mo | 6 Mo | 7 Mo | **+2 Mo (hausse)** | réussi |
| vanilla | 1 | 376 Mo | 99 Mo | 112 Mo | **-264 Mo (baisse)** | réussi |
| vanilla | 2 | 125 Mo | 118 Mo | 124 Mo | **-1 Mo (baisse)** | réussi |

Pour les deux drivers, seule la première fois `CmaFree` a fortement baissé ; à partir de cette valeur basse, le second chargement a réussi avec une baisse nette quasi nulle. Comme l'ancien diagnostic ne jugeait qu'en fonction de « la quantité récupérée par rapport à la quantité consommée pendant le chargement », il classait à tort en `FAIL` des cas normaux tels que le deuxième essai, où `CmaFree` était déjà bas dès le départ.

### 8.3 Génération, libération et rechargement au sein d'un même processus

| Indicateur | `FOLL_LONGTERM` | vanilla, 1ʳᵉ fois | vanilla, répétition à CMA bas |
|---|---:|---:|---:|
| Générations terminées | 20/20 | 20/20 | 20/20 |
| 1ᵉʳ chargement | réussi | réussi | réussi |
| 2ᵉ chargement après libération | réussi | réussi | réussi |
| `CmaFree` génération 1→20 | 464→1 648 kB | 115 376→123 728 kB | 82 320→83 296 kB |
| `MemAvailable` génération 1→20 | 6 706 208→6 788 432 kB | 6 830 352→6 910 560 kB | 6 871 504→6 906 368 kB |
| RSS pendant la génération | fixe à 63 888 kB | 63 904 à 63 920 kB | 63 936 à 63 952 kB |
| Échecs d'allocation CMA | 0 | 0 | 0 |

La répétition vanilla à CMA bas a débuté avec `CmaFree=87,424 kB` ; immédiatement après libération complète, il était à 79 520 kB, puis remonté à 87 344 kB (différence nette de 80 kB). Aucun comportement de perte cumulative n'a été observé en répétant chargement, génération et libération. Le fait que `nr_foll_pin_*` soit à 0 pour vanilla vient simplement de la non-utilisation de l'API `FOLL_PIN` ; cette valeur ne peut donc pas servir à comparer le succès de la libération du pin.

### 8.4 Interprétation de la baisse initiale

Entre l'état juste après redémarrage de la version vanilla et l'ensemble des contre-essais, `Cached` est passé d'environ 1 845 872 kB à environ 4 988 224 kB, tandis que `MemAvailable` s'est maintenu entre 7 071 280 kB et environ 6 962 816 kB. Cette augmentation correspond à la lecture du HEF de plusieurs Go, ce qui permet d'expliquer la baisse initiale de `CmaFree` non pas comme une perte de mémoire inaccessible, mais comme une utilisation en cache de pages libres incluant des pages CMA movable.

### 8.5 Conclusion opérationnelle

1. Le chargement de modèle ne doit pas être rejeté sur la seule valeur absolue de `CmaFree`. Sur matériel réel, le chargement de Qwen a réussi même à partir de moins de 1 Mo.
2. Un `CmaFree` bas doit être enregistré comme télémétrie ; c'est l'erreur réelle d'allocation mémoire renvoyée par HailoRT qui doit servir de critère d'échec.
3. La valeur observée de `CmaFree`, l'échec réel de chargement et le diagnostic de fuite ne doivent pas être confondus ; ils doivent être traités selon les trois états suivants.

| État | Condition de jugement | Traitement produit | Redémarrage / enquête |
|---|---|---|---|
| `INCONCLUSIVE` | Uniquement une baisse initiale, moins de 3 fois, ou ne remplissant pas les conditions de `FAIL` ci-dessous | Enregistrer la télémétrie et tenter le chargement. Ne pas rejeter sur la seule base d'un `CmaFree` bas | Pas de redémarrage. Ajouter des mesures dans les mêmes conditions |
| `OPERATIONAL_FAIL` | HailoRT a effectivement renvoyé une erreur réelle d'allocation de mémoire hôte | Ne considérer en échec que cette demande de chargement précise ; arrêter les workloads Hailo inutiles et réessayer | Pas de redémarrage pour un cas isolé. Suivre la politique opérationnelle seulement si l'échec réel se répète et ne se rétablit pas même après libération des workloads. La Phase 0.5 actuelle se limite à l'enregistrement de `would_fire`, sans redémarrage automatique |
| `FAIL` | Répétition de la même condition 3 fois depuis un état à CMA bas, avec une baisse nette par rapport à la baseline après libération dépassant **10 Mo pour au moins 2 essais sur 3**, une somme des baisses nettes positives sur les 3 essais dépassant **20 Mo**, et accompagnée d'une augmentation monotone de la RSS ou d'une baisse de `MemAvailable` de plus de **128 Mo** | Enregistrer séparément comme diagnostic de fuite, distinct de la faisabilité individuelle de chargement | Reprendre l'enquête côté kernel / HailoRT et recueillir des preuves directes. Le seul établissement du diagnostic ne déclenche pas de redémarrage automatique |

Ce critère à 3 répétitions est destiné aux diagnostics futurs et n'est pas appliqué rétroactivement à §8.2, où les essais en processus indépendants n'ont été menés que 2 fois par driver. La conclusion du 4ᵉ essai combine l'A/B de §8.2 avec les 20 générations/libérations/rechargements au sein d'un même processus et la répétition à CMA bas de §8.3.
4. Le remplacement par `FOLL_LONGTERM` reste une bonne pratique générale de l'API DMA de Linux, mais n'a montré aucun effet sur ce problème ; le matériel réel a été restauré vers la version vanilla officielle 5.4.0.
5. Le déclenchement de redémarrage automatique ne doit jamais reposer sur `CmaFree` bas seul ; l'observation d'un échec réel de chargement est une condition obligatoire.

---

## 9. Actions à venir (au 2026-08-17)

1. L'examen du correctif `FOLL_LONGTERM` et sa réfutation sur matériel réel sont achevés. Le diff et la méthode de restauration permettant de reproduire l'expérience sont conservés en annexe B, et ne sont pas appliqués au driver de production.
2. **Le produit est déjà corrigé** : `core/hailo_device_core/device_manager_genai.py::acquire_genai` a été modifié en v4.620.8 pour continuer le chargement réel même lorsque `CmaFree` est inférieur au besoin estimé, en enregistrant `acquire_low_cma_observed`. Seule une erreur réelle de mémoire hôte renvoyée par la factory HailoRT est désormais enregistrée dans le tracker de rejet, et `tests/test_hailo_cma_false_positive.py` fixe ce comportement de poursuite du chargement depuis une valeur basse.
3. La mention de l'ancien brouillon forum, selon laquelle un `LLM(...)` ultérieur aurait été rejeté par HailoRT pour CMA hôte insuffisante, a été réauditée dans les logs et l'ancienne implémentation. La session PID 3237 citée en référence ne contient aucun enregistrement d'acquisition après release, et tous les rejets pour CMA bas traçables ce jour-là dans les logs étaient l'événement interne propre `acquire_rejected_low_cma`, survenant avant tout appel à HailoRT. L'échec ayant atteint la factory dans une session distincte était de status 8 (`HAILO_INTERNAL_FAILURE`), et non le status 3 correspondant à une erreur de mémoire hôte. Il n'existe donc aucune preuve HailoRT OOM confirmant l'ancienne mention ; `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md` sera formellement retiré, en précisant qu'un rejet propre au garde-fou interne avait été mêlé au rapport.
4. La publication corrective intégrera dans un unique brouillon actuel les chiffres et le champ d'application de §8, la correction du garde-fou d'implémentation, la réfutation de `FOLL_LONGTERM` et les avertissements d'instrumentation, sans conserver l'ancien brouillon en anglais sous une forme copiable.
5. L'enquête côté kernel / HailoRT sur la fuite ne sera reprise que si un échec réel de chargement ou une perte cumulative de mémoire disponible à chaque répétition venait à se reproduire. Le cas échéant, des preuves directes seront recueillies via `page_owner`, les informations de débogage CMA, le status d'échec d'allocation, la RSS, `MemAvailable`, etc.

---

## Annexe A. Procédure de restauration vers v5.3.0

Après un `remove --all` unique depuis dkms, la restauration échoue avec `apt-get install --reinstall` si aucun `.deb` ne subsiste dans le cache apt (échec constaté ici aussi : « impossible de réinstaller car le téléchargement n'est pas possible »). Comme dpkg continue de reconnaître le paquet `hailort-pcie-driver` comme `ii` (installé), l'arbre dkms peut être reconstruit manuellement à partir de la destination d'extraction source du paquet `/usr/src/hailort-pcie-driver/`, tant qu'elle n'a pas disparu :

```bash
sudo rmmod hailo1x_pci

sudo rm -rf /usr/src/hailo1x_pci-5.3.0
sudo cp -r /usr/src/hailort-pcie-driver /usr/src/hailo1x_pci-5.3.0
sudo sed 's/@PCIE_DRIVER_VERSION@/5.3.0/' \
  /usr/src/hailo1x_pci-5.3.0/linux/pcie/dkms.conf.in \
  | sudo tee /usr/src/hailo1x_pci-5.3.0/linux/pcie/dkms.conf > /dev/null

# dkms.conf doit être placé directement à la racine de l'arbre (une erreur survient s'il reste sous linux/pcie/)
sudo cp /usr/src/hailo1x_pci-5.3.0/linux/pcie/dkms.conf /usr/src/hailo1x_pci-5.3.0/dkms.conf

sudo dkms add -m hailo1x_pci -v 5.3.0
sudo dkms build -m hailo1x_pci -v 5.3.0 -k $(uname -r)
sudo dkms install -m hailo1x_pci -v 5.3.0 -k $(uname -r) --force
sudo depmod -a
sudo modprobe hailo1x_pci
sudo udevadm trigger --subsystem-match=hailo1x
```

Vérification de la restauration :

```bash
cat /sys/module/hailo1x_pci/version   # → 5.3.0
hailortcli fw-control identify        # → réponse normale = restauration terminée
```

---

## Annexe B. Conservation, application et restauration vanilla du patch de pilote pour l'expérience de réfutation

### B.1 Objet conservé et positionnement

Le diff de pilote effectivement utilisé pour l'A/B a été conservé tel quel dans le fichier suivant.

- `docs/development/patches/hailo1x_pci-5.4.0-foll-longterm-cma-debug-experiment.patch`
- SHA-256 : `7b5c4027f37432dbbbe39e4bdec2f0f5e8dd87e133473b5a44c44b1e86c5503f`
- Source de référence : `hailo-ai/hailort-drivers` tag `v5.4.0`, commit `b6dd17c609504e648eb516ff4a867167edf56f3c`
- Fichiers concernés : `linux/vdma/ioctl.c`, `linux/vdma/memory.c`, `linux/vdma/vdma.c`

Ce patch ne se limite pas au remplacement par `pin_user_pages(FOLL_LONGTERM)` / `unpin_user_page()` ; il inclut aussi l'instrumentation `CMA_DBG` utilisée en §7.1. Il s'agit donc d'un **diff complet à visée de vérification**, destiné à reproduire le module expérimental utilisé lors de l'A/B, et non d'un patch recommandé pour la production. L'expérience n'ayant révélé aucun effet, le matériel réel a déjà été restauré vers le vanilla officiel 5.4.0. La bibliothèque HailoRT en espace utilisateur n'a subi aucune modification.

Les valeurs d'identification relevées dans le même environnement (noyau, source, build) sont les suivantes.

| État | `srcversion` |
|---|---|
| Patch expérimental | `C84A00ABB326748A1832CE1` |
| Vanilla officiel 5.4.0 | `A260C39C9F2C06DD4FB072E` |

### B.2 Vérification avant application

Ce qui suit ne doit être exécuté que si `/usr/src/hailo1x_pci-5.4.0` sur le Raspberry Pi pointe bien vers le commit officiel ci-dessus et si aucune modification locale n'affecte les 3 fichiers concernés. Si le commit, la somme de contrôle du patch ou la somme de contrôle du `memory.c` vanilla ne correspondent pas, il faut s'arrêter et ne jamais forcer l'application du patch.

```bash
set -euo pipefail

REPO=/home/pi/GitHub/yu_ai_manager
SRC=/usr/src/hailo1x_pci-5.4.0
PATCH="$REPO/docs/development/patches/hailo1x_pci-5.4.0-foll-longterm-cma-debug-experiment.patch"
EXPECTED_HEAD=b6dd17c609504e648eb516ff4a867167edf56f3c
EXPECTED_PATCH_SHA=7b5c4027f37432dbbbe39e4bdec2f0f5e8dd87e133473b5a44c44b1e86c5503f
EXPECTED_MEMORY_SHA=85d564acaa70cdb41eb18bad35ad958d3b2af168ae03c17466976cbe64b1e58c

test "$(sudo git -c safe.directory="$SRC" -C "$SRC" rev-parse HEAD)" = "$EXPECTED_HEAD"
printf '%s  %s\n' "$EXPECTED_PATCH_SHA" "$PATCH" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_MEMORY_SHA" "$SRC/linux/vdma/memory.c" | sha256sum -c -
sudo git -c safe.directory="$SRC" -C "$SRC" diff --exit-code -- \
  linux/vdma/ioctl.c linux/vdma/memory.c linux/vdma/vdma.c
sudo git -c safe.directory="$SRC" -C "$SRC" apply --check "$PATCH"
```

### B.3 Application du patch expérimental

Uniquement si toutes les vérifications ont réussi, le patch est appliqué et le module DKMS installé pour le prochain démarrage. Ne pas échanger manuellement le module chargé via `rmmod` / `modprobe` ; effectuer la bascule par un redémarrage normal après le build.

```bash
set -euo pipefail

SRC=/usr/src/hailo1x_pci-5.4.0
PATCH=/home/pi/GitHub/yu_ai_manager/docs/development/patches/hailo1x_pci-5.4.0-foll-longterm-cma-debug-experiment.patch
KERNEL_VERSION="$(uname -r)"

sudo git -c safe.directory="$SRC" -C "$SRC" apply "$PATCH"
sudo dkms build -m hailo1x_pci -v 5.4.0 -k "$KERNEL_VERSION" --force
sudo dkms install -m hailo1x_pci -v 5.4.0 -k "$KERNEL_VERSION" --force
sudo depmod -a "$KERNEL_VERSION"

modinfo -n hailo1x_pci
modinfo -F srcversion hailo1x_pci
head -n 1 /sys/module/hailo1x_pci/srcversion
```

`modinfo` indique le module installé pour le prochain démarrage, tandis que `/sys/module/.../srcversion` indique le module actuellement chargé. Il est normal que les valeurs diffèrent à ce stade. Une fois prêt, redémarrer et vérifier après le démarrage que les deux valeurs concordent.

```bash
sudo reboot

# après reconnexion
modinfo -F srcversion hailo1x_pci
head -n 1 /sys/module/hailo1x_pci/srcversion
```

Dans le même environnement de vérification, la valeur attendue après application du patch est `C84A00ABB326748A1832CE1`. En cas de valeur différente, ne pas poursuivre les essais par supposition ; vérifier le diff source, le noyau et les journaux de build DKMS.

### B.4 Restauration vers le vanilla officiel 5.4.0

La restauration ne repose pas sur l'application inverse du patch ; les 3 fichiers concernés sont explicitement restaurés depuis le commit vérifié. Cela évite un état où l'application serait partielle ou où seule l'instrumentation subsisterait.

```bash
set -euo pipefail

SRC=/usr/src/hailo1x_pci-5.4.0
EXPECTED_HEAD=b6dd17c609504e648eb516ff4a867167edf56f3c
EXPECTED_MEMORY_SHA=85d564acaa70cdb41eb18bad35ad958d3b2af168ae03c17466976cbe64b1e58c
KERNEL_VERSION="$(uname -r)"

test "$(sudo git -c safe.directory="$SRC" -C "$SRC" rev-parse HEAD)" = "$EXPECTED_HEAD"
sudo git -c safe.directory="$SRC" -C "$SRC" restore --source="$EXPECTED_HEAD" -- \
  linux/vdma/ioctl.c linux/vdma/memory.c linux/vdma/vdma.c
sudo git -c safe.directory="$SRC" -C "$SRC" diff --exit-code -- \
  linux/vdma/ioctl.c linux/vdma/memory.c linux/vdma/vdma.c
printf '%s  %s\n' "$EXPECTED_MEMORY_SHA" "$SRC/linux/vdma/memory.c" | sha256sum -c -

sudo dkms build -m hailo1x_pci -v 5.4.0 -k "$KERNEL_VERSION" --force
sudo dkms install -m hailo1x_pci -v 5.4.0 -k "$KERNEL_VERSION" --force
sudo depmod -a "$KERNEL_VERSION"

modinfo -F srcversion hailo1x_pci
head -n 1 /sys/module/hailo1x_pci/srcversion
```

Dans le même environnement de vérification, la valeur attendue pour le module vanilla installé est `A260C39C9F2C06DD4FB072E`. Après avoir confirmé que la valeur actuellement chargée diffère, redémarrer, puis vérifier après reconnexion que les deux valeurs sont bien `A260C39C9F2C06DD4FB072E`.

---

## Référence : documents liés

- `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md` — données de mesure de la fuite CMA basées sur l'ancienne mesure, script de reproduction, brouillon de publication forum (conclusion corrigée au §8 du présent document)
- [HAILORT_5_3_0_MIGRATION.md](HAILORT_5_3_0_MIGRATION.md) — enregistrement de la migration v5.2.0 → v5.3.0 (changement de nom du nœud de périphérique vers `/dev/h1x-0`, etc.)
- [HAILO_CMA_LEAK_HAILORT_5_3_0.md](HAILO_CMA_LEAK_HAILORT_5_3_0.md) — enregistrement en japonais du problème de fuite CMA basé sur l'ancien diagnostic (conclusion corrigée au §8 du présent document)
- Dépôt GitHub `hailo-ai/hailort-drivers` (GPL-2.0, source publique) : <https://github.com/hailo-ai/hailort-drivers>
