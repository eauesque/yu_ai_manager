# Autenticación PIN entre pares y emparejamiento de token

**Versión implementación**: 4.92.0
**Archivos relacionados**: `extensions/builtin_lan_cowork/`, `core/lan_cowork_core/`

---

## Descripción general

Antes de v4.92, comunicación entre pares en LAN usaba solo encabezado `X-Peer-Id` para identificación. Este encabezado puede ser falsificado por cualquiera en LAN, seguridad insuficiente.

Desde v4.92, transición a **emparejamiento basado en aprobación PIN con token**.

- Enviar "solicitud de emparejamiento" en primer contacto
- Administrador aprueba en panel administración, emite PIN 6 dígitos
- Después ingresar PIN, se emite token Bearer (válido 30 días)
- Comunicación posterior usa `Authorization: Bearer <token>`

Método `X-Peer-Id` antiguo se puede mantener para compatibilidad en configuración, pero operaciones DELETE siempre requieren nueva autenticación.

---

## Flujo de emparejamiento

```
[Peer A origen]                        [Peer B destino]
       │                                      │
       │--- POST /api/lan/pair/request ------->|
       │    (peer_id, display_name, public_key)|
       │                                      │
       │                              Admin verifica en /lan-cowork/peers
       │                                      │
       |<--- SSE: peer_pairing.pin_ready ------|
       │    (PIN 6 dígitos, válido 5 min)      |
       │                                      │
       │--- POST /api/lan/pair/verify -------->|
       │    (peer_id, pin)                     │
       │                                      │
       |<--- 200 OK: { token, expires_at } ----|
       │    (Token Bearer, válido 30 días)     |
       │                                      │
       │--- Siguiente Authorization: Bearer    |
```

### Detalles de cada paso

| Paso | Endpoint | Descripción |
|------|----------|------|
| 1. Enviar solicitud | `POST /api/lan/pair/request` | Enviar peer ID, nombre pantalla, clave pública |
| 2. Esperar aprobación | — | Administrador confirma en `/lan-cowork/peers` |
| 3. Emitir PIN | — | Administrador presiona botón aprobación, genera PIN 6 dígitos (5 min válido) |
| 4. Verificar PIN | `POST /api/lan/pair/verify` | Enviar PIN, recibir token Bearer |
| 5. Comunicación autenticada | — | Agregar encabezado `Authorization: Bearer <token>` |

---

## Panel administración (`/lan-cowork/peers`)

### Solicitudes esperando aprobación

Cuando solicitud emparejamiento llega de peer nuevo, aparece en pestaña "Esperando aprobación".

- **Aprobar**: Generar PIN, notificar a peer origen via SSE
- **Rechazar**: Eliminar solicitud. Peer origen recibe 403

### Lista de pares conectados

Muestra pares emparejados y vencimiento token cada uno.

| Columna | Contenido |
|--------|----------|
| Nombre pantalla | Nombre del peer |
| Dirección IP | IP origen última confirmada |
| Vencimiento | Vencimiento token Bearer (30 días) |
| Última conexión | Tiempo último heartbeat |
| Acción | Botón revocación token |

### Revocar token

Presionar botón "Revocar" invalida inmediatamente token Bearer de peer.
Próxima comunicación retorna 401, peer intenta automáticamente re-emparejamiento.

---

## Elementos configuración

Configuración en sección `lan_cowork` de `config.json` o pestaña "LAN Cowork" en panel configuración.

### `ip_check_mode`

Especifica método validación dirección IP origen.

| Valor | Comportamiento |
|-------|---|
| `strict` | Permitir solo si coincide exactamente IP emisión token (predeterminado) |
| `cidr` | Permitir si rango CIDR especificado en `allowed_cidr` |
| `rfc1918` | Permitir toda dirección IP privada (192.168.x.x / 10.x.x.x / 172.16-31.x.x) |

### `allow_legacy_auth`

Especifica mantener compatibilidad autenticación encabezado `X-Peer-Id` antiguo.

- `true`: Permitir algunas operaciones solo con encabezado `X-Peer-Id` (predeterminado: `true`)
- `false`: Rechazar todas conexiones sin token Bearer

> **Advertencia**: Operaciones usando método `DELETE` (parar escaneo, forzar eliminar, etc.) siempre requieren token Bearer, independiente configuración `allow_legacy_auth`.

### `protect_heartbeat`

Especifica requerer autenticación en endpoint heartbeat (`/api/lan/heartbeat`).

- `true`: Heartbeat requiere token Bearer
- `false`: Heartbeat pasa sin autenticación (predeterminado: `false`)

Heartbeat se envía frecuentemente, `false` evita retraso en detección vencimiento token.

### `protect_events`

Especifica requerer autenticación en transmisión SSE (`/api/events/`).

- `true`: Conexión SSE requiere token Bearer
- `false`: SSE pasa sin autenticación (predeterminado: `false`)

---

## Notas seguridad

### Hash de token

Token Bearer emitido **no se guarda en texto plano** en base datos.
Se guardan después hash con scrypt (N=16384, r=8, p=1). Incluso si BD se expone, no se puede recuperar token original.

### Enmascaramiento registro

- Encabezado `Authorization: Bearer <token>` se reemplaza automáticamente por `Bearer [REDACTED]` al registrar
- Código PIN tampoco aparece en registro

### Límite velocidad

Se aplican límites velocidad para prevenir ataque DoS o fuerza bruta:

| Endpoint | Límite |
|----------|--------|
| `POST /api/lan/pair/request` | 10/min/IP |
| `POST /api/lan/pair/verify` | 30/min/IP |

PIN vence automáticamente en 5 min, se puede verificar solo 1 vez por solicitud.

---

## Solución de problemas

### Solicitud emparejamiento no llega

- Verificar URL peer destino configurado correctamente
- Verificar firewall no bloquea puerto
- Comprobar registro peer destino recepción `pair/request`

### PIN vencido

Validez PIN es 5 min. Si vence, presionar botón "Aprobar" nuevamente en panel administración para emitir PIN nuevo.

### Token deja funcionar de repente

Posibles causas:

1. Administrador revocó token en panel administración
2. Vencimiento 30 días ha pasado
3. IP cambió con `ip_check_mode: strict`

Ejecutar re-emparejamiento.

### Después cambiar `allow_legacy_auth` a `false` no hay conexión

Si peers existentes aún usan autenticación antigua, todos retornan 401.
Completar re-emparejamiento en cada peer antes cambiar `allow_legacy_auth: false`.
