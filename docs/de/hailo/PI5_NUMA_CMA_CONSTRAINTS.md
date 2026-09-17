# CMA-Beschränkungen unter `numa=fake=8` auf dem Pi 5

Praktische Erkenntnisse zur CMA-Zuweisung auf dem Raspberry Pi 5 (8 GB) beim Ausführen von Hailo-10H-Workloads.
Beschreibt die Obergrenze von `cma=`, den Grund, warum Werte über 512M stillschweigend fehlschlagen, und wie CMA-Speicher zurückgewonnen wird, den der Display-Treiber verbraucht hat.

**Zielgruppe**: Entwickler, die auf dem Raspberry Pi 5 Hailo-GenAI-Modelle (LLM, Speech2Text) ausführen
(mit AI HAT / AI HAT+).

---

## ⚠️ Hinweis zur Firmware-Regression 2026-05

**Seit Release 2026-05-13 von `raspi-firmware 1:1.20260513-1` + `pieeprom-2026-05-11`** führt das Schreiben von `cma=` in `/boot/firmware/cmdline.txt` — unabhängig von der Größe — dazu, dass die VC-Firmware-Mailbox vollständig verstummt (`vcgencmd ioctl_set_msg failed:-1`, `raspberrypi-clk -22`, HEVC `-517`, fehlendes cpufreq-sysfs).

**Ab 2026-05-16 bestätigte empfohlene Methode**: Nicht `cma=` in cmdline, sondern `dtoverlay=cma,cma-512` in `/boot/firmware/config.txt` eintragen. Da die Reservierung über den `linux,cma`-Reserved-Memory-Node des Device Tree erfolgt, kollidiert sie nicht mit der neuen Firmware. Details siehe §6 und [`docs/development/investigations/pi5_firmware_cma_mailbox_regression_2026-05-16.md`](../../development/investigations/pi5_firmware_cma_mailbox_regression_2026-05-16.md).

Die folgende ältere Beschreibung (Empfehlung von cmdline `cma=512M`) ist das Prüfergebnis vom 2026-04-15. Die Erkenntnis zur Obergrenze (512M) durch die NUMA-Knotengrenze bleibt weiterhin gültig, **aber der Konfigurationsort wechselt von cmdline zum overlay-Argument in config.txt**.

---

## TL;DR

- **Der Konfigurationsort ist `dtoverlay=cma,cma-512` in `config.txt`** (bestätigt am 2026-05-16. `cma=` in cmdline zerstört bei der neuen Firmware die Mailbox)
- `cma-1024` und `cma-768` **schlagen auf dem Pi 5 (8 GB) stillschweigend fehl** — `CmaTotal` wird 0, weder Kernel-Panic noch Warnung erscheint (Obergrenze durch NUMA-Knotengrenze; es wird vermutet, dass dieselbe Beschränkung auch über den overlay-Weg bestehen bleibt)
- **`cma-512` ist der bestätigte Grenzwert und die Empfehlung** (am 2026-05-16 über den overlay-Weg auf dem Pi 5 8 GB erneut verifiziert, `CmaTotal: 524288 kB` bestätigt zugewiesen)
- Grundursache: Der Standard-Kernel des Pi 5 wendet `numa=fake=8` an und begrenzt zusammenhängende Zuweisungen auf einen NUMA-Knoten (1 GB)
- **`dtoverlay=vc4-kms-v3d` + `max_framebuffers=2` verbrauchen beim Booten ~157 MB CMA** — selbst wenn die Initialisierung des DRM-Treibers fehlschlägt (verifiziert am 2026-04-15)
- **`camera_auto_detect=1`** lädt `pisp_be` und `videobuf2_dma_contig` und verbraucht zusätzlichen CMA-Speicher. Für kopflose (headless) Systeme wird die Deaktivierung empfohlen
- **Headless-optimierte Baseline** (beide Overlays deaktiviert): ~98 MB CMA-Nutzung beim Booten, ~414 MB frei für Hailo-Modelle
- **YOLO-InferModel nutzt 0 MB CMA** (bestätigt am 2026-04-15) — nur GenAI-Modelle (LLM, Speech2Text) werden aus CMA zugewiesen
- Gleichzeitiges Laden von LLM (qwen2.5-1.5b) + Whisper-base: insgesamt ~328 MB — passt innerhalb der Headless-optimierten Baseline
- CMA wird bei einem Server-Neustart nicht zurückgewonnen — nur ein vollständiger Systemneustart (PCIe-Wiedereinschalten) gibt ihn frei (`hailo1x_pci`-Treiberfehler, bereits an Hailo gemeldet)
- Die VDevice ist als **Singleton mit Prozesslebensdauer** zu behandeln. Verdrängen/Neuladen ist verboten

---

## 1. Symptom

Wenn `cma=1G` (oder `cma=768M`) in `/boot/firmware/cmdline.txt` gesetzt und neu gestartet wird, ergibt sich Folgendes:

```
$ grep CmaTotal /proc/meminfo
CmaTotal:              0 kB
```

Das System startet normal. Es gibt weder eine Kernel-Panic noch eine Fehlermeldung. Die CMA-Einstellung in `cmdline.txt` wird **stillschweigend ignoriert**, und alles, was von CMA abhängt (Hailo-10H-NPU, V4L2-Kameras usw.), schlägt bei der Initialisierung fehl.

**Überprüfen Sie nach jeder Änderung von `cmdline.txt` stets die CMA-Zuweisung:**

```bash
grep CmaTotal /proc/meminfo
```

---

## 2. Grundursache: die Knotengrenze von `numa=fake=8`

Der Standard-Raspberry-Pi-OS-Kernel für den Pi 5 wendet `numa=fake=8` an und teilt die 8 GB physischen Speicher in **acht virtuelle NUMA-Knoten zu je 1 GB** auf:

```
numa=fake=8 physical memory layout (8 GB total):

┌──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┐
│ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │
│node0 │node1 │node2 │node3 │node4 │node5 │node6 │node7 │
└──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┘
```

Linux-CMA (`cma_init_reserved_mem`) muss beim Booten als **zusammenhängender physischer Speicher, der keine NUMA-Knotengrenze überschreitet**, zugewiesen werden.
Dies erzwingt eine strikte Obergrenze von 1 Knoten = 1 GB. Da der Kernel selbst Speicher desselben Knotens belegt, kann nicht genau 1 GB reserviert werden:

> **Die folgende Tabelle ist ein Messprotokoll aus der Zeit der cmdline-Methode, Stand 2026-04-15.**
> Die Erkenntnis zum Obergrenzwert (512M), der von der NUMA-Knotengrenze herrührt, bleibt weiterhin gültig, aber **`cma=` in cmdline darf jetzt nicht mehr verwendet werden** (siehe Hinweis zur Firmware-Regression am Anfang des Dokuments).
> Die aktuelle Konfigurationsmethode ist `dtoverlay=cma,cma-512` in `config.txt` (§6).

| Einstellung in `cmdline.txt` (Aufzeichnung vom 2026-04-15) | Ergebnis |
|---|---|
| `cma=1G` | Versucht den gesamten Knoten zu verbrauchen. Kein Platz für den Kernel → **stiller Fehlschlag**, CmaTotal=0 |
| `cma=768M` | Überschreitet den verlässlichen zusammenhängenden Bereich → **stiller Fehlschlag**, CmaTotal=0 (verifiziert am 2026-04-15) |
| `cma=512M` | Hälfte eines Knotens → **bestätigt stabil** ✓ (verifiziert am 2026-04-15) ← Die Empfehlung zu jener Zeit. **Verwenden Sie jetzt `dtoverlay=cma,cma-512`** |
| `cma=384M` | Nicht getestet (512M ist bestätigt; 384M ist unnötig) |
| `cma=256M` | Stabil, aber bei gleichzeitiger Nutzung von LLM + Whisper knapp |
| `cma=128M` | Stabil, aber für Hailo GenAI unzureichend (allein das LLM benötigt ~234 MB) |

### Warum der Fehlschlag stillschweigend erfolgt

`cma_init_reserved_mem` gerät bei einem Zuweisungsfehler nicht in Panik. Der Kernel startet mit `CmaTotal=0` und verhält sich, als wäre kein CMA angefordert worden.
Der in `cmdline.txt` geschriebene Wert wird faktisch ignoriert.

---

## 3. CMA-Anforderungen von Hailo-10H

Gemessen auf Raspberry Pi 5, AI HAT+, HailoRT 5.3.0:

| Modell / Kombination | CMA-Nutzung | Anmerkung |
|---|---|---|
| LLM — qwen2.5-1.5b-chat (einzeln) | **~234 MB** | gemessen am 2026-04-15 |
| YOLO-InferModel (yolov8n, configure + bindings) | **0 MB** | bestätigt am 2026-04-15 |
| Whisper-tiny (einzeln) | ~70 MB | geschätzt |
| Whisper-base (einzeln) | ~100 MB | geschätzt |
| Whisper-small (einzeln) | ~150 MB | geschätzt |
| **LLM + Whisper-tiny (gleichzeitig)** | **~246 MB** | gemessen bei CMA 256 MB |
| **LLM + Whisper-base (gleichzeitig)** | **~334 MB** | geschätzt. Erwartet, innerhalb der Headless-Baseline zu bleiben |

**YOLO nutzt 0 MB CMA**: Bei HailoRT 5.3.0 weisen YOLO-InferModel, `configure()` und `create_bindings()` überhaupt keinen CMA-Speicher zu.
Ein-/Ausgabe-DMA-Puffer werden nicht aus CMA, sondern über `set_buffer()` aus vorab zugewiesenen numpy-Arrays gemappt.
YOLO ist daher kein Faktor in der CMA-Budgetberechnung.

Mit CMA 512 MB und angewendeter Headless-Optimierung (siehe §5) wird erwartet, dass folgende Konfigurationen funktionieren:

- Nur LLM (~234 MB, ~180 MB Spielraum)
- Nur Whisper-tiny / Whisper-base (passt problemlos)
- LLM + Whisper-base gleichzeitig (insgesamt ~334 MB, ~80 MB Spielraum)

Die Kombination Whisper-small mit LLM (geschätzt ~384 MB) nähert sich der theoretischen Grenze — vor dem Vertrauen darauf sollten Sie dies durch reale Messung bestätigen.

Details siehe die Ergebnisse gleichzeitiger Ladetests in [hailo_genai_concurrent_2026-04-15.md](../../development/investigations/hailo_genai_concurrent_2026-04-15.md).

---

## 4. CMA wird erst bei einem vollständigen Neustart zurückgewonnen

Von HailoRT zugewiesener CMA-Speicher verbleibt im Speicher bis zu einem vollständigen Systemneustart.
Dies gilt unabhängig von `VDevice.release()`, der Beendigung des Serverprozesses oder dem Neuladen des Kernelmoduls.

**Grundursache** (bestätigt am 2026-04-15): `hailo1x_pci` behält DMA-kohärente Zuweisungen auch nach dem Schließen des Geräte-Filedeskriptors oder dem Neuladen des Moduls bei.
Freigegeben wird der Speicher nur durch einen vollständigen Neustart (PCIe-Wiedereinschalten). Der Bug wurde bereits an Hailo gemeldet.

| Phase | CmaFree (CMA 512 MB, Headless-optimiert) |
|---|---|
| Booten | **~426 MB** |
| Nach LLM-Ladevorgang (~234 MB) | ~192 MB |
| Nach Whisper-base-Ladevorgang (~100 MB) | ~92 MB |
| Nach `VDevice.release()` | ~92 MB (**wird nicht zurückgegeben**) |
| Nach Beenden des Serverprozesses | ~92 MB (**wird nicht zurückgegeben**) |
| Nach `rmmod hailo1x_pci && modprobe hailo1x_pci` | ~92 MB (**wird nicht zurückgegeben**) |
| Nach vollständigem Systemneustart | **~426 MB (wiederhergestellt)** |

**Implikation**: Der CMA-Verbrauch akkumuliert sich über Server-Neustarts innerhalb derselben Boot-Sitzung hinweg.
Erwarten Sie nicht, dass CMA durch einen Server-Neustart zurückgewonnen wird. Entwerfen Sie die VDevice als **Singleton mit Prozesslebensdauer**.
Wenn CMA erschöpft ist, wird er nur durch einen vollständigen Systemneustart wiederhergestellt.

---

## 5. Headless-Optimierung: `/boot/firmware/config.txt`

Die Standard-`config.txt` von Pi OS enthält zwei Einstellungen, die selbst auf einem kopflosen (headless, ohne Display) System erhebliche Mengen an CMA verbrauchen.

### 5.1 `dtoverlay=vc4-kms-v3d` und `max_framebuffers=2`

**Effekt**: Die Pi-5-Firmware reserviert beim Booten CMA-Framebuffer für die Display-Pipeline im Voraus.
Mit `max_framebuffers=2` verbraucht dies ~157 MB CMA, **bevor überhaupt ein Userspace-Prozess läuft**.

Diese Zuweisung bleibt bestehen, selbst wenn der Linux-DRM-Treiber später bei der Initialisierung fehlschlägt (z. B. `[drm] Couldn't stop firmware display driver: -22` oder `Couldn't get core clock` in `dmesg`).

| Zustand von `config.txt` | CmaFree beim Booten |
|---|---|
| `dtoverlay=vc4-kms-v3d` + `max_framebuffers=2` aktiviert (Standard) | **~257 MB** |
| Beide auskommentiert | **~305 MB** (+~48 MB) |

**Korrektur** (Headless-/Server-Modus):

```ini
# /boot/firmware/config.txt
#dtoverlay=vc4-kms-v3d
#max_framebuffers=2
```

**Kompromiss**: Für hardwarebeschleunigte Anzeige und 3D (V3D) wird `vc4-kms-v3d` benötigt.
Wenn auf das System nur per SSH oder Web-Interface zugegriffen wird, ist eine Deaktivierung unbedenklich.

### 5.2 `camera_auto_detect=1` und `display_auto_detect=1`

**Effekt**: Diese Overlays sondieren beim Booten CSI-Kameras und DSI-Displays und laden `pisp_be` (Pi-ISP-Backend) und `videobuf2_dma_contig`.
Die geladenen Module und erkannte Hardware reservieren zusätzlichen CMA-Speicher im Voraus.

| Zustand von `config.txt` | CmaFree beim Booten |
|---|---|
| `camera_auto_detect=1` + `display_auto_detect=1` | ~305 MB (nach Deaktivierung von vc4) |
| Beide auf 0 gesetzt | **~426 MB** (+~121 MB) |

**Korrektur**:

```ini
camera_auto_detect=0
display_auto_detect=0
```

**Hinweis**: `camera_auto_detect=0` betrifft nur CSI-Kameras. USB-Kameras (UVC / `uvcvideo`) sind davon nicht betroffen und funktionieren weiterhin normal.

### 5.3 Empfohlene minimale `config.txt` für Headless-AI-HAT+-Einsatz

```ini
auto_initramfs=1
arm_64bit=1
arm_boost=1

[cm5]
dtoverlay=dwc2,dr_mode=host

[all]
dtparam=pciex1_gen=3
```

Geschätzter CMA-Verbrauch beim Booten mit dieser Konfiguration: **~98 MB genutzt**, ~414 MB frei für Hailo-Modelle.

### 5.4 CMA-Budgetübersicht (CMA 512 MB, Headless-optimiert)

| Konfiguration | CmaFree | Für Hailo verfügbar |
|---|---|---|
| Standard (vc4-kms-v3d + Kamera aktiviert) | ~257 MB | ~257 MB |
| vc4-kms-v3d + max_framebuffers deaktiviert | ~305 MB | ~305 MB |
| + camera/display_auto_detect=0 | **~426 MB** | **~426 MB** |
| Nach LLM-Ladevorgang (~234 MB) | ~192 MB | für Whisper |
| Nach LLM + Whisper-base-Ladevorgang (~100 MB) | ~92 MB | (Spielraum) |

---

## 6. Empfohlene Konfiguration

### `dtoverlay=cma,cma-512` setzen (bestätigt am 2026-05-16)

```bash
# Aktuellen CMA-Status prüfen
grep CmaTotal /proc/meminfo

# 1) Bestehendes cma= aus cmdline.txt entfernen (zerstört bei neuer Firmware die Mailbox)
sudo sed -i 's/ *cma=[^ ]*//g' /boot/firmware/cmdline.txt

# 2) dtoverlay=cma,cma-512 in den [all]-Abschnitt von config.txt eintragen
sudo sed -i '/^\[all\]$/a dtoverlay=cma,cma-512' /boot/firmware/config.txt

# 3) Kaltstart empfohlen (Netzstecker ziehen und wieder einstecken)
sudo sync && sudo poweroff

# Nach dem Neustart verifizieren (alle 4 Punkte müssen geprüft werden)
vcgencmd version                                # Broadcom-Antwort erforderlich (Stille = Fehlschlag)
grep CmaTotal /proc/meminfo                     # 524288 kB erwartet
journalctl -b -k | grep 'linux,cma'             # "initialized node linux,cma" muss erscheinen
journalctl -b -k | grep '0x00030087'            # darf nicht erscheinen
```

Wenn in dmesg `OF: reserved mem: initialized node linux,cma, compatible id shared-dma-pool` erscheint, ist dies der Beweis, dass die Reservierung über den DT-Weg erfolgte.
Erscheint stattdessen `Reserved memory: bypass linux,cma node, using cmdline CMA params instead`, bedeutet dies, dass noch `cma=` in cmdline vorhanden ist — dieses muss entfernt werden.

### Bei Aktivierung von `vc4-kms-v3d`

Wird KMS-DRM für die Anzeige benötigt, kann dies in Form eines overlay-Arguments integriert werden:
```ini
dtoverlay=vc4-kms-v3d,cma-512
```
Da `vc4-kms-v3d` jedoch, wie in §5.1 beschrieben, ~157 MB CMA verbraucht, wird für Hailo-GenAI-Einsatzzwecke die Deaktivierung empfohlen.

### Verifikation nach jeder Kernel-/Firmware-/Konfigurationsänderung

Nach Änderungen an `/boot/firmware/cmdline.txt` oder `config.txt` sowie nach Kernel-/Firmware-Upgrades können sich der CMA-Status und die Mailbox-Antwort stillschweigend ändern.
Machen Sie die oben genannte Verifikation der 4 Punkte zur Routine nach jedem Neustart.

---

## 7. Wechselwirkung mit anderen `numa=fake=8`-Problemen

`numa=fake=8` verursacht mindestens zwei verschiedene Probleme, die für dieses Projekt relevant sind:

| Problem | Symptom | Grundursache |
|---|---|---|
| Stiller CMA-Fehlschlag | `CmaTotal=0` nach `cma=1G`, `cma=768M` | NUMA-Knotengrenze begrenzt zusammenhängende Zuweisungen |
| Fehlschlag bei Node.js-Installation | npm/node-Installer bricht mit Speicherfehler ab | Speicher pro NUMA-Knoten (1 GB) wird fälschlich als Gesamt-RAM erkannt. Stromaufwärts gemeldet als [anthropics/claude-code#33864](https://github.com/anthropics/claude-code/issues/33864) |
| CMA-Drain durch `vc4-kms-v3d` | Verbraucht beim Booten ~157 MB. Wird auch bei fehlgeschlagener DRM-Initialisierung nicht zurückgegeben | `max_framebuffers=2` lässt die Firmware CMA-Framebuffer reservieren, noch bevor der Linux-Treiber startet |

Sowohl der stille Fehlschlag als auch der vc4-Drain gehen auf dieselbe grundlegende Beschränkung zurück (DMA-Zone unter 4 GB, NUMA-Knotengrenze).
Prüfen Sie bei unerwarteten speicherbezogenen Störungen zuerst `/proc/meminfo` und `config.txt`.

---

## 8. Schnelle Diagnose-Checkliste

```bash
# 1. Mailbox-Antwort (bei neuer Firmware zuerst prüfen)
vcgencmd version                     # Stille = Verdacht, dass cma= noch in cmdline steht

# 2. CMA-Zuweisung prüfen
grep CmaTotal /proc/meminfo          # 0 kB = stiller Fehlschlag

# 3. DT-Weg vs. cmdline-Weg prüfen
journalctl -b -k | grep 'linux,cma'
# Erwartet: "initialized node linux,cma, compatible id shared-dma-pool" (DT-Weg = normal)
# Fehler:   "bypass linux,cma node, using cmdline CMA params instead" (cmdline verbleibt)

# 4. NUMA-Topologie prüfen
numactl --hardware                   # Zeigt Anzahl der Knoten und Speicher pro Knoten

# 5. Aktuelle Kommandozeile und Overlay-Einstellung prüfen
cat /boot/firmware/cmdline.txt       # Prüfen, dass kein cma= enthalten ist
grep '^dtoverlay=cma' /boot/firmware/config.txt   # dtoverlay=cma,cma-512 muss vorhanden sein

# 6. Verfügbarkeit des Hailo-Geräts prüfen
ls /dev/h1x-*                        # HailoRT 5.3.0: /dev/h1x-0
hailortcli fw-control identify       # Prüfen, dass die NPU zugänglich ist

# 7. config.txt auf CMA-Verbraucher prüfen
grep -E 'vc4-kms-v3d|camera_auto_detect|display_auto_detect|max_framebuffers' \
  /boot/firmware/config.txt

# 8. Geladene Kernelmodule prüfen (CMA-Nutzer)
lsmod | grep -E 'vc4|v3d|pisp|videobuf2_dma'
```

---

**Testumgebung**: Raspberry Pi 5 8 GB, Raspberry Pi OS
(Linux 6.12.62+rpt-rpi-2712, aarch64), HailoRT 5.3.0, AI HAT+, CMA=512M
(**erneut verifiziert am 2026-05-16**: Linux 6.18.29+rpt-rpi-2712 / raspi-firmware 1:1.20260513-1 / pieeprom-2026-05-11 / Hailo-10H AI HAT — über `dtoverlay=cma,cma-512` wurden 524288 kB zugewiesen, Mailbox-Antwort bestätigt)
