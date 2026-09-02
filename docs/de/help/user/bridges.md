# Bridge-Integrationenn

Mit der Bridge-Funktion können Sie Eingabeaufforderungen direkt von YU AI Manager an verschiedene AI-Bildgeneratoren senden.

## Unterstützte Bridges

### SD WebUI Bridge
Integration mit Stable Diffusion WebUI (Automatic1111 / Forge).
- Prompt-Austausch
- Parameter-Übertragung

### NAI Bridge
Integration mit NovelAI.
- Automatische Prompt-Syntax-Konvertierung (SD ↔ NAI)
- Automatische Qualitäts-Tag-Einfügung

#### Vibe Transfer (NovelAI-Trank) und encode-vibe-Cache

NAI V4+-Modelle erfordern eine Vorverarbeitung von Referenzbildern über `/ai/encode-vibe`
(**2 Anlas pro Aufruf**), bevor sie in Generierungsanfragen genutzt werden können.

Um Anlas-Verschwendung bei wiederholten Generierungen mit demselben Bild zu vermeiden,
werden Kodierungsergebnisse lokal gecacht:

```
data/nai_vibe_cache/<sha256>__<model>__<info_extracted>.bin
```

- **Schlüssel**: SHA256 des Rohbilds + Modellname + Informationsextraktionsgrad (0,01-Schritte)
- **Maximalgröße**: 500 MB standardmäßig. Änderbar unter Settings > NAI Bridge > „Vibe encode cache (MB)" (0 = deaktiviert)
- **LRU-Verdrängung**: Bei Überschreitung des Limits werden älteste Einträge im Hintergrund gelöscht

### ComfyUI Bridge
Integration mit ComfyUI.
- Prompt-Einfügung in Workflows
- Angepasstes Output-Format

## Stapel-Generierung

Alle drei Bridges unterstützen Stapel-Generierung im Haupt-Generierungspfad (A1111-kompatible Semantik).

### Batch count / Batch size

- **Batch count** — Anzahl der aufeinanderfolgenden Generierungsdurchläufe (zeitliche Richtung). Der Client ruft die API einmal pro Iteration auf.
- **Batch size** — Anzahl der parallel generierten Bilder pro API-Aufruf (VRAM-Richtung). In NAI Bridge nicht angezeigt.
- Gesamtbilder = Batch count × Batch size

Bei festem Seed wird der Seed im Loop als `base + i` inkrementiert (gleiche Verhaltensweise wie A1111). Bei `-1` (zufällig) wird jedes Mal ein neuer zufälliger Seed verwendet.

### Stop-Buttons

| Bridge | Einzeldurchlauf (count=1) | Loop (count>1) |
|---|---|---|
| NAI | Kein Stop-Button | Nur „Nach aktuellem Bild stoppen" |
| SD WebUI | „Stop" (Server-Cancel-API) | „Nach aktuellem Bild stoppen" + „Stop" |
| ComfyUI | „Stop" (Server-Cancel-API) | „Nach aktuellem Bild stoppen" + „Stop" |

- **Stop (sofort)** — Bricht den laufenden API-Aufruf ab und stoppt den Loop. Bei SD WebUI / ComfyUI wird auch die Server-Cancel-API aufgerufen.
- **Nach aktuellem Bild stoppen** — Lässt das aktuelle Bild fertig generieren und überspringt dann die nächste Iteration.

NAI Bridge zeigt keinen Stop-Button für die Einzel-Generierung, weil die NAI API Anlas (Credits) verbucht, sobald der fetch-Request akzeptiert wird. Das Unterbrechen der HTTP-Verbindung stoppt weder die serverseitige Generierung noch erstattet sie die Kosten — daher würde ein Stop-Button nur zu Verwirrung führen.

### VRAM-Hinweis

Eine höhere Batch size erhöht den VRAM-Verbrauch auf der Server-GPU proportional zur Bildanzahl. Bei SDXL mit Batch size 4 oder mehr kann es zu OOM kommen — beginnen Sie mit 1 und erhöhen Sie schrittweise.

## Qualitäts-Presets

Nutzen Sie den „QP"-Button in der Bridge-Toolbar, um Qualitäts-Verbesserungs-Tags in einem Klick einzufügen.

Integrierte Presets:
- SD High Quality
- SD Realistic
- NAI Quality
- NAI Artistic
- Minimal

Benutzerdefinierte Presets sind ebenfalls möglich.

## Auflösungs-Presets

SD WebUI Bridge und ComfyUI Bridge haben über Width/Height-Eingabe ein „Resolution Preset"-Dropdown und ⇄ Swap-Button. Häufige Auflösungen können mit einem Klick eingegeben werden.

- **SD 1.5** — Für SD1.5-Modelle, 5 Varianten basierend auf 512
- **SDXL Trained** — SDXL-offizielle Lern-Buckets, 9 Varianten (beste Qualität)
- **SDXL Cheat Sheet** — 12 Varianten mit Film/Foto-Seitenverhältnissen auf 8er-Vielfache (Komposition-Fokus, von [Civitai](https://civitai.com/articles/2246/sdxl-image-size-cheat-sheet))

Wenn Sie „Custom" wählen, bleibt der aktuelle W/H-Wert erhalten. Nach Preset-Anwendung können Sie W/H manuell ändern, und es kehrt automatisch zu „Custom" zurück. Mit dem ⇄-Button können Sie Width und Height tauschen.

Die Cheat Sheet-Auflösungen liegen außerhalb der offiziellen Buckets, daher können einige Modelle leichte Kompositionsveränderungen zeigen.

> In ComfyUI Bridge wird dies nur im Simple-Modus angewendet. Raw JSON Workflow-Modus-Knotenwerte sind nicht betroffen.

## Bridge-zu-Bridge-Transfer

Prompts können direkt zwischen Bridges übertragen werden. Zwischen SD und NAI wird Syntax automatisch konvertiert.

