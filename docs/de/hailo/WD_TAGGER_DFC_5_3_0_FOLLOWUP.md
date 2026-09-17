# DFC-Konvertierungs-Nachbericht: WD-Tagger-Modelle mit DFC v5.3.0 erneut verifiziert

**Datum**: 2026-04-06
**DFC-Version**: 5.3.0
**Vorheriger Bericht**: [`ONNX_TO_HEF_CONVERSION_REPORT.md`](ONNX_TO_HEF_CONVERSION_REPORT.md) (2026-03-06)
**Umgebung**: WSL2 (Ubuntu 24.04), x86_64

---

## Hintergrund

Im März 2026 wurde berichtet, dass alle drei WD-Tagger-Varianten (SwinV2, ViT, ConvNeXt) in der Parser-Phase von Hailo Dataflow Compiler v5.2.0 fehlschlugen und den Quantisierungsschritt nicht erreichten. Der ursprüngliche Bericht ist in [`ONNX_TO_HEF_CONVERSION_REPORT.md`](ONNX_TO_HEF_CONVERSION_REPORT.md) gespeichert.

Da DFC v5.3.0 veröffentlicht wurde, wurden dieselben 3 Modelle erneut verifiziert. Die Ergebnisse werden hier dokumentiert.

---

## Ergebnis-Zusammenfassung

| Modell | Größe | DFC 5.2.0-Fehler | DFC 5.3.0-Fehler | Änderung |
|---|---|---|---|---|
| `wd-swinv2-tagger-v3` | 446 MB | `_convert_axes_to_nhwc` → `IndexError` | Identisch | **Keine** |
| `wd-vit-tagger-v3` | 362 MB | Gleich | Identisch (auch nach onnxsim-Retry) | Nur Retry-Fluss hinzugefügt |
| `wd-convnext-tagger-v3` | 377 MB | `UnsupportedShuffleLayerError` | Gleich + zusätzlicher `UnsupportedModelError` | **Fehler nahmen zu** |

**Alle 3 Modelle schlagen immer noch in der Parser-Phase fehl**. Die 500 vorbereiteten Kalibrierungsbilder können wie bei v5.2.0 nicht verwendet werden.

---

## Was sich in DFC v5.3.0 geändert hat

Die Fehler bestehen weiterhin, aber im Vergleich zu v5.2.0 sind folgende Verbesserungen sichtbar:

### 1. Neue Methode `_create_layer_normalization_layer`

Diese Methode existierte in v5.2.0 nicht. DFC v5.3.0 versucht nun, den `LayerNormalization`-Operator in einem dedizierten Code-Pfad explizit zu behandeln. Dies ist definitiv ein Beweis für laufende Entwicklungsarbeit.

Die **interne Implementierung ist jedoch noch unvollständig** — nach dem Aufruf der Methode gibt der `_convert_axes_to_nhwc`-Aufruf immer noch `IndexError: list index out of range` für dieselben Tensor-Shapes wie in v5.2.0.

### 2. Hinzugefügter onnxsim-Vereinfachungs- + Retry-Fluss

Für ViT und ConvNeXt vereinfacht DFC v5.3.0 jetzt automatisch die eingegebene ONNX mit `onnxsim` und wiederholt das Parsen. Das vereinfachte Modell wird als `model.sim.onnx` neben der Eingabedatei gespeichert. Ein nützliches Sicherheitsnetz für Modelle mit redundanten ONNX-Graphen.

Da die Grundursache jedoch auf der `_convert_axes_to_nhwc`-Seite liegt, **schlägt der Retry an genau derselben Stelle fehl**.

### 3. End-Knoten-Empfehlungsfunktion

Für ConvNeXt empfiehlt DFC v5.3.0 jetzt spezifische End-Knoten und fordert den Benutzer auf, diese anzupinnen und erneut zu versuchen. Eine nette UX-Verbesserung.

Der Retry mit empfohlenen End-Knoten schlägt ebenfalls fehl, da die Grundursache beim LayerNormalization/Transpose-Handling liegt, nicht bei der End-Knoten-Auswahl.

---

## Grundursache (unverändert seit März)

Der DFC ONNX-Parser schlägt weiterhin bei der Achsentransformation, wenn die Eingabe-Tensoren des `LayerNormalization`-Operators nicht dem erwarteten NCHW-Format folgen. Die Aufrufkette ist:

```
_create_layer_normalization_layer
  → get_layer_normalization_info
    → _convert_axes_to_nhwc
      → IndexError: list index out of range
```

Für ConvNeXt gibt es zusätzlich `UnsupportedShuffleLayerError` bei mehreren `Transpose`-Nodes (`token_5` bis `token_34`), was die Unvollständigkeit der Transpose-Behandlung für das von dieser Architektur verwendete channels-last-Muster anzeigt.

Kurz gesagt: **Neue Code-Pfade existieren, aber die ursprünglich fehlgeschlagenen Fälle können noch nicht verarbeitet werden**.

---

## Anfragen (unverändert seit März)

Die zwei Anfragen aus dem März-Beitrag bestehen weiterhin:

### 1. `_convert_axes_to_nhwc` für mehrdimensionale `LayerNormalization` reparieren

Bis zum Methodenaufruf kann jetzt erreicht werden (Verbesserung). Aber die Achsen-Mapping-Logik selbst schlägt bei Nicht-NCHW-Eingabe-Tensoren fehl.
SwinV2, ViT, ConvNeXt und andere moderne Transformer-Architekturen sind alle davon abhängig, dass dies korrekt funktioniert.

### 2. ONNX Runtime Execution Provider für Hailo-10H

Dieser würde DFC-vollständige Konvertierung optional machen und diese Klasse von Problemen strukturell lösen. Viele Community-Benutzer würden ONNX-Modelle direkt auf Hailo-10H ausführen wollen, auch bei geringerem Durchsatz als ein vollständig quantisiertes HEF.

---

## Über die "ONNX Runtime Hailo Pipeline"-Komponente

Die DFC v5.3.0-Versionshinweise erwähnen eine "ONNX Runtime Hailo Pipeline"-Komponente. Wenn diese Komponente WD-Tagger-Inferenz auf Hailo-10H **ohne vollständige DFC-Konvertierung** ermöglicht (d.h. als ORT-Execution-Provider, der nur unterstützte Untergraphen an NPU delegiert), wären offizielle Anleitungen sehr hilfreich.

Spezifische Fragen:
- Ist diese Komponente als Vorwärts-Pfad für Modelle gedacht, die DFC derzeit nicht parsen kann?
- Wird eine partielle HEF benötigt (parsbarer Untergraph zu HEF kompiliert, Rest über ORT auf CPU)?
- Gibt es Beispielcode oder Tutorials für Transformer-ONNX-Modelle?

---

## Reproduktionsschritte

```bash
# 1. Saubere Python-venv mit DFC v5.3.0 einrichten
python3.11 -m venv venv
source venv/bin/activate
pip install hailo_dataflow_compiler-5.3.0-py3-none-linux_x86_64.whl

# 2. Alle drei WD-Tagger-ONNX-Modelle herunterladen
for variant in swinv2 vit convnext; do
  huggingface-cli download \
    "SmilingWolf/wd-${variant}-tagger-v3" \
    model.onnx --local-dir "./wd-${variant}-tagger-v3"
done

# 3. Für jedes Modell Parsen versuchen
for variant in swinv2 vit convnext; do
  hailo parser onnx "./wd-${variant}-tagger-v3/model.onnx" \
    --hw-arch hailo10h \
    --tensor-shapes input_1:1,448,448,3 2>&1 | tee "${variant}_5.3.0.log"
done
```

Vollständige Fehler-Logs auf Anfrage verfügbar.

---

## Testumgebung

| Element | Details |
|---|---|
| OS | Ubuntu 24.04 (WSL2) |
| CPU | AMD Ryzen 5 5600X |
| RAM | 151 GB |
| Python | 3.11 |
| DFC | 5.3.0 |
| Modelle | `SmilingWolf/wd-{swinv2,vit,convnext}-tagger-v3` (HuggingFace) |
| Kalibrierungsdaten | 500 ComfyUI / SD-Ausgaben (Quantisierung nicht erreicht, nicht verwendet) |

---

## Fazit

Die in DFC v5.3.0 sichtbaren Entwicklungsanstrengungen (`_create_layer_normalization_layer`, onnxsim-Retry-Fluss, End-Knoten-Empfehlungen) sind wirklich ermutigend — genau der Fortschritt, den die Community erwartet hat. Die verbleibende Lücke ist die Implementierung des Inhalts von `_convert_axes_to_nhwc`, die jetzt erreichbar ist, aber für diese Modelle noch nicht korrekt funktioniert.

Erneute Verifizierung bei jedem DFC-Release fortsetzen und bei Statusänderungen Folgeberichte veröffentlichen. Wenn Hailo-Mitarbeiter dies lesen und vollständige Fehler-Logs, SHA-256-Hashes der ONNX-Modelle oder minimalen Reproduktionscode benötigen, werden diese gerne bereitgestellt.
