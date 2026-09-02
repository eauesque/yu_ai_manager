# Barre d'outils modale

La barre d'outils unifiée en bas de la modal de détail fournit l'accès à tous les contrôles principaux pendant la visualisation d'images/vidéos.

## Structure

### Barre principale (toujours visible)

**Mode image fixe:**
- ☆ Favori
- ⓘ Basculer le panneau d'info
- ‹ › Précédent / Suivant
- Zoom (− / 100% / +)
- Mode d'ajustement (fit / fit-w / fit-h / fit-custom + hauteur / original)
- Spread 2P / direction ↔ (le cas échéant)
- ⛶ Immersif / ⤢ Plein écran
- 📁 Collection
- Bridge Envoyer (Envoyer prompt ▾ / Envoyer image ▾)

**Mode vidéo/audio (disposition à 2 niveaux):**
- Haut: affichage de l'heure + barre de recherche (largeur max 720px)
- Bas: ☆ Fav / ⓘ Info / ‹ › / ▶ Lecture ⏪ ⏩ / ♪ Muet + volume / ⛶ ⤢ / 📁

### Menu de débordement (bouton …)

Consolide les opérations peu fréquentes dans une liste verticale:
- Lecture automatique + intervalle
- Répéter / vitesse / reprendre (pour vidéo)
- FPB / grille de caractères (pour images fixes)
- ZIP / vue conteneur
- Guide clavier ?
- Réduire la barre d'outils «

## Raccourcis clavier

| Touche | Action |
|---|---|
| `T` | Basculer la visibilité de la barre d'outils |
| `V` | Mode immersif |
| `F` | Plein écran |
| `I` | Panneau d'info |
| `H` | Guide clavier |
| `P` | Lecture automatique |
| `Space` / `K` | Lecture / pause (vidéo) |
| `J` / `0` | Rembobiner (vidéo) |
| `L` | Avance rapide (vidéo) |
| `M` | Muet (vidéo) |
| `R` | Répéter (vidéo) |
| `←` / `→` | Image précédente / suivante |
| `ESC` | Fermer le menu de débordement → modal dans l'ordre |

## Réduire et restaurer

Méthodes pour réduire la barre d'outils:
- Dans le menu de débordement (…), sélectionnez "Réduire la barre d'outils"
- Appuyez sur la touche `T`

Méthodes pour restaurer:
- Cliquez sur la poignée de bord au centre inférieur de l'écran
- Appuyez à nouveau sur la touche `T`

La position de la poignée de bord s'ajuste automatiquement en fonction de la présence de la pellicule lors de l'état réduit.

## Accessibilité

- La barre d'outils entière a `role="toolbar"`
- Le bouton de débordement utilise `aria-haspopup="menu"` / `aria-expanded` mis à jour dynamiquement
- Les éléments du menu de débordement ont `role="menuitem"`
- La poignée de bord est un `<button>` standard utilisable avec Entrée / Espace
- Pour satisfaire WCAG 2.5.5 (Taille cible), la poignée visuellement 8px a une zone d'impact invisible de 24px de haut étendue via `::before`
