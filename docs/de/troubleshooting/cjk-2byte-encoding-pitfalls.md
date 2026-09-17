# Fallen und Gegenmaßnahmen bei CJK- / 2-Byte-Zeichenkodierung

Dieses Dokument fasst die typischen Bugs im 2-Byte-Raum, vor allem rund um Japanisch (CP932/Shift-JIS), und die in diesem Projekt gewählten Lösungen zusammen.
Ziel ist es, Entwicklern und KI-Agenten, die auf dieselben Probleme stoßen, als Referenz zu dienen.

---

## 1. Absturz der Windows-Konsole durch cp932

### Symptom

Die Windows `cmd.exe` / PowerShell / Git Bash haben als Standard-Ausgabekodierung **cp932 (Shift-JIS)**.
Wird mit `print()` ein Unicode-Zeichen ausgegeben, das nicht in cp932 existiert, stürzt das Programm sofort mit `UnicodeEncodeError` ab.

```
UnicodeEncodeError: 'charmap' codec can't encode character '—' in position 12
```

### Beispiele problematischer Zeichen

| Zeichen | Name | Wo verwendet |
|------|------|------------|
| `—` (U+2014) | em dash | Trennzeichen in Log-Ausgaben |
| `–` (U+2013) | en dash | Fortschrittsanzeige |
| `✓ ✗ ✅ ❌ ⚠️` | Häkchen, Emojis | Erfolg/Fehler-Anzeige |
| `🧹 📦 📁 🔍 🔧` | Emojis | Anzeige der Verarbeitungsinhalte |
| `█ ░` | Blockzeichen | Fortschrittsbalken |

### Gegenmaßnahme

- **In `print()` nur ASCII-sichere Zeichen verwenden**: `[OK]`, `[NG]`, `[!]`, `--`, `#`, `-` usw.
- Dasselbe gilt für Logger (`logging`). Wenn das Handler-Encoding cp932 ist, tritt dasselbe Problem auf
- Mit `PYTHONIOENCODING=utf-8` lässt sich das umgehen, aber da es von der Benutzerumgebung abhängt, ist defensives Beharren auf ASCII sicherer

### Auswirkungsumfang

In diesem Projekt wurden in einem Durchlauf **19 Dateien** korrigiert (v2.28.0).
KI (Claude/GPT) erzeugt mit hoher Wahrscheinlichkeit Emojis oder em dashes,
daher ist dies **einer der wichtigsten Punkte bei der Review KI-generierten Codes**.

---

## 2. Verschrottete ZIP-Dateinamen (CP437 mojibake)

### Symptom

ZIP-Dateien, die unter älterem Windows (95/98/XP) erstellt wurden,
speichern Dateinamen in **Shift-JIS (CP932)**, doch die ZIP-Spezifikation enthält keine Encoding-Information.
Pythons `zipfile` dekodiert, wenn das UTF-8-Flag (Bit 11) nicht gesetzt ist, mit **CP437**,
wodurch japanische Dateinamen zu `âwâCâèâb` verunstaltet werden.

### Gegenmaßnahme: 10-stufige Fallback-Kette

In `core/infra_core/encoding.py` ist eine Prioritätsliste der CJK-Encodings definiert:

```
UTF-8 (zipfile versucht zuerst) → CP932 → EUC-JP → ISO-2022-JP
→ EUC-KR → CP949 → GB2312 → GBK → Big5 → CP950
```

- `chardet` / `cchardet` werden **nicht** verwendet: bei kurzen Dateinamen (10-30 Byte) zu viele Fehleinschätzungen
- Feste Prioritätsliste ist reproduzierbarer und einfacher zu debuggen

### Parameter `metadata_encoding` in Python 3.11+

```python
# Ab Python 3.11 kann metadata_encoding direkt angegeben werden
zf = zipfile.ZipFile(path, metadata_encoding='cp932')
```

Da dies ZIPs mit anderen Encodings als CP932 nicht abdeckt,
wird bei Fehlschlag ohne `metadata_encoding` erneut geöffnet und mit `repair_cp437_name()` versucht, den Namen wiederherzustellen.

### Für 7z

7-Zip hat eine eigene Dateinamenverarbeitung. Über das 7z-CLI kann ebenfalls
CP437-mojibake auftreten, der gleichartig mit `repair_cp437_name()` wiederhergestellt wird.

---

## 3. Scanner hängt bei 2-Byte-Zeichen in ZIP/7z

### Symptom

Beim Lesen des Zentralverzeichnisses alter, Shift-JIS-kodierter ZIPs gerät
`zipfile.ZipFile()` bei bestimmten Byte-Folgen in blockierendes I/O und hängt.
Tritt besonders bei Archiven mit vielen Dateien auf.

### Gegenmaßnahme

1. **Timeout-Schutz**: Einführung des Daemon-Thread-Helpers `run_with_timeout()`
   - Dateilistung (listing): 30 Sekunden
   - Scan-I/O: 60 Sekunden
2. **scan_errors-Tabelle** (migration v24): Timeouts und Encoding-Fehler dauerhaft in der DB protokollieren
   - Fehlertypen: `encoding` / `timeout` / `scan` / `archive_scan` / `archive_timeout` / `filesystem`

---

## 4. SQLite FTS5 tokenchars Anführungszeichen-Problem

### Symptom

Bei der `tokenize`-Direktive von SQLite FTS5 kommt es je nach Kombination
der Anführungszeichen beim Verwenden der Option `tokenchars` zu Parse-Fehlern.

```sql
-- NG: Äußere Single Quotes + innere Double Quotes → Parse-Fehler
tokenize='unicode61 tokenchars "_:."'

-- OK: Äußere Double Quotes + innere Single Quotes
tokenize="unicode61 tokenchars '_:.'"
```

### Ursache

Der Parser des SQLite-FTS5-Tokenizers kann Double Quotes innerhalb äußerer Single Quotes
nicht korrekt analysieren. Auch Verhaltensunterschiede zwischen SQLite-Versionen (bestätigt auf 3.45.1) sind möglich.

### Gegenmaßnahme

Auf Python-Seite Triple-Quote-Varianten unterscheiden:

```python
# OK: In Pythons ''' innen kann man im SQL sowohl " als auch ' verwenden
con.execute('''
    CREATE VIRTUAL TABLE fts USING fts5(
        col1,
        tokenize="unicode61 tokenchars '_:.'"
    )
''')
```

### Entdeckungsweg

Tritt beim Neuaufbau der FTS5-Tabelle in Migration 29 dieses Projekts auf.
KI-generierter Code nutzte die äußere Single-Quote-Syntax,
was den Server beim Start in SQLite 3.45.1 crashen ließ (in v2.70.1 behoben).

---

## 5. UTF-16-Kodierung in WebP-EXIF

### Symptom

Einige Bildgenerierungstools (insb. NAI-Serie) speichern WebP-EXIF-Metadaten
mit **UTF-16 (mit BOM)**.
Normale UTF-8-Dekodierung erzeugt Mojibake.

### Gegenmaßnahme

- BOM (Byte Order Mark) erkennen und UTF-16 BE/LE bestimmen
- Ohne BOM heuristisch BE/LE schätzen
- Als Fallback UTF-8 → latin-1 versuchen

---

## 6. Kodierung von PNG tEXt-Chunks

### Symptom

Laut PNG-Spezifikation sind tEXt-Chunks als **Latin-1 (ISO-8859-1)** definiert,
doch die meisten KI-Bildgenerierungs-Tools speichern UTF-8-kodierte Strings unverändert.
Bei `latin-1`-Dekodierung entsteht Mojibake bei Japanisch.

### Gegenmaßnahme

Zuerst mit UTF-8 dekodieren und bei Fehler auf latin-1 zurückfallen:

```python
try:
    text = raw_bytes.decode('utf-8')
except UnicodeDecodeError:
    text = raw_bytes.decode('latin-1')
```

---

## 7. Windows-Pfad-Backslashes in config.json

### Symptom

Windows-Pfade enthalten Backslashes (`\`); wenn Pfade manuell in JSON-Dateien geschrieben werden,
entstehen fehlerhafte Escape-Sequenzen.

```json
{"scan_roots": ["C:\Users\test"]}  // \U und \t werden als Escape-Sequenzen interpretiert
```

### Gegenmaßnahme

- `_repair_json_backslashes()` repariert dies beim Serverstart automatisch
- Intern werden Pfade normalisiert gespeichert

---

## 8. pathlib und WSL UNC-Pfade

### Symptom

Unter WSL (Windows Subsystem for Linux) kann `pathlib.Path.exists()` für
UNC-Pfade (`\\server\share\...`) falsche Ergebnisse liefern.

### Gegenmaßnahme

- Für die Existenzprüfung von UNC-Pfaden `os.path.exists()` verwenden
- `pathlib` ist zwar praktisch, bei Netzwerkpfaden aber unzuverlässig

---

## 9. UTF-8 BOM bei CSV-Export

### Symptom

Öffnet man UTF-8-CSV-Dateien ohne BOM in Excel, entsteht Mojibake.
Excel interpretiert UTF-8 ohne BOM als ANSI (in japanischer Umgebung CP932).

### Gegenmaßnahme

```python
buf.write("﻿")  # UTF-8 BOM for Excel compatibility
```

Ein BOM (`﻿`) wird am Anfang der CSV eingefügt.
Excel erkennt die Datei dann korrekt als UTF-8.

---

## 10. `ensure_ascii=False` in JSON

### Symptom

Pythons `json.dumps()` escaped standardmäßig Nicht-ASCII-Zeichen als `\uXXXX`.
Wenn MCP-Tool-Antworten japanische Tagnamen oder Dateipfade als `タグ` enthalten,
fällt es KI-Agenten schwer, den Inhalt zu verstehen.

### Gegenmaßnahme

```python
json.dumps(data, ensure_ascii=False, indent=2)
```

In diesem Projekt wird dies in allen MCP-Tool-Modulen (10 Dateien) einheitlich verwendet.

---

## 11. Ausgabe-Dekodierung des Ordnerauswahl-Dialogs

### Symptom

Beim Aufruf des Ordnerauswahl-Dialogs aus Windows-PowerShell ist die
Ausgabe von `subprocess` in CP932 kodiert.
Standard-UTF-8-Dekodierung verursacht `UnicodeDecodeError`.

### Gegenmaßnahme

```python
result = subprocess.run(..., capture_output=True)
path = result.stdout.decode('cp932', errors='replace').strip()
```

Mit `errors='replace'` sichere Verarbeitung auch bei Dekodierungsfehlern.

---

## Hinweise für KI-Agenten

Viele der obigen Probleme sind Muster, **die KI beim Code-Generieren leicht übersieht**:

1. **Keine Emojis oder Schmuckzeichen in `print()`** — KI verwendet sie oft für optische Aufwertung
2. **Keine Annahmen über Dateinamen-Encoding** — UTF-8-Annahmen brechen in CP932-Umgebungen
3. **SQLite-Anführungszeichen real testen** — manchmal funktioniert die dokumentierte Variante nicht
4. **`json.dumps()` mit `ensure_ascii=False`** — Pflicht bei japanischen Daten
5. **Subprocess-Ausgaben mit dem Umgebungs-Encoding dekodieren** — Windows nutzt oft CP932
6. **CSV mit BOM speichern** — für Excel-Kompatibilität

---

## Referenz: Verwandte Dateien im Projekt

| Datei | Inhalt |
|---------|------|
| `core/infra_core/encoding.py` | CJK-Fallback-Kette, CP437-Mojibake-Reparatur |
| `core/schema_core/schema_migrate_steps_29.py` | Korrekte Schreibweise der FTS5 tokenchars Anführungszeichen |
| `core/tools/fs_dialog.py` | CP932-Dekodierung des Ordnerauswahl-Dialogs |
| `core/configuration/json_rw.py` | Reparatur der config.json-Backslashes |
| `routes/collections.py` | BOM-Anfügen beim CSV-Export |
| `CLAUDE.md` | Abschnitt „Windows-Hinweise > Konsolenausgabe" |
