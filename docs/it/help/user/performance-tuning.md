# Guida all'Ottimizzazione delle Prestazioni

Guida di tuning per usare comodamente YU AI Manager in ambienti con oltre 100.000 file. Molte ottimizzazioni funzionano automaticamente con le impostazioni predefinite, ma è possibile ottenere ulteriori miglioramenti adattandole all'ambiente.

---

## 1. Hardware Consigliato

| Elemento | Requisiti minimi | Consigliato (oltre 100K file) |
|----------|-----------------|-------------------------------|
| CPU | 2 core | 4+ core (la generazione thumbnail viene parallelizzata) |
| RAM | 4 GB | 8 GB o più |
| Storage | HDD | **SSD fortemente consigliato** — direttamente correlato alla velocità di risposta del database |
| Rete | — | Gigabit o superiore per accesso LAN |

**Particolarmente importante**: Il file database (`data/tags.db`) deve essere posizionato su SSD. I file immagine possono stare su HDD, ma se il DB è su HDD la ricerca e la navigazione diventano notevolmente lente.

---

## 2. Ottimizzazione della Scansione Iniziale

### Suddivisione delle Radici di Scansione

Scansionare grandi quantità di file in una volta richiede tempo. Si consiglia di registrare più radici di scansione in Settings > Scan Roots e scansionare gradualmente.

- Prima scansionare le cartelle usate più frequentemente
- Aggiungere le cartelle rimanenti alla coda di scansione (vengono elaborate automaticamente in ordine)
- La registrazione duplicata della stessa cartella viene rilevata e saltata automaticamente

### Navigazione Disponibile Durante la Scansione

Durante la scansione, la ricerca e la visualizzazione thumbnail funzionano normalmente. Internamente viene usata una connessione database di sola lettura, quindi le operazioni di scrittura della scansione non bloccano la navigazione.

### Ottimizzazione Automatica dopo la Scansione

Al completamento della scansione le statistiche del database vengono aggiornate automaticamente (ANALYZE). Questo ottimizza il piano di esecuzione delle query di ricerca, accelerando le ricerche successive. Non è richiesta nessuna operazione speciale.

---

## 3. Miglioramento della Velocità di Navigazione

### Cache Service Worker

Il Service Worker del browser memorizza automaticamente i seguenti contenuti:

| Tipo | Limite cache | Effetto |
|------|-------------|---------|
| Thumbnail | 5.000 elementi | La visualizzazione della griglia dal secondo accesso è immediata |
| Anteprima (1200px) | 200 elementi | Accelerazione visualizzazione modale |
| Immagine originale | 50 elementi | La ri-visualizzazione delle immagini recenti è immediata |

Il Service Worker è gestito automaticamente dal browser, non è necessaria nessuna configurazione speciale.

### Abilitazione dello Scroll Virtuale

Per visualizzare migliaia di risultati di ricerca, abilitare lo scroll virtuale migliora notevolmente le prestazioni di rendering.

**Procedura di abilitazione**: Settings > Appearance > "Virtual Scroll" su ON

Lo scroll virtuale renderizza nella DOM solo le card visibili a schermo, riducendo notevolmente l'utilizzo di memoria e il carico di rendering. Fortemente consigliato per librerie dell'ordine delle decine di migliaia.

### Thumbnail WebP

I thumbnail vengono generati in formato WebP (30-40% più piccoli rispetto a JPEG). Questo riduce il traffico, con effetti particolarmente visibili per l'accesso tramite LAN. Viene applicato automaticamente senza configurazione.

---

## 4. Prestazioni di Ricerca

### Effetto degli Indici

Nel database vengono creati automaticamente indici ottimizzati per i principali pattern di ricerca. L'ordinamento per data, i filtri tag e la ricerca per percorso funzionano rapidamente.

**Valori di riferimento**:
- Ricerca senza filtri: entro 50ms anche con 280K file
- Ricerca con filtri tag: entro 100ms
- Ricerca per percorso (FTS5): entro 50ms

### FTS5 Full-Text Search vs Ricerca LIKE

Per la ricerca per percorso viene usato automaticamente l'indice FTS5 (Full-Text Search). Da 20 a 100 volte più veloce rispetto alla tradizionale ricerca LIKE (`%keyword%`).

**Nota sulla ricerca in giapponese**: Le ricerche con kanji, hiragana e katakana potrebbero usare internamente il fallback LIKE. Questo è un comportamento normale dovuto alle limitazioni del tokenizzatore FTS5 di SQLite.

---

## 5. Ottimizzazione della Riproduzione Video

### Cache Faststart

Per accelerare la riproduzione di file MP4/MOV, il processing faststart viene applicato automaticamente. I video con faststart iniziano la riproduzione in streaming immediatamente.

| Elemento | Valore |
|----------|--------|
| Posizione cache | `cache/faststart/` |
| Limite capacità | 4 GB (gestito automaticamente con LRU) |
| Limite per file | 500 MB |
| Target | MP4, MOV (WebM saltato perché non necessario) |

**Riferimento miglioramento percepito**:

| Dimensione file | Senza faststart | Con faststart |
|----------------|-----------------|---------------|
| 5-50 MB | 2-10 secondi di attesa | Riproduzione a ~200ms |
| 50-200 MB | 10-60 secondi di attesa | Riproduzione a ~500ms |
| 200-500 MB | Attesa di minuti | Riproduzione a ~1 secondo |

### Verifica FFmpeg

Il processing faststart richiede FFmpeg. Se non installato, i video vengono riprodotti dopo il download completo.

```bash
ffmpeg -version
```

---

## 6. Gestione Utilizzo Memoria

### SQLite mmap

Per database di grandi dimensioni (oltre 100K file), la mmap SQLite (I/O memory-mapped) viene automaticamente impostata a 1 GB. Questo accelera le query di lettura sfruttando la page cache del sistema operativo.

**In ambienti con RAM ≤ 4 GB**: La mmap potrebbe saturare la memoria. In tal caso monitorare la memoria libera del sistema, e se lo swapping è frequente chiudere le altre applicazioni.

### Gestione Tab del Browser

YU AI Manager comunica in tempo reale con ogni tab tramite SSE (Server-Sent Events).

- Massimo 10 connessioni SSE simultanee per IP
- Chiudere i tab non necessari libera le risorse di connessione
- Aprire molti tab aumenta anche l'utilizzo di memoria del browser

**Consigliato**: Mantenere il numero di tab aperti contemporaneamente a 3-4 al massimo.

---

## 7. Troubleshooting — Checklist per Quando si Sente "Lento"

### Verifica Base

- [ ] **Si usa SSD**: Se `data/tags.db` è su HDD, tutte le operazioni saranno lente
- [ ] **FFmpeg è installato**: Obbligatorio per accelerazione riproduzione video
- [ ] **Numero di tab del browser**: Verificare che non ce ne siano più di 5 aperti

### Navigazione Lenta

- [ ] **Abilitare lo scroll virtuale**: Settings > Appearance > Virtual Scroll
- [ ] **Non cancellare la cache del browser**: La cache del Service Worker è attiva
- [ ] **Verificare se è in corso una scansione**: Durante la scansione il primo caricamento thumbnail richiede tempo

### Ricerca Lenta

- [ ] **Completare la scansione**: Al completamento della scansione viene eseguito ANALYZE e la ricerca viene ottimizzata
- [ ] **Risultati di ricerca oltre 100K**: Aggiungere filtri (tag, date, percorso ecc.) per restringere i risultati

### Riproduzione Video Lenta

- [ ] **Verifica presenza FFmpeg**: Verificare con `ffmpeg -version`
- [ ] **Capacità cache faststart**: Verificare che la cartella `cache/faststart/` non superi 4 GB
- [ ] **Dimensione file**: I video oltre 500 MB non sono soggetti alla cache faststart

---

## 8. Valori di Riferimento delle Prestazioni

Tempi di risposta di riferimento in un ambiente correttamente ottimizzato.

| Operazione | Scala 280K file | Scala 100K file |
|------------|-----------------|-----------------|
| Visualizzazione griglia (primo accesso) | 200-500ms | 100-300ms |
| Visualizzazione griglia (con cache) | < 50ms | < 50ms |
| Ricerca tag | < 100ms | < 50ms |
| Ricerca percorso (FTS5) | < 50ms | < 30ms |
| Thumbnail (cache hit) | < 5ms | < 5ms |
| Avvio riproduzione video (con faststart) | 200ms | 200ms |

Se questi valori sono notevolmente superati, verificare la checklist sopra.

---

## Modalità veloce (server Rust)

Negli ambienti supportati, l'avvio passa automaticamente al server Rust (`yu-server`).

In Impostazioni -> «Server» -> «Modalità veloce» si sceglie **come ottenerlo**:

- **Scaricare il binario pubblicato** (predefinito) -- non compila mai
- **Compilare su questa macchina** -- non scarica mai
- **Scaricare e, se fallisce, compilare**

Compilare richiede almeno 8 GB liberi e usa molta CPU e memoria. **Su macchine con poca memoria (un Raspberry Pi, ad esempio) può esaurire lo swap e far cadere l'intero sistema.** Tutte le funzioni restano utilizzabili durante la compilazione. Compilare su Windows richiede inoltre gli strumenti di compilazione di Visual Studio (il linker).

L'avanzamento appare nella stessa schermata: tempo trascorso, l'ultima riga di cargo, esito positivo o negativo e se la compilazione si è fermata a metà. Il log grezzo è in `bin/fast-mode-build.log`.

Quando la modalità veloce viene rifiutata per lo stato di questa copia (bundle web non aggiornato, un'estensione fuori dall'elenco incluso), ottenere un binario non cambia la risposta: non si scarica né si compila. Anche quel motivo è mostrato lì.
