# Guida allo sviluppo

Un manuale per estendere, personalizzare e fare il debug di questo software da soli.

---

## L'idea di base

Questo software è stato creato da un essere umano che dava istruzioni e lamentele a un agente IA.
Ogni riga di codice è stata scritta dall'IA.

In altre parole: **puoi fare la stessa cosa.**

Non devi essere un programmatore. Non devi chiedere all'autore. Tutto ciò di cui hai bisogno è la volontà di pensare chiaramente, spiegare con precisione e ripetere.

Non hai bisogno di quella cosa con testo bianco che scorre su uno schermo nero.
Abbandona prima quel preconcetto e quel pregiudizio.
Tutto può essere fatto visivamente ora. Che epoca per vivere.

---

## Prima di iniziare

### Ottenere YU AI Manager

Esegui semplicemente il programma di installazione.
Segui le istruzioni sullo schermo. È tutto.

Una cosa da ricordare:
Al momento non ci sono aggiornamenti automatici. Quando esce una nuova versione, esegui di nuovo il programma di installazione per sostituirlo.

### Connettere MCP

Apri YU AI Manager e vai su **Impostazioni → Chiavi API**.
C'è una sezione chiamata **Snippet di connessione MCP**. Copia il JSON con un clic.

Poi apri Claude Desktop e vai su **Impostazioni (icona a ingranaggio) → Sviluppatore → Modifica configurazione**.
Incolla il JSON copiato, salva e riavvia Claude Desktop.

È tutto. Questo è tutto ciò che serve per connettersi.

**Sulle chiavi API:** Se vuoi configurare manualmente senza lo Snippet, crea una chiave nelle stesse **Impostazioni → Chiavi API**. Le chiavi che iniziano con `sk_...` vengono mostrate solo una volta alla creazione. Copiala sul momento.

### Verifica il tuo ambiente

1. YU AI Manager è in esecuzione? — Avvialo e controlla
2. Il server MCP è in esecuzione? — Controlla nelle impostazioni di Claude Desktop
3. Hai accesso a un agente IA? — Claude Desktop, o qualcosa di equivalente

È tutto. Sei pronto.

---

## Usare MCP

Se il server MCP è in esecuzione, usalo. Punto.

YU AI Manager ha endpoint di aiuto integrati per gli agenti IA.
Tramite MCP, puoi accedere direttamente al database, ai log, alle impostazioni e **al codice sorgente stesso**.
Far guardare l'IA direttamente tramite MCP è più veloce e preciso che spiegare attraverso l'interfaccia del browser.

Di' semplicemente questo all'agente IA:

```
Connettiti al server MCP di YU AI Manager.
Controlla gli endpoint di aiuto e dimmi cosa puoi fare.
```

### Lascia che MCP legga il codice sorgente

YU AI Manager ha strumenti di riferimento al codice sorgente integrati.

- **source_tree** — Mostra la struttura dei file come albero
- **source_read** — Legge il contenuto di un file specificato
- **source_search** — Ricerca full-text nell'intero codice sorgente

Gli agenti IA possono usarli per leggere il codice sorgente direttamente nella chat.
Non è necessario aprire una cartella in GitHub Desktop e darla a Claude Code.

Quando vuoi che l'IA guardi il codice sorgente, di' questo:

```
Controlla la struttura dei file con source_tree,
poi leggi i file rilevanti con source_read.
```

---

## Aggiungere funzionalità

Non chiedere all'autore di aggiungere funzionalità al core. La risposta è no.

Usa il sistema di estensioni.
**Tutto il lavoro può essere fatto interamente nella chat di Claude Desktop.** Non devi lasciare la tua scrivania.

### Passo 1: Decidere cosa costruire nella chat

Non dire solo "costruiscilo" dal nulla.

Prima organizza quello che vuoi nella chat di Claude Desktop.
"Voglio questo tipo di funzionalità", "Voglio automatizzare questo tipo di operazione" — verbalizzalo attraverso la conversazione con l'IA.

Una volta che sei chiaro su cosa costruire, di' questo:

```
Crea un documento di specifica.
```

L'IA creerà la spec.

### Passo 2: Lasciaglielo costruire

Non devi spostarti a un banco di lavoro. Continua nella stessa chat:

```
La spec è pronta. Implementala come Estensione.
Crea l'impalcatura con create_extension, scrivi il codice con write_extension_file.
Verifica che non ci siano problemi con validate_extension.
```

L'IA creerà e modificherà i file di Estensione direttamente tramite MCP.
Alla tua scrivania, tutto viene fatto solo attraverso la chat.

**Ma se andare avanti è la tua decisione.**

Prendi i suggerimenti dell'IA come riferimento. Ma non sei obbligato a seguirli.
Sei tu quello con lo scopo, non l'IA.
Non delegare il tuo giudizio.

Quando sei d'accordo, lascia che implementi. Se qualcosa sembra sbagliato, dillo. Ripeti finché non funziona.

Quando l'Estensione è completa, riavvia YU AI Manager.
Una nuova Estensione apparirà in Impostazioni → Estensioni. Controlla i permessi, approvala, e funziona.

### Passo 3: Condividere (Opzionale)

Se hai costruito qualcosa di utile, puoi condividerlo.
Se altri lo useranno è una loro decisione. Abbiamo fatto, tu decidi.

---

## Segnalare bug

### Passo 1: Ottenere i log

Apri YU AI Manager e vai su **Impostazioni → Log**.
Copia i log intorno al momento in cui si è verificato il problema.

Se non riesci a trovare i log, descrivi quanto segue con precisione:
- Cosa hai fatto
- Cosa ti aspettavi
- Cosa è successo effettivamente

"Qualcosa non va" non è una descrizione.

### Passo 2: Fare uno screenshot o un video

Se il problema è visivo e le parole non possono descriverlo:

- **Screenshot**: `Windows + Shift + S`
- **Registrazione schermo**: `Windows + Shift + R`

Su Mac: Lo screenshot è `Cmd + Shift + 4`, la registrazione è `Cmd + Shift + 5`

Puoi trascinare le immagini direttamente nella chat.
Un'immagine vale molto più di mille parole di spiegazione confusa.

**Puoi anche condividere cosa sta succedendo nel browser.**

Premi `F12` nel browser. Si aprirà un pannello sul bordo dello schermo.
Non devi capirlo adesso. Ricorda solo questo.

Quando l'agente IA dice "apri F12 e controlla gli errori", è lì.
Se vedi elementi rossi e gialli, selezionali tutti, copiali e pasali all'agente così come sono.
Questo è tutto ciò che devi fare.

### Passo 3: Postarlo su GitHub

Posta i log e gli screenshot in un issue di GitHub.
L'autore potrebbe darci un'occhiata. Prima o poi. Nessuna garanzia.

Se vuoi che venga risolto ora, passa alla sezione successiva.

---

## Correggere i bug da soli (Consigliato)

Più veloce che aspettare l'autore. Davvero.

### Strumenti

**Chat di Claude Desktop + MCP.** È tutto.

Pensare, investigare, correggere — tutto fatto qui.
Puoi leggere e scrivere file di Estensione tramite MCP, e anche eseguire scansioni del codice.
Nient'altro necessario.

### Flusso di debug

Descrivi il problema nella chat di Claude Desktop.
Log, screenshot, cosa stavi facendo, cosa ti aspettavi — metti tutto dentro.

Con MCP, l'IA può leggere il codice sorgente direttamente e controllare lo stato del sistema. Digli:

```
Quando clicco su [X] in YU AI Manager, succede [Y]. Dovrebbe essere [Z].
Controlla i log del backend e lo stato tramite MCP.
Leggi anche il codice sorgente correlato con source_tree e source_read.
Identifica la causa e correggila.
```

L'IA identificherà la causa e proporrà una correzione.
Applica la correzione con write_extension_file e verifica con validate_extension.
Riavvia YU AI Manager e controlla il comportamento.

### Cosa dare all'agente IA

1. **Log di errore** — Il testo grezzo, non parafrasato
2. **Screenshot o video** — Per bug visivi
3. **Cosa stavi facendo** — L'operazione quando si è verificato il problema
4. **Cosa ti aspettavi** — Cosa avrebbe dovuto succedere
5. **Scopo** — Non solo il sintomo, ma perché ne hai bisogno

### Quando l'IA non capisce

L'IA non è umana. Non colmerà sempre le lacune che hai lasciato.

- Potrebbe fare domande — rispondi con precisione
- Potrebbe non funzionare come previsto — digli esattamente cosa è diverso
- Se continua a dare risposte fuori tema, riformula la tua richiesta
- Se ti accorgi che mancano informazioni, aggiungile
- Se le parole non arrivano, passa i file rilevanti

Questo è lavoro iterativo. Funziona. Continua.

È essenzialmente la stessa cosa che dare istruzioni a un umano. Tranne che non c'è ego, né umore, né sentimenti di cui preoccuparsi — quindi è molto più semplice.

---

## Prima ripulire ciò che è visibile

Prima di schiacciare bug invisibili, metti in ordine ciò che puoi vedere.
Spruzzare insetticida su un campo coperto di erbacce è inutile. Prima livellare il terreno.

Hai implementato qualcosa. Sembra che funzioni. Ma se la superficie stia effettivamente funzionando correttamente — spesso non puoi dirlo cliccando in giro da solo. Perdi cose. Smetti di notarle una volta che ti ci sei abituato.

Usa Playwright. L'agente IA opererà il browser e ispezionerà l'UI angolo per angolo.

Di' all'agente IA:

```
Usa Playwright per operare YU AI Manager e trovare bug UI/UX,
poi valuta e suggerisci miglioramenti da una prospettiva UX.
```

L'IA opererà il browser, individuando layout rotti, pulsanti morti, flussi non naturali, navigazione confusa — e li segnala. Non solo correzioni di bug, ma anche suggerimenti dalla prospettiva "questo è difficile da usare" arriveranno.

Se accettarli è la tua decisione, ma ascoltali tutti prima.

Una volta fatto questo, passa alle cose invisibili.

---

## Eliminare ogni bug invisibile

I bug visibili possono essere corretti. Il problema sono i bug invisibili.

Pensa allo spazio sotto il frigorifero. Vedi uno scarafaggio di fronte.
Ma sposta il frigorifero, e c'è tutto un altro mondo sotto.
Il software è uguale. Bug che non appaiono nei log, bug che non possono essere riprodotti, bug che nessuno ha attivato — esistono sicuramente. È quasi impossibile per un umano trovarli tutti.

Il debug MCP è l'insetticida per quello.

### Come

Di' all'agente IA:

```
Connettiti all'MCP di YU AI Manager e fai il debug dell'intero codice sorgente.
Usa source_tree per capire la struttura dei file, poi leggi i file con source_read.
Segnala tutti i bug potenziali, i problemi di coerenza e tutto ciò che potrebbe causare errori.
```

L'IA legge il codice sorgente, controlla lo stato effettivo del sistema tramite MCP e scova problemi che non si mostrano in superficie.
Quando arriva il rapporto, faglielo correggere.

### Essere persistenti

Non fermarsi a un round.

Quando l'IA dice "è tutto", rispondi con questo:

```
C'è altro?
```

Continua a ripetere questo. L'IA scava un po' più in profondità ogni volta.
Quando dice davvero "nient'altro", puoi fidarti che sia davvero finita.

Essere persistenti non è una virtù. Ma quando si tratta di bug, la persistenza è giustizia.

---

## Fare una revisione della sicurezza prima di pubblicare

Se intendi pubblicare un'Estensione, prima esegui una revisione della sicurezza.

Non è difficile. È veloce.

Di' semplicemente all'agente IA:

```
Fai una revisione della sicurezza di questa Estensione (o codice).
Controlla anche la configurazione e le informazioni sandbox di YU AI Manager tramite MCP.
Leggi i file rilevanti con source_read e segnala eventuali problemi.
```

YU AI Manager ha una funzione di scansione del codice integrata per le Estensioni.
Si esegue automaticamente quando un'Estensione viene caricata. Riavvia il server e carica l'Estensione una volta.

La scansione rileva automaticamente:
- Moduli pericolosi (`subprocess`, `ctypes`, `importlib`)
- Operazioni dirette sul DB (`sqlite3` — usa SandboxedDB)
- Esecuzione dinamica del codice (`eval`, `exec`, `__import__`)
- Accesso alla rete (`requests`, `urllib`, ecc.)

I problemi critici impediranno il caricamento dell'Estensione. Gli avvisi consentiranno il caricamento ma vengono registrati nei log.
Controlla i log e correggi tutti i problemi.

Se stai pubblicando codice che gira sul sistema di qualcun altro, assumiti quella responsabilità.

Per i dettagli sul modello di sicurezza, leggi "[Extension Security Model](docs/en/help/developer/extension-security.md)."

---

## Non toccare core

Con le Estensioni, sei in un mondo protetto.
Se cambi ciò che protegge — core e Estensioni integrate — non dimenticare mai che influenza tutto, e **tu stesso potresti essere travolto dall'esplosione.**

Se stai usando la versione Tauri, o in ogni caso, non puoi toccare core o Estensioni integrate da Claude Desktop.
Non "non dovresti" — è **impossibile come capacità**.
Il percorso API non esiste. Non puoi toccare ciò che non puoi vedere.

Se devi assolutamente toccarlo, usa la versione Python. È tutto.

---

## Sulla pazienza

Gli agenti IA sono potenti, ma non magici. Alcuni problemi richiedono più tentativi.

Quando ti senti frustrato:
- Fai un passo indietro
- Rileggi cosa gli hai detto
- Pensa a quale informazione manca
- Prova da un angolo diverso

I problemi si risolvono. Ciò di cui hai bisogno non è urlare, ma pensare chiaramente.

---

## Parole finali

L'autore ha costruito questo software in 18 giorni, dicendo all'IA cosa fare.
Ogni funzionalità, ogni correzione, ogni decisione di design è nata dalle conversazioni.

In altre parole, ciò che è scritto solo in questo documento è sufficiente per costruire qualcosa di quella portata.

I fondamentali sono tutti cose noiose.
Ma sono il primo passo nel posare le pietre di una diga.
Come impilare le pietre, come correggere l'angolo — lo impari lungo la strada.
I problemi complessi e difficili alla fine diventeranno anche risolvibili.

Tuttavia, se i fondamentali vengono trascurati, le cose crollano anche a scala modesta.

Non scartare ciò che è scritto sopra.
Per rendere il terreno solido, la cosa più importante è rendere la base delle proprie competenze solida come una roccia.

Gli strumenti sono qui. La documentazione è qui.

**Vai.**
