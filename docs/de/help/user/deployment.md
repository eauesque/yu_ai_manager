# Deployment- und Betriebsleitfaden

Zusammenfassung der Verfahren zum Betrieb von YU AI Manager in Produktionsumgebungen.

## 1. Überblick

Drei Hauptbetriebsmuster:

| Muster | Verwendung | Konfiguration |
|---------|------|------|
| Direktausführung | Persönliche Nutzung / Entwicklung | Python + venv starten |
| Docker | Server-Betrieb | docker-compose mit Quart + Nginx |
| Reverse Proxy | Externe Veröffentlichung | Hinter bestehenden Webserver stellen |

In allen Fällen werden Daten in `data/tags.db` (SQLite) gespeichert. Externer DB-Server nicht erforderlich.

---

## 2. Direktausführung (Entwicklung / persönliche Nutzung)

### Setup

```bash
# Repository holen
git clone <repository-url> && cd yu_ai_manager

# Python-Virtualumgebung erstellen
python -m venv venv

# Virtualumgebung aktivieren
# Linux / macOS
source venv/bin/activate
# Windows (PowerShell)
.\venv\Scripts\Activate.ps1
# Windows (Git Bash)
source venv/Scripts/activate

# Abhängigkeitspakete installieren
uv pip install -r requirements.txt

# Frontend-Build
pnpm install && pnpm run build

# Starten
python web_ui.py --db data/tags.db
```

Browser auf `http://localhost:5000` öffnen.

### Argument-Einstellung über launch-args.txt

`launch-args.txt.example` nach `launch-args.txt` kopieren und bearbeiten, um Start-Argumente zu fixieren. CLI-Argumente haben Vorrang.

```txt
# Port ändern
--port 5100
# LAN-Veröffentlichung (0.0.0.0-Binding)
--lan
# PIN-Authentifizierung
--pin 1234
```

### systemd-Service (Linux)

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

### Windows-Service

`start.bat` im Task-Planer registrieren ist am einfachsten. Auf "Bei Anmeldung ausführen" setzen.

---

## 3. Docker-Deployment

### Schnellstart

```bash
# Konfigurationsdatei vorbereiten
cp config.json.example config.json
# config.json bearbeiten (pin, scan_roots usw.)

mkdir -p data

# Bauen und starten
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

Zugriff über `http://localhost` (via Nginx).

### docker-compose.prod.yml-Konfiguration

- **app**: Quart-Anwendung (Port 5000, nur intern)
- **nginx**: Reverse Proxy (Port 80 extern veröffentlicht)

### Volume-Mounts

| Host | Container | Zweck |
|-------|---------|------|
| `data/` | `/app/data/` | DB-Datei-Persistenz |
| `config.json` | `/app/config.json` | Konfigurationsdatei (nur lesen) |
| `static/` | `/app/static/` | Statische Dateien (direkt von Nginx geliefert) |

Bildordner als zusätzliche Mounts in `docker-compose.yml` hinzufügen:

```yaml
volumes:
  - /path/to/images:/images:ro
```

### Umgebungsvariablen

`deploy/.env.example` nach `deploy/.env` kopieren und bearbeiten.

| Variable | Standard | Beschreibung |
|------|----------|------|
| `NGINX_PORT` | `80` | Nginx-Veröffentlichungsport |
| `UPSTREAM_HOST` | `app` | Quart-Container-Name |
| `UPSTREAM_PORT` | `5000` | Quart-Port |

### Bei Verwendung von Podman

Funktioniert auch mit Podman statt Docker. `podman compose` oder `podman-compose` installieren und dieselben Befehle verwenden. Details in `docs/de/installation/podman.md`.

---

## 4. Reverse-Proxy-Konfiguration

### Nginx-Konfigurationspunkte

`deploy/nginx.conf.template` enthält praktische Einstellungen:

- **Statische Dateien**: `/static/` direkt von Nginx liefern (Quart umgehen)
- **SSE**: `/api/events/` mit `proxy_buffering off` Buffer deaktivieren
- **Upload-Limit**: `client_max_body_size 100m` (mit Quart-Seite angleichen)
- **Gzip**: JSON, CSS, JS komprimieren

### SSL/TLS (Let's Encrypt)

Docker-Nginx-Konfiguration ist nur HTTP. Für HTTPS zwei Methoden:

**Methode 1: Vorgelagerter Proxy (empfohlen)**

Cloudflare, Caddy, Traefik usw. vorgelagert stellen und HTTPS terminieren.

```
Client --HTTPS--> Caddy/Traefik --HTTP--> Nginx:80 --> Quart:5000
```

**Methode 2: SSL direkt in Nginx hinzufügen**

`listen 443 ssl;` und Zertifikatspfade zu `nginx.conf.template` hinzufügen und Zertifikat mit certbot besorgen.

### Trusted-Proxy-Konfiguration

Bei Reverse-Proxy-Verwendung vertrauenswürdige IPs in `config.json` angeben:

```json
{
  "server": {
    "trusted_proxy_ips": ["127.0.0.1", "::1", "172.16.0.0/12"]
  }
}
```

---

## 5. Authentifizierungskonfiguration

4 Authentifizierungstypen verfügbar:

### PIN-Authentifizierung (Browser-Zugriff)

```json
{ "pin": "your-secret-pin" }
```

Bei LAN-Veröffentlichung (`--lan` oder `0.0.0.0`-Binding) ist PIN Pflicht.

### API-Schlüssel-Authentifizierung (Programm-Zugriff)

API-Schlüssel über Settings generieren und in Anfrage-Header angeben:

```bash
curl -H "Authorization: Bearer sk_..." http://localhost:5000/api/search
```

CSRF-Header (`X-Requested-With`) bei API-Schlüssel nicht erforderlich.

### Trusted-Proxy-Authentifizierung

Bei Konfiguration mit `X-Remote-User`-Header vom Reverse Proxy verwendbar. `trusted_proxy_ips`-Einstellung erforderlich.

### LAN-Share-Modus

Gast-Freigabelinks über `/s/`-Pfad ausstellen. Überspringt PIN und authentifiziert per Token.

---

## 6. Backup und Wiederherstellung

Regelmäßig zu backuppende Dateien:

| Datei | Inhalt |
|---------|------|
| `data/tags.db` | SQLite-DB mit allen Metadaten, Tags, Einstellungen |
| `config.json` | Anwendungskonfiguration |
| `data/secret.key`, `data/secret.salt` | Verschlüsselungsschlüssel |

### Backup-Verfahren

```bash
# DB-Kopie (auch während des Betriebs sicher)
sqlite3 data/tags.db ".backup backup/tags_$(date +%Y%m%d).db"

# Konfiguration und Verschlüsselungsschlüssel
cp config.json data/secret.key data/secret.salt backup/
```

### Wiederherstellungsverfahren

Backup-Dateien an ursprünglichem Ort platzieren und Server neu starten.
DB-Migrationen werden beim Start automatisch angewendet.

Verlust der Verschlüsselungsschlüssel (`secret.key`, `secret.salt`) macht verschlüsselte Konfigurationswerte (API-Zugangsdaten usw.) unwiederherstellbar.

---

## 7. Upgrade-Verfahren

```bash
# 1. Server stoppen
# 2. Code aktualisieren
git pull

# 3. Abhängigkeitspakete aktualisieren
source venv/bin/activate
uv pip install -r requirements.txt

# 4. Frontend neu bauen
pnpm install && pnpm run build

# 5. Server starten
python web_ui.py --db data/tags.db
```

DB-Schema-Migration wird beim Start automatisch ausgeführt.

Bei Docker nur neu bauen:

```bash
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

---

## 8. Überwachung und Logs

### Log-Streaming

Echtzeit-Logs über Settings > Logs-Tab überprüfen. SSE-Stream zu Browser via `/api/logs/stream`.

Frühere Logs über `/api/logs/recent`.

### Health-Check

`/api/server-info`-Endpunkt für Betriebsstatus:

```bash
curl http://localhost:5000/api/server-info
```

Gibt Version, DB-Schema-Version, Zeitzone usw. zurück. Für Überwachungstools diesen Endpunkt verwenden.

### Diagnose per MCP

`debug_health_check`-Tool von MCP-Client (Claude Desktop usw.) aufrufen führt DB-Konsistenzprüfung, Suchfunktionsprüfung und Zählerverifizierung in einem aus.
