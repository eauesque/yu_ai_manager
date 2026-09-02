# Matriz de inferencia distribuida

**Versión**: v4.67.0 o posterior

## Descripción general

Página `/mesh-inference` permite cambiar habilitación/deshabilitación por tipo inferencia para cada peer en mesh inference. Objetivos son tagger, clip, yolo, whisper (4 tipos).

Esto permite, sin editar config, asignar roles como dedicar NPU Hailo Pi5 solo a tagger, procesar clip en host GPU.

## Uso

1. Hacer clic "🕸️ Inferencia distribuida" en barra navegación
2. Hacer clic cada celda en matriz tabla cambiar habilitado/deshabilitado
   - ☑ = habilitado (usar ese tipo inferencia en ese peer)
   - ☐ = deshabilitado (omitir ese peer)
   - — = ese peer no proporciona ese tipo (no operable)
3. Botón "Solo modo local" deshabilita todos peers remotos de una vez
4. Estado guardado automáticamente en `data/mesh_inference_state.json`

## Comportamiento

- Configuración conservada para peers offline (aplicada automáticamente al reconectar)
- "Solo modo local" presionable solo cuando mínimo 1 tipo habilitado localmente
- Iniciar lote tagger con tagger deshabilitado en todos peers genera error `no_enabled_peers`, falla inmediata
- Desconexión/reconexión peer detectada mDNS conserva estado deshabilitación

## Relación con verificación inferencia distribuida YOLO existente

Casilla "Inferencia distribuida" en página detección YOLO conservada por compatibilidad inversa, combinada así:

| yoloDistributed | Columna yolo matriz | Comportamiento real |
|---|---|---|
| ✅ ON | Todos peers habilitados | Distribuida tradicional en todos peers |
| ✅ ON | Algunos deshabilitados | Omitir peers deshabilitados |
| ❌ OFF | Ignorado | Solo local (router bypass) |

## Relacionado

- Referencia API: [api/mesh-inference.md](../api/mesh-inference.md)
- LLM Router (capa separada): [../llm-router/](../llm-router/)
