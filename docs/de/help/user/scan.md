# Scan

## Scan-Verzeichnis registrieren

Settings > Scan Tab um Scan-Verzeichnisse hinzuzufügen.

- Drag & Drop zum Neuordnen
- Checkbox zum Ein-/Ausschalten
- Mehrere Verzeichnisse möglich

## Scan ausführen

- Nach Verzeichnis-Hinzufügung Auto-Start
- Manueller Scan über Tools-Seite oder MCP `trigger_scan`
- Scan-Fortschritt wird in Echtzeit über SSE benachrichtigt

## Auto Scan (Watcher)

Mit Auto Scan Watcher Extension aktiviert werden Dateiänderungen in registrierten Verzeichnissen automatisch erkannt und gescannt.

## Remote Dateisysteme

Beim Scannen von Remote-Pfaden (WSL / NAS / SMB), Settings > Remote FS Tab Timeout-Einstellungen anpassen.

## Großbibliotheken scannen

Beim Scannen von Hunderttausenden bis Millionen Dateien beachten Sie:

- **Suche während Scan möglich**: Such-API nutzt schreibgeschützte DB-Verbindung, nicht betroffen von Scan-Schreibsperren
- **WAL Auto-Management**: Während Scan wird WAL-Checkpoint alle 2000 Dateien auto-ausgeführt, um WAL-Aufblähung zu verhindern
- **scan.db_busy Event**: SSE-Events bei Scan-Start/Completion, um Frontend Busy-Status anzuzeigen

## Scan-Worker-Prozess

Ab v3.27.0 läuft Scan in separatem Prozess von web_ui.py.
Dies bedeutet **Web-UI Neustart bricht Scan nicht ab**.

### Wie es funktioniert

- Scan von WebUI starten startet Background-Worker-Prozess
- Worker schreibt Fortschritts-JSON und PID-Datei nach `/tmp/yu-scan/`
- WebUI pollt diese Datei und relayed über SSE zum Frontend
- Nach WebUI-Neustart wird laufender Worker auto-erkannt und Fortschritt-Display wiederhergestellt

### Operieren von CLI

Worker können auch direkt von CLI gesteuert werden. Funktioniert auch wenn WebUI gestoppt ist.

```bash
# Status überprüfen
python -m core.scan.scan_worker status

# Laufenden Scan stoppen (graceful shutdown — Unterbrechungsposition in DB speichern)
python -m core.scan.scan_worker stop

# Scan direkt von CLI starten
python -m core.scan.scan_worker start --db ./tags.db --root /path/to/images

# Optionen
#   --recursive / --no-recursive  Subverzeichnisse einschließen (Standard: recursive)
#   --scan-zips                   Bilder in ZIP/7z scannen
#   --force                       Bestehende Dateien neu-scannen
#   --resume                      Unterbrochenen Scan fortsetzen
#   --config config.json          Konfigurationsdatei angeben
```

### Sicherheitsmechanismen

- **Parent-Prozess-Überwachung**: Worker von WebUI gestartet überwacht WebUI-Prozess-Existenz in 60-Sekunden-Intervallen. Wenn WebUI abnormal endet, Worker stoppt auto nach Speicherung der Unterbrechung
- **SIGTERM-Unterstützung**: Mit `stop`-Befehl oder `kill` SIGTERM gesendet, Worker beendet aktuelle Verarbeitung, committed in DB, speichert Unterbrechungsposition, stoppt
- **Duplikats-Verhinderung**: Gleichzeitig nur ein Worker möglich

### Fehlerbehebung

Wenn Worker nicht antwortet:

```bash
# PID überprüfen
cat /tmp/yu-scan/worker.pid

# Prozess erzwungen beenden
kill -9 $(cat /tmp/yu-scan/worker.pid)

# Restliche Dateien aufräumen
rm -f /tmp/yu-scan/worker.pid /tmp/yu-scan/progress.json
```

## Scan-Fehler

Bei Scan-Fehlern MCP `get_scan_errors` nutzen.

