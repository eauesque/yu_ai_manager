# Atelier-System (γ)

**Atelier System** ist die visuelle Identität, die yu_ai_manager eingeführt hat — eine hybride Designsprache aus Editorial × Refined × Brutalism.

## Markenhierarchie

**eauesque** (Produktmarke) > **yu_ai_manager** (App) > **Atelier System** (Name des Designsystems)

Atelier System befindet sich auf derselben Ebene wie Material / Fluent, angeordnet unter der eauesque-Produktmarke.

## Adopitionsmodell: Opt-in additives Theme

Bestehende Themes (light / dark / theme-retro / theme-glow) bleiben unverändert. Atelier wird angewendet, indem `body.theme-atelier-light` oder `body.theme-atelier-dark` **hinzugefügt** wird — keine destruktive Ersetzung.

- **Neue Benutzer**: Standard auf Atelier light / dark (folgt dem System `prefers-color-scheme`)
- **Zurückkehrende Benutzer**: Einstellungen bleiben erhalten; Sie können jederzeit zu Legacy zurückwechseln

Umschalten über Einstellungen → Sonstiges → "Atelier Theme".

## Hybrid aus drei Schriftarten

| Rolle | Schriftart | Notizen |
|---|---|---|
| Display + Body | **Fraunces** Variable | opsz/wght Achsen steuern h1=96 / h2=48 / h3=24 / body=14 / eyebrow=11 mit optischer Größe, die der gerenderten Größe entspricht |
| UI sans | **Inter** Variable | Navigation, Schaltflächen, Labels, Eyebrow |
| Data mono | **JetBrains Mono** Variable | Eingabeaufforderungssyntax (Gewichtungen, LoRA, Embeds), Metadatenwerte |

Alle selbst gehostet (Latin Extended Subset). Fraunces 176K / Inter 148K / JetBrains Mono 52K. SIL Open Font License v1.1.

Regenerieren über `scripts/build_atelier_fonts.py`.

## Zweistufige Akzente

| Token | Zweck | Light / Dark |
|---|---|---|
| `--accent-warm` | Dekorativ, Atmosphäre, Favoriten | `#c9a063` / `#d4a96e` |
| `--accent-tool` | Aktion, Fokuskontur, aktiver Zustand | `#2f5c8a` / `#5a8fc5` |

Die Trennung von Dekoration und Aktion macht UI-Affordanzen auf den ersten Blick eindeutig.

## --canvas (bildbereich-neutrales Grau)

AI-Bildbereiche (Modal-Bildbereich, Thumbnail-Raster) befinden sich auf einer **neutralen grauen Leinwand**, getrennt von der warm-gefärbten UI-Verkleidung, damit die Farbwahrnehmung der Bilder nicht beeinflusst wird:

- `--canvas`: `#d4d4d2` (light) / `#1a1a1a` (dark)
- `--canvas-raised`: `#c8c8c6` (light) / `#222222` (dark)

Chrome (`--bg`, `--surface`, `--surface-raised`) behält die warm-beige Familie bei.

## WCAG-Kontrastverifizierung

8 Paare × light/dark = 16 Fälle, behauptet durch `tests/test_atelier_wcag.py`. Body-Text 4.5:1, beiläufig (Fokuskontur / Eyebrow) 3:1.

```
uv run pytest tests/test_atelier_wcag.py
```

## Modal

- Bildbereich: `--canvas`
- Info-Panel: `--surface-raised` + Fraunces roman (kein Kursiv)
- Eingabeaufforderungs-Body: Fraunces roman; `(...:1.2)` und `<lora:...>` wechseln zu inline JetBrains Mono
- Werkzeugleiste (v4.126.2 kreisförmige Pillen): glass + accent-tool aktiv
- Schließen / Navigationspfeil / Fav-Schaltfläche: glass + accent-tool Fokuskontur
- Favorit aktiv: Warm-Akzent (dekorativ, getrennt von Tool-Blau)

## Header-Logo

Zweilinige Konstruktion:
- Zeile 1: `yu` (Fraunces 22pt)
- Zeile 2: `eauesque` (JetBrains Mono 9pt Signatur)

Eine redaktionelle Unterschrift, die die Markenhierarchie visualisiert. Legacy nav-brand bleibt für nicht-Atelier-Themes an Ort und Stelle.

## Dateien

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

## Barrierefreiheit

- `prefers-reduced-motion: reduce` bricht transform/animation ab (Opazitätsübergänge bleiben erhalten)
- `:focus-visible` überall verwendet `--accent-tool` 2px Kontur + 2px Versatz (WCAG 2.5.5 + 1.4.11)
- WCAG AA (4.5:1 Body, 3:1 beiläufig) verifiziert über 16 Paare

## Rollback-Pfad

Wenn etwas schief geht, Einstellungen → "Atelier Theme" → "Off" stellt sofort legacy light/dark wieder her. Benutzerdefinierte Themes (preset-*) sind nicht betroffen.
