# Rapporto di Compatibilità del Browser

**Data del sondaggio:** 2026-02-23

## Browser Supportati (Consigliati)

| Browser  | Versione Minima | Versione Supporto Completo |
|----------|----------------|---------------------|
| Chrome   | 80+            | 94+                 |
| Firefox  | 74+            | 101+                |
| Safari   | 13.1+          | 16+                 |
| Edge     | 80+            | 94+                 |

IE11 e versioni precedenti non sono supportati.

---

## Compatibilità API

| Funzionalità | Chrome | Firefox | Safari | Edge | Note |
|---------|--------|---------|--------|------|-------|
| Fetch API / async/await | 55+ | 52+ | 11+ | 15+ | Tutti i browser sono supportati |
| AbortController | 66+ | 57+ | 11.1+ | 16+ | Tutti i browser sono supportati |
| IntersectionObserver | 51+ | 55+ | 12.1+ | 16+ | Utilizzato per lo scorrimento infinito |
| Optional chaining `?.` | 80+ | 74+ | 13.1+ | 80+ | Utilizzato ampiamente in tutto il codebase |
| scroll-snap | 69+ | 68+ | 13+ | 79+ | Utilizzato per le schede dock |
| `scrollbar-gutter` | 94+ | 101+ | **16+** | 94+ | Non supportato su Safari 15 e versioni precedenti |
| `inset` CSS shorthand | 102+ | 106+ | **16+** | 102+ | Non supportato su Safari 15 e versioni precedenti |
| `backdrop-filter` | 76+ | **Non supportato** | 9+ | 79+ | Non supportato su Firefox |
| `-webkit-backdrop-filter` | ✓ | **Non supportato** | 9+ | ✓ | Nessuna alternativa per Firefox |

---

## Problemi Noti

### 🔴 Firefox — `backdrop-filter` Non Supportato

- **File interessati:** `dock-shell-panel.css`, `search-results-modal-nav.css`
- **Sintomo:** L'effetto di sfocatura del pannello (glassmorphism) non viene renderizzato, lasciando lo sfondo trasparente
- **Gravità:** Degradazione della qualità visiva (la funzionalità non è interessata)
- **Piano:** Non affrontato (in futuro potrebbe essere aggiunto un fallback di sfondo opaco per Firefox)

### 🟡 Safari 15 e Versioni Precedenti — `scrollbar-gutter`, `inset` Non Supportati

- **File interessati:** `dock-cards.css`, `uxpatch-i18n-paths.css`
- **Sintomo:** Oscillazione della regione della barra di scorrimento e piccoli offset di calcolo della posizione
- **Gravità:** Minore (il layout rimane funzionale)

---

## Misure di Compatibilità Esistenti (Buone Pratiche)

- Sia `-webkit-backdrop-filter` che lo standard `backdrop-filter` sono dichiarati
- Le barre di scorrimento di Firefox utilizzano `scrollbar-width` / `scrollbar-color`
- Le barre di scorrimento WebKit utilizzano `-webkit-scrollbar`
- Le API distruttive (`crypto.randomUUID`, `structuredClone`, `.at()`, ecc.) non vengono utilizzate

---

## Candidati Futuri

| Elemento | Priorità | Descrizione |
|------|----------|-------------|
| Fallback backdrop-filter Firefox | P3 | Passa a uno sfondo semi-trasparente senza sfocatura |
| `@supports` query condizionale | P3 | Rilevamento delle funzionalità CSS |
