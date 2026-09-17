# Fehlerbehebung

## Häufige Probleme

### Server startet nicht

- Prüfen Sie, ob das Python Virtual Environment aktiviert ist: `source venv/bin/activate`
- Prüfen Sie, ob die Abhängigkeiten installiert sind: `uv pip install -r requirements.txt`
- Prüfen Sie, ob der Port belegt ist: `ss -tlnp | grep 5000`

### Bilder werden nicht angezeigt

- Die Thumbnail-API benötigt die tatsächlichen Bilddateien
- Prüfen Sie, ob der Pfad in der `files`-Tabelle mit dem tatsächlichen Dateipfad übereinstimmt
- Prüfen Sie, ob der Pfad des Scan-Roots korrekt ist

### Kein Zugriff aus dem LAN

- Prüfen Sie, ob unter Settings > Server „LAN Access" aktiviert ist
- Prüfen Sie, ob die PIN-Authentifizierung konfiguriert ist (bei LAN-Freigabe Pflicht)
- Prüfen Sie, ob der entsprechende Port in der Firewall freigegeben ist
- Prüfen Sie, ob die IP-Adresse des Servers korrekt ist

### MCP-Verbindungsfehler

- Prüfen Sie, ob `YU_BASE_URL` korrekt ist
- Prüfen Sie, ob der Server läuft
- Prüfen Sie, ob der API-Schlüssel gültig ist
- Bei Verbindung über LAN: Prüfen Sie, ob der HTTP/SSE-Endpunkt (`/mcp`) verfügbar ist

### Scan ist langsam

- Deaktivieren von `compute_hash` beschleunigt den Vorgang
- Bei Remote-Pfaden: Passen Sie das Timeout von Remote FS an
- Bei sehr vielen Dateien dauert der Erstscan einige Zeit

### Thumbnail-Generierung ist langsam

- Während des Scans ist die Disk-I/O stark ausgelastet, weshalb die Thumbnail-Erzeugung langsamer ist. Nach Scanabschluss wird automatisch ein Preview-Preheating ausgeführt
- **pyvips (optional)**: Bei vielen großen JPEG-Bildern beschleunigt libvips per Shrink-on-Load
  - Linux: `sudo apt install libvips-dev && uv pip install pyvips`
  - macOS: `brew install vips && uv pip install pyvips`
  - Windows: DLL von der [libvips-Release-Seite](https://github.com/libvips/libvips/releases) herunterladen, zu PATH hinzufügen, dann `uv pip install pyvips`
  - Wenn installiert, wird es automatisch erkannt. Andernfalls läuft alles mit Pillow weiter
- **Pillow-SIMD (optional)**: Beschleunigt Bildgrößenänderung um Faktor 2-4 mit ARM NEON / x86 AVX2
  - `uv pip install pillow-simd` (Drop-in-Ersatz für Pillow)
  - ARM-NEON-optimierter Build: `CC="cc -mfpu=neon" uv pip install --force-reinstall pillow-simd`
  - Ohne Wheel werden Build-Tools (gcc usw.) benötigt

## Debugging

- Serverlogs unter Settings > Logs-Tab einsehen
- MCP-Debug-Modus: `YU_DEBUG_MODE=1` aktiviert zusätzliche Tools
- DB-Integritätsprüfung: `python db_health.py`
