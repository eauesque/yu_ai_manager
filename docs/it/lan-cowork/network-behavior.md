# Comportamento di rete di LAN Cowork (cosa accade sulla LAN)

> Destinazione: v4.538.0 e successivi di Rust standalone (`yu-server`). Per configurazioni ibride con backend Python,
> consultare la sezione "Differenze dalla versione Python" alla fine di questa pagina.

Questa pagina riassume **"cosa inizia a fare il tuo server sulla rete quando abiliti LAN Cowork"**.
Leggi questa sezione prima di modificare le impostazioni.

---

## Punti chiave

- **Per impostazione predefinita non fa nulla.** Rust standalone non ascolta né annuncia nulla sulla LAN
  a meno che non sia esplicitamente abilitato tramite le impostazioni descritte di seguito.
- Se abilitato, il server **diviene rilevabile dai nodi sulla stessa LAN**. Questo è il comportamento previsto dalla progettazione.
- **L'assenza di PIN non interrompe l'annuncio di discovery.** Per dettagli, consulta "Relazione con il PIN (punto facilmente frainteso)".

---

## Cosa accade quando è abilitato

| Operazione | Descrizione |
|---|---|
| **Ascolto UDP** | Si effettua il binding su `0.0.0.0:19850` (tutte le interfacce) |
| **Annunci periodici** | Ogni 10 secondi, trasmette un messaggio HELLO firmato a `255.255.255.255:19850`. Il contenuto include l'ID del nodo, la chiave pubblica, la porta API, il nome host e altro ancora |
| **Registrazione di altri nodi** | Verifica la firma dei messaggi HELLO ricevuti e registra i nodi remoti nell'elenco dei peer locali (TOFU) |
| **Ricezione HTTP in ingresso** | Gli endpoint per i peer riportati nella tabella seguente iniziano a rispondere |
| **Distribuzione locale** | Gli eventi peer accettati vengono inviati all'SSE (`/api/events/stream`) sottoscritto dalla schermata di login |
| **Pulizia della scadenza** | Ogni 60 secondi rimuove dalla memoria le richieste di abbinamento scadute e i PIN in testo non crittografato |

### Endpoint ricevuti in ingresso

| Endpoint | Autenticazione |
|---|---|
| `GET /ext/lan_cowork/api/peer/discover` | **Nessuna sessione richiesta** (interrogazione dell'elenco dei peer) |
| `GET /ext/lan_cowork/api/peer/status` | **Nessuna sessione richiesta** (descrittore del nodo stesso) |
| `POST /ext/lan_cowork/api/peer/register` | **Nessuna sessione richiesta** (auto-registrazione del peer; il server convalida la destinazione della registrazione) |
| `POST /ext/lan_cowork/api/peer/pair/request` / `pair/verify` | **Nessuna sessione richiesta** (inizio dell'abbinamento; i peer non accoppiati non possono avere una sessione) |
| `POST /ext/lan_cowork/api/peer/token/renew` | Firma + nonce (Bearer non richiesto) |
| `POST /ext/lan_cowork/api/peer/event` / `heartbeat` | Firma + token Bearer |

"Nessuna sessione richiesta" significa **non richiedere una sessione di login**, non significa **nessuna autenticazione**.
Poiché i peer non abbinati non possono avere una sessione di login, questi 5 percorsi rimangono aperti come eccezione.
Tutti gli altri percorsi richiedono l'accesso come al solito.

---

## Come abilitare e disabilitare

Cambiare tramite la sezione **`extensions`** di `config.json`.

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "enabled": true
    }
  }
}
```

- **Se la chiave non è presente, la funzione è "disabilitata"** (Rust standalone).
- È necessario **riavviare** per applicare le modifiche.
- Se desideri cambiare temporaneamente, puoi specificare anche tramite opzioni di avvio. L'ordine di priorità è
  **riga di comando > `config.json` > variabile di ambiente > impostazione predefinita**.

| Metodo | Abilita | Disabilita |
|---|---|---|
| Riga di comando | `--native-daemon` | `--no-native-daemon` |
| Variabile di ambiente | `YU_LAN_COWORK_NATIVE_DAEMON=1` | Lo stesso con `=0` |

> La variabile di ambiente interpreta come "abilitato" solo `1` / `true` / `yes`. `on` e `Y` vengono **trattati come disabilitati**.

### Verifica se è abilitato

```bash
curl -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5000/ext/lan_cowork/api/peer/status
```

| Risposta | Significato |
|---|---|
| `200` | Abilitato. La funzionalità peer è in esecuzione |
| `405` | **Disabilitato** (la funzione non è incorporata) |
| `503` | Abilitato ma non pronto (chiavi specifiche del nodo non generate o inizializzazione interna non riuscita) |

> **Non puoi fare affidamento sulla visualizzazione dell'elenco delle estensioni nella schermata.** L'elenco delle estensioni
> potrebbe mostrare LAN Cowork come "abilitato", ma questa visualizzazione si basa sulle informazioni fornite in bundle,
> ed è **indipendente dal fatto che il daemon descritto sopra sia effettivamente in esecuzione**.
> Per determinare lo stato, usa la risposta dell'endpoint sopra o la riga `native_daemon=...` nei log di avvio.

---

## Relazione con il PIN (punto facilmente frainteso)

**Non è accurato pensare che, se non hai impostato un PIN, nulla sulla LAN può accedere.**

- **Corretto**: Per utilizzare `--lan` (ascolto su tutte le interfacce), un PIN è obbligatorio e, se assente, l'avvio si ferma.
  L'ascolto predefinito è `127.0.0.1`, quindi **in un avvio normale la parte HTTP non è raggiungibile dalla LAN**.
- **Avvertenza 1**: Se specifichi direttamente l'IP della LAN con `--host`, il controllo di obbligatorietà del PIN viene ignorato.
  Inoltre, se il PIN non è impostato, il gate di accesso stesso si apre, quindi **evita di esporre il server alla LAN senza PIN**.
- **Avvertenza 2**: **L'annuncio UDP è indipendente dalla presenza di un PIN.** Se abilitato,
  anche un nodo senza PIN annuncia la propria presenza sulla LAN ogni 10 secondi. Il PIN limita solo l'esposizione HTTP.

In altre parole, **il PIN limita l'esposizione della parte HTTP, ma non interrompe l'annuncio di discovery.**

### Quando l'ascolto è solo su loopback (v4.539.0 e successive)

Se l'indirizzo di ascolto è solo loopback (il valore predefinito `127.0.0.1`, che vale anche per la versione desktop),
**questo nodo non si annuncia sulla LAN**. Gli altri nodi non potrebbero connettersi anche se si annunciasse.
Dopo l'avvio viene registrato una sola volta il seguente avviso (è WARN, non INFO, quindi è visibile per impostazione predefinita).

```
LAN Cowork discovery inactive: server listens on loopback only; bind a LAN address or use --lan
```

Per usarlo sulla LAN, associa un indirizzo LAN oppure usa `--lan` (`--lan` richiede un PIN).

> Prima di v4.539.0, un listener solo loopback annunciava un IP LAN. I peer potevano scoprirlo,
> ma non connettersi; per questo il comportamento è stato modificato.

---

## Cose da sapere prima di abilitare

- **Anche se disabiliti la funzione, le informazioni sui peer registrate mentre era abilitata non vengono eliminate automaticamente.** Inoltre,
  **al primo avvio dopo l'abilitazione**, viene eseguita una pulizia dei vecchi record peer
  (i record non raggiungibili da più di 7 giorni e quelli non abbinati per più di 1 ora vengono eliminati).
  Ti consigliamo di fare un backup di `tags.db` prima di cambiare l'impostazione.
- Gli eventi peer ricevuti vengono inviati all'SSE (`/api/events/stream`) sottoscritto dalla schermata di login. **Il contenuto è input dal nodo remoto**
  (l'ID del mittente viene sostituito con un valore autenticato dal lato server).
- Nel log vengono registrati **solo il numero, il tipo e l'ID del mittente**, non il contenuto dell'evento.
- Se desideri controllare l'attività, abilita il livello INFO nei log
  (ad es. `RUST_LOG=yu_server=info`). Con le impostazioni predefinite, le righe che indicano la ricezione di eventi peer non vengono emesse.

---

## Differenze dalla versione Python

| | Backend Python ibrido | Rust standalone |
|---|---|---|
| Impostazione predefinita | **Abilitato** (se non presente in `config.json`, è abilitato) | **Disabilitato** (richiede un'abilitazione esplicita) |
| Implementazione | Gestito dall'estensione Python | Gestito da `yu-server` |

**Rust standalone è intenzionalmente "disabilitato per impostazione predefinita".** Questo per evitare che il comportamento di rete
cambi con il solo aggiornamento. Il comportamento della configurazione ibrida rimane invariato.

> Nel primo tempo della documentazione, l'impostazione di abilitazione veniva indicata come `{"lan_cowork": {"enabled": true}}`
> (al livello superiore), ma **questa chiave non viene letta da nessuna implementazione.** La sezione `extensions` sopra indicata è
> la posizione corretta.
