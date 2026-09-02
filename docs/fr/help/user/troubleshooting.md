# Dépannage

## Problèmes Courants

### Le serveur ne démarre pas

- Vérifier que l'environnement virtuel Python est activé : `source venv/bin/activate`
- Vérifier que les dépendances sont installées : `uv pip install -r requirements.txt`
- Vérifier que le port n'est pas utilisé : `ss -tlnp | grep 5000`

### Les images ne s'affichent pas

- L'API de miniatures requiert que le fichier image existe physiquement
- Vérifier que les chemins dans la table `files` correspondent aux chemins réels
- Vérifier que les chemins des racines de scan sont corrects

### Accès impossible depuis le LAN

- Vérifier que « LAN Access » est ON dans Settings > Server
- Vérifier que l'authentification PIN est configurée (obligatoire en publication LAN)
- Vérifier que le port est ouvert dans le pare-feu
- Vérifier que l'adresse IP du serveur est correcte

### Erreur de connexion MCP

- Vérifier que `YU_BASE_URL` est correct
- Vérifier que le serveur est démarré
- Vérifier que la clé API est valide
- Pour les accès LAN, vérifier que l'endpoint HTTP/SSE (`/mcp`) est utilisable

### Le scan est lent

- Désactiver `compute_hash` accélère le scan
- Pour les chemins distants, ajuster les paramètres de timeout Remote FS
- Avec un grand nombre de fichiers, le premier scan prend du temps

### La génération de miniatures est lente

- Pendant le scan, les E/S disque sont saturées, ralentissant la génération de miniatures. Le préchauffage démarre automatiquement à la fin du scan
- **pyvips (optionnel)** : pour beaucoup d'images JPEG grandes, l'accélération via shrink-on-load de libvips
  - Linux : `sudo apt install libvips-dev && uv pip install pyvips`
  - macOS : `brew install vips && uv pip install pyvips`
  - Windows : télécharger le DLL depuis la [page des releases libvips](https://github.com/libvips/libvips/releases), ajouter au PATH puis `uv pip install pyvips`
  - Détection automatique si installé. Fonctionne aussi sans, avec Pillow
- **Pillow-SIMD (optionnel)** : accélération 2-4x du redimensionnement via ARM NEON / x86 AVX2
  - `uv pip install pillow-simd` (drop-in replacement de Pillow)
  - Build optimisé ARM NEON : `CC="cc -mfpu=neon" uv pip install --force-reinstall pillow-simd`
  - Outils de build (gcc, etc.) nécessaires là où il n'y a pas de wheel

## Débogage

- Vérifier les logs serveur dans Settings > onglet Logs
- Mode debug MCP : outils supplémentaires disponibles avec `YU_DEBUG_MODE=1`
- Vérification d'intégrité DB : `python db_health.py`
