# Hailo-10H AI Hat+ — Documentation de développement

Enregistrement d'implémentation d'inférence AI avec Raspberry Pi 5 + Hailo AI Hat+ (Hailo-10H).

Connaissances acquises lors du développement réel dans des domaines insuffisamment documentés officiellement, partagées publiquement.

## Liste des documents

| Fichier | Contenu |
|---------|------|
| [HAILORT_5_3_0_MIGRATION.md](HAILORT_5_3_0_MIGRATION.md) | Notes de migration HailoRT 5.2.0 → 5.3.0. Diff d'API, renommage du nœud de périphérique (`/dev/h1x-0`), compatibilité HEF, script de test de fumée |
| [VDEVICE_SHARING_PATTERN.md](VDEVICE_SHARING_PATTERN.md) | Pattern d'implémentation du gestionnaire VDevice partagé pour faire coexister plusieurs modèles (YOLO/CLIP/LLM/VLM/Whisper) dans le même processus |
| [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md) | Limitations d'allocation CMA du Pi 5 (comportement sous `numa=fake=8`). Pourquoi `cma=1G` échoue silencieusement, `cma-512` (`dtoverlay=cma,cma-512` dans `config.txt`) en tant que plafond confirmé et valeur recommandée, exigences mémoire de Hailo GenAI, comportement de non-retour de la CMA par `VDevice.release()` |
| [HAILO_SEMANTIC_SEARCH_DEVLOG.md](HAILO_SEMANTIC_SEARCH_DEVLOG.md) | Journal de développement de la recherche sémantique CLIP. Enregistrement d'implémentation par phase, problèmes rencontrés et solutions |
| [HAILO_DEVICE_CONTROL.md](HAILO_DEVICE_CONTROL.md) | Méthode de contrôle du périphérique Hailo, gestion VDevice, contrôle exclusif, commutation de modèles |
| [ONNX_TO_HEF_CONVERSION_GUIDE.md](ONNX_TO_HEF_CONVERSION_GUIDE.md) | Procédure de conversion ONNX → HEF. Dataflow Compiler, quantification, dépannage |
| [ONNX_TO_HEF_CONVERSION_REPORT.md](ONNX_TO_HEF_CONVERSION_REPORT.md) | Rapport de vérification de conversion (DFC v5.2.0). Analyse détaillée des échecs pour 3 variantes de WD-Tagger |
| [WD_TAGGER_DFC_5_3_0_FOLLOWUP.md](WD_TAGGER_DFC_5_3_0_FOLLOWUP.md) | Suivi DFC v5.3.0. Nouvelle vérification des mêmes 3 modèles WD-Tagger (toujours en échec), plus les améliorations confirmées dans v5.3.0 (nouveau `_create_layer_normalization_layer`, flux de réessai onnxsim, recommandation end-node) |
| [CLIP_ONNX_DEVLOG.md](CLIP_ONNX_DEVLOG.md) | Journal de développement CLIP ONNX multi-backend. Fallback pour les environnements sans matériel Hailo |
| [HAILO_CMA_LEAK_HAILORT_5_3_0.md](HAILO_CMA_LEAK_HAILORT_5_3_0.md) | **Contrainte structurelle de la fuite CMA et mesures**. Le fait que `VDevice.release()` ne récupère pas la CMA, la fuite continue pendant l'inférence (environ 14 Mo/min), et le fait que **ni le kill du processus enfant, ni la sortie du processus, ni le déchargement du module ne permettent la récupération** (mesuré indépendamment à 2 reprises lors du PoC Phase 0, seulement +8 Mo après SIGTERM + 30 secondes d'attente). Le seul moyen de récupération fiable est le redémarrage du Pi **(ancienne conclusion. Corrigée au §8 de [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) suite au nouvel essai sur HailoRT / driver 5.4.0)** |
| [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) | **Correction et nouvelle vérification du jugement de fuite CMA ci-dessus**. Comparaison A/B entre le vanilla officiel et la version corrigée `FOLL_LONGTERM` sur HailoRT / driver 5.4.0, corrigeant l'ancien jugement qui n'avait observé que la quantité de récupération absolue de `CmaFree` après le premier chargement HEF. Inclut le diff source v5.3.0 → v5.4.0, les pièges de la procédure de build maison, et les données mesurées |
| [HAILO_AUTO_REBOOT_PHASE05.md](HAILO_AUTO_REBOOT_PHASE05.md) | Guide opérationnel de la voie de redémarrage automatique adoptée suite à ce qui précède. Phase d'observation (n'enregistre que `would_fire` sans redémarrer), seuils de décision, raison du `mode = "off"` par défaut |
| [HAILO_AUTO_REBOOT_PHASE05_RUNBOOK.md](HAILO_AUTO_REBOOT_PHASE05_RUNBOOK.md) | Runbook pour cet environnement pour la même phase. Procédures de démarrage, de vérification et de clôture de l'observation |
| [HAILO_LLM_SUBPROCESS_DEVLOG.md](HAILO_LLM_SUBPROCESS_DEVLOG.md) | Journal d'implémentation résolvant le blocage de la boucle d'événements Quart par le GIL pendant le cold_load (~71 secondes), via l'isolation en subprocess de l'inférence de chat LLM |
| [HAILO_10H_ECOSYSTEM_ASSESSMENT.md](HAILO_10H_ECOSYSTEM_ASSESSMENT.md) | Évaluation de l'écosystème Hailo-10H (au 2026-03-19, HailoRT/DFC v5.2.0) |

## Éléments importants connus

### Environnement / Raspberry Pi 5

- **Limite CMA de 512 Mo sur Pi 5 (8 Go), à configurer dans `config.txt`** : Le kernel par défaut applique `numa=fake=8`, divisant la RAM en 8 × 1 Go de nœuds NUMA. La CMA doit tenir dans les limites d'un seul nœud, et `cma-1024` ainsi que `cma-768` échouent silencieusement (`CmaTotal=0`, sans panique kernel). **`cma-512` est le plafond confirmé et la valeur recommandée** (revérifié le 2026-05-16 via overlay, `CmaTotal: 524288 kB`). En raison d'une régression du firmware de 2026-05, utiliser `dtoverlay=cma,cma-512` dans `/boot/firmware/config.txt` plutôt que `cma=` en cmdline. Voir [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md) pour les détails
- **Toujours vérifier CMA après redémarrage** : Confirmer avec `grep CmaTotal /proc/meminfo`. Si 0, la configuration a été ignorée
- **`VDevice.release()` ne récupère pas la CMA** : La CMA est conservée pour toute la session OS. Traiter VDevice comme un singleton de portée session. **N'est pas récupérée même après un redémarrage de processus** — il a été mesuré indépendamment à 2 reprises lors du PoC Phase 0 que ni le kill du processus enfant, ni la sortie du processus, ni le déchargement du module ne permettent la récupération (seulement +8 Mo après SIGTERM + 30 secondes d'attente, contre une valeur attendue ≥250 Mo). Le seul moyen de récupération fiable est un `sudo reboot` du Pi lui-même (cycle d'alimentation PCIe). Voir [HAILO_CMA_LEAK_HAILORT_5_3_0.md](HAILO_CMA_LEAK_HAILORT_5_3_0.md) pour les détails et la solution adoptée. **Correction** : ce point repose sur une ancienne mesure. Le nouvel essai A/B sur HailoRT / driver 5.4.0 n'a pas reproduit de fuite CMA en usage réel, corrigé au §8 de [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md)
- **`numa=fake=8` affecte l'installation Node.js** : La mémoire par nœud NUMA (1 GB) est mal reconnue comme RAM totale, et les installeurs npm/node s'arrêtent. Signalé upstream : [anthropics/claude-code#33864](https://github.com/anthropics/claude-code/issues/33864)
- **Wheel Python nécessite un build depuis les sources** : Pas de wheel aarch64 ni sur PyPI ni dans la Hailo Developer Zone
- **Exclusivité avec hailo-ollama** : Besoin d'arrêter hailo-ollama pendant l'utilisation de VDevice
- **Fuite VDevice à la fin du processus** : Vérifier avec `lsof /dev/hailo*` et traiter avec `kill PID`

### VDevice / API

- **Utiliser l'API InferModel** : `VDevice.create_infer_model()` est correct. L'ancienne API VStreams (`InferVStreams`, `ConfigureParams.create_from_hef`) retourne `HAILO_NOT_IMPLEMENTED` sur Hailo-10H
- **InferModel ne supporte que les modèles simples** : Les HEF YOLO à 1 entrée fonctionnent, mais les HEF Whisper à 2 entrées 4 sorties retournent `HAILO_INVALID_ARGUMENT` dans `configure()`. Utiliser le GenAI SDK pour les modèles complexes
- **VDevice mappe 1 périphérique physique** : Créer 2 instances `VDevice()` simultanément → `HAILO_OUT_OF_PHYSICAL_DEVICES(74)`
- **Libération complète de VDevice lors de la commutation de modèles** : Mettre juste la référence Python à `None` est insuffisant. Libérer explicitement le périphérique physique avec `VDevice.release()` avant de créer un nouveau VDevice
- **`set_format_type(FormatType.FLOAT32)` non supporté dans hailort 5.2.0** : L'attribut `format_type` n'existe pas. Quantifier/déquantifier manuellement en uint8 ou utiliser le GenAI SDK
- **La sortie est quantifiée en uint8** : Allouer le buffer de sortie en float32 → `buffer size mismatch`. Allouer en uint8 et convertir en float32 avec les paramètres de déquantification (scale, zero_point)

### GenAI (LLM / VLM / Speech2Text)

- **`temperature=0.0` refusé dans HailoRT 5.3.0** : `LLM.generate()` lève `HAILO_INVALID_ARGUMENT` avec `temperature=0`. Clamper avant l'appel : `temperature = max(temperature, 0.01)`. Affecte quand les clients compatibles OpenAI envoient `temperature=0` par défaut
- **Chargement simultané de 2 GenAI possible** : LLM + Whisper-tiny peuvent être chargés simultanément sur le même VDevice (confirmé dans HailoRT 5.3.0). Marge CMA lors du chargement des deux : environ 10 MB sur 256 MB. Risque de dépassement mémoire pour Whisper-base et supérieur
- **Budget CMA LLM + Whisper-tiny** : Total ~246 MB (mesuré). Voir [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md) pour tous les chiffres CMA des modèles

### Whisper (reconnaissance vocale)

- **Utiliser le GenAI SDK** : `hailo_platform.genai.Speech2Text` fournit le pipeline complet. Exécution encodeur+décodeur entièrement sur NPU
- **Le HEF est uniquement le décodeur** : `Whisper-Base.hef` a 2 entrées (encoder_features + token_embeddings) et 4 sorties (vocabulaire divisé en 4). Ne fonctionne pas avec l'API InferModel
- **Entrée du GenAI SDK** : Données audio PCM float32 little-endian (`<f4`), normalisées [-1,1]
- **Fallback ONNX** : Si le GenAI SDK n'est pas disponible, exécuter encodeur+décodeur sur CPU avec les modèles ONNX de HuggingFace

### YOLO (détection d'objets)

- **Fonctionne avec l'API InferModel** : Les HEF à 1 entrée fonctionnent sans problème
- **Fallback ONNX** : Si Hailo n'est pas disponible, `yolo11n.onnx` est téléchargé automatiquement. La sortie `(1,84,8400)` est compatible avec yolov8n
- **Délai de refroidissement après échec d'initialisation** : Pas de réessai pendant 60 secondes après un échec d'initialisation du moteur

### Inférence distribuée

- **Vérification de santé requise** : Confirmer la vie/mort des nœuds distants avec `filter_available()` avant de démarrer la distribution
- **En cas de panne distante** : Fallback des éléments restants en local. Détection automatique au prochain batch lors du rétablissement
- **Distribution de charge de travail** : La grande différence de vitesse entre GPU et NPU rend la division égale inefficace. La distribution dynamique basée sur la mesure de débit est un défi futur
