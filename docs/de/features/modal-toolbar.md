# Modal-Werkzeugleiste

Die einheitliche Werkzeugleiste am unteren Rand des Detail-Modals bietet Zugriff auf alle primären Steuerelemente während der Bild-/Videoansicht.

## Struktur

### Primäre Leiste (immer sichtbar)

**Modus für Standbilder:**
- ☆ Favorit
- ⓘ Info-Panel umschalten
- ‹ › Zurück / Weiter
- Zoom (− / 100% / +)
- Anpassungsmodus (fit / fit-w / fit-h / fit-custom + Höhe / original)
- Spread 2P / Richtung ↔ (falls zutreffend)
- ⛶ Immersiv / ⤢ Vollbild
- 📁 Sammlung
- Bridge Senden (Eingabeaufforderung senden ▾ / Bild senden ▾)

**Video-/Audiomodus (2-schichtiges Layout):**
- Oben: Zeitanzeige + Suchleiste (max. 720px Breite)
- Unten: ☆ Fav / ⓘ Info / ‹ › / ▶ Abspielen ⏪ ⏩ / ♪ Stummschaltung + Lautstärke / ⛶ ⤢ / 📁

### Überfluss-Menü (… Schaltfläche)

Konsolidiert selten verwendete Operationen in einer vertikalen Liste:
- Automatische Wiedergabe + Intervall
- Wiederholen / Geschwindigkeit / Fortsetzen (für Video)
- FPB / Zeichenraster (für Standbilder)
- ZIP / Container-Ansicht
- Tastaturleitfaden ?
- Werkzeugleiste einklappen «

## Tastaturkürzel

| Taste | Aktion |
|---|---|
| `T` | Sichtbarkeit der Werkzeugleiste umschalten |
| `V` | Immersiver Modus |
| `F` | Vollbild |
| `I` | Info-Panel |
| `H` | Tastaturleitfaden |
| `P` | Automatische Wiedergabe |
| `Space` / `K` | Abspielen / Pause (Video) |
| `J` / `0` | Zurückspulen (Video) |
| `L` | Schneller Vorlauf (Video) |
| `M` | Stummschaltung (Video) |
| `R` | Wiederholen (Video) |
| `←` / `→` | Vorheriges / nächstes Bild |
| `ESC` | Überfluss-Menü schließen → Modal in Reihenfolge |

## Einklappen und Wiederherstellen

Methoden zum Einklappen der Werkzeugleiste:
- Wählen Sie im Überfluss-Menü (…) "Werkzeugleiste einklappen"
- Drücken Sie die Taste `T`

Methoden zum Wiederherstellen:
- Klicken Sie auf den Kantengriff in der unteren Bildschirmmitte
- Drücken Sie die Taste `T` erneut

Die Position des Kantengriffs wird beim eingeklappten Zustand automatisch an das Vorhandensein eines Filmstreifens angepasst.

## Barrierefreiheit

- Die gesamte Werkzeugleiste hat `role="toolbar"`
- Die Überfluss-Schaltfläche verwendet `aria-haspopup="menu"` / `aria-expanded` wird dynamisch aktualisiert
- Menüelemente im Überfluss haben `role="menuitem"`
- Der Kantengriff ist eine Standard-`<button>` die mit Eingabe / Leertaste bedienbar ist
- Um WCAG 2.5.5 (Zielgröße) zu erfüllen, hat der visuell 8px Griff eine 24px-hohe unsichtbare Trefferfläche, die über `::before` erweitert wird
