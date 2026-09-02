# Configurazione di Hailo-10H

Guida alla configurazione lato host per l'utilizzo di Raspberry Pi 5 + Hailo AI Hat+ (Hailo-10H NPU) con YU AI Manager. Poiché la parte relativa all'hardware e al sistema operativo non può essere completata tramite PyPI, sono necessarie alcune preparazioni manuali.

> **Destinatari**: Solo se si desidera abilitare le estensioni Hailo (GenAI Chat / Semantic Search / YOLO Detect / Tagger / Whisper) su un Raspberry Pi 5 (si consigliano 8 GB) con hardware Hailo-10H. Negli ambienti senza hardware Hailo, nessuna delle operazioni di questa pagina è necessaria.

---

## 1. Prerequisiti

- Raspberry Pi 5 (8 GB fortemente consigliati; con 4 GB è difficile caricare più modelli contemporaneamente a causa dei vincoli CMA)
- Hailo AI Hat+ (Hailo-10H)
- Raspberry Pi OS Bookworm 64-bit (aarch64)
- Python 3.13.x (fissato a `<3.14` tramite `requires-python` in `pyproject.toml`; `uv` seleziona automaticamente la versione 3.13)

---

## 2. Installazione del driver PCIe

Hailo-10H utilizza il modulo kernel dedicato `hailo1x_pci` (rinominato dal precedente `hailo_pci` a partire da HailoRT 5.3.0).

```bash
sudo apt update
sudo apt install hailo-all
sudo reboot
```

Verifica dopo il riavvio:

```bash
lsmod | grep hailo1x
ls /dev/h1x-0
dmesg | grep -i hailo | tail -20
```

Risultati attesi:

- `hailo1x_pci` è caricato
- Esiste il nodo dispositivo `/dev/h1x-0` (non il vecchio `/dev/hailo0`)
- In `dmesg` sono presenti le righe `Firmware loaded in NNNN ms` e `Device created at /dev/h1x-0`

> **Non c'è problema se `/dev/hailo0` non è presente.** A partire da HailoRT 5.3.0, `/dev/h1x-0` è il valore predefinito e questa applicazione riconosce entrambi (`core/llm_router/hailo_detect.py`).

---

## 3. Installazione di HailoRT (lato sistema)

Binario `hailortcli` e libreria condivisa `libhailort.so`. Sono inclusi nel pacchetto `hailo-all`, ma se è necessaria l'ultima versione, scaricare il file `.deb` dalla Hailo Developer Zone e installarlo sopra la versione esistente.

Verifica:

```bash
hailortcli fw-control identify
```

Output atteso (punti principali):

```
Device Architecture: HAILO10H
Firmware Version: 5.3.0 (release,app)
```

---

## 4. Preparazione del wheel Python (`hailort-*.whl`)

Questa è la parte non disponibile su PyPI. **Il wheel Python Hailo per aarch64 non è disponibile nemmeno nella Hailo Developer Zone, quindi deve essere compilato manualmente.**

### 4.1 Compilazione dal codice sorgente

```bash
cd ~
git clone --branch v5.3.0 https://github.com/hailo-ai/hailort.git
cd hailort
./build.sh -aarch64
# Al termine, hailort-5.3.0-cp313-cp313-linux_aarch64.whl viene generato nell'albero di build
```

(Consultare il README ufficiale di Hailo per i dettagli del processo di compilazione e le dipendenze.)

### 4.2 Posizionamento del wheel nella directory home

Copiare il wheel compilato in **uno dei seguenti percorsi**; l'applicazione lo rileverà automaticamente all'avvio:

| Percorso di ricerca (priorità) | Scopo |
|---|---|
| Variabile d'ambiente `$HAILORT_WHEEL` | Percorso completo arbitrario (priorità massima) |
| `$HOME/share/` | **Posizione consigliata** |
| `$HOME/hailort/` | Quando l'albero di build viene mantenuto nella posizione del sorgente |
| `$HOME/Downloads/` | Posizione temporanea dopo il download |
| `$HOME/` (direttamente) | Ultima risorsa |

Procedura consigliata:

```bash
mkdir -p ~/share
cp ~/hailort/hailort-5.3.0-cp313-cp313-linux_aarch64.whl ~/share/
```

### 4.3 Meccanismo di installazione automatica

All'esecuzione di `./start.sh`, viene eseguito `scripts/install_hailo.py`:

1. Verifica se `import hailo_platform` ha successo nel venv
2. Solo in caso di errore: cerca un wheel **compatibile con la versione Python corrente (cp313) + architettura (aarch64)** nei percorsi di ricerca sopra indicati
3. Installa il wheel più recente trovato con `uv pip install`
4. Se non viene trovato alcun wheel o è già installato: nessuna azione (operazione silenziosa)

Pertanto non è necessario eseguire `uv pip install` manualmente. È sufficiente posizionare il wheel nella directory home e riavviare `./start.sh`.

---

## 4.4 Posizionamento dei file modello HEF

Posizionare i file HEF (modelli compilati per NPU) utilizzati dalle estensioni in `~/hailo_models/`.

| File | Scopo | Dimensione approssimativa |
|---|---|---:|
| `yolov8n.hef` | Rilevamento oggetti YOLO | 7 MB |
| `clip_vit_b_16_image_encoder.hef` | **Semantic Search (immagine CLIP)** | 76 MB |
| `clip_vit_b_16_text_encoder.hef` | Semantic Search (testo CLIP, opzionale) | 77 MB |
| `Whisper-{Tiny,Base,Small}.hef` | Riconoscimento vocale | 75–405 MB |
| `Qwen3-1.7B-Instruct.hef` | LLM Chat | 2,9 GB |
| `Qwen3-VL-2B-Instruct.hef` | VLM (immagine+testo) | 3,2 GB |

Download diretto senza autenticazione dal bucket S3 di Hailo Model Zoo (formato URL):

```
https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef
```

Esempio (encoder immagine CLIP):

```bash
mkdir -p ~/hailo_models
curl -L -o ~/hailo_models/clip_vit_b_16_image_encoder.hef \
  https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_image_encoder.hef
```

> **Se i file HEF mancano, l'estensione verrà visualizzata come `Non disponibile`.** Ad esempio, se lo stato di Semantic Search mostra `hailo-10h (CLIP HEF non posizionato)`, significa che `clip_vit_b_16_image_encoder.hef` non è presente in `~/hailo_models/`. Per facilitare la distinzione dai problemi hardware o di runtime Python, la risposta include le cause in tre livelli: `runtime_ok` / `hardware_ok` / `hef_ok` (passare il cursore sul testo di stato per visualizzare i dettagli).

È anche possibile specificare un'altra directory con la variabile d'ambiente `HAILO_HEF_DIR`.

---

## 5. Parametri del kernel (CMA)

I modelli GenAI di Hailo (LLM/VLM/Whisper) richiedono CMA (Contiguous Memory Allocator) per il DMA.

Aggiungere alla fine di `/boot/firmware/cmdline.txt`:

```
cma=256M
```

> **Su Pi 5 (8 GB), `cma=1G` o `cma=512M` falliscono silenziosamente.** Poiché il kernel predefinito applica `numa=fake=8`, il CMA deve stare entro il limite di un singolo nodo NUMA (1 GB), e oltre `256M` si ottiene `CmaTotal=0` (senza panic). Dettagli: [`docs/ja/hailo/PI5_NUMA_CMA_CONSTRAINTS.md`](../../hailo/PI5_NUMA_CMA_CONSTRAINTS.md)

Verifica dopo il riavvio:

```bash
grep CmaTotal /proc/meminfo
# CmaTotal:         262144 kB  ← 256 MB indica successo
```

Se il valore è `0 kB`, verificare il valore e ridurlo se necessario.

---

## 6. Coesistenza con hailo-ollama (opzionale)

Se si esegue `hailo-ollama` (la versione Hailo NPU di Ollama) sullo stesso dispositivo:

- **HailoRT 5.3.0 e successivi**: Avviare con `HAILO_OLLAMA_VDEVICE_GROUP_ID=YU_SHARED hailo-ollama` per condividere il dispositivo fisico con il lato yu_ai_manager (group_id `YU_SHARED`); lo scheduler HailoRT eseguirà il time-slicing in modalità ROUND_ROBIN
- **Prima di 5.2.0**: Il group_id non è accettato, quindi è necessario fermare `hailo-ollama` con `systemctl stop hailo-ollama` prima di avviare yu_ai_manager

---

## 7. Verifica del funzionamento

Dopo l'avvio di `./start.sh`, la configurazione è riuscita se i seguenti elementi sono abilitati nella WebUI sotto **Impostazioni → Estensioni**:

- `builtin_hailo_genai` (Hailo Chat / LLM / VLM / Speech2Text)
- `builtin_hailo_semantic_search` (CLIP Semantic Search)
- `builtin_hailo_yolo_detect` (Rilevamento oggetti YOLO)

O direttamente tramite CLI:

```bash
uv run python -c "
from hailo_platform import VDevice
v = VDevice()
print('VDevice OK')
v.release()
"
```

---

## 8. Risoluzione dei problemi

### Tutte le estensioni Hailo mostrano «non caricato»

→ Il wheel Python potrebbe non essere installato. Verificare:

```bash
uv run python -c "import hailo_platform; print(hailo_platform.__file__)"
```

In caso di `ModuleNotFoundError`: posizionare il wheel nella directory home e riavviare `./start.sh` (§4.2).

### `hailortcli fw-control identify` fallisce con `HAILO_OPEN_FILE_FAILURE`

→ Problema con il driver o il nodo dispositivo. Verificare se `hailo1x_pci` è caricato in `lsmod | grep hailo1x` e se `ls /dev/h1x-0` esiste. Se entrambi mancano, ripetere §2 e riavviare.

### `HAILO_OUT_OF_HOST_MEMORY` durante il caricamento di LLM/VLM / Pi si blocca

→ CMA insufficiente. Verificare con `grep CmaTotal /proc/meminfo` se sono disponibili 256 MB (§5). Poiché `VDevice.release()` non restituisce CMA, potrebbe essere necessario riavviare il processo dopo aver cambiato più modelli ripetutamente.

### `HAILO_OUT_OF_PHYSICAL_DEVICES(74)`

→ Un altro processo occupa VDevice. Identificare il responsabile con `lsof /dev/h1x-0` (tipicamente `hailo-ollama` o un processo precedente non terminato correttamente con Ctrl+C), eseguire `kill` e riavviare.

### Python è stato aggiornato alla versione 3.14 ed è incompatibile con il wheel

→ Questo repository è fissato in `pyproject.toml` con `requires-python = ">=3.13,<3.14"`. Il primo `uv sync` dopo il clone seleziona 3.13.x. Se è stato impostato manualmente `.python-version = 3.14`, ripristinarlo.

---

## 9. Documentazione correlata

- [`docs/ja/hailo/README.md`](../../hailo/README.md) — Indice della documentazione di sviluppo Hailo-10H
- [`docs/ja/hailo/HAILORT_5_3_0_MIGRATION.md`](../../hailo/HAILORT_5_3_0_MIGRATION.md) — Note di migrazione HailoRT 5.2.0 → 5.3.0
- [`docs/ja/hailo/PI5_NUMA_CMA_CONSTRAINTS.md`](../../hailo/PI5_NUMA_CMA_CONSTRAINTS.md) — Dettagli sui vincoli CMA di Pi 5
- [`scripts/install_hailo.py`](../../../../scripts/install_hailo.py) — Script di rilevamento automatico del wheel
