# Valutazione dell'Ecosistema Hailo-10H

**Data di creazione**: 2026-03-19
**Target**: Hailo-10H (AI HAT 2 for Raspberry Pi 5)
**HailoRT**: v5.2.0
**DFC**: v5.2.0
**Scopo**: Documentare l'esperienza di sviluppo con Hailo-10H in questo progetto e organizzare i vincoli realistici e le prospettive future

---

## Valutazione Complessiva

**L'hardware è eccellente. L'ecosistema software è decisamente carente.**

Hailo-10H è un NPU con 40 TOPS di prestazioni di inferenza e il suo potenziale come hardware è sufficiente. Tuttavia, poiché la toolchain software è chiusa e immatura, gli sviluppatori **praticamente non possono** portare i propri modelli e farli girare liberamente.

In questo progetto abbiamo sviluppato funzionalità multiple con Hailo-10H — ricerca semantica CLIP, rilevamento oggetti YOLO, chat LLM/VLM, riconoscimento vocale Whisper e server tagger distribuito — ma tutte quelle che funzionano stabilmente **utilizzano HEF precompilati scaricati dall'ufficiale Model Zoo di Hailo**, e non abbiamo **mai** potuto convertire con successo i nostri modelli da ONNX a HEF.

---

## Stato di Implementazione nel Progetto

### Funzionalità Operative (tutte usano HEF ufficiali)

| Funzionalità | API utilizzata | Fonte HEF |
|-------------|----------------|-----------|
| Encoder immagine CLIP | `VDevice.create_infer_model()` | Hailo Model Zoo (S3) |
| Rilevamento oggetti YOLO | `VDevice.create_infer_model()` | Hailo Model Zoo (S3) |
| Chat LLM | `hailo_platform.genai.LLM` | Hailo GenAI Model Zoo |
| Inferenza VLM immagine+testo | `hailo_platform.genai.VLM` | Hailo GenAI Model Zoo |
| Riconoscimento vocale Whisper | `hailo_platform.genai.Speech2Text` | Hailo GenAI Model Zoo |

### Funzionalità Non Riuscite (fallimento conversione HEF)

| Funzionalità | Cosa si è tentato | Risultato |
|-------------|-------------------|-----------|
| WD-Tagger (SwinV2) | Conversione ONNX → HEF | DFC non riesce a processare LayerNormalization, fallisce |
| WD-Tagger (ViT) | Conversione ONNX → HEF | Stesso errore |
| WD-Tagger (ConvNeXt) | Conversione ONNX → HEF | DFC non riesce a processare l'operazione Transpose, fallisce |

### Note Sull'Implementazione

In questo progetto abbiamo implementato tutte le funzionalità **chiamando direttamente** l'API Python della wheel `hailo_platform`. Non utilizziamo hailo-ollama né hailo-apps.

In particolare, le seguenti funzionalità sono state costruite autonomamente prima che Hailo le fornisse ufficialmente:

- **VDevice Device Manager con controllo esclusivo** — Cambio automatico tra CLIP/YOLO/LLM/VLM/S2T su un singolo VDevice. hailo-apps non ha un meccanismo di condivisione dispositivi
- **Fallback multi-backend** — Cambio trasparente automatico Hailo → CoreML → ONNX Runtime
- **Pipeline di dequantizzazione uint8** — Ripristino di float32 da scale/zero_point di `quant_info`
- **Architettura di inferenza distribuita LAN** — Tagging parallelo con work-stealing su più macchine

Questi sviluppi sono stati effettuati **praticamente in assenza di documentazione API**.

---

## Problemi con Hailo Dataflow Compiler (DFC)

### Cos'è DFC

Compilatore per convertire modelli ONNX/TensorFlow nel formato HEF (Hailo Executable Format) per Hailo-10H. Funziona su x86_64 Linux e converte i modelli con la seguente pipeline:

```
model.onnx → HAR (float32) → ottimizzazione → quantizzazione (INT8) → compilazione → model.hef
```

### La Realtà

**DFC converte correttamente solo le architetture pre-verificate da Hailo per il proprio Model Zoo.**

Tentativi di conversione in questo progetto (2026-03-06, DFC v5.2.0):

| Modello | Dimensione | Errore | Fase raggiunta |
|---------|-----------|--------|----------------|
| wd-swinv2-tagger-v3 | 446 MB | `IndexError` in `_convert_axes_to_nhwc` | Prima dell'ottimizzazione |
| wd-vit-tagger-v3 | 362 MB | Stesso | Prima dell'ottimizzazione |
| wd-convnext-tagger-v3 | 377 MB | `UnsupportedShuffleLayerError` | Prima dell'ottimizzazione |

Tutti e 3 i modelli **falliscono a livello di parser** prima di raggiungere la fase di ottimizzazione.

### Causa Radice

Il parser ONNX di DFC non riesce a processare i seguenti operatori:

- `LayerNormalization` (conversione assi su tensori multidimensionali)
- `Transpose` (pattern di conversione channels-last/first)

Questi sono elementi costitutivi fondamentali delle architetture Transformer (SwinV2, ViT, ConvNeXt ecc.), usati dalla maggior parte dei modelli principali dal 2022 in poi.

### Portata di Supporto Effettiva di DFC

| Architettura | Supporto DFC | Base |
|-------------|-------------|------|
| ResNet, MobileNet ecc. (CNN) | Supportata | Molti presenti nel Model Zoo |
| YOLO v5/v8/v11 | Supportata | HEF disponibili nel Model Zoo |
| CLIP ViT (versione Hailo) | Supportata | HEF disponibili nel Model Zoo (Hailo l'ha convertito) |
| SwinTransformer V2 | Non supportata | Fallimento conversione LayerNorm |
| Vision Transformer (generico) | Non supportata | Fallimento conversione LayerNorm |
| ConvNeXt | Non supportata | Fallimento conversione Transpose |

---

## Problemi con il Formato HEF

- **Specifica binaria non pubblica** — Hailo non pubblica la documentazione del formato
- **Nessun altro strumento di generazione oltre a DFC** — Impossibile creare HEF con strumenti di terze parti
- **Reverse engineering non praticabile** — Richiede conoscenza del set di istruzioni NPU e dell'architettura del flusso dati

In sostanza, i modelli che DFC non riesce a convertire **non possono in alcun modo girare su Hailo-10H**. Non esistono alternative.

---

## Valutazione della Toolchain di Sviluppo

### hailo_platform (Python SDK)

| Elemento | Valutazione |
|----------|-------------|
| API InferModel | Funziona ma documentazione estremamente carente |
| API GenAI (LLM/VLM/S2T) | Relativamente usabile. Ma molti comportamenti undocumented |
| Distribuzione wheel Python | Non su PyPI. La wheel aarch64 richiede build da sorgente |
| Messaggi di errore | Minimi. Difficile identificare la causa di mismatch dimensioni buffer |
| Gestione VDevice | Solo accesso esclusivo. Impossibile uso simultaneo di modelli multipli |

### Comportamenti Undocumented Scoperti Durante lo Sviluppo

1. **L'API InferModel è quella corretta** — La vecchia API VStreams (`InferVStreams`, `ConfigureParams.create_from_hef`) restituisce `HAILO_NOT_IMPLEMENTED` su Hailo-10H
2. **L'output è quantizzato uint8** — Allocare il buffer come float32 dà `buffer size mismatch`. Bisogna allocare uint8 e dequantizzare in seguito
3. **`input()`/`output()` sono proprietà** — Non metodi (incoerente con altre API Hailo)
4. **Ottenere `quant_info`** — Si ottiene con `infer_model.output().quant_info` ma non esiste documentazione che lo spieghi
5. **Esclusione con hailo-ollama** — VDevice in uso richiede di fermare hailo-ollama. Il messaggio di errore non chiarisce la causa

---

## Confronto con Prodotti Concorrenti

### Ryzen AI (XDNA) NPU

| Elemento | Hailo-10H | Ryzen AI (XDNA) |
|----------|----------|-----------------|
| Prestazioni | 40 TOPS | 16~50 TOPS (dipende dalla generazione) |
| Portabilità modelli | Conversione DFC obbligatoria, spesso fallisce | **ONNX Runtime supportato direttamente** |
| Esperienza sviluppatore | Toolchain proprietaria, documentazione scarsa | `pip install onnxruntime-directml` è tutto |
| Ecosistema | Chiuso, dipendente da Model Zoo | ONNX / DirectML / collaborazione Microsoft |
| Unità diffuse | Pi + AI HAT, dongle USB (previsto) | **Milioni di notebook con NPU integrata** |

L'integrazione con Ryzen AI si riduce a:

```python
import onnxruntime as ort
session = ort.InferenceSession("model.onnx", providers=["DmlExecutionProvider"])
```

Su Hailo-10H la stessa cosa è impossibile. Non esiste ONNX Runtime Execution Provider.

### NVIDIA CUDA

| Elemento | Hailo-10H | NVIDIA CUDA |
|----------|----------|-------------|
| Portabilità modelli | Via DFC, spesso fallisce al di fuori del Model Zoo | ONNX / PyTorch / TensorFlow → funziona direttamente |
| Toolchain | Immatura, semi-chiusa | Matura, pubblica, documentazione abbondante |
| Community sviluppatori | Minuscola | La più grande al mondo |
| Fascia di prezzo | Economica (~$70) | Costosa ($200~$2000+) |

L'unico vantaggio di Hailo è **prezzo e consumo energetico**.

---

## Relazione con hailo-apps (2025-10)

### Panoramica di hailo-apps

Raccolta di applicazioni ufficiali rilasciata da Hailo nel ottobre 2025. Include oltre 20 app di esempio:

- GenAI: voice_assistant, vlm_chat, agent_tools_example, whisper
- Pipeline: rilevamento oggetti, stima pose, riconoscimento volti, classificazione CLIP, OCR
- Standalone: demo Python/C++ per apprendimento HailoRT

### Confronto con Questo Progetto

| Elemento | hailo-apps | Questo progetto |
|----------|-----------|-----------------|
| Supporto VLM | App vlm_chat | Implementazione diretta `hailo_platform.genai.VLM` |
| CLIP | App clip | Integrato come sistema di ricerca semantica |
| LLM | simple_llm_chat | Integrato come Extension GenAI |
| Whisper | simple_whisper_chat | Integrato come Extension Speech-to-Text |
| Gestione dispositivi | Nessuna (premessa app singola) | **Device Manager con controllo esclusivo (cambio auto CLIP/YOLO/LLM/VLM/S2T)** |
| Fallback backend | Nessuno | **Cambio automatico Hailo → CoreML → ONNX** |
| Inferenza distribuita | Nessuna | **Work-stealing distribuito LAN** |
| Integrazione | App demo separate | Singola applicazione WebUI integrata |

---

## Prospettive Future

### Breve Termine (Realistico)

- **ONNX Runtime + distribuzione LAN è l'unica soluzione pratica** — Operare con il backend ONNX del server tagger distribuito
- Limitare Hailo-10H agli usi per cui esistono HEF ufficiali (YOLO, CLIP, LLM, Whisper)
- Rinunciare all'esecuzione NPU dei modelli custom

### Medio Termine (Ottimistico)

- ASUS ecc. rilasciano dongle USB con Hailo-10H → aumento utenti
- L'aumento di utenti potrebbe spingere Hailo a migliorare gli strumenti
- Le future versioni di DFC potrebbero aggiungere supporto per Transformer

### Lungo Termine (Sfide Strutturali)

- Finché Hailo non fornisce un ONNX Runtime EP, perderà l'ecosistema sviluppatori contro Ryzen AI (XDNA)
- Anche se l'hardware si diffonde con i dongle USB, senza libertà software rimane "una chiave veloce su cui gira YOLO"
- La situazione in cui i 40 TOPS di potenziale sono utilizzabili solo con le decine di modelli del Model Zoo continua

---

## Riepilogo

Hailo-10H ha ottime prestazioni hardware con 40 TOPS, ma a causa della chiusura e dell'immaturità dell'ecosistema software, è **praticamente impossibile** per gli sviluppatori portare e utilizzare liberamente i propri modelli.

In questo progetto abbiamo costruito un software più integrato di hailo-apps (la raccolta di applicazioni ufficiale di Hailo) esplorando API undocumented. Tuttavia, non siamo riusciti a realizzare l'esecuzione NPU di modelli custom (WD-Tagger) a causa dei vincoli di DFC.

**"Gli strumenti sono troppo pochi per sviluppare praticamente"** — questa è l'onesta conclusione dopo mesi di sviluppo con Hailo-10H.

---

## Documenti Correlati

- [`HAILO_SEMANTIC_SEARCH_DEVLOG.md`](./HAILO_SEMANTIC_SEARCH_DEVLOG.md) — Log di sviluppo della ricerca semantica CLIP (Phase 1~12+)
- [`ONNX_TO_HEF_CONVERSION_GUIDE.md`](./ONNX_TO_HEF_CONVERSION_GUIDE.md) — Guida alla conversione DFC (materiale di riferimento)
- [`HAILO_DEVICE_CONTROL.md`](./HAILO_DEVICE_CONTROL.md) — Design gestione dispositivo VDevice
- [`../features/distributed-tagger-server.md`](../features/distributed-tagger-server.md) — Documentazione server tagger distribuito
