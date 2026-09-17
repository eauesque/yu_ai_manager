# Raccolta Casi d'Uso

Raccolta degli utilizzi tipici di YU AI Manager in formato "in questo caso si usa così".

---

## 1. Organizzare Grandi Quantità di Immagini AI

Quando si hanno migliaia di immagini generate con NovelAI o Stable Diffusion accumulate in cartelle e diventa difficile consultarle.

### Procedura

1. Registrare la cartella di scansione nella scheda **Settings > Scan** (multipli possibili)
2. Dopo l'aggiunta della cartella, la scansione si avvia automaticamente. È possibile anche scansionare all'interno di ZIP/7z
3. Dopo il completamento della scansione, filtrare le immagini nella pagina principale tramite ricerca tag (es. `1girl, blue_eyes`) o ordinamento
4. Selezionare le immagini preferite, tasto destro > **Aggiungi alla collezione** per raggruppare
5. Le collezioni sono consultabili in qualsiasi momento dalla barra laterale per gruppo

### Suggerimenti

- La ricerca e la navigazione sono disponibili anche durante la scansione
- Abilitando l'estensione Auto Scan Watcher, le nuove aggiunte alla cartella vengono rilevate automaticamente
- Anche con scala di milioni di elementi, la paginazione è veloce con Keyset Pagination

---

## 2. Cercare Immagini Generate con un Prompt Specifico

Quando non si ricorda un prompt di una certa composizione passata.

### Procedura

1. Cambiare il target di ricerca nella barra di ricerca a **in_prompt**
2. Inserire la parola chiave ricordata (es. `cherry blossom`) e cercare
3. Con le espressioni regolari si può filtrare in modo più flessibile (es. `masterpiece.*cherry`)

---

## 3. Trovare Immagini con Composizione Simile

Quando si pensa "doveva esserci un'altra immagine con un'atmosfera simile a questa".

### Metodo A: Ricerca Similarità pHash (composizione/colori)

1. Aprire il modale dettaglio dell'immagine
2. Cliccare il pulsante **Cerca immagini simili**
3. Le immagini con composizione vicina vengono elencate nel pannello laterale tramite pHash

### Metodo B: Ricerca Semantica CLIP (significato/concetto)

1. Cliccare il pulsante **Ricerca Semantica** a destra della barra di ricerca
2. Inserire una descrizione in linguaggio naturale (es. "ragazza in piedi in riva al mare")
3. CLIP comprende il significato delle immagini e le visualizza in ordine di similarità

---

## 4. Gestire le Immagini Preferite

Quando si vogliono consultare rapidamente solo i capolavori tra le grandi quantità di immagini.

### Procedura

1. Registrare i preferiti con il **pulsante cuore** sulla card immagine o nel modale dettaglio
2. Impostare la **valutazione a stelle** (1~5 livelli) nel modale dettaglio per valutare la qualità
3. Lasciare note libere nelle **annotazioni** (es. "Candidato al ritocco", "Già pubblicato su SNS")
4. Filtrare con "Solo preferiti", "Stelle 4+" ecc. nei filtri di ricerca

---

## 5. Inviare il Prompt di un'Immagine ad Altro Strumento

Quando si vuole riutilizzare il prompt di un'immagine passata per generare variazioni con un altro strumento.

### Procedura

1. Aprire il modale dettaglio dell'immagine e verificare le informazioni prompt
2. Cliccare il pulsante **Invia a SD WebUI** / **Invia a ComfyUI** / **Invia a NAI**
3. Si apre la pagina Bridge con il prompt pre-compilato
4. Modificare il prompt se necessario ed eseguire con lo strumento di generazione

### Suggerimenti

- Tra SD e NAI la sintassi dei pesi `()` e `{}` viene convertita automaticamente
- Con il pulsante **QP** nella toolbar del Bridge è possibile inserire preset qualità con un clic
- È possibile inviare ai vari Bridge anche da Prompt Converter o Prompt Simulator

---

## 6. Visualizzare Immagini in Archivi ZIP/7z

Quando si vuole verificare il contenuto di un set di immagini scaricato in un ZIP senza estrarlo.

### Procedura

1. Registrare la cartella contenente i file ZIP/7z in Settings > Scan
2. Abilitare **Scansione dentro ZIP/7z** nelle opzioni di scansione
3. Dopo il completamento della scansione, le immagini nell'archivio sono ricercabili e visualizzabili come le normali immagini
4. Nel modale dettaglio vengono mostrati il nome dell'archivio e il percorso interno

---

## 7. Condividere Immagini con il Team o la Famiglia

Quando si vogliono far visualizzare immagini da altri dispositivi (smartphone, tablet ecc.) sulla stessa rete Wi-Fi.

### Procedura

1. Attivare "LAN Access" su ON nella scheda **Settings > Server**
2. Impostare un **codice PIN** (obbligatorio per la pubblicazione LAN)
3. Riavviare il server
4. Accedere da `http://<indirizzo_IP_server>:5000` dagli altri dispositivi in LAN
5. Inserire il PIN e accedere

### Suggerimenti

- Emettendo un **token LAN Share** (percorso `/s/`), è possibile condividere un link di accesso guest senza PIN
- Nella schermata del server viene mostrato un QR code, quindi basta inquadrarlo con la fotocamera dello smartphone per accedere
- Supporta anche l'autenticazione Trusted Proxy tramite reverse proxy

---

## 8. Taggare Automaticamente

Quando si vuole assegnare automaticamente tag alle immagini facendo analizzare le immagini all'AI.

### Metodo A: WD-Tagger (veloce, specializzato nei tag)

1. Scaricare il modello ONNX di WD-Tagger in **Settings**
2. Cliccare **Esegui WD-Tagger** dalla pagina Tools o dal modale dettaglio
3. Vengono assegnati automaticamente tag in stile Danbooru

### Metodo B: AI Analysis (linguaggio naturale, alta precisione)

1. Aggiungere un server Ollama o compatibile OpenAI in **Settings > AI Analysis**
2. Eseguire l'analisi dalla **scheda AI Analysis** nel modale dettaglio immagine
3. Viene generata una descrizione in linguaggio naturale dell'immagine

---

## 9. Visualizzare Statistiche e Report

Quando si vuole capire le tendenze e la crescita della propria libreria di immagini.

### Procedura

1. Aprire la pagina **Stats** dalla navigazione e verificare le statistiche complessive
2. Visualizzare report mensili dettagliati dalla pagina **Monthly Report**
3. Verificare i trofei di risultato nella sezione **Trophies**

---

## 10. Integrazione con Agenti AI tramite MCP

Quando si vuole operare la libreria di immagini da Claude Desktop o altri strumenti AI compatibili MCP.

### Procedura

1. Registrare il server MCP di YU AI Manager nella configurazione del client MCP (Claude Desktop ecc.)
   ```json
   {
     "command": "python",
     "args": ["-m", "mcp_server"],
     "env": { "YU_DB": "./tags.db" }
   }
   ```
2. Dare istruzioni in linguaggio naturale all'AI come "cerca immagini" o "aggiungi ai preferiti"
3. Sono disponibili oltre 60 strumenti tra cui `search_images`, `add_favorite`, `trigger_scan`

---

## 11. Usare Hailo-10H come Server Compatibile OpenAI

Quando in un ambiente con NPU Hailo-10H si vuole usarla come server AI locale compatibile con OpenAI SDK.

### Endpoint Supportati

| Endpoint | Funzione | API OpenAI Corrispondente |
|----------|----------|-----------------------------|
| `GET /ext/hailo-genai/v1/models` | Lista modelli scaricati | List Models |
| `POST /ext/hailo-genai/v1/chat/completions` | Generazione testo/comprensione immagine (VLM) | Chat Completions |
| `POST /ext/hailo-genai/v1/audio/transcriptions` | Trascrizione audio | Audio Transcriptions |
| `POST /ext/hailo-genai/v1/embeddings` | Testo→vettore (CLIP) | Embeddings |

### Procedura

1. Verificare che l'estensione Hailo GenAI sia abilitata in **Extensions > GenAI**
2. Scaricare il modello da usare (LLM: `qwen2.5-1.5b-chat` ecc., VLM: `llava-v1.6-vicuna-7b` ecc.)
3. Impostare il **Base URL** nelle impostazioni di connessione degli strumenti esterni:
   ```
   http://localhost:5000/ext/hailo-genai/v1
   ```
4. L'API Key non è necessaria (accesso locale). Se lo strumento la richiede obbligatoriamente, inserire un valore dummy (es. `dummy`)

### Note

- **Esclusività dispositivo**: Hailo-10H può caricare solo 1 modello GenAI alla volta (LLM o VLM o S2T). Il cambio modalità si effettua dalla pagina GenAI
- **Limitazioni URL immagine**: Per motivi di sicurezza, gli URL `http://` per la specifica delle immagini sono bloccati. Usare il formato `data:image/...;base64,...` o il formato `file_id:` di YU AI Manager

## Organizzazione libreria AI art

- Registra folder immagini generati
- Scansiona automaticamente
- Etichetta con WD-Tagger
- Organizza in collezioni per stile/artista

## Training dataset LoRA

- Filtra immagini per qualità rating
- Esporta collezione per training
- Annota con metadata training
- Raccogli best results

## Archivio prompt

- Ricerca semantica per concetto
- Raccogli prompt simili
- Versiona perfezionamenti
- Condividi workflow migliori

## Collaborazione team

- Fleet Admin per coordinare nodi
- Mesh Inference per distribuire load
- LAN Cowork per peer sharing
- SNS per showcase results

## Automazione data

- MCP per agent workflow
- Batch operations batch processing
- Scheduler per manutenzione
- Plugin per estensione custom
