# Perdita di CMA in HailoRT 5.3.0 — Diagnosi confermata e vincoli operativi

> **Nota di correzione**: questo documento è il registro della diagnosi della perdita di CMA basata sulla vecchia misurazione; le vecchie conclusioni secondo cui la CMA non viene recuperata nemmeno dopo `release()`, che perde in modo continuo a circa 14 MB/min durante l'inferenza, e che il solo riavvio del Pi è un mezzo di recupero certo, sono state ritirate. Il giudizio finale, ottenuto dalla riprova con HailoRT/driver 5.4.0, è stato corretto in [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) §8. Non fare riferimento alle vecchie conclusioni di questo documento come giudizio operativo attuale.

**Creato**: 2026-05-17 (scoperto e registrato nella v4.214.11)
**Ambito interessato**: Raspberry Pi 5 + Hailo-10H + `hailort==5.3.0` (percorso `hailo_platform.genai`)
**Sintomo**: Una volta caricato un LLM, la CMA viene a malapena recuperata anche dopo aver chiamato `VDevice.release()` / `LLM.release()`. Inoltre, la CMA continua a perdere in modo continuo durante l'inferenza. Non esiste alcun mezzo di recupero se non riavviare il Pi.
**Stato**: Confermato come vincolo strutturale lato driver. Si stanno esaminando soluzioni alternative.

---

## 1. Fondamento della diagnosi confermata

Utilizzando il registratore di eventi CMA introdotto nella `v4.214.10` (`logs/hailo_cma.log`, `core/hailo_device_core/device_helpers.py::log_hailo_cma_event`), il 2026-05-17 è stata misurata la seguente sequenza.

### 1-1. Log di osservazione (raw)

`logs/hailo_cma.log`:

```text
2026-05-17T14:05:13+0900 event=vdevice_create_pre  cma_free_mb=392 pid=3237
2026-05-17T14:05:14+0900 event=vdevice_create_post cma_free_mb=393 pid=3237
2026-05-17T14:05:14+0900 event=acquire_pre  cma_free_mb=393 pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
2026-05-17T14:06:25+0900 event=acquire_post cma_free_mb=108 pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
        ↓ 6 minuti di utilizzo in chat (circa 5–10 messaggi di inferenza)
2026-05-17T14:12:36+0900 event=release_pre  cma_free_mb=24  pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
2026-05-17T14:12:36+0900 event=release_post cma_free_mb=25  pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
```

### 1-2. Interpretazione

| Fase | Differenza CmaFree | Significato |
|---|---|---|
| `vdevice_create_pre` → `vdevice_create_post` | **+1 MB (≈ 0)** | La creazione di VDevice stessa consuma a malapena CMA |
| `acquire_pre` → `acquire_post` (caricamento Qwen3-1.7B-Instruct) | **−285 MB** | 1 LLM consuma 285 MB |
| `acquire_post` → `release_pre` (6 minuti di inferenza) | **−84 MB / 6 min ≒ −14 MB/min** | **Perdita continua anche durante l'inferenza** |
| `release_pre` → `release_post` (scaricamento LLM) | **+1 MB** | **`release()` non restituisce effettivamente CMA** |

### 1-3. Confronto con l'ipotesi precedente

Questo è un risultato di misurazione che contraddice parzialmente l'ipotesi iniziale del §7 di `SQLCIPHER_MMAP_CORRUPTION.md` creato il 2026-05-16 e l'ipotesi del vecchio documento secondo cui «la strategia di ritenzione di VDevice (il nostro `_maybe_reset_vdevice` vuoto) amplifica la perdita». Poiché la creazione di VDevice = 0 MB / release = 0 MB, **cambiare la strategia di ritenzione (= cambiare `_maybe_reset_vdevice` per reimpostarsi ogni volta) non avrebbe alcun effetto**.

---

## 2. Vincoli strutturali

In base ai risultati misurati, HailoRT 5.3.0 (build della comunità, API `hailo_platform.genai`) presenta tre problemi coesistenti:

1. **`VDevice.release()` / `release()` del modello GenAI non recupera la CMA dell'host** (confermato dalla misurazione)
   - All'interno di un singolo processo, il driver PCIe (`hailo1x_pci`) continua a mantenere le regioni DMA, e non si verifica alcuna operazione equivalente a `munmap`
2. **Perdita continua di CMA durante l'inferenza (~14 MB/min)** (confermato dalla misurazione)
   - Osservazione odierna: 84 MB persi in 6 minuti durante l'utilizzo di Qwen3-1.7B-Instruct
   - Un percorso separato indipendente da caricamento/scaricamento. L'esaurimento si verifica anche senza scaricare
3. **Nessun metodo confermato per recuperare in modo affidabile la CMA tranne il riavvio del Pi** (misurazione + rapporti della comunità)
   - Anche il riavvio del processo server (equivalente a `systemctl restart yu-ai-manager`) è incompleto poiché `hailo1x_pci` mantiene DMA fino al ciclo di alimentazione PCIe. Il recupero completo richiede `sudo reboot` del Pi (misurato in questo repository)
   - Esistono più rapporti indipendenti nella comunità Hailo: <https://community.hailo.ai/t/hailo-10h-on-rpi5-undocumented-api-findings-dfc-conversion-failures-with-transformer-based-models-swinv2-vit-convnext/18979> e <https://community.hailo.ai/t/hailo-10h-throughput-degrades-irreversibly-within-minutes-of-continuous-use-125-41-fps-only-host-reboot-recovers/19218> (indica esplicitamente che `VDevice.release()` / uscita del processo / ricarica del driver non recupera, solo il riavvio dell'host lo fa)
   - Questo è già documentato per gli utenti nel messaggio di errore di rifiuto preventivo di `acquire_genai` (`core/hailo_device_core/device_manager_genai.py::acquire_genai`, "a full system reboot is required")

### 2-1. «Terminare un processo figlio restituisce CMA?»: **Confutato dalla misurazione** (2026-05-17 Phase 0 PoC)

La versione precedente (rev1) concludeva teoricamente che «il kernel Linux recupera le pagine DMA durante il teardown di `mm_struct`, quindi terminare un processo figlio recupera completamente la CMA», ma **la misurazione con Phase 0 PoC (`tools/diag_hailo_cma_reclaim.py`) ha confermato in modo indipendente due volte che terminare un processo figlio recupera a malapena CMA**.

**Risultati della misurazione (2° ciclo, versione rigorosa)**:

| Punto di misurazione | CmaFree | Δ |
|---|---:|---:|
| Linea base (prima dell'avvio del PoC) | 503 MB | — |
| Dopo la creazione di VDevice | 372 MB | **-131 MB** (la costruzione di VDevice consuma CMA nel processo figlio avviato a freddo) |
| Dopo il caricamento dell'LLM | 372 MB | 0 MB (LLM contenuto nel pool DMA di VDevice, nessun nuovo consumo) |
| Dopo SIGTERM + join | 378 MB | +6 MB |
| **Dopo 30 secondi di attesa** | **380 MB** | **Solo +8 MB recuperati in totale** |

A fronte di un recupero atteso di ≥250 MB, il valore misurato era solo di +8 MB (+1 MB nella prima misurazione casuale). Questo è a livello di jitter del sistema — **non si è verificato alcun recupero significativo di CMA**.

**Diagnosi confermata**:

- Il driver `hailo1x_pci` gestisce il pool DMA nello **stato globale interno del driver** e non nell'`mm_struct` del processo utente (stimato)
- Nessun recupero tramite `process exit`, `kill` o `module unload` (coerente con i rapporti della comunità)
- **L'unico metodo di recupero confermato è `sudo reboot` del Pi (= ciclo di alimentazione PCIe)** ← questo è il fatto misurato indicato in §2 riga 3

Rapporto dettagliato: `docs/superpowers/specs/codex-reviews/2026-05-17-hailo-subprocess-isolation-phase0-poc-result.md`

Come risultato di questi ritrovamenti, `docs/superpowers/specs/2026-05-17-hailo-subprocess-isolation-design.md` viene contrassegnato come **REJECTED**, e l'approccio di mitigazione tramite isolamento del subprocess viene abbandonato. L'approccio di riavvio automatico del §4 (D) viene adottato come alternativa.

---

## 3. Implicazioni operative

### 3-1. «1 modello per riavvio del Pi» è effettivamente il limite

- Con Pi 5 (limite CMA 512 MB, non aumentabile secondo le specifiche Pi) + LLM Qwen3 (285 MB):
    - CmaFree immediatamente dopo il riavvio ≒ 480 MB
    - Dopo il caricamento di 1 LLM → CmaFree ≒ 190 MB
    - Dopo decine di minuti di inferenza → CmaFree ≒ 50 MB o meno
    - **Caricare un secondo modello è permanentemente impossibile** (richiede 250+ MB ma il rimanente è insufficiente, e release non lo restituisce)

### 3-2. L'utilizzo simultaneo di LLM + VLM / LLM + S2T non è possibile

- I casi d'uso che alternano tra VLM (basato su llava, ~300 MB), S2T (whisper-small, ~175 MB) e LLM sono impossibili a causa dei vincoli sopra indicati, a meno di seguire la procedura **caricare → riavviare → caricare**.
- **L'UX multi-modello come «allegare un'immagine durante la conversazione per passare a un altro modello» o «trascrivere l'audio della conversazione» non è strutturalmente realizzabile con HailoRT 5.3.0**.

### 3-3. Le sessioni di inferenza continua prolungata sono difficili

- La perdita di 14 MB/min significa che anche partendo da 200 MB di CmaFree, si dimezza in 14 minuti e si esaurisce quasi completamente in 30 minuti.
- Le sessioni di chat superiori a 30 minuti non possono essere stabilizzate senza un riavvio del Pi nel mezzo.

---

## 4. Possibili contromisure

Elencate con priorità e sforzo:

| Opzione | Effetto | Sforzo | Effetti collaterali / Rischi |
|---|---|---|---|
| ~~(A) Isolare le operazioni Hailo in un subprocess e terminare periodicamente per restituire CMA al kernel~~ | ❌ **REJECTED** (confutato da Phase 0 PoC, riprodotto due volte). Il recupero dopo kill era solo di +8 MB totali — ipotesi fallita | — | Non adottato |
| **(B) Aggiornare `_CMA_ESTIMATES_MB` a valori misurati + margine** | Migliora la precisione del rifiuto preventivo (riduce i tentativi di caricamento falsi positivi) | ✅ Applicabile immediatamente, 1 riga | I casi che funzionavano appena con l'ipotesi di 250 MB verranno rifiutati, ma stavano già fallendo |
| **(C) Banner UI quando `CmaFree < 80 MB` / WARN in error.log quando `< 30 MB`** | Gli utenti possono capire la situazione e vengono invitati a riavviare il Pi | Medio | Rischio di affaticamento da avvisi / notifiche eccessive |
| **(D) Rilevare `CmaFree < 30 MB` e inviare SIGTERM al supervisor** | Recupero automatico (anche se è necessario il riavvio completo del Pi, tramite `systemctl reboot`) | Medio | Richiede permessi supervisor / interruzione della sessione durante altri lavori |
| **(E) Attendere la correzione di HailoRT + documentare chiaramente i vincoli** | Costo 0 | 0 | Dipende dal ciclo di rilascio di Hailo (mesi+) |
| **(F) Inviare richiesta di correzione al bug tracker / forum di Hailo** | Accelera potenzialmente i tempi di correzione | Piccolo | La velocità di risposta dipende dal contratto di supporto e dallo stato della comunità |

Politica a breve termine (implementata in v4.214.11): **Applicare (B) + questo documento (punto di partenza per E e F)**.
Politica a medio termine (spec separato): Considerare nell'ordine di **(C) avviso UI → (A) isolamento subprocess**.
Lungo termine: Monitorare le versioni di HailoRT e aggiornare questo documento per rimuovere i vincoli una volta corretti.

---

## 5. Documenti / Codice correlati

- `core/hailo_device_core/device_manager_genai.py::acquire_genai` — La verifica preventiva di CmaFree + il messaggio di errore per l'utente espone esplicitamente questo vincolo
- `core/hailo_device_core/device_helpers.py::_CMA_ESTIMATES_MB` — Stime dei requisiti CMA per modello (qwen aumentato da 250 → 300 nella v4.214.11)
- `core/hailo_device_core/device_helpers.py::log_hailo_cma_event` — Strumentazione di misurazione introdotta nella v4.214.10. I dati di misurazione in questo documento provengono da qui
- `core/hailo_device_core/device_manager_state.py::_maybe_reset_vdevice` — Design che mantiene VDevice per la durata del processo (funzione vuota). Questa misurazione conferma che modificarlo per reimpostarlo non contribuirebbe al recupero della CMA
- `docs/ja/hailo/HAILO_AUTO_REBOOT_PHASE05.md` — Guida dell'operatore per la fase di osservazione 0.5. Procedura per raccogliere solo i log `would_fire` con `mode=lazy` + `dry_run=true`
- `docs/ja/hailo/PI5_NUMA_CMA_CONSTRAINTS.md` — Limite totale di CMA del Pi5 e consumo base di ogni driver (camera / KMS / Hailo / HEVC)
- `docs/ja/hailo/HAILORT_5_3_0_MIGRATION.md` — Contesto della migrazione a HailoRT 5.3.0 e differenze note

---

## 6. Procedura di riproduzione (per i rapporti di problemi Hailo)

Procedura di riproduzione minima per i rapporti di bug esterni:

```bash
# 1. Confermare la linea base immediatamente dopo il riavvio del Pi
grep CmaFree /proc/meminfo
# CmaFree: ~480000 kB

# 2. Avviare il server + caricare il 1° LLM (es.: inviare 1 messaggio tramite GenAI in /tools)
# 1 richiesta a /api/llm/generate o /api/chat/send

# 3. Verificare CmaFree
grep CmaFree /proc/meminfo
# CmaFree: ~100 MB (-280 MB)

# 4. Scaricare il modello
curl -X POST http://127.0.0.1:5000/ext/hailo-genai/api/model/unload -d '{"model":"llm"}'

# 5. Verificare CmaFree
grep CmaFree /proc/meminfo
# CmaFree: ~100 MB (non restituito ← bug)

# 6. Tentativo di ricaricare lo stesso / un altro modello → rifiutato per CMA insufficiente
```

Comportamento atteso: Al passaggio 5, CmaFree dovrebbe tornare a un valore vicino alla linea base del passaggio 1 (>400 MB).
Comportamento effettivo: Viene restituito solo circa +1 MB, il ricaricamento è impossibile.
