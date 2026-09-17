# Scan

## Enregistrement des Dossiers de Scan

Ajoutez les dossiers à scanner dans Settings > onglet Scan.

- Réorganisation possible par glisser-déposer
- Activation/désactivation via case à cocher
- Plusieurs dossiers peuvent être enregistrés

## Exécution du Scan

- Le scan démarre automatiquement après l'ajout d'un dossier
- Le scan manuel s'exécute depuis la page Tools ou via `trigger_scan` de MCP
- La progression pendant le scan est notifiée en temps réel via SSE

## Scan Automatique (Watcher)

En activant l'extension Auto Scan Watcher, les modifications de fichiers dans les dossiers enregistrés sont détectées automatiquement et scannées.

## Système de Fichiers Distant

Lors du scan de chemins distants comme WSL / NAS / SMB, ajustez les paramètres de timeout dans Settings > onglet Remote FS.

## Scan sur les Grandes Bibliothèques

Points d'attention lors du scan de plusieurs centaines de milliers à plus d'un million de fichiers :

- **La recherche d'images est possible pendant le scan** : l'API de recherche utilise une connexion DB en lecture seule, donc elle n'est pas affectée par le verrou d'écriture du scan
- **Gestion automatique du WAL** : pendant le scan, un checkpoint WAL est exécuté automatiquement tous les 2000 fichiers pour éviter le gonflement du fichier WAL
- **Événement scan.db_busy** : des événements SSE sont envoyés au début/à la fin du scan, permettant au frontend d'afficher l'état occupé

## Processus Worker de Scan

Depuis v3.27.0, le scan s'exécute dans un processus séparé indépendant de web_ui.py. Ainsi, **le scan n'est pas interrompu même si web_ui est redémarré**.

### Fonctionnement

- Lorsque vous démarrez un scan depuis le WebUI, un processus worker démarre en arrière-plan
- Le worker écrit un fichier de progression (JSON) et un fichier PID dans `/tmp/yu-scan/`
- Le WebUI interroge ce fichier de progression et le relaie au frontend via SSE
- Au redémarrage du WebUI, le worker en cours est détecté automatiquement et l'affichage de progression est reconnecté

### Opérations CLI

Le worker peut aussi être contrôlé directement depuis la CLI. Utilisable même lorsque le WebUI est arrêté.

```bash
# Vérifier l'état
python -m core.scan.scan_worker status

# Arrêter un scan en cours (graceful shutdown — enregistre la position d'interruption en DB)
python -m core.scan.scan_worker stop

# Démarrer un scan directement depuis la CLI
python -m core.scan.scan_worker start --db ./tags.db --root /path/to/images

# Options
#   --recursive / --no-recursive  Inclure les sous-répertoires (par défaut : recursive)
#   --scan-zips                   Scanner aussi les images dans les ZIP/7z
#   --force                       Re-scanner les fichiers existants
#   --resume                      Reprendre un scan interrompu
#   --config config.json          Spécifier un fichier de configuration
```

### Mécanismes de Sécurité

- **Surveillance du processus parent** : le worker lancé depuis le WebUI surveille la vie du processus WebUI toutes les 60 secondes. Si le WebUI se termine anormalement, le worker enregistre automatiquement l'interruption et s'arrête
- **Gestion SIGTERM** : avec la commande `stop` ou `kill` envoyant SIGTERM, le processus en cours est terminé, commit en DB, sauvegarde de la position d'interruption, puis sortie
- **Prévention des doublons** : plusieurs workers ne peuvent pas démarrer simultanément

### Dépannage

Si le worker ne répond pas :

```bash
# Vérifier le PID
cat /tmp/yu-scan/worker.pid

# Forcer l'arrêt du processus
kill -9 $(cat /tmp/yu-scan/worker.pid)

# Nettoyer les fichiers résiduels
rm -f /tmp/yu-scan/worker.pid /tmp/yu-scan/progress.json
```

## Erreurs de Scan

Si une erreur survient pendant le scan, vous pouvez la consulter via `get_scan_errors` de MCP.
