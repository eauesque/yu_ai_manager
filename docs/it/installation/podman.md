# Setup con Podman

L'ambiente container di YU AI Manager supporta sia Docker che Podman. Gli script di gestione (`scripts/yu-docker.sh`, `tools/docker-build.sh`) rilevano automaticamente il runtime installato.

---

## Prerequisiti

- Podman 4.0 o superiore
- Plugin `podman compose` (Podman 4.7+) o `podman-compose` (pip)

### Installazione di Podman

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

### Installazione degli Strumenti Compose

Per usare `docker-compose.yml` con Podman, è necessario uno dei seguenti.

```bash
# Metodo 1: podman-compose (pip, leggero)
uv pip install podman-compose

# Metodo 2: plugin podman compose (Podman 4.7+)
# Potrebbe essere incluso con podman stesso. Verificare con:
podman compose version
```

---

## Utilizzo Base

### Tramite Script di Gestione (consigliato)

Lo script rileva automaticamente Docker / Podman, quindi i comandi sono uguali a Docker.

```bash
# Setup iniziale
./scripts/yu-docker.sh init

# Build
./scripts/yu-docker.sh build

# Avvio
./scripts/yu-docker.sh up

# Log
./scripts/yu-docker.sh logs

# Stop
./scripts/yu-docker.sh down
```

### Comandi Diretti

```bash
# Build
podman build -t yu-ai-manager .

# Avvio (compose)
podman compose up yu-ai-manager -d

# Avvio (singolo)
podman run -d --name yu-ai-manager \
  -p 5000:5000 \
  -v ./data:/app/data \
  -v ./uploads:/app/uploads \
  yu-ai-manager

# Build variante Hailo
./tools/docker-build.sh --hailo --hailo-wheel ~/hailort/dist/*.whl
```

---

## Differenze con Docker e Considerazioni

### Modalità Rootless

Podman funziona di default in modalità rootless (senza privilegi root). Funziona nella maggior parte dei casi, ma prestare attenzione ai seguenti punti.

| Elemento | Impatto | Soluzione |
|----------|---------|-----------|
| Porta inferiore a 1024 | Non bindabile in rootless | Nessun problema poiché si usa la porta 5000 |
| Passthrough dispositivo | Accesso a `/dev/hailort0` ecc. richiede permessi | `podman run --device` + permessi gruppo, o `sudo podman` |
| Mappatura UID | `appuser` nel container e UID host differiscono | Se ci sono problemi di permessi sui volumi, correggere con `podman unshare chown` |

```bash
# Verifica mappatura UID
podman unshare cat /proc/self/uid_map

# Esempio correzione permessi volume
podman unshare chown -R 1000:1000 ./data ./uploads
```

### Passthrough Dispositivo Hailo

```bash
# In rootless potrebbe non essere possibile accedere a /dev/hailort0
# Metodo 1: Aggiungere l'utente al gruppo hailort
sudo usermod -aG hailort $USER

# Metodo 2: Eseguire in modalità rootful
sudo podman compose -f docker-compose.yml -f docker-compose.hailo.yml up yu-ai-manager
```

### Rete

La rete predefinita di Podman è `podman`, equivalente a `bridge` di Docker. Le reti personalizzate (`debug-net`) in `docker-compose.debug.yml` funzionano allo stesso modo.

### Volumi

Supporta sia volumi nominati che bind mount. I bind mount (`./data:/app/data`) in `docker-compose.yml` funzionano direttamente.

### Integrazione systemd (gestione server Linux)

Podman si integra facilmente con systemd. Per configurare l'avvio automatico:

```bash
# Genera unit systemd dopo l'avvio del container
podman generate systemd --new --name yu-ai-manager > ~/.config/systemd/user/yu-ai-manager.service

# Abilitazione
systemctl --user daemon-reload
systemctl --user enable --now yu-ai-manager.service

# Avvio automatico dei servizi utente anche all'avvio della macchina (linger)
loginctl enable-linger $USER
```

---

## Alias CLI Docker (opzionale)

Per usare direttamente documentazione e script per Docker:

```bash
# Aggiungere a ~/.bashrc o ~/.zshrc
alias docker=podman
alias docker-compose=podman-compose
```

Gli script di gestione rilevano automaticamente, quindi questi alias non sono obbligatori.

---

## Risoluzione dei Problemi

### Avviso `WARN[0000] "/" is not a shared mount`

```bash
# Può verificarsi con Podman rootless. Per eliminarlo se indesiderato:
podman system migrate
```

### `podman compose` Non Trovato

```bash
# Per Podman inferiore a 4.7, il plugin non è incluso
# Installare podman-compose con pip
uv pip install podman-compose
```

### Impossibile Accedere a localhost dal Container

In Podman rootless usare `host.containers.internal` (equivalente a `host.docker.internal` di Docker).

---

## Riepilogo Compatibilità

| File | Compatibilità Podman | Note |
|------|---------------------|------|
| `Dockerfile` | OK | Specifica OCI standard |
| `Dockerfile.debug` | OK | |
| `Dockerfile.playwright` | OK | |
| `deploy/Dockerfile` | OK | |
| `docker-compose.yml` | OK | |
| `docker-compose.debug.yml` | OK | |
| `docker-compose.hailo.yml` | OK | Attenzione ai permessi passthrough dispositivo |
| `deploy/docker-compose.prod.yml` | OK | |
| `tools/docker-build.sh` | OK | Rilevamento automatico runtime |
| `scripts/yu-docker.sh` | OK | Rilevamento automatico runtime |
| `.dockerignore` | OK | Podman usa lo stesso file |

## Installazione Podman

```bash
# Linux
sudo apt-get install podman

# macOS
brew install podman
```

## Build immagine

```bash
podman build -t yu-ai-manager:latest .
```

## Avvia container

```bash
podman run -d \
  --name yu-ai-manager \
  -p 5000:5000 \
  -v /path/data:/app/data \
  yu-ai-manager:latest
```

## Variabili ambiente

```bash
-e YU_PIN=1234
-e YU_PORT=5000
-e YU_LAN=1
```
