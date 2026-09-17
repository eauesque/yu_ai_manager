# Évaluation de l'écosystème Hailo-10H

**Date de création** : 2026-03-19  
**Cible** : Hailo-10H (AI HAT 2 pour Raspberry Pi 5)  
**HailoRT** : v5.2.0  
**DFC** : v5.2.0  
**Objectif** : Documenter l'expérience de développement Hailo-10H dans ce projet et clarifier les contraintes réelles ainsi que les perspectives futures

---

## Évaluation globale

**Le matériel est excellent. L'écosystème logiciel est décisivement insuffisant.**

Le Hailo-10H est un NPU avec 40 TOPS de performances d'inférence et le potentiel matériel est suffisant. Cependant, en raison de la fermeture et de l'immaturité de la chaîne d'outils logiciels, il est **pratiquement impossible** pour les développeurs d'apporter et de faire fonctionner librement leurs propres modèles.

Dans ce projet, nous avons développé une utilisation multifacette du Hailo-10H pour la recherche sémantique CLIP, la détection d'objets YOLO, le chat LLM/VLM, la reconnaissance vocale Whisper et les serveurs de tagging distribués, mais tout ce qui fonctionne de manière stable **utilise des HEF précompilés téléchargés depuis le Hailo Model Zoo officiel**, et il n'y a **pas un seul exemple** où nous avons pu convertir avec succès nos propres modèles de ONNX en HEF.

---

## État de l'implémentation dans ce projet

### Fonctionnalités qui marchent (toutes avec téléchargement de HEF officiel)

| Fonctionnalité | API utilisée | Source HEF |
|------|---------|-----------|
| Encodeur d'image CLIP | `VDevice.create_infer_model()` | Hailo Model Zoo (S3) |
| Détection d'objets YOLO | `VDevice.create_infer_model()` | Hailo Model Zoo (S3) |
| Chat LLM | `hailo_platform.genai.LLM` | Hailo GenAI Model Zoo |
| Inférence image+texte VLM | `hailo_platform.genai.VLM` | Hailo GenAI Model Zoo |
| Reconnaissance vocale Whisper | `hailo_platform.genai.Speech2Text` | Hailo GenAI Model Zoo |

### Fonctionnalités qui n'ont pas marché (échec de conversion HEF)

| Fonctionnalité | Ce qui a été essayé | Résultat |
|------|-----------|------|
| WD-Tagger (SwinV2) | Conversion ONNX → HEF | Échec : DFC ne peut pas traiter LayerNormalization |
| WD-Tagger (ViT) | Conversion ONNX → HEF | Identique |
| WD-Tagger (ConvNeXt) | Conversion ONNX → HEF | Échec : DFC ne peut pas traiter l'opération Transpose |

### Points notables de l'implémentation

Dans ce projet, toutes les fonctionnalités ont été implémentées en **appelant directement** l'API Python de la wheel `hailo_platform`. hailo-ollama et hailo-apps n'ont pas été utilisés.

En particulier, les éléments suivants ont été construits en interne avant que Hailo ne les fournisse officiellement :

- **Gestionnaire de périphériques à VDevice exclusif** — Commutation automatique entre CLIP/YOLO/LLM/VLM/S2T sur un seul VDevice. hailo-apps n'a pas de mécanisme de partage de périphérique
- **Fallback multi-backend** — Commutation transparente automatique Hailo → CoreML → ONNX Runtime
- **Pipeline de déquantification uint8** — Restauration de float32 à partir des scale/zero_point de `quant_info`
- **Architecture d'inférence distribuée LAN** — Tagging parallèle work-stealing sur plusieurs machines

Ces développements ont été réalisés **dans un état quasi-absence de documentation API**. Les spécifications d'entrée/sortie de l'API InferModel, les exigences de taille de buffer et la méthode d'obtention des paramètres de quantification ont tous été élucidés à partir des messages d'erreur et de déductions sur le code source.

---

## Problèmes du Hailo Dataflow Compiler (DFC)

### Qu'est-ce que le DFC

Compilateur pour convertir les modèles ONNX / TensorFlow au format HEF (Hailo Executable Format) pour Hailo-10H. Fonctionne sur x86_64 Linux, avec le pipeline de conversion suivant :

```
model.onnx → HAR (float32) → Optimisation → Quantification (INT8) → Compilation → model.hef
```

### La réalité

**Le DFC ne peut convertir correctement que les architectures que Hailo a pré-validées pour son propre Model Zoo.**

Tentatives de conversion dans ce projet (2026-03-06, DFC v5.2.0) :

| Modèle | Taille | Erreur | Étape atteinte |
|--------|-------|--------|---------|
| wd-swinv2-tagger-v3 | 446 MB | `IndexError` in `_convert_axes_to_nhwc` | Avant l'optimisation |
| wd-vit-tagger-v3 | 362 MB | Identique | Avant l'optimisation |
| wd-convnext-tagger-v3 | 377 MB | `UnsupportedShuffleLayerError` | Avant l'optimisation |

Les 3 modèles ont tous échoué **au niveau du parser avant d'atteindre l'étape d'optimisation**. 500 images de calibration avaient été préparées mais n'ont jamais été utilisées.

### Cause profonde

Le parser ONNX du DFC ne peut pas traiter les opérateurs suivants :

- `LayerNormalization` (conversion d'axes pour tenseurs multidimensionnels)
- `Transpose` (patterns de conversion channels-last/first)

Ce sont des blocs de construction fondamentaux des architectures de type Transformer (SwinV2, ViT, ConvNeXt, etc.), utilisés par la grande majorité des modèles récents depuis 2022.

### Étendue de support réelle du DFC

| Architecture | Support DFC | Base |
|---------------|---------|------|
| CNN type ResNet, MobileNet | ✓ Supporté | Nombreux dans le Model Zoo |
| YOLO v5/v8/v11 | ✓ Supporté | HEF disponibles dans le Model Zoo |
| CLIP ViT (version Hailo) | ✓ Supporté | HEF dans le Model Zoo (converti par Hailo) |
| SwinTransformer V2 | ✗ Non supporté | Échec de conversion LayerNorm |
| Vision Transformer (générique) | ✗ Non supporté | Échec de conversion LayerNorm |
| ConvNeXt | ✗ Non supporté | Échec de conversion Transpose |

> **Note** : Le fait que le CLIP ViT soit dans le Model Zoo suggère probablement que Hailo fait un traitement spécial en interne (conversion manuelle de graphe ou parser personnalisé). Même ViT échoue quand des utilisateurs ordinaires essaient de le convertir avec DFC.

---

## Problèmes du format HEF

- **Spécification binaire non publique** — Hailo ne publie pas la documentation du format
- **Aucun autre moyen de génération que DFC** — Impossible de créer des HEF avec des outils tiers
- **Rétro-ingénierie également non réaliste** — Nécessite une connaissance du jeu d'instructions et de l'architecture de flux de données du NPU

En d'autres termes, les modèles que DFC ne peut pas convertir **ne peuvent pas du tout fonctionner sur Hailo-10H**. Il n'existe pas d'alternative.

---

## Évaluation de la chaîne d'outils de développement

### hailo_platform (Python SDK)

| Élément | Évaluation |
|------|------|
| API InferModel | Fonctionne mais documentation extrêmement insuffisante |
| API GenAI (LLM/VLM/S2T) | Relativement utilisable. Cependant nombreux comportements undocumented |
| Distribution wheel Python | Absent de PyPI. La wheel aarch64 nécessite un build depuis les sources |
| Messages d'erreur | Minimaux. Difficile d'identifier la cause des désaccords de taille de buffer |
| Gestion VDevice | Accès exclusif uniquement. Utilisation simultanée de plusieurs modèles impossible |

### Comportements undocumented élucidés pendant le développement

1. **L'API InferModel est correcte** — L'ancienne API VStreams (`InferVStreams`, `ConfigureParams.create_from_hef`) retourne `HAILO_NOT_IMPLEMENTED` sur Hailo-10H
2. **La sortie est quantifiée en uint8** — L'allocation de buffer en float32 donne `buffer size mismatch`. Il faut allouer en uint8 puis déquantifier
3. **`input()`/`output()` sont des propriétés** — Pas des méthodes (incohérent avec les autres API Hailo)
4. **Obtention de `quant_info`** — Les scale/zero_point sont disponibles via `infer_model.output().quant_info`, mais aucune documentation n'explique cela
5. **Exclusivité avec hailo-ollama** — Il faut arrêter hailo-ollama pendant l'utilisation de VDevice. La cause est difficile à comprendre depuis les messages d'erreur

---

## Comparaison avec les produits concurrents

### Ryzen AI (XDNA) NPU

| Élément | Hailo-10H | Ryzen AI (XDNA) |
|------|----------|-----------------|
| Performance | 40 TOPS | 16~50 TOPS (selon la génération) |
| Apporter ses propres modèles | Conversion DFC requise, généralement échoue | **ONNX Runtime prend en charge directement** |
| Expérience développeur | Chaîne d'outils propriétaire, documentation insuffisante | `pip install onnxruntime-directml` suffit |
| Écosystème | Fermé, dépendant du Model Zoo | ONNX / DirectML / collaboration Microsoft |
| Nombre d'unités | Pi + AI HAT, clé USB (prévu) | **Déjà intégré dans des millions de laptops** |

L'intégration avec Ryzen AI se résume à ceci :

```python
import onnxruntime as ort
session = ort.InferenceSession("model.onnx", providers=["DmlExecutionProvider"])
```

Impossible à faire de la même façon avec Hailo-10H. Aucun Execution Provider ONNX Runtime n'existe.

### NVIDIA CUDA

| Élément | Hailo-10H | NVIDIA CUDA |
|------|----------|-------------|
| Apporter ses propres modèles | Via DFC, généralement échoue hors Model Zoo | ONNX / PyTorch / TensorFlow → fonctionne directement |
| Chaîne d'outils | Immature, semi-fermée | Mature, ouverte, documentation abondante |
| Communauté développeurs | Très petite | La plus grande au monde |
| Gamme de prix | Bon marché (~70$) | Cher (200~2000$+) |

L'unique avantage de Hailo est le **prix et la consommation énergétique**.

---

## Relation avec hailo-apps (2025-10)

### Vue d'ensemble de hailo-apps

Collection d'applications officielles publiée par Hailo en octobre 2025. Contient plus de 20 applications exemples :

- GenAI : voice_assistant, vlm_chat, agent_tools_example, whisper
- Pipeline : détection d'objets, estimation de pose, reconnaissance faciale, classification CLIP, OCR
- Standalone : démos d'apprentissage HailoRT en Python/C++

### Comparaison avec ce projet

| Élément | hailo-apps | Ce projet |
|------|-----------|-------------|
| Support VLM | Application vlm_chat | Implémentation directe `hailo_platform.genai.VLM` |
| CLIP | Application clip | Intégré comme système de recherche sémantique |
| LLM | simple_llm_chat | Intégré comme Extension GenAI |
| Whisper | simple_whisper_chat | Intégré comme Extension Speech-to-Text |
| Gestion du périphérique | Aucune (1 application à la fois) | **Gestionnaire de périphériques exclusif (commutation auto CLIP/YOLO/LLM/VLM/S2T)** |
| Fallback backend | Aucun | **Commutation automatique Hailo → CoreML → ONNX** |
| Inférence distribuée | Aucune | **Work-stealing distribué LAN** |
| Degré d'intégration | Applications démo individuelles | Application WebUI intégrée unique |

Ce projet avait déjà implémenté des fonctionnalités équivalentes ou supérieures à hailo-apps depuis les API bas niveau de la wheel `hailo_platform` avant la publication de hailo-apps.

---

## Perspectives

### Court terme (réaliste)

- **ONNX Runtime + LAN distribué est la seule solution pratique** — Fonctionnement avec le backend ONNX du serveur de tagging distribué
- Hailo-10H limité aux usages avec des HEF officiels disponibles (YOLO, CLIP, LLM, Whisper)
- Abandon de l'exécution NPU des modèles personnalisés

### Moyen terme (espoir)

- ASUS et d'autres fabricants lancent des clés USB Hailo-10H → augmentation du nombre d'utilisateurs
- L'augmentation des utilisateurs peut mettre une pression sur Hailo pour améliorer les outils
- Possibilité que DFC ajoute le support des architectures Transformer dans des versions futures

### Long terme (défis structurels)

- À moins que Hailo fournisse un ONNX Runtime EP, il perdra face à Ryzen AI (XDNA) en termes d'écosystème développeur
- Même si le matériel se démocratise via les clés USB, sans liberté logicielle, il restera « une clé qui fait tourner YOLO rapidement »
- Le potentiel de 40 TOPS restera limité à quelques dizaines de modèles du Model Zoo

---

## Résumé

Bien que le Hailo-10H possède d'excellentes performances matérielles de 40 TOPS, la fermeture et l'immaturité de l'écosystème logiciel rendent **pratiquement impossible** pour les développeurs d'utiliser librement leurs propres modèles.

Dans ce projet, nous avons construit un logiciel d'intégration dépassant la collection officielle d'applications Hailo (hailo-apps) en élucidant à tâtons des API undocumented. Cependant, même ainsi, l'exécution NPU de modèles personnalisés (WD-Tagger) n'a pas pu être réalisée en raison des limitations de DFC.

**« Les outils sont trop insuffisants pour que le développement soit praticable »** — c'est la conclusion honnête après plusieurs mois de développement avec le Hailo-10H.

---

## Documents liés

- [`HAILO_SEMANTIC_SEARCH_DEVLOG.md`](./HAILO_SEMANTIC_SEARCH_DEVLOG.md) — Journal de développement de la recherche sémantique CLIP (Phases 1~12+)
- [`ONNX_TO_HEF_CONVERSION_GUIDE.md`](./ONNX_TO_HEF_CONVERSION_GUIDE.md) — Guide de conversion DFC (document de référence)
- [`ONNX_TO_HEF_CONVERSION_REPORT.md`](./ONNX_TO_HEF_CONVERSION_REPORT.md) — Rapport d'échec de conversion WD-Tagger
- [`CLIP_ONNX_DEVLOG.md`](./CLIP_ONNX_DEVLOG.md) — Journal de développement du fallback CLIP ONNX
- [`HAILO_DEVICE_CONTROL.md`](./HAILO_DEVICE_CONTROL.md) — Conception de gestion de périphérique VDevice
- [`../features/distributed-tagger-server.md`](../features/distributed-tagger-server.md) — Documentation du serveur de tagging distribué
