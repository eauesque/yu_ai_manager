# Matrice d'Inférence Distribuée

**Version** : v4.67.0 et suivantes

## Vue d'ensemble

Sur la page `/mesh-inference`, vous pouvez basculer activé/désactivé par type d'inférence pour chaque pair participant à la mesh inference. Les cibles sont les 4 types : tagger, clip, yolo, whisper.

Cela permet de répartir les rôles sans toucher à la config, comme dédier le NPU Hailo du Pi5 au tagger, ou traiter clip sur un hôte GPU.

## Utilisation

1. Cliquer sur « 🕸️ Inférence distribuée » dans la barre de navigation
2. Cliquer chaque cellule du tableau matriciel pour basculer activé/désactivé
   - ☑ = activé (ce type d'inférence est utilisé sur ce pair)
   - ☐ = désactivé (ce pair est ignoré)
   - — = ce pair ne fournit pas ce type (non cliquable)
3. Le bouton « Mode local uniquement » désactive en masse tous les pairs distants
4. L'état est automatiquement persisté dans `data/mesh_inference_state.json`

## Comportement

- Les paramètres sont conservés même pour les pairs hors ligne (réappliqués automatiquement à la reconnexion)
- « Mode local uniquement » n'est cliquable que s'il y a au moins un type activé en local
- Lancer un batch tagger quand tagger est désactivé sur tous les pairs échoue immédiatement avec l'erreur `no_enabled_peers`
- L'état de désactivation est conservé même si un pair part temporairement et revient lors d'une re-découverte mDNS

## Relation avec le Checkbox YOLO Distribué Existant

La case « Inférence distribuée » de la page de détection YOLO est conservée pour compatibilité descendante et se combine comme suit :

| yoloDistributed | Colonne yolo de la matrice | Comportement réel |
|---|---|---|
| ✅ ON | Tous les pairs activés | Distribution sur tous les pairs comme avant |
| ✅ ON | Certains désactivés | Saute les pairs désactivés |
| ❌ OFF | Ignoré | Local uniquement (bypass du router) |

## Voir aussi

- Référence API : [api/mesh-inference.md](../api/mesh-inference.md)
- LLM Router (autre couche) : [../llm-router/](../llm-router/)
