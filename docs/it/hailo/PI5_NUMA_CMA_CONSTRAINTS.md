# Vincoli CMA su Pi 5 con `numa=fake=8`

Conoscenze pratiche sull'allocazione CMA su Raspberry Pi 5 (8 GB) durante l'esecuzione di workload Hailo-10H.
Descrive il limite massimo di `cma=`, il motivo per cui i valori superiori a 512M falliscono silenziosamente, e come recuperare la CMA consumata dal driver del display.

**Destinatari**: sviluppatori che eseguono modelli Hailo GenAI (LLM, Speech2Text) su Raspberry Pi 5
(con AI HAT / AI HAT+).

---

## ⚠️ Attenzione: regressione firmware 2026-05

**A partire dalla release del 2026-05-13 `raspi-firmware 1:1.20260513-1` + `pieeprom-2026-05-11`**, scrivere `cma=` in `/boot/firmware/cmdline.txt` — indipendentemente dalla dimensione — silenzia completamente il mailbox del firmware VC (`vcgencmd ioctl_set_msg failed:-1`, `raspberrypi-clk -22`, HEVC `-517`, sysfs cpufreq mancante).

**Metodo consigliato e confermato a partire dal 2026-05-16**: invece di `cma=` in cmdline, scrivere `dtoverlay=cma,cma-512` in `/boot/firmware/config.txt`. Poiché viene allocata tramite il nodo di memoria riservata `linux,cma` del DT, non entra in conflitto con il nuovo firmware. Per i dettagli vedere il §6 e [`docs/development/investigations/pi5_firmware_cma_mailbox_regression_2026-05-16.md`](../../development/investigations/pi5_firmware_cma_mailbox_regression_2026-05-16.md).

La descrizione precedente riportata più sotto (che raccomandava `cma=512M` in cmdline) riflette i risultati di verifica del 2026-04-15. La conoscenza relativa al valore limite (512M) dovuto al confine dei nodi NUMA resta valida, ma **il punto in cui va impostato è passato dal cmdline all'argomento overlay di config.txt**.

---

## TL;DR

- **Il punto di configurazione è `dtoverlay=cma,cma-512` in `config.txt`** (confermato il 2026-05-16; `cma=` in cmdline rompe il mailbox con il nuovo firmware)
- `cma-1024` e `cma-768` **falliscono silenziosamente** su Pi 5 (8 GB) — `CmaTotal` diventa 0, senza panic del kernel né avvisi (limite dovuto al confine dei nodi NUMA; si presume che lo stesso vincolo resti anche via overlay)
- **`cma-512` è il valore limite confermato ed è quello raccomandato** (riverificato via overlay su Pi 5 8 GB il 2026-05-16, confermata l'allocazione di `CmaTotal: 524288 kB`)
- Causa radice: il kernel Pi 5 predefinito applica `numa=fake=8`, limitando le allocazioni contigue a un singolo nodo NUMA (1 GB)
- **`dtoverlay=vc4-kms-v3d` + `max_framebuffers=2` consuma ~157 MB di CMA all'avvio** — anche quando l'inizializzazione del driver DRM fallisce (verificato il 2026-04-15)
- **`camera_auto_detect=1`** carica `pisp_be` e `videobuf2_dma_contig`, consumando CMA aggiuntiva. Se ne raccomanda la disattivazione sui sistemi headless
- **Baseline ottimizzata per headless** (entrambi gli overlay disattivati): ~98 MB di CMA usati all'avvio, ~414 MB liberi per i modelli Hailo
- **YOLO InferModel usa 0 MB di CMA** (confermato il 2026-04-15) — solo i modelli GenAI (LLM, Speech2Text) allocano dalla CMA
- Caricamento simultaneo di LLM (qwen2.5-1.5b) + Whisper-base: totale ~328 MB — rientra nella baseline ottimizzata per headless
- La CMA non viene recuperata al riavvio del server — viene rilasciata solo con un riavvio completo del sistema (ripristino dell'alimentazione PCIe) (bug del driver `hailo1x_pci`, già segnalato a Hailo)
- Trattare VDevice come **singleton per la durata del processo**. Vietato l'eviction/reload

---

## 1. Sintomi

Se si imposta `cma=1G` (o `cma=768M`) in `/boot/firmware/cmdline.txt` e si riavvia, si ottiene quanto segue:

```
$ grep CmaTotal /proc/meminfo
CmaTotal:              0 kB
```

Il sistema si avvia normalmente. Nessun panic del kernel, nessun messaggio d'errore. L'impostazione CMA in `cmdline.txt` viene **ignorata silenziosamente**, e l'inizializzazione di tutto ciò che dipende dalla CMA (NPU Hailo-10H, telecamere V4L2, ecc.) fallisce.

**Dopo ogni modifica a `cmdline.txt`, verificare sempre l'allocazione CMA:**

```bash
grep CmaTotal /proc/meminfo
```

---

## 2. Causa radice: il confine dei nodi con `numa=fake=8`

Il kernel predefinito di Raspberry Pi OS per Pi 5 applica `numa=fake=8`, suddividendo gli 8 GB di memoria fisica in **8 nodi NUMA virtuali da 1 GB ciascuno**:

```
numa=fake=8 physical memory layout (8 GB total):

┌──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┐
│ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │
│node0 │node1 │node2 │node3 │node4 │node5 │node6 │node7 │
└──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┘
```

La CMA di Linux (`cma_init_reserved_mem`) deve essere allocata all'avvio come **memoria fisica contigua che non attraversi il confine dei nodi NUMA**.
Questo impone un limite rigido di 1 nodo = 1 GB. Poiché il kernel stesso occupa memoria nello stesso nodo, non è possibile riservare esattamente 1 GB:

> **La tabella seguente è una registrazione delle misurazioni effettuate con il metodo cmdline al 2026-04-15.**
> La conoscenza del valore limite (512M) dovuto al confine dei nodi NUMA resta valida tuttora, ma **il `cma=` in cmdline non va più utilizzato** (vedi la regressione firmware descritta in apertura).
> Il metodo di configurazione attuale è `dtoverlay=cma,cma-512` in `config.txt` (§6).

| Impostazione `cmdline.txt` (registrazione al 2026-04-15) | Risultato |
|---|---|
| `cma=1G` | Tenta di consumare l'intero nodo. Nessuno spazio per il kernel → **fallimento silenzioso**, CmaTotal=0 |
| `cma=768M` | Supera l'intervallo contiguo affidabile → **fallimento silenzioso**, CmaTotal=0 (verificato il 2026-04-15) |
| `cma=512M` | Metà di un nodo → **stabilità confermata** ✓ (verificato il 2026-04-15) ← la raccomandazione dell'epoca. **Ora usare `dtoverlay=cma,cma-512`** |
| `cma=384M` | Non verificato (512M è confermato; 384M non è necessario) |
| `cma=256M` | Stabile, ma risicato con LLM + Whisper contemporanei |
| `cma=128M` | Stabile, ma insufficiente per Hailo GenAI (solo l'LLM richiede ~234 MB) |

### Perché il fallimento è silenzioso

`cma_init_reserved_mem` non genera un panic in caso di fallimento dell'allocazione. Il kernel si avvia con `CmaTotal=0` e si comporta come se la CMA non fosse mai stata richiesta.
Il valore scritto in `cmdline.txt` viene di fatto ignorato.

---

## 3. Requisiti CMA di Hailo-10H

Misurato su Raspberry Pi 5, AI HAT+, HailoRT 5.3.0:

| Modello / combinazione | Uso CMA | Note |
|---|---|---|
| LLM — qwen2.5-1.5b-chat (da solo) | **~234 MB** | Misurato il 2026-04-15 |
| YOLO InferModel (yolov8n, configure + bindings) | **0 MB** | Confermato il 2026-04-15 |
| Whisper-tiny (da solo) | ~70 MB | Stima |
| Whisper-base (da solo) | ~100 MB | Stima |
| Whisper-small (da solo) | ~150 MB | Stima |
| **LLM + Whisper-tiny (contemporanei)** | **~246 MB** | Misurato con CMA 256 MB |
| **LLM + Whisper-base (contemporanei)** | **~334 MB** | Stima. Ci si aspetta che rientri nella baseline headless |

**YOLO usa 0 MB di CMA**: in HailoRT 5.3.0, YOLO InferModel, `configure()` e `create_bindings()` non allocano affatto dalla CMA.
I buffer DMA di input/output vengono mappati da array numpy pre-allocati tramite `set_buffer()`, non dalla CMA.
YOLO non è quindi un fattore nel calcolo del budget CMA.

Applicando CMA 512 MB con l'ottimizzazione headless (vedi §5), ci si aspetta che funzionino le seguenti configurazioni:

- Solo LLM (~234 MB, ~180 MB di margine)
- Solo Whisper-tiny / Whisper-base (rientra facilmente)
- LLM + Whisper-base contemporanei (totale ~334 MB, ~80 MB di margine)

La combinazione di Whisper-small e LLM (stimata ~384 MB) si avvicina al limite teorico — verificare con misurazioni reali prima di farvi affidamento.

Per i dettagli, vedere i risultati dei test di caricamento simultaneo in [hailo_genai_concurrent_2026-04-15.md](../../development/investigations/hailo_genai_concurrent_2026-04-15.md).

---

## 4. La CMA non viene recuperata fino a un riavvio completo

La CMA allocata da HailoRT resta in memoria fino a un riavvio completo del sistema.
Questo vale indipendentemente da `VDevice.release()`, dalla terminazione del processo server o dal reload del modulo kernel.

**Causa radice** (confermata il 2026-04-15): `hailo1x_pci` mantiene le allocazioni DMA coerenti anche dopo la chiusura del fd del device o il reload del modulo.
Vengono rilasciate solo con un riavvio completo (ripristino dell'alimentazione PCIe). Il bug è già stato segnalato a Hailo.

| Fase | CmaFree (CMA 512 MB, ottimizzazione headless) |
|---|---|
| Avvio | **~426 MB** |
| Dopo il caricamento dell'LLM (~234 MB) | ~192 MB |
| Dopo il caricamento di Whisper-base (~100 MB) | ~92 MB |
| Dopo `VDevice.release()` | ~92 MB (**non restituita**) |
| Dopo la terminazione del processo server | ~92 MB (**non restituita**) |
| Dopo `rmmod hailo1x_pci && modprobe hailo1x_pci` | ~92 MB (**non restituita**) |
| Dopo un riavvio completo del sistema | **~426 MB (ripristinata)** |

**Implicazione**: il consumo di CMA si accumula attraverso i riavvii del server all'interno della stessa sessione di avvio.
Non aspettarsi che un riavvio del server recuperi la CMA. Progettare VDevice come **singleton per la durata del processo**.
Se la CMA si esaurisce, viene ripristinata solo con un riavvio completo del sistema.

---

## 5. Ottimizzazione headless: `/boot/firmware/config.txt`

Il `config.txt` predefinito di Pi OS contiene due impostazioni che consumano grandi quantità di CMA anche su sistemi headless (senza display).

### 5.1 `dtoverlay=vc4-kms-v3d` e `max_framebuffers=2`

**Effetto**: il firmware Pi 5 pre-alloca framebuffer CMA per la pipeline del display all'avvio.
Con `max_framebuffers=2`, questo consuma ~157 MB di CMA **prima ancora che i processi in userspace vengano eseguiti**.

L'allocazione persiste anche se il driver DRM di Linux fallisce successivamente l'inizializzazione (ad es. `[drm] Couldn't stop firmware display driver: -22` oppure `Couldn't get core clock` in `dmesg`).

| Stato di `config.txt` | CmaFree all'avvio |
|---|---|
| `dtoverlay=vc4-kms-v3d` + `max_framebuffers=2` attivi (predefinito) | **~257 MB** |
| Entrambi commentati | **~305 MB** (+~48 MB) |

**Correzione** (modalità headless / server):

```ini
# /boot/firmware/config.txt
#dtoverlay=vc4-kms-v3d
#max_framebuffers=2
```

**Compromesso**: `vc4-kms-v3d` è necessario per il display con accelerazione hardware e per il 3D (V3D).
Se si accede al sistema solo via SSH o interfaccia web, disattivarlo è sicuro.

### 5.2 `camera_auto_detect=1` e `display_auto_detect=1`

**Effetto**: questi overlay effettuano il probe delle telecamere CSI e dei display DSI all'avvio, caricando `pisp_be` (Pi ISP backend) e `videobuf2_dma_contig`.
I moduli caricati e l'hardware rilevato pre-allocano varie quantità aggiuntive di CMA.

| Stato di `config.txt` | CmaFree all'avvio |
|---|---|
| `camera_auto_detect=1` + `display_auto_detect=1` | ~305 MB (dopo la disattivazione di vc4) |
| Entrambi impostati a 0 | **~426 MB** (+~121 MB) |

**Correzione**:

```ini
camera_auto_detect=0
display_auto_detect=0
```

**Nota**: `camera_auto_detect=0` influisce solo sulle telecamere CSI. Le telecamere USB (UVC / `uvcvideo`) non ne risentono e continuano a funzionare normalmente.

### 5.3 `config.txt` minimo raccomandato per uso headless con AI HAT+

```ini
auto_initramfs=1
arm_64bit=1
arm_boost=1

[cm5]
dtoverlay=dwc2,dr_mode=host

[all]
dtparam=pciex1_gen=3
```

Stima della CMA all'avvio con questa configurazione: **~98 MB usati**, ~414 MB liberi per i modelli Hailo.

### 5.4 Riepilogo del budget CMA (CMA 512 MB, ottimizzazione headless)

| Configurazione | CmaFree | Disponibile per Hailo |
|---|---|---|
| Predefinita (vc4-kms-v3d + telecamera attivi) | ~257 MB | ~257 MB |
| vc4-kms-v3d + max_framebuffers disattivati | ~305 MB | ~305 MB |
| + camera/display_auto_detect=0 | **~426 MB** | **~426 MB** |
| Dopo il caricamento dell'LLM (~234 MB) | ~192 MB | Per Whisper |
| Dopo il caricamento di LLM + Whisper-base (~100 MB) | ~92 MB | (margine) |

---

## 6. Configurazione raccomandata

### Impostare `dtoverlay=cma,cma-512` (confermato il 2026-05-16)

```bash
# Verificare lo stato CMA attuale
grep CmaTotal /proc/meminfo

# 1) Rimuovere l'eventuale cma= esistente da cmdline.txt (perché rompe il mailbox con il nuovo firmware)
sudo sed -i 's/ *cma=[^ ]*//g' /boot/firmware/cmdline.txt

# 2) Aggiungere dtoverlay=cma,cma-512 alla sezione [all] di config.txt
sudo sed -i '/^\[all\]$/a dtoverlay=cma,cma-512' /boot/firmware/config.txt

# 3) Si raccomanda un riavvio a freddo (staccare e riattaccare l'alimentazione)
sudo sync && sudo poweroff

# Verificare dopo il riavvio (controllare tutti e 4 i punti)
vcgencmd version                                # Risposta Broadcom richiesta (silenzio = fallimento)
grep CmaTotal /proc/meminfo                     # Atteso 524288 kB
journalctl -b -k | grep 'linux,cma'             # Deve comparire "initialized node linux,cma"
journalctl -b -k | grep '0x00030087'            # Non deve comparire
```

Se in dmesg compare `OF: reserved mem: initialized node linux,cma, compatible id shared-dma-pool`, è la prova che l'allocazione è avvenuta tramite il percorso DT.
Al contrario, se compare `Reserved memory: bypass linux,cma node, using cmdline CMA params instead`, significa che è rimasto un `cma=` in cmdline: va rimosso.

### Se si desidera attivare `vc4-kms-v3d`

Se è necessario il KMS DRM per il display, è possibile integrarlo nella forma di argomento dell'overlay:
```ini
dtoverlay=vc4-kms-v3d,cma-512
```
Tuttavia, come indicato al §5.1, vc4-kms-v3d consuma ~157 MB di CMA, quindi per l'uso con Hailo GenAI se ne raccomanda la disattivazione.

### Verificare dopo ogni modifica al kernel / firmware / configurazione

Dopo modifiche a `/boot/firmware/cmdline.txt` o `config.txt`, o dopo un aggiornamento di kernel/firmware, lo stato della CMA e la risposta del mailbox possono cambiare silenziosamente.
Rendere la verifica dei 4 punti sopra indicati una routine post-riavvio.

---

## 7. Interazione con altri problemi di `numa=fake=8`

`numa=fake=8` causa almeno due problemi distinti rilevanti per questo progetto:

| Problema | Sintomo | Causa radice |
|---|---|---|
| Fallimento silenzioso della CMA | `CmaTotal=0` dopo `cma=1G`, `cma=768M` | Il confine dei nodi NUMA limita le allocazioni contigue |
| Fallimento dell'installazione di Node.js | L'installer npm/node si interrompe per un errore di memoria | La memoria per nodo NUMA (1 GB) viene erroneamente rilevata come la RAM totale. Segnalato upstream come [anthropics/claude-code#33864](https://github.com/anthropics/claude-code/issues/33864) |
| Drenaggio CMA di `vc4-kms-v3d` | Consuma ~157 MB all'avvio. Non viene restituita anche se l'init DRM fallisce | `max_framebuffers=2` fa riservare al firmware un framebuffer CMA prima dell'avvio del driver Linux |

Sia il fallimento silenzioso che il drenaggio di vc4 derivano dallo stesso vincolo di fondo (la zona DMA dei primi 4 GB, il confine dei nodi NUMA).
In caso di guasti imprevisti legati alla memoria, controllare prima `/proc/meminfo` e `config.txt`.

---

## 8. Checklist diagnostica rapida

```bash
# 1. Risposta del mailbox (controllo prioritario col nuovo firmware)
vcgencmd version                     # Silenzio = sospetto di cma= residuo in cmdline

# 2. Verificare l'allocazione CMA
grep CmaTotal /proc/meminfo          # 0 kB = fallimento silenzioso

# 3. Verificare il percorso DT vs il percorso cmdline
journalctl -b -k | grep 'linux,cma'
# Atteso: "initialized node linux,cma, compatible id shared-dma-pool" (percorso DT = normale)
# NG:     "bypass linux,cma node, using cmdline CMA params instead" (cma= residuo in cmdline)

# 4. Verificare la topologia NUMA
numactl --hardware                   # Mostra il numero di nodi e la memoria per nodo

# 5. Verificare la command line attuale e la configurazione overlay
cat /boot/firmware/cmdline.txt       # Verificare che non contenga cma=
grep '^dtoverlay=cma' /boot/firmware/config.txt   # dtoverlay=cma,cma-512 deve essere presente

# 6. Verificare la disponibilità del dispositivo Hailo
ls /dev/h1x-*                        # HailoRT 5.3.0: /dev/h1x-0
hailortcli fw-control identify       # Verificare che l'NPU sia accessibile

# 7. Verificare config.txt per i consumatori di CMA
grep -E 'vc4-kms-v3d|camera_auto_detect|display_auto_detect|max_framebuffers' \
  /boot/firmware/config.txt

# 8. Verificare i moduli kernel caricati (utenti della CMA)
lsmod | grep -E 'vc4|v3d|pisp|videobuf2_dma'
```

---

**Ambiente di verifica**: Raspberry Pi 5 8 GB, Raspberry Pi OS
(Linux 6.12.62+rpt-rpi-2712, aarch64), HailoRT 5.3.0, AI HAT+, CMA=512M
(**riverificato il 2026-05-16**: Linux 6.18.29+rpt-rpi-2712 / raspi-firmware 1:1.20260513-1 / pieeprom-2026-05-11 / Hailo-10H AI HAT, 524288 kB allocati via `dtoverlay=cma,cma-512`, risposta mailbox confermata)
