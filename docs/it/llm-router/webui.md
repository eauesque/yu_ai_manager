# WebUI del LLM Router

Un dashboard amministrativo accessibile in `/llm-router`. Consente di controllare lo stato dei backend registrati e abilitarli/disabilitarli.

---

## Layout della Pagina

```
┌─────────────────────────────────────┐
│  🤖 LLM Router          [Refresh All] │
├─────────┬─────────┬────────┬─────────┤
│Backends │ Enabled │ Models │ Aliases │  ← Schede di riepilogo
├─────────┴─────────┴────────┴─────────┤
│  Tabella Backends                    │
├───────────────────────────────────────┤
│  Tabella Routing Aliases             │
└───────────────────────────────────────┘
```

### Schede di Riepilogo (4)

| Scheda | Contenuto |
|---|---|
| **Backends** | Numero totale di backend registrati nel catalogo |
| **Enabled** | Numero di backend che non sono disabilitati |
| **Models** | Numero totale di modelli esposti da tutti i backend |
| **Routing aliases** | Numero di alias definiti nel file di configurazione |

I valori delle schede vengono renderizzati automaticamente recuperando `/api/llm_router/status` al caricamento della pagina.

---

## Tabella Backends

Ogni riga corrisponde a un singolo backend fisico (ad es. un'istanza Ollama).

### Descrizioni delle Colonne

| Colonna | Descrizione |
|---|---|
| **Alias** | Un nome breve univoco che identifica il backend (ad es. `ollama-mac`, `mdns-pi5-hailo`). Utilizzato come chiave per la configurazione del routing e la risoluzione dell'alias |
| **Base URL** | L'URL di base dell'endpoint compatibile con OpenAI del backend (ad es. `http://192.168.1.10:11434`) |
| **Status** | Stato di connettività del backend. Vedi i dettagli di seguito |
| **SLO** | Stato del carico di risorse del backend (`vision_idle` / `vision_active` / `unknown`). Utilizzato per i backend Hailo Vision |
| **Models** | Numero di modelli recuperati nell'ultima sonda. Potrebbe essere espandibile per mostrare un elenco dettagliato a seconda dell'implementazione |
| **Last Seen** | Data e ora dell'ultima risposta riuscita (ISO 8601). `null` se nessuna risposta riuscita è mai stata ricevuta |
| **Actions** | Pulsanti di azione per singolo backend (vedi di seguito) |

### Valori di Status

| Valore | Significato |
|---|---|
| `ready` | L'ultima sonda ha avuto successo e l'elenco dei modelli è stato recuperato |
| `unreachable` | Si è verificato un timeout di connessione o un errore |
| `unknown` | Nessuna sonda è stata ancora eseguita (ad es. subito dopo l'avvio) |
| `probing` | Una sonda è attualmente in corso (potrebbe apparire brevemente nell'UI durante un Refresh) |

> **Suggerimento**: i backend `unreachable` sono esclusi dal routing ma rimangono nel catalogo. Dopo il ripristino della rete, esegui Refresh All o un Refresh individuale per ripristinarli a `ready`.

### Valori SLO

| Valore | Significato |
|---|---|
| `vision_idle` | L'attività Vision è inattiva. Il carico LLM è basso |
| `vision_active` | Un'attività Vision è in esecuzione. Il router LLM potrebbe dare priorità ad altri backend |
| `unknown` | Le informazioni SLO non sono disponibili (backend non-Hailo, o il recupero ha fallito) |

---

## Pulsante Refresh All

Fai clic su **Refresh All** in alto a destra per forzare una sonda su tutti i backend, aggiornando i loro elenchi di modelli e stati.

- Il pulsante è disabilitato durante l'esecuzione e la pagina viene nuovamente renderizzata al completamento
- Comportamento interno: Chiama `POST /api/llm_router/refresh` (nessun corpo) per eseguire `discover_all` per tutti i backend
- I refresh individuali dei backend potrebbero essere disponibili tramite un pulsante Refresh nella colonna Actions (dipendente dall'implementazione)

---

## Disabilitazione / Abilitazione di Singoli Backend

### Passaggi

1. Guarda la colonna **Actions** nella tabella dei backend
2. Fai clic sul pulsante **Disable** sulla riga del backend che vuoi disabilitare
3. Il pulsante cambia in **Enable** e la riga viene evidenziata in grigio
4. Per riabilitare, fai clic su **Enable**

### Comportamento e Persistenza

- Le modifiche vengono riflesse immediatamente nel catalogo in memoria
- Contemporaneamente, viene eseguita una scrittura atomica in `data/llm_router_state.json`

  ```json
  {
    "version": 1,
    "disabled_aliases": ["ollama-slow", "mdns-pi5"]
  }
  ```

- Lo stato disabilitato è preservato tra i riavvii dell'applicazione
- Se un backend scoperto da mDNS era disabilitato prima dell'avvio, lo stato disabilitato viene automaticamente applicato dopo la scoperta (meccanismo `_pending_disabled`)
- Se la scrittura fallisce, lo stato in memoria viene ripristinato per evitare incoerenza con il disco

### Comportamento dei Backend Disabilitati

- Esclusi dal routing negli endpoint compatibili con OpenAI come `/v1/chat/completions`
- Il routing diretto a un backend disabilitato restituisce `503 Service Unavailable`
- I backend disabilitati appaiono comunque nella tabella WebUI (per la visibilità dello stato e la riabilitazione)

---

## Tabella Routing Aliases

Visualizza il mapping tra i nomi di modelli logici e gli ID dei modelli fisici come definito nel file di configurazione.

| Colonna | Descrizione |
|---|---|
| **Alias** | Il nome logico che i client specificano nel parametro `model` (ad es. `default-llm`, `fast-chat`) |
| **Physical Model** | L'ID del modello fisico che elabora effettivamente la richiesta (formato: `backend-alias/model-name`, ad es. `ollama-mac/qwen2.5:7b`) |

### Ruolo degli Alias

Gli alias consentono di scambiare backend o modelli senza modificare il codice del client.

- I client inviano richieste utilizzando un nome logico come `"model": "default-llm"`
- Il LLM Router risolve `default-llm → ollama-mac/qwen2.5:7b` e indirizza la richiesta
- Quando si migra un backend a un'altra macchina, basta cambiare l'obiettivo dell'alias

Gli alias sono definiti staticamente nel file di configurazione e il WebUI li visualizza in modalità sola lettura. Le modifiche richiedono la modifica del file di configurazione e il riavvio dell'applicazione.

---

## Operazioni Comuni

### Quando un Backend è Non Raggiungibile

1. Verifica che il servizio backend (Ollama, ecc.) sia in esecuzione
2. Esegui **Refresh All** o un Refresh individuale
3. Se il problema persiste, controlla i dettagli dell'errore nella colonna `last_error` (o nella risposta API)

### Disabilitazione Permanente di un Backend Scoperto da mDNS

1. Fai clic su **Disable** nella colonna Actions del backend target
2. L'alias viene salvato in `data/llm_router_state.json`, quindi rimane disabilitato anche dopo la ri-scoperta

### Arresto Temporaneo del Carico su uno Specifico Backend

Usa **Disable** per escluderlo immediatamente dal routing, quindi **Enable** per ripristinarlo al termine. Non è necessario alcun riavvio.
