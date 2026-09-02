# Guía de Configuración de Inferencia Distribuida

> Versión objetivo: v4.67.0 en adelante

## ¿Qué es la Inferencia Distribuida?

Una característica en la que múltiples nodos de yu_ai_manager colaboran para **paralelizar y distribuir** el procesamiento de inferencia como etiquetado, CLIP, YOLO y reconocimiento de voz. Puede compartir escaneos de archivos grandes en múltiples máquinas o delegar el etiquetado a un Pi5 con Hailo NPU.

```
┌──────────────┐   Lote de Imágenes ┌──────────────┐
│   Local      │ ──────────────────► │  Pi5 (Hailo) │  etiquetador × 200 imágenes
│   (Escaneo)  │ ──────────────────► │Máquina GPU   │  etiquetador × 300 imágenes
│              │ ──────────────────► │    Local     │  etiquetador × 100 imágenes
└──────────────┘   Trabajo           └──────────────┘
                  Compartido
```

---

## Requisitos Previos

Las siguientes condiciones deben cumplirse en cada nodo:

1. yu_ai_manager está ejecutándose
2. **La extensión LAN Cowork está habilitada** (`"extensions": {"builtin-lan-cowork": {"enabled": true}}`)
3. Los nodos están **emparejados entre sí** ([Guía de Autenticación de Pares](../lan-cowork/peer-auth.md))
4. Los motores de inferencia a utilizar están configurados en cada nodo (ONNX / Hailo / Whisper, etc.)

---

## Pasos de Configuración

### Paso 1: Habilitar LAN Cowork en cada Nodo

En `config.json` en todos los nodos:

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "enabled": true
    }
  }
}
```

Después del reinicio, los nodos se descubrirán mutuamente automáticamente a través de mDNS.

### Paso 2: Completar el Emparejamiento

Realice el emparejamiento entre todos los pares de nodos (bidireccional).
Detalles: [Autenticación por PIN de Pares y Emparejamiento de Tokens](../lan-cowork/peer-auth.md)

### Paso 3: Verificar la Matriz de Inferencia Distribuida

Abra `/mesh-inference` en cualquier nodo.

Los nodos emparejados aparecen como filas, los tipos de inferencia aparecen como columnas:

| Nodo | etiquetador | clip | yolo | whisper |
|---|---|---|---|---|
| Local | ☑ Habilitado | ☑ Habilitado | ☑ Habilitado | ☑ Habilitado |
| pi5-hailo | ☑ Habilitado | ☑ Habilitado | — No Disponible | — No Disponible |
| gpu-win | ☑ Habilitado | ☑ Habilitado | ☑ Habilitado | ☑ Habilitado |

- **☑ Habilitado**: Usar este nodo para inferencia
- **☐ Deshabilitado**: Omitir (puede alternarse manualmente)
- **—**: Este nodo no tiene el motor de inferencia objetivo (no puede operarse)

### Paso 4: Verificar la Operación

Ejecute un lote de etiquetado y confirme en los registros que se están utilizando múltiples nodos:

```
[mesh-inference] dispatching tagger: 600 items to 3 peers
[mesh-inference] pi5-hailo: processed 200, errors 0
[mesh-inference] gpu-win:   processed 300, errors 0
[mesh-inference] local:     processed 100, errors 0
```

---

## Requisitos por Tipo de Inferencia

| Tipo | Motor Requerido | Descripción |
|---|---|---|
| `tagger` | ONNX (WD14, etc.) o Hailo NPU | Etiquetado estilo Danbooru para imágenes |
| `clip` | ONNX CLIP o Hailo | Vectores de incrustación semántica para imágenes (para búsqueda semántica) |
| `yolo` | ONNX YOLO | Detección de objetos en imágenes |
| `whisper` | faster-whisper o remoto | Transcripción de voz a texto para audio/video |

Los nodos sin un motor configurado mostrarán "—" para ese tipo y no se enrutarán para ese tipo.

---

## Ejemplos de Diseño de Roles

### Ejemplo 1: Dedicar Pi5 + Hailo NPU para Etiquetado

Asigne Pi5 exclusivamente para etiquetado para reducir la carga en otros nodos.

Configuración de la matriz:
- Pi5: etiquetador ☑, otros ☐
- Local: clip ☑, yolo ☑, whisper ☑, etiquetador ☐ (delegar a Pi5)

### Ejemplo 2: Escaneo Masivo Rápido

Habilite el etiquetador en la máquina GPU y la máquina local, compartiendo archivos automáticamente a través del trabajo compartido. No es necesaria ninguna división manual.

### Ejemplo 3: Modo Solo Local (Temporal)

Haga clic en el botón "Modo Solo Local" en `/mesh-inference` para deshabilitar todos los pares remotos a la vez. Útil cuando la red se desconecta.

---

## Solución de Problemas

### El Par No Aparece en la Matriz

1. Verifique que el par sea reconocido con `/api/lan/peers`
2. Confirme que el emparejamiento está completo ([peer-auth.md](../lan-cowork/peer-auth.md))
3. Verifique que LAN Cowork esté habilitado en el nodo remoto

### El Enrutamiento a un Nodo Específico No Funciona

- Verifique que el tipo objetivo para ese nodo muestre ☑ en la matriz
- Compruebe que la respuesta de `/api/lan/peers` muestre `status: "online"` para ese nodo
- Verifique que se esté recibiendo el latido del nodo remoto (busque `heartbeat` en los registros)

### Todo Se Procesa Localmente

Si todos los pares remotos están desconectados o deshabilitados, ocurre una reversión local automática.
Este es el funcionamiento normal (no es un error).

### Error `no_enabled_peers`

Ese tipo está deshabilitado en todos los nodos.
Habilite al menos 1 nodo para ese tipo en la matriz.

---

## Documentación Relacionada

- [Arquitectura de Inferencia Distribuida](overview.md) — Diseño interno de trabajo compartido y DisableAwareStrategy
- [Matriz de Inferencia Distribuida](toggle.md) — Detalles de operación de WebUI
- [Descripción General de LAN Cowork](../lan-cowork/README.md) — Configuración general de LAN Cowork
- [Autenticación por PIN de Pares](../lan-cowork/peer-auth.md) — Procedimiento de emparejamiento
