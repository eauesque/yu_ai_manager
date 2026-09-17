# Hailo-10H AI Hat+ Entwicklungsmaterial

Raspberry Pi 5 + Hailo AI Hat+ (Hailo-10H) für AI-Inferenz Implementierung.

Offizielle Dokumentation ist unvollständig, daher werden Erkenntnisse aus echter Entwicklung veröffentlicht.

## Dokumentations-Liste

| Datei | Inhalt |
|---------|------|
| [HAILORT_5_3_0_MIGRATION.md](HAILORT_5_3_0_MIGRATION.md) | HailoRT 5.2.0 → 5.3.0 Migrationsnoten. API Unterschiede, Device-Knoten-Umbennung (`/dev/h1x-0`), HEF Kompatibilität, Smoke-Test-Skripte |
| [VDEVICE_SHARING_PATTERN.md](VDEVICE_SHARING_PATTERN.md) | Mehrere Modelle (YOLO/CLIP/LLM/VLM/Whisper) im gleichen Prozess mit Shared VDevice Manager |
| [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md) | Grenzen der CMA-Zuweisung auf dem Pi 5 (Verhalten unter `numa=fake=8`). Warum `cma=1G` still fehlschlägt, `cma-512` (`dtoverlay=cma,cma-512` in `config.txt`) als bestätigte Obergrenze und empfohlener Wert, Speicheranforderungen von Hailo GenAI, das Nicht-Rückgabeverhalten von CMA bei `VDevice.release()` |
| [HAILO_SEMANTIC_SEARCH_DEVLOG.md](HAILO_SEMANTIC_SEARCH_DEVLOG.md) | CLIP Semantische Such-Entwicklungslog. Phase-Implementierungs-Historien, auftretende Probleme und Lösungen |
| [HAILO_DEVICE_CONTROL.md](HAILO_DEVICE_CONTROL.md) | Hailo Device-Kontrolle, VDevice-Verwaltung, Exklusive Kontrolle, Modell-Wechsel |
| [ONNX_TO_HEF_CONVERSION_GUIDE.md](ONNX_TO_HEF_CONVERSION_GUIDE.md) | ONNX → HEF Konvertierungs-Verfahren. Dataflow Compiler, Quantisierung, Troubleshooting |
| [ONNX_TO_HEF_CONVERSION_REPORT.md](ONNX_TO_HEF_CONVERSION_REPORT.md) | Konvertierungs-Validierung Report (DFC v5.2.0). WD-Tagger 3 Modell Fehler-Detail Analyse |
| [WD_TAGGER_DFC_5_3_0_FOLLOWUP.md](WD_TAGGER_DFC_5_3_0_FOLLOWUP.md) | DFC v5.3.0 Follow-up. Gleiche WD-Tagger 3 Modell Neuvalidierung (immer noch Fehler), Plus v5.3.0 Verbesserungen (neue `_create_layer_normalization_layer`, onnxsim retry flow, end-node Empfehlungen) |
| [CLIP_ONNX_DEVLOG.md](CLIP_ONNX_DEVLOG.md) | CLIP ONNX Multi-Backend Entwicklungslog. Fallback für Hailo-Hardware-freie Umgebungen |
| [HAILO_CMA_LEAK_HAILORT_5_3_0.md](HAILO_CMA_LEAK_HAILORT_5_3_0.md) | **Strukturelle Einschränkung und Messung des CMA-Leaks**. Dass `VDevice.release()` nicht zurückgewinnt, der fortlaufende Leak während der Inferenz (ca. 14 MB/Minute), und dass **weder Kill des Kindprozesses noch Prozessende noch Modul-Unload zur Rückgewinnung führen** (in Phase-0-PoC zweimal unabhängig gemessen, nach SIGTERM + 30 Sekunden Wartezeit nur +8 MB). Das einzige zuverlässige Rückgewinnungsmittel ist der Neustart des Pi selbst **(alte Schlussfolgerung. Durch erneute Tests mit HailoRT / driver 5.4.0 in [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) §8 korrigiert)** |
| [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) | **Korrektur und erneute Verifikation der obigen CMA-Leak-Beurteilung**. A/B-Vergleich zwischen offiziellem vanilla und der `FOLL_LONGTERM`-Fix-Version mit HailoRT / driver 5.4.0, der die alte Beurteilung als Fehlurteil korrigiert, das nur den absoluten `CmaFree`-Erholungsbetrag nach dem ersten HEF-Laden betrachtet hatte. Mit Quellcode-Diff v5.3.0 → v5.4.0, Fallstricken beim Eigenbau und Messdaten |
| [HAILO_AUTO_REBOOT_PHASE05.md](HAILO_AUTO_REBOOT_PHASE05.md) | Betriebsleitfaden für die daraufhin eingeführte automatische Reboot-Strategie. Beobachtungsphase (protokolliert nur `would_fire`, ohne Neustart), Entscheidungsschwellen, Grund für den Standardwert `mode = "off"` |
| [HAILO_AUTO_REBOOT_PHASE05_RUNBOOK.md](HAILO_AUTO_REBOOT_PHASE05_RUNBOOK.md) | Runbook für dieselbe Phase in dieser Umgebung. Verfahren zum Starten, Überprüfen und Abschließen der Beobachtung |
| [HAILO_LLM_SUBPROCESS_DEVLOG.md](HAILO_LLM_SUBPROCESS_DEVLOG.md) | Implementierungslog zur Behebung des Problems, dass die Quart Event Loop während cold_load (~71 Sekunden) durch das GIL blockiert, mittels Subprocess-Isolierung der LLM-Chat-Inferenz |
| [HAILO_10H_ECOSYSTEM_ASSESSMENT.md](HAILO_10H_ECOSYSTEM_ASSESSMENT.md) | Bewertung des Hailo-10H-Ökosystems (Stand 2026-03-19, HailoRT/DFC v5.2.0) |

## Wichtige Bekannte Punkte

### Umgebung / Raspberry Pi 5

- **Die CMA-Obergrenze auf dem Pi 5 (8 GB) beträgt 512 MB, konfiguriert in `config.txt`**: Der Standard-Kernel wendet `numa=fake=8` an und teilt den RAM in 8 × 1 GB NUMA-Knoten auf. CMA muss innerhalb der Grenzen eines einzelnen Knotens liegen; `cma-1024` und `cma-768` schlagen still fehl (`CmaTotal=0`, kein Kernel-Panic). **`cma-512` ist die bestätigte Obergrenze und der empfohlene Wert** (am 2026-05-16 über ein Overlay erneut verifiziert, `CmaTotal: 524288 kB`). Aufgrund einer Firmware-Regression von 2026-05 ist nicht die cmdline `cma=`, sondern `dtoverlay=cma,cma-512` in `/boot/firmware/config.txt` zu verwenden. Details siehe [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md)
- **Nach Neustart immer CMA validieren**: `grep CmaTotal /proc/meminfo` Check. Wenn 0 bedeutet Setting ignoriert
- **`VDevice.release()` gibt CMA nicht zurück**: CMA wird über die gesamte OS-Sitzung hinweg gehalten. VDevice ist als Singleton im Sitzungsumfang zu behandeln. **Auch ein Prozess-Neustart gibt es nicht frei** —— dass weder Kill des Kindprozesses noch Prozessende noch Modul-Unload zur Rückgewinnung führen, wurde im Phase-0-PoC zweimal unabhängig gemessen (nach SIGTERM + 30 Sekunden Wartezeit nur +8 MB, erwartet ≥250 MB). Das einzige zuverlässige Rückgewinnungsmittel ist `sudo reboot` (PCIe Power-Cycle) auf dem Pi selbst. Details und die daraufhin ergriffene Maßnahme siehe [HAILO_CMA_LEAK_HAILORT_5_3_0.md](HAILO_CMA_LEAK_HAILORT_5_3_0.md). **Korrektur**: Dieser Punkt basiert auf der alten Messung. Im A/B-Retest mit HailoRT / driver 5.4.0 trat der praktisch relevante CMA-Leak nicht erneut auf, korrigiert in [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) §8
- **`numa=fake=8` betrifft Node.js Install**: Speicher pro NUMA-Knoten (1 GB) wird als Total RAM falsch erkannt, npm/node Installer abgebrochen. Upstream gemeldet: [anthropics/claude-code#33864](https://github.com/anthropics/claude-code/issues/33864)
- **Python Wheel ist Source Build**: Keine aarch64 Wheel auf PyPI oder Hailo Developer Zone
- **hailo-ollama Exklusion**: Stoppen Sie hailo-ollama wenn VDevice in Nutzung
- **VDevice Leak bei Prozess-Ende**: `lsof /dev/hailo*` überprüfen und `kill PID` tun

### VDevice / API

- **InferModel API verwenden**: `VDevice.create_infer_model()` ist korrekt. Alte VStreams API (`InferVStreams`, `ConfigureParams.create_from_hef`) ist auf Hailo-10H `HAILO_NOT_IMPLEMENTED`
- **InferModel unterstützt nur einfache Modelle**: 1-Input YOLO HEF funktioniert, aber 2-Input 4-Output Whisper HEF gibt `configure()` `HAILO_INVALID_ARGUMENT`. Nutzen Sie GenAI SDK für komplexe Modelle
- **VDevice mapped zu 1 physikalisches Device**: Wenn Sie 2 `VDevice()` Instanzen gleichzeitig erstellen, bekommen Sie `HAILO_OUT_OF_PHYSICAL_DEVICES(74)`
- **Model-Wechsel benötigt vollständige VDevice-Freigabe**: Python-Ref auf `None` setzen ist unzureichend. Nutzen Sie `VDevice.release()` um physikalisches Device explizit freizugeben vor neuer VDevice-Erstellung
- **`set_format_type(FormatType.FLOAT32)` nicht unterstützt in hailort 5.2.0**: `format_type` Attribut existiert nicht. Manuelle uint8 Quantisierung/De-Quantisierung oder GenAI SDK
- **Output ist uint8 Quantisiert**: Float32 Output Buffer allokieren gives `buffer size mismatch`. Allokiere mit uint8, De-Quantisiere mit Parametern (scale, zero_point) zu float32

### GenAI (LLM / VLM / Speech2Text)

- **HailoRT 5.3.0 lehnt `temperature=0.0` ab**: `LLM.generate()` gibt `HAILO_INVALID_ARGUMENT` bei `temperature=0` aus. Clamp vor call: `temperature = max(temperature, 0.01)`. Betrifft OpenAI-kompatible Clients, die standardmäßig `temperature=0` senden
- **GenAI × 2 gleich-Zeit Laden möglich**: LLM + Whisper-tiny können gleich-Zeit auf gleicher VDevice laden (HailoRT 5.3.0 überprüft). CMA-Puffer nach Laden: 256 MB etwa 10 MB. Whisper-base+ has höhere Memory Overflow Wahrscheinlichkeit
- **LLM + Whisper-tiny CMA Budget**: Etwa 246 MB total (measured). Alle Modell CMA-Zahlen siehe [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md)

### Whisper (Sprach-Erkennung)

- **GenAI SDK verwenden**: `hailo_platform.genai.Speech2Text` bietet Full-Pipeline. Encoder+Decoder vollständig auf NPU ausführen
- **HEF ist nur Decoder**: `Whisper-Base.hef` 2-Input (encoder_features + token_embeddings) und 4-Output (vocab 4-teilig aufgeteilt). InferModel API funktioniert nicht
- **GenAI SDK Input**: Little-endian float32 (`<f4`), [-1,1] normalisierte PCM Audio-Daten
- **ONNX Fallback**: Wenn GenAI SDK nicht available, HuggingFace ONNX Modelle für Encoder+Decoder auf CPU

### YOLO (Objekt-Detektion)

- **InferModel API funktioniert**: 1-Input HEF kein Problem
- **ONNX Fallback**: Wenn Hailo nicht available, auto `yolo11n.onnx` herunterladen. Output `(1,84,8400)` ist yolov8n kompatibel
- **Init-Fehler Cooldown**: Nach Engine Init Fehler 60 Sekunden nicht retry

### Verteilte Inferenz

- **Healthcheck erforderlich**: `filter_available()` Remote-Knoten Leben überprüfen vor Verteilungs-Start
- **Remote-Fehler**: Verbleibende Items auf Local fallback. Nach Wiederherstellung auto-erkannt in nächsten Batch
- **Workload-Verteilung**: GPU vs NPU Speed-Unterschied ist groß, gleiche Aufteilung ist ineffizient. Dynamic-Verteilung basierend Durchsatz-Messung ist zukünftige Aufgabe

