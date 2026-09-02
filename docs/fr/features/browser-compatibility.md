# Rapport de compatibilité des navigateurs

**Date du sondage :** 2026-02-23

## Navigateurs pris en charge (Recommandés)

| Navigateur | Version minimale | Version avec toutes les fonctionnalités |
|----------|----------------|---------------------|
| Chrome   | 80+            | 94+                 |
| Firefox  | 74+            | 101+                |
| Safari   | 13.1+          | 16+                 |
| Edge     | 80+            | 94+                 |

IE11 et les versions antérieures ne sont pas pris en charge.

---

## Compatibilité des API

| Fonctionnalité | Chrome | Firefox | Safari | Edge | Remarques |
|---------|--------|---------|--------|------|-------|
| Fetch API / async/await | 55+ | 52+ | 11+ | 15+ | Tous les navigateurs pris en charge |
| AbortController | 66+ | 57+ | 11.1+ | 16+ | Tous les navigateurs pris en charge |
| IntersectionObserver | 51+ | 55+ | 12.1+ | 16+ | Utilisé pour le défilement infini |
| Chaînage optionnel `?.` | 80+ | 74+ | 13.1+ | 80+ | Utilisé largement dans le codebase |
| scroll-snap | 69+ | 68+ | 13+ | 79+ | Utilisé pour les cartes dock |
| `scrollbar-gutter` | 94+ | 101+ | **16+** | 94+ | Non pris en charge sur Safari 15 et antérieurs |
| Raccourci CSS `inset` | 102+ | 106+ | **16+** | 102+ | Non pris en charge sur Safari 15 et antérieurs |
| `backdrop-filter` | 76+ | **Non pris en charge** | 9+ | 79+ | Non pris en charge sur Firefox |
| `-webkit-backdrop-filter` | ✓ | **Non pris en charge** | 9+ | ✓ | Pas d'alternative pour Firefox |

---

## Problèmes connus

### 🔴 Firefox — `backdrop-filter` non pris en charge

- **Fichiers affectés :** `dock-shell-panel.css`, `search-results-modal-nav.css`
- **Symptôme :** L'effet de flou du panneau (glassmorphism) n'est pas rendu, laissant le fond transparent
- **Gravité :** Dégradation de la qualité visuelle (la fonctionnalité n'est pas affectée)
- **Plan :** Non traité (un fond opaque de secours pour Firefox peut être ajouté à l'avenir)

### 🟡 Safari 15 et antérieurs — `scrollbar-gutter`, `inset` non pris en charge

- **Fichiers affectés :** `dock-cards.css`, `uxpatch-i18n-paths.css`
- **Symptôme :** Instabilité de la région de scrollbar et légers décalages de calcul de position
- **Gravité :** Mineure (la disposition reste fonctionnelle)

---

## Mesures de compatibilité existantes (Bonnes pratiques)

- À la fois `-webkit-backdrop-filter` et le standard `backdrop-filter` sont déclarés
- Les scrollbars de Firefox utilisent `scrollbar-width` / `scrollbar-color`
- Les scrollbars WebKit utilisent `-webkit-scrollbar`
- Les API destructrices (`crypto.randomUUID`, `structuredClone`, `.at()`, etc.) ne sont pas utilisées

---

## Futurs candidats

| Élément | Priorité | Description |
|------|----------|-------------|
| Fallback backdrop-filter Firefox | P3 | Basculer vers un fond semi-transparent sans flou |
| Requête conditionnelle `@supports` | P3 | Détection des fonctionnalités CSS |
