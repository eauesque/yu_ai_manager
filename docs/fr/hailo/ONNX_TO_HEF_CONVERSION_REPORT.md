# Rapport de conversion ONNX vers HEF

**Date** : 2026-03-06
**Objectif** : Convertir les modèles WD-Tagger ONNX au format Hailo HEF pour permettre l'inférence sur Raspberry Pi 5 + AI HAT 2 (Hailo-10H)
**Résultat** : Échec (conversion impossible pour toutes les variantes de modèles)

---

## Environnement

| Élément | Détails |
|------|------|
| OS | Ubuntu 24.04 (WSL2) |
| Python | 3.11.13 (installé avec uv) |
| Hailo Dataflow Compiler | v5.2.0 |
| GPU | CUDA 12.8, Driver 591 |
| RAM | 151GB |

---

## Modèles testés

### 1. wd-swinv2-tagger-v3 (SwinTransformer V2)

- **Source** : `SmilingWolf/wd-swinv2-tagger-v3` (446MB)
- **Entrée** : `[batch, 448, 448, 3]` float32
- **Sortie** : `[batch, 10861]` float32
- **Résultat** : Échec
- **Erreur** : `IndexError: list index out of range` dans `_convert_axes_to_nhwc`
- **Cause** : La conversion d'axes de LayerNormalization non supportée dans DFC v5.2.0

### 2. wd-vit-tagger-v3 (Vision Transformer)

- **Source** : `SmilingWolf/wd-vit-tagger-v3` (362MB)
- **Entrée** : `[batch, 448, 448, 3]` float32
- **Sortie** : `[batch, 10861]` float32
- **Résultat** : Échec
- **Erreur** : Identique (`IndexError` dans `_convert_axes_to_nhwc`)
- **Cause** : ViT utilise également LayerNormalization, échec au même endroit

### 3. wd-convnext-tagger-v3 (ConvNeXt)

- **Source** : `SmilingWolf/wd-convnext-tagger-v3` (377MB)
- **Entrée** : `[batch, 448, 448, 3]` float32
- **Sortie** : `[batch, 10861]` float32
- **Résultat** : Échec
- **Erreur** : `UnsupportedShuffleLayerError` (nombreux nœuds Transpose) + `UnsupportedModelError` (incompatibilité de shape pour Mul)
- **Cause** : Les opérations Transpose liées à la conception channels-last de ConvNeXt ne sont pas supportées par DFC

---

## Cause profonde de l'échec

Le parser ONNX de DFC v5.2.0 ne peut pas traiter correctement les opérations suivantes :

1. **LayerNormalization** : Erreur d'index lors de la conversion d'axes NHWC pour LayerNorm sur des tenseurs 3D et supérieurs
2. **Transpose (Shuffle)** : Pattern Transpose utilisé pour les conversions channels-last/first de ConvNeXt non supporté

Toutes les variantes de WD-Tagger (SwinV2, ViT, ConvNeXt) sont des architectures modernes qui utilisent largement LayerNormalization, impossibles à convertir avec DFC v5.2.0.

---

## Données de calibration

- 500 images sélectionnées aléatoirement parmi les sorties de ComfyUI / Stable Diffusion forge
- Même pré-traitement que WD-Tagger (RGBA→RGB composite blanc, redimensionnement conservation ratio, padding blanc, conversion BGR) appliqué
- Sauvegardées en `calibration_data.npy`, mais non utilisées car l'étape de conversion n'a pas été atteinte

---

## Possibilités futures

- **Versions futures de DFC** : Vaut la peine de réessayer si Hailo améliore le support de LayerNormalization / Transpose
- **Modification de modèle** : Création d'un modèle modifié remplaçant LayerNorm par BatchNorm (effort important, risque de dégradation de précision)
- **Maintien du statu quo** : Continuer l'inférence avec ONNX Runtime (CPU)
