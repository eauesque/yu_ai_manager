# Integrazione GitHub

## Panoramica

GitHub Integration è un'estensione che permette di gestire centralmente da YU AI Manager repository GitHub, issue, pull request, discussion e release. Supporta account multipli GitHub e i token vengono crittografati e conservati in modo sicuro. Dal dashboard è possibile verificare rapidamente notifiche e statistiche repository, con funzionalità di triage issue automatico tramite AI.

## Setup

### Ottenere un Personal Access Token (PAT) GitHub

1. Accedere a GitHub e aprire **Settings > Developer settings > Personal access tokens > Tokens (classic)**
2. Cliccare su **Generate new token (classic)**
3. Inserire il nome del token e impostare la scadenza
4. Spuntare **`repo`** negli scope (necessario per accesso completo al repository)
5. Cliccare su **Generate token** e copiare il token mostrato

> **Nota**: Il token viene mostrato solo in questa schermata. Copiarlo prima di chiudere.

### Aggiunta di un Account

1. Cliccare sulla scheda **GitHub** dal launcher Extension, o accedere direttamente a `/ext/github`
2. Aprire la scheda **Settings**
3. Cliccare su **Aggiungi account**
4. Inserire le seguenti informazioni:
   - **Etichetta**: Nome visualizzato dell'account (es. "Personale", "Lavoro")
   - **Token**: Il PAT ottenuto sopra
   - **Repository**: Inserire i repository da monitorare in formato `owner/repo` (multipli possibili)
5. Dopo il salvataggio, selezionare l'account dal menu a tendina

## Funzionalità

### Dashboard

Selezionando un account, il dashboard si carica automaticamente.

- **Notifiche**: Lista notifiche GitHub non lette
- **Statistiche repository**: Visualizzazione a card di stelle, fork e issue aperte
- **Schede riepilogative**: Panoramica dei repository monitorati a colpo d'occhio

### Issue

- Filtraggio per repository e stato (open/closed)
- Visualizzazione dettagliata issue (testo, commenti, etichette)
- Creazione nuova issue
- **Funzionalità triage**: Classificazione automatica issue tramite AI
  - `valid_bug` — Bug report valido
  - `needs_info` — Informazioni aggiuntive necessarie
  - `skip` — Nessun intervento necessario
- **Coda issue**: Polling automatico nuove issue GitHub e accodamento locale. Notifica aggregate degli elementi non letti quando il client MCP (Claude Desktop) si connette.

### Pull Request

- Lista e filtraggio PR
- Visualizzazione statistiche diff (righe aggiunte/eliminate/file modificati)
- Verifica contenuto delle modifiche per file nella vista dettagliata

### Discussion

- Recupero lista discussion tramite GraphQL API
- Visualizzazione badge categorie e badge risposta

### Release

- Lista ultime release dei repository monitorati
- Verifica note di release

### Impostazioni

- Aggiunta, modifica, eliminazione e abilitazione/disabilitazione account
- Visualizzazione residuo rate limit API
- Configurazione filtro lingua e intervallo di schedulazione
- Configurazione intervallo polling coda issue, chiusura automatica issue non valide, notifiche connessione MCP
- Modifica prompt triage per issue, PR e discussion ([vedi esempi](/help/github-triage-examples))

### Coda Issue

La coda issue esegue periodicamente il polling di GitHub e salva le nuove issue localmente.

- **Polling**: Esecuzione automatica tramite scheduler (intervallo configurabile, default 60 minuti)
- **Notifiche**: Notifica aggregata degli issue non elaborati a Claude Desktop alla connessione MCP
- **Triage**: Classificazione di ogni issue in coda come valido/non valido
- **Chiusura automatica**: Chiusura automatica su GitHub degli issue classificati non validi con commento template
- **Polling manuale**: Cliccare "Poll Now" in Settings per recupero immediato

### Prompt di Triage

È possibile personalizzare le istruzioni AI usate per il triage di issue, PR e discussion.

- Prompt modificabili separati per ogni tipo (Issue, PR, Discussion)
- Prompt predefiniti forniti, ripristinabili in qualsiasi momento con "Ripristina predefinito"
- Per template multilingua e vari stili vedere [esempi prompt triage](/help/github-triage-examples)
- I prompt vengono salvati in config.json (non crittografati poiché non contengono informazioni riservate)

## Integrazione MCP

GitHub Integration dispone di 12 tool MCP e può essere operato direttamente da Claude Code.

- Recupero lista/dettaglio issue
- Recupero lista/dettaglio PR
- Recupero notifiche
- Recupero e aggiornamento prompt triage
- Gestione coda issue (lista non elaborati, triage, rifiuto, polling)

Usando i tool MCP è possibile consultare informazioni GitHub senza lasciare l'IDE durante l'editing del codice.

## Suggerimenti

- **Account multipli**: È più gestibile separare gli account per uso personale e lavorativo
- **Permessi token**: Con scope `repo` tutte le funzionalità base sono utilizzabili. Per repository privati di organizzazioni è necessaria un'ulteriore autorizzazione SSO
- **Utilizzo del triage**: Per repository con molte issue, il triage automatico è efficiente per classificare le priorità
- **Rate limit**: Le API GitHub hanno un limite di richieste per ora. Il residuo è verificabile dalla scheda Settings
- **Sicurezza token**: I token vengono crittografati e salvati lato server. Non vengono mai salvati in chiaro

## Setup

1. Settings > GitHub tab
2. Genera token GitHub personal access
3. Incolla token in settings
4. Autentica connessione

## Funzioni

- **Issue reporting**: Segnala bug direttamente da app
- **Issue polling**: Monitora issue assegnati
- **Auto-comment**: Commenta automaticamente con metadata
- **Workflow trigger**: Attiva GitHub Actions

## Polling impostazioni

Settings > Scheduler, configura `github_issue_poll` frequency.
Intervalli consigliati: 5min - 1ora.

## Permessi token richiesti

- `repo` — Accesso repository
- `workflow` — Trigger Actions
- `issues` — Gestione issue

## Troubleshooting

- Token scaduto: Rigenera
- Rate limit: Aumenta polling interval
- Auth fallita: Verifica token permessi
