# Configuración del LLM Router

## Agregando a config.json

```json
{
  "llm_router": {
    "enabled": true,
    "auth": {
      "mode": "loopback",
      "api_key": "",
      "allow_loopback_bypass": true
    },
    "backends": [
      {
        "alias": "ollama-local",
        "base_url": "http://localhost:11434/v1",
        "type": "ollama",
        "auto_discover": true
      }
    ],
    "aliases": {
      "local-fast": "ollama-local/qwen2.5:7b",
      "local-coder": "ollama-local/qwen2.5-coder:32b"
    }
  }
}
```

## Integración con Claude Code

```bash
ANTHROPIC_BASE_URL=http://localhost:5000/v1 claude
```

Al hacer solicitudes, especifique un alias o nombre físico en el campo `model`:
- `local-fast` (alias)
- `ollama-local/qwen2.5:7b` (nombre físico)

## Integración con Continue (VSCode)

`config.json`:
```json
{
  "models": [
    {
      "title": "Local Coder",
      "provider": "openai",
      "apiBase": "http://localhost:5000/v1",
      "model": "local-coder",
      "apiKey": "dummy"
    }
  ]
}
```

## Autodescubrimiento de nodos -- Compatibilidad con nombre de host `.local` (LAN Hogareña)

Cuando ejecuta múltiples máquinas en una LAN hogareña (p. ej., Mac mini + Pi5 + máquina GPU Windows), puede usar nombres de host `.local` en lugar de direcciones IP en `base_url`. De esta forma, **la configuración sigue funcionando incluso si DHCP reasigna direcciones IP**. No se requiere implementación adicional en el lado de yu_ai_manager -- `httpx` resuelve nombres automáticamente a través del resolutor del SO (Bonjour / Avahi / mDNSResponder).

```json
{
  "llm_router": {
    "enabled": true,
    "backends": [
      { "alias": "ollama-mac", "base_url": "http://mac-mini.local:11434/v1", "type": "ollama" },
      { "alias": "ollama-pi5", "base_url": "http://pi5.local:11434/v1",      "type": "ollama" },
      { "alias": "ollama-win", "base_url": "http://gpu-rig.local:11434/v1",  "type": "ollama" }
    ],
    "aliases": {
      "local-fast":  "ollama-mac/qwen2.5:7b",
      "local-coder": "ollama-pi5/qwen2.5-coder:32b",
      "local-big":   "ollama-win/llama3.3:70b"
    }
  }
}
```

Muestra: [`config.example.local-hostname.json`](../../../config.example.local-hostname.json)

### Requisitos

| Sistema Operativo | Requerido |
|---|---|
| macOS | Bonjour (integrado, no se requiere instalación adicional) |
| Linux | `avahi-daemon` (`sudo apt install avahi-daemon` / `sudo systemctl enable --now avahi-daemon`) |
| Windows 10/11 | mDNSResponder (Win10 1803 y posterior pueden resolver `.local` nativamente. Si no funciona, instale Bonjour Print Services) |

### Verificación

```bash
# Pruebe que la resolución funciona
python -c "import socket; print(socket.gethostbyname('mac-mini.local'))"
# → Si devuelve 192.168.x.x, está funcionando
```

### Entre subredes / LAN corporativa / VPN

mDNS funciona a través de multidifusión L2, por lo que **no puede atravesar enrutadores, VPN o VLAN aisladas en redes corporativas**. En estos entornos, especifique direcciones IP directamente como antes:

```json
"backends": [
  { "alias": "remote-gpu", "base_url": "http://10.20.30.40:11434/v1", "type": "ollama" },
  { "alias": "tailscale-mac", "base_url": "http://100.x.x.x:11434/v1", "type": "ollama" }
]
```

Si necesita un reflector mDNS en un entorno segmentado por VLAN, consulte al administrador de su LAN. yu_ai_manager no proporciona un reflector mDNS o proxy.

### Limitaciones conocidas

- **La resolución mDNS de Windows puede ser ocasionalmente lenta** (~1 segundo): Se recomienda establecer el `timeout` del backend en 3 segundos o más
- **El sufijo `.local` es obligatorio**: Usar solo `mac-mini` volverá a NetBIOS / DNS, así que siempre escriba `mac-mini.local`
- **Ollama no se anuncia a través de mDNS**: Solo se usa la resolución de nombre de host; el puerto (11434) debe especificarse manualmente. Para Ollama colocalizado con yu, v4.71.0 agrega un anunciante `_ollama._tcp.local.` en el lado de yu. Para nodos Ollama pure bare (sin yu colocalizado), ver "Manejo de nodos Ollama pure bare (sin yu alojado conjuntamente)" a continuación para la política

## Variables de entorno

| Variable | Comportamiento |
|---|---|
| `TAGDB_DISABLE_LLM_ROUTER` | Configure en `1` para desactivar el enrutador completo |
| `TAGDB_DISABLE_LLM_ROUTER_REFRESH` | Configure en `1` para desactivar el bucle de actualización de 5 minutos |
| `TAGDB_LLM_ROUTER_AUTH_MODE` | Anular con `none`/`loopback`/`api_key` |

## Documentación multiidioma

Siguiendo las `docs/ reading rules` en CLAUDE.md, las versiones `en/zh-tw/zh-cn/ko` se sincronizan basadas en la fuente `ja/` (como una tarea separada después de la implementación; ver TODO.md).

## Autodescubrimiento de nodos (Fase B -- v4.64.0 y posterior)

Los nodos yu_ai_manager en la misma LAN se descubren automáticamente entre sí a través de mDNS (`_yu-ai._tcp.local.`). Incluso sin escribir manualmente backends en `config.json`, los nodos descubiertos se registran automáticamente en el `BackendCatalog` con alias `mdns-<prefix>`.

### Cómo funciona

1. Al inicio, `core/mdns/` anuncia `_yu-ai._tcp.local.`
2. Se suscribe a los registros TXT de otros nodos y verifica que las claves requeridas (versión/node_id/llm_base_url) estén presentes
3. Para nodos con una versión principal coincidente, envía un HTTP GET a `http://<addr>:<web_port>/api/mdns/identity` para confirmar que producto/node_id/versión coinciden
4. Los nodos verificados se registran en el LLM Router como `BackendInfo(alias="mdns-<node_id[:8]>")`
5. A partir de ahí, el bucle de sonda existente maneja actualizaciones periódicas

### Requisitos previos

- El respondedor mDNS del SO debe estar ejecutándose (macOS: Bonjour, Linux: Avahi, Windows: mDNSResponder)
- Los nodos deben estar en la misma subred L2 (para escenarios entre enrutadores / VPN, use la configuración manual de la Fase A)
- UDP 5353 debe permitirse a través del firewall local
- **Ollama debe exponerse a la LAN** -- Ollama se vincula a `127.0.0.1:11434` por defecto, por lo que es inaccesible desde otros nodos en la LAN. Configure la variable de entorno `OLLAMA_HOST=0.0.0.0:11434` antes de iniciar Ollama (macOS: `launchctl setenv OLLAMA_HOST "0.0.0.0:11434"`, Linux: unidad systemd / `.bashrc`, Windows: variables de entorno del sistema). Si esto no se establece, yu_ai_manager determina que es solo localhost y no anunciará `llm_base_url` (aparecerá una advertencia en el registro de inicio)

### Autodetección de Ollama

Si no hay entrada localhost en `llm_router.backends` en `config.json`, yu_ai_manager busca Ollama al inicio en el siguiente orden:

1. `http://<LAN_IP>:11434/api/tags` -- Ollama alcanzable desde la LAN
2. `http://localhost:11434/api/tags` -- Incluso si se detecta, no se realiza anuncio de LAN (se muestra la advertencia anterior)

Si se devuelve una respuesta 200 de la IP de LAN, se incluye automáticamente como `llm_base_url` en el registro TXT. Esto está diseñado para participación sin configuración de nodos collocated Ollama a través de mDNS. Puertos no estándar (11435, etc.) o lmstudio / llamacpp aún requieren entradas explícitas en `config.json`.

### Manejo de nodos Ollama pure bare (sin yu alojado conjuntamente) (política)

Los nodos Ollama pure bare donde `yu_ai_manager` **no** se está ejecutando (p. ej., una Mac de un miembro de la familia que solo tiene Ollama instalado, o un contenedor Ollama en un NAS) **no están cubiertos por autodescubrimiento**. `Ollama` en sí no tiene una función que anuncie `_ollama._tcp.local.` oficialmente, por lo que estructuralmente no hay forma de detectarlos.

Para usar tales nodos desde el LLM Router, configúrelos **manualmente** a través de uno de:

```json
{
  "llm_router": {
    "backends": [
      { "alias": "ollama-nas",    "base_url": "http://nas.local:11434/v1",     "type": "ollama" },
      { "alias": "ollama-family", "base_url": "http://192.168.1.42:11434/v1", "type": "ollama" }
    ]
  }
}
```

- Si su entorno admite nombres de host `.local` (ver "Autodescubrimiento de nodos -- Compatibilidad con nombre de host `.local`" arriba), prefiera eso
- De lo contrario, hardcodee la IP fija

#### Por qué no se intenta el autodescubrimiento

Al diseñar esto (2026-04-11), se compararon las siguientes tres opciones y se eligió la opción (c) guía de configuración manual:

| Opción | Descripción | Decisión |
|---|---|---|
| (a) Escanear toda la LAN `:11434` al inicio | Sonda de fuerza bruta todos los hosts en la subred | **Rechazado** -- carga de red pesada, disruptivo en LAN corporativa / grande, puede confundirse con escaneo de puertos, contradice la filosofía edge-first |
| (b) Daemon anunciador Ollama externo | Envío de un anunciador ligero proporcionado por yu que se ejecuta junto a cada host Ollama | **Rechazado** -- requiere un proceso residente adicional, que es equivalente a solo instalar `yu_ai_manager`. Derrota el punto de "pure bare" |
| (c) Configuración manual de backend vía IP fija / `.local` | Entradas escritas a mano en `config.json` | **Elegido** -- cero implementación adicional, comportamiento explícito, evita arrastrar a los usuarios a escaneos involuntarios |

Si Ollama upstream más tarde anuncia `_ollama._tcp.local.` oficialmente, o agrega un mecanismo oficial de descubrimiento de servicio, lo revisaremos como Fase D en ese momento.

### Deshabilitación

Puede deshabilitar el autodescubrimiento en entornos donde no es necesario (aislamiento Docker, LAN corporativa, CI, etc.):

- Agregue `"mdns": {"enabled": false}` a `config.json`
- O configure la variable de entorno `YU_AI_MDNS_DISABLED=1`

### Comportamientos conocidos

- **Entornos multi-hogar (Wi-Fi + Ethernet)**: Con la configuración predeterminada (`bind_address: null`), el anuncio ocurre en ambas interfaces y `PeerInfo.addresses` contendrá múltiples IPs. Para restringir a una única interfaz, especifique `"bind_address": "192.168.x.y"`.
- **Colisión de alias**: Si un backend en `config.json` usa un alias en formato `mdns-xxxxxxxx`, la configuración manual tiene prioridad y la entrada descubierta por mDNS se omite.
- **Entre subredes**: mDNS funciona solo dentro del dominio de transmisión L2 por defecto. Para operación entre subredes, use el enfoque de nombre de host `.local` de la Fase A.
- **Seguridad**: mDNS en sí no tiene autenticación. Está diseñado para entornos confiables como LAN hogares. Se recomienda deshabilitar en Wi-Fi público o grandes redes compartidas. La verificación `/api/mdns/identity` previene la identificación errónea accidental de nodos o mezcla de versiones anteriores incompatibles.
