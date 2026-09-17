# Système Atelier (γ)

**Atelier System** est l'identité visuelle introduite dans yu_ai_manager — un langage de conception hybride Editorial × Refined × Brutalist.

## Hiérarchie des marques

**eauesque** (marque produit) > **yu_ai_manager** (application) > **Atelier System** (nom du système de conception)

Atelier System se situe au même niveau que Material / Fluent, organisé sous la marque produit eauesque.

## Modèle d'adoption: thème additif opt-in

Les thèmes existants (light / dark / theme-retro / theme-glow) restent inchangés. Atelier s'applique en **ajoutant** `body.theme-atelier-light` ou `body.theme-atelier-dark` — aucun remplacement destructif.

- **Nouveaux utilisateurs**: par défaut sur Atelier light / dark (suit `prefers-color-scheme` du système)
- **Utilisateurs revenant**: paramètres préservés; vous pouvez revenir à la version legacy à tout moment

Bascule via Paramètres → Divers → "Atelier Theme".

## Hybride trois polices

| Rôle | Police | Notes |
|---|---|---|
| Display + body | **Fraunces** Variable | axes opsz/wght pilotent h1=96 / h2=48 / h3=24 / body=14 / eyebrow=11 avec correspondance de taille optique |
| UI sans | **Inter** Variable | Navigation, boutons, labels, eyebrow |
| Data mono | **JetBrains Mono** Variable | Syntaxe de prompt (poids, LoRA, embeds), valeurs de métadonnées |

Tous auto-hébergés (sous-ensemble Latin Extended). Fraunces 176K / Inter 148K / JetBrains Mono 52K. Licence SIL Open Font v1.1.

Régénérer via `scripts/build_atelier_fonts.py`.

## Accents à deux niveaux

| Token | Objectif | Light / Dark |
|---|---|---|
| `--accent-warm` | Décoratif, ambiance, favoris | `#c9a063` / `#d4a96e` |
| `--accent-tool` | Action, contour de focus, état actif | `#2f5c8a` / `#5a8fc5` |

Séparer la décoration de l'action rend les affordances UI sans ambiguïté au premier coup d'œil.

## --canvas (gris neutre de zone d'image)

Les régions d'image IA (zone d'image modale, grille de vignettes) vivent sur un **canevas gris neutre**, séparé du chrome UI chaud pour que la perception des couleurs d'image ne soit pas biaisée:

- `--canvas`: `#d4d4d2` (light) / `#1a1a1a` (dark)
- `--canvas-raised`: `#c8c8c6` (light) / `#222222` (dark)

Chrome (`--bg`, `--surface`, `--surface-raised`) conserve la famille chaud-beige.

## Vérification du contraste WCAG

8 paires × light/dark = 16 cas, affirms par `tests/test_atelier_wcag.py`. Texte de corps 4.5:1, incident (contour de focus / eyebrow) 3:1.

```
uv run pytest tests/test_atelier_wcag.py
```

## Modale

- Zone d'image: `--canvas`
- Panneau info: `--surface-raised` + Fraunces roman (pas d'italique)
- Corps de prompt: Fraunces roman; `(...:1.2)` et `<lora:...>` basculent en JetBrains Mono en ligne
- Barre d'outils (v4.126.2 pilules circulaires): glass + accent-tool actif
- Fermer / flèche de navigation / bouton fav: glass + contour focus accent-tool
- Favori actif: accent chaud (décoratif, tenu séparé du bleu outil)

## Logo d'en-tête

Construction deux lignes:
- Ligne 1: `yu` (Fraunces 22pt)
- Ligne 2: `eauesque` (signature JetBrains Mono 9pt)

Une signature éditoriale qui visualise la hiérarchie des marques. Le nav-brand legacy reste en place pour les thèmes non-atelier.

## Fichiers

```
ui/default/static/css/atelier/
  atelier-tokens.css       # @font-face + body.theme-atelier-* + tokens
  atelier-components.css   # h1-h3, p, eyebrow, glass btn, prompt-syntax
  atelier-index.css        # logo + sidebar + grid + pill search
  atelier-modal.css        # full modal (canvas + glass + accent-tool)

ui/default/static/fonts/atelier/
  Fraunces-VariableFont.subset.woff2     # 176K
  Inter-VariableFont.subset.woff2        # 148K
  JetBrainsMono-VariableFont.subset.woff2 # 52K
  LICENSE.md                              # OFL v1.1
```

## Accessibilité

- `prefers-reduced-motion: reduce` annule transform/animation (transitions d'opacité conservées)
- `:focus-visible` partout utilise `--accent-tool` contour 2px + décalage 2px (WCAG 2.5.5 + 1.4.11)
- WCAG AA (4.5:1 corps, 3:1 incident) vérifié sur 16 paires

## Chemin de retour arrière

Si quelque chose tourne mal, Paramètres → "Atelier Theme" → "Off" restaure instantanément light/dark legacy. Les thèmes personnalisés (preset-*) ne sont pas affectés.
