# Linee guida per la sicurezza dell'API

Utilizza questo documento ogni volta che aggiungi o modifichi un endpoint dell'API.

## Prima decisione

Ogni endpoint deve essere classificato in anticipo come uno dei seguenti:

- `public`
- `session/user`
- `admin`
- `localhost-only`

Se non sei sicuro, scegli `admin`.

## Regole fondamentali

1. Non assumere che `GET` sia sicuro.
2. Le `read-only API keys` sono solo per letture semplici.
3. I percorsi interni, inventari, cronologia, contenuti, registri e risultati di analisi sono `admin`.
4. I controlli localhost devono utilizzare helper consapevoli del proxy.
5. Gli endpoint di configurazione richiedono allowlist e validazione rigorosa.
6. I segreti devono essere crittografati e oscurati attraverso helper condivisi.

## Non sicuro per le chiavi di sola lettura

- percorsi interni
- inventari di ID file/membro
- prompt, annotazioni, trascrizioni, registri di chat
- risultati OCR / analisi
- coda, cronologia, audit, approvazione, programmatore, stato di errore della scansione
- stato backend di estensione / profilo / backup / webhook / secret
- risultati recuperati con credenziali di terze parti archiviate

## Controlli localhost

Non usare direttamente:

```
request.remote_addr == "127.0.0.1"
```

Utilizza invece helper esistenti:

- `get_client_ip()`
- `is_local_request()`
- `is_loopback_request()`

## Regole endpoint di configurazione

Obbligatorio:

- allowlist di chiavi
- validazione del tipo rigorosa
- validazione di intervallo / enum / URL
- offuscamento del secret nelle letture
- archiviazione crittografata per i segreti

Vietato:

- `config.update(...)` cieco
- `bool(value)` per i booleani della richiesta
- fusioni generiche che aggirare la gestione dei segreti

## Segreti

- non restituire mai i valori del secret corrente
- non includere mai token/header/blob secret negli endpoint dell'elenco
- non sovrascrivere mai i secret esistenti con segnaposti mascherati
- utilizzare sempre un archivio dedicato o helper condiviso

## Richieste in uscita dalle API

Non effettuare sonde a monte o ricerche di individuazione dagli endpoint `GET`.

Se inevitabile:

- richiedi `admin`
- mantieni i timeout brevi
- blocca localhost / IP privato / destinazioni di metadati

## Test minimi

Per gli endpoint sensibili, aggiungi:

1. `read-only key -> 403`
2. `admin key -> 200`
3. `invalid input -> 400`
4. controlli di offuscamento del secret
5. test di regressione localhost consapevoli del proxy dove pertinente

## Checklist di revisione

- È questo `GET` veramente sicuro per l'accesso pubblico/sola lettura?
- Espone percorsi, inventari, prompt, trascrizioni, cronologia o metadati grezzi?
- Divulga segreti?
- Utilizza helper consapevoli del proxy?
- Evita la coercizione booleana implicita?
- Evita le fusioni di configurazione cieche?
- Evita le richieste in uscita non intenzionali?
- Include test di regressione dell'ambito amministrativo?

Politica predefinita: inizia limitato, quindi apri deliberatamente solo quando necessario.
