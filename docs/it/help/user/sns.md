# SNS Share e Bluesky Monitor

## Panoramica

SNS Share è un'estensione che permette di condividere direttamente su Bluesky e X (Twitter) le immagini generate con AI da YU AI Manager. Il testo del post viene generato automaticamente da un template personalizzabile, con sostituzione automatica delle variabili dei metadati dell'immagine. Bluesky Monitor aggiunge funzionalità di monitoraggio notifiche, con possibilità di triage AI e risposta automatica.

## Setup

### Ottenere Bluesky App Password

1. Accedere a [bsky.app](https://bsky.app) e aprire **Impostazioni > App Passwords**
2. Cliccare su **Aggiungi App Password**
3. Inserire il nome (es. "YU AI Manager") e cliccare **Crea App Password**
4. Copiare la password mostrata

> **Nota**: L'App Password è visibile solo in questa schermata. Copiarla prima di chiudere il dialogo. Non usare mai la password principale di Bluesky.

### Configurazione in YU AI Manager

1. Aprire **Settings** dal menu di navigazione
2. Passare alla scheda **SNS**
3. Inserire le seguenti informazioni:
   - **Handle Bluesky**: Nome handle (es. `yourname.bsky.social`)
   - **App Password**: L'App Password ottenuta sopra
   - **Template post**: Template per il testo del post (vedere [Variabili template](#variabili-template))
4. Cliccare **Salva**

## Funzionalità

### Condivisione su Bluesky

È possibile condividere direttamente le immagini su Bluesky dalla vista dettagliata.

1. Aprire il modale dettaglio dell'immagine
2. Cliccare sul pulsante **SNS**
3. Verificare e modificare il testo del post generato
4. Cliccare **Pubblica su Bluesky**

- Il testo del post viene generato espandendo le variabili dei metadati dal template configurato
- Le immagini vengono automaticamente compresse e ridimensionate per rispettare il limite di 1 MB di Bluesky
- I post sono limitati a **300 grapheme** (il testo in eccesso viene troncato automaticamente)
- È possibile scegliere se allegare o meno l'immagine

### Condivisione su X (Twitter)

Condivide le informazioni dell'immagine su X usando un Web Intent (apre la schermata di post di X nel browser).

1. Aprire il modale dettaglio dell'immagine
2. Cliccare sul pulsante **SNS**
3. Cliccare **Condividi su X**

Si apre la schermata di post di X in un nuovo tab del browser con il testo generato dal template. È possibile modificare il testo prima di pubblicare. Su X l'allegato automatico dell'immagine non è disponibile, è necessario allegarla manualmente.

### Bluesky Monitor

Bluesky Monitor fa il polling delle notifiche Bluesky e le accoda localmente per triage e risposta.

#### Tipi di Notifica

- **Menzioni**: Sei stato menzionato in un post
- **Risposte**: Qualcuno ha risposto al tuo post
- **Citazioni**: Il tuo post è stato citato
- **Seguaci**: Qualcuno ti ha seguito
- **Mi piace**: Il tuo post ha ricevuto un mi piace
- **Repost**: Il tuo post è stato repostato

#### Polling

Le notifiche vengono recuperate automaticamente a intervalli configurabili (default: 30 minuti, minimo: 5 minuti). È anche possibile attivare immediatamente il polling da Settings o dagli strumenti MCP.

#### Sistema di Coda

Ogni notifica viene inserita nella coda con stato **pending** (in attesa). Può poi transitare ai seguenti stati:

- **notified** — Notificato al client MCP (Claude Desktop)
- **dismissed** — Rifiutato come non necessario

#### Triage

Classificazione AI che determina se ogni notifica richiede attenzione:

- **valid** — Richiede attenzione (domanda, bug report, richiesta di collaborazione ecc.)
- **invalid** — Ignorabile (elogi generici, spam, contenuti bot ecc.)

Ci sono prompt di triage personalizzabili per tipo di notifica (menzione, risposta, citazione). Vengono forniti prompt predefiniti ripristinabili in qualsiasi momento.

#### Risposta Automatica

È possibile inviare risposte automatiche basate su template per menzioni/risposte/citazioni classificate come valid:

- Abilitare la risposta automatica nelle impostazioni Monitor
- Personalizzare i template di risposta per tipo di notifica
- Le risposte sono limitate a 300 grapheme

#### Auto-rifiuto

Seguaci, mi piace e repost possono essere automaticamente rifiutati per ridurre il rumore nella coda. Ogni tipo è regolabile individualmente in Settings.

## Integrazione MCP

SNS Share & Bluesky Monitor dispone di 15 strumenti MCP:

**Condivisione (6 strumenti)**:
- `share_to_bluesky` — Pubblica immagine su Bluesky
- `get_x_share_url` — Recupera URL Web Intent X
- `get_sns_preview` — Anteprima espansione template
- `test_bluesky_connection` — Test connessione API
- `get_sns_config` / `save_sns_config` — Recupero/salvataggio configurazione SNS

**Coda notifiche (5 strumenti)**:
- `bsky_get_pending_notifications` — Recupera notifiche non elaborate
- `bsky_get_notification_queue` — Recupera elementi coda con filtri
- `bsky_triage_notification` — Imposta risultato triage (valid/invalid)
- `bsky_send_auto_response` — Invia risposta alla notifica
- `bsky_poll_notifications` — Attiva immediatamente il polling

**Configurazione Monitor (4 strumenti)**:
- `bsky_get_monitor_config` / `bsky_save_monitor_config` — Recupero/salvataggio configurazione Monitor
- `bsky_get_triage_prompts` / `bsky_save_triage_prompts` — Recupero/salvataggio prompt triage e template risposta

## Variabili Template

Variabili utilizzabili nei template post:

| Variabile | Descrizione |
|-----------|-------------|
| `{positive_short}` | Prompt positivo (primi 100 caratteri) |
| `{positive}` | Testo completo prompt positivo |
| `{negative_short}` | Prompt negativo (primi 50 caratteri) |
| `{model}` | Nome modello |
| `{seed}` | Valore seed |
| `{steps}` | Numero step di sampling |
| `{cfg}` | CFG scale |
| `{sampler}` | Nome sampler |
| `{size}` | Dimensione immagine |
| `{tags}` | Top 5 tag |
| `{filename}` | Nome file |

Template predefinito: `{positive_short}`

## Suggerimenti

- **Sicurezza App Password**: Usare sempre l'App Password, non la password principale di Bluesky. L'App Password può essere disabilitata in qualsiasi momento dalle impostazioni di bsky.app
- **Rate limit**: Le API Bluesky hanno limiti di rate. Evitare post consecutivi. Anche l'upload di immagini viene conteggiato nel rate limit
- **Conteggio Grapheme**: Bluesky usa i grapheme cluster, non i caratteri, per il limite di 300 caratteri. I caratteri CJK vengono contati come 1 grapheme
- **Compressione immagini**: Le immagini oltre 1 MB vengono ridimensionate automaticamente. Se la preparazione dell'immagine fallisce, il post viene pubblicato solo con testo
- **Intervallo polling Monitor**: Impostare l'intervallo di polling in base al volume di notifiche
- **Auto-rifiuto**: Abilitare l'auto-rifiuto di seguaci, mi piace e repost permette di concentrarsi sulle notifiche che richiedono attenzione

## Configurazione

Settings > SNS tab per configurare account.

### Bluesky

1. Accedi Bluesky
2. Copia handle (@user.bsky.social)
3. Genera app password (non account password)
4. Paste handle e password in settings

### X (Twitter)

1. Crea API app su developer.twitter.com
2. Genera Bearer token
3. Paste in settings

### Mastodon

1. Seleziona istanza Mastodon
2. Crea app in Preferences > Development
3. Copia access token
4. Paste in settings

## Condivisione immagini

From image detail modal, bottone "Share SNS" per post con:
- Immagine (thumbnail)
- Prompt principale
- Model name
- Link condivisione pubblica

## Privacy

- Solo dati pubblici condivisi
- Confida user approval prima post
- Token salvati crittografati in secret store
