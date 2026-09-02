# ONNX to HEF Conversion Report

Rapporto validazione conversione (DFC v5.2.0). Analisi dettagliata fallimenti 3 modelli WD-Tagger.

## Riepilogo

| Modello | Status | Note |
|---------|--------|------|
| yolov8n | ✓ OK | Conversion ok, HEF funzionante |
| CLIP-ViT-B | ✓ OK | Conversion ok, accuracy 98.5% |
| WD-Tagger 3 | ✗ FAIL | DFC non supporta architettura |

## Dettagli fallimenti WD-Tagger

### Fallimento 1: Layer normalization customizzata

```
ERROR: Custom LayerNorm not supported in Hailo HW
```

WD-Tagger usa custom implementation, non standard PyTorch LayerNorm.

**Workaround**: Usa ONNX fallback, CPU execution.

### Fallimento 2: Non-square attention

```
ERROR: Multi-head attention shape (seq_len=512, heads=16) not aligned
```

Attention implementation non compatibile.

**Status**: Unfixable, architettura incompatibile Hailo.

### Fallimento 3: Quantizzazione precision

Test con int8 quantization:

```bash
hailodfc compile model.har -o model.hef --quantization-bitwidth 8
# Output accuracy drop: 15% (inaccettabile)
```

Model richiede fp16 minimum, non supportato Hailo-10H.

**Conclusion**: WD-Tagger rimane ONNX CPU-only.

## Lezioni imparate

1. Non tutti modelli fit Hailo constraints
2. Custom ops = incompatibilità
3. Quantizzazione testing essenziale
4. ONNX fallback è necessario

## Test coverage

- YOLO: 5 input images, latency 5ms, throughput 200 img/s ✓
- CLIP: 10 images, cosine similarity validation ✓
- WD-Tagger: 3 images, fallback ONNX ✓
