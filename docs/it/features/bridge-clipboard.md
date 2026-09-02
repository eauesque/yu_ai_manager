# Scorciatoia degli Appunti del Bridge

Sulle pagine NAI Bridge / ComfyUI Bridge / SD WebUI Bridge, un tasto di scelta rapida ti permette
di inviare istantaneamente il testo degli appunti nel campo del prompt. Quando hai copiato un prompt
da un'altra finestra, puoi applicarlo senza dover prima fare clic sulla textarea.

## Scorciatoia

| SO | Tasti |
|---|---|
| Windows / Linux | `Ctrl` + `Alt` + `V` |
| macOS | `⌘` + `⌥` + `V` |

Questo si affianca alla funzione di incolla nativa del browser (`Ctrl`+`V`) e non
interferisce con il comportamento di incolla esistente.

## Comportamento

1. Apri una delle pagine Bridge
2. Copia il testo da una fonte esterna (`Ctrl`+`C`)
3. Premi `Ctrl`+`Alt`+`V` mentre la pagina Bridge ha il focus
4. Selezione della destinazione:
   - Se una textarea è in focus → inserito nella posizione del cursore in quella textarea
   - Se nulla è in focus → inserito nel campo del prompt positivo (NAI: `#nabPrompt` / ComfyUI: `#cfbPrompt` / SD: `#sdwbPrompt`)
5. Al completamento, viene mostrato un messaggio "Clipboard text inserted"

## Campi di Destinazione

| Bridge | Priorità di destinazione |
|---|---|
| NAI Bridge | `nabPrompt` → `nabNegative` |
| ComfyUI Bridge | `cfbPrompt` → `cfbNegative` → `cfbWorkflowJson` |
| SD WebUI Bridge | `sdwbPrompt` → `sdwbNegative` |

## Permessi del Browser

Questa funzione utilizza l'**API degli Appunti** del browser (`navigator.clipboard.readText()`),
quindi il browser potrebbe chiederti il permesso di lettura degli appunti al primo utilizzo.
Se lo neghi, la funzione non funzionerà.

Nei browser più vecchi in cui l'API degli Appunti non è disponibile, viene mostrato un messaggio
"Clipboard API not available" e non accade nulla. Il normale incolla `Ctrl`+`V` continua a funzionare come prima.

## Limitazioni

- Alcuni browser richiedono HTTPS o `localhost` affinché `navigator.clipboard` sia disponibile (Chrome consente `localhost`)
- È supportato solo testo semplice — non immagini o testo ricco
- Gli elementi non `<textarea>` (ad es. le aree `contenteditable`) non vengono targetizzati
  anche quando in focus
