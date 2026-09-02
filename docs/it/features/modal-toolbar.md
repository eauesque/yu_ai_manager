# Barra degli strumenti modale

La barra degli strumenti unificata in fondo al modale di dettaglio fornisce accesso a tutti i controlli principali durante la visualizzazione di immagini/video.

## Struttura

### Barra primaria (sempre visibile)

**Modalità immagine fissa:**
- ☆ Preferito
- ⓘ Attiva/Disattiva pannello info
- ‹ › Precedente / Successivo
- Zoom (− / 100% / +)
- Modalità adattamento (fit / fit-w / fit-h / fit-custom + altezza / original)
- Spread 2P / direzione ↔ (se applicabile)
- ⛶ Immersivo / ⤢ Schermo intero
- 📁 Raccolta
- Bridge Invia (Invia prompt ▾ / Invia immagine ▾)

**Modalità video/audio (layout a 2 livelli):**
- Superiore: visualizzazione tempo + barra di ricerca (larghezza max 720px)
- Inferiore: ☆ Fav / ⓘ Info / ‹ › / ▶ Riproduci ⏪ ⏩ / ♪ Muto + volume / ⛶ ⤢ / 📁

### Menu overflow (pulsante …)

Consolida operazioni poco frequenti in un elenco verticale:
- Riproduzione automatica + intervallo
- Ripeti / velocità / riprendi (per video)
- FPB / griglia caratteri (per immagini fisse)
- ZIP / visualizzazione contenitore
- Guida tastiera ?
- Comprimi barra degli strumenti «

## Scorciatoie da tastiera

| Tasto | Azione |
|---|---|
| `T` | Attiva/Disattiva visibilità barra degli strumenti |
| `V` | Modalità immersiva |
| `F` | Schermo intero |
| `I` | Pannello info |
| `H` | Guida tastiera |
| `P` | Riproduzione automatica |
| `Space` / `K` | Riproduci / pausa (video) |
| `J` / `0` | Riavvolgi (video) |
| `L` | Avanti veloce (video) |
| `M` | Muto (video) |
| `R` | Ripeti (video) |
| `←` / `→` | Immagine precedente / successiva |
| `ESC` | Chiudi menu overflow → modale in ordine |

## Comprimi e ripristina

Metodi per comprimere la barra degli strumenti:
- Dal menu overflow (…), selezionare "Comprimi barra degli strumenti"
- Premere il tasto `T`

Metodi per ripristinare:
- Fare clic sul punto di aggancio del bordo al centro inferiore dello schermo
- Premere di nuovo il tasto `T`

La posizione del punto di aggancio del bordo si regola automaticamente in base alla presenza della striscia di pellicola durante lo stato compresso.

## Accessibilità

- L'intera barra degli strumenti ha `role="toolbar"`
- Il pulsante overflow utilizza `aria-haspopup="menu"` / `aria-expanded` aggiornato dinamicamente
- Gli elementi del menu overflow hanno `role="menuitem"`
- Il punto di aggancio del bordo è un `<button>` standard utilizzabile con Invio / Spazio
- Per soddisfare WCAG 2.5.5 (Dimensione target), il punto di aggancio visivamente 8px ha un'area di impatto invisibile di 24px di altezza estesa tramite `::before`
