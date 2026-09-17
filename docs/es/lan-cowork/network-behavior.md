# Comportamiento de red de LAN Cowork (qué ocurre en LAN)

> Objetivo: Rust standalone v4.538.0 o posterior (`yu-server`). Para la configuración de uso simultáneo del backend de Python (hybrid),
> consulte "Diferencias con la versión de Python" al final.

Esta página resume en una sola página **"qué comienza a hacer tu máquina en la red cuando habilitas LAN Cowork"**.
Léela antes de cambiar cualquier configuración.

---

## Puntos clave

- **Por defecto no hace nada.** Rust standalone no espera ni anuncia nada en la LAN a menos que se habilite explícitamente
  mediante la configuración descrita más adelante.
- Cuando se habilita, **tu nodo se vuelve detectable por otros nodos en la misma LAN**. Este es el comportamiento previsto por diseño.
- **La presencia o ausencia de PIN no detiene los anuncios de descubrimiento.** Consulta "Relación con PIN (punto de confusión común)" para más detalles.

---

## Qué comienza cuando se habilita

| Operación | Descripción |
|---|---|
| **Escucha UDP** | Se vincula a `0.0.0.0:19850` (todas las interfaces) |
| **Anuncios periódicos** | Cada 10 segundos, transmite un HELLO firmado a `255.255.255.255:19850`. El contenido incluye el ID del nodo, clave pública, puerto API, nombre de host, etc. |
| **Registro de otros nodos** | Verifica la firma del HELLO recibido y registra el nodo remoto en tu lista de pares (TOFU) |
| **Aceptación de HTTP entrante** | Los puntos finales de pares en la tabla siguiente comienzan a responder |
| **Distribución local** | Entrega eventos de pares aceptados al SSE (`/api/events/stream`) que la pantalla conectada suscribe |
| **Limpieza de expiración** | Cada 60 segundos, limpia las solicitudes de emparejamiento expiradas y los PIN en texto plano de la memoria |

### Puntos finales aceptados en entrante

| Punto final | Autenticación |
|---|---|
| `GET /ext/lan_cowork/api/peer/discover` | **Sesión no requerida** (consulta de lista de pares) |
| `GET /ext/lan_cowork/api/peer/status` | **Sesión no requerida** (descriptor de nodo propio) |
| `POST /ext/lan_cowork/api/peer/register` | **Sesión no requerida** (auto-registro de pares; el servidor verifica el destino) |
| `POST /ext/lan_cowork/api/peer/pair/request` / `pair/verify` | **Sesión no requerida** (inicio de emparejamiento; los pares sin emparejar no pueden tener sesión) |
| `POST /ext/lan_cowork/api/peer/token/renew` | Firma + nonce (Bearer no requerido) |
| `POST /ext/lan_cowork/api/peer/event` / `heartbeat` | Firma + token Bearer |

"Sesión no requerida" no significa **sin autenticación**, sino que **no requiere una sesión de inicio de sesión**.
Dado que los pares sin emparejar no pueden tener sesión, solo estas 5 rutas se abren como excepción.
El resto de rutas requieren inicio de sesión como es habitual.

---

## Cómo habilitar y deshabilitar

Se cambia en la **sección `extensions`** de `config.json`.

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "enabled": true
    }
  }
}
```

- **Si la clave no existe, está "deshabilitada"** (Rust standalone).
- Se requiere **reiniciar** para que tenga efecto.
- Para cambios temporales, también se puede especificar en las opciones de inicio. El orden de prioridad es
  **línea de comandos > `config.json` > variable de entorno > predeterminado**.

| Método | Habilitar | Deshabilitar |
|---|---|---|
| Línea de comandos | `--native-daemon` | `--no-native-daemon` |
| Variable de entorno | `YU_LAN_COWORK_NATIVE_DAEMON=1` | `=0` |

> La variable de entorno solo interpreta `1` / `true` / `yes` como "habilitado". `on` e `Y` se tratan como **deshabilitado**.

### Comprobación de si está habilitado

```bash
curl -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5000/ext/lan_cowork/api/peer/status
```

| Respuesta | Significado |
|---|---|
| `200` | Habilitado. La función de pares está operativa |
| `405` | **Deshabilitado** (la función no está integrada) |
| `503` | Habilitado pero no listo (claves específicas del nodo no generadas o inicialización interna fallida) |

> **La visualización de la lista de extensiones en la pantalla no es confiable.** La lista de extensiones puede mostrar
> LAN Cowork como "habilitado", pero se basa en información integrada y es **independiente de si el daemon anterior
> se está ejecutando realmente**. La determinación debe hacerse por la respuesta del punto final anterior o la línea
> `native_daemon=...` en el registro de inicio.

---

## Relación con PIN (punto de confusión común)

**No es exacto pensar que si no configuraste un PIN, nada en la LAN puede tocarlo.**

- **Correcto**: Usar `--lan` (escuchar en todas las interfaces) requiere PIN; sin él, el inicio se detiene.
  La escucha predeterminada es `127.0.0.1`, por lo que **en el inicio normal, la cara HTTP no es alcanzable desde la LAN**.
- **Advertencia 1**: Si especificas la IP de LAN directamente en `--host`, esta verificación de PIN obligatorio no se aplica.
  Además, sin PIN configurado, la puerta de inicio de sesión se abre, por lo que **evita exponer sin PIN a la LAN**.
- **Advertencia 2**: **Los anuncios UDP son independientes de que haya un PIN configurado.** Si se habilita,
  incluso un nodo sin PIN anuncia su existencia en la LAN cada 10 segundos. El PIN solo limita la exposición HTTP.

En otras palabras, **PIN reduce la exposición de la cara HTTP pero no detiene los anuncios de descubrimiento.**

### Cuando se escucha solo en loopback (v4.539.0 y posteriores)

Si la dirección de escucha es solo loopback (el valor predeterminado `127.0.0.1`, que también se aplica a la versión de escritorio),
**este nodo no se anuncia en la LAN**. Los demás nodos no podrían conectarse aunque se anunciara.
Después del inicio se registra una vez la siguiente advertencia (es WARN, no INFO, por lo que se ve de forma predeterminada).

```
LAN Cowork discovery inactive: server listens on loopback only; bind a LAN address or use --lan
```

Para usarlo en la LAN, vincula una dirección LAN o usa `--lan` (`--lan` requiere un PIN).

> Antes de v4.539.0, un oyente solo en loopback anunciaba una IP de LAN. Los pares podían descubrirlo,
> pero no conectarse; por eso se cambió este comportamiento.

---

## Qué saber antes de habilitar

- **Al deshabilitar, la información de pares registrada mientras estaba habilitada no se revierte automáticamente.** Además,
  **al habilitar y al iniciar por primera vez**, se ejecuta la limpieza de registros de pares antiguos
  (se eliminan registros sin alcance durante 7 días o más y registros sin emparejar durante más de 1 hora).
  Se recomienda hacer una copia de seguridad de `tags.db` antes de cambiar.
- Los eventos de pares recibidos se envían al SSE que la pantalla conectada suscribe. **El contenido proviene de entrada del nodo remoto**
  (el ID de origen se reemplaza por un valor autenticado en el lado del servidor).
- Lo que permanece en el registro es **solo el recuento, tipo e ID de origen**; el contenido del evento no se registra.
- Si deseas confirmar el estado operativo, habilita el nivel de registro INFO
  (ejemplo: `RUST_LOG=yu_server=info`). En la configuración predeterminada, no se emite la línea que indica la recepción de eventos de pares.

---

## Diferencias con la versión de Python

| | Uso simultáneo del backend de Python (hybrid) | Rust standalone |
|---|---|---|
| Predeterminado | **Habilitado** (habilitado si no hay elemento en `config.json`) | **Deshabilitado** (requiere habilitación explícita) |
| Implementación | Extensión de Python | `yu-server` |

**Rust standalone es deliberadamente "deshabilitado por defecto".** Esto es para evitar que el comportamiento de la red
cambie solo por actualizar. El comportamiento de la configuración hybrid no ha cambiado.

> En la documentación anterior se indicaba la configuración de habilitación como `{"lan_cowork": {"enabled": true}}` (nivel superior), pero
> **esta clave de posición no es leída por ninguna implementación.** La sección `extensions` anterior es la ubicación correcta.
