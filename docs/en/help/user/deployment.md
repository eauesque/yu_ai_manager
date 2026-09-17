# Deployment and Operations Guide

This guide covers how to deploy and operate YU AI Manager in a production environment.

## 1. Overview

There are three main deployment patterns.

| Pattern | Use Case | Architecture |
|---------|----------|-------------|
| Direct execution | Personal use / development | Launch with Python + venv |
| Docker | Server deployment | Quart + Nginx via docker-compose |
| Reverse proxy | Public-facing | Placed behind an existing web server |

In all cases, data is stored in `data/tags.db` (SQLite). No external database server is required.

---

## 2. Direct Execution (Development / Personal Use)

### Setup

```bash
# Clone the repository
git clone <repository-url> && cd yu_ai_manager

# Create a Python virtual environment
python -m venv venv

# Activate the virtual environment
# Linux / macOS
source venv/bin/activate
# Windows (PowerShell)
.\venv\Scripts\Activate.ps1
# Windows (Git Bash)
source venv/Scripts/activate

# Install dependencies
uv pip install -r requirements.txt

# Build the frontend
pnpm install && pnpm run build

# Start the server
python web_ui.py --db data/tags.db
```

Open `http://localhost:5000` in your browser.

### Setting Arguments via launch-args.txt

Copy `launch-args.txt.example` to `launch-args.txt` and edit it to set persistent launch arguments. CLI arguments take precedence.

```txt
# Change port
--port 5100
# Enable LAN access (bind to 0.0.0.0)
--lan
# PIN authentication
--pin 1234
```

### Running as a systemd Service (Linux)

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

### Running as a Windows Service

The simplest approach is to register `start.bat` in Task Scheduler. Set it to run at logon.

---

## 3. Docker Deployment

### Quick Start

```bash
# Prepare the config file
cp config.json.example config.json
# Edit config.json (pin, scan_roots, etc.)

mkdir -p data

# Build & start
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

Access via `http://localhost` (through Nginx).

### docker-compose.prod.yml Structure

- **app**: Quart application (port 5000, internal only)
- **nginx**: Reverse proxy (port 80, externally exposed)

### Volume Mounts

| Host | Container | Purpose |
|------|-----------|---------|
| `data/` | `/app/data/` | Persistent DB storage |
| `config.json` | `/app/config.json` | Configuration file (read-only) |
| `static/` | `/app/static/` | Static files served directly by Nginx |

Mount your image folders by adding volumes for the paths specified in `config.json`'s `scan_roots`.

```yaml
# Add to docker-compose.prod.yml
volumes:
  - /path/to/images:/images:ro
```

### Environment Variables

Copy `deploy/.env.example` to `deploy/.env` and edit it.

| Variable | Default | Description |
|----------|---------|-------------|
| `NGINX_PORT` | `80` | Nginx public port |
| `UPSTREAM_HOST` | `app` | Quart container name (no need to change) |
| `UPSTREAM_PORT` | `5000` | Quart port (no need to change) |

### Using Podman

Podman works as a drop-in replacement for Docker. Install `podman compose` or `podman-compose` and use the same commands. See `docs/en/installation/podman.md` for details.

---

## 4. Reverse Proxy Configuration

### Key Nginx Settings

`deploy/nginx.conf.template` contains a production-ready configuration. Key points:

- **Static files**: Serve `/static/` directly from Nginx (bypassing Quart)
- **SSE**: Disable buffering for `/api/events/` with `proxy_buffering off`
- **Upload limit**: `client_max_body_size 100m` (match the Quart-side limit)
- **Gzip**: Compress JSON, CSS, and JS

### SSL/TLS (Let's Encrypt)

The Docker Nginx configuration is HTTP-only. For HTTPS, there are two approaches.

**Option 1: Front Proxy (Recommended)**

Place Cloudflare, Caddy, Traefik, or similar in front to handle HTTPS termination.

```
Client --HTTPS--> Caddy/Traefik --HTTP--> Nginx:80 --> Quart:5000
```

**Option 2: Add SSL Directly to Nginx**

Add `listen 443 ssl;` and certificate paths to `nginx.conf.template`, then obtain a Let's Encrypt certificate using certbot.

### Trusted Proxy Configuration

When running behind a reverse proxy, specify the trusted IPs in `config.json`.

```json
{
  "server": {
    "trusted_proxy_ips": ["127.0.0.1", "::1", "172.16.0.0/12"]
  }
}
```

This ensures `X-Forwarded-For` / `X-Forwarded-Proto` headers are processed correctly. CIDR notation is supported.

---

## 5. Authentication Settings

Four authentication methods are available. Combine them according to your needs.

### PIN Authentication (For Browser Access)

```json
{ "pin": "your-secret-pin" }
```

PIN is required when exposing to LAN (`--lan` or binding to `0.0.0.0`). The server will refuse to start if bound to `0.0.0.0` without a PIN configured.

### API Key Authentication (For Programmatic Access)

Issue an API key from the Settings page and include it in request headers.

```bash
curl -H "Authorization: Bearer sk_..." http://localhost:5000/api/search
```

The CSRF header (`X-Requested-With`) is not required for API key authentication.

### Trusted Proxy Authentication

Used when the reverse proxy appends an `X-Remote-User` header. The `trusted_proxy_ips` setting is required.

### LAN Share Mode

Share links for guests can be issued via `/s/` paths. These bypass PIN and authenticate individually by token.

---

## 6. Backup and Recovery

Three types of files should be backed up regularly.

| File | Contents |
|------|----------|
| `data/tags.db` | SQLite DB containing all metadata, tags, and settings |
| `config.json` | Application configuration |
| `data/secret.key`, `data/secret.salt` | Encryption keys (used for settings encryption) |

### Backup Procedure

```bash
# Copy the DB (safe even while running)
sqlite3 data/tags.db ".backup backup/tags_$(date +%Y%m%d).db"

# Config and encryption keys
cp config.json data/secret.key data/secret.salt backup/
```

### Recovery Procedure

Simply place the backup files in their original locations and restart the server. DB migrations are applied automatically at startup.

If the encryption keys (`secret.key`, `secret.salt`) are lost, encrypted configuration values (API credentials, etc.) cannot be decrypted. Always back them up.

---

## 7. Upgrade Procedure

```bash
# 1. Stop the server
# 2. Update the code
git pull

# 3. Update dependencies
source venv/bin/activate  # or .\venv\Scripts\Activate.ps1
uv pip install -r requirements.txt

# 4. Rebuild the frontend
pnpm install && pnpm run build

# 5. Start the server
python web_ui.py --db data/tags.db
```

DB schema migrations are executed automatically at startup. No manual steps are needed.

For Docker, simply rebuild.

```bash
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

---

## 8. Monitoring and Logging

### Log Streaming

View real-time logs in the Settings > Logs tab. Logs are streamed to the browser via SSE (`/api/logs/stream`).

Historical logs can be retrieved via `/api/logs/recent`.

### Health Check

Use the `/api/server-info` endpoint to check the server status.

```bash
curl http://localhost:5000/api/server-info
```

This returns information such as version, DB schema version, and timezone. Use this endpoint for health checks in monitoring tools.

### Diagnostics via MCP

From an MCP client (such as Claude Desktop), invoke the `debug_health_check` tool to run DB integrity checks, search verification, and count validation all at once.
