# Documentación de desarrollo de Hailo-10H AI Hat+

Registros de implementación de inferencia de AI utilizando Raspberry Pi 5 + Hailo AI Hat+ (Hailo-10H).

Se hace pública información adquirida en desarrollo real sobre áreas donde la documentación oficial es insuficiente.

## Lista de documentos

| Archivo | Contenido |
|---------|----------|
| [HAILORT_5_3_0_MIGRATION.md](HAILORT_5_3_0_MIGRATION.md) | Notas de migración HailoRT 5.2.0 → 5.3.0. Diferencias de API, renombre de nodo de dispositivo (`/dev/h1x-0`), compatibilidad HEF, script de prueba |
| [VDEVICE_SHARING_PATTERN.md](VDEVICE_SHARING_PATTERN.md) | Patrón de implementación de administrador de VDevice compartido para coexistir múltiples modelos (YOLO/CLIP/LLM/VLM/Whisper) en mismo proceso |
| [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md) | Limitación de asignación CMA de Pi 5 (comportamiento bajo `numa=fake=8`). Por qué `cma=1G` falla silenciosamente, `cma-512` (`dtoverlay=cma,cma-512` en `config.txt`) como límite verificado y valor recomendado, los requisitos de memoria de Hailo GenAI, el comportamiento de no devolución de CMA de `VDevice.release()` |
| [HAILO_SEMANTIC_SEARCH_DEVLOG.md](HAILO_SEMANTIC_SEARCH_DEVLOG.md) | Registro de desarrollo de búsqueda semántica CLIP. Registro de implementación por fase, problemas encontrados y soluciones |
| [HAILO_DEVICE_CONTROL.md](HAILO_DEVICE_CONTROL.md) | Método de control de dispositivo Hailo, gestión de VDevice, control de exclusión, conmutación de modelos |
| [ONNX_TO_HEF_CONVERSION_GUIDE.md](ONNX_TO_HEF_CONVERSION_GUIDE.md) | Procedimiento de conversión ONNX → HEF. Dataflow Compiler, cuantización, solución de problemas |
| [ONNX_TO_HEF_CONVERSION_REPORT.md](ONNX_TO_HEF_CONVERSION_REPORT.md) | Informe de validación de conversión (DFC v5.2.0). Análisis detallado de fallo de 3 modelos de WD-Tagger |
| [WD_TAGGER_DFC_5_3_0_FOLLOWUP.md](WD_TAGGER_DFC_5_3_0_FOLLOWUP.md) | Actualización DFC v5.3.0. Revalidación del mismo modelo WD-Tagger 3 (fallo persistente), además mejoras confirmadas en v5.3.0 (nuevo `_create_layer_normalization_layer`, flujo de reintento onnxsim, recomendación end-node) |
| [CLIP_ONNX_DEVLOG.md](CLIP_ONNX_DEVLOG.md) | Registro de desarrollo CLIP ONNX multi-backend. Fallback para entorno sin hardware Hailo |
| [HAILO_CMA_LEAK_HAILORT_5_3_0.md](HAILO_CMA_LEAK_HAILORT_5_3_0.md) | **Restricción estructural de la fuga de CMA y medición real**. `VDevice.release()` no la recupera, fuga continua durante la inferencia (aprox. 14 MB/min), y **no se recupera ni con kill del proceso hijo, ni con salida del proceso, ni con descarga del módulo** (medido de forma independiente 2 veces en el PoC de la Fase 0, solo +8 MB tras SIGTERM + 30 s de espera). El único medio de recuperación seguro es el reinicio del propio Pi **(conclusión antigua. Corregida en [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) §8 mediante la reprueba con HailoRT / driver 5.4.0)** |
| [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) | **Corrección y reverificación del veredicto de fuga de CMA anterior**. Se comparó en A/B la versión oficial vanilla y la versión corregida con `FOLL_LONGTERM` de HailoRT / driver 5.4.0, y se corrigió el veredicto anterior — que solo consideraba la cantidad de recuperación absoluta de `CmaFree` tras la primera carga del HEF — como un veredicto erróneo. Incluye la diferencia de código fuente v5.3.0 → v5.4.0, las trampas del procedimiento de compilación propia y datos de medición real |
| [HAILO_AUTO_REBOOT_PHASE05.md](HAILO_AUTO_REBOOT_PHASE05.md) | Guía operativa de la vía de reinicio automático adoptada a raíz de lo anterior. Fase de observación (solo registra `would_fire` sin reiniciar), umbrales de decisión, motivo del `mode = "off"` predeterminado |
| [HAILO_AUTO_REBOOT_PHASE05_RUNBOOK.md](HAILO_AUTO_REBOOT_PHASE05_RUNBOOK.md) | Manual de operaciones (runbook) de la misma fase para este entorno. Procedimientos de inicio, verificación y finalización de la observación |
| [HAILO_LLM_SUBPROCESS_DEVLOG.md](HAILO_LLM_SUBPROCESS_DEVLOG.md) | Registro de implementación que resolvió el bloqueo del event loop de Quart por el GIL durante cold_load (~71 s), mediante el aislamiento en subprocess de la inferencia de chat LLM |
| [HAILO_10H_ECOSYSTEM_ASSESSMENT.md](HAILO_10H_ECOSYSTEM_ASSESSMENT.md) | Evaluación del ecosistema Hailo-10H (2026-03-19, a fecha de HailoRT/DFC v5.2.0) |

## Puntos conocidos importantes

### Entorno / Raspberry Pi 5

- **El límite de CMA en Pi 5 (8 GB) es 512 MB, y se configura en `config.txt`**: El kernel predeterminado aplica `numa=fake=8`, dividiendo la RAM en 8 nodos NUMA de 1 GB. CMA debe caber dentro del límite de un único nodo, y `cma-1024` y `cma-768` fallan silenciosamente (`CmaTotal=0` sin pánico de kernel). **`cma-512` es el límite verificado y el valor recomendado** (revalidado el 2026-05-16 mediante overlay, `CmaTotal: 524288 kB`). Debido a una regresión de firmware de 2026-05, use `dtoverlay=cma,cma-512` en `/boot/firmware/config.txt` en lugar del parámetro de arranque `cma=`. Para más detalles, consulte [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md)
- **Siempre verifique CMA después de reboot**: Confirme con `grep CmaTotal /proc/meminfo`. Si es 0, configuración fue ignorada
- **`VDevice.release()` no devuelve el CMA**: El CMA se mantiene durante toda la sesión del SO. Trate VDevice como un singleton de ámbito de sesión. **Tampoco se recupera con el reinicio del proceso** —— se ha medido de forma independiente en dos ocasiones en el PoC de la Fase 0 que no se recupera ni con el kill del proceso hijo, ni con la salida del proceso, ni con la descarga del módulo (solo +8 MB tras SIGTERM + 30 s de espera, frente a un valor esperado ≥250 MB). El único medio de recuperación seguro es el `sudo reboot` (ciclo de energía PCIe) del propio Pi. Para más detalles y la solución adoptada, consulte [HAILO_CMA_LEAK_HAILORT_5_3_0.md](HAILO_CMA_LEAK_HAILORT_5_3_0.md). **Corrección**: este punto se basa en una medición antigua. En la reprueba A/B con HailoRT / driver 5.4.0 no se reprodujo una fuga de CMA con efecto práctico, corregido en [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) §8
- **`numa=fake=8` afecta instalación de Node.js**: Memoria por nodo NUMA (1 GB) confundida con RAM total, instalador npm/node aborta. Reportado upstream: [anthropics/claude-code#33864](https://github.com/anthropics/claude-code/issues/33864)
- **Python wheel requiere compilación desde fuente**: Sin wheel aarch64 en PyPI o Hailo Developer Zone
- **Exclusión con hailo-ollama**: Detener hailo-ollama mientras usa VDevice
- **Fuga de VDevice al salir de proceso**: Confirmar con `lsof /dev/hailo*`, resolver con `kill PID`

### VDevice / API

- **Usar InferModel API**: `VDevice.create_infer_model()` es correcto. API VStreams antigua (`InferVStreams`, `ConfigureParams.create_from_hef`) retorna `HAILO_NOT_IMPLEMENTED` en Hailo-10H
- **InferModel soporta solo modelos simples**: HEF YOLO de 1 entrada funciona, pero HEF Whisper de 2 entrada/4 salida retorna `HAILO_INVALID_ARGUMENT` en `configure()`. Usar GenAI SDK para modelos complejos
- **VDevice mapea a 1 dispositivo físico**: Crear 2 instancias de `VDevice()` simultáneamente retorna `HAILO_OUT_OF_PHYSICAL_DEVICES(74)`
- **Liberar completamente VDevice al cambiar modelo**: Establecer referencia Python a `None` es insuficiente. Liberar explícitamente dispositivo físico con `VDevice.release()` antes crear VDevice nuevo
- **`set_format_type(FormatType.FLOAT32)` no soportado en hailort 5.2.0**: Atributo `format_type` no existe. Realizar cuantización/descuantización uint8 manualmente o usar GenAI SDK
- **Salida cuantizada uint8**: Asignar buffer de salida como float32 causa `buffer size mismatch`. Asignar como uint8, convertir float32 con parámetros de descuantización (scale, zero_point)

### GenAI (LLM / VLM / Speech2Text)

- **HailoRT 5.3.0 rechaza `temperature=0.0`**: `LLM.generate()` genera `HAILO_INVALID_ARGUMENT` con `temperature=0`. Abreviar antes llamada: `temperature = max(temperature, 0.01)`. Afecta clientes compatibles OpenAI que envían `temperature=0` por defecto
- **Carga simultánea de 2× GenAI posible**: LLM + Whisper-tiny pueden cargarse simultáneamente en VDevice (confirmado HailoRT 5.3.0). Margen CMA después cargar ambos: aprox. 10 MB de 256 MB. Whisper-base+ probable desbordamiento de memoria
- **Presupuesto CMA LLM + Whisper-tiny**: Aprox. 246 MB total (medido). Valores CMA de todos modelos en [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md)

### Whisper (reconocimiento de voz)

- **Usar GenAI SDK**: `hailo_platform.genai.Speech2Text` proporciona canalización completa. Ejecutar codificador+decodificador completamente en NPU
- **HEF solo decodificador**: `Whisper-Base.hef` es 2 entrada (encoder_features + token_embeddings) 4 salida (vocab dividido en 4). No funciona con InferModel API
- **Entrada de GenAI SDK**: Datos PCM audio float32 little-endian (`<f4`), normalización [-1,1]
- **Fallback ONNX**: Si GenAI SDK no disponible, ejecutar codificador+decodificador CPU con modelo ONNX HuggingFace

### YOLO (detección de objetos)

- **Funciona con InferModel API**: HEF de 1 entrada sin problemas
- **Fallback ONNX**: Si Hailo no disponible, descargar automáticamente `yolo11n.onnx`. Salida `(1,84,8400)` compatible yolov8n
- **Enfriamiento tras fallo inicialización**: No reintentar 60 segundos después fallo inicialización motor

### Inferencia distribuida

- **Verificación de salud obligatoria**: Confirmar vida/muerte nodo remoto con `filter_available()` antes comenzar distribución
- **Fallo remoto**: Fallback automático items restantes localmente. Detección automática en próximo lote al recuperarse
- **Distribución de carga**: Gran diferencia velocidad GPU vs NPU, división uniforme ineficiente. Distribución dinámica basada medición throughput es desafío futuro
