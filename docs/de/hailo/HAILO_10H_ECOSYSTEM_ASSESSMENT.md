# Hailo-10H Ecosystem-Bewertung

**Erstellt**: 2026-03-19  
**Ziel**: Hailo-10H (AI HAT 2 for Raspberry Pi 5)  
**HailoRT**: v5.2.0  
**DFC**: v5.2.0  
**Zweck**: Erfahrungen mit der Hailo-10H-Entwicklung in diesem Projekt dokumentieren und realistische Einschränkungen sowie Ausblicke zusammenfassen

---

## Gesamtbewertung

**Hardware ausgezeichnet. Software-Ökosystem entscheidend unzureichend.**

Hailo-10H ist eine NPU mit 40 TOPS Inferenzleistung, und das Hardware-Potenzial ist durchaus vorhanden. Jedoch ist die Software-Toolchain geschlossen und unreif, sodass Entwickler eigene Modelle praktisch **nicht frei einsetzen können**.

In diesem Projekt wurden CLIP-semantische Suche, YOLO-Objekterkennung, LLM/VLM-Chat, Whisper-Spracherkennung und ein verteilter Tagger-Server implementiert — alles mit Hailo-10H auf vielfältige Weise. Stabil funktioniert jedoch **nur, was auf vorcompilierte HEF-Dateien aus Hailos offiziellem Model Zoo zurückgreift**. Eigene ONNX-zu-HEF-Konvertierungen sind **kein einziges Mal gelungen**.

---

## Implementierungsstatus in diesem Projekt

### Funktionierende Funktionen (alle mit offiziellen HEF-Downloads)

| Funktion | Verwendete API | HEF-Quelle |
|------|---------|-----------|
| CLIP-Bild-Encoder | `VDevice.create_infer_model()` | Hailo Model Zoo (S3) |
| YOLO-Objekterkennung | `VDevice.create_infer_model()` | Hailo Model Zoo (S3) |
| LLM-Chat | `hailo_platform.genai.LLM` | Hailo GenAI Model Zoo |
| VLM-Bild+Text-Inferenz | `hailo_platform.genai.VLM` | Hailo GenAI Model Zoo |
| Whisper-Spracherkennung | `hailo_platform.genai.Speech2Text` | Hailo GenAI Model Zoo |

### Nicht funktionierende Funktionen (HEF-Konvertierung fehlgeschlagen)

| Funktion | Versuchter Inhalt | Ergebnis |
|------|-----------|------|
| WD-Tagger (SwinV2) | ONNX → HEF-Konvertierung | DFC konnte LayerNormalization nicht verarbeiten |
| WD-Tagger (ViT) | ONNX → HEF-Konvertierung | Gleich |
| WD-Tagger (ConvNeXt) | ONNX → HEF-Konvertierung | DFC konnte Transpose-Operationen nicht verarbeiten |

### Bemerkenswerte Implementierungsaspekte

In diesem Projekt wurden alle Funktionen direkt über die Low-Level-API des `hailo_platform`-Wheels implementiert. hailo-ollama und hailo-apps wurden nicht verwendet.

Insbesondere folgende Elemente wurden vor der offiziellen Bereitstellung durch Hailo selbst entwickelt:

- **VDevice-Exklusivsteuerungsgerätemanager** — CLIP/YOLO/LLM/VLM/S2T auf einem einzigen VDevice automatisch umschalten. hailo-apps hat keinen Mechanismus für Device-Sharing
- **Multi-Backend-Fallback** — Transparenter automatischer Wechsel: Hailo → CoreML → ONNX Runtime
- **uint8-Dequantisierungspipeline** — float32 aus `quant_info` scale/zero_point wiederherstellen
- **LAN-verteilte Inferenzarchitektur** — Paralleles Tagging mit Work-Stealing über mehrere Maschinen

Diese Entwicklungen wurden **in einem Zustand praktisch fehlender API-Dokumentation** durchgeführt. Eingabe-/Ausgabespezifikationen der InferModel-API, Puffergrößenanforderungen und Methoden zum Abrufen von Quantisierungsparametern wurden alle aus Fehlermeldungen und Quellcode-Vermutungen erschlossen.

---

## Probleme mit dem Hailo Dataflow Compiler (DFC)

### Was ist DFC?

Ein Compiler zur Konvertierung von ONNX/TensorFlow-Modellen in das für Hailo-10H geeignete HEF (Hailo Executable Format). Läuft auf x86_64 Linux und konvertiert Modelle in folgendem Pipeline:

```
model.onnx → HAR (float32) → Optimierung → Quantisierung (INT8) → Kompilierung → model.hef
```

### Realität

**DFC kann nur Architekturen korrekt konvertieren, die Hailo intern für seinen Model Zoo vorvalidiert hat.**

Konvertierungsversuche in diesem Projekt (2026-03-06, DFC v5.2.0):

| Modell | Größe | Fehler | Erreichter Schritt |
|--------|-------|--------|---------|
| wd-swinv2-tagger-v3 | 446 MB | `IndexError` in `_convert_axes_to_nhwc` | Vor Optimierung |
| wd-vit-tagger-v3 | 362 MB | Gleich | Vor Optimierung |
| wd-convnext-tagger-v3 | 377 MB | `UnsupportedShuffleLayerError` | Vor Optimierung |

Alle 3 Modelle schlugen **vor der Optimierungsphase** auf Parser-Ebene fehl. 500 Kalibrierungsbilder wurden vorbereitet, wurden aber nie verwendet.

### Grundlegende Ursache

Der ONNX-Parser des DFC kann folgende Operatoren nicht verarbeiten:

- `LayerNormalization` (Achsentransformation bei mehrdimensionalen Tensoren)
- `Transpose` (channels-last/first-Konvertierungsmuster)

Dies sind grundlegende Bausteine von Transformer-Architekturen (SwinV2, ViT, ConvNeXt usw.) und werden von der großen Mehrheit der Modelle seit 2022 verwendet.

### Tatsächlicher DFC-Unterstützungsbereich

| Architektur | DFC-Unterstützung | Grundlage |
|---------------|---------|------|
| ResNet, MobileNet, CNN-Serie | ✓ Unterstützt | Viele im Model Zoo |
| YOLO v5/v8/v11 | ✓ Unterstützt | HEFs im Model Zoo |
| CLIP ViT (Hailo-Version) | ✓ Unterstützt | HEF im Model Zoo (von Hailo konvertiert) |
| SwinTransformer V2 | ✗ Nicht unterstützt | LayerNorm-Konvertierung fehlgeschlagen |
| Vision Transformer (generisch) | ✗ Nicht unterstützt | LayerNorm-Konvertierung fehlgeschlagen |
| ConvNeXt | ✗ Nicht unterstützt | Transpose-Konvertierung fehlgeschlagen |

> **Hinweis**: CLIP ViT ist im Model Zoo, weil Hailo intern spezielle Behandlung (manuelle Graph-Konvertierung oder benutzerdefinierter Parser) angewendet hat. Das gleiche ViT schlägt bei regulären Benutzern mit DFC fehl.

---

## Probleme mit dem HEF-Format

- **Binärspezifikation nicht öffentlich** — Hailo veröffentlicht keine Formatdokumentation
- **Keine anderen Generierungsmethoden als DFC** — Drittanbieter-Tools können keine HEFs erstellen
- **Reverse Engineering auch unpraktisch** — Kenntnisse über NPU-Befehlssatz und Datenflusarchitektur erforderlich

Kurz gesagt: Modelle, die DFC nicht konvertieren kann, **können auf keine Weise auf Hailo-10H ausgeführt werden**. Keine Alternativen existieren.

---

## Bewertung der Entwicklungs-Toolchain

### hailo_platform (Python SDK)

| Element | Bewertung |
|------|------|
| InferModel-API | Funktioniert, aber extrem wenig dokumentiert |
| GenAI-API (LLM/VLM/S2T) | Relativ benutzerfreundlich. Aber viele undokumentierte Verhaltensweisen |
| Python-Wheel-Verteilung | Nicht auf PyPI. aarch64-Wheel muss aus Quellen gebaut werden |
| Fehlermeldungen | Minimal. Schwierig, Ursachen für Puffergrößen-Mismatches zu identifizieren |
| VDevice-Verwaltung | Nur exklusiver Zugriff. Gleichzeitige Nutzung mehrerer Modelle nicht möglich |

### Im Entwicklungsprozess aufgedeckte undokumentierte Verhaltensweisen

1. **InferModel-API ist korrekt** — Die alte VStreams-API (`InferVStreams`, `ConfigureParams.create_from_hef`) gibt `HAILO_NOT_IMPLEMENTED` auf Hailo-10H zurück
2. **Ausgabe ist uint8-quantisiert** — Bei float32-Puffer tritt `buffer size mismatch` auf. uint8 allozieren und danach dequantisieren
3. **`input()`/`output()` sind Eigenschaften** — Keine Methoden (inkonsistent mit anderen Hailo-APIs)
4. **`quant_info`-Abruf** — scale/zero_point über `infer_model.output().quant_info` abrufbar, aber kein Dokument erklärt dies
5. **Exklusivität mit hailo-ollama** — VDevice bei laufendem hailo-ollama anhalten. Fehlermeldungen zeigen nicht klar die Ursache

---

## Vergleich mit Konkurrenzprodukten

### Ryzen AI (XDNA) NPU

| Element | Hailo-10H | Ryzen AI (XDNA) |
|------|----------|-----------------|
| Leistung | 40 TOPS | 16–50 TOPS (je nach Generation) |
| Modell-Import | DFC-Konvertierung erforderlich, scheitert meist | **ONNX Runtime direkt unterstützt** |
| Entwicklererfahrung | Proprietäre Toolchain, wenig Dokumentation | Fertig mit `pip install onnxruntime-directml` |
| Ökosystem | Geschlossen, abhängig vom Model Zoo | ONNX / DirectML / Microsoft-Zusammenarbeit |
| Marktdurchdringung | Pi + AI HAT, USB-Dongle (geplant) | **Millionen von Notebooks bereits eingebaut** |

Ryzen AI-Integration lässt sich auf dieses reduzieren:

```python
import onnxruntime as ort
session = ort.InferenceSession("model.onnx", providers=["DmlExecutionProvider"])
```

Das Gleiche ist mit Hailo-10H nicht möglich. ONNX Runtime Execution Provider existiert nicht.

### NVIDIA CUDA

| Element | Hailo-10H | NVIDIA CUDA |
|------|----------|-------------|
| Modell-Import | Über DFC, außerhalb Model Zoo meist fehlgeschlagen | ONNX / PyTorch / TensorFlow → direkt |
| Toolchain | Unreif, halb-offen | Ausgereift, offen, reichlich Dokumentation |
| Entwickler-Community | Minimal | Weltweit größte |
| Preisklasse | Günstig (ca. 70 $) | Teuer (200–2000+ $) |

Hailos einziger Vorteil ist **Preis und Stromverbrauch**.

---

## Beziehung zu hailo-apps (2025-10)

### Überblick über hailo-apps

Offizielle Anwendungssammlung, die Hailo im Oktober 2025 veröffentlichte. Enthält 20+ Beispielanwendungen:

- GenAI: voice_assistant, vlm_chat, agent_tools_example, whisper
- Pipeline: Objekterkennung, Pose-Estimation, Gesichtserkennung, CLIP-Klassifizierung, OCR
- Standalone: HailoRT-Lerndemonstrations für Python/C++

### Vergleich mit diesem Projekt

| Element | hailo-apps | Dieses Projekt |
|------|-----------|-------------|
| VLM-Unterstützung | vlm_chat-App | `hailo_platform.genai.VLM` direkt implementiert |
| CLIP | CLIP-App | Als semantisches Suchsystem integriert |
| LLM | simple_llm_chat | Als GenAI-Extension integriert |
| Whisper | simple_whisper_chat | Als Speech-to-Text-Extension integriert |
| Geräteverwaltung | Keine (setzt einzelne App voraus) | **Exklusivsteuerungsgerätemanager (CLIP/YOLO/LLM/VLM/S2T automatisch umschaltend)** |
| Backend-Fallback | Keiner | **Hailo → CoreML → ONNX automatisch umschaltend** |
| Verteilte Inferenz | Keine | **LAN-verteiltes Work-Stealing** |
| Integrationsgrad | Einzelne Demo-Apps | Einzelne integrierte WebUI-Anwendung |

---

## Ausblick

### Kurzfristig (realistisch)

- **ONNX Runtime + LAN-Verteilung ist die einzige praktische Lösung** — Mit ONNX-Backend des verteilten Tagger-Servers betreiben
- Hailo-10H auf Anwendungsfälle mit offiziellen HEFs beschränken (YOLO, CLIP, LLM, Whisper)
- NPU-Ausführung benutzerdefinierter Modelle aufgeben

### Mittelfristig (hoffnungsvoll)

- ASUS und andere werden Hailo-10H USB-Dongles auf den Markt bringen → mehr Benutzer
- Mit mehr Benutzern könnte Druck auf Hailo entstehen, Tools zu verbessern
- Zukünftige DFC-Versionen könnten Transformer-Unterstützung hinzufügen

### Langfristig (strukturelle Herausforderungen)

- Wenn Hailo keinen ONNX Runtime EP bereitstellt, verlieren sie beim Entwicklerökosystem gegen Ryzen AI (XDNA)
- Selbst wenn sich die Hardware durch USB-Dongles verbreitet, ist 40 TOPS-Potenzial auf Dutzende Model-Zoo-Modelle beschränkt

---

## Zusammenfassung

Hailo-10H hat ausgezeichnete Hardware mit 40 TOPS, aber aufgrund der Geschlossenheit und Unreife des Software-Ökosystems ist es für Entwickler **praktisch unmöglich**, eigene Modelle frei einzusetzen.

In diesem Projekt wurden durch schrittweises Aufdecken undokumentierter APIs integrierte Software entwickelt, die über Hailos eigene Anwendungssammlung (hailo-apps) hinausgeht. Trotzdem konnte die NPU-Ausführung von Custom Models (WD-Tagger) aufgrund der DFC-Einschränkungen nicht realisiert werden.

**"Die Tools sind so unzulänglich, dass Entwicklung praktisch nicht möglich ist"** — Das ist das ehrliche Fazit nach Monaten der Hailo-10H-Entwicklung.

---

## Verwandte Dokumente

- [`HAILO_SEMANTIC_SEARCH_DEVLOG.md`](./HAILO_SEMANTIC_SEARCH_DEVLOG.md) — Entwicklungsprotokoll der CLIP-semantischen Suche (Phase 1-12+)
- [`ONNX_TO_HEF_CONVERSION_GUIDE.md`](./ONNX_TO_HEF_CONVERSION_GUIDE.md) — DFC-Konvertierungsleitfaden (Referenz)
- [`ONNX_TO_HEF_CONVERSION_REPORT.md`](./ONNX_TO_HEF_CONVERSION_REPORT.md) — WD-Tagger-Konvertierungsfehlerbericht
- [`CLIP_ONNX_DEVLOG.md`](./CLIP_ONNX_DEVLOG.md) — CLIP ONNX-Fallback-Entwicklungsprotokoll
- [`HAILO_DEVICE_CONTROL.md`](./HAILO_DEVICE_CONTROL.md) — VDevice-Geräteverwaltungsdesign
- [`../features/distributed-tagger-server.md`](../features/distributed-tagger-server.md) — Dokumentation des verteilten Tagger-Servers
