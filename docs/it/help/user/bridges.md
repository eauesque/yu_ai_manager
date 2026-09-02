# Integrazione Bridge

Con la funzione Bridge, puoi inviare prompt direttamente ai vari strumenti di generazione di immagini IA da YU AI Manager.

## Bridge supportati

### SD WebUI Bridge
Integrazione con Stable Diffusion WebUI (Automatic1111 / Forge).
- Invio/ricezione prompt
- Trasferimento parametri generazione

### NAI Bridge
Integrazione con NovelAI.
- Conversione automatica sintassi prompt (SD ↔ NAI)
- Inserimento automatico quality tag

#### Vibe Transfer (pozione NovelAI) e cache encode-vibe

I modelli NAI V4+ richiedono la pre-codifica delle immagini di riferimento tramite `/ai/encode-vibe`
(**2 Anlas per chiamata**) prima che possano essere usate nelle richieste di generazione.

Per evitare sprechi di Anlas durante generazioni ripetute con la stessa immagine, i risultati
di codifica vengono memorizzati nella cache locale:

```
data/nai_vibe_cache/<sha256>__<model>__<info_extracted>.bin
```

- **Chiave**: SHA256 dell'immagine raw + nome del modello + informazione estratta (passi da 0,01)
- **Dimensione massima**: 500 MB predefinita. Modificabile in Settings > NAI Bridge > "Vibe encode cache (MB)" (0 = disabilitato)
- **Eliminazione LRU**: i file più vecchi vengono eliminati in un thread in background quando il limite viene superato

### ComfyUI Bridge
Integrazione con ComfyUI.
- Inserimento prompt nel workflow
- Personalizzazione formato output

## Generazione in batch

Tutti e tre i Bridge supportano la generazione in batch nel percorso di generazione principale (semantica compatibile con A1111).

### Batch count / Batch size

- **Batch count** — Numero di esecuzioni di generazione sequenziali (asse temporale). Il client chiama l'API una volta per iterazione.
- **Batch size** — Numero di immagini generate in parallelo per chiamata API (asse VRAM). Non visualizzato in NAI Bridge.
- Totale immagini = Batch count × Batch size

Con seed fisso, il seed viene incrementato come `base + i` a ogni iterazione del loop (stesso comportamento di A1111). Con `-1` (casuale), viene usato un seed casuale diverso ogni volta.

### Bottoni di stop

| Bridge | Singola esecuzione (count=1) | Loop (count>1) |
|---|---|---|
| NAI | Nessun bottone stop | Solo «Ferma dopo l'attuale» |
| SD WebUI | «Stop» (API cancel del server) | «Ferma dopo l'attuale» + «Stop» |
| ComfyUI | «Stop» (API cancel del server) | «Ferma dopo l'attuale» + «Stop» |

- **Stop (immediato)** — Interrompe la chiamata API in corso e ferma il loop. Per SD WebUI / ComfyUI viene chiamata anche l'API cancel del server.
- **Ferma dopo l'attuale** — Lascia completare l'immagine in corso, poi salta l'iterazione successiva.

NAI Bridge non mostra il bottone stop per la generazione singola perché l'API NAI addebita Anlas (crediti) nel momento in cui accetta il fetch. Interrompere la connessione HTTP non ferma la generazione lato server né rimborsa il credito — un bottone stop causerebbe solo confusione.

### Nota sulla VRAM

Aumentare il Batch size incrementa il consumo di VRAM della GPU del server proporzionalmente al numero di immagini. Con SDXL e Batch size 4 o superiore possono verificarsi errori OOM; inizia da 1 e aumenta gradualmente.

## Quality Preset

Nel toolbar di ogni Bridge, il bottone "QP" consente di inserire tag di aumento qualità con un click.

Preset built-in:
- SD High Quality
- SD Realistic
- NAI Quality
- NAI Artistic
- Minimal

Puoi creare anche preset personalizzati.

## Resolution Preset

SD WebUI Bridge e ComfyUI Bridge hanno un dropdown "Resolution Preset" e pulsante ⇄ Swap sopra gli input Width/Height. Inserisci risoluzioni comuni con un click.

- **SD 1.5** — 5 varianti basate su 512 per modelli SD 1.5
- **SDXL Trained** — 9 varianti bucket training ufficiale SDXL (priorità qualità massima)
- **SDXL Cheat Sheet** — 12 varianti con aspect ratio approssimati multipli di 8 per cinema/fotografia (priorità composizione, fonte [Civitai](https://civitai.com/articles/2246/sdxl-image-size-cheat-sheet))

Con `Custom` selezionato conserva valori W/H esistenti. Dopo applicazione preset, se editi W/H manualmente torna automaticamente a `Custom`. Pulsante ⇄ scambia Width e Height.

Le risoluzioni Cheat Sheet sono fuori dai bucket ufficiali, quindi alcuni modelli potrebbero avere leggera distorsione compositiva.

> Per ComfyUI Bridge si applica solo in Simple mode. Raw JSON Workflow mode non è influenzato da valori nodi.

## Trasferimento tra Bridge

Puoi trasferire prompt direttamente tra Bridge. La sintassi tra SD ↔ NAI si converte automaticamente.
