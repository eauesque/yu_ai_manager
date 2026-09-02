# Test-Wartungs-Playbook

Die ersten Anlaufpunkte, wenn pytest durch veraltete Testinfrastruktur oder Umgebungsabhängigkeiten stehen bleibt.

## Ziel

- `failed` und `skipped` voneinander trennen
- Normale umgebungsbedingte Skips von zu reparierenden stale Tests unterscheiden
- Den kürzesten Weg fixieren, wenn ein Broad Run (`pytest tests -q --maxfail=1`) stehen bleibt

## Grundbefehle

Reguläre Gesamtprüfung:

```powershell
venv\Scripts\python.exe -m pytest tests -q --maxfail=1
```

Skip-Gründe ebenfalls anzeigen:

```powershell
venv\Scripts\python.exe -m pytest tests -q -rs
```

Shared Test Server strikt behandeln:

```powershell
$env:PYTEST_STRICT_AUTOSTART_SERVER="1"
venv\Scripts\python.exe -m pytest tests\api -q
```

Lizenz-Audit:

```powershell
venv\Scripts\python.exe scripts\license_audit.py
```

## Wie die aktuellen Skips zu lesen sind

Im Broad Run vom 2026-04-21 verteilen sich die Hauptgründe für Skips auf folgende 5 Kategorien.

### 1. Shared Test Server nicht gestartet

Der häufigste Skip. Der Shared Server aus `tests/conftest.py` wird best-effort gestartet; wenn das scheitert, fallen Browser-/Server-abhängige Tests nicht auf fail, sondern auf skip.

Typischer Grund:

- `Shared test server unavailable on port <PORT>`

Hauptziel:

- `tests/api/`
- Browser-UX-Review-Gruppe
- Browser-/Server-abhängige Tests von LAN Cowork / Fleet
- Live-Browser-Tests, die `TARGET_URL` / `BASE` / `TARGET` nutzen
- Audit-Tests, die eigene Playwright-/WebKit-Fixtures statt `page` verwenden

Im normalen Run sind das **normale Skips**. Aber in folgenden Fällen lohnt Untersuchung:

- Unit-Tests, die nicht auf Shared Server angewiesen sind, werden mit demselben Grund geskippt
- Shared-Server-Tests, die vorher liefen, sind plötzlich massenhaft geskippt
- Auch mit `PYTEST_STRICT_AUTOSTART_SERVER=1` bleibt die Ursache unklar

### 2. OS-spezifische Tests

Sandbox/AppArmor/Process-Isolation ist Linux-exklusiv. Auf Windows ist Skip korrekt.

Typische Beispiele:

- `tests/basic/test_os_isolation.py`
- `tests/test_process_isolation_integration.py`

Typische Gründe:

- `Linux only`
- `AppArmor ist Linux-spezifisch`

Das sind **normale Skips**.

### 3. Optionale Abhängigkeiten / fehlende externe Komponenten

Test-Gruppen, die in Umgebungen ohne bestimmte Pakete oder externe Knoten nicht laufen.

Typische Beispiele:

- mDNS-E2E: `optional zeroconf package is not installed`
- Browserstart: `Playwright unavailable`, `launch failed`
- ONNX / YAML / ComfyUI / externe Inferenz-Knoten nicht verbunden

Das sind **normale Skips**. Nicht zu reparieren; nur die Voraussetzungen fehlen.

### 4. Fehlende Testdaten

Browser-Tests, die Bilder, Suchergebnisse, Chatlogs oder mehrere Datensätze benötigen und mit der leichten DB nicht laufen, werden geskippt.

Typische Gründe:

- `No search results available in database`
- `Übersprungen, da keine Bilder in der DB`
- `Mindestens 2 Dateien erforderlich`
- `No prompts to test copy`

Meist **normale Skips**. Wenn die Fixture eigentlich die nötigen Daten bereitstellen sollte, auf Stale-Werden prüfen.

### 5. Rate-Limits / Schutz externer APIs

Integrationstests, die externe Dienste oder Rate-Limits respektieren, werden geskippt.

Typisches Beispiel:

- `Übersprungen wegen Rate-Limit`

Das ist **normales Skip**.

### 6. Langfristige Fuzz- / Burn-in-Tests

Das Burn-in unter `tests/fuzz/` ist für die zusätzliche Belastungs- und Crash-Resilienz-Prüfung gedacht, nicht fürs reguläre Regressions-Checks.

Standardmäßig per Marker-Ausdruck in `pytest.ini` ausgeschlossen.

Zum gezielten Ausführen:

```powershell
venv\Scripts\python.exe -m pytest tests\fuzz -q -m fuzz
```

Bei Bedarf:

```powershell
$env:FUZZ_DURATION="60"
venv\Scripts\python.exe -m pytest tests\fuzz\test_api_fuzz.py -q -m fuzz
```

Diese **gehören nicht in den normalen Broad Run**.

## Muster, die als abnormal behandelt werden sollten

Das Folgende nicht mit "ist ja nur ein Skip" abtun, sondern als Test-Wartungsziel betrachten.

### A. Früher bestandene Lightweight-Tests fallen jetzt im Setup-Skip aus

Beispiele:

- API-Smoke-Tests, die mit app/client-Fixture allein funktionieren sollten, werden in Shared-Server-Abhängigkeit gezogen
- Migration-/Schema-/DB-Helper-Unit-Tests scheitern, weil Runtime Global State zuvor initialisiert worden sein müsste

In diesen Fällen Mismatch zwischen Test-Harness und Implementierungsvoraussetzungen vermuten.

### B. Broad Run läuft, aber Einzel-Run schlägt fehl

Typisch:

- Abhängigkeit von Process-Global State
- Der Test hängt zufällig an Nebeneffekten eines früheren Tests im Broad Run

Auch im Einzel-Run muss der Zustand reproduzierbar sein.

### C. Skip-Grund ist vage

Schlechte Beispiele:

- `failed`
- `not ready`
- `something wrong`

Der Skip-Grund sollte in einem kurzen Satz sagen, was fehlt.

## Reparatur-Reihenfolge

1. Hard Failures beheben, die den Broad Run stoppen
2. Stale Tests reparieren, die nur im Einzel-Run brechen
3. Shared-Server-/Browser-Skips von fail auf safe skip umstellen
4. Optionale Abhängigkeiten und reale Hardware-Abhängigkeiten als Optional-Skip beibehalten

## Was in dieser Wartungsrunde fixiert wurde

- Browser-/Server-abhängige Tests: Shared-Server-unavailable wird konsistent als skip behandelt, nicht als fail
- License Audit betrachtet nur die in `requirements*.txt` deklarierten Abhängigkeiten, nicht das gesamte venv
- Die Test-DB erfüllt das aktuelle Search-Schema inklusive Path-FTS-Voraussetzung
- Migration 54 / 55 sind robust gegenüber Weiterentwicklung des Base-Schemas und nicht initialisiertem Runtime State

## Entscheidungskriterien im Zweifel

- Wenn nur das Voraussetzungsumfeld fehlt, reicht skip
- Bei veralteten Erwartungen, die der aktuellen Implementierung nicht folgen, Test reparieren
- Bei Abhängigkeit von Nebeneffekten im Broad Run Implementierung oder Test reparieren
- Wenn ein Unit-Test Process-Global State verlangt, Design hinterfragen
