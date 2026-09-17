# Guia de Design — CSS, Temas e Design Responsivo

Diretrizes e padrões de implementação para o design de UIs personalizadas.

## Sistema de Variáveis CSS

A UI de referência gerencia temas com propriedades personalizadas CSS.
Usar essas variáveis em UIs personalizadas facilita a alternância de temas e o suporte ao modo escuro.

### Variáveis Principais

```css
:root {
  --bg: #f5f6f8;         /* fundo da página */
  --card: #ffffff;        /* fundo de cards/painéis */
  --text: #222;           /* texto principal */
  --muted: #666;          /* subtexto/dicas */
  --border: #e6e6e6;      /* bordas/divisores */
  --shadow: 0 4px 14px rgba(0,0,0,0.08);  /* sombra do card */
  --btn-bg: #ffffff;      /* fundo do botão */
  --btn-text: #222;       /* texto do botão */
  --btn-hover: #f6f9ff;   /* hover do botão */
  --accent: #2563eb;      /* cor de destaque (compatível com WCAG AA) */
}
```

### Variáveis do Modo Escuro

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

`color-scheme: dark` afeta a esquema de cores dos controles de formulário do OS (caixas de seleção, barras de rolagem, etc.).

### Lista Completa de Variáveis

Consulte [theming.md](../api/theming.md) para detalhes.

## Criando Temas

### Definindo Temas Personalizados

Os temas são definidos sobrescrevendo variáveis CSS vinculadas a classes do `body`:

```css
/* Tema Ocean */
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

/* Tema Sakura (modo claro) */
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

### Aplicando Temas

Alternar classes de tema com JavaScript:

```javascript
function setTheme(themeName) {
  document.body.className = document.body.className
    .replace(/theme-\S+/g, '')
    .trim();
  if (themeName && themeName !== 'default') {
    document.body.classList.add(`theme-${themeName}`);
  }
  localStorage.setItem('customTheme', themeName);
}

const saved = localStorage.getItem('customTheme');
if (saved) setTheme(saved);
```

### Alternância do Modo Escuro

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

## Design Responsivo

### Breakpoints

| Breakpoint | Uso |
|----------------|------|
| `max-width: 600px` | Mobile (menu hambúrguer, grid de 1 coluna) |
| `max-width: 900px` | Tablet (grid de 2 colunas, barra lateral recolhida) |
| `min-width: 901px` | Desktop (grid de 3+ colunas, barra lateral sempre visível) |

### Layout de Grid

```css
.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
  padding: 16px;
}

@media (max-width: 600px) {
  .image-grid {
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 8px;
    padding: 8px;
  }
}

@media (min-width: 1600px) {
  .image-grid {
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 16px;
  }
}
```

## Padrões de Componentes

### Card

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

### Botões

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

.btn-primary {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
.btn-primary:hover { filter: brightness(1.1); }

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

### Notificação Toast

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

### Avaliação por Estrelas

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

## Performance

### Carregamento Lazy de Imagens

```html
<img src="/api/thumbnail/${id}" loading="lazy" alt="${filename}">
```

`loading="lazy"` é carregamento lazy nativo do navegador.

### Cache de Miniaturas

`/api/thumbnail/<id>` retorna ETag e headers de cache de 24 horas.
O navegador faz cache automaticamente, portanto nenhuma implementação adicional é necessária.

### Paginação para Grandes Quantidades

Para bibliotecas com mais de 150.000 itens, recomenda-se carregamento incremental com paginação baseada em cursor:

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

const sentinel = document.getElementById('sentinel');
new IntersectionObserver(entries => {
  if (entries[0].isIntersecting && nextCursor) loadMore();
}).observe(sentinel);
```

## Acessibilidade

### Contraste de Cores

- Texto: Manter WCAG AA (4.5:1 ou mais)
- O padrão `--accent` `#2563eb` tem 5.17:1 no fundo branco
- O `--accent` do modo escuro `#60a5fa` tem contraste suficiente em fundo escuro

### Operação por Teclado

```css
:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

:focus:not(:focus-visible) {
  outline: none;
}
```

### Links de Salto

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
