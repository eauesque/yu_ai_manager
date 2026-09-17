# Enregistrement de fichiers par glisser-déposer

Glissez et déposez des fichiers image/vidéo sur la page de la bibliothèque principale (`/`) pour les enregistrer
dans un répertoire **Drop Inbox** configuré et les enregistrer automatiquement dans
la bibliothèque. Le chemin d'analyse normal (`scan_one`) est utilisé, donc l'extraction de métadonnées, la génération de miniatures et le marquage s'exécutent comme ils le feraient pour une analyse normale.

## Comportement

1. Avec la page principale ouverte, glissez des fichiers à partir de l'explorateur de fichiers ou d'une autre fenêtre de navigateur
2. Une superposition s'affiche sur la fenêtre montrant le chemin cible (Drop Inbox)
3. Au dépôt, chaque fichier est copié dans la Drop Inbox et enregistré
4. Un toast affiche le nombre de succès et d'échecs

## Résolution de la Drop Inbox

La Drop Inbox est résolue dans cet ordre de priorité :

1. `drop_inbox_dir` du `config.json` (paramètre explicite)
2. Si non défini : la première racine d'analyse activée est utilisée telle quelle

**Contrainte** : `drop_inbox_dir` **doit** se trouver à l'intérieur de l'une des entrées `scan_roots`.
Tout chemin en dehors des racines d'analyse est rejeté avec HTTP 400. Ceci préserve
l'invariant que les racines d'analyse sont la source unique de vérité pour les fichiers de la bibliothèque.

## Exemple de configuration

```json
{
  "scan_roots": [
    { "path": "D:/Pictures/AI", "enabled": true, "recursive": true }
  ],
  "drop_inbox_dir": "D:/Pictures/AI/inbox"
}
```

La `drop_inbox_dir` est créée si elle n'existe pas (son parent doit toujours être
à l'intérieur de `scan_roots`).

## Gestion des collisions de noms

Si un fichier portant le même nom existe déjà dans la boîte de réception, des suffixes `_1`, `_2`,
... sont automatiquement ajoutés. Les fichiers existants ne sont jamais remplacés.

## Extensions autorisées

| Catégorie | Extensions |
|---|---|
| Images | `.png` `.jpg` `.jpeg` `.webp` `.gif` `.bmp` `.tiff` `.tif` `.svg` |
| Vidéos | `.mp4` `.webm` `.mov` `.avi` `.mkv` `.m4v` |

Les archives (`.zip` / `.7z` / `.rar`) ne sont **pas prises en charge** via glisser-déposer. Placez
les fichiers d'archive directement dans une racine d'analyse et exécutez une analyse ordinaire à la place.

## Limitations

- La taille totale de la requête est limitée à `MAX_CONTENT_LENGTH` (par défaut **100 MB**)
- Les noms de fichiers contenant une traversée de répertoires (`..`) sont rejetés
- Le dépôt d'un répertoire entier n'est actuellement pas pris en charge (fichiers individuels uniquement)

## API HTTP

### `POST /api/dnd-upload`

Accepte les téléchargements de fichiers multipart, les enregistre dans la Drop Inbox et les enregistre
dans la bibliothèque.

Réponse :

```json
{
  "ok": true,
  "total": 3,
  "success": 2,
  "results": [
    { "ok": true, "status": "added", "file_id": 12345, "path": "...", "filename": "a.png" },
    { "ok": true, "status": "skipped", "path": "...", "filename": "b.png" },
    { "ok": false, "code": "unsupported_type", "error": "...", "filename": "c.xyz" }
  ]
}
```

### `GET /api/dnd-inbox`

Retourne la Drop Inbox résolue actuellement pour l'affichage de la superposition de l'interface.

```json
{ "ok": true, "inbox": "D:/Pictures/AI/inbox", "explicit": true }
```

### `POST /api/files/register-path`

Enregistre un fichier déjà sur le disque par chemin (sans téléchargement). Le chemin doit être à l'intérieur
de `scan_roots`. Utilisé par l'outil MCP `register_file`.

```json
{ "path": "D:/Pictures/AI/inbox/a.png" }
```

## Outils MCP

| Outil | Description |
|---|---|
| `register_file(path)` | Enregistrer un fichier dans la bibliothèque à un chemin absolu |
| `drop_inbox_info()` | Retourner le répertoire Drop Inbox actuellement résolu |
