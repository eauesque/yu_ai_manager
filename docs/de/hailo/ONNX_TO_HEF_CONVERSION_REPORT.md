# ONNX zu HEF Konvertierungsbericht

**Durchführungsdatum**: 2026-03-06
**Zweck**: WD-Tagger ONNX-Modelle in das Hailo-HEF-Format konvertieren und auf Raspberry Pi 5 + AI HAT 2 (Hailo-10H) inferenzfähig machen
**Ergebnis**: Fehlgeschlagen (Konvertierung für alle Modell-Varianten nicht möglich)

---

## Umgebung

| Element | Details |
|------|------|
| OS | Ubuntu 24.04 (WSL2) |
| Python | 3.11.13 (via uv installiert) |
| Hailo Dataflow Compiler | v5.2.0 |
| GPU | CUDA 12.8, Treiber 591 |
| RAM | 151GB |

---

## Getestete Modelle

### 1. wd-swinv2-tagger-v3 (SwinTransformer V2)

- **Quelle**: `SmilingWolf/wd-swinv2-tagger-v3` (446MB)
- **Eingabe**: `[batch, 448, 448, 3]` float32
- **Ausgabe**: `[batch, 10861]` float32
- **Ergebnis**: Fehlgeschlagen
- **Fehler**: `IndexError: list index out of range` in `_convert_axes_to_nhwc`
- **Ursache**: Achsentransformation von LayerNormalization in DFC v5.2.0 nicht unterstützt

### 2. wd-vit-tagger-v3 (Vision Transformer)

- **Quelle**: `SmilingWolf/wd-vit-tagger-v3` (362MB)
- **Eingabe**: `[batch, 448, 448, 3]` float32
- **Ausgabe**: `[batch, 10861]` float32
- **Ergebnis**: Fehlgeschlagen
- **Fehler**: Gleich (`IndexError` in `_convert_axes_to_nhwc`)
- **Ursache**: ViT verwendet ebenfalls LayerNormalization, scheitert an derselben Stelle

### 3. wd-convnext-tagger-v3 (ConvNeXt)

- **Quelle**: `SmilingWolf/wd-convnext-tagger-v3` (377MB)
- **Eingabe**: `[batch, 448, 448, 3]` float32
- **Ausgabe**: `[batch, 10861]` float32
- **Ergebnis**: Fehlgeschlagen
- **Fehler**: `UnsupportedShuffleLayerError` (zahlreiche Transpose-Nodes) + `UnsupportedModelError` (Mul-Shape-Mismatch)
- **Ursache**: Transpose-Operationen für ConvNeXts channels-last-Design von DFC nicht unterstützt

---

## Grundlegende Fehlerursache

Der ONNX-Parser von DFC v5.2.0 kann folgende Operationen nicht korrekt verarbeiten:

1. **LayerNormalization**: Indexfehler bei NHWC-Achsentransformation von LayerNorm auf dreidimensionalen+ Tensoren
2. **Transpose (Shuffle)**: Transpose-Muster für channels-last/first-Konvertierung in ConvNeXt nicht unterstützt

Alle WD-Tagger-Varianten (SwinV2, ViT, ConvNeXt) sind moderne Architekturen, die LayerNormalization extensiv verwenden, und können in DFC v5.2.0 nicht konvertiert werden.

---

## Kalibrierungsdaten

- 500 Zufallsbilder aus ComfyUI / Stable Diffusion forge-Ausgaben ausgewählt
- Gleiche Vorverarbeitung wie WD-Tagger angewendet (RGBA→RGB weißer Hintergrund, Seitenverhältnis-Resize, weißes Padding, BGR-Konvertierung)
- Als `calibration_data.npy` gespeichert, wurde aber nicht verwendet da der Konvertierungsschritt nicht erreicht wurde

---

## Zukünftige Möglichkeiten

- **Zukünftige DFC-Versionen**: Bei Verbesserung der LayerNormalization/Transpose-Unterstützung durch Hailo erneut versuchen
- **Modellmodifikation**: Modifiziertes Modell mit durch BatchNorm ersetztem LayerNorm erstellen (hoher Aufwand, Genauigkeitsverlustrisiko)
- **Status quo beibehalten**: Weiterhin Inferenz mit ONNX Runtime (CPU) betreiben
