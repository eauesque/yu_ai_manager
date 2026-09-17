# Autenticazione PIN Peer-to-Peer e Token Pairing

**Versione di implementazione**: 4.92.0
**File correlati**: `extensions/builtin_lan_cowork/`, `core/lan_cowork_core/`

---

## Panoramica

Prima della v4.92, la comunicazione tra peer in LAN utilizzava solo l'header `X-Peer-Id` per identificare il partner. Questo header poteva essere falsificato da chiunque in LAN, rendendo la sicurezza insufficiente.

Dalla v4.92, si è passati al metodo **token pairing basato su approvazione PIN**.

- Al primo collegamento viene inviata una "richiesta di pairing"
- L'amministratore del partner approva dalla schermata di gestione ed emette un PIN a 6 cifre
- Inserendo il PIN viene emesso un Bearer token (valido 30 giorni)
- Le comunicazioni successive vengono autenticate con `Authorization: Bearer <token>`

Il vecchio metodo con header `X-Peer-Id` può mantenere la compatibilità con le impostazioni, ma le operazioni DELETE richiedono sempre la nuova autenticazione.

---

## Flusso di Pairing

```
[Peer A (origine)]                     [Peer B (destinazione)]
       |                                      |
       |--- POST /api/lan/pair/request ------->|
       |    (peer_id, display_name, public_key)|
       |                                      |
       |                              L'amministratore verifica/approva su /lan-cowork/peers
       |                                      |
       |<--- SSE: peer_pairing.pin_ready ------|
       |    (PIN 6 cifre, scadenza 5 minuti)  |
       |                                      |
       |--- POST /api/lan/pair/verify -------->|
       |    (peer_id, pin)                     |
       |                                      |
       |<--- 200 OK: { token, expires_at } ----|
       |    (Bearer token, valido 30 giorni)   |
       |                                      |
       |--- Seguono Authorization: Bearer <token>
```

### Dettagli di Ogni Step

| Step | Endpoint | Descrizione |
|------|----------|-------------|
| 1. Invio richiesta | `POST /api/lan/pair/request` | Invio peer ID, nome visualizzato, chiave pubblica |
| 2. Attesa approvazione | — | L'amministratore verifica su `/lan-cowork/peers` |
| 3. Emissione PIN | — | L'amministratore preme il pulsante approva per generare il PIN a 6 cifre (valido 5 minuti) |
| 4. Verifica PIN | `POST /api/lan/pair/verify` | Invio PIN e ricezione Bearer token |
| 5. Comunicazione autenticata | — | Aggiunta header `Authorization: Bearer <token>` |

---

## Schermata di Gestione (`/lan-cowork/peers`)

### Richieste in Attesa di Approvazione

Quando arriva una richiesta di pairing da un nuovo peer, viene visualizzata nella scheda "In attesa di approvazione" della schermata di gestione.

- **Approvazione**: Genera un PIN e lo notifica al peer richiedente via SSE
- **Rifiuto**: Elimina la richiesta. Il peer richiedente riceve 403

### Lista Peer Connessi

Visualizza la lista dei peer con pairing completato e la scadenza di ogni token.

| Colonna | Contenuto |
|---------|-----------|
| Nome visualizzato | Nome del peer |
| Indirizzo IP | Ultimo IP di connessione verificato |
| Scadenza | Data di scadenza del Bearer token (30 giorni) |
| Ultima connessione | Orario dell'ultimo heartbeat |
| Operazioni | Pulsante revoca token |

### Revoca Token

Premendo il pulsante "Revoca", il Bearer token del peer target viene invalidato immediatamente. Alla comunicazione successiva viene restituito 401 e il peer tenta automaticamente il re-pairing.

---

## Impostazioni

Le impostazioni si modificano nella sezione `lan_cowork` di `config.json`, o dalla scheda "LAN Collaborazione" nella schermata delle impostazioni.

### `ip_check_mode`

Specifica il metodo di verifica dell'indirizzo IP di origine.

| Valore | Comportamento |
|--------|---------------|
| `strict` | Permette solo corrispondenza esatta con l'IP al momento dell'emissione del token (predefinito) |
| `cidr` | Permette se nell'intervallo CIDR specificato in `allowed_cidr` |
| `rfc1918` | Permette tutti gli indirizzi IP privati (192.168.x.x / 10.x.x.x / 172.16-31.x.x) |

### `allow_legacy_auth`

Specifica se mantenere la compatibilità con il vecchio metodo di autenticazione tramite header `X-Peer-Id`.

- `true`: Permette alcune operazioni solo con l'header `X-Peer-Id` (predefinito: `true`)
- `false`: Rifiuta tutte le connessioni senza Bearer token

> **Nota**: Le operazioni che usano il metodo DELETE (interruzione scansione, eliminazione forzata ecc.) richiedono sempre il Bearer token indipendentemente dall'impostazione `allow_legacy_auth`.

### `protect_heartbeat`

Specifica se richiedere autenticazione anche per l'endpoint heartbeat (`/api/lan/heartbeat`).

- `true`: Anche il heartbeat richiede il Bearer token
- `false`: Il heartbeat passa senza autenticazione (predefinito: `false`)

### `protect_events`

Specifica se richiedere autenticazione anche per lo stream SSE di eventi (`/api/events/`).

- `true`: Anche la connessione SSE richiede il Bearer token
- `false`: L'SSE passa senza autenticazione (predefinito: `false`)

---

## Note sulla Sicurezza

### Hash dei Token

I Bearer token emessi **non vengono salvati in chiaro** nel database. Vengono salvati dopo l'hashing con scrypt (N=16384, r=8, p=1). Anche in caso di fuga del DB, il token originale non può essere ripristinato.

### Mascheramento dei Log

- L'header `Authorization: Bearer <token>` viene automaticamente sostituito con `Bearer [REDACTED]` nell'output dei log
- Anche i PIN non rimangono nei log

### Rate Limiting

Per prevenire attacchi DoS e brute force, si applicano i seguenti rate limit.

| Endpoint | Limite |
|----------|--------|
| `POST /api/lan/pair/request` | 10 al minuto/IP |
| `POST /api/lan/pair/verify` | 30 al minuto/IP |

Il PIN scade automaticamente dopo 5 minuti e può essere verificato solo una volta per richiesta.

---

## Risoluzione dei Problemi

### La Richiesta di Pairing Non Arriva

- Verificare che l'URL del peer partner sia impostato correttamente
- Verificare che la porta non sia bloccata dal firewall
- Verificare lo stato di ricezione di `pair/request` nei log del peer partner

### Il PIN è Scaduto

La validità del PIN è di 5 minuti. Se scaduto, premere di nuovo il pulsante "Approva" nella schermata di gestione per emettere un nuovo PIN.

### Il Token ha Smesso di Funzionare Improvvisamente

Le possibili cause sono:

1. L'amministratore ha revocato il token dalla schermata di gestione
2. La validità di 30 giorni è scaduta
3. L'indirizzo IP è cambiato con `ip_check_mode: strict`

Eseguire il re-pairing.

### Dopo aver Impostato `allow_legacy_auth` su `false` Non si Riesce a Connettersi

Se i peer esistenti usano ancora il vecchio metodo di autenticazione, tutti ricevono 401. Completare il re-pairing su ogni peer, poi passare a `allow_legacy_auth: false`.

## Pairing

Due peer si accoppiano tramite codice QR o link condivisione:

1. Apri Settings > LAN Cowork su peer A
2. Genera QR code
3. Scansiona da peer B
4. Conferma su entrambi

## Certificati TLS

Peer generano automaticamente cert TLS auto-firmati.
Verificati per fingerprint, non chain CA.

## Refresh token

Token refresh ogni 24 ore automaticamente.
Revoca manuale disponibile in Settings.

## Troubleshooting

- Peer non visibile: verifica firewall UDP 5353 (mDNS)
- Connection timeout: controlla latenza rete
- Auth fallita: ripeti pairing
