# Configuración

## Configuración del servidor

| Elemento | Descripción |
|------|------|
| Host | Dirección de bind (con LAN OFF, fija en 127.0.0.1) |
| Port | Número de puerto del servidor web |
| LAN Access | Con ON permite el acceso desde otros dispositivos de la LAN |
| PIN Auth | Exige introducir un PIN al acceder |
| Boss Mode | Pantalla de inicio de sesión con PIN con aspecto de periódico |

## Configuración del escaneo

Añadir, eliminar, reordenar y activar/desactivar las carpetas registradas.

## Configuración del parser

| Elemento | Descripción |
|------|------|
| Extract A1111 | Extrae metadatos en formato Stable Diffusion WebUI |
| Extract ComfyUI | Extrae metadatos de workflow de ComfyUI |
| Normalize tags | Unifica las etiquetas a minúsculas |
| Compute hash | Calcula el hash del archivo (para detección de duplicados) |
| FTS | Activa el índice de búsqueda de texto completo |

## Claves API

Gestiona claves API para herramientas externas (servidor MCP, scripts, agentes).
Se utilizan con autenticación Bearer.

## Apariencia

Personalización de tema, color de acento, imagen de fondo, efectos de sonido, etc.

## Almacén de secretos cifrado

Los valores sensibles como PIN, contraseña de Bluesky y secretos de webhook se protegen con cifrado Fernet del paquete `cryptography`.

- **Formato de cifrado**: cadena con prefijo `enc:`
- **Compatibilidad**: los valores en texto plano existentes siguen funcionando (solo se cifran las nuevas grabaciones)
- **Instalación**: `uv pip install cryptography` (la función de cifrado se desactiva si no está instalado)

### Backend de claves

La clave de cifrado se obtiene con la siguiente prioridad:

1. **Passphrase** — Si se establece la variable de entorno `YU_SECRET_PASSPHRASE`, la clave se deriva mediante PBKDF2-HMAC-SHA256 (600 000 iteraciones). La sal se guarda automáticamente en `data/secret.salt`
2. **Llavero del SO** — Si el paquete `keyring` está instalado, la clave se guarda en Windows Credential Manager / macOS Keychain / Linux Secret Service
3. **Archivo** — `data/secret.key` (compatibilidad anterior, se genera automáticamente la primera vez)

```bash
# Ejemplo de configurar la passphrase
export YU_SECRET_PASSPHRASE="my-strong-passphrase"

# Usar el llavero
uv pip install keyring
```

### Exportar / importar claves

Para migrar a otra máquina o hacer copia de seguridad, se pueden exportar/importar las claves de cifrado en formato JSON protegido con contraseña.

- `POST /api/settings/secrets/export` — Exporta protegido con contraseña (8 caracteres o más)
- `POST /api/settings/secrets/import` — Restaura la clave con los datos exportados y la contraseña
- `POST /api/settings/secrets/migrate-keychain` — Migra de archivo al llavero
- `GET /api/settings/secrets/status` — Consulta el estado del backend

### Migración al llavero

Para migrar al llavero una clave guardada en archivo, llame a `/api/settings/secrets/migrate-keychain`. Tras la migración, `data/secret.key` se elimina automáticamente.

## Integración con 1Password CLI

En entornos con la CLI `op` instalada, se pueden obtener secretos dinámicamente desde un Vault de 1Password.

### Configuración

1. Instale [1Password CLI](https://developer.1password.com/docs/cli/)
2. Inicie sesión con `op signin`
3. Añada un mapeo `op_secrets` en `config.json`:

```json
{
  "op_secrets": {
    "server.pin": "op://Private/YuManager/pin",
    "sns.bluesky.app_password": "op://Private/Bluesky/app_password"
  }
}
```

4. Configure indicando `op_uri` desde la API de Settings o la herramienta MCP:

```
settings_set(key="server.pin", value="", op_uri="op://Private/YuManager/pin")
```

### Comportamiento

- Si la clave está registrada en `op_secrets`, el secreto se obtiene con `op read`
- El valor obtenido se cachea en memoria durante 5 minutos
- En entornos sin la CLI `op`, se hace fallback al almacén local cifrado
- Puede comprobar el estado de autenticación de 1Password con `GET /api/settings/op-status`

## Herramientas MCP de Settings

Se puede gestionar la configuración desde un cliente MCP (como Claude Desktop).

| Herramienta | Descripción |
|--------|------|
| `settings_get_schema` | Obtiene el esquema de todas las opciones (tipo, descripción, categoría) |
| `settings_get_all` | Obtiene todos los valores (los secretos aparecen enmascarados) |
| `settings_get` | Obtiene el valor de una opción |
| `settings_set` | Actualiza el valor (los secretos se cifran automáticamente) |
| `secrets_status` | Obtiene el estado del backend de claves de cifrado |
| `secrets_export` | Exporta la clave en JSON protegido con contraseña |
| `secrets_import` | Importa la clave desde datos exportados |
