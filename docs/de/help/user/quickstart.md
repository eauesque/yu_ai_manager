# YU AI Manager in 5 Minuten starten

## Was ist YU AI Manager

YU AI Manager ist eine WebUI-Anwendung, mit der Sie die Metadaten von KI-generierten Bildern (Stable Diffusion / NovelAI / ComfyUI usw.) zentral verwalten können. Prompts und Modellinformationen, die in Bilder eingebettet sind, werden automatisch extrahiert, sodass Tag-Suche, Anzeige und Organisation effizient ablaufen.

---

## Betriebsumgebung

| Element | Anforderung |
|------|------|
| Python | 3.11 oder höher |
| Node.js | 18 oder höher (für Frontend-Build) |
| OS | Windows 10/11, macOS, Linux |
| Browser | Chrome / Firefox / Edge (aktuelle Version empfohlen) |

---

## Installationsanleitung

### 1. Repository klonen

```bash
git clone https://github.com/your-repo/yu_ai_manager.git
cd yu_ai_manager
```

### 2. Python Virtual Environment erstellen

**macOS / Linux:**

```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows (PowerShell):**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Windows (Git Bash):**

```bash
python -m venv venv
source venv/Scripts/activate
```

### 3. Python-Abhängigkeiten installieren

```bash
uv pip install -r requirements.txt
```

> Falls `uv` nicht installiert ist, installieren Sie es zuerst mit `pip install uv`.

### 4. Frontend bauen

```bash
pnpm install
pnpm run build
```

> Falls `pnpm` nicht installiert ist, installieren Sie es zuerst mit `npm install -g pnpm`.

Damit ist die Installation abgeschlossen.

---

## Erster Start

### 1. Server starten

```bash
# Falls venv nicht aktiviert ist, zuerst aktivieren
source venv/bin/activate        # macOS/Linux
# source venv/Scripts/activate  # Windows Git Bash

python web_ui.py
```

### 2. Im Browser öffnen

Öffnen Sie nach dem Start die folgende URL im Browser:

```
http://localhost:5000
```

*(Screenshot des Hauptbildschirms)*

---

## Die ersten Schritte

### Schritt 1: Bildordner scannen und registrieren

Registrieren Sie den Ordner, in dem sich Ihre KI-generierten Bilder befinden, und lassen Sie die Metadaten einlesen.

1. Öffnen Sie **Settings** über das Hamburger-Menü oben rechts
2. Wählen Sie den Tab **Scan**
3. Fügen Sie den Pfad des zu scannenden Ordners hinzu
4. Nach dem Hinzufügen des Ordners startet der Scan automatisch

*(Screenshot des Scan-Ordner-Registrierungsbildschirms)*

Während des Scans wird oben im Bildschirm eine Fortschrittsleiste angezeigt. Bei vielen Bildern kann dies einige Minuten dauern, jedoch können Sie auch während des Scans suchen und durchsuchen.

### Schritt 2: Bilder im Thumbnail-Raster anzeigen

Nach Abschluss des Scans wird auf der Hauptseite ein Thumbnail-Raster angezeigt.

*(Screenshot der Thumbnail-Raster-Anzeige)*

- **Scrollen**: Durch virtuelles Scrollen werden große Mengen an Bildern flüssig dargestellt
- **Sortieren**: Über das Sortiermenü oben nach Datum, Bewertung usw. sortieren
- **Rechtsklick**: Über das Kontextmenü können Favoriten oder Sammlungen hinzugefügt werden

### Schritt 3: Bilder per Tag-Suche filtern

Geben Sie Tags kommagetrennt in die Suchleiste ein, um nur die passenden Bilder anzuzeigen.

```
1girl, blue_eyes, school_uniform
```

*(Screenshot des Tag-Suchbildschirms)*

- **Autovervollständigung**: Vorschläge werden während der Eingabe angezeigt
- **Filter**: Filtern nach Datumsbereich, Dateiformat, Sternebewertung usw.
- **Prompt-Volltextsuche**: Der gesamte Prompt-Text kann ebenfalls durchsucht werden

### Schritt 4: Bildinformationen im Detail-Modal ansehen

Ein Klick auf ein Thumbnail öffnet das Detail-Modal.

*(Screenshot des Detail-Modals)*

- **Info-Tab**: Prompt, negativer Prompt, Modellname, Generierungsparameter usw. einsehen
- **AI-Analyse-Tab**: Zeigt die automatische Tag-Zuweisung durch WD-Tagger (sofern konfiguriert)
- **Sternebewertung**: Bilder können mit 1 bis 5 Sternen bewertet werden
- **Favorit**: Mit dem Herzsymbol als Favorit markieren
- **Tag-Bearbeitung**: Benutzertags können hinzugefügt oder entfernt werden
- **Tastaturbedienung**: Mit den Pfeiltasten links/rechts zum vorherigen/nächsten Bild wechseln

---

## Zusammenfassung häufiger Aktionen

| Was Sie möchten | Aktion |
|-------------|------|
| Bilder suchen | Tags in Suchleiste eingeben |
| Details zu einem Bild | Thumbnail anklicken |
| Zu Favoriten hinzufügen | Herzsymbol im Detail-Modal oder Kontextmenü |
| Sterne vergeben | Sternsymbol im Detail-Modal |
| Bilder zu Sammlung hinzufügen | Rechtsklick-Menü > Zur Sammlung hinzufügen |
| Mehrere Bilder auswählen | Strg+Klick (oder Umschalt+Klick für Bereichsauswahl) |
| Neuen Ordner scannen | Settings > Scan-Tab |

---

## Nächste Schritte

Wenn Sie mit den Grundfunktionen vertraut sind, probieren Sie auch folgende Funktionen aus.

### Settings (Einstellungen)

In der Settings-Seite können Sie Erscheinungsbild, Zeitzone, LAN-Freigabe usw. anpassen.
Details finden Sie im [Settings-Leitfaden](settings.md).

### Bridge (Anbindung an Bildgeneratoren)

Mit SD WebUI / ComfyUI / NovelAI API können Prompts gesendet und empfangen werden.
Details finden Sie im [Bridge-Leitfaden](bridges.md).

### Extensions (Erweiterungen)

Viele Erweiterungen stehen zur Verfügung, darunter WD-Tagger (automatisches Tagging), Prompt-Bibliothek, Chat-Log-Viewer usw. Die Verwaltung erfolgt unter Settings > Extensions.

### Semantische Suche

Wenn Sie ein CLIP-Modell konfigurieren, können Sie mit natürlicher Sprache wie „Mädchen, das am Meer den Sonnenuntergang betrachtet" suchen.
Details finden Sie im [Such-Leitfaden](search.md).

### MCP Server

Mit Claude Desktop und anderen KI-Agenten können Sie YU AI Manager bedienen. Verbindung erfolgt über stdio-Transport.

---

## Fehlerbehebung

Falls Probleme auftreten, konsultieren Sie den [Fehlerbehebungsleitfaden](troubleshooting.md).

Häufige Probleme:

- **`uv`-Befehl nicht gefunden**: Mit `pip install uv` installieren
- **`pnpm`-Befehl nicht gefunden**: Mit `npm install -g pnpm` installieren
- **Port 5000 wird verwendet**: Mit `python web_ui.py --port 5100` einen anderen Port angeben
- **Bilder werden nicht angezeigt**: Prüfen Sie, ob der Pfad des Scan-Ordners korrekt ist und ob die Bilddateien physisch vorhanden sind
