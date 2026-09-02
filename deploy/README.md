# YU AI Manager -- Deployment Guide

> **[日本語](README.ja.md) | [繁體中文](README.zh-tw.md) | [简体中文](README.zh-cn.md) | [한국어](README.ko.md)**

## Prerequisites

- Docker Engine 20.10 or later
- Docker Compose V2 (`docker compose` command)
- A `config.json` file at the project root

## Quick Start

```bash
# 1. Prepare config.json in the project root
cp config.json.example config.json
# Edit config.json (set pin, scan_roots, etc.)

# 2. Create the data directory (first time only)
mkdir -p data


# 3. Build & start
docker compose -f deploy/docker-compose.prod.yml up -d --build

# 4. Open in browser
# http://localhost (when NGINX_PORT=80)
```

## Stop / Restart

```bash
# Stop
docker compose -f deploy/docker-compose.prod.yml down

# Restart (after code changes)
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

## Environment Variables

Copy `deploy/.env.example` to `deploy/.env` and edit as needed.

| Variable | Default | Description |
|----------|---------|-------------|
| `NGINX_PORT` | `80` | Port exposed by Nginx on the host |
| `UPSTREAM_HOST` | `app` | Hostname of the Flask container (usually no change needed) |
| `UPSTREAM_PORT` | `5000` | Port of the Flask container (usually no change needed) |

## Volume Mounts

| Host | Container | Description |
|------|-----------|-------------|
| `data/` | `/app/data/` | Persistent SQLite DB (`tags.db`) |
| `config.json` | `/app/config.json` | Application config (read-only) |
| `static/` | `/app/static/` | Static files served directly by Nginx |

### The data directory must exist before the server starts

Whoever deploys creates it; the server does not. In standalone mode yu-server
will create `tags.db` itself when it is missing, but it deliberately will not
create the directory holding it: a mistyped `--db` path would otherwise produce
an empty new library that looks exactly like a lost one. A missing directory is
refused at start-up, naming the resolved absolute path.

Docker users get this from `mkdir -p data` in Quick Start. For
`deploy/yu-server.service`, the directory containing `${YU_DB}` must already
exist — `deploy/systemd/yu-server.service` runs from `WorkingDirectory` with the
relative default `data/tags.db`, so create `data/` under that directory. The
desktop build handles it on its own (`src-tauri/src/app_dirs.rs::ensure_data_dir`).

Standalone also requires `--db-key` (or `YU_DB_KEY`): the server has no default
key and refuses to create an unencrypted database, because the Python version
opens `tags.db` through SQLCipher unconditionally and could never open a
plaintext one.

## PIN Authentication (Production)

When exposing to the LAN, set a PIN in `config.json`. The server refuses to start if bound to `0.0.0.0` without a PIN.

```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 5000,
    "lan": true
  },
  "pin": "your-secret-pin"
}
```

In a Docker environment, Nginx acts as the frontend, so Flask always listens on `0.0.0.0:5000`. Control external access via Nginx port bindings.

## SSL/TLS Termination (Reverse Proxy Pattern)

This Nginx configuration only serves HTTP (port 80). For SSL/TLS, use one of the following approaches.

### Option 1: Place a reverse proxy in front

```
[Client] --HTTPS--> [Cloudflare / Caddy / Traefik]
                              |
                          --HTTP--> [This Nginx :80]
                                        |
                                    --> [Flask :5000]
```

### Option 2: Add SSL directly to this Nginx

Edit `nginx.conf.template` to add `listen 443 ssl;` and certificate paths. Integration with Let's Encrypt (certbot) is common.

## Reverse Proxy Settings (ProxyFix)

When accessing through a reverse proxy such as Nginx, configure `config.json` so the application correctly recognizes the client IP, protocol, and host.

### Option 1: Specify trusted_proxy_ips (recommended)

```json
{
  "server": {
    "trusted_proxy_ips": ["127.0.0.1", "::1", "172.16.0.0/12"]
  }
}
```

CIDR notation is supported. `X-Forwarded-For` / `X-Forwarded-Proto` / `X-Forwarded-Host` headers from trusted IPs are processed automatically.

### Option 2: behind_proxy flag (simple)

```json
{
  "deploy": {
    "behind_proxy": true
  }
}
```

If `trusted_proxy_ips` is not set, only loopback addresses (`127.0.0.1`, `::1`) are trusted. Use Option 1 when the proxy runs in a separate container (e.g., Docker Compose).

## Troubleshooting

### Container won't start

```bash
# Check logs
docker compose -f deploy/docker-compose.prod.yml logs app
docker compose -f deploy/docker-compose.prod.yml logs nginx
```

### DB file permission errors

Check the permissions of the `data/` directory. The in-container process needs write access.

```bash
chmod 777 data/
```

### Static files return 404

Make sure the built `static/dist/` directory exists.

```bash
# Build on the host
pnpm run build

# Or include in the Docker build
```

---

## WD-Tagger Remote Server

A standalone inference server for distributed tagging across multiple machines on a LAN. This script runs independently without the YU AI Manager main application.

### Supported Backends

| Backend | Runs on | Required files | Use case |
|---------|---------|----------------|----------|
| `onnx` | CPU / CUDA / ROCm | `model.onnx` | General purpose (runs on any machine) |
| `hailo` | Hailo-10H NPU | `model.hef` | High-speed inference on Pi 5 + Hailo-10H |
| `auto` | Hailo first, then ONNX fallback | Both or either | Recommended |

### Setup

```bash
# 1. Install required packages
pip install numpy Pillow

# ONNX backend:
pip install onnxruntime          # CPU
pip install onnxruntime-gpu      # NVIDIA CUDA

# Hailo backend:
# Install the hailo_platform wheel from Hailo Developer Zone or source

# 2. Prepare the model directory
mkdir -p models/wd-swinv2-tagger-v3
# Download model.onnx and selected_tags.csv from HuggingFace:
#   https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3
# For Hailo, also place model.hef (converted from ONNX with Dataflow Compiler)

# 3. Start the server
python hailo_tagger_server.py --model-dir ./models/wd-swinv2-tagger-v3

# Specify backend explicitly:
python hailo_tagger_server.py --backend onnx --model-dir ./models/wd-swinv2-tagger-v3
python hailo_tagger_server.py --backend hailo --model-dir ./models/wd-swinv2-tagger-v3

# LAN access requires a generated bearer token:
TOKEN="$(openssl rand -hex 32)"
python hailo_tagger_server.py --host 0.0.0.0 --token "$TOKEN" --model-dir ./models/wd-swinv2-tagger-v3

# Using a JSON config file:
python hailo_tagger_server.py --config tagger_config_example.json
```

### Config file example (`tagger_config_example.json`)

```json
{
  "port": 8080,
  "host": "127.0.0.1",
  "backend": "auto",
  "model": "wd-swinv2-tagger-v3",
  "model_dir": "./models/wd-swinv2-tagger-v3",
  "ort_provider": "",
  "general_threshold": 0.35,
  "character_threshold": 0.85,
  "bearer_token": "REPLACE_WITH_A_RANDOM_SECRET"
}
```

### YU AI Manager Configuration

Register the server in the main YU AI Manager WebUI under **Settings > Tagger** tab.

1. "Add Server" > Type: `hailo_remote`
2. Endpoint URL: `http://<worker-ip>:8080`
3. Bearer Token: the generated token
4. Distribution mode: `parallel` (for multi-machine parallel processing)

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Server status (backend, device, model) |
| `/tag` | POST | Image tagging (multipart/form-data, field: `image`) |

### Health check example

```bash
curl http://192.168.1.101:8080/health
# {"status": "idle", "backend": "onnx", "device": "onnx-cpu", "model": "wd-swinv2-tagger-v3", ...}
```

### Tagging example

```bash
curl -X POST http://192.168.1.101:8080/tag \
  -F "image=@test.png"
# {"tags": [{"tag": "1girl", "confidence": 0.97, "category": "general"}, ...], "elapsed_ms": 150}
```
