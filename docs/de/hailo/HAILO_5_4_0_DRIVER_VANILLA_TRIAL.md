# Korrektur und Verifikationsprotokoll der Beurteilung „CMA nicht freigegeben" bei HailoRT / driver 5.4.0

Erstellt: 2026-08-16 / Letzte Aktualisierung: 2026-08-17 / Entsprechende Version: yu_ai_manager 4.623.1

Zum Sachverhalt, der als CMA-Nichtfreigabe beurteilt wurde (siehe `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md`), wurde mit `hailo-ai/hailort-drivers` v5.4.0 (veröffentlicht am 2026-08-16, GPL-2.0, Quellcode offen) eine Hypothesenprüfung sowie ein A/B-Test zwischen dem offiziellen vanilla und der `FOLL_LONGTERM`-Fix-Version durchgeführt. Dies ist das Protokoll, in dem die Fehlbeurteilung auf Messseite korrigiert wurde.

---

## 1. Schlussfolgerung

**Abschließender Nachtest vom 2026-08-17 (4. Durchgang): Das `VERDICT: FAIL` bis zum 3. Durchgang war eine Fehlbeurteilung, die allein auf dem absoluten `CmaFree`-Erholungsbetrag nach dem ersten HEF-Laden als Leck-Kriterium beruhte. Im A/B-Vergleich zwischen dem offiziellen vanilla 5.4.0 und der `FOLL_LONGTERM`-Fix-Version waren fortlaufendes Laden ausgehend von niedrigem `CmaFree`, Freigabe und erneutes Laden innerhalb desselben Prozesses, 20 Generierungen sowie sämtliche Testwiederholungen ausgehend von einem noch niedrigeren `CmaFree`-Zustand allesamt erfolgreich. Bei RSS und `CmaFree` während der Generierung gab es keinen monotonen Anstieg oder Abfall, und CMA-Zuweisungsfehler traten 0-mal auf. Der anfängliche `CmaFree`-Rückgang entsprach dem Anstieg des Seiten-Caches durch die Multi-GB-HEF, und `MemAvailable` blieb bei ca. 7 GB stabil. Unter den diesmal getesteten Bedingungen — Pi 5 + Hailo-10H + HailoRT/driver 5.4.0, einzelnes Modell, einzelnes Gerät, kurze Wiederholung — trat kein praktisch relevanter CMA-Leak erneut auf, und auch der `FOLL_LONGTERM`-Fix zeigte keine messbare Verbesserung. Langfristiger Dauerbetrieb, gleichzeitige Nutzung mehrerer Modelle, Hailo-8 sowie der Betrieb unter IOMMU wurden nicht getestet und liegen außerhalb des Geltungsbereichs dieser Schlussfolgerung.**

### 1.1 Verlauf der Beurteilung

| Durchgang | Datum | Beurteilung zu diesem Zeitpunkt | Grundlage der Aktualisierung/Korrektur |
|---|---|---|---|
| 1. Durchgang | 2026-08-16 | Beurteilung nicht möglich | Wurde nur der driver auf 5.4.0 gesetzt, wies die exakte Übereinstimmungsprüfung mit library 5.3.0 die API zurück (§3) |
| 2. Durchgang | 2026-08-17 | Nur eingeschränkter Test abgeschlossen | driver / library / firmware wurden auf 5.4.0 abgestimmt, die `run2`-Wiederholung erreichte ein Plateau, aber die direkte Reproduktion über pyhailort wurde noch nicht durchgeführt (§4) |
| 3. Durchgang | 2026-08-17 | Vorläufiges `FAIL` (später als Fehlbeurteilung erkannt) | Altes Diagnoseergebnis, das nur den absoluten `CmaFree`-Erholungsbetrag nach dem ersten HEF-Laden beurteilte. Eine Einzelmessung konnte Speicherverlust und Seiten-Cache-Nutzung nicht unterscheiden (§5, §7) |
| 4. Durchgang | 2026-08-17 | Kein praktisch relevanter Leak reproduzierbar | vanilla / `FOLL_LONGTERM` A/B, Wiederholung bei niedrigem CMA, erneutes Laden im selben Prozess, 20 Generierungen, Messung von RSS · `MemAvailable` · Zuweisungsfehlern korrigierte den 3. Durchgang (§8) |

---

## 2. Quellcode-Diff v5.3.0 → v5.4.0 (`hailo-ai/hailort-drivers`)

Alle Dateien zwischen beiden Tags wurden über die GitHub API verglichen (diff). Da es sich um einen einzelnen Squash-Commit handelt, ließ sich aus der Commit-Message nichts entnehmen; die Bestätigung erfolgte über den tatsächlichen Datei-Diff. An der **Logik selbst** der CMA-Reservierung/-Freigabe (dem Paar `dma_alloc_coherent`/`dma_free_coherent`) gab es keine Änderung; die folgenden Änderungen sind überwiegend Refactoring bzw. defensive Korrekturen:

| Datei | Änderungsinhalt |
|---|---|
| `linux/utils/compact.h` → `compat.h` | Umbenennung der Datei der Kernel-Kompatibilitätsschicht |
| `linux/vdma/memory.c` | NULL-Prüfung zu `hailo_desc_list_release()` hinzugefügt, Zeiger nach Freigabe auf NULL gesetzt (defensive Korrektur zur **Vermeidung von Doppel-Freigaben**) |
| `linux/vdma/vdma.h` | Redundantes Feld `kernel_address` aus `hailo_descriptors_list_buffer` entfernt (in `desc_list.descs` integriert) |
| `common/vdma_common.c` | DMA-Transfer-Abschlussprüfung von direkter `hw_num_proc`-Berechnung auf Vergleich von `num_proc`/`num_avail` umgestellt (möglicherweise Bugfix im Tracking des Transfer-Abschlusses) |
| `linux/vdma/monitor.c` | `del_timer_sync` → `timer_delete_sync` (Anpassung an neuen Kernel-API-Namen) |
| `common/pcie_common.c` | md5-Feld aus dem FW-Steuerungsprotokoll entfernt, SCU-Log-Korruptionsprüfung von nur den ersten 4 Bytes auf vollständige Prüfung der ersten 5 Wörter verschärft |

Auch der Fehlermeldungstext wurde geändert (langer Beschreibungstext → verkürzt zu `out of CMA memory.`), aber der Kontrollfluss von Reservierung/Freigabe ist identisch. **Aus diesem Diff allein lässt sich keine Änderung erkennen, die der damaligen Hypothese (CMA-Nichtfreigabe beim Modell-Neuladen) entspricht.**

---

## 3. Praktischer Austauschversuch und Stolperstellen (2026-08-16, 1. Versuch)

Auf einem Raspberry Pi 5 + Hailo-10H, mit laufendem `hailo1x_pci 5.3.0` (per dkms verwaltet), wurde versucht, per manuellem Build auf v5.4.0 zu wechseln.

### 3.1 `make install` hängt nicht von `all` ab

Das `install`-Target in `linux/pcie/Makefile` besteht nur aus `modules_install`, und es wird ohne Warnung abgeschlossen, selbst wenn das Build-Artefakt (`.ko`) nicht existiert (genauer: Es erscheint zwar eine Warnung über das Fehlen von `System.map`, aber daraus wird nicht klar, dass die Ursache ein fehlender Build ist).

```makefile
install:
	$(Q)$(MAKE) -C $(KERNEL_DIR) M=$(PWD) INSTALL_MOD_DIR=kernel/drivers/misc modules_install
	$(Q)$(DEPMOD) -a

all: $(TARGET_DIR) print-versions
	$(Q)$(MAKE)  -C $(KERNEL_DIR) M=$(PWD) $(GDB_FLAG) $(USER_FLAGS) modules
	$(Q)cp $(DRIVER_NAME_NO_EXT)* $(TARGET_DIR)
```

**Unbedingt in der Reihenfolge `make all && sudo make install` ausführen.**

### 3.2 Die Kernel-Header von Raspberry Pi enthalten kein `System.map`

Bei der Ausführung von `modules_install` erscheint folgende Warnung, und `depmod` wird stillschweigend übersprungen:

```
Warning: modules_install: missing 'System.map' file. Skipping depmod.
```

Grund: `/usr/src/linux-headers-<kernelver>/System.map` existiert nicht. `/boot/System.map-<kernelver>` existiert jedoch, daher lässt sich das Problem durch Kopieren lösen:

```bash
sudo cp /boot/System.map-$(uname -r) /usr/src/linux-headers-$(uname -r)/System.map
sudo depmod -a
```

Unterlässt man dies, kann `modprobe` die neu installierte `.ko` nicht auflösen, und es kommt zu `FATAL: Module hailo1x_pci not found` (obwohl die `.ko`-Datei selbst durchaus unter `/lib/modules/<kernelver>/kernel/drivers/misc/` existiert).

### 3.3 udev-Regeln greifen ohne reload/trigger nicht sofort

`/lib/udev/rules.d/51-hailo-pcie-udev.rules`:

```
SUBSYSTEM=="hailo1x", MODE="0666"
```

Unmittelbar nach dem Modulaustausch ist `/dev/h1x-0` `crw-------` (nur root). Lösung:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hailo1x
```

### 3.4 Eine Versions-Abweichung zwischen Treiber und Library ist fatal

Führt man `hailortcli` mit nur auf 5.4.0 angehobenem Kernel-Treiber aus:

```
dmesg: Mismatch Driver version pcie driver 5:4:0 pci_ep driver 5:3:0
dmesg: hailo_soc_get_driver_info has failed with err -22

hailortcli: [HailoRT] [error] CHECK failed - Driver version (5.4.0) is different from library version (5.3.0)
hailortcli: [HailoRT] [error] Driver version mismatch, status HAILO_INVALID_DRIVER_VERSION(76)
```

Die HailoRT-Library verlangt eine **exakte Übereinstimmung** mit dem Kernel-Treiber; wird nur eine Seite vorab aktualisiert, werden sämtliche API-Aufrufe sofort zurückgewiesen. Eine reine vanilla-Verifikation des Treibers allein ist nicht möglich; auch das Userspace-Paket `hailort` (das SDK selbst) muss gleichzeitig aktualisiert werden.

- `apt-cache policy hailort` → Kandidat 5.3.0 (Stand heute, 5.4.0 noch nicht im offiziellen apt verteilt)
- `gh api repos/hailo-ai/hailort/releases` → Tag `v5.4.0` existiert, aber `assets` ist leer (keine gebauten deb-Pakete, nur Quellcode)

Das heißt: **Ohne `hailort` selbst als deb zu installieren oder komplett aus dem Quellcode zu bauen, ist keine praktische Verifikation von 5.4.0 möglich.** Ein Vollständig-Build wäre ein größerer Build mit C++ CMake + Python-Bindings und würde das Risiko bergen, abhängige Pakete wie `hailo-tappas` und `python3-hailort` mit hineinzuziehen; daher wurde dies im 1. Durchgang vorerst zurückgestellt und die Entscheidung getroffen, auf die offizielle deb-Verteilung zu warten.

---

## 4. Protokoll des Eigenbau-Verfahrens (2026-08-17, 2. Versuch)

Ohne auf die Verteilung des offiziellen deb-Pakets über apt zu warten, wurde aus dem GitHub-Quellcode (driver: GPL-2.0, `hailort` selbst: MIT) in Eigenregie gebaut und ins System eingespielt; hier das Verfahren und die dabei aufgetretenen Stolperstellen.

### 4.1 Build-Umgebung

- `checkinstall` installiert (`sudo apt-get install -y checkinstall`). Allerdings kollidierte der `xz`-Kompressionsschritt des Kernelmoduls mit `installwatch` (dem LD_PRELOAD-basierten Datei-Tracking-Mechanismus von checkinstall), sodass die Ausführung von `make install` über checkinstall jedes Mal mit `xz: ... Datei oder Verzeichnis nicht gefunden` fehlschlug. **Für die Paketierung von Kernelmodulen kein checkinstall verwenden, sondern dkms (für den driver selbst) bzw. das reine `make install` (für die Userspace-Library)**
- Vor dem Build Speicher freigegeben: doppelt laufende `headroom mcp serve`-Prozesse und `rust-analyzer` temporär gestoppt (insgesamt knapp 1 GB freigegeben). Der Pi-Speicher betrug 7,9 Gi, während des Builds konnte ein verfügbarer Wert von ca. 3,8 Gi gehalten werden

### 4.2 Build von `hailort` (Userspace-Library)

```bash
git clone --branch v5.4.0 --depth 1 https://github.com/hailo-ai/hailort.git
cd hailort/build   # ディレクトリを作成してから
cmake .. -DCMAKE_BUILD_TYPE=Release   # 外部依存(protobuf/spdlog/eigen等)を FetchContent で自動取得、約4分
cmake --build . -j2   # -j2 に制限(メモリ逼迫回避)、約15分
sudo make install     # /usr/local/{include,lib,bin} に配置。apt 版(5.3.0, /usr 配下)と共存可能
```

Da bei allen `option()`-Standardwerten schwergewichtige Komponenten (GStreamer, Tests, Server, Ollama-Anbindung usw.) auf OFF stehen, wurden nur `libhailort.so`, `hailortcli` und `libhailopp` gebaut — eine vergleichsweise schlanke Konfiguration.

**Hinweis**: Das Ergebnis von `make install` landet unter `/usr/local` und überschreibt nicht die apt-Version (unter `/usr`, 5.3.0). Bei der Funktionsprüfung muss der Pfad explizit angegeben werden, z. B. `LD_LIBRARY_PATH=/usr/local/lib /usr/local/bin/hailortcli ...`.

### 4.3 Austausch des driver (Kernelmodul) und Firmware-Update

Der driver selbst wurde per dkms gebaut und installiert (nach demselben Verfahren wie im Wiederherstellungsschritt in Anhang A, ersetzt durch `-v 5.4.0`), und per `rmmod`/`modprobe` neu geladen. An diesem Punkt zeigte `hailortcli` `HAILO_DRIVER_OPERATION_FAILED(36)` bzw. dmesg `Mismatch Driver version pcie driver 5:4:0 pci_ep driver 5:3:0`, woraufhin sich herausstellte, dass **auch die Firmware auf dem Gerät (SoC-seitig, pci_ep) separat auf 5.4.0 angehoben werden muss**.

```bash
# 公式 S3 から firmware を取得（driver リポジトリ同梱のスクリプトを使用）
bash hailort-drivers/download_firmware_hailo10h.sh
# 既存 firmware をバックアップしてから新版に差し替え
sudo cp -r /lib/firmware/hailo/hailo10h /lib/firmware/hailo/hailo10h.backup-5.3.0
sudo cp <展開先>/hailo10h_fw_5.4.0/* /lib/firmware/hailo/hailo10h/
sudo chown -R root:root /lib/firmware/hailo/hailo10h/
```

Hier wurde versucht, das Modul neu zu laden (`rmmod`/`modprobe`, inklusive `support_soft_reset=1`), aber dmesg meldete durchgehend `SOC Firmware batch was already loaded`. Eine Prüfung des Treiber-Quellcodes ergab, dass `load_soc_firmware()` (der Ladeweg für die SoC-Firmware des Hailo-10H) keine Soft-Reset-Verarbeitung über `support_soft_reset` implementiert (diese existiert nur in `load_nnc_firmware()` für Hailo-8), und dass dieser Schritt bedingungslos übersprungen wird, solange `hailo_pcie_is_firmware_loaded()` true zurückgibt. Das heißt: **Der Firmware-Zustand auf dem SoC lässt sich durch Modul-Neuladen nicht ändern, ein tatsächliches Aus- und Wiedereinschalten des Geräts ist zwingend erforderlich.**

Nach dem Neustart protokollierte dmesg das Schreiben des Firmware-Batches (in der Reihenfolge `customer_certificate.bin` · `scu_fw.bin` · `u-boot-*.dtb.signed` · `u-boot-spl.bin` · `fitImage` · `image-fs`, 4064 ms) → `SOC Firmware Batch loaded successfully`, und `hailortcli fw-control identify` antwortete korrekt mit `Firmware Version: 5.4.0 (release,app)`.

### 4.4 Einfache CMA-Verhaltensprüfung und ihre Grenzen

Mit `hailortcli run2` (resnet_v1_18.hef, ein im Paket `hailo_tutorials` enthaltenes kleines Modell) wurde ein einzelner load/run/exit-Durchlauf sowie der `CmaFree`-Verlauf (`/proc/meminfo`) bei 8 aufeinanderfolgenden Ausführungen beobachtet:

| Ausführung | CmaFree (kB) |
|---|---|
| baseline (unmittelbar nach Neustart) | 170464 |
| iter 1 | 134864 |
| iter 2 | 134144 |
| iter 3〜8 | 133744 (unverändert, Plateau) |

Innerhalb weniger Durchläufe wurde ein Plateau erreicht, bis zum 8. Durchlauf wurde kein zusätzlicher Leak beobachtet. Dies ist jedoch ein einfacher load/run/exit über die CLI (jeweils ein separater Prozess-Start), und unterscheidet sich von beiden bekannten Lecks, die in `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md` berichtet werden — (a) die Nichtfreigabe bei `VDevice.release()`/Modell-Neuladen **innerhalb desselben Prozesses** und (b) der fortlaufende Leak während der Ausführung von `generate_stream()` (LLM-Inferenz). Dieses Ergebnis ist daher kein Beleg dafür, dass das Problem „gelöst" wäre.

Die eigentliche Reproduktion (`tools/diag_hailo_cma_reclaim.py` sowie das im forum-followup-doc beschriebene Skript) lädt das GenAI-LLM über das Python-Binding `hailo_platform` (pyhailort) und ließ sich daher in der 5.4.0-Umgebung nicht ohne Weiteres ausführen:

```
$ .venv 内の hailo_platform は libhailort.so.5.3.0 に固定リンク（ldd で確認）
$ VDevice() 構築時に driver(5.4.0)/library(5.3.0) のバージョン不一致で同じ HAILO_INVALID_DRIVER_VERSION に該当する見込み
```

Zu diesem Zeitpunkt war der Neubau von pyhailort (Python-Binding) aus dem 5.4.0-Quellcode und der Austausch in `.venv` noch nicht in Angriff genommen, wurde jedoch im 3. Versuch (§5) durchgeführt.

---

## 5. Neubau von pyhailort und erneute Ausführung der Reproduktion (2026-08-17, 3. Versuch)

Dieser Abschnitt dokumentiert die vorläufige Beurteilung zum Zeitpunkt des 3. Versuchs. Beurteilungsmethode und Schlussfolgerung wurden im A/B-Test des 4. Durchgangs (§8) korrigiert.

### 5.1 Build von pyhailort (Python-Binding)

`hailort/libhailort/bindings/python/platform/` im `hailort`-Hauptrepository ist die pip-Paketquelle von pyhailort (`pyproject.toml`, basierend auf scikit-build-core + pybind11). Der Build erfolgte mit explizitem Linking gegen das in §4.2 bereits unter `/usr/local` installierte libhailort 5.4.0:

```bash
cd hailort/libhailort/bindings/python/platform
CMAKE_ARGS="-DLIBHAILORT_PATH=/usr/local/lib/libhailort.so.5.4.0 -DHAILORT_INCLUDE_DIR=/usr/local/include" \
  <venv>/bin/python -m pip install .
```

Innerhalb der Build-Isolation wurden `scikit-build-core`/`pybind11` automatisch von PyPI bezogen und gebaut, das `hailort`-Paket in `.venv` wurde von 5.3.0 auf das 5.4.0-Wheel ersetzt. Per `ldd` wurde bestätigt, dass `_pyhailort*.so` gegen `/usr/local/lib/libhailort.so.5.4.0` gelinkt ist, und auch construct/release von `VDevice()` funktionierten für sich genommen einwandfrei.

### 5.2 Erneute Ausführung der bestehenden Reproduktion (`tools/diag_hailo_cma_reclaim.py`)

Mit demselben Reproduktionsskript, demselben Beurteilungskriterium und derselben HEF (`~/hailo_models/Qwen3-1.7B-Instruct.hef`) wie im Mai 2026, in derselben Umgebung mit auf 5.4.0 ersetztem `hailo_platform` in `.venv`, wurde erneut gemessen:

```bash
uv run python tools/diag_hailo_cma_reclaim.py --signal terminate
```

Ergebnis (`logs/hailo_cma_reclaim_poc.json`):

| Ereignis | CmaFree (MB) |
|---|---|
| baseline_before_spawn | 159 |
| after_vdevice_created / after_llm_loaded | 22（消費 137 MB） |
| child kill (`terminate`) 直後 | 23 |
| post_wait +5s | 26 |
| post_wait +10s | 28 |
| post_wait +15s | 29 |
| post_wait +20s〜+30s | **0** (von 29 MB nochmals um ca. 28,5 MB gesunken; auch nach Ablauf mehrerer Minuten blieb `CmaFree` bei rund 512 kB hängen) |

Dieser erneute Rückgang von 29 MB auf ca. 512 kB ließ sich nicht auf zeitgleiche Konkurrenz durch andere Prozesse zurückführen, aber allein aus dieser Messung lässt sich die Ursache nicht bestimmen; er bleibt als ungeklärte Beobachtung bestehen. Allein die Seiten-Cache-Nutzung nach dem ersten Laden (§8.4) kann diesen Zwischenverlauf nicht erklären, und da es für diesen Durchlauf keine Wiederholungsmessung gibt, bei der RSS, `MemAvailable` und Zuweisungsfehler gleichzeitig erfasst wurden, wird er nicht als Grundlage für die abschließende Beurteilung in §8 herangezogen.

Der Bereich um 512 kB liegt jedoch im selben Band wie die während des `FOLL_LONGTERM`-Tests in §8.3 beobachteten 464→1.648 kB, und von diesem Zustand aus gelangen 20 Generierungen, Freigabe und erneutes Laden erfolgreich zum Abschluss. Der Verlauf, der zu diesem niedrigen Wert führte, bleibt ungeklärt, aber es ist praktisch bestätigt, dass **dieses Band von `CmaFree` an sich keinen unmittelbar gefährlichen Zustand oder eine Ladeunfähigkeit bedeutet**.

Originaltext, den das alte Diagnosewerkzeug ausgab (vorläufige Beurteilung zum Zeitpunkt des 3. Durchgangs; die endgültige Beurteilung wurde in §8 korrigiert):

```
VERDICT: FAIL — only -22 MB recovered after kill+wait. spec hypothesis invalid → pivot to auto-reboot alternatives
```

In diesem Versuch wurde nur festgestellt, dass sich `CmaFree` nach dem ersten HEF-Laden nicht gemäß dem alten Beurteilungskriterium erholte. Weder der Verlust an verfügbarem Speicher nach Prozessende noch das Fortbestehen des Lecks in v5.4.0 wurde damit belegt. Im 3. Durchgang wurde dies vorläufig als Nichtfreigabe interpretiert, doch diese Interpretation und Beurteilungsmethode wurden in §8 korrigiert.

---

## 6. Kernel-Absturz während des 3. Versuchs und Wiederherstellung des CMA-Debug-Codes (2026-08-17)

### 6.1 Vorfall und mögliche Ursache

Um den Freigabepfad von CMA zu untersuchen, wurde in `linux/vdma/memory.c` der lokalen DKMS-Quelle ein `#include` von `linux/mm.h` sowie Messcode hinzugefügt, der unmittelbar vor `dma_free_coherent()` `virt_to_page()` / `page_count()` aufruft. Das Laden eines Moduls mit dieser Änderung führte bei Hailo-Nutzung zu einem Hänger und Bootunfähigkeit, weshalb aktuell über `module_blacklist=hailo1x_pci,hailo_pci` in `/boot/firmware/cmdline.txt` das automatische Laden gestoppt wird.

Die von `dma_alloc_coherent()` zurückgegebene virtuelle CPU-Adresse direkt per `virt_to_page()` in eine Page umzuwandeln, ist kein Vertrag der DMA-API. Da das Mapping-Format der zurückgegebenen Adresse dem Allocator überlassen bleibt, ist der daraus gewonnene `page_count()`-Wert kein korrektes Mittel zur Beobachtung des CMA-Referenzzählers und kann zu ungültigen Page-Referenzen führen. Der Messcode wird in beiden Freigabepfaden — descriptor list und continuous buffer — ausgeführt.

Der Hinzufügungszeitpunkt war 10:15:36, der Beginn des betreffenden DKMS-Builds 10:15:39, sodass davon auszugehen ist, dass das hängengebliebene Modul diesen Code enthielt. Da kein Stack-Trace unmittelbar vor dem Absturz vorliegt, ist die Ursache nicht streng belegt, aber es handelt sich um die einzige lokale Code-Änderung, die in der vanilla v5.4.0 nicht vorhanden ist, und gilt daher als wahrscheinlichste Ursache.

### 6.2 Wiederhergestellter Zustand

Die folgenden 7 Zeilen (das `#include` von `linux/mm.h`, zwei `virt_to_page()`/`page_count()`-Log-Stellen) wurden entfernt, DKMS wurde neu gebaut, und `depmod` wurde abgeschlossen.

- Kernel: `6.18.39+rpt-rpi-2712`
- Neu gebautes Modul: `/lib/modules/6.18.39+rpt-rpi-2712/updates/dkms/hailo1x_pci.ko.xz`
- In `modules.dep` ist das obige Modul registriert
- Der Blacklist-Eintrag bleibt bestehen, das neu gebaute Modul wurde noch nicht geladen

Vor dem nächsten Schritt soll zunächst ein Wiederherstellungsweg wie eine serielle Konsole sichergestellt werden, bevor die Blacklist entfernt und das erste Laden nach einem Neustart bestätigt wird. Bei der eigentlichen Untersuchung des CMA-Nichtfreigabe-Problems wird die Messung, die die von der DMA-API zurückgegebene Adresse in eine interne Page umwandelt, nicht wieder eingeführt; stattdessen werden das vom Treiber gehaltene Puffer-Register, die zugewiesenen Größen und die Anzahl der `dma_free_coherent()`-Aufrufe beobachtet.

**Nachtrag (2026-08-17, später)**: Nachdem eine `cmdline.txt`-Sicherung (`cmdline.txt.bak-blacklisted`) angelegt worden war, wurde die Blacklist entfernt, neu gestartet und der normale Start bestätigt (auch die serielle Konsole `console=serial0,115200` ist eingerichtet, sodass ein Wiederherstellungsweg sichergestellt ist). Ab hier wurde die Untersuchung mit der sicheren Instrumentierung aus §7 fortgesetzt (keine Roh-Page-Prüfung, nur Ausgabe bestehender Zähler/Größen als Log).

---

## 7. Bildung und Ausschluss von Ursachenhypothesen — Verifikation und Widerlegung von `FOLL_LONGTERM` (2026-08-17)

Dieser Abschnitt dokumentiert die Bildung von Ursachenhypothesen im Anschluss an den 3. Versuch sowie die Ursachenkandidaten, die durch Experimente ausgeschlossen werden konnten. Die Rolle hier ist die Eingrenzung der Kandidaten; die abschließende Beurteilung zum Vorliegen eines CMA-Lecks hängt vom A/B-Test des 4. Durchgangs (§8) ab.

Nach dem Absturz in §6 wurde die Untersuchung mit sicherer Instrumentierung fortgesetzt, die den direkten Zugriff auf Page-Interna wie `virt_to_page()` vermeidet (nur Log-Ausgabe per `dev_err()`, keine Prüfung/Umwandlung roher Zeiger).

### 7.1 Inhalt der Instrumentierung

An folgenden Stellen in `linux/vdma/memory.c` / `linux/vdma/ioctl.c` / `linux/vdma/vdma.c` wurden Logs hinzugefügt, die die vorhandenen atomaren Zähler (`controller->desc_cma_in_use` / `controller->cma_in_use`) und die Zuweisungsgröße ausgeben (kein Zugriff auf Page-Interna):

- `hailo_desc_list_create`/`hailo_desc_list_release` (alloc/free der descriptor list)
- `hailo_vdma_continuous_buffer_alloc`/`hailo_vdma_continuous_buffer_free` (alloc/free des continuous buffer)
- `hailo_desc_list_release_ioctl`/`hailo_vdma_continuous_buffer_free_ioctl` (expliziter Freigabepfad über ioctl)
- `hailo_vdma_buffer_map`/`hailo_vdma_buffer_destroy` (DMA-Mapping/-Unmapping-Pfad für Userspace-Puffer; auch `buffer_type`/`is_mmio`/`is_dmabuf` werden ausgegeben)
- `hailo_vdma_file_context_finalize` (gesammelte Bereinigung bei fops_release, Zähler-Ausgabe bei ENTER/EXIT)

### 7.2 Beobachtungsergebnis

Unmittelbar nach dem Neustart (`CmaFree` ≈ 451 MB) wurde `tools/diag_hailo_cma_reclaim.py --signal terminate` ausgeführt und alle Logs per `sudo dmesg | grep CMA_DBG` gesammelt und ausgewertet.

- **`CmaFree` in `/proc/meminfo`**: 451 MB → 195 MB (**256 MB verbraucht**) → auch 30 Sekunden nach kill+Wartezeit noch 204 MB (**247 MB niedriger als baseline**)
- **`desc_cma_in_use` des Treibers selbst (descriptor list, über `dma_alloc_coherent`)**: höchstens 2–4 MB. Zum EXIT-Zeitpunkt von `file_context_finalize` sicher wieder auf 0 zurückgesetzt
- **`cma_in_use` (continuous buffer, über `dma_alloc_coherent`)**: während dieser Sitzung durchgehend 0 (continuous buffer wurde kein einziges Mal verwendet)
- **DMA-Mapping von Userspace-Puffern (`hailo_vdma_buffer_map`, `buffer_type=0`=`HAILO_DMA_USER_PTR_BUFFER`, `is_mmio=0`, `is_dmabuf=0`)**: 621 Aufrufe, davon **342 mit Größe 8 MB (`0x800000`)** (insgesamt Mapping-Aufrufe im Umfang von 2,7 GB; vermutlich wird derselbe hostseitige Staging-Puffer in der Pipeline-Verarbeitung wiederverwendet). `hailo_vdma_buffer_destroy` wurde 628-mal aufgerufen und entspricht nahezu 1:1 `buffer_map`; **als Mapping-Register des Treibers selbst ist keine Inkonsistenz erkennbar** (`dma_unmap_sg` wird korrekt aufgerufen)
- **SWIOTLB (`/sys/kernel/debug/swiotlb/`)**: `io_tlb_used_hiwater=0`. Der Bounce-Buffer wurde kein einziges Mal genutzt
- Das Hailo-Gerät liegt nicht unter IOMMU (`/sys/bus/pci/devices/0001:01:00.0/iommu_group` nicht vorhanden)

Zu diesem Zeitpunkt wurde nicht die treibereigene Zuweisung über `dma_alloc_coherent()` (desc list, continuous buffer), sondern der von `hailo_vdma_buffer_map()` behandelte Pfad — das „DMA-Mapping vorhandenen, vom Userspace reservierten Speichers" (`HAILO_DMA_USER_PTR_BUFFER`) — als Ursachenkandidat für den `CmaFree`-Rückgang interpretiert. Auf diesem Pfad reserviert der Treiber kein neues CMA, sondern fixiert (pinnt) vorhandene Userspace-Pages, um sie DMA-fähig zu machen.

### 7.3 Ursachenhypothese: `FOLL_LONGTERM` fehlt bei `get_user_pages()`

Eine Prüfung von `prepare_sg_table()` (aufgerufen innerhalb von `hailo_vdma_buffer_map()`) in `linux/vdma/memory.c` ergab:

```c
pinned_pages = compat_get_user_pages(user_address, npages, FOLL_WRITE | FOLL_FORCE, pages);
```

`compat_get_user_pages` ist (da dieser Kernel 6.18.39 unter `LINUX_VERSION_CODE >= KERNEL_VERSION(6, 5, 0)` fällt) schlicht ein Alias für `get_user_pages()`, und **das Flag `FOLL_LONGTERM` ist nicht gesetzt**. Auch die Freigabeseite (`clear_sg_table()`) ruft das entsprechende `put_page()` auf; es wird weiterhin das alte `get_user_pages()`/`put_page()` verwendet, nicht die neuere `pin_user_pages()`/`unpin_user_pages()`-API-Familie.

Gemäß der dokumentierten Praxis des Linux-Kernels (`Documentation/core-api/pin_user_pages.rst`) **sollte Code, der wie bei DMA-Transfers Page-Referenzen über längere Zeit hält, `pin_user_pages()` mit `FOLL_LONGTERM` verwenden**. Wird `FOLL_LONGTERM` nicht angegeben, wird die Eigenschaft von CMA, „bei Bedarf für andere Zwecke verschiebbar (migratable)" zu sein, über längere Zeit außer Kraft gesetzt, falls zufällig im CMA-Bereich liegende Userspace-Pages per `get_user_pages()` fixiert werden. Der CMA-Allocator migriert solche Pages normalerweise vor einer langfristigen Fixierung aus dem CMA-Bereich heraus, aber auf einem Pfad ohne `FOLL_LONGTERM` unterbleibt diese Migration, sodass **CMA für die Dauer der Fixierung effektiv verloren geht, und selbst nach der Freigabe (`put_page()`) nicht sofort als freier CMA-Bereich erkannt wird** (da zusätzlich Migration/Kompaktierung nötig ist).

Diese Hypothese war konsistent mit der Einzelmessung des 3. Durchgangs (§7.2):
- Die treibereigenen CMA-Zähler sind irrelevant (`get_user_pages` läuft nicht über `dma_alloc_coherent`)
- Die Aufrufanzahl von map/destroy ist korrekt ausgeglichen (`put_page()` selbst wird korrekt aufgerufen. Das Problem ist die langsame/unvollständige „Rückkehr" zu CMA nach der Freigabe)
- Beim Laden eines großen LLM wie Qwen3-1.7B-Instruct werden zahlreiche 8-MB-Puffer im Host-Speicher reserviert und DMA-gemappt; enthält ein Teil davon Pages innerhalb des CMA-Bereichs, tritt dieses Problem zutage
- Auch die langsame und teilweise Erholung von `CmaFree` nach kill (in 30 Sekunden nur +15–30 MB, danach über mehrere Minuten weiterer langsamer Anstieg) ist damit konsistent (`put_page()` selbst wird bei Prozessende sicher aufgerufen, aber die Rückgewinnung als freier CMA-Bereich scheint zusätzliche Verarbeitung zu benötigen)

### 7.4 Implementierung und praktische Verifikation des Fix-Kandidaten → Widerlegung (2026-08-17, Folgebericht)

`prepare_sg_table()` wurde tatsächlich von `get_user_pages(FOLL_WRITE | FOLL_FORCE)` + `put_page()` auf `pin_user_pages(FOLL_WRITE | FOLL_FORCE | FOLL_LONGTERM)` + `unpin_user_page()` umgestellt, das `#include` von `<linux/mm.h>` hinzugefügt, gebaut, per dkms neu registriert und bis zum praktischen Laden vollständig durchgeführt (bestätigt, dass die Symbole `pin_user_pages`/`unpin_user_page` per `modprobe --dump-modversions` korrekt aufgelöst werden).

Ergebnis derselben Reproduktion, ausgehend vom hohen `CmaFree`-Zustand (453 MB) unmittelbar nach Neustart:

| | vor dem Fix (n=mehrere Durchläufe) | nach dem Fix (n=1) |
|---|---|---|
| baseline | 436–451 MB | 453 MB |
| after_llm_loaded | 173–195 MB (256–263 MB verbraucht) | 180 MB (273 MB verbraucht) |
| after_post_wait | 188–204 MB (9–15 MB zurückgewonnen) | 190 MB (**10 MB zurückgewonnen**) |
| `VERDICT` nach altem Beurteilungskriterium | `FAIL` | **`FAIL` (keine Änderung)** |

> Diese Tabelle ist bei Durchlaufanzahl und Aggregationsmethode nicht symmetrisch und ist kein strenger A/B-Vergleich. Die A/B-Beurteilung erfolgt anhand des Ergebnisses aus §8, das unter identischen Bedingungen wiederholt wurde.

Eine Prüfung von `dmesg` auf `CMA_DBG buffer_map` zeigte, dass auch nach dem Fix dieselben 0x800000-(8-MB-)Puffer problemlos über `pin_user_pages` gemappt wurden (keine Pin-Fehler oder Kernel-Warnungen), der Codepfad selbst also wie beabsichtigt ausgeführt wurde. Auch eine erzwungene Kompaktierung per `echo 1 > /proc/sys/vm/compact_memory` zeigte keine Wirkung. `MemAvailable` blieb mit 7,1 GB gesund, und dass nicht ein Speichermangel im Gesamtsystem, sondern allein die spezifische Buchführungsgröße `CmaFree` sich nicht erholte, blieb wie vor dem Fix bestehen.

**Schlussfolgerung: Die Hypothese des fehlenden `FOLL_LONGTERM` wurde durch das Experiment widerlegt.** Der Wechsel von `get_user_pages()` zu `pin_user_pages()`+`FOLL_LONGTERM` ist zwar eine legitime, der dokumentierten Praxis des Linux-Kernels entsprechende Verbesserung, war aber nicht die direkte Ursache des in dieser Sitzung beobachteten CMA-Nichtfreigabe-Symptoms. Die Hypothese selbst ist theoretisch schlüssig (das Zusammenspiel zwischen dem Migrationsmechanismus von CMA und langfristiger Fixierung ist ein real existierendes, bekanntes Problemfeld) und bleibt als Hinweis auf die Codequalität weiterhin gültig, wird aber **nicht als alleinige Ursache eingestuft, die das diesmalige Messergebnis erklärt**.

### 7.5 Ausschluss von Ursachenkandidaten (abschließende Beurteilung siehe §8)

Die folgenden Ursachenkandidaten konnten durch Experimente eindeutig **ausgeschlossen** werden. Diese Liste ist als Ergebnis der Hypothesenprüfung gültig, stellt aber nicht die Beurteilung des Vorliegens eines Lecks selbst dar.

- Die treibereigene Zuweisung über `dma_alloc_coherent()` (desc list, continuous buffer) — nur wenige MB, kehrt korrekt auf 0 zurück
- Inkonsistenz bei map/destroy-Aufrufen des SG-Mappings — ausgeglichen
- SWIOTLB-Bounce-Buffer — kein einziges Mal genutzt (`io_tlb_used_hiwater=0`)
- Fehlendes `FOLL_LONGTERM` bei `get_user_pages()` — Fix implementiert und praktisch verifiziert, keine Verbesserung

Bis zum 3. Durchgang blieb als Faktum bestehen, dass `MemAvailable` gesund blieb, während allein `CmaFree` nach dem ersten Laden abfiel. Damals wurde dies als Nichtfreigabe interpretiert, aber eine Einzelmessung kann nicht zwischen „Verlust an verfügbarem Speicher" und „Umwandlung von movable CMA-Pages in Seiten-Cache" unterscheiden. Im 4. Durchgang wurde ausgehend von niedrigem `CmaFree` erneut getestet und die Beurteilung anhand von tatsächlicher Ladefähigkeit, Nettoabnahme bei Wiederholung, RSS und CMA-Zuweisungsfehlern korrigiert.

---

## 8. 4. Versuch: vanilla / `FOLL_LONGTERM` A/B-Nachtest und Feststellung der Fehlbeurteilung (2026-08-17)

### 8.1 Vergleichsobjekte

- `FOLL_LONGTERM`-Fix-Version: `pin_user_pages(FOLL_LONGTERM)` / `unpin_user_page()`, beim Laden `srcversion=C84A00ABB326748A1832CE1`
- Offizielles vanilla 5.4.0: Tag `v5.4.0`, Commit `b6dd17c609504e648eb516ff4a867167edf56f3c`, `get_user_pages()` / `put_page()`, beim Laden `srcversion=A260C39C9F2C06DD4FB072E`
- Kernel: `6.18.39+rpt-rpi-2712`
- HEF: `Qwen3-1.7B-Instruct.hef`（2,880,748,478 bytes）

### 8.2 Zwei aufeinanderfolgende Ladevorgänge in unabhängigen Prozessen

| Treiber | Durchlauf | baseline | loaded | nach exit | Änderung ggü. baseline | Laden |
|---|---:|---:|---:|---:|---:|---|
| `FOLL_LONGTERM` | 1 | 338 MB | 34 MB | 25 MB | **-313 MB (Abnahme)** | erfolgreich |
| `FOLL_LONGTERM` | 2 | 5 MB | 6 MB | 7 MB | **+2 MB (Zunahme)** | erfolgreich |
| vanilla | 1 | 376 MB | 99 MB | 112 MB | **-264 MB (Abnahme)** | erfolgreich |
| vanilla | 2 | 125 MB | 118 MB | 124 MB | **-1 MB (Abnahme)** | erfolgreich |

Bei beiden Treibern fiel `CmaFree` nur beim ersten Mal deutlich ab, und das Laden ausgehend von diesem niedrigen Wert beim zweiten Mal war erfolgreich, wobei die Nettoabnahme nahezu 0 betrug. Die bisherige Diagnose beurteilte allein anhand der Frage, „wie viele MB von der während des Ladens verbrauchten Menge zurückgegeben wurden", und stufte dadurch auch normale Fälle wie den zweiten Durchlauf, bei dem `CmaFree` bereits zu Beginn niedrig war, fälschlich als `FAIL` ein.

### 8.3 Generierung, Freigabe und erneutes Laden innerhalb desselben Prozesses

| Kennzahl | `FOLL_LONGTERM` | vanilla, 1. Mal | vanilla, Wiederholung bei niedrigem CMA |
|---|---:|---:|---:|
| Generierung abgeschlossen | 20/20 | 20/20 | 20/20 |
| 1. Laden | erfolgreich | erfolgreich | erfolgreich |
| 2. Laden nach Freigabe | erfolgreich | erfolgreich | erfolgreich |
| `CmaFree` bei Generierung 1→20 | 464→1,648 kB | 115,376→123,728 kB | 82,320→83,296 kB |
| `MemAvailable` bei Generierung 1→20 | 6,706,208→6,788,432 kB | 6,830,352→6,910,560 kB | 6,871,504→6,906,368 kB |
| RSS während Generierung | konstant 63,888 kB | 63,904〜63,920 kB | 63,936〜63,952 kB |
| CMA-Zuweisungsfehler | 0 | 0 | 0 |

Die Wiederholung bei niedrigem CMA für vanilla begann bei `CmaFree=87,424 kB`, unmittelbar nach der vollständigen Freigabe lag der Wert bei 79,520 kB und kehrte anschließend auf 87,344 kB zurück (Nettodifferenz 80 kB). Es zeigt sich kein Verhalten, bei dem durch wiederholtes Laden, Generieren und Freigeben Speicher verloren geht. Dass `nr_foll_pin_*` bei vanilla 0 ist, liegt daran, dass die `FOLL_PIN`-API nicht verwendet wird; dieser Wert kann daher nicht für den Vergleich der Pin-Freigabe herangezogen werden.

### 8.4 Interpretation des anfänglichen Rückgangs

Bei vanilla stieg `Cached` vom Zeitpunkt unmittelbar nach dem Neustart bis nach Abschluss aller Nachtests von 1,845,872 kB auf ca. 4,988,224 kB, während `MemAvailable` von 7,071,280 kB auf ca. 6,962,816 kB gehalten wurde. Der Anstieg entspricht dem Einlesen der Multi-GB-HEF und lässt sich so erklären, dass der anfängliche `CmaFree`-Rückgang nicht ein Verlust an unzugänglichem Speicher ist, sondern die Nutzung freier Pages — einschließlich movabler CMA-Pages — als Seiten-Cache.

### 8.5 Betriebliche Schlussfolgerung

1. Das Laden eines Modells darf nicht allein aufgrund des absoluten Werts von `CmaFree` abgelehnt werden. In der Praxis gelang das Laden von Qwen sogar ausgehend von unter 1 MB.
2. Niedriges `CmaFree` wird als Telemetrie erfasst; für die Fehlerbeurteilung wird der tatsächliche HailoRT-Speicherzuweisungsfehler herangezogen.
3. Der beobachtete `CmaFree`-Wert, tatsächliche Ladefehler und Leck-Diagnose dürfen nicht vermischt werden; sie werden in folgenden drei Zuständen behandelt:

| Zustand | Beurteilungsbedingung | Maßnahme auf Produktseite | Neustart/Untersuchung |
|---|---|---|---|
| `INCONCLUSIVE` | Nur anfänglicher Rückgang, weniger als 3 Durchläufe, oder die unten genannten `FAIL`-Bedingungen sind nicht erfüllt | Telemetrie wird erfasst, das Laden wird versucht. Niedriges `CmaFree` allein führt nicht zur Ablehnung | Kein Neustart. Weitere Messungen unter denselben Bedingungen |
| `OPERATIONAL_FAIL` | HailoRT hat tatsächlich einen host-memory allocation error zurückgegeben | Nur diese Ladeanfrage wird als Fehlschlag gewertet, unnötige Hailo-Workloads werden gestoppt und ein erneuter Versuch unternommen | Kein Neustart bei einem einzelnen Vorkommen. Nur wenn sich tatsächliche Fehler wiederholen und sich nach Freigabe der Workload nicht erholen, greift die Betriebsrichtlinie. Aktuell zeichnet Phase 0.5 nur `would_fire` auf und startet nicht automatisch neu |
| `FAIL` | Bei 3 Wiederholungen unter denselben Bedingungen ausgehend von niedrigem CMA ist die Nettoabnahme ggü. baseline nach Freigabe **bei 2 von 3 Durchläufen über 10 MB pro Durchlauf**, die Summe der positiven Nettoabnahmen aus 3 Durchläufen liegt **über 20 MB**, und es liegt ein monotoner RSS-Anstieg oder ein Rückgang von `MemAvailable` um mehr als 128 MB vor | Wird getrennt von der Ladefähigkeit einzelner Vorgänge als Leck-Diagnose erfasst | Untersuchung auf Kernel-/HailoRT-Seite wird wieder aufgenommen, direkte Beweise werden gesammelt. Die reine Diagnosefeststellung löst keinen automatischen Neustart aus |

Dieses 3-Durchlauf-Kriterium ist für künftige Diagnosen gedacht und wird nicht rückwirkend auf §8.2 angewendet, wo der unabhängige Prozessversuch je Treiber nur 2 Durchläufe umfasste. Die Schlussfolgerung des 4. Durchgangs beruht zusätzlich zum A/B aus §8.2 auf der Gesamtbetrachtung der 20 Generierungen, Freigaben und erneuten Ladevorgänge im selben Prozess sowie der Wiederholung bei niedrigem CMA aus §8.3.
4. Der `FOLL_LONGTERM`-Austausch ist als allgemeine Praxis der Linux-DMA-API sinnvoll, zeigte in diesem Fall aber keine Wirkung; das System wurde wieder auf das offizielle vanilla 5.4.0 zurückgesetzt.
5. Die automatische Neustart-Beurteilung wird nicht allein durch niedriges `CmaFree` ausgelöst, sondern setzt zwingend die Beobachtung eines tatsächlichen Ladefehlers voraus.

---

## 9. Weitere Maßnahmen (Stand 2026-08-17)

1. Die Prüfung und praktische Widerlegung des `FOLL_LONGTERM`-Fixes sind abgeschlossen. Diff und Wiederherstellungsmethode zur Reproduktion sind in Anhang B gespeichert und werden nicht auf den Produktions-Treiber angewendet.
2. **Produktseitig bereits umgesetzt**: `core/hailo_device_core/device_manager_genai.py::acquire_genai` wurde in v4.620.8 so angepasst, dass auch bei niedrigerem `CmaFree` als der geschätzte Bedarf `acquire_low_cma_observed` protokolliert und das tatsächliche Laden fortgesetzt wird. Im Ablehnungs-Tracker wird nur der tatsächliche HailoRT-host-memory-error protokolliert, den die factory zurückgegeben hat; `tests/test_hailo_cma_false_positive.py` fixiert die Fortsetzung des Ladens ausgehend von niedrigen Werten.
3. Die Aussage im alten Forum-Entwurf, „ein nachfolgendes `LLM(...)` wurde von HailoRT wegen insufficient host CMA abgelehnt", wurde anhand von Logs und der alten Implementierung erneut geprüft. In der zitierten PID-3237-Sitzung gibt es keinen acquire-Eintrag nach release, und sämtliche im selben Tages-Log nachvollziehbaren Ablehnungen wegen niedrigem CMA waren das eigene, HailoRT vorgelagerte Ereignis `acquire_rejected_low_cma`. Ein in einer anderen Sitzung bis zur factory durchgedrungener Fehlschlag hatte status 8 (`HAILO_INTERNAL_FAILURE`), nicht status 3 des host-memory error. Es gibt somit keinen HailoRT-OOM-Beleg, der die alte Aussage stützt; in `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md` wird ausdrücklich vermerkt, dass eine Ablehnung durch die eigene Schutzlogik in den Bericht eingeflossen ist, und die Aussage wird zurückgezogen.
4. Der Korrekturbeitrag fasst die Zahlen und den Geltungsbereich aus §8, die Korrektur der Implementierungs-Schutzlogik, die Widerlegung von `FOLL_LONGTERM` und die Hinweise zur Instrumentierung in einem einzigen aktuellen Entwurf zusammen; der alte englische Entwurf wird nicht in kopierbarer Form belassen.
5. Nur wenn ein tatsächlicher Ladefehler oder ein sich bei jeder Wiederholung kumulierender Verlust an verfügbarem Speicher erneut auftritt, wird die Leck-Untersuchung auf Kernel-/HailoRT-Seite wieder aufgenommen. Dabei werden direkte Beweise wie `page_owner`, CMA-Debug-Informationen, Zuweisungsfehler-Status, RSS und `MemAvailable` gesammelt.

---

## Anhang A. Wiederherstellungsverfahren auf v5.3.0

Nach einem `remove --all` von dkms schlägt die Wiederherstellung fehl, wenn im apt-Cache kein `.deb` mehr vorhanden ist, da `apt-get install --reinstall` dann nicht funktioniert (auch hier trat dies auf: `ダウンロードできないため、再インストールは不可能`). Da dpkg das Paket `hailort-pcie-driver` weiterhin als `ii` (installiert) führt, lässt sich der dkms-Baum manuell rekonstruieren, sofern das Quellverzeichnis des Pakets `/usr/src/hailort-pcie-driver/` nicht gelöscht wurde:

```bash
sudo rmmod hailo1x_pci

sudo rm -rf /usr/src/hailo1x_pci-5.3.0
sudo cp -r /usr/src/hailort-pcie-driver /usr/src/hailo1x_pci-5.3.0
sudo sed 's/@PCIE_DRIVER_VERSION@/5.3.0/' \
  /usr/src/hailo1x_pci-5.3.0/linux/pcie/dkms.conf.in \
  | sudo tee /usr/src/hailo1x_pci-5.3.0/linux/pcie/dkms.conf > /dev/null

# dkms.conf はツリー直下に置く必要がある（linux/pcie/ 配下ではエラーになる）
sudo cp /usr/src/hailo1x_pci-5.3.0/linux/pcie/dkms.conf /usr/src/hailo1x_pci-5.3.0/dkms.conf

sudo dkms add -m hailo1x_pci -v 5.3.0
sudo dkms build -m hailo1x_pci -v 5.3.0 -k $(uname -r)
sudo dkms install -m hailo1x_pci -v 5.3.0 -k $(uname -r) --force
sudo depmod -a
sudo modprobe hailo1x_pci
sudo udevadm trigger --subsystem-match=hailo1x
```

Wiederherstellungsbestätigung:

```bash
cat /sys/module/hailo1x_pci/version   # → 5.3.0
hailortcli fw-control identify        # → 正常応答なら復旧完了
```

---

## Anhang B. Speicherung, Anwendung und Wiederherstellung des Widerlegungs-Patches für den Treiber

### B.1 Gespeicherte Objekte und Einordnung

Der im A/B tatsächlich verwendete Treiber-Diff wurde unverändert in folgender Datei gespeichert.

- `docs/development/patches/hailo1x_pci-5.4.0-foll-longterm-cma-debug-experiment.patch`
- SHA-256: `7b5c4027f37432dbbbe39e4bdec2f0f5e8dd87e133473b5a44c44b1e86c5503f`
- Basis-Quelle: `hailo-ai/hailort-drivers` Tag `v5.4.0`, Commit `b6dd17c609504e648eb516ff4a867167edf56f3c`
- Betroffene Dateien: `linux/vdma/ioctl.c`, `linux/vdma/memory.c`, `linux/vdma/vdma.c`

Dieser Patch enthält nicht nur den Wechsel zu `pin_user_pages(FOLL_LONGTERM)` / `unpin_user_page()`, sondern auch die in §7.1 verwendete `CMA_DBG`-Instrumentierung. Es handelt sich also um einen **vollständigen Verifikations-Diff** zur Reproduktion des experimentellen Moduls beim A/B-Test, nicht um einen für den Produktivbetrieb empfohlenen Patch. Im Experiment zeigte sich keine Wirkung, und das aktuelle Gerät wurde bereits auf das offizielle vanilla 5.4.0 zurückgesetzt. An der HailoRT-Userspace-Library wurden keine Änderungen vorgenommen.

Die in derselben Kernel-/Quell-/Build-Umgebung bestätigten Kennwerte sind wie folgt.

| Zustand | `srcversion` |
|---|---|
| Experimenteller Patch | `C84A00ABB326748A1832CE1` |
| Offizielles vanilla 5.4.0 | `A260C39C9F2C06DD4FB072E` |

### B.2 Prüfung vor der Anwendung

Folgendes wird nur ausgeführt, wenn `/usr/src/hailo1x_pci-5.4.0` auf dem Raspberry Pi auf den oben genannten offiziellen Commit zeigt und an den drei betroffenen Dateien keine lokalen Änderungen vorliegen. Stimmen Commit, Patch-Prüfsumme oder die Prüfsumme von vanilla `memory.c` nicht überein, wird abgebrochen; der Patch darf nicht erzwungen angewendet werden.

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

### B.3 Anwendung des experimentellen Patches

Nur wenn alle Prüfungen erfolgreich waren, wird der Patch angewendet und das DKMS-Modul für den nächsten Boot installiert. Das geladene Modul wird nicht manuell per `rmmod`/`modprobe` ausgetauscht, sondern der Wechsel erfolgt nach dem Build über einen normalen Neustart.

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

`modinfo` zeigt das für den nächsten Boot installierte Modul, `/sys/module/.../srcversion` das aktuell geladene Modul. Dass die Werte zu diesem Zeitpunkt unterschiedlich sind, ist normal. Sobald die Vorbereitung abgeschlossen ist, wird neu gestartet und nach dem Start bestätigt, dass beide übereinstimmen.

```bash
sudo reboot

# 再接続後
modinfo -F srcversion hailo1x_pci
head -n 1 /sys/module/hailo1x_pci/srcversion
```

In derselben Verifikationsumgebung ist der Erwartungswert nach Anwendung des Patches `C84A00ABB326748A1832CE1`. Weicht er ab, wird der Test nicht auf Verdacht fortgesetzt; stattdessen werden Quell-Diff, Kernel und DKMS-Build-Log geprüft.

### B.4 Wiederherstellung des offiziellen vanilla 5.4.0

Die Wiederherstellung verlässt sich nicht auf das Rückgängigmachen des Patches, sondern stellt die drei betroffenen Dateien explizit aus dem verifizierten Commit wieder her. Dadurch wird ein Zustand vermieden, in dem nur teilweise angewendet wurde oder nur die Instrumentierung übrig bleibt.

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

In derselben Verifikationsumgebung ist der Erwartungswert des installierten vanilla-Moduls `A260C39C9F2C06DD4FB072E`. Es wird bestätigt, dass der aktuell geladene Wert abweicht, dann wird neu gestartet und nach dem Wiederverbinden bestätigt, dass beide `A260C39C9F2C06DD4FB072E` lauten.

---

## Referenz: Verwandte Dokumente

- `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md` — Auf der alten Messung beruhende Messdaten, Reproduktionsskripte und Forum-Entwurf zum CMA-Leck (Schlussfolgerung in §8 dieses Dokuments korrigiert)
- [HAILORT_5_3_0_MIGRATION.md](HAILORT_5_3_0_MIGRATION.md) — Protokoll der Migration von v5.2.0 auf v5.3.0 (u. a. Umbenennung des Device-Node-Namens auf `/dev/h1x-0`)
- [HAILO_CMA_LEAK_HAILORT_5_3_0.md](HAILO_CMA_LEAK_HAILORT_5_3_0.md) — Protokoll des CMA-Leck-Problems basierend auf der alten Diagnose (Schlussfolgerung in §8 dieses Dokuments korrigiert)
- `hailo-ai/hailort-drivers` GitHub-Repository (GPL-2.0, Quellcode offen): <https://github.com/hailo-ai/hailort-drivers>
