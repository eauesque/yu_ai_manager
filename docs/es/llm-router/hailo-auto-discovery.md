# Hailo LLM Auto-discovery

**Versión compatible**: v4.66.0 y posteriores

## Descripción general

yu_ai_manager puede descubrir automáticamente y utilizar puntos finales LLM que se ejecutan en la NPU Hailo del Pi5 sin editar `config.json`. Simplemente conecte un Pi5 a la LAN, y otros nodos yu_ai_manager pueden llamar al Hailo LLM.

## Dos tipos de puntos finales

| Punto Final | Descripción | Patrón de URL Predeterminado |
|---|---|---|
| **yu extension Hailo LLM** | LLM compatible con OpenAI proporcionado por la extensión incorporada `builtin-hailo-genai` en yu_ai_manager | `http://<host>:<yu-port>/ext/hailo-genai/v1/` |
| **hailo-ollama** | LLM compatible con OpenAI proporcionado por el binario externo `/usr/bin/hailo-ollama` (puerto predeterminado `:8000`) | `http://<host>:8000/v1/` |

Ambos pueden ejecutarse simultáneamente y ambos se registran automáticamente. Con HailoRT 5.3.0+ y `HAILO_OLLAMA_VDEVICE_GROUP_ID=YU_SHARED` configurado, el planificador HailoRT comparte el dispositivo físico mediante round-robin, por lo que no hay conflicto al usar ambos simultáneamente.

## Autoregistro local (Fase A)

Al inicio, yu_ai_manager detecta independientemente los siguientes dos puntos finales:

1. **yu extension**: Si `hailo_platform.genai.LLM` es importable y existe `/dev/hailo0` o `/dev/h1x-0`, se registra automáticamente como backend `hailo-local` en el catálogo
   (v4.66.1 agregó compatibilidad con Raspberry Pi 5 + AI HAT + HailoRT 5.3.0 que expone el dispositivo como `/dev/h1x-0`)
2. **hailo-ollama**: Se envía una sonda HTTP a `localhost:8000/v1/models` (timeout de 2 segundos). Si se recibe una respuesta 200, se registra automáticamente como backend `hailo-ollama-local`

Si un backend con el mismo alias ya existe en `llm_router.backends` en `config.json`, esa configuración tiene prioridad (no será sobrescrita).

## Anuncio mDNS (Fase B)

Basado en los resultados de detección de la Fase A, yu_ai_manager anuncia capacidades Hailo a otros nodos a través de registros TXT de mDNS:

- `capabilities=llm,hailo` -- Indica que la yu extension está disponible
- `hailo_ollama_url=http://192.168.1.10:8000/v1/` -- Se incluye solo si hailo-ollama se está ejecutando (reescrito a una IP accesible desde la LAN)

Cuando otros nodos yu_ai_manager reciben esto a través de mDNS, realizan verificación de identidad a través del punto final `/api/mdns/identity`, luego registran automáticamente backends adicionales con los siguientes alias:

- `mdns-<node_id[:8]>-hailo` -- yu extension Hailo LLM (cuando `capabilities` incluye `hailo`, la URL se deriva del `web_port` del peer + direcciones)
- `mdns-<node_id[:8]>-hailo-ollama` -- hailo-ollama externo (cuando se anuncia `hailo_ollama_url`, la URL del registro TXT se usa tal cual)

## Configuración

Habilitado por defecto. Puede deshabilitarlo en `config.json` de la siguiente manera:

```json
{
  "llm_router": {
    "hailo_ollama": {
      "enabled": false,
      "port": 8000
    }
  }
}
```

- **`enabled`**: Configure en `false` para deshabilitar completamente la detección automática de hailo-ollama. La detección de la yu extension se controla por separado (se determina automáticamente según si la extensión está cargada)
- **`port`**: Número de puerto para hailo-ollama (predeterminado 8000). Los valores fuera del rango 1-65535 vuelven al predeterminado con un registro de advertencia

## Notas de seguridad

**hailo-ollama no tiene autenticación**. Cuando se anuncia a través de mDNS, **cualquier nodo en la LAN puede consumir libremente los recursos de inferencia de hailo-ollama**.

| Punto Final | Autenticación | Exposición LAN Efectiva |
|---|---|---|
| yu extension (`/ext/hailo-genai/v1/`) | Cadena de autenticación web de yu (PIN/sesión/clave API) | Solo clientes autenticados con yu |
| hailo-ollama (`hailo_ollama_url`) | **Ninguna** | **Todos los nodos en la LAN** |

Para entornos que no sean LAN hogares o VLAN confiables (p. ej., Wi-Fi público), deshabilite el anuncio automático con `hailo_ollama.enabled: false`.

## Apariencia en la WebUI del LLM Router

Los backends registrados automáticamente se muestran en el panel `/llm-router` (v4.65.0):

- `hailo-local` / `hailo-ollama-local` -- Detectado localmente (fuente: insignia `static`)
- `mdns-<id>-hailo` / `mdns-<id>-hailo-ollama` -- Descubierto a través de mDNS (fuente: insignia `mdns`)

Todos pueden ser deshabilitados temporalmente a través del interruptor Deshabilitar. El estado deshabilitado se persiste en `data/llm_router_state.json` y se retiene después de reinicios (implementado en v4.65.0).

## Seguridad contra falsos positivos

La detección de la Fase A tiene dos mecanismos de seguridad:

1. **Evitar sondas propias**: Si `hailo_ollama.port` se establece en el mismo valor que el puerto web propio de yu, la sonda se omite completamente (evita que yu se malidentifique a sí mismo como hailo-ollama)
2. **Prioridad del backend existente**: Si un backend con el mismo `localhost:<port>/v1` ya está registrado en `config.json`, se omite la sonda para respetar la intención del usuario

## Elementos TODO pendientes

- (P3) Traducciones multiidioma (`en`, `zh-tw`, `zh-cn`, `ko`) -- planeado para abordarse junto con el trabajo pendiente de traducción de la WebUI del LLM Router v4.65.0
- (P3) Pruebas de integración de Pi5 -- Equivalente de 16 elementos de Playwright en una configuración de 2 nodos
- (P3) Compatibilidad con IPv6 -- Actualmente `_pick_lan_ip` solo devuelve IPv4
- (P3) Compatibilidad con múltiples dispositivos Hailo -- Supone un alias `hailo-local` fijo. El diseño de sufijo de índice debe considerarse para casos como múltiples dongles USB
- (P3) `BackendCatalog.remove_backend()` -- Actualmente `_mark_unreachable` solo actualiza el estado y no elimina del catálogo

## Documentación relacionada

- [Configuración del LLM Router](./setup.md)
- Especificación de diseño: `docs/superpowers/specs/2026-04-08-hailo-auto-discovery-design.md`
- Plan de implementación: `docs/superpowers/plans/2026-04-08-hailo-auto-discovery.md`

## v4.66.2 -- Autenticación de peer confiable (Reparación de un agujero de autenticación real)

En el Hailo auto-discovery de v4.66.0, la extensión `/ext/hailo-genai/*` de yu estaba detrás de la cadena de autenticación web. Cuando el controlador del LLM Router (que no tiene ni un token Bearer ni una sesión) intentaba sondear/enviar, el middleware de autenticación devolvía HTML de trampa, causando fallos de análisis JSON y que el backend quedara atrapado como `unreachable`.

### Cómo funciona

- Un nuevo `TrustedPeerRegistry` siembra `127.0.0.1` / `::1` en el tiempo de inicialización
- Cuando `LlmRouterMdnsBridge` verifica con éxito un peer (HTTP GET a `/api/mdns/identity` + confirmación de coincidencia de node_id), todas las direcciones anunciadas de ese peer se agregan al registro
- `auth_chain.check_trusted_peer` omite la autenticación PIN al recibir una solicitud para rutas `/ext/<name>/v1/*` si remote_addr está en el registro
- Los caminos de autenticación de clave API / sesión / cookie existentes permanecen sin cambios

### Relación con Quick Lock

- **loopback** (sonda propia de yu): Siempre pasa, incluso durante quick_lock
- **IP del peer**: Las solicitudes se rechazan durante quick_lock (`check_quick_lock` devuelve 503). Esto significa que los pares también respetan el estado "usuario bloqueó intencionalmente"

Esto permite que los siguientes escenarios funcionen como se espera:

- Sonda propia `hailo-local` de pi2 (`http://localhost:5000/ext/hailo-genai/v1/models`)
- Envío entre nodos desde Windows a `mdns-<id>-hailo` de pi2 (`http://192.168.50.4:5000/ext/hailo-genai/v1/chat/completions`)

### Configuración

No se necesian cambios en el archivo de configuración. Incluso en entornos donde mDNS está deshabilitado, la semilla de loopback aún funciona, por lo que la corrección de sonda propia está disponible sin condiciones.

### Depuración

Establezca la variable de entorno `TAGDB_DEBUG_TRUSTED_PEERS=1` antes de iniciar yu para agregar un campo `trusted_ips` a la respuesta `/api/mdns/peers`. No establezca esto en producción (la lista de confianza es esencialmente una "lista de objetivos de ataque" y no debe exponerse en puntos finales no autenticados).

### Límite de seguridad

Operando bajo la suposición de "LAN confiable" (misma premisa que v4.64.0 mDNS Fase B). La protección contra nodos maliciosos con acceso físico a la LAN está fuera del alcance -- use la palanca de deshabilitación de la WebUI `/llm-router` o quick_lock para tales casos.

Ver `docs/superpowers/specs/2026-04-09-trusted-peer-auth-design.md` para detalles.
