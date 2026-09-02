# YU AI Manager

Una WebUI per gestire i metadati delle immagini generate da IA.

## Panoramica

Uno strumento WebUI per estrarre, cercare e gestire i metadati (prompt, modelli, seed, ecc.) incorporati nelle immagini generate da IA.

**Cosa puoi fare:**

- Scansiona cartelle o archivi ZIP in blocco per registrare le immagini automaticamente
- Ricerca e filtra per prompt, tag, nome del modello, valore seed e altro
- Invia immagini a SD / ComfyUI / NovelAI istantaneamente per la rigenerazione
- Auto-tagging con WD-Tagger, analisi con Ollama/OpenAI
- Accedi da un telefono o un altro dispositivo sulla tua LAN tramite codice QR

**Sorgenti supportate**: Stable Diffusion (A1111/Forge), NovelAI V3/V4, ComfyUI

## Requisiti

- Windows / Linux / macOS

> **Nessuna installazione manuale.** `start.sh` / `start.bat` esegue il bootstrap di tutti gli strumenti necessari nell'albero del progetto (nessuna modifica al sistema, nessun privilegio di amministratore).

## Installazione e avvio

```bash
git clone https://github.com/eauesque/yu_ai_manager.git
cd yu_ai_manager

# Windows
start.bat

# macOS / Linux
./start.sh
```

Installazione automatica al primo avvio:

| Strumento | Modalità di installazione |
| --- | --- |
| `uv` | Scaricato automaticamente in `./bin/uv` |
| Python 3.11+ | Installato automaticamente da `uv` |
| Node.js 22 LTS | Opzionale — chiede se scaricarlo in `./bin/node/` (~30 MB) |
| pnpm | Attivato tramite `corepack` una volta presente Node.js |
| ffmpeg | Opzionale — su Windows/macOS chiede se scaricarlo in `./bin/ffmpeg/` (~80 MB), su Linux mostra il comando `apt`/`dnf`/`pacman` specifico della distribuzione |

Imposta `YU_AUTO_INSTALL=1` per saltare le richieste in ambienti non interattivi (CI, ecc.). ffmpeg è richiesto solo dalle estensioni video / speech-to-text / OCR — l'app stessa si avvia senza.

Gli avvii successivi riutilizzano l'ambiente e reinstallano/ricompilano solo quando cambiano i manifest delle dipendenze o i sorgenti TypeScript.

Aggiungi `--db`, `--port`, `--lan`, `--pin`, ecc. in `launch-args.txt` per una configurazione persistente.

## Funzionalità principali

### Scansione e registrazione
- Estrazione automatica dei metadati da PNG / WebP / JPEG
- Scansione trasparente di archivi ZIP / 7z (senza estrazione)
- Aggiunta di file tramite drag & drop

### Ricerca e navigazione
- Ricerca full-text per prompt, tag, nome del modello, valore seed
- Ricerca regex, filtri multi-condizione
- Ricerca di immagini simili tramite pHash, ricerca semantica CLIP

### Organizzazione
- Preferiti, valutazioni a stelle (1–5), note (annotazioni)
- Collezioni (raggruppamento)
- Dashboard delle statistiche, report mensili, sistema di trofei

### Bridge con strumenti di generazione
- Trasferimento istantaneo dei prompt a SD WebUI / Forge / ComfyUI / NovelAI
- Trasferimento tramite clipboard supportato

### Assistenza IA
- Auto-tagging WD-Tagger
- Analisi del contenuto delle immagini tramite Ollama / OpenAI
- Speech-to-text (S2T)

### Rete e condivisione
- Modalità condivisione LAN (accesso tramite codice QR dal telefono)
- Server MCP (integrazione di agenti IA)
- Gestione flotta (controllo centralizzato di più istanze)

### Personalizzazione
- Sistema di UI personalizzata ed estensioni
- Supporto temi (chiaro / scuro)
- App desktop Tauri (nessun browser richiesto)

## Lingue

English / 日本語 / 繁體中文 / 简体中文 / 한국어

## Documentazione

- [Avvio rapido](docs/en/help/user/quickstart.md)
- [Casi d'uso](docs/en/help/user/use-cases.md)
- [Riferimento API](docs/en/api/README.md)
- [Ottimizzazione delle prestazioni](docs/en/help/user/performance-tuning.md)
- [Deployment](docs/en/help/user/deployment.md)
- [Sviluppo di estensioni](docs/en/plugin-development/getting-started.md)
- [UI personalizzata](docs/en/custom-ui/README.md)
- [Strumenti MCP](docs/en/api/MCP_TOOLS_REFERENCE.md)
- [Tutti i documenti](docs/en/README.md)

## Sviluppo e personalizzazione

Vedi [DEVELOPMENT.it.md](DEVELOPMENT.it.md) ([English](DEVELOPMENT.en.md))

## Quando hai un problema — chiedi all'IA

### Se non si avvia

Apri il progetto in Claude Code Desktop o un altro agente AI con il seguente messaggio:

> `start.bat` (oppure `start.sh`) non si avvia. Investigare.

> **Nota**: In Claude Code Desktop devi specificare la cartella del progetto prima di iniziare la conversazione.

### Problemi, impostazioni, utilizzo dopo l'avvio

**Passaggio 1 — Ottenere il contesto**

Apri la pagina di aiuto (`/help`) e premi il pulsante **"Copia contesto AI"**.
Usa la sessione del browser acceduto per eseguire il fetch di `GET /api/ai-context` e copiare il JSON negli appunti (funziona anche in ambienti LAN http://).

> **Nota (se hai una chiave API)**: Se hai una chiave API con scope admin, puoi chiamare direttamente `GET /api/ai-context` con l'intestazione `Authorization: Bearer <key>`.

**Passaggio 2 — Passarlo all'IA**

Incolla il JSON copiato nel chat IA e continua con la tua domanda:

> [JSON incollato]
> Dato questo, [descrizione del problema], risolvilo.

`/api/ai-context` contiene la versione corrente, le funzionalità abilitate, i suggerimenti di configurazione, l'elenco delle API e le regole CSRF — tutto ciò che l'IA ha bisogno per aiutarti in modo accurato.

## FAQ

[docs/en/FAQ.md](docs/en/FAQ.md)

## Segnalazione di bug

[GitHub Issues](https://github.com/eauesque/yu_ai_manager/issues)

## Licenza

MIT License — [LICENSE](LICENSE) / [Versione semplificata](docs/en/LICENSE.md)
