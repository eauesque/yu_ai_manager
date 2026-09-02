# Thématisation — Propriétés personnalisées CSS

Ceci est une liste des propriétés personnalisées CSS utilisées dans l'interface de référence (`ui/default/`).
Une interface personnalisée peut remplacer l'apparence des composants existants en redéfinissant ces variables.

Source : `ui/default/static/css/base/base-theme.css`

## Variables principales (`:root` / `body.dark`)

| Variable | Clair | Sombre | Objectif |
|----------|-------|--------|---------|
| `--bg` | `#f5f6f8` | `#0f1115` | Arrière-plan de la page |
| `--card` | `#ffffff` | `#1b1f2a` | Arrière-plan de la carte/panneau |
| `--text` | `#222` | `#e7eaf0` | Texte principal |
| `--muted` | `#666` | `#aab2c0` | Sous-texte/indices |
| `--border` | `#e6e6e6` | `#2b3240` | Bordures/séparateurs |
| `--shadow` | `0 4px 14px rgba(0,0,0,0.08)` | `0 10px 26px rgba(0,0,0,0.45)` | Ombre de carte |
| `--btn-bg` | `#ffffff` | `#1b2030` | Arrière-plan du bouton |
| `--btn-text` | `#222` | `#e7eaf0` | Texte du bouton |
| `--btn-hover` | `#f6f9ff` | `#222a3d` | Survol du bouton |
| `--tooltip-bg` | `rgba(0,0,0,0.85)` | `rgba(0,0,0,0.92)` | Arrière-plan de l'info-bulle |
| `--tooltip-text` | `#fff` | `#fff` | Texte de l'info-bulle |
| `--accent` | `#2563eb` | `#60a5fa` | Couleur d'accent (liens, surbrillances de boutons) |

## Variables du mode sombre

### Jetons d'étiquette

| Variable | Valeur | Objectif |
|----------|--------|---------|
| `--tag-bg` | `#4a4a4a` | Arrière-plan de l'étiquette |
| `--tag-text` | `#f0f0f0` | Texte de l'étiquette |
| `--tag-border` | `#666` | Bordure de l'étiquette |
| `--tag-hover-bg` | `#5a5a5a` | Arrière-plan du survol de l'étiquette |
| `--tag-hover-border` | `#888` | Bordure du survol de l'étiquette |
| `--tag-focus-ring` | `#60a5fa` | Anneau de focus de l'étiquette |

### Variantes de catégorie d'étiquette

| Variable | Objectif |
|----------|---------|
| `--tag-ns-*` | Étiquettes de namespace (bg, border, text) |
| `--tag-wh-*` | Étiquettes de poids élevé |
| `--tag-wl-*` | Étiquettes de poids faible |
| `--tag-we-*` | Étiquettes de poids mis en avant |

### Prompt négatif

| Variable | Valeur | Objectif |
|----------|--------|---------|
| `--neg-prompt-bg` | `#2d2424` | Arrière-plan du prompt négatif |
| `--neg-prompt-border` | `#fc8181` | Bordure du prompt négatif |
| `--neg-heading` | `#fc8181` | En-tête négatif |

### Accordéon

| Variable | Valeur | Objectif |
|----------|--------|---------|
| `--accordion-bg` | `#252525` | Arrière-plan de l'accordéon |
| `--accordion-border` | `#3a3a3a` | Bordure de l'accordéon |
| `--accordion-header-bg` | `#2a2a2a` | Arrière-plan de l'en-tête |
| `--accordion-header-text` | `#e0e0e0` | Texte de l'en-tête |

## Classes de thème

| Classe | Description |
|--------|-------------|
| `body.dark` | Mode sombre |
| `body.theme-retro` | Thème rétro néon (Code Konami) |
| `body.theme-glow` | Effet de lueur personnalisé |

## Application des thèmes

Pour modifier le thème dans une interface personnalisée :

```css
/* Exemple de thème personnalisé */
body.theme-ocean {
  --bg: #0a1628;
  --card: #132744;
  --text: #c8daf0;
  --accent: #38bdf8;
  color-scheme: dark;
}
```

Le thème prend effet en ajoutant une classe à l'élément `body`.
La propriété `color-scheme: dark` en mode sombre affecte les couleurs des contrôles de formulaire OS.
