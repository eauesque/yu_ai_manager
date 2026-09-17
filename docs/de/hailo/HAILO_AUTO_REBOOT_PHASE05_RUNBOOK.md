# Hailo Auto-Reboot Phase 0.5 — Betriebshandbuch für diese Umgebung

**Erstellt**: 2026-05-17 (v4.215.1)
**Zielumgebung**: — Pi 5, der dieses Repository betreibt
**Zweck**: Ein eigenständiges Handbuch, das den Start, die Überprüfung und den Abschluss der Phase-0.5-Beobachtung ermöglicht, auch wenn die ursprüngliche Chat-Sitzung verloren gegangen ist.
**Designspezifikation**: `docs/superpowers/specs/2026-05-17-hailo-auto-reboot-design.md` (rev3 APPROVED)
**Allgemeiner Operator-Leitfaden**: `docs/de/hailo/HAILO_AUTO_REBOOT_PHASE05.md` (dieses Dokument ist die umgebungsspezifische Variante)

---

## 0. Voraussetzungen und bereits abgeschlossene Arbeiten

- Phase-0.5-Beobachtungsimplementierung in v4.215.1 in main gemergt und gepusht (Commit `80af4fb73` + Merge `69be148c6`)
- `config.json` (Repository-Wurzel) enthält bereits den `hailo.auto_reboot`-Block, **hinzugefügt am 2026-05-17**
  - Empfohlene Einstellungen: `mode = "lazy"` + `dry_run = true`
  - Sicherungskopie: `config.json.bak.<Zeitstempel>`
- **Es wird kein tatsächlicher Neustart ausgelöst** (`dry_run = true` + Phase 0.5 zeichnet nur `would_fire`-Events auf)

config.json überprüfen:

```bash
cd /home/pi/GitHub/yu_ai_manager
jq .hailo.auto_reboot config.json
# → {"mode":"lazy","dry_run":true,...} sollte erscheinen
```

---

## 1. Erststart und Aktivierungsverfahren

### 1.1 Server-Neustart

Ein Neustart ist erforderlich, um die Konfigurationsänderung zu übernehmen. **Starten Sie mit der aktuell verwendeten Startmethode neu.**

Typischer Startbefehl (an die eigene Umgebung anpassen):

```bash
cd /home/pi/GitHub/yu_ai_manager
uv run python web_ui.py --config config.json --db data/tags.db
```

Falls als systemd-Dienst betrieben, den entsprechenden Unit mit `sudo systemctl restart <unit>` neu starten.

### 1.2 Überprüfung innerhalb von 30 Sekunden nach dem Start (3 Punkte)

#### A. Ist das `boot_baseline`-Event aufgezeichnet?

```bash
tail -n 20 /home/pi/GitHub/yu_ai_manager/logs/hailo_auto_reboot.log
```

Erwartet: Eine Zeile mit `{"event":"boot_baseline","state":"idle","mode":"lazy","dry_run":true,"cma_free_mb":<int|null>,"hailo_runtime_version":"5.3.0",...}`.

**Fehlerbehebung, falls nicht vorhanden**:

- `logs/hailo_auto_reboot.log` existiert nicht → Judge-Loop läuft nicht (möglicherweise nicht im `["full"]`-Modus gestartet oder `TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE`-Umgebungsvariable gesetzt)
- Datei existiert, ist aber leer → Pfadauflösungsfehler in `core/hailo_device_core/auto_reboot_logger.py`; Berechtigungen des `logs/`-Verzeichnisses prüfen
- `cma_free_mb: null` → `/proc/meminfo` konnte nicht gelesen werden (erwartetes Verhalten auf Nicht-Pi-Hardware, harmlos)

#### B. Ist opt-in über die `/api/system/cma`-Antwort aktiv?

Bei Browser-PIN-Login ist kein API-Key erforderlich. Entweder curl verwenden oder im Browser-DevTools-Konsole (bei PIN-Login) ausführen:

```js
fetch("/ext/hailo-genai/api/system/cma").then(r => r.json()).then(j => console.log(j.cma.auto_reboot))
```

Erwartet:

```json
{
  "enabled": true,
  "mode": "lazy",
  "dry_run": true,
  "state": "idle",
  "consecutive_rejects": 0
}
```

Bei `enabled: false` oder `mode: "off"` → prüfen, ob `hailo.auto_reboot.mode` in config.json `"lazy"` ist und ob der Server vollständig neu gestartet wurde.

#### C. Keine Startfehler in `error.log`?

```bash
tail -n 50 /home/pi/GitHub/yu_ai_manager/logs/error.log | grep -iE "hailo_auto_reboot|auto_reboot"
```

Keine Ausgabe bedeutet OK. Bei Fehlern siehe „8. Bekannte Fallstricke" am Ende dieses Dokuments.

---

## 2. Täglicher Betrieb während der Beobachtungsphase

### 2.1 Normaler Betrieb

**Hauptaktion**:

- **LLM-Chat wie gewohnt nutzen** über `/ext/hailo-genai/chat` oder `/tools` (z. B. Qwen3-1.7B)
- VLM / S2T nach Bedarf verwenden
- Längere Sitzungen (30+ Minuten am Stück) und mehrfacher Modellwechsel sind ebenfalls sinnvoll, um die Beobachtungsdaten zu erweitern

Keine spezielle Überprüfung erforderlich. **Je normaler die Nutzung, desto mehr Daten sammelt Phase 0.5** — das ist das Designziel.

### 2.2 Wöchentliche Überprüfung (einmal pro Woche, ~5 Minuten)

```bash
cd /home/pi/GitHub/yu_ai_manager

# Anzahl der Vorkommen je Event-Typ
jq -r '.event' logs/hailo_auto_reboot.log | sort | uniq -c

# Zeitstempel und CmaFree für would_fire-Events
grep would_fire logs/hailo_auto_reboot.log | jq -r '[.ts, .cma_free_mb] | @tsv'

# Grund für drain_entered (cma vs. rejects)
grep drain_entered logs/hailo_auto_reboot.log | jq -r '[.ts, .cma_free_mb, .consecutive_rejects, .reason] | @tsv' 2>/dev/null || \
  grep drain_entered logs/hailo_auto_reboot.log | head -10
```

**Prüfpunkte**:

- `would_fire` tritt mindestens 1 Mal auf → Phase-1-Einführung lohnt sich (prüfen, ob die aufgezeichneten Zeitpunkte mit manuellen Neustarts übereinstimmen)
- `prewarn_entered` tritt häufig auf, schreitet aber nicht zu `drain_entered` fort → `prewarn_threshold_mb` (80 MB) möglicherweise zu niedrig; neu kalibrieren
- `drain_entered`-Grund ist immer `rejects` → DRAIN ist reject-gesteuert; andere Maßnahmen als Schwellenwertanpassung erforderlich

---

## 3. Beobachtungsabschluss und Entscheidungskriterien für Phase 1

### 3.1 Erforderlicher Beobachtungszeitraum

**Mindestens 7 Tage / Empfohlen 14 Tage**. Der Zeitraum sollte mindestens folgende Muster abdecken:

- Normaler LLM-Chat
- Langer LLM-Chat (30+ Minuten in einer Sitzung)
- VLM / S2T-Modellwechsel
- Mindestens eine `acquire_genai`-Vorab-Ablehnung (unzureichender CmaFree)
- Erster Ladevorgang nach Pi-Neustart

### 3.2 Numerische Kriterien für die Phase-1-Einführung

Zusammenfassung:

```bash
cd /home/pi/GitHub/yu_ai_manager
jq -r '.event' logs/hailo_auto_reboot.log | sort | uniq -c
```

Entscheidungstabelle:

| Beobachtungsergebnis | Phase-1-Entscheidung |
|---|---|
| `would_fire` ≥ 1 | **GO** (automatisches Neustarten hat Mehrwert) |
| `would_fire` = 0, `drain_entered` ≥ 1 | Schwellenwerte anpassen und Phase 1 erwägen (DRAIN wird erreicht, aber `would_fire` nicht — `fire_grace_seconds` könnte verkürzt werden) |
| Nur `prewarn_entered`, `drain_entered` = 0 | Aktueller Schwellenwert erreicht nie den „kritischen" Zustand → Phase 1 je nach Nutzungsmuster ggf. nicht nötig |
| Alle Events 0 (nur `boot_baseline`) | CMA wird bei dieser Nutzung nicht erschöpft → Phase 1 nicht erforderlich |

### 3.3 Aufgaben nach Beobachtungsabschluss

1. Zusammenfassung in `docs/de/hailo/HAILO_AUTO_REBOOT_PHASE05_OBSERVATION_RESULTS.md` (neu) speichern
2. Bei Phase-1-Einführung: zu Phase 1 in spec rev3 §5.2 (UI-DRAIN-Banner + i18n) übergehen; Schwellenwerte in §3.1 auf Basis der Beobachtungsdaten neu bestätigen
3. Falls Phase 1 nicht benötigt: `mode = "off"` in config.json setzen und Beobachtungsprotokoll archivieren

---

## 4. Deaktivierungsverfahren (Notfall / Beobachtungsstopp)

```bash
cd /home/pi/GitHub/yu_ai_manager
jq '.hailo.auto_reboot.mode = "off"' config.json > config.json.tmp && mv config.json.tmp config.json
# Server neu starten
```

Auch bei `mode = "off"` werden JSONL-Events weiterhin aufgezeichnet (WARN-Ausgabe in `error.log` wird unterdrückt). Um vollständig zu deaktivieren, Umgebungsvariable verwenden:

```bash
TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE=1 uv run python web_ui.py ...
```

---

## 5. Protokolldatei-Referenz (Verwandte Dateien)

| Datei | Zweck |
|---|---|
| `logs/hailo_auto_reboot.log` | **Hauptprotokoll dieser Funktion**. JSONL-Format; Rotation bei 10 MB × 30 Sicherungskopien |
| `logs/hailo_cma.log` | Bestehender CMA-Event-Logger (seit v4.214.10). Zeichnet VDevice/Modell-Lifecycle-Events wie `acquire_genai` auf |
| `logs/error.log` | Anwendungsweites Fehlerprotokoll. Wenn `mode != "off"`, werden auch WARN-Zusammenfassungen für `drain_entered` / `would_fire` ausgegeben |

---

## 6. Zugehörige Code-Stellen (für zukünftige Untersuchungen)

| Funktion | Datei |
|---|---|
| Zustandsmaschine + RejectTracker | `core/hailo_device_core/auto_reboot.py` |
| JSONL writer | `core/hailo_device_core/auto_reboot_logger.py` |
| Hintergrundschleifen-Einstiegspunkt | `core/web/startup_background_hailo_judge.py` |
| Hintergrundaufgaben-Registrierung | `core/web/startup_background.py` (`hailo_auto_reboot_judge`) |
| Konfigurationsstandards | `core/configuration/defaults.py` (`hailo.auto_reboot`) |
| acquire_genai-Hook | `core/hailo_device_core/device_manager_genai.py` |
| `/api/system/cma`-Erweiterung | `extensions/builtin_hailo_genai/hailo_genai_ext.py` |
| Unit-Tests | `tests/test_hailo_auto_reboot_judge.py`, `tests/test_hailo_auto_reboot_logger.py` |

---

## 7. Prüfverlauf (Referenz)

Diese Implementierung hat den vollständigen AGENTS-Prüfprozess durchlaufen (siehe v4.215.1-Commit-Nachricht). Einzelne Berichtsdateien wurden unter `.claude/agent-outputs/` abgelegt, sind jedoch in `.gitignore` eingetragen und werden nicht von git verwaltet. Sie können bei Bedarf neu generiert werden.

---

## 8. Bekannte Fallstricke

| Symptom | Ursache und Abhilfe |
|---|---|
| Nichts erscheint in `logs/hailo_auto_reboot.log` | Server nicht neu gestartet / `mode = "off"` noch gesetzt / nicht im `["full"]`-Modus gestartet / `TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE`-Umgebungsvariable gesetzt |
| `cma_free_mb: null` tritt dauerhaft auf | Läuft auf Nicht-Pi-Hardware (z. B. WSL2) oder `/proc/meminfo` konnte nicht gelesen werden; auf tatsächlicher Pi-Hardware erneut prüfen |
| `hailo_runtime_version: null` | `hailo_platform`-Paket in dieser Umgebung nicht installiert; auf tatsächlichem Pi 5 wird dieser Wert gesetzt, wenn HailoRT 5.3.0 installiert ist |
| `would_fire` erscheint nie | Nutzungslast zu gering oder Schwellenwerte zu locker; langen Endlos-Chat / Modellwechsel versuchen und erneut beobachten |
| `eager`-Modus konfiguriert, aber nicht aktiv | In Phase 0.5 fällt `eager` absichtlich auf `off` zurück (mit Warnungsprotokoll); geplant für Implementierung in Phase 1+ |

---

## 9. Notfall-Rollback

Falls die Phase-0.5-Implementierung selbst ein Problem aufweist (geringe Wahrscheinlichkeit, da kein tatsächlicher Neustart ausgelöst wird):

```bash
cd /home/pi/GitHub/yu_ai_manager
# Rollback von v4.215.1 auf v4.214.13 (nur Spezifikation, vor der Implementierung)
git revert -m 1 69be148c6
git push
```

Oder **vollständige Deaktivierung nur über die Konfiguration** (empfohlen):

```bash
# Zur Startumgebung hinzufügen und Server neu starten
TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE=1 uv run python web_ui.py ...
```

---

## 10. Pflege dieses Dokuments

- Nach Beobachtungsabschluss **die §3.3-Zusammenfassung am Ende dieses Dokuments ergänzen** (für die Phase-1-Entscheidung in zukünftigen Chat-Sitzungen erforderlich)
- Nach Phase-1-Einführung dieses Dokument in `HAILO_AUTO_REBOOT_PHASE05_RUNBOOK_ARCHIVED.md` umbenennen und ein neues Phase-1-Handbuch erstellen
- Dieses Dokument liegt unter `/home/pi/GitHub/yu_ai_manager/docs/de/hailo/HAILO_AUTO_REBOOT_PHASE05_RUNBOOK.md` (git-verwaltet)
