# LAN Cowork

> Versión objetivo: v4.55.0 en adelante (autenticación PIN disponible desde v4.92.0)

## ¿Qué es LAN Cowork?

LAN Cowork es una función de extensión que permite la coordinación de múltiples nodos yu_ai_manager en una red.  
Cada máquina funciona de forma independiente, permitiendo distribuir cargas de procesamiento pesado o gestionar colectivamente como una Fleet.

```
┌──────────────┐     Descubrimiento   ┌──────────────┐
│  Windows PC  │◄─────────────────────►│   Mac Mini   │
│ (GPU activo) │   Emparejamiento PIN │ (Control)    │
│              │◄─────────────────────►│              │
│  Inferencia  │                      │  Gestión de  │
│ distribuida  │                      │    Fleet     │
│(etiquetador)│                      │              │
└──────────────┘                      └──────────────┘
        ▲                                     ▲
        └─────────────────────────────────────┘
                      ▼
              ┌──────────────┐
              │ Raspberry Pi │
              │ (Hailo NPU)  │
              └──────────────┘
```

---

## Descripción de características

| Característica | Descripción |
|---|---|
| **Descubrimiento automático mDNS** | Descubrir automáticamente nodos en la misma LAN sin configuración |
| **Emparejamiento PIN** | Autenticación PIN aprobada por administrador para emitir tokens entre pares |
| **Inferencia distribuida** | Procesamiento paralelo de etiquetador, CLIP, YOLO y Whisper en múltiples nodos |
| **Distribución de generación** | Delegar trabajos SD WebUI / ComfyUI a nodos LAN |
| **Gestión de Fleet** | Gestionar centralmente registros y actualizaciones de versión en todos los nodos |
| **Retransmisión de eventos de pares** | Transmitir eventos de otros nodos a su propio SSE |
| **Enrutamiento LLM** | Registrar automáticamente pares descubiertos en LLM Router |

---

## Pasos de configuración

### 1. Habilitación

Agregar a `config.json`:

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "enabled": true,
      "peer_name": "my-desktop"
    }
  }
}
```

> **Nota**: Esta página indicaba anteriormente la clave de activación en el nivel superior como `{"lan_cowork": {...}}`, pero ninguna implementación lee una clave en esa ubicación. La sección `extensions` mostrada arriba es la ubicación correcta.

> **El valor predeterminado depende del backend:** el backend de Python (híbrido) trata una clave ausente como **habilitada**, mientras que el servidor independiente de Rust permanece **deshabilitado** salvo que se habilite explícitamente. Para saber qué ocurre realmente en la red una vez habilitado, consulte [Comportamiento de red](network-behavior.md).

Después del reinicio:
- Escuchar otros nodos en UDP 19850
- Comenzar a anunciar _yu-ai._tcp.local. mediante mDNS

### 2. Emparejar nodos

Para conectar del Nodo A al Nodo B:

1. **WebUI del Nodo A** → `Configuración` → `LAN Cowork` → Agregar URL del Nodo B
2. El Nodo A envía `POST /api/lan/pair/request`
3. **WebUI del Nodo B** → `/lan-cowork/peers` → Aprobar en la pestaña "Aprobación pendiente"
4. PIN de 6 dígitos se envía al Nodo A (vía SSE)
5. El Nodo A ingresa PIN → Obtener token Bearer (válido 30 días)

> **Nota**: El emparejamiento es unidireccional. Realice tanto A→B como B→A.

Vea [Autenticación PIN entre pares e Emparejamiento de Token](peer-auth.md) para más detalles.

### 3. Verificar operación

```bash
# Lista de pares descubiertos (desde Nodo A)
curl http://localhost:5000/api/mdns/peers

# Pares reconocidos por LAN Cowork
curl http://localhost:5000/api/lan/peers
```

---

## Configuración específica de características

### Inferencia distribuida

La inferencia distribuida está disponible automáticamente después de completar el emparejamiento.

- `Configuración` → `LAN Cowork` → Habilitar tipos de inferencia (etiquetador/CLIP/YOLO/Whisper) para cada nodo
- O configurar individualmente mediante la matriz en la página `/mesh-inference`

Detalles: [Configuración de Inferencia Distribuida](../mesh-inference/setup.md)

### Gestión de Fleet

Configure un nodo "jefe" para gestionar otros nodos:

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "fleet": {
        "chief": true,
        "allow_remote_update": true,
        "allow_update_from": [
          "<paired peer_id>"
        ]
      }
    }
  }
}
```

Detalles: [Gestión de Fleet](../features/fleet-admin.md)

### Distribución de generación (Delegación de trabajos SD / ComfyUI)

Distribuya automáticamente trabajos de generación a nodos equipados con GPU. Disponible mediante registro de backend de archivo de configuración o descubrimiento automático mDNS.  
Si el Nodo B ejecuta SD WebUI / ComfyUI, estará disponible inmediatamente después de la configuración.

---

## Requisitos de red

| Puerto / Protocolo | Propósito | Requerido |
|---|---|---|
| UDP 5353 | mDNS (descubrimiento de nodos) | Solo LAN L2 mismo |
| UDP 19850 | Descubrimiento LAN Cowork | Solo LAN L2 mismo |
| TCP 5000 (predeterminado) | API, emparejamiento, inferencia | Entre pares |

- mDNS no funciona a través de enrutadores o VPNs (use IP fija o nombre de host `.local`)
- Asegúrese de que UDP 5353 y TCP 5000 estén abiertos en la LAN en su firewall

---

## Índice de documentación

| Documento | Contenido |
|---|---|
| [Autenticación PIN entre pares](peer-auth.md) | Flujo de emparejamiento, gestión de token, configuración de seguridad |
| [Configuración de Inferencia Distribuida](../mesh-inference/setup.md) | Pasos para paralelizar inferencia en múltiples nodos |
| [Matriz de Inferencia Distribuida](../mesh-inference/toggle.md) | Habilitar/deshabilitar por par y por tipo mediante WebUI |
| [Arquitectura de Inferencia Distribuida](../mesh-inference/overview.md) | Diseño interno, robo de trabajo, persistencia |
| [Gestión de Fleet](../features/fleet-admin.md) | Gestión centralizada de registros remotos y actualizaciones de versión |
| [API mDNS Peer](../api/mdns-peers.md) | Detalles de puntos finales `/api/mdns/*` |

---

## Seguridad

- mDNS no tiene autenticación. **Use solo en LANs domésticas o redes confiables**
- En Wi-Fi público o LANs compartidas, deshabilite con `"mdns": {"enabled": false}`
- La comunicación entre pares está protegida por tokens Bearer del emparejamiento PIN (almacenado como hash scrypt)
- `ip_check_mode: strict` permite solo la IP desde la cual se emitió el token (predeterminado)
