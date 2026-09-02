# Podman Setup

YU AI Manager's container environment supports both Docker and Podman. The management scripts (`scripts/yu-docker.sh`, `tools/docker-build.sh`) auto-detect the installed runtime.

---

## Prerequisites

- Podman 4.0 or later
- `podman compose` plugin (Podman 4.7+) or `podman-compose` (pip)

### Installing Podman

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

### Installing a Compose Tool

One of the following is required to use `docker-compose.yml` with Podman:

```bash
# Option 1: podman-compose (pip, lightweight)
uv pip install podman-compose

# Option 2: podman compose plugin (Podman 4.7+)
# May already be bundled with Podman. Check with:
podman compose version
```

---

## Basic Usage

### Via Management Scripts (Recommended)

The scripts auto-detect Docker or Podman, so the commands are identical to Docker usage:

```bash
# Initial setup
./scripts/yu-docker.sh init

# Build
./scripts/yu-docker.sh build

# Start
./scripts/yu-docker.sh up

# Logs
./scripts/yu-docker.sh logs

# Stop
./scripts/yu-docker.sh down
```

### Direct Commands

```bash
# Build
podman build -t yu-ai-manager .

# Start (compose)
podman compose up yu-ai-manager -d

# Start (standalone)
podman run -d --name yu-ai-manager \
  -p 5000:5000 \
  -v ./data:/app/data \
  -v ./uploads:/app/uploads \
  yu-ai-manager

# Hailo variant build
./tools/docker-build.sh --hailo --hailo-wheel ~/hailort/dist/*.whl
```

---

## Differences from Docker

### Rootless Mode

Podman runs in rootless mode (no root privileges) by default. Most use cases work out of the box, but keep the following points in mind:

| Item | Impact | Resolution |
|------|--------|------------|
| Ports below 1024 | Cannot bind in rootless mode | Not an issue -- this project uses port 5000 |
| Device passthrough | Access to `/dev/hailort0` etc. requires permissions | Use `podman run --device` with group permissions, or `sudo podman` |
| UID mapping | Container `appuser` UID differs from host UID | Fix volume permission issues with `podman unshare chown` |

```bash
# Check UID mapping
podman unshare cat /proc/self/uid_map

# Fix volume permissions (example)
podman unshare chown -R 1000:1000 ./data ./uploads
```

### Hailo Device Passthrough

```bash
# Rootless mode may not have access to /dev/hailort0
# Option 1: Add the user to the hailort group
sudo usermod -aG hailort $USER

# Option 2: Run as rootful
sudo podman compose -f docker-compose.yml -f docker-compose.hailo.yml up yu-ai-manager
```

### Networking

Podman's default network is called `podman` and is equivalent to Docker's `bridge`. Custom networks defined in `docker-compose.debug.yml` (e.g., `debug-net`) work without modification.

```bash
# List networks
podman network ls
```

### Volumes

Both named volumes and bind mounts are supported. Bind mounts in `docker-compose.yml` (e.g., `./data:/app/data`) work as-is.

### systemd Integration (Linux Server Deployments)

Podman integrates easily with systemd. To configure auto-start:

```bash
# Generate a systemd unit after starting the container
podman generate systemd --new --name yu-ai-manager > ~/.config/systemd/user/yu-ai-manager.service

# Enable
systemctl --user daemon-reload
systemctl --user enable --now yu-ai-manager.service

# Enable user service auto-start at boot (linger)
loginctl enable-linger $USER
```

---

## Docker CLI Compatibility Aliases (Optional)

To use Docker-oriented documentation and scripts as-is:

```bash
# Add to ~/.bashrc or ~/.zshrc
alias docker=podman
alias docker-compose=podman-compose
```

The management scripts auto-detect the runtime, so these aliases are not required.

---

## Troubleshooting

### `WARN[0000] "/" is not a shared mount` Warning

```bash
# This may occur with rootless Podman. It is harmless, but to suppress it:
podman system migrate
```

### `podman compose` Not Found

```bash
# Podman versions before 4.7 do not bundle the compose plugin
# Install podman-compose via pip instead
uv pip install podman-compose
```

### Cannot Access localhost from Inside a Container

Rootless Podman uses `host.containers.internal` (equivalent to Docker's `host.docker.internal`).

```bash
# When accessing the web service from a debug container,
# use the docker-compose.debug.yml network (http://web:5000) -- no issue
```

### Image Cleanup

```bash
# Remove unused images
podman image prune -a

# Remove all resources
podman system prune -a
```

---

## Compatibility Summary

| File | Podman Compatible | Notes |
|------|-------------------|-------|
| `Dockerfile` | OK | Standard OCI spec |
| `Dockerfile.debug` | OK | |
| `Dockerfile.playwright` | OK | |
| `deploy/Dockerfile` | OK | |
| `docker-compose.yml` | OK | |
| `docker-compose.debug.yml` | OK | |
| `docker-compose.hailo.yml` | OK | Device passthrough requires permissions |
| `deploy/docker-compose.prod.yml` | OK | |
| `tools/docker-build.sh` | OK | Auto-detects runtime |
| `scripts/yu-docker.sh` | OK | Auto-detects runtime |
| `.dockerignore` | OK | Podman reads the same file |
