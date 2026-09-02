# Follow-up Conversione DFC: Rivalutazione dei Modelli WD-Tagger con DFC v5.3.0

**Data**: 2026-04-06
**Versione DFC**: 5.3.0
**Report precedente**: [`ONNX_TO_HEF_CONVERSION_REPORT.md`](ONNX_TO_HEF_CONVERSION_REPORT.md) (2026-03-06)
**Ambiente**: WSL2 (Ubuntu 24.04), x86_64

---

## Contesto

Nel marzo 2026, è stato riportato che le 3 varianti di WD-Tagger (SwinV2, ViT, ConvNeXt) fallivano tutte a livello di parser nella fase di analisi con Hailo Dataflow Compiler v5.2.0, senza raggiungere la fase di quantizzazione. Il report originale è conservato in [`ONNX_TO_HEF_CONVERSION_REPORT.md`](ONNX_TO_HEF_CONVERSION_REPORT.md).

Poiché DFC v5.3.0 è stato rilasciato, si sono rivalutati gli stessi 3 modelli e i risultati vengono qui registrati.

---

## Riepilogo Risultati

| Modello | Dimensione | Errore DFC 5.2.0 | Errore DFC 5.3.0 | Cambiamento |
|---------|-----------|-----------------|-----------------|-------------|
| `wd-swinv2-tagger-v3` | 446 MB | `IndexError` in `_convert_axes_to_nhwc` | Identico | **Nessuno** |
| `wd-vit-tagger-v3` | 362 MB | Stesso | Identico (anche dopo retry con onnxsim) | Solo flusso retry aggiunto |
| `wd-convnext-tagger-v3` | 377 MB | `UnsupportedShuffleLayerError` | Identico + `UnsupportedModelError` aggiunto | **Errori aumentati** |

**Tutti e 3 i modelli continuano a fallire nella fase parser.** Le 500 immagini di calibrazione preparate non vengono usate, esattamente come con v5.2.0.

---

## Cosa è Cambiato in DFC v5.3.0

Il fallimento persiste, ma si notano i seguenti miglioramenti rispetto a v5.2.0:

### 1. Nuovo Metodo `_create_layer_normalization_layer`

Questo metodo non esisteva in v5.2.0. In DFC v5.3.0, l'operatore `LayerNormalization` viene gestito esplicitamente con un percorso di codice dedicato. Questa è certamente una prova che lo sviluppo sta avanzando.

Tuttavia **l'implementazione interna è incompleta**, e la chiamata `_convert_axes_to_nhwc` dopo l'invocazione del metodo genera `IndexError: list index out of range` con la stessa forma del tensore di v5.2.0.

### 2. Aggiunta di Semplificazione onnxsim + Flusso Retry

Per ViT e ConvNeXt, DFC v5.3.0 ora semplifica automaticamente l'ONNX di input con `onnxsim` e riprova il parsing. Il modello semplificato viene salvato come `model.sim.onnx` accanto al file di input.

Per i modelli attuali, poiché la causa radice è nel lato `_convert_axes_to_nhwc`, anche il retry **fallisce nello stesso punto**.

### 3. Funzione di Raccomandazione End Node

Per ConvNeXt, DFC v5.3.0 raccomanda end node specifici quando il parser rinuncia, invitando l'utente a riprovare fissando quel nodo.

Anche il retry con gli end node raccomandati fallisce allo stesso modo.

---

## Causa Radice (Invariata da Marzo)

Il parser ONNX di DFC continua a fallire nella conversione degli assi quando il tensore di input all'operatore `LayerNormalization` non segue il formato NCHW previsto. La call chain è:

```
_create_layer_normalization_layer
  → get_layer_normalization_info
    → _convert_axes_to_nhwc
      → IndexError: list index out of range
```

Per ConvNeXt, si aggiunge anche `UnsupportedShuffleLayerError` su più nodi `Transpose` (`token_5` ~ `token_34`), che mostra la gestione incompleta del pattern channels-last usato da questa architettura.

In sintesi, **il nuovo percorso di codice esiste ma non gestisce ancora i casi che fallivano in origine**.

---

## Richieste (Invariate da Marzo)

### 1. Correzione di `_convert_axes_to_nhwc` per `LayerNormalization` multidimensionale

Ora è possibile raggiungere il punto in cui il metodo viene chiamato (miglioramento). Ma la logica di mappatura degli assi fallisce con tensori non-NCHW. Architetture Transformer recenti come SwinV2, ViT, ConvNeXt dipendono tutte dal corretto funzionamento di questo.

### 2. ONNX Runtime Execution Provider per Hailo-10H

Con questo, la conversione completa con DFC diventerebbe opzionale, risolvendo strutturalmente questa classe di problemi.

---

## Informazioni sull'Ambiente di Test

| Elemento | Dettagli |
|----------|---------|
| OS | Ubuntu 24.04 (WSL2) |
| CPU | AMD Ryzen 5 5600X |
| RAM | 151 GB |
| Python | 3.11 |
| DFC | 5.3.0 |
| Modelli | `SmilingWolf/wd-{swinv2,vit,convnext}-tagger-v3` (HuggingFace) |
| Dati di calibrazione | 500 immagini output ComfyUI / SD (non usate poiché la quantizzazione non viene raggiunta) |

---

## Istruzioni di Riproduzione

```bash
# 1. Setup DFC v5.3.0 in un venv Python pulito
python3.11 -m venv venv
source venv/bin/activate
pip install hailo_dataflow_compiler-5.3.0-py3-none-linux_x86_64.whl

# 2. Scarica i 3 modelli ONNX WD-Tagger
for variant in swinv2 vit convnext; do
  huggingface-cli download \
    "SmilingWolf/wd-${variant}-tagger-v3" \
    model.onnx --local-dir "./wd-${variant}-tagger-v3"
done

# 3. Testa il parsing per ogni modello
for variant in swinv2 vit convnext; do
  hailo parser onnx "./wd-${variant}-tagger-v3/model.onnx" \
    --hw-arch hailo10h \
    --tensor-shapes input_1:1,448,448,3 2>&1 | tee "${variant}_5.3.0.log"
done
```

---

## Conclusione

I progressi nello sviluppo di DFC v5.3.0 (`_create_layer_normalization_layer`, flusso retry onnxsim, raccomandazione end node) sono genuinamente incoraggianti. Il gap rimanente è nell'implementazione del contenuto di `_convert_axes_to_nhwc`: ora è raggiungibile, ma non funziona ancora correttamente per i modelli attuali.

Si continuerà a rivalutare a ogni rilascio di DFC e a pubblicare aggiornamenti se la situazione cambia.
