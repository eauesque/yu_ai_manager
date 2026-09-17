# ffmpeg Installations-Anleitung

Tag Database nutzt ffmpeg zur Thumbnail-Erstellung von Videodateien (WebM, MP4 etc.).

## Windows

### Option 1: Scoop (empfohlen)
```powershell
# Scoop installieren (falls nicht vorhanden)
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
irm get.scoop.sh | iex

# ffmpeg installieren
scoop install ffmpeg
```

### Option 2: Chocolatey
```powershell
# Chocolatey installieren (falls nicht vorhanden)
# Mit Administratorrechten ausführen
Set-ExecutionPolicy Bypass -Scope Process -Force
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

# ffmpeg installieren
choco install ffmpeg
```

### Option 3: Manueller Download
1. Von hier herunterladen: https://www.gyan.dev/ffmpeg/builds/
2. Nach `C:\ffmpeg` entpacken
3. PATH hinzufügen:
   - "Umgebungsvariablen" öffnen
   - "Path" bearbeiten
   - `C:\ffmpeg\bin` hinzufügen
4. Terminal neu starten

---

## macOS

### Homebrew (empfohlen)
```bash
# Homebrew installieren (falls nicht vorhanden)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# ffmpeg installieren
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

## Installations-Bestätigung

```bash
ffmpeg -version
```

Versionsinformationen anzeigen bedeutet Erfolg.

---

## Video-Thumbnail-Test

```bash
# WebUI starten
python web_ui.py --db tags.db

# WebM-Datei verschieben
# Thumbnail wird automatisch generiert
```

---

## Fehlerbehebung

### Fehler: „ffmpeg not installed"

**Symptom**: Video-Thumbnail zeigt Fehlermeldung

**Lösungen**:
1. Überprüfen Sie, ob ffmpeg installiert ist: `ffmpeg -version`
2. Terminal / PowerShell neu starten
3. WebUI neu starten
4. PATH-Einstellung überprüfen

### Thumbnail wird nicht generiert

**Symptom**: Thumbnail zeigt „Failed to extract video frame"

**Mögliche Ursachen**:
- Videodatei ist beschädigt
- Video-Codec wird nicht unterstützt
- ffmpeg Timeout (über 10 Sekunden)

**Debug**:
```bash
# Manueller Test
ffmpeg -i your_video.webm -ss 00:00:01 -vframes 1 test_thumb.jpg

# Logs überprüfen
# "[ERROR] ffmpeg" Nachricht suchen
```

---

## Optional: GPU-Beschleunigung

Für schnellere Videoverarbeitung (fortgeschrittene Nutzer):

### Windows (NVIDIA)
```bash
# NVIDIA Build herunterladen:
# https://www.gyan.dev/ffmpeg/builds/
# "ffmpeg-release-full.7z" wählen
```

### macOS (VideoToolbox)
```bash
# In Homebrew Build enthalten
```

### Linux (VAAPI)
```bash
sudo apt install ffmpeg vainfo
```

---

## Performance-Hinweise

- Erste Thumbnail-Generierung: ca. 1-3 Sekunden
- Gecachte Thumbnails: unter 100ms
- ZIP-Dateien: Werden temporal entpackt
- Timeout: 10 Sekunden pro Video

---

## Ohne ffmpeg

Wenn ffmpeg nicht verfügbar ist:
- Video-Thumbnails zeigen Fehler
- Video-Metadaten-Suche funktioniert weiterhin
- Für volle Funktionalität wird ffmpeg-Installation empfohlen

