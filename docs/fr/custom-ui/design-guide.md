# Guide de conception — CSS, thèmes et responsive

Directives de conception et patterns d'implémentation pour l'UI personnalisée.

## Système de variables CSS

L'UI de référence gère les thèmes via des propriétés personnalisées CSS.
L'utilisation de ces variables dans votre UI personnalisée facilite la gestion du changement de thème et du mode sombre.

### Variables principales

```css
:root {
  --bg: #f5f6f8;         /* Arrière-plan de la page */
  --card: #ffffff;        /* Arrière-plan des cartes et panneaux */
  --text: #222;           /* Texte principal */
  --muted: #666;          /* Sous-texte, indications */
  --border: #e6e6e6;      /* Bordures et séparateurs */
  --shadow: 0 4px 14px rgba(0,0,0,0.08);  /* Ombre des cartes */
  --btn-bg: #ffffff;      /* Arrière-plan des boutons */
  --btn-text: #222;       /* Texte des boutons */
  --btn-hover: #f6f9ff;   /* Survol des boutons */
  --accent: #2563eb;      /* Couleur d'accent (conforme WCAG AA) */
}
```

### Variables du mode sombre

```css
body.dark {
  --bg: #0f1115;
  --card: #1b1f2a;
  --text: #e7eaf0;
  --muted: #aab2c0;
  --border: #2b3240;
  --shadow: 0 10px 26px rgba(0,0,0,0.45);
  --btn-bg: #1b2030;
  --btn-text: #e7eaf0;
  --btn-hover: #222a3d;
  --accent: #60a5fa;
  color-scheme: dark;
}
```

`color-scheme: dark` affecte la coloration des contrôles de formulaire OS (cases à cocher, barres de défilement, etc.).

### Liste complète des variables

Consultez [theming.md](../api/theming.md) pour les détails.

## Création de thèmes

### Définition d'un thème personnalisé

Les thèmes sont définis en surchargeant les variables CSS liées à une classe de `body` :

```css
/* Thème Ocean */
body.theme-ocean {
  --bg: #0a1628;
  --card: #132744;
  --text: #c8daf0;
  --muted: #7a9cc0;
  --border: #1e3a5f;
  --shadow: 0 8px 24px rgba(0,0,0,0.5);
  --btn-bg: #1a3050;
  --btn-text: #c8daf0;
  --btn-hover: #243d5f;
  --accent: #38bdf8;
  color-scheme: dark;
}

/* Thème Sakura (mode clair) */
body.theme-sakura {
  --bg: #fff5f5;
  --card: #ffffff;
  --text: #4a3030;
  --muted: #8a7070;
  --border: #f0d0d0;
  --shadow: 0 4px 14px rgba(200,100,100,0.1);
  --accent: #e8457a;
  color-scheme: light;
}
```

### Application d'un thème

Basculer les classes de thème en JavaScript :

```javascript
function setTheme(themeName) {
  // Supprimer les classes de thème existantes
  document.body.className = document.body.className
    .replace(/theme-\S+/g, '')
    .trim();
  if (themeName && themeName !== 'default') {
    document.body.classList.add(`theme-${themeName}`);
  }
  // Persistance
  localStorage.setItem('customTheme', themeName);
}

// Restauration au démarrage
const saved = localStorage.getItem('customTheme');
if (saved) setTheme(saved);
```

### Bascule du mode sombre

Logique de détection du mode sombre de l'UI de référence :

```javascript
function initDarkMode() {
  const saved = localStorage.getItem('darkMode');
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  const isDark = saved !== null ? saved === 'true' : prefersDark;
  document.body.classList.toggle('dark', isDark);
}

function toggleDarkMode() {
  const isDark = document.body.classList.toggle('dark');
  localStorage.setItem('darkMode', String(isDark));
}

initDarkMode();
```

## Design responsive

### Points de rupture

Points de rupture utilisés dans l'UI de référence :

| Point de rupture | Usage |
|----------------|------|
| `max-width: 600px` | Mobile (menu hamburger, grille à 1 colonne) |
| `max-width: 900px` | Tablette (grille à 2 colonnes, barre latérale rétractable) |
| `min-width: 901px` | Bureau (grille à 3 colonnes ou plus, barre latérale toujours visible) |

### Mise en page en grille

Grille responsive pour les résultats de recherche d'images :

```css
.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
  padding: 16px;
}

/* Mobile : cartes plus petites */
@media (max-width: 600px) {
  .image-grid {
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 8px;
    padding: 8px;
  }
}

/* Grand écran : plus d'espace */
@media (min-width: 1600px) {
  .image-grid {
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 16px;
  }
}
```

### Barre de navigation

Barre de navigation adaptée au mobile :

```css
.navbar {
  display: flex;
  align-items: center;
  padding: 0 16px;
  height: 48px;
  background: var(--card);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 100;
}

.nav-links {
  display: flex;
  gap: 8px;
}

.hamburger { display: none; }

@media (max-width: 600px) {
  .nav-links {
    display: none;
    position: absolute;
    top: 48px;
    left: 0;
    right: 0;
    flex-direction: column;
    background: var(--card);
    border-bottom: 1px solid var(--border);
    padding: 8px;
  }
  .nav-links.open { display: flex; }
  .hamburger { display: block; }
}
```

## Patterns de composants

### Composant carte

Pattern de base pour une carte d'image :

```css
.card {
  background: var(--card);
  border-radius: 8px;
  overflow: hidden;
  box-shadow: var(--shadow);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.card:hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 32px rgba(0,0,0,0.3);
}

.card img {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  display: block;
}

.card-body {
  padding: 10px 12px;
}

.card-title {
  font-size: 0.85rem;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-meta {
  font-size: 0.75rem;
  color: var(--muted);
  margin-top: 2px;
}
```

### Boutons

```css
.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: var(--btn-bg);
  color: var(--btn-text);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.875rem;
  cursor: pointer;
  transition: background 0.15s;
}

.btn:hover { background: var(--btn-hover); }

/* Bouton primaire */
.btn-primary {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
.btn-primary:hover {
  filter: brightness(1.1);
}

/* Petit bouton (action secondaire) */
.btn-sm {
  padding: 4px 10px;
  font-size: 0.8rem;
}
```

### Modal

```css
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s;
}

.modal-overlay.active {
  opacity: 1;
  pointer-events: auto;
}

.modal {
  background: var(--card);
  border-radius: 12px;
  padding: 24px;
  max-width: 600px;
  width: 90%;
  max-height: 80vh;
  overflow-y: auto;
  box-shadow: 0 20px 60px rgba(0,0,0,0.5);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.modal-close {
  background: none;
  border: none;
  color: var(--muted);
  font-size: 1.5rem;
  cursor: pointer;
}
```

### Jetons de tags

```css
.tag {
  display: inline-block;
  padding: 2px 8px;
  background: var(--tag-bg, #4a4a4a);
  color: var(--tag-text, #f0f0f0);
  border: 1px solid var(--tag-border, #666);
  border-radius: 4px;
  font-size: 0.75rem;
  cursor: pointer;
  transition: background 0.1s;
}

.tag:hover {
  background: var(--tag-hover-bg, #5a5a5a);
  border-color: var(--tag-hover-border, #888);
}
```

### Notifications toast

```css
.toast {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%) translateY(100px);
  background: var(--card);
  color: var(--text);
  padding: 12px 24px;
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.4);
  z-index: 2000;
  opacity: 0;
  transition: transform 0.3s ease, opacity 0.3s ease;
}

.toast.show {
  transform: translateX(-50%) translateY(0);
  opacity: 1;
}
```

```javascript
function showToast(message, duration = 3000) {
  const el = document.getElementById('toast');
  el.textContent = message;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), duration);
}
```

### Notation par étoiles

```css
.star-rating {
  display: inline-flex;
  gap: 2px;
}

.star-rating .star {
  cursor: pointer;
  font-size: 1.2rem;
  color: var(--muted);
  transition: color 0.1s;
}

.star-rating .star.filled { color: #fbbf24; }
.star-rating .star:hover { color: #f59e0b; }
```

```javascript
function createStarRating(fileId, currentRating = 0) {
  const container = document.createElement('div');
  container.className = 'star-rating';
  for (let i = 1; i <= 5; i++) {
    const star = document.createElement('span');
    star.className = 'star' + (i <= currentRating ? ' filled' : '');
    star.textContent = '★';
    star.onclick = async () => {
      const newRating = i === currentRating ? 0 : i;
      await api('/api/ratings/set', {
        method: 'POST',
        body: JSON.stringify({ file_id: fileId, rating: newRating }),
      });
      // Mettre à jour l'UI
      container.querySelectorAll('.star').forEach((s, idx) => {
        s.classList.toggle('filled', idx < newRating);
      });
    };
    container.appendChild(star);
  }
  return container;
}
```

## Performance

### Chargement différé des images

```html
<img src="/api/thumbnail/${id}" loading="lazy" alt="${filename}">
```

`loading="lazy"` est le chargement différé natif du navigateur. Les images se chargent quand elles entrent dans la zone visible lors du défilement.

### Cache des miniatures

`/api/thumbnail/<id>` renvoie ETag et des en-têtes de cache de 24 heures.
Le navigateur gère automatiquement le cache, aucune implémentation supplémentaire n'est nécessaire.

### Affichage de nombreuses images

Pour les bibliothèques de plus de 150 000 éléments, ajouter tous les éléments au DOM en une seule fois dégradera les performances.
Il est recommandé d'utiliser la pagination par curseur pour charger progressivement :

```javascript
let nextCursor = null;
let loading = false;

async function loadMore() {
  if (loading) return;
  loading = true;
  const params = new URLSearchParams({ limit: '50' });
  if (nextCursor) params.set('cursor', nextCursor);
  const res = await fetch(`/api/search?${params}`);
  const json = await res.json();
  const items = json.results || json.data?.results || [];
  nextCursor = json.next_cursor || json.data?.next_cursor || null;

  const grid = document.getElementById('results');
  items.forEach(f => {
    const card = document.createElement('div');
    card.className = 'card';
    const img = document.createElement('img');
    img.src = `/api/thumbnail/${f.id}`;
    img.loading = 'lazy';
    card.appendChild(img);
    grid.appendChild(card);
  });
  loading = false;
}

// Détection du défilement avec Intersection Observer
const sentinel = document.getElementById('sentinel');
new IntersectionObserver(entries => {
  if (entries[0].isIntersecting && nextCursor) loadMore();
}).observe(sentinel);
```

## Accessibilité

### Contraste des couleurs

- Texte : maintenir WCAG AA (4,5:1 ou plus)
- `--accent` par défaut `#2563eb` est à 5,17:1 sur fond blanc
- `--accent` en mode sombre `#60a5fa` offre un contraste suffisant sur fond sombre

### Navigation au clavier

```css
/* Visualiser l'anneau de focus */
:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

/* Masquer l'anneau de focus pour les interactions non-clavier */
:focus:not(:focus-visible) {
  outline: none;
}
```

### Lien de saut

L'UI de référence place un lien de saut en haut de l'écran :

```html
<a href="#main-content" class="skip-link">Skip to main content</a>
```

```css
.skip-link {
  position: absolute;
  top: -100px;
  left: 16px;
  z-index: 9999;
  padding: 8px 16px;
  background: var(--accent);
  color: #fff;
  border-radius: 4px;
}
.skip-link:focus { top: 8px; }
```
