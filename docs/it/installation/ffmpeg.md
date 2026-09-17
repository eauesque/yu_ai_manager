# Guida all'Installazione di FFmpeg

Tag Database usa FFmpeg per generare thumbnail dei file video (WebM, MP4 ecc.).

## Windows

### Opzione 1: Scoop (consigliato)
```powershell
# Installa Scoop (se non installato)
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
irm get.scoop.sh | iex

# Installa ffmpeg
scoop install ffmpeg
```

### Opzione 2: Chocolatey
```powershell
# Installa Chocolatey (se non installato)
# Eseguire come amministratore
Set-ExecutionPolicy Bypass -Scope Process -Force
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

# Installa ffmpeg
choco install ffmpeg
```

### Opzione 3: Download Manuale
1. Scarica da: https://www.gyan.dev/ffmpeg/builds/
2. Estrai in `C:\ffmpeg`
3. Aggiungi al PATH:
   - Apri "Variabili d'ambiente"
   - Modifica "Path"
   - Aggiungi `C:\ffmpeg\bin`
4. Riavvia il terminale

---

## macOS

### Homebrew (consigliato)
```bash
# Installa Homebrew (se non installato)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Installa ffmpeg
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

## Verifica Installazione

```bash
ffmpeg -version
```

Se vengono mostrate le informazioni sulla versione l'installazione è riuscita.

---

## Risoluzione dei Problemi

### Errore "ffmpeg not installed"

**Sintomo**: Messaggio di errore nei thumbnail video

**Soluzione**:
1. Verificare che ffmpeg sia installato: `ffmpeg -version`
2. Riavviare il terminale / PowerShell
3. Riavviare il WebUI
4. Verificare le impostazioni PATH

### Thumbnail non Generati

**Sintomo**: "Failed to extract video frame" nel thumbnail

**Possibili cause**:
- File video corrotto
- Codec video non supportato
- Timeout ffmpeg (superiore a 10 secondi)

**Debug**:
```bash
# Test manuale
ffmpeg -i your_video.webm -ss 00:00:01 -vframes 1 test_thumb.jpg

# Controllare i log
# Cercare i messaggi "[ERROR] ffmpeg"
```

---

## Note sulle Prestazioni

- Prima generazione thumbnail: circa 1-3 secondi
- Thumbnail in cache: sotto i 100ms
- File ZIP: elaborati dopo estrazione in directory temporanea
- Timeout: 10 secondi per video

---

## Senza ffmpeg

Se ffmpeg non è disponibile:
- Nei thumbnail dei file video viene mostrato un errore
- La ricerca video per metadati rimane comunque possibile
- Per la piena funzionalità si raccomanda l'installazione di ffmpeg

## Linux

```bash
# Ubuntu / Debian
sudo apt-get install ffmpeg

# Fedora
sudo dnf install ffmpeg
```

## macOS

```bash
# Con Homebrew
brew install ffmpeg
```

## Windows

1. Scarica da https://ffmpeg.org/download.html
2. Estrai directory
3. Aggiungi a PATH

Verifica:
```bash
ffmpeg -version
```
