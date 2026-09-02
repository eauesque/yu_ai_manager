# Correzione e verifica del giudizio di mancato rilascio CMA in HailoRT / driver 5.4.0

Creato: 2026-08-16 / Ultimo aggiornamento: 2026-08-17 / Versione di riferimento: yu_ai_manager 4.623.1

Registro della correzione di un errore di giudizio lato misurazione, riguardante un evento che era stato giudicato come mancato rilascio di CMA (vedi `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md`), effettuata mediante verifica dell'ipotesi e test A/B tra la versione ufficiale vanilla e quella corretta con `FOLL_LONGTERM` su `hailo-ai/hailort-drivers` v5.4.0 (pubblicata il 2026-08-16, GPL-2.0, sorgente pubblico).

---

## 1. Conclusione

**Riprova finale del 2026-08-17 (quarto tentativo): il `VERDICT: FAIL` emesso fino al terzo tentativo era un errore di giudizio dovuto all'aver usato, come unico criterio di rilevamento della perdita, la sola quantità di recupero assoluto di `CmaFree` dopo il primo caricamento di un HEF. Confrontando in A/B la versione ufficiale vanilla 5.4.0 e la versione corretta con `FOLL_LONGTERM`, sono riusciti tutti i test: caricamenti consecutivi partendo da `CmaFree` basso, rilascio e ricaricamento all'interno dello stesso processo, 20 generazioni consecutive, e l'intera ripetizione dei test partendo da uno stato di `CmaFree` ancora più basso. Non si è osservato alcun incremento o decremento monotono di RSS e `CmaFree` durante la generazione, e i fallimenti di allocazione CMA sono stati zero. Il calo iniziale di `CmaFree` corrisponde all'aumento della cache delle pagine per l'HEF di più GB, e `MemAvailable` si è mantenuto intorno ai 7GB. Nelle condizioni testate in questa occasione — Pi 5 + Hailo-10H + HailoRT/driver 5.4.0, singolo modello, singolo dispositivo, ripetizioni di breve durata — la perdita di CMA non si riproduce in condizioni pratiche, e la correzione con `FOLL_LONGTERM` non porta alcun miglioramento misurabile. Il funzionamento continuo prolungato, l'uso simultaneo di più modelli, Hailo-8 e il funzionamento sotto IOMMU non sono stati testati e restano fuori dall'ambito di questa conclusione.**

### 1.1 Evoluzione del giudizio

| Tentativo | Data | Giudizio al momento | Motivo dell'aggiornamento/correzione |
|---|---|---|---|
| Primo | 2026-08-16 | Impossibile giudicare | Aggiornando solo il driver a 5.4.0, la verifica di corrispondenza esatta con la library 5.3.0 rifiutava le chiamate API (§3) |
| Secondo | 2026-08-17 | Completati solo test limitati | Allineati driver/library/firmware a 5.4.0, le ripetizioni di `run2` hanno raggiunto un plateau, ma la riproduzione diretta tramite pyhailort non era ancora stata eseguita (§4) |
| Terzo | 2026-08-17 | `FAIL` provvisorio (poi rivelatosi un errore di giudizio) | Vecchio risultato diagnostico basato solo sulla quantità di recupero assoluto di `CmaFree` dopo il primo caricamento HEF. Una misurazione singola non permetteva di distinguere tra perdita di memoria e utilizzo della cache delle pagine (§5, §7) |
| Quarto | 2026-08-17 | Nessuna perdita riproducibile in condizioni pratiche | Corretto il terzo tentativo misurando A/B vanilla / `FOLL_LONGTERM`, ripetizioni con CMA basso, ricaricamento nello stesso processo, 20 generazioni, RSS, `MemAvailable` e fallimenti di allocazione (§8) |

---

## 2. Differenze del codice sorgente v5.3.0 → v5.4.0 (`hailo-ai/hailort-drivers`)

Diff di tutti i file tra i due tag tramite GitHub API. Trattandosi di un singolo commit squash, il commit message non fornisce informazioni utili; la verifica è stata fatta sul diff dei file reali. Non ci sono modifiche alla **logica stessa** di allocazione/rilascio della CMA (coppia `dma_alloc_coherent`/`dma_free_coherent`); le modifiche seguenti sono principalmente refactoring e correzioni difensive:

| File | Contenuto della modifica |
|---|---|
| `linux/utils/compact.h` → `compat.h` | Rinomina del file del layer di compatibilità del kernel |
| `linux/vdma/memory.c` | Aggiunto controllo NULL a `hailo_desc_list_release()`, puntatore azzerato a NULL dopo il rilascio (correzione difensiva per **prevenire il doppio rilascio**) |
| `linux/vdma/vdma.h` | Rimosso il campo ridondante `kernel_address` da `hailo_descriptors_list_buffer` (integrato in `desc_list.descs`) |
| `common/vdma_common.c` | Riscritta la logica di determinazione del completamento del trasferimento DMA, dal calcolo diretto di `hw_num_proc` al confronto `num_proc`/`num_avail` (possibile correzione di bug nel tracciamento del completamento del trasferimento) |
| `linux/vdma/monitor.c` | `del_timer_sync` → `timer_delete_sync` (adeguamento al nuovo nome dell'API del kernel) |
| `common/pcie_common.c` | Rimosso il campo md5 dal protocollo di controllo del firmware, rafforzata la verifica di corruzione dei log SCU dai soli primi 4 byte al controllo completo delle prime 5 word |

Anche il testo dei messaggi di errore è cambiato (da una descrizione lunga a `out of CMA memory.`, abbreviato), ma il flusso di controllo di allocazione/rilascio è identico. **Da questo solo diff non si legge alcuna modifica corrispondente all'ipotesi dell'epoca (mancato rilascio di CMA al ricaricamento del modello)**.

---

## 3. Sostituzione sul dispositivo reale e problemi riscontrati (2026-08-16, primo tentativo)

Su Raspberry Pi 5 + Hailo-10H, con `hailo1x_pci 5.3.0` in funzione (gestito da dkms), è stato tentato il passaggio a v5.4.0 tramite build manuale.

### 3.1 `make install` non dipende da `all`

Il target `install` del `linux/pcie/Makefile` esegue solo `modules_install` e completa senza avvisi anche se il prodotto della build (`.ko`) non esiste (più precisamente compare un avviso sull'assenza di `System.map`, ma non fa capire che la causa è la mancata build).

```makefile
install:
	$(Q)$(MAKE) -C $(KERNEL_DIR) M=$(PWD) INSTALL_MOD_DIR=kernel/drivers/misc modules_install
	$(Q)$(DEPMOD) -a

all: $(TARGET_DIR) print-versions
	$(Q)$(MAKE)  -C $(KERNEL_DIR) M=$(PWD) $(GDB_FLAG) $(USER_FLAGS) modules
	$(Q)cp $(DRIVER_NAME_NO_EXT)* $(TARGET_DIR)
```

**Eseguire sempre nell'ordine `make all && sudo make install`.**

### 3.2 Gli header del kernel di Raspberry Pi non includono `System.map`

Durante l'esecuzione di `modules_install` compare il seguente avviso e `depmod` viene saltato silenziosamente:

```
Warning: modules_install: missing 'System.map' file. Skipping depmod.
```

Ciò accade perché `/usr/src/linux-headers-<kernelver>/System.map` non esiste. Poiché `/boot/System.map-<kernelver>` esiste, si risolve copiandolo:

```bash
sudo cp /boot/System.map-$(uname -r) /usr/src/linux-headers-$(uname -r)/System.map
sudo depmod -a
```

Se non si esegue questo passaggio, `modprobe` non riesce a risolvere il `.ko` appena installato e si ottiene `FATAL: Module hailo1x_pci not found` (anche se il file `.ko` esiste effettivamente in `/lib/modules/<kernelver>/kernel/drivers/misc/`).

### 3.3 Le regole udev non vengono applicate immediatamente senza reload/trigger

`/lib/udev/rules.d/51-hailo-pcie-udev.rules`:

```
SUBSYSTEM=="hailo1x", MODE="0666"
```

Subito dopo la sostituzione del modulo, `/dev/h1x-0` diventa `crw-------` (solo root). Si risolve con:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hailo1x
```

### 3.4 L'incompatibilità di versione tra driver e library è fatale

Eseguendo `hailortcli` con solo il driver del kernel aggiornato a 5.4.0:

```
dmesg: Mismatch Driver version pcie driver 5:4:0 pci_ep driver 5:3:0
dmesg: hailo_soc_get_driver_info has failed with err -22

hailortcli: [HailoRT] [error] CHECK failed - Driver version (5.4.0) is different from library version (5.3.0)
hailortcli: [HailoRT] [error] Driver version mismatch, status HAILO_INVALID_DRIVER_VERSION(76)
```

La library HailoRT richiede una **corrispondenza esatta** con il driver del kernel; se si aggiorna solo uno dei due in anticipo, tutte le chiamate API vengono rifiutate immediatamente. Non è possibile verificare il solo driver vanilla in isolamento: è necessario aggiornare contemporaneamente anche il pacchetto userspace `hailort` (il corpo dell'SDK).

- `apt-cache policy hailort` → candidato 5.3.0 (alla data odierna, 5.4.0 non è ancora distribuito sull'apt ufficiale)
- `gh api repos/hailo-ai/hailort/releases` → il tag `v5.4.0` esiste ma `assets` è vuoto (nessun deb precompilato, solo sorgente)

In altre parole, **senza installare HailoRT tramite deb o costruirlo completamente dal sorgente, non è possibile verificare 5.4.0 sul campo**. Una build completa comporterebbe una build corposa di CMake C++ + binding Python, con il rischio di coinvolgere anche pacchetti dipendenti come `hailo-tappas` e `python3-hailort`; per questo motivo, nel primo tentativo si è deciso di rimandare e attendere la distribuzione ufficiale del deb.

---

## 4. Registro della procedura di build personalizzata (2026-08-17, secondo tentativo)

Procedura e problemi riscontrati costruendo autonomamente dal sorgente GitHub (driver: GPL-2.0, corpo di `hailort`: MIT), senza attendere la distribuzione apt/deb ufficiale, e installando il risultato sul sistema.

### 4.1 Ambiente di build

- Installato `checkinstall` (`sudo apt-get install -y checkinstall`). Tuttavia lo step di compressione `xz` del modulo kernel entra in conflitto con `installwatch` (il meccanismo di tracciamento file basato su LD_PRELOAD di checkinstall), e l'esecuzione di `make install` tramite checkinstall falliva ogni volta. **Per pacchettizzare i moduli kernel non usare checkinstall, ma dkms (per il driver vero e proprio) o il semplice `make install` (per la library userspace)**
- Liberata memoria prima della build: sospesi temporaneamente i processi duplicati di `headroom mcp serve` e `rust-analyzer` (liberato in totale poco meno di 1 GB). La memoria del Pi è di 7,9 Gi; anche durante la build si è potuto mantenere una disponibilità di circa 3,8 Gi

### 4.2 Build di `hailort` (library userspace)

```bash
git clone --branch v5.4.0 --depth 1 https://github.com/hailo-ai/hailort.git
cd hailort/build   # dopo aver creato la directory
cmake .. -DCMAKE_BUILD_TYPE=Release   # 外部依存(protobuf/spdlog/eigen等)を FetchContent で自動取得、約4分
cmake --build . -j2   # -j2 に制限(メモリ逼迫回避)、約15分
sudo make install     # /usr/local/{include,lib,bin} に配置。apt 版(5.3.0, /usr 配下)と共存可能
```

Poiché i valori predefiniti delle `option()` hanno tutti i componenti pesanti (GStreamer, test, server, integrazione Ollama, ecc.) impostati su OFF, viene costruita solo una configurazione relativamente leggera con `libhailort.so`, `hailortcli` e `libhailopp`.

**Nota**: il prodotto di `make install` viene collocato sotto `/usr/local` e non sovrascrive la versione apt (sotto `/usr`, 5.3.0). Durante la verifica di funzionamento è necessario specificare esplicitamente il percorso, come in `LD_LIBRARY_PATH=/usr/local/lib /usr/local/bin/hailortcli ...`.

### 4.3 Sostituzione del driver (modulo kernel) e aggiornamento del firmware

Il driver stesso è stato costruito e installato tramite dkms (sostituendo con `-v 5.4.0`, con la stessa procedura del ripristino dell'appendice A), poi ricaricato con `rmmod`/`modprobe`. A questo punto `hailortcli` restituiva `HAILO_DRIVER_OPERATION_FAILED(36)` e in dmesg compariva `Mismatch Driver version pcie driver 5:4:0 pci_ep driver 5:3:0`; si è scoperto che **anche il firmware sul dispositivo (lato SoC, pci_ep) deve essere aggiornato separatamente a 5.4.0**.

```bash
# Ottiene il firmware dall'S3 ufficiale (usando lo script incluso nel repository del driver)
bash hailort-drivers/download_firmware_hailo10h.sh
# Esegue il backup del firmware esistente prima di sostituirlo con la nuova versione
sudo cp -r /lib/firmware/hailo/hailo10h /lib/firmware/hailo/hailo10h.backup-5.3.0
sudo cp <展開先>/hailo10h_fw_5.4.0/* /lib/firmware/hailo/hailo10h/
sudo chown -R root:root /lib/firmware/hailo/hailo10h/
```

A questo punto si è tentato di ricaricare il modulo (`rmmod`/`modprobe`, incluso `support_soft_reset=1`), ma dmesg continuava a restituire costantemente `SOC Firmware batch was already loaded`. Controllando il sorgente del driver, si è visto che `load_soc_firmware()` (il percorso di caricamento del firmware SoC per Hailo-10H) non implementa l'elaborazione di soft reset tramite `support_soft_reset` (implementata solo in `load_nnc_firmware()` per Hailo-8), ed è implementato in modo da essere saltato incondizionatamente finché `hailo_pcie_is_firmware_loaded()` restituisce true. In altre parole, **lo stato del firmware sul SoC non può essere modificato tramite ricaricamento del modulo, ed è indispensabile un ciclo di alimentazione del dispositivo reale**.

Dopo il riavvio, dmesg ha registrato la scrittura del batch di firmware (`customer_certificate.bin`, `scu_fw.bin`, `u-boot-*.dtb.signed`, `u-boot-spl.bin`, `fitImage`, `image-fs`, in quest'ordine, 4064 ms) seguita da `SOC Firmware Batch loaded successfully`, e `hailortcli fw-control identify` ha risposto correttamente con `Firmware Version: 5.4.0 (release,app)`.

### 4.4 Verifica semplificata del comportamento CMA e limiti

Osservato l'andamento di `CmaFree` (`/proc/meminfo`) con `hailortcli run2` (resnet_v1_18.hef, un modello piccolo incluso nel pacchetto `hailo_tutorials`), sia in un singolo load/run/exit sia in 8 esecuzioni consecutive:

| Esecuzione | CmaFree (kB) |
|---|---|
| baseline (subito dopo il riavvio) | 170464 |
| iter 1 | 134864 |
| iter 2 | 134144 |
| iter 3-8 | 133744 (nessuna variazione, plateau) |

Si raggiunge un plateau dopo poche ripetizioni e non si è osservata alcuna perdita aggiuntiva fino all'ottava esecuzione. Tuttavia si tratta di un semplice load/run/exit via CLI (avvio in processi separati), un percorso diverso da entrambe le due perdite note segnalate in `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md` — (a) il mancato rilascio al momento di `VDevice.release()`/ricaricamento del modello **all'interno dello stesso processo**, (b) la perdita continua durante l'esecuzione di `generate_stream()` (inferenza LLM) — e quindi questo risultato non costituisce prova che il problema sia "risolto".

La riproduzione principale (`tools/diag_hailo_cma_reclaim.py` e lo script descritto nel documento forum-followup) carica il LLM GenAI tramite il binding Python `hailo_platform` (pyhailort), e quindi non poteva essere eseguita così com'era nell'ambiente 5.4.0:

```
$ .venv 内の hailo_platform は libhailort.so.5.3.0 に固定リンク（ldd で確認）
$ VDevice() 構築時に driver(5.4.0)/library(5.3.0) のバージョン不一致で同じ HAILO_INVALID_DRIVER_VERSION に該当する見込み
```

A questo punto la ricostruzione di pyhailort (binding Python) dal sorgente 5.4.0 e la sua sostituzione nel `.venv` non era ancora stata avviata, ma è stata eseguita nel terzo tentativo (§5).

---

## 5. Ricostruzione di pyhailort e riesecuzione della riproduzione (2026-08-17, terzo tentativo)

Questa sezione registra il giudizio provvisorio al momento del terzo tentativo. Il metodo di giudizio e la conclusione sono stati corretti nel test A/B del quarto tentativo (§8).

### 5.1 Build di pyhailort (binding Python)

`hailort/libhailort/bindings/python/platform/` nel repository principale di `hailort` è la sorgente del pacchetto pip di pyhailort (`pyproject.toml`, basato su scikit-build-core + pybind11). Build eseguita collegando esplicitamente libhailort 5.4.0 già collocato in `/usr/local` in §4.2:

```bash
cd hailort/libhailort/bindings/python/platform
CMAKE_ARGS="-DLIBHAILORT_PATH=/usr/local/lib/libhailort.so.5.4.0 -DHAILORT_INCLUDE_DIR=/usr/local/include" \
  <venv>/bin/python -m pip install .
```

All'interno dell'isolamento della build, `scikit-build-core`/`pybind11` sono stati recuperati automaticamente da PyPI per la build; il wheel `hailort` del `.venv` è stato sostituito da 5.3.0 a 5.4.0. Con `ldd` si è confermato che `_pyhailort*.so` è collegato a `/usr/local/lib/libhailort.so.5.4.0`, e anche il construct/release di `VDevice()` funzionava correttamente da solo.

### 5.2 Riesecuzione della riproduzione esistente (`tools/diag_hailo_cma_reclaim.py`)

Con lo stesso script di riproduzione, lo stesso criterio di giudizio e lo stesso HEF (`~/hailo_models/Qwen3-1.7B-Instruct.hef`) di 2026-05, si è rimisurato nello stesso ambiente, sostituendo solo `hailo_platform` del `.venv` con la versione 5.4.0:

```bash
uv run python tools/diag_hailo_cma_reclaim.py --signal terminate
```

Risultato (`logs/hailo_cma_reclaim_poc.json`):

| Evento | CmaFree (MB) |
|---|---|
| baseline_before_spawn | 159 |
| after_vdevice_created / after_llm_loaded | 22 (consumati 137 MB) |
| subito dopo child kill (`terminate`) | 23 |
| post_wait +5s | 26 |
| post_wait +10s | 28 |
| post_wait +15s | 29 |
| post_wait +20s-+30s | **0** (ulteriore calo di circa 28,5 MB da 29 MB; anche dopo diversi minuti, `CmaFree` rimane bloccato intorno a 512 kB) |

Non si è potuto confermare che questo ulteriore calo da 29 MB a circa 512 kB fosse dovuto a competizione con altri processi nello stesso momento, ma resta un'osservazione non chiarita di cui non si è potuta identificare la causa solo con questa misurazione. L'utilizzo della cache delle pagine dopo il primo caricamento (§8.4) da solo non spiega questo andamento intermedio, e poiché questa esecuzione non include un test ripetuto con raccolta simultanea di RSS, `MemAvailable` e fallimenti di allocazione, non viene usata come base per il giudizio finale di §8.

Tuttavia, questo intorno di 512 kB è nella stessa fascia dei 464→1.648 kB osservati durante il test `FOLL_LONGTERM` di §8.3, e da quello stato si sono riusciti 20 generazioni, il rilascio e il ricaricamento. Il processo con cui si è arrivati a questo valore basso resta non chiarito, ma è stato confermato sul dispositivo reale che **`CmaFree` in questa fascia, di per sé, non implica immediatamente uno stato pericoloso o l'impossibilità di caricamento**.

Testo originale prodotto dal vecchio strumento diagnostico (giudizio provvisorio al momento del terzo tentativo; il giudizio finale è stato corretto in §8):

```
VERDICT: FAIL — only -22 MB recovered after kill+wait. spec hypothesis invalid → pivot to auto-reboot alternatives
```

Ciò che è stato accertato in questo tentativo è soltanto che `CmaFree`, dopo il primo caricamento HEF, non si è ripristinato secondo il vecchio criterio di giudizio. Non è stata dimostrata né la perdita di memoria disponibile dopo la terminazione del processo, né il mancato fix della perdita in v5.4.0. Nel terzo tentativo si è interpretato provvisoriamente come mancato rilascio, ma tale interpretazione e il relativo metodo di giudizio sono stati corretti in §8.

---

## 6. Crash del kernel durante il terzo tentativo e ripristino del codice di debug CMA (2026-08-17)

### 6.1 Evento e possibili cause

Per indagare il percorso di rilascio della CMA, era stato aggiunto al sorgente DKMS locale `linux/vdma/memory.c` l'include di `linux/mm.h` e codice di strumentazione che chiama `virt_to_page()` / `page_count()` subito prima di `dma_free_coherent()`. Caricando un modulo con questa modifica, il sistema si bloccava durante l'uso di Hailo diventando inavviabile; per questo motivo, attualmente il caricamento automatico è bloccato tramite `module_blacklist=hailo1x_pci,hailo_pci` in `/boot/firmware/cmdline.txt`.

Convertire direttamente in pagina, tramite `virt_to_page()`, l'indirizzo virtuale CPU restituito da `dma_alloc_coherent()` non fa parte del contratto della DMA API. Poiché il formato di mappatura dell'indirizzo restituito è demandato all'allocator, il `page_count()` ottenuto in questo modo non è un mezzo corretto per osservare il conteggio dei riferimenti CMA e può generare riferimenti a pagine non validi. Il codice di strumentazione veniva eseguito su entrambi i percorsi di rilascio, sia della descriptor list sia del continuous buffer.

L'orario di aggiunta era 10:15:36 e l'inizio della relativa build DKMS 10:15:39, quindi si può concludere che il modulo bloccato includesse questo codice. Non è stato possibile ottenere lo stack trace immediatamente precedente al crash, quindi non si tratta di una determinazione rigorosa della causa, ma essendo l'unica modifica locale al codice eseguibile assente nella vanilla v5.4.0, viene considerata la causa più probabile.

### 6.2 Stato ripristinato

Sono state rimosse le seguenti 7 righe (l'include di `linux/mm.h` e i log `virt_to_page()` / `page_count()` in due punti), e la DKMS è stata ricostruita completando anche `depmod`.

- Kernel: `6.18.39+rpt-rpi-2712`
- Modulo ricostruito: `/lib/modules/6.18.39+rpt-rpi-2712/updates/dkms/hailo1x_pci.ko.xz`
- Il modulo sopra indicato è già registrato in `modules.dep`
- La blacklist rimane attiva; il modulo ricostruito non è ancora stato caricato

La prossima volta, dopo aver assicurato un percorso di ripristino come una console seriale, si rimuoverà la blacklist e si verificherà il primo caricamento tramite riavvio. Per l'indagine sul problema stesso del mancato rilascio della CMA, non si reintrodurrà la strumentazione che converte l'indirizzo restituito dalla DMA API in pagina interna; si osserveranno invece il registro dei buffer mantenuto dal driver, la dimensione delle allocazioni e il numero di chiamate a `dma_free_coherent()`.

**Aggiunta (2026-08-17, più tardi)**: dopo aver preparato un backup di `cmdline.txt` (`cmdline.txt.bak-blacklisted`), si è rimossa la blacklist e riavviato, confermando un avvio regolare (anche la console seriale `console=serial0,115200` è configurata, garantendo un percorso di ripristino). Da qui in avanti l'indagine è proseguita con la strumentazione sicura di §7 (nessuna ispezione di pagine grezze, solo output di log dei contatori e delle dimensioni esistenti).

---

## 7. Formazione ed esclusione delle ipotesi causali — verifica e confutazione di `FOLL_LONGTERM` (2026-08-17)

Questa sezione registra la formazione delle ipotesi causali derivate dal terzo tentativo e i candidati causali esclusi tramite esperimenti. Il ruolo qui è restringere i candidati; il giudizio finale sulla presenza o assenza di una perdita CMA dipende dal test A/B del quarto tentativo (§8).

Sulla base del crash di §6, l'indagine è proseguita con una strumentazione sicura che evita l'accesso diretto alle pagine tramite `virt_to_page()` e simili (solo output di log tramite `dev_err()`, senza ispezione o conversione di puntatori grezzi).

### 7.1 Contenuto della strumentazione

Nei seguenti punti di `linux/vdma/memory.c` / `linux/vdma/ioctl.c` / `linux/vdma/vdma.c` sono stati aggiunti log che riportano i contatori atomici esistenti (`controller->desc_cma_in_use` / `controller->cma_in_use`) e la dimensione delle allocazioni (senza alcun accesso diretto alle pagine):

- `hailo_desc_list_create`/`hailo_desc_list_release` (alloc/free della descriptor list)
- `hailo_vdma_continuous_buffer_alloc`/`hailo_vdma_continuous_buffer_free` (alloc/free del continuous buffer)
- `hailo_desc_list_release_ioctl`/`hailo_vdma_continuous_buffer_free_ioctl` (percorso ioctl di rilascio esplicito)
- `hailo_vdma_buffer_map`/`hailo_vdma_buffer_destroy` (percorso di mappatura/smappatura DMA dei buffer userspace; vengono riportati anche `buffer_type`/`is_mmio`/`is_dmabuf`)
- `hailo_vdma_file_context_finalize` (pulizia collettiva al momento di fops_release, con output dei contatori a ENTER/EXIT)

### 7.2 Risultati osservati

Eseguito `tools/diag_hailo_cma_reclaim.py --signal terminate` subito dopo il riavvio (`CmaFree` ≈ 451 MB), raccogliendo e aggregando tutti i log con `sudo dmesg | grep CMA_DBG`.

- **`CmaFree` di `/proc/meminfo`**: 451 MB → 195 MB (**consumati 256 MB**) → 204 MB anche dopo kill + 30 secondi di attesa (**valore inferiore di 247 MB rispetto al baseline**)
- **`desc_cma_in_use` del driver stesso (descriptor list, via `dma_alloc_coherent`)**: al massimo circa 2-4 MB. Torna sicuramente a 0 al momento di EXIT di `file_context_finalize`
- **`cma_in_use` (continuous buffer, via `dma_alloc_coherent`)**: sempre 0 durante questa sessione (il continuous buffer non è mai stato usato)
- **Mappatura DMA dei buffer userspace (`hailo_vdma_buffer_map`, `buffer_type=0`=`HAILO_DMA_USER_PTR_BUFFER`, `is_mmio=0`, `is_dmabuf=0`)**: chiamata 621 volte, di cui **342 volte di dimensione 8 MB (`0x800000`)** (in totale chiamate di mappatura per 2,7 GB; sembra che lo stesso buffer di staging lato host venga riutilizzato nell'elaborazione della pipeline). `hailo_vdma_buffer_destroy` è stata chiamata 628 volte, in corrispondenza quasi 1:1 con `buffer_map`, e **non risulta compromesso il registro di mappatura del driver stesso** (`dma_unmap_sg` viene chiamata correttamente)
- **SWIOTLB (`/sys/kernel/debug/swiotlb/`)**: `io_tlb_used_hiwater=0`. Il bounce buffer non è mai stato usato
- Il dispositivo Hailo non è sotto IOMMU (`/sys/bus/pci/devices/0001:01:00.0/iommu_group` assente)

A questo punto, non le allocazioni del driver stesso della famiglia `dma_alloc_coherent()` (desc list, continuous buffer), ma il percorso gestito da `hailo_vdma_buffer_map()` — "mappatura per DMA di memoria già allocata dallo userspace" (`HAILO_DMA_USER_PTR_BUFFER`) — è stato interpretato come candidato causa del calo di CMA. In questo percorso il driver non alloca nuova CMA, ma fissa (pin) le pagine utente esistenti per renderle utilizzabili in DMA.

### 7.3 Ipotesi causale: `FOLL_LONGTERM` non specificato in `get_user_pages()`

Verificando `prepare_sg_table()` di `linux/vdma/memory.c` (chiamata internamente da `hailo_vdma_buffer_map()`):

```c
pinned_pages = compat_get_user_pages(user_address, npages, FOLL_WRITE | FOLL_FORCE, pages);
```

`compat_get_user_pages` (poiché questo kernel 6.18.39 rientra in `LINUX_VERSION_CODE >= KERNEL_VERSION(6, 5, 0)`) è semplicemente un alias di `get_user_pages()`, e **il flag `FOLL_LONGTERM` non è specificato**. Anche il lato di rilascio (`clear_sg_table()`) chiama il corrispondente `put_page()`; non si usa la nuova famiglia di API `pin_user_pages()`/`unpin_user_pages()`, ma restano quelle tradizionali `get_user_pages()`/`put_page()`.

Secondo le prassi documentate del kernel Linux (`Documentation/core-api/pin_user_pages.rst`), il codice che, come i trasferimenti DMA, **mantiene a lungo un riferimento alle pagine dovrebbe usare `pin_user_pages()` con `FOLL_LONGTERM`**. Se `FOLL_LONGTERM` non viene specificato, anche quando una pagina utente che si trovava per caso nella regione CMA viene fissata con `get_user_pages()`, la proprietà originaria della CMA di essere "spostabile verso altri usi quando necessario" (migratable) viene disattivata a lungo termine. L'allocatore CMA normalmente migra tale pagina fuori dalla regione CMA prima del fissaggio a lungo termine, ma nei percorsi che non usano `FOLL_LONGTERM` questa migrazione non avviene; quindi **finché la pagina resta fissata, viene di fatto persa dalla regione CMA in quella misura, e anche dopo il rilascio (`put_page()`) non viene immediatamente riconosciuta come spazio libero della CMA** (poiché sono necessarie ulteriori operazioni di migrazione/compattazione).

Questa ipotesi era coerente con la misurazione singola al momento del terzo tentativo (§7.2):

- I contatori CMA del driver stesso non sono coinvolti (`get_user_pages` non passa per `dma_alloc_coherent`)
- Il numero di chiamate map/destroy è correttamente bilanciato (`put_page()` stessa viene chiamata correttamente; il problema è che il "ritorno" alla CMA dopo il rilascio è lento/incompleto)
- Caricando un LLM grande come Qwen3-1.7B-Instruct, viene allocata e mappata in DMA una grande quantità di buffer da 8 MB sulla memoria host, e il problema si manifesta se una parte di essi include pagine all'interno della regione CMA
- È coerente anche con il recupero lento e parziale di `CmaFree` dopo il kill (circa +15-30 MB in 30 secondi, con un aumento graduale nei minuti successivi) (`put_page()` stessa viene sicuramente chiamata alla terminazione del processo, ma sembra necessario un ulteriore trattamento per il recupero come spazio libero della CMA)

### 7.4 Implementazione del candidato di correzione e verifica sul dispositivo reale → confutazione (2026-08-17, seguito)

Si è effettivamente sostituito `prepare_sg_table()` da `get_user_pages(FOLL_WRITE | FOLL_FORCE)` + `put_page()` a `pin_user_pages(FOLL_WRITE | FOLL_FORCE | FOLL_LONGTERM)` + `unpin_user_page()`, aggiungendo l'include di `<linux/mm.h>`, e si è completata la build, la ri-registrazione dkms e il caricamento sul dispositivo reale (si è confermato che i simboli `pin_user_pages`/`unpin_user_page` vengono risolti correttamente con `modprobe --dump-modversions`).

Risultato dell'esecuzione della stessa riproduzione partendo dallo stato di `CmaFree` alto (453 MB) subito dopo il riavvio:

| | Prima della correzione (n=più run) | Dopo la correzione (n=1) |
|---|---|---|
| baseline | 436-451 MB | 453 MB |
| after_llm_loaded | 173-195 MB (consumati 256-263 MB) | 180 MB (consumati 273 MB) |
| after_post_wait | 188-204 MB (recuperati 9-15 MB) | 190 MB (**recuperati 10 MB**) |
| `VERDICT` secondo il vecchio criterio | `FAIL` | **`FAIL` (nessun cambiamento)** |

> Questa tabella è asimmetrica nel numero di run e nel metodo di aggregazione, e non costituisce un confronto A/B rigoroso. Il giudizio A/B si basa sui risultati di §8, ripetuti nelle stesse condizioni.

Verificando `CMA_DBG buffer_map` con `dmesg`, si è visto che anche dopo la correzione lo stesso buffer di dimensione 0x800000 (8 MB) veniva mappato senza problemi tramite `pin_user_pages` (nessun fallimento di pin né avviso del kernel), e il percorso di codice stesso veniva eseguito come previsto. Anche la compattazione forzata tramite `echo 1 > /proc/sys/vm/compact_memory` non ha avuto effetto. `MemAvailable` è rimasto sano a 7,1 GB, e anche il fatto che non fosse una carenza di memoria dell'intero sistema ma solo la specifica contabilità di `CmaFree` a non recuperarsi era identico a prima della correzione.

**Conclusione: l'ipotesi della mancanza di `FOLL_LONGTERM` è stata confutata dall'esperimento.** La sostituzione da `get_user_pages()` a `pin_user_pages()`+`FOLL_LONGTERM` è un miglioramento legittimo in linea con le prassi documentate del kernel Linux, ma non era la causa diretta del sintomo di mancato rilascio della CMA osservato in questa sessione. L'ipotesi in sé è teoricamente fondata (l'interazione tra il meccanismo di migrazione della CMA e il fissaggio a lungo termine è una categoria di problema nota e reale), e resta valida come osservazione sulla qualità del codice, ma si giudica che **non sia la causa radice che spiega da sola i risultati misurati in questa occasione**.

### 7.5 Esclusione dei candidati causali (il giudizio finale è in §8)

Di seguito i candidati causali che sono stati **esclusi** chiaramente tramite esperimento. Questo elenco è valido come risultato della verifica delle ipotesi, ma non costituisce di per sé il giudizio sulla presenza o assenza di una perdita.

- Le allocazioni del driver stesso via `dma_alloc_coherent()` (desc list, continuous buffer) — solo pochi MB, tornano correttamente a 0
- L'incoerenza delle chiamate map/destroy della mappatura SG — sono bilanciate
- Il bounce buffer SWIOTLB — mai usato (`io_tlb_used_hiwater=0`)
- La mancanza di `FOLL_LONGTERM` in `get_user_pages()` — la correzione è stata implementata e verificata sul dispositivo reale, ma senza miglioramento

Il fatto rimasto fino al terzo tentativo era che, restando `MemAvailable` sano, solo `CmaFree` diminuiva dopo il primo caricamento. All'epoca questo è stato interpretato come mancato rilascio, ma un singolo tentativo non permette di distinguere tra "perdita di memoria disponibile" e "riconversione di pagine CMA movable in cache delle pagine". Nel quarto tentativo si è riprovato partendo da `CmaFree` basso, misurando l'effettiva possibilità di caricamento, la diminuzione netta nelle ripetizioni, l'RSS e i fallimenti di allocazione CMA, correggendo così il giudizio.

---

## 8. Quarto tentativo: nuovo test A/B vanilla / `FOLL_LONGTERM` e conferma dell'errore di giudizio (2026-08-17)

### 8.1 Oggetti del confronto

- Versione corretta con `FOLL_LONGTERM`: `pin_user_pages(FOLL_LONGTERM)` / `unpin_user_page()`, al caricamento `srcversion=C84A00ABB326748A1832CE1`
- Vanilla ufficiale 5.4.0: tag `v5.4.0`, commit `b6dd17c609504e648eb516ff4a867167edf56f3c`, `get_user_pages()` / `put_page()`, al caricamento `srcversion=A260C39C9F2C06DD4FB072E`
- Kernel: `6.18.39+rpt-rpi-2712`
- HEF: `Qwen3-1.7B-Instruct.hef` (2.880.748.478 byte)

### 8.2 Due caricamenti consecutivi in processi indipendenti

| Driver | Tentativo | baseline | loaded | dopo exit | variazione rispetto al baseline | Caricamento |
|---|---:|---:|---:|---:|---:|---|
| `FOLL_LONGTERM` | 1 | 338 MB | 34 MB | 25 MB | **-313 MB (diminuzione)** | Riuscito |
| `FOLL_LONGTERM` | 2 | 5 MB | 6 MB | 7 MB | **+2 MB (aumento)** | Riuscito |
| vanilla | 1 | 376 MB | 99 MB | 112 MB | **-264 MB (diminuzione)** | Riuscito |
| vanilla | 2 | 125 MB | 118 MB | 124 MB | **-1 MB (diminuzione)** | Riuscito |

In entrambi i driver, solo al primo caricamento `CmaFree` diminuiva sensibilmente, e il secondo caricamento partendo da quel valore basso riusciva con una diminuzione netta quasi nulla. La vecchia diagnosi giudicava solo in base a "quanti MB sono tornati rispetto a quanto consumato durante il caricamento", classificando così come `FAIL` anche casi normali come il secondo, in cui `CmaFree` era già basso fin dall'inizio.

### 8.3 Generazione, rilascio e ricaricamento nello stesso processo

| Metrica | `FOLL_LONGTERM` | vanilla, 1° volta | vanilla, ripetizione a CMA basso |
|---|---:|---:|---:|
| Generazioni completate | 20/20 | 20/20 | 20/20 |
| 1° caricamento | Riuscito | Riuscito | Riuscito |
| 2° caricamento dopo il rilascio | Riuscito | Riuscito | Riuscito |
| `CmaFree` dalla generazione 1 alla 20 | 464→1.648 kB | 115.376→123.728 kB | 82.320→83.296 kB |
| `MemAvailable` dalla generazione 1 alla 20 | 6.706.208→6.788.432 kB | 6.830.352→6.910.560 kB | 6.871.504→6.906.368 kB |
| RSS durante la generazione | fisso a 63.888 kB | 63.904-63.920 kB | 63.936-63.952 kB |
| Fallimenti di allocazione CMA | 0 | 0 | 0 |

La ripetizione a CMA basso con vanilla è iniziata con `CmaFree=87,424 kB`, era a 79.520 kB subito dopo il rilascio completo, per poi tornare a 87.344 kB (differenza netta di 80 kB). Non si osserva un comportamento in cui si perde di più ripetendo caricamento/generazione/rilascio. Il fatto che `nr_foll_pin_*` di vanilla sia 0 è dovuto al non uso dell'API `FOLL_PIN`, e quindi non può essere usato per confrontare il successo/fallimento del rilascio del pin.

### 8.4 Interpretazione del calo iniziale

Dal riavvio con vanilla fino alla fine di tutte le riprove, `Cached` è aumentato da 1.845.872 kB a circa 4.988.224 kB, mentre `MemAvailable` si è mantenuto da 7.071.280 kB a circa 6.962.816 kB. L'entità dell'aumento è coerente con il caricamento di HEF di più GB, e il calo iniziale di `CmaFree` si può spiegare non come perdita di memoria inaccessibile, ma come utilizzo nella cache delle pagine di pagine libere, incluse pagine CMA movable.

### 8.5 Conclusione operativa

1. Non si deve rifiutare il caricamento del modello basandosi solo sul valore assoluto di `CmaFree`. Sul dispositivo reale il caricamento di Qwen è riuscito anche partendo da meno di 1 MB.
2. Registrare `CmaFree` basso come telemetria, e usare come criterio di fallimento l'effettivo errore di allocazione di memoria di HailoRT.
3. Non confondere il valore osservato di `CmaFree`, il fallimento effettivo di caricamento e la diagnosi di perdita; trattarli secondo i tre stati seguenti.

| Stato | Condizione di giudizio | Trattamento a livello di prodotto | Riavvio/indagine |
|---|---|---|---|
| `INCONCLUSIVE` | Solo il calo iniziale, meno di 3 volte, oppure non soddisfa le condizioni `FAIL` riportate sotto | Registrare la telemetria e tentare il caricamento. Non rifiutare solo per `CmaFree` basso | Non riavviare. Aggiungere misurazioni nelle stesse condizioni |
| `OPERATIONAL_FAIL` | HailoRT ha restituito un effettivo host-memory allocation error | Considerare fallita solo quella richiesta di caricamento, arrestare i workload Hailo non necessari e riprovare | Non riavviare per un singolo caso. Seguire la policy operativa solo se il fallimento effettivo si ripete e non si risolve nemmeno dopo il rilascio del workload. La Fase 0.5 attuale registra solo `would_fire` senza riavvio automatico |
| `FAIL` | Ripetendo 3 volte le stesse condizioni partendo da uno stato di CMA basso, la diminuzione netta rispetto al baseline dopo il rilascio è **superiore a 10 MB in almeno 2 tentativi su 3**, la somma delle 3 diminuzioni nette positive è **superiore a 20 MB**, ed è accompagnata da un aumento monotono di RSS o da un calo di `MemAvailable` superiore a 128 MB | Registrare come diagnosi di perdita separata dalla possibilità di caricamento del singolo caso | Riprendere l'indagine lato kernel/HailoRT e raccogliere prove dirette. Non riavviare automaticamente solo perché la diagnosi è stata stabilita |

Questo criterio delle 3 ripetizioni è destinato alle diagnosi future e non è applicato retroattivamente a §8.2 di questa sezione, dove i tentativi in processi indipendenti erano solo 2 per ciascun driver. La conclusione del quarto tentativo integra, oltre all'A/B di §8.2, anche le 20 generazioni nello stesso processo, il rilascio e il ricaricamento, e la ripetizione a CMA basso di §8.3.
4. La sostituzione con `FOLL_LONGTERM` è valida come prassi generale della DMA API di Linux, ma non ha avuto effetto su questo caso; il dispositivo reale è stato riportato alla vanilla ufficiale 5.4.0.
5. Il giudizio di riavvio automatico non deve scattare solo per `CmaFree` basso; l'osservazione di un fallimento effettivo di caricamento è condizione necessaria.

---

## 9. Azioni future (al 2026-08-17)

1. Lo studio della correzione `FOLL_LONGTERM` e la sua confutazione sul dispositivo reale sono completati. Il diff per la riproduzione e il metodo di ripristino sono conservati nell'Appendice B e non vengono applicati al driver di produzione.
2. **Il lato prodotto è già stato adeguato**: `core/hailo_device_core/device_manager_genai.py::acquire_genai` è stato modificato in v4.620.8 in modo da registrare `acquire_low_cma_observed` e proseguire con il caricamento effettivo anche quando `CmaFree` è inferiore alla quantità stimata necessaria. Nel tracker dei rifiuti viene registrato solo l'effettivo host-memory error di HailoRT restituito dalla factory, e `tests/test_hailo_cma_false_positive.py` fissa il comportamento di prosecuzione del caricamento da valori bassi.
3. È stata riesaminata, tramite i log e la vecchia implementazione, la descrizione della vecchia bozza del forum secondo cui "il successivo `LLM(...)` è stato rifiutato da HailoRT per insufficient host CMA". Nella sessione PID 3237 citata come fonte non c'è alcuna registrazione di acquire dopo il release, e tutti i rifiuti per CMA basso rintracciabili nei log dello stesso giorno erano l'evento proprietario `acquire_rejected_low_cma`, precedente alla chiamata a HailoRT. In un'altra sessione, il fallimento che ha raggiunto la factory era status 8 (`HAILO_INTERNAL_FAILURE`), non lo status 3 dell'host-memory error. Non esiste quindi alcuna prova di OOM di HailoRT a sostegno della vecchia descrizione, e in `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md` si ritira esplicitamente, dichiarando che un rifiuto proveniente dalla guardia proprietaria si era mescolato nel report.
4. Il post di correzione integra in un'unica bozza corrente i valori numerici e l'ambito di applicazione di §8, la correzione della guardia implementata, la confutazione di `FOLL_LONGTERM` e gli avvertimenti relativi alla strumentazione, senza lasciare la vecchia bozza in inglese in forma copiabile.
5. Si riprenderà l'indagine sulla perdita lato kernel/HailoRT solo se si riproduce un fallimento effettivo di caricamento o una perdita cumulativa di memoria disponibile a ogni ripetizione. In tal caso si raccoglieranno prove dirette come `page_owner`, informazioni di debug della CMA, status dei fallimenti di allocazione, RSS e `MemAvailable`.

---

## Appendice A. Procedura di ripristino a v5.3.0

Dopo un `remove --all` da dkms, il ripristino tramite `apt-get install --reinstall` fallisce se non rimane il `.deb` nella cache apt (è fallito anche in questo caso: impossibile reinstallare perché non è possibile scaricarlo). Poiché dpkg riconosce il pacchetto `hailort-pcie-driver` ancora come `ii` (installato), se la directory di estrazione del sorgente del pacchetto `/usr/src/hailort-pcie-driver/` non è stata cancellata, si può ricostruire manualmente l'albero dkms a partire da lì:

```bash
sudo rmmod hailo1x_pci

sudo rm -rf /usr/src/hailo1x_pci-5.3.0
sudo cp -r /usr/src/hailort-pcie-driver /usr/src/hailo1x_pci-5.3.0
sudo sed 's/@PCIE_DRIVER_VERSION@/5.3.0/' \
  /usr/src/hailo1x_pci-5.3.0/linux/pcie/dkms.conf.in \
  | sudo tee /usr/src/hailo1x_pci-5.3.0/linux/pcie/dkms.conf > /dev/null

# dkms.conf deve stare nella radice dell'albero (sotto linux/pcie/ genera un errore)
sudo cp /usr/src/hailo1x_pci-5.3.0/linux/pcie/dkms.conf /usr/src/hailo1x_pci-5.3.0/dkms.conf

sudo dkms add -m hailo1x_pci -v 5.3.0
sudo dkms build -m hailo1x_pci -v 5.3.0 -k $(uname -r)
sudo dkms install -m hailo1x_pci -v 5.3.0 -k $(uname -r) --force
sudo depmod -a
sudo modprobe hailo1x_pci
sudo udevadm trigger --subsystem-match=hailo1x
```

Verifica del ripristino:

```bash
cat /sys/module/hailo1x_pci/version   # → 5.3.0
hailortcli fw-control identify        # → se risponde normalmente, il ripristino è completo
```

---

## Appendice B. Procedura di conservazione, applicazione e ripristino alla vanilla della patch del driver usata per l'esperimento di confutazione

### B.1 Materiale conservato e sua collocazione

Il diff del driver effettivamente usato per l'A/B è stato conservato così com'è nel seguente file.

- `docs/development/patches/hailo1x_pci-5.4.0-foll-longterm-cma-debug-experiment.patch`
- SHA-256: `7b5c4027f37432dbbbe39e4bdec2f0f5e8dd87e133473b5a44c44b1e86c5503f`
- Sorgente di riferimento: `hailo-ai/hailort-drivers` tag `v5.4.0`, commit `b6dd17c609504e648eb516ff4a867167edf56f3c`
- File interessati: `linux/vdma/ioctl.c`, `linux/vdma/memory.c`, `linux/vdma/vdma.c`

Questa patch non include solo la sostituzione con `pin_user_pages(FOLL_LONGTERM)` / `unpin_user_page()`, ma anche la strumentazione `CMA_DBG` usata in §7.1. Si tratta cioè di un **diff completo per la verifica**, per riprodurre il modulo sperimentale usato nell'A/B, e non di una patch consigliata per la produzione. Non si è riscontrato alcun effetto nell'esperimento, e il dispositivo reale attuale è già stato ripristinato alla vanilla ufficiale 5.4.0. Non sono state apportate modifiche alla library userspace di HailoRT.

I valori identificativi confermati nello stesso ambiente di kernel, sorgente e build sono i seguenti.

| Stato | `srcversion` |
|---|---|
| patch sperimentale | `C84A00ABB326748A1832CE1` |
| vanilla ufficiale 5.4.0 | `A260C39C9F2C06DD4FB072E` |

### B.2 Verifica prima dell'applicazione

Quanto segue va eseguito solo se `/usr/src/hailo1x_pci-5.4.0` sul Raspberry Pi punta al commit ufficiale sopra indicato e non ci sono modifiche locali ai 3 file interessati. Se anche uno solo tra commit, checksum della patch e checksum di `memory.c` vanilla non corrisponde, bisogna fermarsi e non forzare l'applicazione della patch.

```bash
set -euo pipefail

REPO=/home/pi/GitHub/yu_ai_manager
SRC=/usr/src/hailo1x_pci-5.4.0
PATCH="$REPO/docs/development/patches/hailo1x_pci-5.4.0-foll-longterm-cma-debug-experiment.patch"
EXPECTED_HEAD=b6dd17c609504e648eb516ff4a867167edf56f3c
EXPECTED_PATCH_SHA=7b5c4027f37432dbbbe39e4bdec2f0f5e8dd87e133473b5a44c44b1e86c5503f
EXPECTED_MEMORY_SHA=85d564acaa70cdb41eb18bad35ad958d3b2af168ae03c17466976cbe64b1e58c

test "$(sudo git -c safe.directory="$SRC" -C "$SRC" rev-parse HEAD)" = "$EXPECTED_HEAD"
printf '%s  %s\n' "$EXPECTED_PATCH_SHA" "$PATCH" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_MEMORY_SHA" "$SRC/linux/vdma/memory.c" | sha256sum -c -
sudo git -c safe.directory="$SRC" -C "$SRC" diff --exit-code -- \
  linux/vdma/ioctl.c linux/vdma/memory.c linux/vdma/vdma.c
sudo git -c safe.directory="$SRC" -C "$SRC" apply --check "$PATCH"
```

### B.3 Applicazione della patch sperimentale

Solo se tutte le verifiche hanno avuto successo, si applica la patch e si installa il modulo DKMS per il prossimo avvio. Non sostituire manualmente il modulo in caricamento con `rmmod` / `modprobe`; effettuare il passaggio con un normale riavvio dopo la build.

```bash
set -euo pipefail

SRC=/usr/src/hailo1x_pci-5.4.0
PATCH=/home/pi/GitHub/yu_ai_manager/docs/development/patches/hailo1x_pci-5.4.0-foll-longterm-cma-debug-experiment.patch
KERNEL_VERSION="$(uname -r)"

sudo git -c safe.directory="$SRC" -C "$SRC" apply "$PATCH"
sudo dkms build -m hailo1x_pci -v 5.4.0 -k "$KERNEL_VERSION" --force
sudo dkms install -m hailo1x_pci -v 5.4.0 -k "$KERNEL_VERSION" --force
sudo depmod -a "$KERNEL_VERSION"

modinfo -n hailo1x_pci
modinfo -F srcversion hailo1x_pci
head -n 1 /sys/module/hailo1x_pci/srcversion
```

`modinfo` indica il modulo installato per il prossimo avvio, mentre `/sys/module/.../srcversion` indica il modulo attualmente caricato. A questo punto è normale che i valori siano diversi. Una volta pronti, si riavvia e si verifica che, dopo l'avvio, i due valori coincidano.

```bash
sudo reboot

# Dopo la riconnessione
modinfo -F srcversion hailo1x_pci
head -n 1 /sys/module/hailo1x_pci/srcversion
```

Nello stesso ambiente di verifica, il valore atteso dopo l'applicazione della patch è `C84A00ABB326748A1832CE1`. Se differisce, non continuare i test per congetture, ma verificare il diff del sorgente, il kernel e i log di build DKMS.

### B.4 Ripristino alla vanilla ufficiale 5.4.0

Il ripristino non si basa sull'applicazione inversa della patch, ma ripristina esplicitamente i 3 file interessati a partire dal commit verificato. In questo modo si evita uno stato in cui rimangono un'applicazione parziale o solo la strumentazione.

```bash
set -euo pipefail

SRC=/usr/src/hailo1x_pci-5.4.0
EXPECTED_HEAD=b6dd17c609504e648eb516ff4a867167edf56f3c
EXPECTED_MEMORY_SHA=85d564acaa70cdb41eb18bad35ad958d3b2af168ae03c17466976cbe64b1e58c
KERNEL_VERSION="$(uname -r)"

test "$(sudo git -c safe.directory="$SRC" -C "$SRC" rev-parse HEAD)" = "$EXPECTED_HEAD"
sudo git -c safe.directory="$SRC" -C "$SRC" restore --source="$EXPECTED_HEAD" -- \
  linux/vdma/ioctl.c linux/vdma/memory.c linux/vdma/vdma.c
sudo git -c safe.directory="$SRC" -C "$SRC" diff --exit-code -- \
  linux/vdma/ioctl.c linux/vdma/memory.c linux/vdma/vdma.c
printf '%s  %s\n' "$EXPECTED_MEMORY_SHA" "$SRC/linux/vdma/memory.c" | sha256sum -c -

sudo dkms build -m hailo1x_pci -v 5.4.0 -k "$KERNEL_VERSION" --force
sudo dkms install -m hailo1x_pci -v 5.4.0 -k "$KERNEL_VERSION" --force
sudo depmod -a "$KERNEL_VERSION"

modinfo -F srcversion hailo1x_pci
head -n 1 /sys/module/hailo1x_pci/srcversion
```

Nello stesso ambiente di verifica, il valore atteso per il modulo vanilla installato è `A260C39C9F2C06DD4FB072E`. Dopo aver confermato che il valore attualmente caricato è diverso, si riavvia e, dopo la riconnessione, si verifica che entrambi diventino `A260C39C9F2C06DD4FB072E`.

---

## Riferimento: documenti correlati

- `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md` — Dati di misurazione reali della perdita CMA basati sulla vecchia misurazione, script di riproduzione, bozza del post per il forum (la conclusione è stata corretta in questo documento, §8)
- [HAILORT_5_3_0_MIGRATION.md](HAILORT_5_3_0_MIGRATION.md) — Registro della migrazione v5.2.0 → v5.3.0 (cambio del nome del nodo dispositivo in `/dev/h1x-0`, ecc.)
- [HAILO_CMA_LEAK_HAILORT_5_3_0.md](HAILO_CMA_LEAK_HAILORT_5_3_0.md) — Registro del problema di perdita CMA basato sulla vecchia diagnosi (la conclusione è stata corretta in questo documento, §8)
- Repository GitHub `hailo-ai/hailort-drivers` (GPL-2.0, sorgente pubblico): <https://github.com/hailo-ai/hailort-drivers>
