# Erste Schritte

YU AI Manager ist eine WebUI-Anwendung zur Verwaltung von Metadaten KI-generierter Bilder.

## Installation

### Systemvoraussetzungen

- Python 3.11 oder höher
- Node.js 18 oder höher (für Frontend-Build)

### Einrichtungsschritte

```bash
# Repository klonen
git clone https://github.com/your-repo/yu_ai_manager.git
cd yu_ai_manager

# uv installieren (nur beim ersten Mal)
pip install uv

# Python-Virtualumgebung erstellen und Abhängigkeiten installieren
python3 -m venv venv
source venv/bin/activate  # Windows Git Bash: source venv/Scripts/activate
uv pip install -r requirements.txt

# Frontend bauen
pnpm install
pnpm run build

# Optional: Semantische Suche beschleunigen (für große Bibliotheken)
uv pip install faiss-cpu
```

## Starten

```bash
source venv/bin/activate  # Windows Git Bash: source venv/Scripts/activate
python web_ui.py --db ./tags.db --port 5000
```

Browser auf `http://localhost:5000` öffnen.

## Erstkonfiguration

1. **Scan-Ordner registrieren**: Unter Settings > Scan-Tab den Ordner mit KI-Bildern hinzufügen
2. **Scan ausführen**: Nach Ordnerhinzufügung startet der Scan automatisch
3. **Bilder durchsuchen**: Auf der Hauptseite können Bilder gesucht und angesehen werden

## LAN-Veröffentlichung

Für Zugriff von anderen Geräten:

1. Unter Settings > **Server**-Tab "LAN Access" auf ON setzen
2. PIN-Authentifizierung konfigurieren (bei LAN-Veröffentlichung Pflicht)  
   PIN-Code-Feld im **Settings > Server-Tab** mit Ziffern (4–8-stellig) ausfüllen
3. Server neu starten

Von anderen LAN-Geräten über `http://<Server-IP>:5000` zugreifen.
