# Manuel de Débogage YU AI Manager

## Démarrage Rapide

```bash
# Lancer tous les diagnostics
python debug_check.py

# Spécifier la DB
python debug_check.py --db /path/to/tags.db

# Vérification simplifiée (sans syntaxe/Extensions)
python debug_check.py --quick
```

---

## Problèmes Courants et Solutions

### 1. config.json corrompu (problème de backslashes)

**Symptôme :** JSONDecodeError au démarrage serveur
**Cause :** saisie manuelle de chemins Windows, `\U`, `\w`, etc. deviennent des échappements invalides
**Solution :** réparation automatique au démarrage serveur. Pour une réparation manuelle :
```bash
python -c "
from core.config import safe_load_json
data = safe_load_json('config.json')
print('OK' if data else 'FAILED')
"
```

### 2. Certains dossiers sont ignorés par scan-all

**Symptôme :** certains dossiers non traités par « Scanner tous les dossiers »
**Procédure de vérification :**
```bash
# Vérifier le contenu de scan_roots
python -c "
import json
c = json.load(open('config.json'))
for i, r in enumerate(c.get('scan_roots', [])):
    print(f'  [{i}] repr={repr(r)} len={len(r)}')
"
```
**Points à vérifier :**
- Le chemin n'est-il pas trop court (juste `\\wsl.localhost\`) ?
- Pas de `\` en fin ?
- `os.path.exists(path)` retourne True ?

### 3. Le partage QR indique « aucun contenu »

**Symptôme :** bouton partage QR → Positive/Negative sont vides
**Causes possibles :**
1. Pas d'enregistrement dans la table `templates` (meta_source=unknown)
2. Mismatch de clés dans la réponse API (corrigé en v2.7.0)

**Vérification :**
```bash
# Vérifier l'existence du template pour l'ID fichier
python -c "
import sqlite3
con = sqlite3.connect('tags.db')
file_id = 276323  # ID du problème
row = con.execute('SELECT * FROM templates WHERE file_id=?', (file_id,)).fetchone()
print('templates:', 'EXISTS' if row else 'MISSING')
meta = con.execute('SELECT meta_source FROM files WHERE id=?', (file_id,)).fetchone()
print('meta_source:', meta[0] if meta else 'NOT FOUND')
"
```

### 4. Scan échoue sur chemin WSL/UNC

**Symptôme :** échec de probe sur `\\wsl.localhost\...`
**Vérification :**
```bash
python -c "
import os
path = r'\\\\wsl.localhost\\Ubuntu\\home\\user\\...'
print(f'exists: {os.path.exists(path)}')
print(f'isdir: {os.path.isdir(path)}')
print(f'repr: {repr(path)}')
print(f'len: {len(path)}')
"
```
**Attention :** `pathlib.Path.exists()` a un bug sur les chemins UNC WSL. Utiliser `os.path.exists()`.

### 5. Une Extension ne se charge pas

**Symptôme :** n'apparaît pas dans la liste des Extensions
**Vérification :**
```bash
python debug_check.py  # Voir la section vérification Extension
```
**Points à vérifier :**
- `extension.json` ou `extension.yml` existe-t-il ?
- JSON/YAML valide ? (vérifier avec `safe_load_config`)
- Le champ `name` existe-t-il ?

### 6. Lockout par authentification PIN

**Symptôme :** 5 échecs → lockout 60 secondes
**Solution :** attendre 60 secondes. Ou redémarrer le serveur pour réinitialiser.
**Vérification :** outils développeur navigateur → Network → vérifier le message d'erreur dans la réponse `/_pin_check`

### 7. Vérifier le rapport de bug QR / Bundle de la page erreur 500

**Symptôme :** la page entière passe en 500 et affiche une page d'erreur dédiée
**Cible :** exceptions non gérées côté serveur, échec global de page HTML

**Points minimaux à vérifier :**
- Un code QR s'affiche à l'écran
- Le bouton `Copier le JSON Bundle` s'affiche
- Le bouton `Télécharger le Bundle (.json.gz)` s'affiche
- Le `AI Error Bundle` apparaît dans `docs/bugreport.html` après lecture du QR

**Procédure de vérification :**
```bash
# Lancer d'abord le serveur normalement
venv\Scripts\python.exe web_ui.py
```

1. Dans le navigateur, faire des opérations déclenchant intentionnellement une 500
2. Vérifier que le QR et les boutons Bundle apparaissent sur la page d'erreur 500
3. Cliquer sur `Copier le JSON Bundle` et vérifier que le JSON contient `schema`, `error_id`, `request`, `error`, `state`
4. Cliquer sur `Télécharger le Bundle (.json.gz)` et vérifier que `err_*.json.gz` peut être sauvegardé
5. Lire le QR avec un smartphone, ou ouvrir l'URL de la chaîne QR pour accéder à `bugreport.html`
6. Vérifier sur la relay page que le `AI Error Bundle` complet est visible, et que ce JSON entre dans le corps lors de la génération d'Issue GitHub

**Points à regarder :**
- `bundle.error.class` et `bundle.error.message` ne sont pas vides
- `bundle.request.path` correspond à l'URL réelle de l'échec
- `bundle.error.frames` contient file/line/function du point de défaillance
- `bundle.state.server_info` et `bundle.state.extensions` ne manquent pas
- Même avec un QR trop long, la relay page peut décoder

**Isolement :**
- QR apparaît mais relay page échoue au décodage
  Vérifier pack/shrink de `core/web/error_bundle.py` et le décodage gzip de `docs/bugreport.html`
- Les boutons Copy/Download n'apparaissent pas
  Vérifier dans `core/web/error_handlers.py` que `bundle_json` / `bundle_download_b64` sont passés au template
- Seul le téléchargement est cassé
  Vérifier le décodage base64 et la génération de Blob `application/gzip` dans `ui/default/templates/error.html`

**Fichiers associés :**
- `core/web/error_bundle.py`
- `core/web/error_handlers.py`
- `ui/default/templates/error.html`
- `docs/bugreport.html`
- `docs/ja/features/qr-protocol-v1.md`

### 8. Vérifier le client error reporter pour un échec partiel de page

**Symptôme :** la page entière s'ouvre, mais les cartes/sections/chargements API échouent
**Cible :** 4xx/5xx de `fetch`, network error, `window.error`, `unhandledrejection`, tools page loader failure

**Points minimaux à vérifier :**
- Le launcher error reporter apparaît en bas à droite
- La modale peut s'ouvrir depuis le launcher
- `Copy JSON` / `Download .json.gz` / `GitHub Issue` sont utilisables dans la modale
- Le bundle contient `X-Request-Id` et `ui_events`

**Procédure de vérification :**
1. Ouvrir une page qui utilise `apiFetch`
2. Effectuer une opération appelant une API retournant intentionnellement 500, ou une API inexistante
3. Vérifier que le launcher en bas à droite apparaît
4. Ouvrir la modale et vérifier le bundle JSON
5. Vérifier que `request.status`, `request.url`, `request.request_id`, `repro.ui_events` sont inclus
6. Cliquer sur `Download .json.gz` et vérifier que le bundle compressé peut être sauvegardé

**Vérification dans les outils développeur :**
- Dans l'onglet Network, le response header de l'API échouée contient-il `X-Request-Id` ?
- Si une exception non gérée apparaît dans Console, le bundle côté launcher contient-il le même contenu d'erreur ?
- `/api/error-report/enrich` retourne-t-il 200, et le bundle enrichi contient-il `state.server_info` ou `artifacts.recent_logs` ?

**Exemples de reproduction simple :**
- Lever intentionnellement une exception dans le loader de la tools page
- Appeler temporairement un endpoint inexistant comme `apiFetch('/api/not-found-for-debug')`
- Côté serveur, remplacer temporairement la route cible par `api_error(...)` ou lancement d'exception

**Isolement :**
- Le launcher n'apparaît pas malgré l'échec
  Vérifier `src/ts/main/api-utils.ts` ou `src/ts/shared/error-reporter.ts`. Probablement pas passé par le `apiFetch` commun
- Pas de `request_id` dans le bundle
  Vérifier dans `core/web/request_hooks.py` que `X-Request-Id` est ajouté à toutes les réponses
- Informations serveur vides même après enrich
  Vérifier `/api/error-report/enrich` de `routes/server_info.py` et `enrich_error_bundle()` de `core/web/error_bundle.py`
- Certains échecs de tools page non capturés
  Vérifier l'appel à `captureThrownError(...)` dans `src/ts/tools-page/index.ts`

**Fichiers associés :**
- `src/ts/shared/error-reporter.ts`
- `src/ts/main/api-utils.ts`
- `src/ts/tools-page/index.ts`
- `src/ts/nav/index.ts`
- `core/web/request_hooks.py`
- `routes/server_info.py`
- `core/web/error_bundle.py`

---

## Lecture des Logs de Debug

### Sortie Console du Serveur

```
[WARN] config.json had invalid escapes -- auto-repaired and saved
  → La réparation automatique des backslashes de config.json a été exécutée

[DEBUG] scan/start: raw=..., sanitized=...
  → Chemin au démarrage du scan (valeur brute → après sanitisation)

[DEBUG] scan-all root 0: repr=..., len=...
  → Détails de chaque chemin racine lors du scan-all

[Scan] Auto-registered scan root: /path/to/dir
  → Enregistrement automatique à la réussite du scan

[DEBUG share] file_id=123, file_row=yes, tmpl=no
  → API de partage QR : le fichier existe mais pas de template

[ERROR] file.json: JSON parse failed: ...
  → Erreur de parse dans safe_load_json (l'app ne crashe pas)
```

---

## Structure des Fichiers et Cibles de Debug

```
web_ui.py          ← Point d'entrée (démarrage serveur)
core/
  config.py        ← Gestion de configuration, safe_load_*
  server.py        ← Authentification PIN, QuickLock
  scanner.py       ← Moteur de scan
  extensions.py    ← Chargement d'Extensions
  db.py            ← Gestion de connexion DB
  schema.py        ← Définition des tables
routes/
  scan.py          ← API scan
  search.py        ← API recherche
  share.py         ← API partage QR
  tools.py         ← API tools + Inspect API
  debug.py         ← API debug
  pages.py         ← Routing de pages
  server_info.py   ← server-info / API enrich error-report
core/web/
  error_handlers.py ← Page erreur 500 + génération rapport bug QR
  error_bundle.py   ← Génération / réduction / enrich d'error bundle
  request_hooks.py  ← Ajout de X-Request-Id
ui/default/templates/
  error.html       ← UI Copy / Download de la page erreur 500
static/js/
  main.js          ← UI principale (recherche, modale, QR, clavier)
  scan-banner.js   ← Progression scan + scroll-top (toutes pages)
src/ts/shared/
  error-reporter.ts ← Client-side error reporter pour échecs partiels
```
