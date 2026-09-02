# CLIP ONNX Multi-Backend Dev Log

Registro sviluppo CLIP ONNX multi-backend. Fallback per ambienti senza hardware Hailo.

## Background

CLIP embedding per ricerca semantica. Implementazione:
1. Hailo HW accelerated (Raspberry Pi 5)
2. ONNX CPU fallback (notebook senza GPU)
3. HuggingFace remote (cloud)

## Implementazione

```python
class CLIPBackend:
    @staticmethod
    def auto_select():
        """Select best backend available"""
        if hailo_available():
            return HailoBackend()
        elif onnx_available():
            return ONNXBackend()
        else:
            return RemoteBackend()

class HailoBackend:
    def embed(self, image):
        # Hailo inference
        pass

class ONNXBackend:
    def __init__(self):
        self.session = ort.InferenceSession('clip-onnx.onnx')
    
    def embed(self, image):
        # ONNX CPU inference
        input_name = self.session.get_inputs()[0].name
        output = self.session.run(None, {input_name: image})
        return output[0]

class RemoteBackend:
    async def embed(self, image):
        # Call remote API
        pass
```

## Benchmark

| Backend | Image | Latency | Cost |
|---------|-------|---------|------|
| Hailo | 224x224 | 5ms | No |
| ONNX | 224x224 | 120ms | CPU |
| Remote | any | 200ms+ | API quota |

## Fallback strategy

```python
try:
    backend = HailoBackend()
except HailoError:
    logger.warning("Hailo unavailable, using ONNX")
    backend = ONNXBackend()
except:
    logger.error("No local backend, using remote")
    backend = RemoteBackend()
```

## Testing

```bash
pytest tests/clip_onnx_test.py
# Verifica tutti backend
```

## Known issues

- ONNX memory usage alto per batch
- Quantizzazione ONNX degrada qualità
- Remote API latency unpredictable
