# Configuración con Podman

El entorno de contenedor de YU AI Manager es compatible con Docker y Podman.
Los scripts de administración (`scripts/yu-docker.sh`, `tools/docker-build.sh`) detectan automáticamente runtime instalado.

---

## Requisitos previos

- Podman 4.0 o superior
- `podman compose` plugin (Podman 4.7+) o `podman-compose` (pip)

### Instalar Podman

```bash
# Debian / Ubuntu / Raspberry Pi OS
sudo apt install podman

# Fedora
sudo dnf install podman

# macOS (Homebrew)
brew install podman
podman machine init
podman machine start
```

### Instalar herramienta Compose

Para usar `docker-compose.yml` con Podman, se requiere uno de lo siguiente:

```bash
# Método 1: podman-compose (pip, ligero)
uv pip install podman-compose

# Método 2: plugin podman compose (Podman 4.7+)
# A veces incluido con podman. Verificar con:
podman compose version
```

---

## Uso básico

### A través de script de administración (recomendado)

El script detecta Docker / Podman automáticamente, por lo que el comando es igual que para Docker.

```bash
# Configuración inicial
./scripts/yu-docker.sh init

# Compilar
./scripts/yu-docker.sh build

# Iniciar
./scripts/yu-docker.sh up

# Registros
./scripts/yu-docker.sh logs

# Detener
./scripts/yu-docker.sh down
```

### Comando directo

```bash
# Compilar
podman build -t yu-ai-manager .

# Iniciar (compose)
podman compose up yu-ai-manager -d

# Iniciar (individual)
podman run -d --name yu-ai-manager \
  -p 5000:5000 \
  -v ./data:/app/data \
  -v ./uploads:/app/uploads \
  yu-ai-manager

# Compilar variante Hailo
./tools/docker-build.sh --hailo --hailo-wheel ~/hailort/dist/*.whl
```

---

## Diferencias con Docker y notas de precaución

### Modo Rootless

Podman funciona sin root (rootless) de manera predeterminada.
Funciona en la mayoría de casos, pero tenga en cuenta lo siguiente.

| Elemento | Impacto | Solución |
|---|---|---|
| Puerto < 1024 | No se puede enlazar en rootless | Sin problema (usa puerto 5000) |
| Device passthrough | Requiere permisos para acceder `/dev/hailort0` etc. | `podman run --device` + permisos grupo, o `sudo podman` |
| Mapeo UID | UID de `appuser` en contenedor diferente de UID host | Si hay problemas permisos volumen, reparar con `podman unshare chown` |

```bash
# Verificar mapeo UID
podman unshare cat /proc/self/uid_map

# Ejemplo de reparación de permisos volumen
podman unshare chown -R 1000:1000 ./data ./uploads
```

### Device Passthrough Hailo

```bash
# En rootless, puede no haber acceso a /dev/hailort0
# Método 1: Agregar usuario a grupo hailort
sudo usermod -aG hailort $USER

# Método 2: Ejecutar con privilegios
sudo podman compose -f docker-compose.yml -f docker-compose.hailo.yml up yu-ai-manager
```

### Red

Red predeterminada de Podman es `podman`, equivalente a `bridge` de Docker.
Red personalizada de `docker-compose.debug.yml` (`debug-net`) también funciona igual.

```bash
# Verificar redes
podman network ls
```

### Volumen

Compatible con volúmenes nombrados y bind mounts.
El bind mount de `docker-compose.yml` (`./data:/app/data`) funciona igual.

### Integración systemd (operación servidor Linux)

Podman se integra fácilmente con systemd. Para configurar inicio automático:

```bash
# Generar unidad systemd después iniciar contenedor
podman generate systemd --new --name yu-ai-manager > ~/.config/systemd/user/yu-ai-manager.service

# Habilitar
systemctl --user daemon-reload
systemctl --user enable --now yu-ai-manager.service

# Inicio automático servicio usuario en arranque máquina (linger)
loginctl enable-linger $USER
```

---

## Alias de compatibilidad Docker CLI (opcional)

Si desea usar documentación o scripts para Docker tal cual:

```bash
# Agregar a ~/.bashrc o ~/.zshrc
alias docker=podman
alias docker-compose=podman-compose
```

Los scripts de administración detectan automáticamente, por lo que este alias no es obligatorio.

---

## Solución de problemas

### Advertencia `WARN[0000] "/" is not a shared mount`

```bash
# Ocurre a veces en Podman rootless. Inofensivo pero si desea quitarlo:
podman system migrate
```

### `podman compose` no encontrado

```bash
# Podman < 4.7 no incluye plugin
# Instalar podman-compose con pip
uv pip install podman-compose
```

### No se puede acceder localhost desde contenedor

En Podman rootless, usar `host.containers.internal` (equivalente a `host.docker.internal` de Docker).

```bash
# Acceder servicio web desde contenedor debug
# docker-compose.debug.yml usa red (http://web:5000), sin problema
```

### Limpiar imágenes

```bash
# Eliminar imágenes no usadas
podman image prune -a

# Eliminar todos recursos
podman system prune -a
```

---

## Resumen compatibilidad

| Archivo | Compatibilidad Podman | Notas |
|---|---|---|
| `Dockerfile` | OK | Especificación OCI estándar |
| `Dockerfile.debug` | OK | |
| `Dockerfile.playwright` | OK | |
| `deploy/Dockerfile` | OK | |
| `docker-compose.yml` | OK | |
| `docker-compose.debug.yml` | OK | |
| `docker-compose.hailo.yml` | OK | Device passthrough requiere atención permisos |
| `deploy/docker-compose.prod.yml` | OK | |
| `tools/docker-build.sh` | OK | Detección automática runtime |
| `scripts/yu-docker.sh` | OK | Detección automática runtime |
| `.dockerignore` | OK | Podman usa mismo archivo |
