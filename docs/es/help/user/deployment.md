# Guía de despliegue y operación

Pasos para operar YU AI Manager en un entorno de producción.

## 1. Resumen

Hay principalmente 3 patrones de operación.

| Patrón | Uso | Configuración |
|---------|------|------|
| Ejecución directa | Uso personal, desarrollo | Iniciar con Python + venv |
| Docker | Operación en servidor | Quart + Nginx con docker-compose |
| Proxy inverso | Exposición externa | Colocar detrás de servidor web existente |

En todos los casos, los datos se guardan en `data/tags.db` (SQLite). No se necesita un servidor de BD externo.

---

## 2. Ejecución directa (desarrollo / uso personal)

### Configuración

```bash
# Obtener el repositorio
git clone <repository-url> && cd yu_ai_manager

# Crear entorno virtual Python
python -m venv venv

# Activar el entorno virtual
# Linux / macOS
source venv/bin/activate
# Windows (PowerShell)
.\venv\Scripts\Activate.ps1
# Windows (Git Bash)
source venv/Scripts/activate

# Instalar paquetes dependientes
uv pip install -r requirements.txt

# Compilar frontend
pnpm install && pnpm run build

# Iniciar
python web_ui.py --db data/tags.db
```

Abrir `http://localhost:5000` en el navegador.

### Configuración de argumentos con launch-args.txt

Copiar `launch-args.txt.example` a `launch-args.txt` y editarlo para fijar los argumentos de inicio. Los argumentos CLI tienen prioridad.

```txt
# Cambiar puerto
--port 5100
# Exposición LAN (enlace 0.0.0.0)
--lan
# Autenticación PIN
--pin 1234
```

### Como servicio systemd (Linux)

```ini
# /etc/systemd/system/yu-ai-manager.service
[Unit]
Description=YU AI Manager
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/opt/yu_ai_manager
ExecStart=/opt/yu_ai_manager/venv/bin/python web_ui.py --db data/tags.db --lan
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now yu-ai-manager
```

### Como servicio Windows

La forma más sencilla es registrar `start.bat` en el Programador de tareas. Configúralo para ejecutarse "al iniciar sesión".

---

## 3. Despliegue con Docker

### Inicio rápido

```bash
# Preparar archivo de configuración
cp config.json.example config.json
# Editar config.json (pin, scan_roots, etc.)

mkdir -p data

# Compilar e iniciar
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

Se puede acceder en `http://localhost` (vía Nginx).

### Estructura de docker-compose.prod.yml

- **app**: Aplicación Quart (puerto 5000, solo interno)
- **nginx**: Proxy inverso (expone el puerto 80 externamente)

### Montaje de volúmenes

| Host | Contenedor | Uso |
|-------|---------|------|
| `data/` | `/app/data/` | Persistencia del archivo DB |
| `config.json` | `/app/config.json` | Archivo de configuración (solo lectura) |
| `static/` | `/app/static/` | Archivos estáticos servidos directamente por Nginx |

Para los directorios de imágenes, agregar el montaje del path especificado en `scan_roots` de `config.json`:

```yaml
# Agregar a docker-compose.prod.yml
volumes:
  - /path/to/images:/images:ro
```

### Variables de entorno

Copiar `deploy/.env.example` a `deploy/.env` y editarlo.

| Variable | Predeterminado | Descripción |
|------|----------|------|
| `NGINX_PORT` | `80` | Puerto público de Nginx |
| `UPSTREAM_HOST` | `app` | Nombre del contenedor Quart (no cambiar) |
| `UPSTREAM_PORT` | `5000` | Puerto Quart (no cambiar) |

### Uso con Podman

También funciona con Podman en lugar de Docker. Instalar `podman compose` o `podman-compose` y usar los mismos comandos. Consultar `docs/ja/installation/podman.md` para más detalles.

---

## 4. Configuración del proxy inverso

### Puntos clave de la configuración de Nginx

`deploy/nginx.conf.template` contiene una configuración práctica. Los puntos principales son:

- **Archivos estáticos**: Servir `/static/` directamente desde Nginx (bypass de Quart)
- **SSE**: Deshabilitar el buffering con `proxy_buffering off` para `/api/events/`
- **Límite de carga**: `client_max_body_size 100m` (igualar al lado de Quart)
- **Gzip**: Comprimir JSON, CSS, JS

### SSL/TLS (Let's Encrypt)

La configuración Nginx de Docker solo es HTTP. Si se necesita HTTPS, hay 2 métodos:

**Método 1: Proxy frontal (recomendado)**

Colocar Cloudflare, Caddy, Traefik, etc. en el frente para terminar HTTPS.

```
Cliente --HTTPS--> Caddy/Traefik --HTTP--> Nginx:80 --> Quart:5000
```

**Método 2: Agregar SSL directamente a Nginx**

Agregar `listen 443 ssl;` y la ruta del certificado a `nginx.conf.template`, y obtener el certificado de Let's Encrypt con certbot.

### Configuración de Trusted Proxy

Al usar un proxy inverso, especificar las IPs de confianza en `config.json`:

```json
{
  "server": {
    "trusted_proxy_ips": ["127.0.0.1", "::1", "172.16.0.0/12"]
  }
}
```

Esto permite el procesamiento correcto de los encabezados `X-Forwarded-For` / `X-Forwarded-Proto`. Compatible con notación CIDR.

---

## 5. Configuración de autenticación

Hay 4 tipos de autenticación disponibles. Combínalos según el uso.

### Autenticación PIN (para acceso desde navegador)

```json
{ "pin": "your-secret-pin" }
```

Al exponer en LAN (`--lan` o enlace `0.0.0.0`) el PIN es obligatorio. El inicio se rechaza si se enlaza a `0.0.0.0` sin PIN configurado.

### Autenticación por clave API (para acceso programático)

Emitir una clave API desde la pantalla de Settings y adjuntarla al encabezado de las solicitudes.

```bash
curl -H "Authorization: Bearer sk_..." http://localhost:5000/api/search
```

No se necesita el encabezado CSRF (`X-Requested-With`) con la autenticación por clave API.

### Autenticación Trusted Proxy

Se puede usar en una configuración donde el proxy inverso adjunta el encabezado `X-Remote-User`. La configuración `trusted_proxy_ips` es obligatoria.

### Modo LAN Share

Se puede emitir un enlace compartido de invitado con la ruta `/s/`. Omite el PIN y realiza autenticación individual con token.

---

## 6. Copia de seguridad y recuperación

Los archivos que deben respaldarse regularmente son los siguientes 3 tipos:

| Archivo | Contenido |
|---------|------|
| `data/tags.db` | BD SQLite que contiene todos los metadatos, etiquetas y configuración |
| `config.json` | Configuración de la aplicación |
| `data/secret.key`, `data/secret.salt` | Claves de cifrado (usadas para el cifrado de configuración) |

### Procedimiento de copia de seguridad

```bash
# Copia de la BD (segura incluso durante la operación)
sqlite3 data/tags.db ".backup backup/tags_$(date +%Y%m%d).db"

# Configuración y claves de cifrado
cp config.json data/secret.key data/secret.salt backup/
```

### Procedimiento de recuperación

Solo coloca los archivos de copia de seguridad en su lugar original y reinicia el servidor. Las migraciones de la BD se aplican automáticamente al iniciar.

Si se pierden las claves de cifrado (`secret.key`, `secret.salt`), los valores de configuración cifrados (credenciales de API, etc.) no se podrán descifrar. Asegúrate siempre de hacer una copia de seguridad.

---

## 7. Procedimiento de actualización

```bash
# 1. Detener el servidor
# 2. Actualizar el código
git pull

# 3. Actualizar paquetes dependientes
source venv/bin/activate  # o .\venv\Scripts\Activate.ps1
uv pip install -r requirements.txt

# 4. Recompilar el frontend
pnpm install && pnpm run build

# 5. Iniciar el servidor
python web_ui.py --db data/tags.db
```

Las migraciones del esquema de BD se ejecutan automáticamente al iniciar. No se necesita trabajo manual.

Para Docker, solo recompilar:

```bash
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

---

## 8. Monitoreo y registros

### Streaming de registros

Los registros en tiempo real se pueden verificar en la pestaña Settings > Logs. Se transmiten al navegador via SSE (`/api/logs/stream`).

Los registros pasados se pueden obtener con `/api/logs/recent`.

### Verificación de salud

El estado de operación se puede verificar en el endpoint `/api/server-info`.

```bash
curl http://localhost:5000/api/server-info
```

Devuelve información como versión, versión del esquema de BD, zona horaria, etc. Usa este endpoint para las verificaciones de salud de herramientas de monitoreo.

### Diagnóstico vía MCP

Llamar a la herramienta `debug_health_check` desde un cliente MCP (Claude Desktop, etc.) ejecuta en lote la verificación de consistencia de BD, la confirmación del funcionamiento de búsqueda y la verificación de conteos.
