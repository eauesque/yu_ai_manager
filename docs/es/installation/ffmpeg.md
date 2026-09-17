# Guía de instalación de ffmpeg

Tag Database utiliza ffmpeg para generar miniaturas de archivos de video (WebM, MP4, etc.).

## Windows

### Opción 1: Scoop (recomendado)
```powershell
# Instalar Scoop (si no está instalado)
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
irm get.scoop.sh | iex

# Instalar ffmpeg
scoop install ffmpeg
```

### Opción 2: Chocolatey
```powershell
# Instalar Chocolatey (si no está instalado)
# Ejecutar con permisos de administrador
Set-ExecutionPolicy Bypass -Scope Process -Force
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

# Instalar ffmpeg
choco install ffmpeg
```

### Opción 3: Descarga manual
1. Descargar desde: https://www.gyan.dev/ffmpeg/builds/
2. Extraer a `C:\ffmpeg`
3. Agregar a PATH:
   - Abrir "Variables de entorno"
   - Editar "Path"
   - Agregar `C:\ffmpeg\bin`
4. Reiniciar terminal

---

## macOS

### Homebrew (recomendado)
```bash
# Instalar Homebrew (si no está instalado)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Instalar ffmpeg
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

## Verificar instalación

```bash
ffmpeg -version
```

Si muestra información de versión, instalación fue exitosa.

---

## Probar miniatura de video

```bash
# Iniciar WebUI
python web_ui.py --db tags.db

# Mover archivo WebM
# Las miniaturas se generarán automáticamente
```

---

## Solución de problemas

### Error "ffmpeg not installed"

**Síntoma**: Mensaje de error mostrado en miniatura de video

**Solución**:
1. Verificar ffmpeg instalado: `ffmpeg -version`
2. Reiniciar terminal / PowerShell
3. Reiniciar WebUI
4. Verificar configuración de PATH

### Miniatura no se genera

**Síntoma**: "Failed to extract video frame" mostrado en miniatura

**Posibles causas**:
- Archivo video corrupto
- Códec de video no soportado
- Timeout ffmpeg (más de 10 segundos)

**Depuración**:
```bash
# Probar manualmente
ffmpeg -i your_video.webm -ss 00:00:01 -vframes 1 test_thumb.jpg

# Verificar registro
# Buscar mensaje "[ERROR] ffmpeg"
```

---

## Opcional: Aceleración GPU

Para procesamiento de video más rápido (usuarios avanzados):

### Windows (NVIDIA)
```bash
# Descargar compilación NVIDIA:
# https://www.gyan.dev/ffmpeg/builds/
# Seleccionar "ffmpeg-release-full.7z"
```

### macOS (VideoToolbox)
```bash
# Incluido en compilación Homebrew
```

### Linux (VAAPI)
```bash
sudo apt install ffmpeg vainfo
```

---

## Notas de rendimiento

- Primera generación miniatura: aprox. 1-3 segundos
- Miniatura en caché: menos de 100ms
- Archivo ZIP: procesar después extraer directorio temporal
- Timeout: 10 segundos por video

---

## Sin ffmpeg

Si ffmpeg no disponible:
- Miniatura de archivo video mostrará error
- Búsqueda de video por metadatos sigue siendo posible
- Se recomienda instalar ffmpeg para funcionalidad completa
