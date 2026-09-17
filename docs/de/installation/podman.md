# Einrichtung mit Podman

Die Container-Umgebung von YU AI Manager unterstützt sowohl Docker als auch Podman.
Die Verwaltungsskripte (`scripts/yu-docker.sh`, `tools/docker-build.sh`) erkennen die installierte Runtime automatisch.

---

## Voraussetzungen

- Podman 4.0 oder höher
- `podman compose`-Plugin (Podman 4.7+) oder `podman-compose` (pip)

### Podman installieren

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

### Compose-Tool installieren

Um `docker-compose.yml` mit Podman zu verwenden, wird eines der folgenden Tools benötigt.

```bash
# Variante 1: podman-compose (pip, leichtgewichtig)
uv pip install podman-compose

# Variante 2: podman compose-Plugin (Podman 4.7+)
# Manchmal in Podman selbst enthalten. Prüfen mit:
podman compose version
```

---

## Grundlegende Verwendung

### Über das Verwaltungsskript (empfohlen)

Da das Skript Docker / Podman automatisch erkennt, sind die Befehle mit Docker identisch.

```bash
# Initiale Einrichtung
./scripts/yu-docker.sh init

# Build
./scripts/yu-docker.sh build

# Start
./scripts/yu-docker.sh up

# Log
./scripts/yu-docker.sh logs

# Stopp
./scripts/yu-docker.sh down
```

### Direkte Befehle

```bash
# Build
podman build -t yu-ai-manager .

# Start (compose)
podman compose up yu-ai-manager -d

# Start (einzeln)
podman run -d --name yu-ai-manager \
  -p 5000:5000 \
  -v ./data:/app/data \
  -v ./uploads:/app/uploads \
  yu-ai-manager

# Hailo-Variante bauen
./tools/docker-build.sh --hailo --hailo-wheel ~/hailort/dist/*.whl
```

---

## Unterschiede und Hinweise zu Docker

### Rootless-Modus

Podman läuft standardmäßig rootless (ohne Root-Rechte).
In den meisten Fällen funktioniert alles unverändert, beachten Sie jedoch Folgendes.

| Element | Auswirkung | Maßnahme |
|---|---|---|
| Port unter 1024 | Im Rootless-Modus nicht bindbar | Port 5000 wird verwendet, kein Problem |
| Geräte-Durchreichung | `/dev/hailort0` usw. benötigt Rechte | `podman run --device` + Gruppenrechte, oder `sudo podman` |
| UID-Mapping | `appuser` im Container und Host-UID unterscheiden sich | Bei Berechtigungsproblemen mit `podman unshare chown` korrigieren |

```bash
# UID-Mapping prüfen
podman unshare cat /proc/self/uid_map

# Beispiel zur Korrektur von Volume-Rechten
podman unshare chown -R 1000:1000 ./data ./uploads
```

### Hailo-Gerätedurchreichung

```bash
# Im Rootless-Modus kann /dev/hailort0 manchmal nicht zugänglich sein
# Variante 1: Benutzer zur Gruppe hailort hinzufügen
sudo usermod -aG hailort $USER

# Variante 2: Rootful ausführen
sudo podman compose -f docker-compose.yml -f docker-compose.hailo.yml up yu-ai-manager
```

### Netzwerk

Das Standardnetzwerk von Podman heißt `podman` und entspricht Dockers `bridge`.
Auch das benutzerdefinierte Netzwerk (`debug-net`) aus `docker-compose.debug.yml` funktioniert unverändert.

```bash
# Netzwerk prüfen
podman network ls
```

### Volumes

Sowohl Named Volumes als auch Bind-Mounts werden unterstützt.
Die Bind-Mounts aus `docker-compose.yml` (`./data:/app/data`) funktionieren unverändert.

### systemd-Integration (Linux-Server-Betrieb)

Podman lässt sich leicht mit systemd integrieren. So konfigurieren Sie den Autostart:

```bash
# Nach Containerstart systemd-Unit generieren
podman generate systemd --new --name yu-ai-manager > ~/.config/systemd/user/yu-ai-manager.service

# Aktivieren
systemctl --user daemon-reload
systemctl --user enable --now yu-ai-manager.service

# Auch nach Systemstart Benutzerdienste automatisch starten (linger)
loginctl enable-linger $USER
```

---

## Docker-CLI-kompatible Aliase (optional)

Wenn Sie Docker-Dokumentation oder -Skripte unverändert nutzen möchten:

```bash
# In ~/.bashrc oder ~/.zshrc einfügen
alias docker=podman
alias docker-compose=podman-compose
```

Da die Verwaltungsskripte automatische Erkennung haben, sind diese Aliase nicht zwingend erforderlich.

---

## Fehlerbehebung

### Warnung `WARN[0000] "/" is not a shared mount`

```bash
# Kann in Rootless-Podman auftreten. Harmlos, aber falls Sie sie entfernen möchten:
podman system migrate
```

### `podman compose` nicht gefunden

```bash
# Bei Podman unter 4.7 ist das Plugin nicht enthalten
# podman-compose per pip installieren
uv pip install podman-compose
```

### Aus dem Container kann nicht auf localhost zugegriffen werden

Im Rootless-Podman wird `host.containers.internal` verwendet (entspricht Dockers `host.docker.internal`).

```bash
# Beim Zugriff vom Debug-Container auf den Web-Dienst wird
# das Netzwerk aus docker-compose.debug.yml (http://web:5000) verwendet, kein Problem
```

### Images aufräumen

```bash
# Ungenutzte Images löschen
podman image prune -a

# Alle Ressourcen löschen
podman system prune -a
```

---

## Übersicht zur Unterstützung

| Datei | Podman-kompatibel | Hinweis |
|---|---|---|
| `Dockerfile` | OK | Standard-OCI-Spezifikation |
| `Dockerfile.debug` | OK | |
| `Dockerfile.playwright` | OK | |
| `deploy/Dockerfile` | OK | |
| `docker-compose.yml` | OK | |
| `docker-compose.debug.yml` | OK | |
| `docker-compose.hailo.yml` | OK | Bei Gerätedurchreichung auf Rechte achten |
| `deploy/docker-compose.prod.yml` | OK | |
| `tools/docker-build.sh` | OK | Automatische Runtime-Erkennung |
| `scripts/yu-docker.sh` | OK | Automatische Runtime-Erkennung |
| `.dockerignore` | OK | Podman verwendet dieselbe Datei |
