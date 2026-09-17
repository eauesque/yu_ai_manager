# LLM Router

> Versión objetivo: v4.55.0 o posterior

## Qué es LLM Router

LLM Router es un **proxy LLM compatible con OpenAI** integrado en yu_ai_manager.  
Agrupa múltiples backends LLM locales como Ollama, LM Studio y llama.cpp,  
y los proporciona como un **punto final único** a clientes como Claude Code, Continue y Open WebUI.

```
Cliente (Claude Code / Continue, etc.)
          │  (API compatible con OpenAI)
          ▼
    yu_ai_manager
    ┌─────────────────────────────────────────┐
    │           LLM Router                   │
    │                                         │
    │  alias: "claude-opus-4-7" ──► large    │
    │  alias: "local-coder" ──► ollama-mac/…│
    │                                         │
    │  [BackendCatalog]                       │
    │   ollama-mac  ─── 192.168.1.10:11434   │
    │   ollama-pi5  ─── 192.168.1.20:11434   │
    │   mdns-win01  ─── Backends detectados automáticamente por mDNS (alias: "mdns-<prefix>") │
    └─────────────────────────────────────────┘
```

### Capacidades

| Característica | Característica |
|---|---|
| **Agrupación de múltiples backends** | Registre cualquier número de instancias de Ollama en la LAN |
| **Abstracción con alias** | Oculte nombres reales de modelos con `"model": "fast"` |
| **Detección automática de mDNS** | Registre automáticamente nodos yu_ai_manager en la misma LAN sin configuración |
| **Integración con Claude Code** | Implemente `/v1/messages` compatible con Anthropic. Sin proxy adicional necesario |
| **Control dinámico habilitar/deshabilitar** | Cambie backends inmediatamente desde la WebUI. Sin reinicio requerido |
| **Enrutamiento basado en categorías** | Seleccione automáticamente modelos óptimos a través de backends virtuales `large` / `fast` / `vision` |

---

## Arquitectura

```
Cliente (Claude Code / Continue, etc.)
    │
    │ POST /v1/chat/completions
    │ POST /v1/messages          ← Anthropic compatible
    │ GET  /v1/models
    ▼
BackendCatalog  ─── Resolución de alias ──► Backend + nombre del modelo
    │
    ├─ Backends registrados manualmente (escritos en config.json)
    └─ Backends detectados automáticamente por mDNS (alias: "mdns-<prefix>")
```

**Flujo de solicitud:**

1. El cliente solicita con `"model": "claude-opus-4-7"`
2. El router resuelve `"claude-opus-4-7"` → `"large"` en la tabla `aliases`
3. Seleccione un backend válido de la categoría `large`
4. {trans["flow_step_4"]}
5. {trans["flow_step_5"]}

---

## Índice de documentación

| Característica | Característica |
|---|---|
| [Configuración](setup.md) | Cómo escribir config.json, integración con Claude Code/Continue, configuración de mDNS |
| [WebUI](webui.md) | Cómo operar el panel de control `/llm-router` |
| [Detección automática de Hailo](hailo-auto-discovery.md) | Registro automático de peers con Hailo NPU |
| [Manejo de peers inaccesibles](mdns-peer-unreachable.md) | Solución de problemas cuando los peers detectados por mDNS se vuelven `unreachable` |

---

## Gateway Diferencia con Gateway

| | LLM Router | Gateway |
|---|---|---|
| **Ámbito** | Solo LLM (Ollama, etc.) | SD WebUI, ComfyUI, Ollama juntos |
| **Límite de autenticación** | Local puede omitirse. api_key requerido fuera de LAN | Autenticación Bearer basada en alcance para todos los backends |
| **Puntos finales** | `/v1/*` (compatible con OpenAI/Anthropic) | `/v1/*`, `/sd/*`, `/comfy/*` |
| **Caso de uso principal** | Backend para herramientas de codificación de IA | Exponga herramientas de generación de forma segura a clientes externos |

Ambas características funcionan de forma independiente. Si solo usa LLM, LLM Router es suficiente.

---

## Relación con LAN Cowork

Cuando [LAN Cowork](../lan-cowork/README.md) está habilitado,  
los peers en la misma LAN se detectan automáticamente a través de mDNS y se registran automáticamente  
en LLM Router con alias como `mdns-<node_id[:8]>`.  
Se configura un entorno LLM multinodo sin configuración.
