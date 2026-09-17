# Sistema Atelier (γ)

**Atelier System** è l'identità visiva introdotta in yu_ai_manager — un linguaggio di design ibrido Editorial × Refined × Brutalist.

## Gerarchia dei marchi

**eauesque** (marchio prodotto) > **yu_ai_manager** (app) > **Atelier System** (nome del sistema di design)

Atelier System si trova allo stesso livello di Material / Fluent, organizzato sotto il marchio prodotto eauesque.

## Modello di adozione: tema additivo opt-in

I temi esistenti (light / dark / theme-retro / theme-glow) rimangono invariati. Atelier si applica **aggiungendo** `body.theme-atelier-light` o `body.theme-atelier-dark` — nessuna sostituzione distruttiva.

- **Nuovi utenti**: predefinito a Atelier light / dark (segue `prefers-color-scheme` del sistema)
- **Utenti che ritornano**: impostazioni conservate; puoi tornare a legacy in qualsiasi momento

Attiva/Disattiva tramite Impostazioni → Varie → "Atelier Theme".

## Ibrido tre font

| Ruolo | Font | Note |
|---|---|---|
| Display + body | **Fraunces** Variable | gli assi opsz/wght guidano h1=96 / h2=48 / h3=24 / body=14 / eyebrow=11 con corrispondenza della dimensione ottica |
| UI sans | **Inter** Variable | Navigazione, pulsanti, etichette, eyebrow |
| Data mono | **JetBrains Mono** Variable | Sintassi prompt (pesi, LoRA, embeds), valori metadati |

Tutti auto-hosted (sottoinsieme Latin Extended). Fraunces 176K / Inter 148K / JetBrains Mono 52K. Licenza SIL Open Font v1.1.

Rigenera tramite `scripts/build_atelier_fonts.py`.

## Accenti a due livelli

| Token | Scopo | Light / Dark |
|---|---|---|
| `--accent-warm` | Decorativo, atmosfera, preferiti | `#c9a063` / `#d4a96e` |
| `--accent-tool` | Azione, contorno focus, stato attivo | `#2f5c8a` / `#5a8fc5` |

Separare la decorazione dall'azione rende i UI affordances inequivocabili a prima vista.

## --canvas (grigio neutro area immagine)

Le regioni di immagine AI (area immagine modale, griglia miniature) vivono su un **canvas grigio neutro**, separato dal chrome UI caldo in modo che la percezione del colore dell'immagine non sia distorta:

- `--canvas`: `#d4d4d2` (light) / `#1a1a1a` (dark)
- `--canvas-raised`: `#c8c8c6` (light) / `#222222` (dark)

Chrome (`--bg`, `--surface`, `--surface-raised`) mantiene la famiglia caldo-beige.

## Verifica contrasto WCAG

8 coppie × light/dark = 16 casi, affermati da `tests/test_atelier_wcag.py`. Testo corpo 4.5:1, incidentale (contorno focus / eyebrow) 3:1.

```
uv run pytest tests/test_atelier_wcag.py
```

## Modale

- Area immagine: `--canvas`
- Pannello info: `--surface-raised` + Fraunces roman (niente corsivo)
- Corpo prompt: Fraunces roman; `(...:1.2)` e `<lora:...>` passano a JetBrains Mono inline
- Barra strumenti (v4.126.2 pillole circolari): glass + accent-tool attivo
- Chiudi / freccia navigazione / pulsante fav: glass + contorno focus accent-tool
- Preferito attivo: accento caldo (decorativo, tenuto separato dal blu strumento)

## Logo header

Costruzione due righe:
- Riga 1: `yu` (Fraunces 22pt)
- Riga 2: `eauesque` (firma JetBrains Mono 9pt)

Una firma editoriale che visualizza la gerarchia dei marchi. Il nav-brand legacy rimane in posizione per temi non-atelier.

## File

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

## Accessibilità

- `prefers-reduced-motion: reduce` annulla transform/animation (transizioni opacità mantenute)
- `:focus-visible` ovunque usa `--accent-tool` contorno 2px + offset 2px (WCAG 2.5.5 + 1.4.11)
- WCAG AA (4.5:1 corpo, 3:1 incidentale) verificato su 16 coppie

## Percorso rollback

Se qualcosa va storto, Impostazioni → "Atelier Theme" → "Off" ripristina istantaneamente light/dark legacy. I temi personalizzati (preset-*) non sono interessati.
