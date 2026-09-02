# Performance-Optimierungsleitfaden

Tuning-Leitfaden für komfortablen Betrieb von YU AI Manager in Umgebungen mit 100.000+ Dateien.
Viele Optimierungen laufen im Standardbetrieb automatisch, aber für die jeweilige Umgebung angepasst kann noch mehr verbessert werden.

---

## 1. Empfohlene Hardware

| Element | Mindestanforderung | Empfohlen (100.000+ Dateien) |
|------|---------|------------------------|
| CPU | 2 Kerne | 4+ Kerne (Thumbnail-Generierung parallelisiert) |
| RAM | 4 GB | 8 GB+ |
| Speicher | HDD | **SSD dringend empfohlen** — direkte Auswirkung auf DB-Antwortzeit |
| Netzwerk | — | Bei LAN-Nutzung 1 Gbps+ |

**Besonders wichtig**: DB-Datei (`data/tags.db`) unbedingt auf SSD platzieren.
Bilder können auf HDD, aber DB auf HDD verlangsamt Suche und Browsing erheblich.

---

## 2. Erstbeobachtungs-Scan-Optimierung

### Scan-Roots aufteilen

Großmengen-Scans auf einmal dauern lange.
Empfehlung: Scan-Roots in mehrere Ordner aufteilen unter Settings > Scan Roots.

- Meistgenutzte Ordner zuerst scannen
- Restliche in Scan-Warteschlange einreihen (automatisch sequenziell verarbeitet)
- Doppelte Ordner-Registrierung wird automatisch erkannt und übersprungen

### Browsen während des Scans möglich

Während des Scans funktionieren Suche und Thumbnail-Anzeige normal.
Intern werden Nur-Lese-DB-Verbindungen verwendet, sodass Scan-Schreibvorgänge Browsing nicht blockieren.

### Automatische Optimierung nach Scan-Abschluss

Bei Scan-Abschluss werden DB-Statistiken automatisch aktualisiert (ANALYZE).
Dies optimiert den Ausführungsplan für Suchanfragen, wodurch nachfolgende Suchen schneller werden.
Kein manueller Eingriff erforderlich.

---

## 3. Browsing-Geschwindigkeit verbessern

### Service-Worker-Cache

Der Browser-Service-Worker cached folgende Inhalte automatisch:

| Typ | Cache-Limit | Effekt |
|------|-------------|------|
| Thumbnails | 5.000 Einträge | Raster-Anzeige ab 2. Mal sofort |
| Vorschau (1200px) | 200 Einträge | Modal-Anzeige beschleunigt |
| Originalgröße | 50 Einträge | Zuletzt gesehene Bilder sofort erneut anzeigen |

Service Worker wird automatisch vom Browser verwaltet.
Zum Leeren: Browser DevTools > Application > Storage.

### Virtuelles Scrollen aktivieren

Bei Anzeige Tausender Suchergebnisse verbessert virtuelles Scrollen die Darstellungs-Performance erheblich.

**Aktivierung**: Settings > Appearance > "Virtual Scroll" ON

Virtuelles Scrollen rendert nur im sichtbaren Bereich, reduziert Speicherverbrauch und Darstellungslast erheblich.
Für Bibliotheken in Zehntausender-Größenordnung dringend empfohlen.

### WebP-Thumbnails

Thumbnails werden im WebP-Format generiert (30-40% kleiner als JPEG).
Reduziert Übertragungsvolumen, besonders effektiv bei LAN-Zugriff.
Automatisch angewendet, keine Konfiguration erforderlich.

---

## 4. Such-Performance

### Index-Effekte

Die DB enthält automatisch für gängige Suchmuster optimierte Indizes.
Datumssortierung, Tag-Filter, Pfadsuche funktionieren schnell.

**Richtwerte**:
- Suche ohne Filter: Unter 50ms für 280.000+ Dateien
- Suche mit Tag-Filter: Unter 100ms
- Pfadsuche (FTS5): Unter 50ms

### FTS5-Volltextsuche vs. LIKE-Suche

Für Pfadsuchen wird automatisch FTS5 (Full-Text Search)-Index verwendet.
Im Vergleich zu traditioneller LIKE-Suche (`%keyword%`) 20-100x schneller.

FTS5 nicht verfügbar (bei Upgrades von alten DBs): Automatischer Fallback auf LIKE-Suche.
Nach einem Scan wird FTS5-Index aufgebaut.

**Hinweis für CJK-Suche**: Suchen mit Kanji/Hiragana/Katakana können intern LIKE-Fallback verwenden.
Normale Funktion aufgrund SQLite FTS5-Tokenizer-Einschränkung.

---

## 5. Video-Wiedergabe-Optimierung

### Faststart-Cache

Zur Beschleunigung der MP4/MOV-Videowiedergabe wird Faststart-Verarbeitung automatisch angewendet.
Faststart-verarbeitete Videos beginnen sofort mit Streaming-Wiedergabe.

| Element | Wert |
|------|-----|
| Cache-Speicherort | `cache/faststart/` |
| Kapazitätslimit | 4 GB (automatisch per LRU verwaltet) |
| Dateilimit | 500 MB |
| Ziel | MP4, MOV (WebM nicht erforderlich, übersprungen) |

**Erfahrungswerte**:

| Dateigröße | Ohne Faststart | Mit Faststart |
|--------------|---------------|---------------|
| 5-50 MB | 2-10 Sek. Wartezeit | ~200ms Wiedergabestart |
| 50-200 MB | 10-60 Sek. Wartezeit | ~500ms Wiedergabestart |
| 200-500 MB | Minuten Wartezeit | ~1 Sek. Wiedergabestart |

### FFmpeg prüfen

Faststart-Verarbeitung benötigt FFmpeg:

```bash
ffmpeg -version
```

---

## 6. Speicherverbrauchsverwaltung

### SQLite mmap

Für große DBs (100.000+ Dateien) wird SQLite mmap (Memory-Mapped I/O) automatisch auf 1 GB gesetzt.
Leseanfragen werden dadurch durch OS-Seiten-Cache beschleunigt.

**Bei 4 GB RAM oder weniger**: mmap kann Speicher belasten.
Beim häufigen Auftreten von Swapping andere Anwendungen schließen.

### Browser-Tab-Verwaltung

YU AI Manager kommuniziert per SSE (Server-Sent Events) in Echtzeit mit jedem Tab.

- Maximal 10 simultane SSE-Verbindungen pro IP
- Unbenötigte Tabs schließen um Verbindungsressourcen freizugeben
- Viele offene Tabs erhöhen auch Browser-Speicherverbrauch

**Empfehlung**: Maximal 3-4 gleichzeitig geöffnete Tabs.

---

## 7. Fehlerbehebung — "Zu langsam"-Checkliste

### Grundlegende Prüfungen

- [ ] **SSD verwendet?**: `data/tags.db` auf HDD verlangsamt alle Operationen
- [ ] **FFmpeg installiert?**: Pflicht für Video-Beschleunigung
- [ ] **Browser-Tab-Anzahl**: Mehr als 5 prüfen

### Browsing langsam

- [ ] **Virtuelles Scrollen aktivieren**: Settings > Appearance > Virtual Scroll
- [ ] **Browser-Cache nicht löschen**: Service-Worker-Cache ist aktiv
- [ ] **Scan laufend?**: Während Scan normal nutzbar, aber erste Thumbnail-Generierung dauert

### Suche langsam

- [ ] **Scan abschließen**: ANALYZE läuft nach Scan-Abschluss
- [ ] **Suchergebnis überschreitet 100.000**: Filter hinzufügen (Tags, Datum, Pfad usw.)

### Video-Wiedergabe langsam

- [ ] **FFmpeg prüfen**: Mit `ffmpeg -version` prüfen
- [ ] **Faststart-Cache-Kapazität**: `cache/faststart/`-Ordner überschreitet 4 GB nicht (automatisch verwaltet)
- [ ] **Dateigröße**: Dateien über 500 MB sind vom Faststart-Cache ausgenommen

### Server insgesamt langsam

- [ ] **Simultane Zugriffe**: SSE-Verbindungen über 10 pro IP
- [ ] **Upload laufend?**: Dateien nahe 100 MB-Upload-Limit
- [ ] **Settings > Logs-Tab**: Fehler und Warnungen im Server-Log prüfen

---

## 8. Performance-Richtwerte

Richtwerte für gut optimierte Umgebungen:

| Operation | 280.000 Dateien | 100.000 Dateien |
|------|-----------------|-----------------|
| Raster-Anzeige (erstmalig) | 200-500ms | 100-300ms |
| Raster-Anzeige (mit Cache) | Unter 50ms | Unter 50ms |
| Tag-Suche | Unter 100ms | Unter 50ms |
| Pfadsuche (FTS5) | Unter 50ms | Unter 30ms |
| Thumbnail (Cache-Treffer) | Unter 5ms | Unter 5ms |
| Videostart (Faststart) | 200ms | 200ms |

Wenn diese Werte erheblich überschritten werden, Checkliste oben überprüfen.

---

## Schnellmodus (Rust-Server)

Auf unterstützten Geräten wechselt der Start automatisch auf den Rust-Server (`yu-server`).

Unter Einstellungen -> „Server" -> „Schnellmodus" lässt sich die **Bezugsart** wählen:

- **Veröffentlichte Binärdatei laden** (Standard) -- baut nie
- **Auf diesem Gerät bauen** -- lädt nie
- **Laden, und bauen falls das fehlschlägt**

Das Bauen benötigt 8 GB freien Speicher und beansprucht CPU und Arbeitsspeicher stark. **Auf Geräten mit wenig RAM (etwa einem Raspberry Pi) kann der Auslagerungsspeicher aufgebraucht werden und das gesamte System abstürzen.** Während der Kompilierung bleiben alle Funktionen nutzbar. Zum Bauen unter Windows werden zusätzlich die Visual-Studio-Buildtools (der Linker) benötigt.

Der Fortschritt erscheint auf demselben Bildschirm: verstrichene Zeit, die letzte Zeile von cargo, Erfolg oder Fehlschlag und ob der Build unterbrochen wurde. Das Rohprotokoll liegt unter `bin/fast-mode-build.log`.

Wird der Schnellmodus wegen des Zustands dieses Verzeichnisses abgelehnt (veraltetes Web-Bundle, eine Erweiterung außerhalb der mitgelieferten Liste), ändert das Holen einer Binärdatei daran nichts -- dann wird weder geladen noch gebaut. Auch dieser Grund wird dort angezeigt.
