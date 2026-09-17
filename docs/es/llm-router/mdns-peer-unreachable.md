# El backend mDNS permanece como 'no alcanzable'

Causas, diagnóstico y resolución para el caso en que un backend añadido mediante
el autodescubrimiento mDNS del LLM Router permanezca en el estado
«no alcanzable (unreachable)» sin recuperarse.

---

## Descripción general de la estructura

```
MdnsService (zeroconf layer)
  └─ on_peer_added / on_peer_updated / on_peer_removed
       └─ LlmRouterMdnsBridge
            ├─ _verify()       ← Verificación HTTP mediante /api/mdns/identity
            ├─ _apply_peer_to_catalog()  ← Registro en BackendCatalog
            ├─ _enter_cooldown() / _in_cooldown()  ← Límite de reintentos tras fallo
            └─ retry_pending_peers()  ← Barrido cada 60 s (desde v4.91.15)
```

**Flujo importante**:

1. zeroconf detecta un peer → se llama a `on_peer_added`
2. `_verify()` llama a `/api/mdns/identity` y valida `node_id` y `product`
3. Éxito → `_apply_peer_to_catalog()` añade el backend al catálogo
4. Fallo → entra en cooldown de 60 s; se ignoran los eventos del mismo `node_id`
5. **Desde v4.91.15**: una tarea de barrido cada 60 s reintenta los peers pendientes tras expirar el cooldown

---

## Patrones frecuentes de «no alcanzable»

### Patrón A — Primer verify falla → silencio por cooldown

**Síntoma**: El backend aparece en el LLM Router pero con status=unreachable.  
**Causa**:
- El servidor HTTP del nodo remoto aún no estaba listo justo después de iniciarse
- El propio puerto había cambiado y el peer referenciaba un TXT antiguo (error de `--port` override antes de v4.91.14: corregido en 35a3679a)

**Comportamiento (antes de v4.91.14)**: Tras expirar el cooldown (60 s) se espera al siguiente evento `on_peer_updated`; si dicho evento no se dispara, nunca se recupera.

**Comportamiento (desde v4.91.15)**: Tras expirar el cooldown, el siguiente tick del barrido (máx. 60 s después) reintenta automáticamente → si tiene éxito, se refleja en el catálogo.

---

### Patrón B — zeroconf no dispara `ServiceStateChange.Updated`

**Síntoma**: El peer se reinició pero el LLM Router mantiene el estado antiguo.  
**Causa**: Dependiendo del estado de caché de zeroconf, puede que no se dispare el evento `Updated` al cambiar un TXT (comportamiento conocido de la librería zeroconf).  
**Resolución**: La tarea de barrido de v4.91.15 lo detecta en menos de 60 s.

---

### Patrón C — El puerto del nodo remoto difiere del valor anunciado

**Síntoma**: curl llega al peer pero los timeouts de verify continúan.  
**Causa**: Se usa el flag `--port` en la CLI pero `server.port` en config.json tiene el valor antiguo → se anuncia el puerto incorrecto en el TXT de mDNS.  
**Corrección**: Solucionado en v4.91.14 (35a3679a): `config["server"]["port"]` se sobreescribe con el puerto real. Si algún script de inicio antiguo modifica config.json directamente, comprueba también ese archivo.

---

### Patrón D — No registrado en trusted_peer_registry

**Síntoma**: El LLM Router muestra «ready» pero el proxy a `/ext/<name>/v1/*` devuelve 403.  
**Causa**: El verify fue exitoso y entró en el catálogo, pero el proceso se reinició antes de llamar a `_apply_peer_to_catalog()`, o `service_kind != "yu"` hizo que se omitiera el registro en el registry (los peers bare Ollama no se registran por diseño).  
**Verificación**:
```bash
curl -s http://127.0.0.1:PORT/api/mdns/peers | python3 -m json.tool | grep -E 'node_id|trusted'
```

---

## Pasos de diagnóstico

### 1. Comprobar el estado actual del peer

```bash
# Lista de peers conocidos
curl -s http://127.0.0.1:PORT/api/mdns/peers | python3 -m json.tool

# Lista de backends del LLM Router (los de mDNS tienen alias con prefijo "mdns-")
curl -s http://127.0.0.1:PORT/api/llm_router/status | python3 -m json.tool
```

### 2. Verificar que el nodo remoto alcanza el propio endpoint de identity

Desde el nodo remoto:
```bash
curl -v http://<propia-IP-LAN>:<PORT>/api/mdns/identity
```

Respuesta esperada:
```json
{"product": "yu_ai_manager", "node_id": "...", "version": "..."}
```

Si falla:
- Problema de firewall o enrutamiento
- El puerto real difiere del anunciado (verificar si se usa `--port` al iniciar)

### 3. Comprobar el puerto anunciado

```bash
# El log de inicio muestra "web_port"
grep -i "web_port\|mdns.*port\|effective_port" logs/app.log | tail -20

# O mediante la API de settings
curl -s http://127.0.0.1:PORT/api/server/info | python3 -m json.tool | grep port
```

### 4. Comprobar el estado de cooldown

GUI: **LLM Router** > tarjeta del backend > Detalles muestra `last_error` y `last_seen_at`.
Si el error es «identity verification failed», el peer es alcanzable pero hay discrepancia de contenido (conflicto de node_id / product). Si es «timeout», HTTP no llega al peer.

### 5. Comprobar los logs del barrido

```bash
grep "\[mdns\] sweep" logs/app.log
```

`sweep re-verified peer <8chars>` indica que el barrido logró la recuperación.

---

## Recuperación manual

Para no esperar al siguiente tick del barrido:

### Método 1: Reiniciar el nodo remoto

Al reiniciar, zeroconf dispara `ServiceStateChange.Removed` + `Added` →
`on_peer_removed` limpia el cooldown → `on_peer_added` realiza la verificación inmediatamente.

### Método 2: Reiniciar el servicio mDNS desde la UI de configuración

**Configuración** > **LLM Router** > botón **Reiniciar mDNS** (si está disponible).

### Método 3: Reiniciar la aplicación

El cooldown solo existe en memoria. Al reiniciar se resetean todos los cooldowns
y se vuelven a verificar todos los peers justo después del arranque.

---

## Puntos de prevención

| Comprobación | Método |
|---|---|
| Al usar `--port`, ¿coincide `server.port` en config.json? | Revisar config.json |
| ¿El firewall permite tráfico entrante en `PORT`? | `sudo ufw status` / Preferencias macOS |
| En entornos multi-NIC, ¿se hace bind a la interfaz LAN correcta? | `mdns.bind_address` en config.json |
| ¿Se está usando v4.91.15 o superior (con tarea de barrido)? | `curl .../api/server/info` |

---

## Archivos relacionados

| Archivo | Función |
|---|---|
| `core/llm_router/mdns_integration.py` | `LlmRouterMdnsBridge`, cooldown, retry_pending_peers |
| `core/web/runtime_mdns.py` | Inicio/detención de la tarea de barrido |
| `core/mdns/service.py` | Wrapper de zeroconf, `list_peers()` |
| `core/web/trusted_peer_registry.py` | Autenticación cross-node para `/ext/*` |
