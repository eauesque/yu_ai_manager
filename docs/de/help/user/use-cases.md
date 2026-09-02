# Anwendungsfälle

Die typischen Einsatzszenarien von YU AI Manager sind im Format „So nutzen Sie es in dieser Situation" zusammengefasst.

---

## 1. Große Mengen an KI-Bildern organisieren

Wenn sich tausende mit NovelAI oder Stable Diffusion generierte Bilder im Ordner angesammelt haben und das Durchsehen schwierig wird.

### Vorgehen

1. Im Tab **Settings > Scan** den Scan-Ordner registrieren (mehrere möglich)
2. Nach Hinzufügen des Ordners startet der Scan automatisch. Auch ZIP/7z-Inhalte können gescannt werden
3. Nach Scan-Abschluss auf der Hauptseite mit Tag-Suche (z. B. `1girl, blue_eyes`) oder Sortierung filtern
4. Gefallene Bilder auswählen und per Rechtsklick > **Zur Sammlung hinzufügen** gruppieren
5. Aus der Sammlungs-Sidebar jederzeit pro Gruppe durchsuchen

### Tipps

- Suche und Anzeige funktionieren auch während des Scans (Read-only-DB-Verbindung, kein Konflikt)
- Mit aktivierter Auto Scan Watcher Extension werden neu hinzugefügte Dateien automatisch erkannt
- Selbst bei 1 Million Einträgen wird per Keyset Pagination schnell geblättert

---

## 2. Bilder mit bestimmten Prompts finden

„Wie war noch mal der Prompt für diese Komposition?" -- wenn Sie sich nicht erinnern können.

### Vorgehen

1. Das Suchziel der Suchleiste auf **in_prompt** umschalten
2. Ein erinnertes Keyword eingeben (z. B. `cherry blossom`)
3. Reguläre Ausdrücke ermöglichen flexibleres Filtern (z. B. `masterpiece.*cherry`)

### Tipps

- Bei aktivierter FTS (Volltextsuche) funktioniert die Suche auch bei vielen Prompts schnell
- Die Kombination mit Datumsbereich- und Dateiformatfilter ist wirkungsvoll
- Mit der Sortierung `random` können vergessene Bilder wiederentdeckt werden

---

## 3. Bilder mit ähnlicher Komposition finden

„Es müsste noch weitere Bilder mit ähnlicher Atmosphäre geben" -- wenn Sie danach suchen möchten.

### Vorgehen A: pHash-Ähnlichkeitssuche (Komposition, Farbstimmung)

1. Detail-Modal des Bildes öffnen
2. Auf **Ähnliche Bilder suchen** klicken
3. Bilder mit ähnlicher Komposition werden per pHash (Perceptual Hash) in der Seitenleiste gelistet

### Vorgehen B: CLIP-Semantiksuche (Bedeutung, Konzept)

1. Rechts neben der Suchleiste auf **Semantiksuche** klicken
2. Beschreibung in natürlicher Sprache eingeben (z. B. „Mädchen am Meer stehend", „Sonnenuntergangsstadt")
3. CLIP versteht die Bedeutung und zeigt nach Ähnlichkeit sortiert

### Tipps

- Die Semantiksuche benötigt ein vorkonfiguriertes CLIP-Modell (ONNX oder Hailo-10H)
- Bei großen Bibliotheken (100.000+ Einträge) verbessert `faiss-cpu` die Suchgeschwindigkeit dramatisch
- pHash eignet sich für Kompositionsübereinstimmung, CLIP für semantische Ähnlichkeit. Beide auszuprobieren, erweitert die Ergebnisse

---

## 4. Favoritenbilder verwalten

Um aus einer Masse von Bildern nur die Meisterwerke schnell wieder anschauen zu können.

### Vorgehen

1. Mit dem **Herz-Button** auf der Bildkarte oder im Detail-Modal als Favorit markieren
2. **Sternebewertung** (1-5) im Detail-Modal setzen, um Qualität zu bewerten
3. In **Annotationen** freien Text hinterlassen (z. B. „Retake-Kandidat", „Bereits auf SNS gepostet")
4. Mit Suchfiltern wie „Nur Favoriten" oder „4+ Sterne" filtern

### Tipps

- Mit Bewertungssortierung (`rating_desc`) lassen sich hoch bewertete Bilder gebündelt anzeigen
- Favoriten- und Bewertungsaktionen sind auch über das Kontextmenü (Rechtsklick) möglich

---

## 5. Prompts an andere Tools senden

Um Prompts aus früher erstellten Bildern in anderen Tools für Regenerierung oder Variationen wiederzuverwenden.

### Vorgehen

1. Detail-Modal des Bildes öffnen und Prompt-Infos prüfen
2. Auf **An SD WebUI senden** / **An ComfyUI senden** / **An NAI senden** klicken
3. Die Bridge-Seite öffnet sich mit automatisch eingefügtem Prompt
4. Prompt bei Bedarf bearbeiten und im Generierungstool ausführen

### Tipps

- Zwischen SD und NAI werden Gewichtungssyntaxen `()` und `{}` automatisch konvertiert
- Mit dem **QP**-Button in der Bridge-Toolbar werden Qualitätspresets per Klick eingefügt
- Auch von Prompt Converter oder Prompt Simulator kann an jede Bridge gesendet werden

---

## 6. Bilder in ZIP/7z-Archiven durchsuchen

Wenn heruntergeladene Bildsets als ZIP vorliegen und Sie den Inhalt ohne Entpacken prüfen möchten.

### Vorgehen

1. Unter Settings > Scan den Ordner mit ZIP/7z-Dateien registrieren
2. In den Scan-Optionen **ZIP/7z-Inhalt scannen** aktivieren
3. Nach Scan-Abschluss können Archivinhalte auf der Hauptseite wie normale Bilder durchsucht und angezeigt werden
4. Im Detail-Modal werden Archivname und Pfad im Archiv angezeigt

### Tipps

- Videos im Archiv werden in einem Temp-Cache (LRU 2 GB) expandiert, sodass wiederholtes Abspielen flüssig ist
- Verschachtelte ZIPs (ZIP-in-ZIP) werden unterstützt
- Mit der Batch-Download-Funktion können Archivbilder in ein neues ZIP gebündelt werden

---

## 7. Bilder mit Team oder Familie teilen

Wenn Sie Bilder von anderen Geräten (Smartphone, Tablet usw.) im selben WLAN anzeigen lassen möchten.

### Vorgehen

1. Im Tab **Settings > Server** „LAN Access" aktivieren
2. Einen **PIN-Code** setzen (bei LAN-Freigabe Pflicht)
3. Server neu starten
4. Von anderen LAN-Geräten unter `http://<Server-IP>:5000` zugreifen
5. Mit PIN anmelden

### Tipps

- Mit **LAN Share Token** (`/s/`-Pfad) können PIN-freie Gastzugriffslinks geteilt werden
- Auf dem Serverbildschirm wird ein QR-Code angezeigt, der vom Smartphone gescannt werden kann
- Auch Trusted-Proxy-Auth über Reverse Proxy wird unterstützt

---

## 8. Automatisch Tags setzen

Wenn manuelles Taggen mühsam ist und Sie KI die Bilder analysieren und automatisch taggen lassen wollen.

### Vorgehen A: WD-Tagger (schnell, auf Tags spezialisiert)

1. In **Settings** das WD-Tagger ONNX-Modell herunterladen
2. Von der Tools-Seite oder Detail-Modal auf **WD-Tagger ausführen** klicken
3. Danbooru-artige Tags werden automatisch zugewiesen

### Vorgehen B: AI Analysis (natürliche Sprache, hohe Genauigkeit)

1. Unter **Settings > AI Analysis** einen Ollama- oder OpenAI-kompatiblen Server hinzufügen
2. Die Analyse aus dem **AI-Analyse-Tab** im Detail-Modal ausführen
3. Eine Bildbeschreibung in natürlicher Sprache wird generiert

### Tipps

- WD-Tagger unterstützt auch einen Kombinationsmodus mit VLM-Engine (OpenAI-API-kompatibel)
- NSFW-Filter und Tag-Normalisierung werden automatisch als Nachverarbeitung angewendet
- Das Schreiben von Tags in XMP-Metadaten wird unterstützt, was die Integration mit anderen Tools erleichtert

---

## 9. Statistiken und Berichte ansehen

Um Trends und Wachstum Ihrer Bildbibliothek zu erkennen.

### Vorgehen

1. In der Navigation die **Stats**-Seite öffnen und Gesamtstatistik prüfen
2. Auf der **Monthly Report**-Seite detaillierte Monatsberichte einsehen
   - Monatliche Dateianzahl, Vergleich zum Vormonat, Top-20-Tags, neue Tags, Quellenverteilung, Tagesstatistik
3. Im Abschnitt **Trophies** erreichte Erfolgstrophäen prüfen

### Tipps

- Trophäen werden in 6 Kategorien (Milestone / Streak / Diversity / Source / Hidden) und 4 Stufen (Bronze bis Platin) stufenweise freigeschaltet
- Bei korrekt gesetzter Zeitzone (Settings > Appearance) werden Tagesstatistiken exakt

---

## 10. Mit KI-Agenten über MCP verbinden

Um von Claude Desktop oder anderen MCP-fähigen KI-Tools aus die Bildbibliothek zu bedienen.

### Vorgehen

1. In den Einstellungen des MCP-Clients (z. B. Claude Desktop) den YU AI Manager MCP-Server registrieren
   ```json
   {
     "command": "python",
     "args": ["-m", "mcp_server"],
     "env": { "YU_DB": "./tags.db" }
   }
   ```
2. Der KI in natürlicher Sprache Anweisungen geben wie „Suche Bilder" oder „Füge zu Favoriten hinzu"
3. Mehr als 60 Tools wie `search_images`, `add_favorite`, `trigger_scan` sind verfügbar

### Tipps

- Aus der MCP-Client-Extension können externe MCP-Server (stdio / SSE / Streamable HTTP) angebunden werden
- Mit API-Key-Authentifizierung können externe Tools die REST-API ohne CSRF-Header direkt aufrufen
- Mit der Hailo-GenAI-Extension ist auch Integration über OpenAI-SDK-kompatible Endpunkte möglich

---

## 11. Hailo-10H als OpenAI-kompatiblen Server nutzen

Wenn Sie in einer Umgebung mit Hailo-10H NPU diesen als OpenAI-SDK-kompatiblen lokalen KI-Server nutzen möchten. Externe Tools wie Open WebUI, Continue.dev oder eigene Skripte können Hailos LLM / VLM / Speech-to-Text / CLIP-Embeddings direkt verwenden.

### Unterstützte Endpunkte

| Endpunkt | Funktion | Entsprechende OpenAI API |
|---|---|---|
| `GET /ext/hailo-genai/v1/models` | Liste heruntergeladener Modelle | List Models |
| `POST /ext/hailo-genai/v1/chat/completions` | Textgenerierung, Bildverständnis (VLM) | Chat Completions |
| `POST /ext/hailo-genai/v1/audio/transcriptions` | Sprachtranskription | Audio Transcriptions |
| `POST /ext/hailo-genai/v1/embeddings` | Text→Vektor (CLIP) | Embeddings |

### Vorgehen

1. Auf der Seite **Extensions > GenAI** sicherstellen, dass die Hailo-GenAI-Extension aktiviert ist
2. Gewünschtes Modell herunterladen (LLM: `qwen2.5-1.5b-chat` usw.; VLM: `llava-v1.6-vicuna-7b` usw.)
3. Im externen Tool die Verbindung konfigurieren und **Base URL** wie folgt setzen:
   ```
   http://localhost:5000/ext/hailo-genai/v1
   ```
   (Portnummer entsprechend der YU-AI-Manager-Startkonfiguration anpassen)
4. API Key wird nicht benötigt (lokaler Zugriff). Falls das Tool einen API Key fordert, einen Dummy-Wert eingeben (z. B. `dummy`)

### Verbindungsbeispiele mit externen Tools

#### Open WebUI

Unter Settings > Connections > OpenAI API hinzufügen:
- **URL**: `http://localhost:5000/ext/hailo-genai/v1`
- **API Key**: `dummy`

#### Continue.dev (VS Code AI-Assistent)

In `~/.continue/config.json` hinzufügen:
```json
{
  "models": [{
    "title": "Hailo Qwen2.5",
    "provider": "openai",
    "model": "qwen2.5-1.5b-chat",
    "apiBase": "http://localhost:5000/ext/hailo-genai/v1",
    "apiKey": "dummy"
  }]
}
```

#### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:5000/ext/hailo-genai/v1",
    api_key="dummy",
)

# Textgenerierung
res = client.chat.completions.create(
    model="qwen2.5-1.5b-chat",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(res.choices[0].message.content)

# Bildverständnis (VLM) — base64-Bild anhängen
import base64
with open("image.png", "rb") as f:
    b64 = base64.b64encode(f.read()).decode()

res = client.chat.completions.create(
    model="llava-v1.6-vicuna-7b",
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": "Describe this image."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ],
    }],
)

# Sprachtranskription
res = client.audio.transcriptions.create(
    model="whisper-1",
    file=open("audio.wav", "rb"),
)

# Text-Embedding (CLIP)
res = client.embeddings.create(
    model="clip",
    input="a girl standing by the sea",
)
print(len(res.data[0].embedding))  # 512
```

### Unterstützte Parameter

- **Chat Completions**: `model`, `messages`, `stream`, `temperature` (0-2), `max_tokens` (64-2048)
- **Audio Transcriptions**: `model`, `file`, `language`, `response_format` (json / text / verbose_json)
- **Embeddings**: `model`, `input` (String oder String-Array)
- **Modell-Aliase**: `whisper-1` → whisper-base, `clip` / `text-embedding-clip` → clip-vit-b-16

### Hinweise

- **Geräte-Exklusivität**: Hailo-10H kann gleichzeitig nur ein GenAI-Modell (LLM oder VLM oder S2T) laden. Das Umschalten der Modi erfolgt auf der GenAI-Seite
- **Beschränkung von Bild-URLs**: Aus Sicherheitsgründen werden Bild-URLs mit `http://` blockiert. Verwenden Sie das Format `data:image/...;base64,...` oder das YU-AI-Manager-Format `file_id:`
- **CLIP-Embedding**: Nur Text→Vektor unterstützt. Bild→Vektor ist über den Endpunkt `/api/semantic/` verfügbar
- **Audioformate**: Andere Formate als WAV (MP3, M4A, OGG usw.) erfordern ffmpeg
- **`usage`-Feld**: Token-Zähler geben immer 0 zurück (Einschränkung der Hailo NPU)
