# ffmpeg Installation Guide

Tag Database uses ffmpeg to generate thumbnails for video files (WebM, MP4, etc.).

## Windows

### Option 1: Scoop (Recommended)
```powershell
# Install Scoop (if not installed)
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
irm get.scoop.sh | iex

# Install ffmpeg
scoop install ffmpeg
```

### Option 2: Chocolatey
```powershell
# Install Chocolatey (if not installed)
# Run as Administrator
Set-ExecutionPolicy Bypass -Scope Process -Force
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

# Install ffmpeg
choco install ffmpeg
```

### Option 3: Manual Download
1. Download from: https://www.gyan.dev/ffmpeg/builds/
2. Extract to `C:\ffmpeg`
3. Add to PATH:
   - Open "Environment Variables"
   - Edit "Path"
   - Add `C:\ffmpeg\bin`
4. Restart terminal

---

## macOS

### Homebrew (Recommended)
```bash
# Install Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install ffmpeg
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

## Verify Installation

```bash
ffmpeg -version
```

Should output version information.

---

## Testing Video Thumbnails

```bash
# Start WebUI
python web_ui.py --db tags.db

# Navigate to a WebM file
# Thumbnail should generate automatically
```

---

## Troubleshooting

### "ffmpeg not installed" error

**Symptom**: Video thumbnails show error message

**Solution**:
1. Verify ffmpeg is installed: `ffmpeg -version`
2. Restart terminal/PowerShell
3. Restart WebUI
4. Check PATH settings

### Thumbnails not generating

**Symptom**: Thumbnails show "Failed to extract video frame"

**Possible causes**:
- Video file is corrupted
- Video codec not supported
- ffmpeg timeout (>10 seconds)

**Debug**:
```bash
# Test manually
ffmpeg -i your_video.webm -ss 00:00:01 -vframes 1 test_thumb.jpg

# Check logs
# Look for "[ERROR] ffmpeg" messages
```

---

## Optional: GPU Acceleration

For faster video processing (advanced):

### Windows (NVIDIA)
```bash
# Download NVIDIA build from:
# https://www.gyan.dev/ffmpeg/builds/
# Choose "ffmpeg-release-full.7z"
```

### macOS (VideoToolbox)
```bash
# Already included in Homebrew build
```

### Linux (VAAPI)
```bash
sudo apt install ffmpeg vainfo
```

---

## Performance Notes

- First thumbnail generation: ~1-3 seconds
- Cached thumbnails: <100ms
- ZIP files: Extracted to temp, then processed
- Timeout: 10 seconds per video

---

## Without ffmpeg

If ffmpeg is not available:
- Video files will show error in thumbnails
- Videos can still be searched by metadata
- Consider installing ffmpeg for full functionality
