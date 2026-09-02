# Documentazione sviluppo Hailo-10H

Documentazione relativa all'implementazione dell'inferenza AI con Raspberry Pi 5 + Hailo AI Hat+ (Hailo-10H).

La documentazione ufficiale è incompleta; qui sono pubblicati gli insegnamenti attuali dello sviluppo.

## Elenco documentazione

| File | Contenuto |
|---------|------|
| [HAILORT_5_3_0_MIGRATION.md](HAILORT_5_3_0_MIGRATION.md) | Note migrazione HailoRT 5.2.0 → 5.3.0. Differenze API, rinominazione nodi dispositivo (`/dev/h1x-0`), compatibilità HEF, script test |
| [VDEVICE_SHARING_PATTERN.md](VDEVICE_SHARING_PATTERN.md) | Pattern di implementazione del VDevice manager condiviso per coesistenza di più modelli (YOLO/CLIP/LLM/VLM/Whisper) nello stesso processo |
| [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md) | Limitazioni allocazione CMA su Pi 5 (comportamento sotto `numa=fake=8`). Perché `cma=1G` fallisce silenziosamente, `cma-512` come limite verificato e valore consigliato (`dtoverlay=cma,cma-512` in `config.txt`), requisiti di memoria di Hailo GenAI, comportamento di non-restituzione della CMA da parte di `VDevice.release()` |
| [HAILO_SEMANTIC_SEARCH_DEVLOG.md](HAILO_SEMANTIC_SEARCH_DEVLOG.md) | Registro sviluppo ricerca semantica CLIP. Record di implementazione per fase, problemi incontrati e soluzioni |
| [HAILO_DEVICE_CONTROL.md](HAILO_DEVICE_CONTROL.md) | Metodi di controllo dispositivo Hailo, gestione VDevice, controllo concorrenza, cambio modello |
| [ONNX_TO_HEF_CONVERSION_GUIDE.md](ONNX_TO_HEF_CONVERSION_GUIDE.md) | Procedura conversione ONNX → HEF. Dataflow Compiler, quantizzazione, troubleshooting |
| [ONNX_TO_HEF_CONVERSION_REPORT.md](ONNX_TO_HEF_CONVERSION_REPORT.md) | Rapporto validazione conversione (DFC v5.2.0). Analisi dettagliata fallimenti 3 modelli WD-Tagger |
| [WD_TAGGER_DFC_5_3_0_FOLLOWUP.md](WD_TAGGER_DFC_5_3_0_FOLLOWUP.md) | Aggiornamento DFC v5.3.0. Rivalutazione stesso modello WD-Tagger 3 (ancora fallisce), miglioramenti rilevati in v5.3.0 (nuovo `_create_layer_normalization_layer`, flusso riprova onnxsim, raccomandazione end-node) |
| [CLIP_ONNX_DEVLOG.md](CLIP_ONNX_DEVLOG.md) | Registro sviluppo CLIP ONNX multi-backend. Fallback per ambienti senza hardware Hailo |
| [HAILO_CMA_LEAK_HAILORT_5_3_0.md](HAILO_CMA_LEAK_HAILORT_5_3_0.md) | **Vincoli strutturali e misurazioni reali della perdita CMA**. Il fatto che `VDevice.release()` non la recuperi, la perdita continua durante l'inferenza (circa 14 MB/min), e che **non venga recuperata né con il kill del processo figlio, né con l'uscita del processo, né con lo scaricamento del modulo** (misurato indipendentemente 2 volte nel PoC di Fase 0, solo +8 MB con SIGTERM + 30 secondi di attesa). L'unico mezzo di recupero certo è il riavvio del Pi **(vecchia conclusione. Corretta in [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) §8 tramite riprova con HailoRT / driver 5.4.0)** |
| [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) | **Correzione e riverifica del giudizio di perdita CMA sopra indicato**. Confronto A/B tra la versione ufficiale vanilla e quella corretta con `FOLL_LONGTERM` su HailoRT / driver 5.4.0, e correzione secondo cui il vecchio giudizio era un errore basato solo sulla quantità di recupero assoluto di `CmaFree` dopo il primo caricamento HEF. Include il diff del sorgente v5.3.0 → v5.4.0, le insidie della procedura di build personalizzata, dati misurati |
| [HAILO_AUTO_REBOOT_PHASE05.md](HAILO_AUTO_REBOOT_PHASE05.md) | Guida operativa alla linea di auto-reboot adottata a seguito di quanto sopra. Fase di osservazione (registra solo `would_fire` senza riavviare), soglie di giudizio, motivo del `mode = "off"` predefinito |
| [HAILO_AUTO_REBOOT_PHASE05_RUNBOOK.md](HAILO_AUTO_REBOOT_PHASE05_RUNBOOK.md) | Runbook per questo ambiente della stessa fase. Procedure di avvio, verifica e conclusione dell'osservazione |
| [HAILO_LLM_SUBPROCESS_DEVLOG.md](HAILO_LLM_SUBPROCESS_DEVLOG.md) | Registro di implementazione che risolve il blocco del Quart event loop causato dal GIL durante il cold_load (~71 secondi), isolando l'inferenza LLM chat in un subprocess |
| [HAILO_10H_ECOSYSTEM_ASSESSMENT.md](HAILO_10H_ECOSYSTEM_ASSESSMENT.md) | Valutazione dell'ecosistema Hailo-10H (al 2026-03-19, HailoRT/DFC v5.2.0) |

## Informazioni sugli elementi noti importanti

### Ambiente / Raspberry Pi 5

- **Il limite CMA su Pi 5 (8 GB) è 512 MB, configurato in `config.txt`**: Il kernel predefinito applica `numa=fake=8`, dividendo la RAM in 8 nodi NUMA da 1 GB ciascuno. La CMA deve stare entro i confini di un singolo nodo; `cma-1024` e `cma-768` falliscono silenziosamente (`CmaTotal=0` senza kernel panic). **`cma-512` è il limite verificato e il valore consigliato** (riverificato tramite overlay il 2026-05-16, `CmaTotal: 524288 kB`). A causa di una regressione firmware del 2026-05, usare `dtoverlay=cma,cma-512` in `/boot/firmware/config.txt` anziché il cmdline `cma=`. Per dettagli vedi [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md)
- **Sempre validare CMA dopo reboot**: Verifica con `grep CmaTotal /proc/meminfo`. Se 0, la configurazione è stata ignorata
- **`VDevice.release()` non restituisce CMA**: la CMA viene mantenuta per l'intera sessione OS. Tratta il VDevice come un singleton con scope di sessione. **Non viene recuperata nemmeno con il riavvio del processo** — è stato misurato indipendentemente 2 volte nel PoC di Fase 0 che non viene recuperata né con il kill del processo figlio, né con l'uscita del processo, né con lo scaricamento del modulo (solo +8 MB con SIGTERM + 30 secondi di attesa, contro un valore atteso ≥250 MB). L'unico mezzo di recupero certo è `sudo reboot` (power-cycle PCIe) del Pi stesso. Per dettagli e la contromisura adottata vedi [HAILO_CMA_LEAK_HAILORT_5_3_0.md](HAILO_CMA_LEAK_HAILORT_5_3_0.md). **Correzione**: questo punto si basa sulla vecchia misurazione. Nella riprova A/B con HailoRT / driver 5.4.0 la perdita di CMA non si è riprodotta in condizioni pratiche, ed è stata corretta in [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) §8
- **`numa=fake=8` influenza installazione Node.js**: La memoria singolo nodo (1 GB) è scambiata per RAM totale, installer npm/node si ferma. Segnalato upstream: [anthropics/claude-code#33864](https://github.com/anthropics/claude-code/issues/33864)
- **Wheel Python ricompilato da sorgenti**: Non ci sono wheel aarch64 nemmeno su PyPI o Hailo Developer Zone
- **Conflitto con hailo-ollama**: Ferma hailo-ollama mentre usi VDevice
- **Leak VDevice all'uscita processo**: Verificare con `lsof /dev/hailo*`, risolvere con `kill PID`

### VDevice / API

- **Usa InferModel API**: `VDevice.create_infer_model()` è corretto. Vecchia VStreams API (`InferVStreams`, `ConfigureParams.create_from_hef`) restituisce `HAILO_NOT_IMPLEMENTED` su Hailo-10H
- **InferModel supporta solo modelli semplici**: 1 input HEF YOLO funziona, ma 2 input 4 output HEF Whisper restituisce `HAILO_INVALID_ARGUMENT` da `configure()`. Usa GenAI SDK per modelli complessi
- **VDevice mappa a 1 dispositivo fisico**: Creazione di 2 istanze `VDevice()` simultanee produce `HAILO_OUT_OF_PHYSICAL_DEVICES(74)`
- **Cambio modello richiede completa liberazione VDevice**: Impostare riferimento Python a `None` non è sufficiente. Chiama `VDevice.release()` per liberare esplicitamente il dispositivo fisico prima di creare nuovo VDevice
- **`set_format_type(FormatType.FLOAT32)` non supportato in hailort 5.2.0**: L'attributo `format_type` non esiste. Quantizza/dequantizza manualmente uint8, oppure usa GenAI SDK
- **Output è quantizzato uint8**: Allocare buffer output float32 produce `buffer size mismatch`. Alloca uint8, converti con parametri dequantizzazione (scale, zero_point) a float32

### GenAI (LLM / VLM / Speech2Text)

- **HailoRT 5.3.0 rifiuta `temperature=0.0`**: `LLM.generate()` genera `HAILO_INVALID_ARGUMENT` con `temperature=0`. Clamp prima della chiamata: `temperature = max(temperature, 0.01)`. Colpisce quando client compatibile OpenAI invia `temperature=0` predefinito
- **Caricamento simultaneo di 2 GenAI è possibile**: LLM + Whisper-tiny può caricarsi simultaneamente su stesso VDevice (confermato HailoRT 5.3.0). Spazio CMA rimanente dopo entrambi i caricamenti: circa 10 MB su 256 MB. Whisper-base+ rischia esaurimento memoria
- **Budget CMA LLM + Whisper-tiny**: Circa 246 MB totali (valore misurato). Valori CMA per tutti i modelli in [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md)

### Whisper (riconoscimento vocale)

- **Usa GenAI SDK**: `hailo_platform.genai.Speech2Text` fornisce completa pipeline. Esecuzione encoder+decoder completamente su NPU
- **HEF è solo decoder**: `Whisper-Base.hef` ha 2 input (encoder_features + token_embeddings) e 4 output (vocab diviso in 4). Non funziona con InferModel API
- **Input GenAI SDK**: little-endian float32 (`<f4`), dati PCM audio normalizzati [-1,1]
- **Fallback ONNX**: Se GenAI SDK non disponibile, usa modello ONNX HuggingFace per esecuzione CPU encoder+decoder

### YOLO (rilevamento oggetti)

- **Funziona con InferModel API**: HEF 1 input nessun problema
- **Fallback ONNX**: Se Hailo non disponibile, auto-scarica `yolo11n.onnx`. Output `(1,84,8400)` compatibile con yolov8n
- **Cooldown dopo fallimento inizializzazione**: Non retry per 60 secondi dopo fallimento inizializzazione engine

### Inferenza distribuita

- **Healthcheck essenziale**: Conferma status nodo remoto con `filter_available()` prima di iniziare distribuzione
- **Su fallimento remoto**: Fallback rimanenti item a locale. Auto-rilevamento al batch successivo al ripristino
- **Allocazione workload**: Differenza velocità GPU vs NPU è grande, divisione uniforme è inefficiente. Allocazione dinamica basata su misurazione throughput è argomento futuro
