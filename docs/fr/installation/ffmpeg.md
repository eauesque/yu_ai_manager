# Guide d'Installation de ffmpeg

Tag Database utilise ffmpeg pour la génération de miniatures de fichiers vidéo (WebM, MP4, etc.).

## Windows

### Option 1 : Scoop (recommandé)
```powershell
# Installer Scoop (si non installé)
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
irm get.scoop.sh | iex

# Installer ffmpeg
scoop install ffmpeg
```

### Option 2 : Chocolatey
```powershell
# Installer Chocolatey (si non installé)
# Exécuter en administrateur
Set-ExecutionPolicy Bypass -Scope Process -Force
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

# Installer ffmpeg
choco install ffmpeg
```

### Option 3 : Téléchargement manuel
1. Télécharger depuis : https://www.gyan.dev/ffmpeg/builds/
2. Extraire dans `C:\ffmpeg`
3. Ajouter au PATH :
   - Ouvrir « Variables d'environnement »
   - Modifier « Path »
   - Ajouter `C:\ffmpeg\bin`
4. Redémarrer le terminal

---

## macOS

### Homebrew (recommandé)
```bash
# Installer Homebrew (si non installé)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Installer ffmpeg
brew install ffmpeg
```

---

## Linux

### Ubuntu/Debian
```bash
sudo apt update
sudo apt install ffmpeg
```

### Fedora
```bash
sudo dnf install ffmpeg
```

### Arch
```bash
sudo pacman -S ffmpeg
```

---

## Vérification de l'Installation

```bash
ffmpeg -version
```

L'affichage des informations de version indique le succès.

---

## Test des Miniatures Vidéo

```bash
# Lancer le WebUI
python web_ui.py --db tags.db

# Naviguer vers un fichier WebM
# Les miniatures sont générées automatiquement
```

---

## Dépannage

### Erreur « ffmpeg not installed »

**Symptôme** : un message d'erreur s'affiche sur les miniatures vidéo

**Solution** :
1. Vérifier que ffmpeg est installé : `ffmpeg -version`
2. Redémarrer le terminal / PowerShell
3. Redémarrer le WebUI
4. Vérifier la configuration du PATH

### Les miniatures ne sont pas générées

**Symptôme** : « Failed to extract video frame » s'affiche sur les miniatures

**Causes possibles** :
- Le fichier vidéo est corrompu
- Le codec vidéo n'est pas supporté
- Timeout ffmpeg (plus de 10 secondes)

**Débogage** :
```bash
# Test manuel
ffmpeg -i your_video.webm -ss 00:00:01 -vframes 1 test_thumb.jpg

# Vérifier les logs
# Rechercher le message "[ERROR] ffmpeg"
```

---

## Optionnel : Accélération GPU

Pour un traitement vidéo plus rapide (utilisateurs avancés) :

### Windows (NVIDIA)
```bash
# Télécharger le build NVIDIA :
# https://www.gyan.dev/ffmpeg/builds/
# Choisir « ffmpeg-release-full.7z »
```

### macOS (VideoToolbox)
```bash
# Inclus dans le build Homebrew
```

### Linux (VAAPI)
```bash
sudo apt install ffmpeg vainfo
```

---

## Remarques sur les Performances

- Première génération de miniature : environ 1-3 secondes
- Miniature en cache : moins de 100 ms
- Fichiers ZIP : traités après extraction dans un répertoire temporaire
- Timeout : 10 secondes par vidéo

---

## Sans ffmpeg

Si ffmpeg n'est pas disponible :
- Une erreur s'affiche sur les miniatures des fichiers vidéo
- La recherche vidéo par métadonnées reste possible
- Pour utiliser toutes les fonctionnalités, l'installation de ffmpeg est recommandée
