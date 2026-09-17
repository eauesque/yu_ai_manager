# Modello di Sicurezza delle Extension

Questo software si distingue per il fatto che "chiunque può creare Extension usando l'AI". Allo stesso tempo, sono integrati meccanismi per proteggere il sistema dalle Extension malintenzionate.

Questa pagina illustra come funziona tale meccanismo.
È scritto in modo comprensibile anche per i non tecnici.

---

## Concezione di Base

Le Extension **operano in un mondo protetto**.

All'interno di questo mondo protetto, le Extension possono agire con relativa libertà. Aggiungere pagine, visualizzare dati, elaborare immagini — questo è il lavoro delle Extension.

Tuttavia, quello che si trova **fuori** dal mondo protetto — il nucleo del sistema (core), le altre Extension, tutti i file del PC — è fisicamente irraggiungibile. Non è che sia "proibito da regole", ma è strutturalmente costruito in modo che **fisicamente non sia raggiungibile**.

---

## Meccanismo dei Permessi

Per fare qualcosa, le Extension hanno bisogno di **permessi**.

I permessi sono progettati con lo stesso modello dei permessi delle app sugli smartphone.

- È normale che un'app fotocamera richieda l'accesso alla fotocamera
- È strano che un'app fotocamera richieda l'accesso ai contatti

Le Extension sono uguali. Se un'Extension per aggiungere filigrane alle immagini richiede accesso alla rete, è giusto diffidarne.

### Flusso di Approvazione

1. Installa un'Extension (o falla creare dall'AI)
2. YU AI Manager esegue automaticamente una scansione del codice e ispeziona cosa intende fare
3. Viene mostrata la lista dei permessi richiesti dall'Extension
4. **L'Extension non funziona finché tu non la approvi**

Leggi attentamente le informazioni mostrate nella schermata di approvazione.
Presta particolare attenzione ai permessi visualizzati in rosso.

### Dopo l'Approvazione dei Permessi

L'Extension funziona nell'ambito dei permessi approvati. I permessi non approvati non sono semplicemente "rifiutati quando l'Extension cerca di usarli" — sono strutturalmente "invisibili".

---

## Tre Controlli Indipendenti

Le Extension sono monitorate da tre meccanismi indipendenti. Questi tre sono indipendenti tra loro, quindi anche se uno viene ingannato, gli altri due continuano a funzionare.

### 1. Scansione del Codice

Il codice dell'Extension viene automaticamente analizzato per rilevare pattern pericolosi. Esecuzione di programmi esterni, operazioni dirette sul database, esecuzione dinamica di codice — questi vengono rilevati immediatamente.

### 2. Controllo dei Permessi

Quando un'Extension chiama un'API, verifica se possiede una "licenza" valida. La licenza viene emessa solo quando si approvano i permessi. L'Extension stessa non può falsificare la licenza.

### 3. Registro di Audit

Tutte le operazioni delle Extension vengono registrate. Questo registro è salvato in un posto indipendente che non può essere sovrascritto dall'Extension stessa.

Se viene rilevata un'anomalia — ad esempio, se si tenta di eseguire un'operazione non dichiarata — viene inviata automaticamente una notifica e, se necessario, la licenza dell'Extension viene invalidata.

---

## Nel Caso di Extension Create con AI

Quando si crea un'Extension da Claude Desktop, l'Extension creata viene automaticamente registrata al **livello più restrittivo**.

È come non dare le chiavi della cassaforte a un nuovo dipendente fin dal primo giorno. Prima lo si fa lavorare con permessi limitati, si verifica che non ci siano problemi, e poi si aggiungono i permessi necessari.

### Cosa Può Fare un'Extension Creata dall'AI

**Utilizzabile senza approvazione:**
- Visualizzazione lettura dati
- Aggiunta pagine alla UI
- Aggiunta schermata di configurazione

**Richiede approvazione:**
- Comunicazione con servizi esterni
- Scrittura nel database
- Lettura di file

**Impossibile indipendentemente da cosa si fa:**
- Lettura o modifica del nucleo del sistema (core)
- Lettura o modifica di altre Extension
- Esecuzione di programmi esterni
- Falsificazione della licenza

---

## Ispezioni Periodiche

Un'Extension approvata una volta non è definitiva.

Se il codice viene modificato e la quantità di modifiche supera una certa soglia, viene richiesta la **ri-approvazione**. Questo impedisce la tecnica di modificare poco per volta finché, senza rendersene conto, si ottiene qualcosa di completamente diverso.

Inoltre, vengono automaticamente eseguite re-ispezioni periodiche del codice. Anche se non c'erano problemi al momento dell'approvazione, i problemi possono emergere con nuove regole di ispezione.

---

## Cosa Devi Fare

1. **Leggi attentamente la schermata di approvazione dei permessi** — Capisci cosa sta richiedendo prima di approvare
2. **Rifiuta richieste di permessi innaturali** — È strano che un'elaborazione immagini richieda la rete
3. **Non ignorare le notifiche** — Se viene rilevata un'anomalia, verificala
4. **Non installare Extension da fonti di cui non ti fidi** — È ovvio

Al contrario, se fai solo questo sei al sicuro. Il resto lo protegge il meccanismo.
