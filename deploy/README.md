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

### Two units, one destination name

There are two server unit files, and they install to the **same** name:

| File | Installer | What it assumes |
|------|-----------|-----------------|
| `deploy/yu-server.service` | `cp` by hand (`scripts/migrate_launch_args.py` prints the command) | `~/.config/yu/server.env` supplies `YU_DB` and `YU_DB_KEY`; passes `--db` explicitly |
| `deploy/systemd/yu-server.service` | `make deploy` | runs from `WorkingDirectory` with the relative default `data/tags.db`; passes `--lan` |

Both land on `~/.config/systemd/user/yu-server.service`, so whichever
installer ran last wins. That is why both files carry the
`Wants=`/`After=yu-db-migrate.service` wiring: for one release only the first
did, and a single `make deploy` silently removed the migration ordering and
put the machine back to stopping at 78 forever. `scripts/pre_push_check.py`
now requires the wiring in both.

`make deploy` does not install the migration unit, and it does not create
`server.env`. The oneshot therefore skips itself on such a machine
(`ConditionPathExists` names `server.env` as well as the script and the
interpreter) rather than failing: `EnvironmentFile=` without a leading dash
fails a unit outright when the file is missing — measured, `Result=resources`,
with `ExecStart` never reached.

To migrate on a `make deploy` machine, install `server.env` as above and add
the oneshot by hand. Pointing it at the right database needs care: this unit
passes no `--db`, so config's `db` key outranks `YU_DB` (see
`resolve_db_path` in `crates/yu-server/src/main.rs`), and a oneshot given a
different path would migrate a database nobody opens.

Ask the binary rather than guessing — it resolves the path the same way the
server does:

```sh
cd "$(systemctl --user show -p WorkingDirectory --value yu-server.service)"
~/.local/bin/yu-server --print-db-path
```

Run it where the server runs: the answer depends on the working directory
(config.json is read from it) and on the environment, so a query made
elsewhere answers a different question. It opens nothing and creates nothing.
Feed the result to the oneshot's `--db`.

Migrating a database the server does not open is the failure this ordering
exists to prevent, and it looks like success: the migration exits 0 and the
server still stops at 78 with the real database untouched. Where both units do
name a database on argv, `scripts/pre_push_check.py` requires the two values
to be identical.

### A database older than the binary

yu-server exits **78** when the database is at an older schema version than the
binary expects and nothing has declared a Python backend that could migrate it.
`RestartPreventExitStatus=78` stops systemd from retrying, because retrying
cannot help.

**78 requires that the version could be read.** A database the binary cannot
open at all is a different outcome — measured, with a real binary against an
encrypted database one version behind:

| Database | Key passed | Exit | What it says |
|---|---|---|---|
| encrypted, behind | yes | **78** | "at schema v88, but this build needs v89" |
| plaintext, behind | — | **78** | same |
| encrypted, behind | **no** | **1** | "cannot read the schema version … No key was supplied (--db-key or YU_DB_KEY)" |
| encrypted, current | **no** | **1** | same — being current changes nothing it can see |

So a keyless machine does not stop at 78 and is not held by
`RestartPreventExitStatus`: systemd retries until `StartLimitBurst` (5 in 300s)
gives up. That is the right outcome — an unreadable database is not a database
proven to be behind — but it means "stops at 78" describes only the machines
that pass a key. The message names the missing key either way. No panic occurs
in any of these cases.

### Migrating it

Run the migrator against the database the service uses:

```sh
cd /path/to/yu_ai_manager
YU_DB_KEY='<the key from server.env>' \
  uv run python scripts/migrate_db_cli.py --db /path/to/data/tags.db
```

It migrates and nothing else: it will not create a database (a file reporting
schema version 0 is refused), it does not read `config.json`, and by default it
refuses to migrate when no pre-migration backup could be taken. Its exit codes
are `0` already-current or migrated, `1` migration failed, `3` no backup
possible, `4` could not open the database (wrong key, damaged, permissions),
`5` version 0, `6` another process holds the write lock.

**The key matters.** Until v4.730.3 the Python side could only open databases
encrypted with its built-in key, so a service whose `YU_DB_KEY` you generated
yourself — which `ExecStartPre` requires you to do — could not be migrated from
Python at all. Pass `--db-key`, or set `YU_DB_KEY`, and it can.

**What the key may contain.** Not whitespace, and none of `' " ; \ & , } ]`.
The migrator has always enforced this; the server did not, so a key holding one
of them produced a database that started fine and could never be migrated —
`openssl rand -hex 32`, which `server.env.example` prescribes, always passes.
Since v4.732.22 the server refuses such a key when it would *create* a
database, and warns (without stopping) when one already exists: that database
must be re-keyed before it can be migrated.

A generated key also rules out a Python backend. The Python *server* reads no
key from the environment — it opens every connection with its built-in one —
so a deployment that sets `YU_PYTHON_URL` has a backend that cannot open this
database at all. yu-server says so at start-up and stops counting Python as a
migrator, which turns "serve a stale database" into the usual exit 78 with the
migration command. Only `scripts/migrate_db_cli.py` takes `YU_DB_KEY`.

### Doing it automatically

`deploy/yu-db-migrate.service` runs that command once, before the server
starts, so an unattended machine recovers without waiting for you:

```sh
install -m644 deploy/yu-db-migrate.service ~/.config/systemd/user/
sed -i "s|__SOURCE_DIR__|$PWD|; s|__UV__|$(command -v uv)|" \
  ~/.config/systemd/user/yu-db-migrate.service
systemctl --user daemon-reload
systemctl --user enable yu-db-migrate.service
```

Both placeholders must be replaced with absolute paths. systemd does not expand
environment variables in `WorkingDirectory`, and while it accepts a bare program
name in `ExecStart`, it resolves it against a fixed PATH that does **not**
include `~/.local/bin` — the unit would verify clean and then fail with
`203/EXEC`.

Leaving either placeholder unreplaced is safe: `ConditionPathExists` then does
not match, systemd records the unit as skipped rather than failed, and the
server behaves exactly as it did before — refusing with 78. The same holds if
`uv` is later removed or moved; the unit names the interpreter as a condition
of its own, because with only the script named it passed the condition and
then died with `203/EXEC` (measured). That is also what happens
on a machine with no Python tree, which is deliberate: the server unit pairs
this one with `Wants=`, never `Requires=`, so a failed or skipped migration
never turns "the database needs migrating" into "a dependency failed".

`TimeoutStartSec=1800` stays generous on purpose. The chain itself is quick —
measured on an empty but schema-complete database, v1 to v89 takes about 2.4
seconds — but that is a floor, not an estimate: most of the cost lives in the
28 steps that transform data, and that is proportional to your library. Time
your own (`time uv run python scripts/migrate_db_cli.py …`) before lowering it.
A migration killed halfway leaves the ledger at whatever step it reached.

If you *do* run a Python backend alongside it, set `YU_PYTHON_URL` in
`server.env`. That declares the migrator, and a stale database then warns once
and serves instead of refusing — which is only correct when Python really is
there to bring it up.

Other start-up failures get five attempts in five minutes
(`StartLimitBurst`/`StartLimitIntervalSec`). A migration already in progress
holds the write lock, so a start during one fails; it recovers on retry. If the
migration outlasts the five attempts systemd marks the unit failed — clear that
with `systemctl --user reset-failed yu-server` before starting again.

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
