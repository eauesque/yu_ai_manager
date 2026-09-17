# Guide de déploiement et d'exploitation

Résumé des procédures pour exploiter YU AI Manager en environnement de production.

## 1. Vue d'ensemble

Il existe principalement 3 patterns d'exploitation.

| Pattern | Usage | Configuration |
|---------|------|------|
| Exécution directe | Usage personnel, développement | Démarrage avec Python + venv |
| Docker | Exploitation serveur | Quart + Nginx avec docker-compose |
| Proxy inverse | Publication externe | Placement derrière un serveur web existant |

Dans tous les cas, les données sont sauvegardées dans `data/tags.db` (SQLite). Aucun serveur DB externe n'est nécessaire.

---

## 2. Exécution directe (développement / usage personnel)

### Configuration

```bash
# Récupérer le dépôt
git clone <repository-url> && cd yu_ai_manager

# Créer l'environnement virtuel Python
python -m venv venv

# Activer l'environnement
# Linux / macOS
source venv/bin/activate
# Windows (PowerShell)
.\venv\Scripts\Activate.ps1
# Windows (Git Bash)
source venv/Scripts/activate

# Installer les paquets de dépendances
uv pip install -r requirements.txt

# Build du frontend
pnpm install && pnpm run build

# Démarrage
python web_ui.py --db data/tags.db
```

Ouvrir `http://localhost:5000` dans le navigateur.

### Configuration des arguments avec launch-args.txt

Copier `launch-args.txt.example` en `launch-args.txt` et modifier pour fixer les arguments de démarrage. Les arguments CLI ont priorité.

```txt
# Changer le port
--port 5100
# Accès LAN (bind 0.0.0.0)
--lan
# Authentification PIN
--pin 1234
```

### Création d'un service systemd (Linux)

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

---

## 3. Déploiement Docker

### Démarrage rapide

```bash
# Préparer le fichier de configuration
cp config.json.example config.json
# Modifier config.json (pin, scan_roots, etc.)

mkdir -p data

# Build & démarrage
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

Accessible via `http://localhost` (via Nginx).

### Structure de docker-compose.prod.yml

- **app** : Application Quart (port 5000, interne uniquement)
- **nginx** : Proxy inverse (port 80 exposé externalement)

### Montages de volumes

| Hôte | Conteneur | Usage |
|-------|---------|------|
| `data/` | `/app/data/` | Persistance du fichier DB |
| `config.json` | `/app/config.json` | Fichier de configuration (lecture seule) |
| `static/` | `/app/static/` | Fichiers statiques distribués directement par Nginx |

Pour les dossiers d'images, ajouter un montage correspondant au chemin spécifié dans `scan_roots` de `config.json`.

```yaml
# Ajouter dans docker-compose.prod.yml
volumes:
  - /path/to/images:/images:ro
```

---

## 4. Configuration du proxy inverse

### Points importants de la configuration Nginx

- **Fichiers statiques** : Distribuer `/static/` directement depuis Nginx (bypass Quart)
- **SSE** : `/api/events/` avec `proxy_buffering off` pour désactiver le buffering
- **Limite d'upload** : `client_max_body_size 100m` (correspondre côté Quart)
- **Gzip** : Compresser JSON, CSS, JS

### SSL/TLS (Let's Encrypt)

**Méthode 1 : Proxy amont (recommandé)**

Placer Cloudflare, Caddy, Traefik, etc. en amont pour la terminaison HTTPS.

```
Client --HTTPS--> Caddy/Traefik --HTTP--> Nginx:80 --> Quart:5000
```

**Méthode 2 : Ajouter SSL directement à Nginx**

Ajouter `listen 443 ssl;` et le chemin du certificat dans `nginx.conf.template`, obtenir un certificat Let's Encrypt avec certbot.

### Configuration Trusted Proxy

En cas d'accès via proxy inverse, spécifier les IPs de confiance dans `config.json`.

```json
{
  "server": {
    "trusted_proxy_ips": ["127.0.0.1", "::1", "172.16.0.0/12"]
  }
}
```

Cela traite correctement les en-têtes `X-Forwarded-For` / `X-Forwarded-Proto`. Notation CIDR supportée.

---

## 5. Configuration de l'authentification

4 types d'authentification sont disponibles. Combiner selon les besoins.

### Authentification PIN (pour accès navigateur)

```json
{ "pin": "votre-pin-secret" }
```

En cas d'exposition LAN (`--lan` ou bind `0.0.0.0`), la configuration du PIN est obligatoire. Démarrage refusé si bind sur `0.0.0.0` sans PIN.

### Authentification par clé API (pour accès programmatique)

Émettre une clé API dans l'écran Settings et l'ajouter à l'en-tête de requête.

```bash
curl -H "Authorization: Bearer sk_..." http://localhost:5000/api/search
```

L'en-tête CSRF (`X-Requested-With`) n'est pas nécessaire avec l'authentification par clé API.

### Authentification Trusted Proxy

Utilisable dans une configuration où le proxy inverse ajoute l'en-tête `X-Remote-User`. Configuration de `trusted_proxy_ips` obligatoire.

### Mode LAN Share

Des liens de partage invité peuvent être émis via le chemin `/s/`. Ignore le PIN et authentifie individuellement par token.

---

## 6. Sauvegarde et restauration

Les fichiers à sauvegarder régulièrement sont les 3 types suivants.

| Fichier | Contenu |
|---------|------|
| `data/tags.db` | DB SQLite contenant toutes les métadonnées, tags et paramètres |
| `config.json` | Configuration de l'application |
| `data/secret.key`, `data/secret.salt` | Clés de chiffrement (utilisées pour le chiffrement des paramètres) |

### Procédure de sauvegarde

```bash
# Copie de la DB (sûre même en cours de fonctionnement)
sqlite3 data/tags.db ".backup backup/tags_$(date +%Y%m%d).db"

# Paramètres et clés de chiffrement
cp config.json data/secret.key data/secret.salt backup/
```

### Procédure de restauration

Il suffit de placer les fichiers de sauvegarde à leur emplacement d'origine et de redémarrer le serveur. Les migrations de schéma DB sont appliquées automatiquement au démarrage.

---

## 7. Procédure de mise à jour

```bash
# 1. Arrêter le serveur
# 2. Mettre à jour le code
git pull

# 3. Mettre à jour les paquets de dépendances
source venv/bin/activate
uv pip install -r requirements.txt

# 4. Reconstruire le frontend
pnpm install && pnpm run build

# 5. Démarrer le serveur
python web_ui.py --db data/tags.db
```

La migration du schéma DB est exécutée automatiquement au démarrage. Aucune opération manuelle n'est nécessaire.

Pour Docker, reconstruire suffit :

```bash
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

---

## 8. Surveillance et logs

### Streaming de logs

Les logs en temps réel peuvent être consultés dans l'onglet Settings > Logs. Ils sont streamés vers le navigateur via SSE (`/api/logs/stream`).

Les logs passés peuvent être obtenus via `/api/logs/recent`.

### Vérification de santé

L'état de fonctionnement peut être vérifié via l'endpoint `/api/server-info`.

```bash
curl http://localhost:5000/api/server-info
```

Version, version du schéma DB, fuseau horaire, etc. sont retournés. Utiliser cet endpoint pour les vérifications de santé des outils de surveillance.

### Diagnostic via MCP

En appelant l'outil `debug_health_check` depuis un client MCP (Claude Desktop, etc.), les vérifications d'intégrité DB, de fonctionnement de la recherche et de validation des comptages peuvent être exécutées en lot.
