# Bridge Clipboard-Verknüpfung

Auf den NAI Bridge / ComfyUI Bridge / SD WebUI Bridge-Seiten ermöglicht eine Tastenkombination das sofortige Einfügen von Zwischenablage-Text in das Eingabefeld. Wenn Sie eine Eingabeaufforderung aus einem anderen Fenster kopiert haben, können Sie diese anwenden, ohne zuerst in das Textfeld klicken zu müssen.

## Verknüpfung

| Betriebssystem | Tasten |
|---|---|
| Windows / Linux | `Ctrl` + `Alt` + `V` |
| macOS | `⌘` + `⌥` + `V` |

Dies wird neben dem nativen Einfügen des Browsers (`Ctrl`+`V`) hinzugefügt und beeinträchtigt das vorhandene Einfügeverhalten nicht.

## Verhalten

1. Öffnen Sie eine der Bridge-Seiten
2. Kopieren Sie Text aus einer externen Quelle (`Ctrl`+`C`)
3. Drücken Sie `Ctrl`+`Alt`+`V`, während die Bridge-Seite fokussiert ist
4. Zielauswahl:
   - Wenn ein Textfeld fokussiert ist → an der Cursor-Position in diesem Textfeld eingefügt
   - Wenn nichts fokussiert ist → in das positive Eingabefeld eingefügt (NAI: `#nabPrompt` / ComfyUI: `#cfbPrompt` / SD: `#sdwbPrompt`)
5. Bei Erfolg wird ein Toast "Clipboard text inserted" angezeigt

## Zielfelder

| Bridge | Zielpriorität |
|---|---|
| NAI Bridge | `nabPrompt` → `nabNegative` |
| ComfyUI Bridge | `cfbPrompt` → `cfbNegative` → `cfbWorkflowJson` |
| SD WebUI Bridge | `sdwbPrompt` → `sdwbNegative` |

## Browser-Berechtigungen

Dies verwendet die **Clipboard API** des Browsers (`navigator.clipboard.readText()`), daher kann der Browser Sie bei der ersten Verwendung zur Bestätigung der Berechtigung zum Lesen der Zwischenablage auffordern. Wenn Sie diese ablehnen, funktioniert die Funktion nicht.

Bei älteren Browsern, auf denen die Clipboard API nicht verfügbar ist, wird ein Toast "Clipboard API not available" angezeigt und nichts geschieht. Das reguläre `Ctrl`+`V`-Einfügen funktioniert weiterhin wie zuvor.

## Einschränkungen

- Einige Browser erfordern HTTPS oder `localhost` für `navigator.clipboard` (Chrome erlaubt `localhost`)
- Nur Klartext wird unterstützt — keine Bilder oder formatierter Text
- Nicht-`<textarea>`-Elemente (z. B. `contenteditable`-Regionen) werden auch wenn fokussiert nicht berücksichtigt
