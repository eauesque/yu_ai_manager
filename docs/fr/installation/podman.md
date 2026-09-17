# Configuration avec Podman

L'environnement conteneurisé de YU AI Manager est compatible avec Docker et Podman. Les scripts de gestion (`scripts/yu-docker.sh`, `tools/docker-build.sh`) détectent automatiquement le runtime installé.

---

## Prérequis

- Podman 4.0 ou supérieur
- Plugin `podman compose` (Podman 4.7+) ou `podman-compose` (pip)

### Installation de Podman

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

### Installation de l'Outil Compose

Pour utiliser `docker-compose.yml` avec Podman, l'une des méthodes suivantes est nécessaire.

```bash
# Méthode 1 : podman-compose (pip, léger)
uv pip install podman-compose

# Méthode 2 : plugin podman compose (Podman 4.7+)
# Peut être inclus avec podman. Vérifier avec :
podman compose version
```

---

## Utilisation de Base

### Via le script de gestion (recommandé)

Le script détectant automatiquement Docker/Podman, les commandes sont identiques à Docker.

```bash
# Configuration initiale
./scripts/yu-docker.sh init

# Build
./scripts/yu-docker.sh build

# Démarrage
./scripts/yu-docker.sh up

# Logs
./scripts/yu-docker.sh logs

# Arrêt
./scripts/yu-docker.sh down
```

### Commandes Directes

```bash
# Build
podman build -t yu-ai-manager .

# Démarrage (compose)
podman compose up yu-ai-manager -d

# Démarrage (autonome)
podman run -d --name yu-ai-manager \
  -p 5000:5000 \
  -v ./data:/app/data \
  -v ./uploads:/app/uploads \
  yu-ai-manager

# Build variante Hailo
./tools/docker-build.sh --hailo --hailo-wheel ~/hailort/dist/*.whl
```

---

## Différences avec Docker et Points d'Attention

### Mode Rootless

Podman fonctionne par défaut en rootless (sans privilèges root). Dans la plupart des cas, cela fonctionne tel quel, mais attention aux points suivants.

| Élément | Impact | Solution |
|---|---|---|
| Port inférieur à 1024 | Pas de bind en rootless | Pas de problème, le port 5000 est utilisé |
| Passthrough de périphérique | Accès à `/dev/hailort0` etc. nécessite des permissions | `podman run --device` + permissions de groupe, ou `sudo podman` |
| Mapping UID | L'UID de `appuser` dans le conteneur diffère de l'hôte | En cas de problème de permissions de volume, corriger avec `podman unshare chown` |

```bash
# Vérifier le mapping UID
podman unshare cat /proc/self/uid_map

# Exemple de correction de permissions de volume
podman unshare chown -R 1000:1000 ./data ./uploads
```

### Passthrough du Périphérique Hailo

```bash
# En rootless, l'accès à /dev/hailort0 peut être impossible
# Méthode 1 : ajouter l'utilisateur au groupe hailort
sudo usermod -aG hailort $USER

# Méthode 2 : exécuter en rootful
sudo podman compose -f docker-compose.yml -f docker-compose.hailo.yml up yu-ai-manager
```

### Réseau

Le réseau par défaut de Podman est `podman`, équivalent du `bridge` de Docker. Le réseau personnalisé (`debug-net`) de `docker-compose.debug.yml` fonctionne aussi tel quel.

```bash
# Vérifier le réseau
podman network ls
```

### Volumes

Les volumes nommés et les bind mounts sont supportés. Le bind mount (`./data:/app/data`) de `docker-compose.yml` fonctionne tel quel.

### Intégration systemd (exploitation serveur Linux)

Podman s'intègre facilement avec systemd. Pour configurer le démarrage automatique :

```bash
# Générer une unité systemd après le démarrage du conteneur
podman generate systemd --new --name yu-ai-manager > ~/.config/systemd/user/yu-ai-manager.service

# Activer
systemctl --user daemon-reload
systemctl --user enable --now yu-ai-manager.service

# Démarrage automatique du service utilisateur au boot (linger)
loginctl enable-linger $USER
```

---

## Alias Compatible Docker CLI (optionnel)

Si vous voulez utiliser tel quel la documentation et les scripts conçus pour Docker :

```bash
# Ajouter à ~/.bashrc ou ~/.zshrc
alias docker=podman
alias docker-compose=podman-compose
```

Le script de gestion détectant automatiquement, cet alias n'est pas obligatoire.

---

## Dépannage

### Avertissement `WARN[0000] "/" is not a shared mount`

```bash
# Peut apparaître avec Podman rootless. Inoffensif, mais pour le supprimer :
podman system migrate
```

### `podman compose` introuvable

```bash
# Avec Podman inférieur à 4.7, le plugin n'est pas inclus
# Installer podman-compose via pip
uv pip install podman-compose
```

### Accès à localhost impossible depuis le conteneur

En Podman rootless, utiliser `host.containers.internal` (équivalent de `host.docker.internal` de Docker).

```bash
# Pour accéder au service web depuis le conteneur debug,
# pas de problème car passage par le réseau de docker-compose.debug.yml (http://web:5000)
```

### Nettoyage des Images

```bash
# Supprimer les images non utilisées
podman image prune -a

# Supprimer toutes les ressources
podman system prune -a
```

---

## Résumé de Compatibilité

| Fichier | Compatible Podman | Remarques |
|---|---|---|
| `Dockerfile` | OK | Spécification OCI standard |
| `Dockerfile.debug` | OK | |
| `Dockerfile.playwright` | OK | |
| `deploy/Dockerfile` | OK | |
| `docker-compose.yml` | OK | |
| `docker-compose.debug.yml` | OK | |
| `docker-compose.hailo.yml` | OK | Attention aux permissions pour le passthrough de périphérique |
| `deploy/docker-compose.prod.yml` | OK | |
| `tools/docker-build.sh` | OK | Détection automatique du runtime |
| `scripts/yu-docker.sh` | OK | Détection automatique du runtime |
| `.dockerignore` | OK | Podman lit le même fichier |
