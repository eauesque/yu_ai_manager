# Suivi DFC : Nouvelle vérification des modèles WD-Tagger avec DFC v5.3.0

**Date** : 2026-04-06
**Version DFC** : 5.3.0
**Rapport précédent** : [`ONNX_TO_HEF_CONVERSION_REPORT.md`](ONNX_TO_HEF_CONVERSION_REPORT.md) (2026-03-06)
**Environnement** : WSL2 (Ubuntu 24.04), x86_64

---

## Contexte

En mars 2026, nous avons rapporté que les 3 variantes de WD-Tagger (SwinV2, ViT, ConvNeXt) échouaient toutes au niveau du parsing avec le Hailo Dataflow Compiler v5.2.0, sans jamais atteindre l'étape de quantification. Le rapport original est sauvegardé dans [`ONNX_TO_HEF_CONVERSION_REPORT.md`](ONNX_TO_HEF_CONVERSION_REPORT.md).

DFC v5.3.0 ayant été publié, voici les résultats de la nouvelle vérification des mêmes 3 modèles.

---

## Résumé des résultats

| Modèle | Taille | Erreur DFC 5.2.0 | Erreur DFC 5.3.0 | Changement |
|---|---|---|---|---|
| `wd-swinv2-tagger-v3` | 446 MB | `IndexError` dans `_convert_axes_to_nhwc` | Identique | **Aucun** |
| `wd-vit-tagger-v3` | 362 MB | Identique | Identique (même après réessai onnxsim) | Ajout du flux de réessai uniquement |
| `wd-convnext-tagger-v3` | 377 MB | `UnsupportedShuffleLayerError` | Identique + `UnsupportedModelError` ajouté | **Les erreurs ont augmenté** |

**Les 3 modèles échouent toujours au niveau du parsing**. Les 500 images de calibration préparées ne peuvent toujours pas être utilisées, comme avec v5.2.0.

---

## Ce qui a changé dans DFC v5.3.0

Bien que les échecs persistent, les améliorations suivantes sont visibles par rapport à v5.2.0 :

### 1. Nouvelle méthode `_create_layer_normalization_layer`

Cette méthode n'existait pas dans v5.2.0. Dans DFC v5.3.0, l'opérateur `LayerNormalization` est explicitement traité par un chemin de code dédié.
C'est clairement la preuve que des efforts de développement sont en cours.

Cependant, **l'implémentation interne est incomplète**, et l'appel de `_convert_axes_to_nhwc` après l'appel de la méthode lève le même `IndexError: list index out of range` avec les mêmes shapes de tenseurs que v5.2.0.

### 2. Ajout du flux de simplification onnxsim + réessai

Pour ViT et ConvNeXt, DFC v5.3.0 simplifie automatiquement l'ONNX d'entrée avec `onnxsim` et relance le parsing. Le modèle simplifié est sauvegardé en `model.sim.onnx` à côté du fichier d'entrée.
C'est un filet de sécurité utile pour les modèles avec des graphes ONNX redondants.

Cependant, pour nos modèles, la cause profonde étant dans `_convert_axes_to_nhwc`, le réessai **échoue exactement au même endroit**.

### 3. Fonctionnalité de recommandation de nœud End

Pour ConvNeXt, DFC v5.3.0 recommande maintenant des nœuds end spécifiques quand le parser abandonne, et invite l'utilisateur à les épingler et relancer.
C'est une amélioration UX appréciable.

Cependant, le réessai avec les nœuds end recommandés échoue également. La cause profonde est dans la gestion de LayerNormalization / Transpose, pas dans la sélection du nœud end.

---

## Cause profonde (inchangée depuis mars)

Le parser ONNX DFC continue d'échouer dans la conversion d'axes quand les tenseurs d'entrée de l'opérateur `LayerNormalization` ne suivent pas le format NCHW attendu. La chaîne d'appels est :

```
_create_layer_normalization_layer
  → get_layer_normalization_info
    → _convert_axes_to_nhwc
      → IndexError: list index out of range
```

Pour ConvNeXt, des `UnsupportedShuffleLayerError` supplémentaires sur plusieurs nœuds `Transpose` (`token_5` ~ `token_34`) montrent l'incomplétude de la gestion Transpose pour le pattern channels-last utilisé par cette architecture.

En résumé, **un nouveau chemin de code existe mais ne gère pas encore les cas qui échouaient déjà**.

---

## Demandes (inchangées depuis mars)

Les 2 demandes soulevées en mars restent d'actualité :

### 1. Corriger `_convert_axes_to_nhwc` pour le support multi-dimensionnel `LayerNormalization`

La méthode est maintenant accessible (amélioration). Mais la logique de mappage d'axes elle-même échoue sur les tenseurs d'entrée non-NCHW.
Les architectures de type Transformer récentes comme SwinV2, ViT, ConvNeXt dépendent toutes du bon fonctionnement de ceci.

### 2. ONNX Runtime Execution Provider pour Hailo-10H

Avec cela, la conversion complète par DFC deviendrait optionnelle, résolvant structurellement cette classe de problèmes. De nombreux utilisateurs de la communauté apprécieraient de pouvoir exécuter des modèles ONNX non modifiés directement sur Hailo-10H, même à plus faible débit que des HEF entièrement quantifiés.

---

## À propos du composant "ONNX Runtime Hailo Pipeline"

Les notes de version de DFC v5.3.0 mentionnent un composant "ONNX Runtime Hailo Pipeline". Si ce composant permet d'exécuter l'inférence WD-Tagger sur Hailo-10H **sans conversion DFC complète** (c'est-à-dire en déléguant au NPU uniquement les sous-graphes compatibles comme execution provider ORT, et en exécutant le reste sur CPU via ORT), nous apprécierions beaucoup des conseils officiels sur son utilisation correcte.

Concrètement :
- Ce composant est-il prévu comme voie de progression pour les modèles que DFC ne peut pas actuellement parser ?
- Un HEF partiel est-il nécessaire (compiler les sous-graphes parsables en HEF, exécuter le reste via ORT sur CPU) ?
- Existe-t-il des exemples de code ou tutoriels pour l'utiliser avec des modèles ONNX de type Transformer ?

---

## Procédure de reproduction

```bash
# 1. Configurer un venv Python propre avec DFC v5.3.0
python3.11 -m venv venv
source venv/bin/activate
pip install hailo_dataflow_compiler-5.3.0-py3-none-linux_x86_64.whl

# 2. Télécharger les 3 variantes de modèles WD-Tagger ONNX
for variant in swinv2 vit convnext; do
  huggingface-cli download \
    "SmilingWolf/wd-${variant}-tagger-v3" \
    model.onnx --local-dir "./wd-${variant}-tagger-v3"
done

# 3. Tenter le parsing de chaque modèle
for variant in swinv2 vit convnext; do
  hailo parser onnx "./wd-${variant}-tagger-v3/model.onnx" \
    --hw-arch hailo10h \
    --tensor-shapes input_1:1,448,448,3 2>&1 | tee "${variant}_5.3.0.log"
done
```

Les logs d'erreur complets de chaque exécution sont disponibles sur demande.

---

## Environnement de test

| Élément | Détails |
|---|---|
| OS | Ubuntu 24.04 (WSL2) |
| CPU | AMD Ryzen 5 5600X |
| RAM | 151 GB |
| Python | 3.11 |
| DFC | 5.3.0 |
| Modèles | `SmilingWolf/wd-{swinv2,vit,convnext}-tagger-v3` (HuggingFace) |
| Données de calibration | 500 images ComfyUI / SD (non utilisées, étape de quantification non atteinte) |

---

## Conclusion

Les efforts de développement visibles dans DFC v5.3.0 (`_create_layer_normalization_layer`, flux de réessai onnxsim, recommandation de nœud end) sont vraiment encourageants — exactement le progrès attendu par la communauté. L'écart restant est dans l'implémentation interne de `_convert_axes_to_nhwc`, maintenant accessible mais ne fonctionnant pas encore correctement pour nos modèles.

Nous continuerons à revérifier à chaque version de DFC et à publier des mises à jour si la situation change. Si quelqu'un chez Hailo lit ceci et a besoin des logs d'erreur complets, des hachages SHA-256 des modèles ONNX, ou d'un code de reproduction minimal, nous serons heureux de les fournir.
