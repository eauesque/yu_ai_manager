# Guida alla Distribuzione e Operatività

Procedure per gestire YU AI Manager in ambienti di produzione.

## 1. Panoramica

Ci sono principalmente 3 pattern di utilizzo.

| Pattern | Utilizzo | Configurazione |
|---------|----------|----------------|
| Esecuzione diretta | Uso personale, sviluppo | Avvio con Python + venv |
| Docker | Gestione server | Quart + Nginx con docker-compose |
| Reverse proxy | Pubblicazione esterna | Posizionato dietro web server esistente |

In tutti i casi, i dati vengono salvati in `data/tags.db` (SQLite). Non è necessario un server DB esterno.

---

## 2. Esecuzione Diretta (Sviluppo / Uso Personale)

### Setup

```bash
# Ottenere il repository
git clone <repository-url> && cd yu_ai_manager

# Creazione ambiente virtuale Python
python -m venv venv

# Attivazione ambiente virtuale
# Linux / macOS
source venv/bin/activate
# Windows (PowerShell)
.\venv\Scripts\Activate.ps1
# Windows (Git Bash)
source venv/Scripts/activate

# Installazione pacchetti dipendenti
uv pip install -r requirements.txt

# Build frontend
pnpm install && pnpm run build

# Avvio
python web_ui.py --db data/tags.db
```

Aprire `http://localhost:5000` nel browser.

### Configurazione Argomenti con launch-args.txt

Copiare `launch-args.txt.example` in `launch-args.txt` e modificarlo per fissare gli argomenti di avvio. Gli argomenti CLI hanno la precedenza.

```txt
# Cambio porta
--port 5100
# Pubblicazione LAN (binding 0.0.0.0)
--lan
# Autenticazione PIN
--pin 1234
```

### Servizio systemd (Linux)

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

### Servizio Windows

Il modo più semplice è registrare `start.bat` nel Task Scheduler. Configurarlo per l'esecuzione "All'accesso".

---

## 3. Deploy Docker

### Avvio Rapido

```bash
# Preparare il file di configurazione
cp config.json.example config.json
# Modificare config.json (pin, scan_roots ecc.)

mkdir -p data

# Build & avvio
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

Accessibile su `http://localhost` (tramite Nginx).

### Struttura docker-compose.prod.yml

- **app**: Applicazione Quart (porta 5000, solo interna)
- **nginx**: Reverse proxy (porta 80 esposta esternamente)

### Mount dei Volumi

| Host | Container | Utilizzo |
|------|-----------|----------|
| `data/` | `/app/data/` | Persistenza file DB |
| `config.json` | `/app/config.json` | File configurazione (sola lettura) |
| `static/` | `/app/static/` | File statici distribuiti direttamente da Nginx |

Per le cartelle immagini, aggiungere un mount aggiuntivo con il percorso specificato in `scan_roots` di `config.json`.

```yaml
# Aggiungere a docker-compose.prod.yml
volumes:
  - /path/to/images:/images:ro
```

### Variabili d'Ambiente

Copiare `deploy/.env.example` in `deploy/.env` e modificarlo.

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `NGINX_PORT` | `80` | Porta pubblica Nginx |
| `UPSTREAM_HOST` | `app` | Nome container Quart (non modificare) |
| `UPSTREAM_PORT` | `5000` | Porta Quart (non modificare) |

### Uso con Podman

Funziona anche con Podman al posto di Docker. Installare `podman compose` o `podman-compose` e usare gli stessi comandi. Per i dettagli vedere `docs/it/installation/podman.md`.

---

## 4. Configurazione Reverse Proxy

### Punti Chiave della Configurazione Nginx

`deploy/nginx.conf.template` contiene una configurazione pratica. I punti principali sono:

- **File statici**: Distribuzione diretta di `/static/` da Nginx (bypass Quart)
- **SSE**: `/api/events/` con `proxy_buffering off` per disabilitare il buffering
- **Limite upload**: `client_max_body_size 100m` (allineato al lato Quart)
- **Gzip**: Compressione JSON, CSS, JS

### SSL/TLS (Let's Encrypt)

La configurazione Nginx Docker è solo HTTP. Per HTTPS ci sono 2 metodi.

**Metodo 1: Proxy anteriore (consigliato)**

Posizionare Cloudflare, Caddy, Traefik ecc. davanti per la terminazione HTTPS.

```
Client --HTTPS--> Caddy/Traefik --HTTP--> Nginx:80 --> Quart:5000
```

**Metodo 2: Aggiunta SSL diretta a Nginx**

Aggiungere `listen 443 ssl;` e il percorso del certificato a `nginx.conf.template`, e ottenere il certificato Let's Encrypt con certbot.

### Configurazione Trusted Proxy

Con accesso tramite reverse proxy, specificare gli IP da fidarsi in `config.json`.

```json
{
  "server": {
    "trusted_proxy_ips": ["127.0.0.1", "::1", "172.16.0.0/12"]
  }
}
```

Questo permette la corretta elaborazione degli header `X-Forwarded-For` / `X-Forwarded-Proto`. Supporta la notazione CIDR.

---

## 5. Configurazione Autenticazione

Sono disponibili 4 tipi di autenticazione. Combinarli in base all'utilizzo.

### Autenticazione PIN (Per accesso browser)

```json
{ "pin": "your-secret-pin" }
```

Con pubblicazione LAN (`--lan` o binding `0.0.0.0`) il PIN è obbligatorio. Il binding `0.0.0.0` senza PIN impostato viene rifiutato all'avvio.

### Autenticazione API Key (Per accesso programmatico)

Emettere una API key dalla schermata Settings e aggiungerla all'header della richiesta.

```bash
curl -H "Authorization: Bearer sk_..." http://localhost:5000/api/search
```

Con autenticazione API key l'header CSRF (`X-Requested-With`) non è necessario.

### Autenticazione Trusted Proxy

Utilizzabile in configurazioni in cui il reverse proxy aggiunge l'header `X-Remote-User`. L'impostazione di `trusted_proxy_ips` è obbligatoria.

### Modalità LAN Share

È possibile emettere link di condivisione guest tramite il percorso `/s/`. Salta il PIN e autentica individualmente con token.

---

## 6. Backup e Ripristino

I file da sottoporre a backup periodicamente sono 3:

| File | Contenuto |
|------|-----------|
| `data/tags.db` | DB SQLite contenente tutti i metadati, tag e impostazioni |
| `config.json` | Configurazione applicazione |
| `data/secret.key`, `data/secret.salt` | Chiavi di crittografia (usate per la crittografia delle impostazioni) |

### Procedura di Backup

```bash
# Copia DB (sicura anche in esecuzione)
sqlite3 data/tags.db ".backup backup/tags_$(date +%Y%m%d).db"

# Impostazioni e chiavi di crittografia
cp config.json data/secret.key data/secret.salt backup/
```

### Procedura di Ripristino

Posizionare i file di backup nel percorso originale e riavviare il server. Le migrazioni DB vengono applicate automaticamente all'avvio.

Se si perdono le chiavi di crittografia (`secret.key`, `secret.salt`), i valori di impostazione crittografati (credenziali API ecc.) non potranno essere decifrati. Assicurarsi di fare il backup.

---

## 7. Procedura di Aggiornamento

```bash
# 1. Fermare il server
# 2. Aggiornare il codice
git pull

# 3. Aggiornare i pacchetti dipendenti
source venv/bin/activate  # o .\venv\Scripts\Activate.ps1
uv pip install -r requirements.txt

# 4. Rebuild frontend
pnpm install && pnpm run build

# 5. Avviare il server
python web_ui.py --db data/tags.db
```

La migrazione schema DB viene eseguita automaticamente all'avvio. Non è necessario alcun intervento manuale.

Per Docker basta eseguire un rebuild.

```bash
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

---

## 8. Monitoraggio e Log

### Streaming Log

I log in tempo reale sono visibili dalla scheda Settings > Logs. Vengono trasmessi in streaming al browser tramite SSE (`/api/logs/stream`).

I log storici sono ottenibili da `/api/logs/recent`.

### Health Check

Lo stato operativo è verificabile dall'endpoint `/api/server-info`.

```bash
curl http://localhost:5000/api/server-info
```

Vengono restituite informazioni su versione, versione schema DB, timezone ecc. Usare questo endpoint per i health check degli strumenti di monitoraggio.

### Diagnostica tramite MCP

Chiamando il tool `debug_health_check` da un client MCP (Claude Desktop ecc.) è possibile eseguire in batch il controllo integrità DB, verifica funzionamento ricerca e validazione conteggi.

## 1. Panoramica

Ci sono 3 pattern operativi principali.

| Pattern | Uso | Configurazione |
|---------|------|------|
| Esecuzione diretta | Uso personale, sviluppo | Python + venv startup |
| Docker | Operazione server | docker-compose con Quart + Nginx |
| Reverse proxy | Accesso pubblico esterno | Dietro server web esistente |

In tutti i casi, dati salvati in `data/tags.db` (SQLite). Nessun server DB esterno richiesto.

---

## 2. Esecuzione diretta (sviluppo, uso personale)

### Setup

```bash
# Ottieni repo
git clone <repository-url> && cd yu_ai_manager

# Crea virtual environment Python
python -m venv venv

# Attiva virtual environment
# Linux / macOS
source venv/bin/activate
# Windows (PowerShell)
.\venv\Scripts\Activate.ps1
# Windows (Git Bash)
source venv/Scripts/activate

# Installa dipendenze
uv pip install -r requirements.txt

# Build frontend
pnpm install && pnpm run build

# Avvia
python web_ui.py --db data/tags.db
```

Apri browser su `http://localhost:5000`.

### Configurazione argomenti con launch-args.txt

Copia `launch-args.txt.example` a `launch-args.txt` e modifica per fissare argomenti startup. Argomenti CLI hanno priorità.

```txt
# Cambia porta
--port 5100
# Accesso LAN (bind 0.0.0.0)
--lan
# Autenticazione PIN
--pin 1234
```

### Servizio systemd (Linux)

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
