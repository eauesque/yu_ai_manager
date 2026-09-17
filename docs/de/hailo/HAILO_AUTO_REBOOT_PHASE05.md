# Hailo Auto-Reboot Phase 0.5 Betriebshandbuch

**Erstellt**: 2026-05-17 (v4.215.0)
**Ziel**: Raspberry Pi 5 + Hailo-10H + HailoRT 5.3.0 CMA-Leak-Beobachtungsbetrieb
**Status**: Beobachtungsphase. Es wird kein tatsächlicher Neustart durchgeführt; `would_fire`-Ereignisse werden nur aufgezeichnet.

---

## 1. Zweck von Phase 0.5

Phase 0.5 ist die Beobachtungsphase des Auto-Reboot-Designs gegen CMA-Leaks in HailoRT 5.3.0 + `hailo1x_pci`.

In dieser Phase berechnet der Zustandsautomat folgende Zustände:

| Zustand | Bedingung |
|---|---|
| `idle` | Normalzustand |
| `prewarn` | `CmaFree < 80 MB` hält 180 Sekunden an |
| `draining` | `CmaFree < 30 MB` hält 60 Sekunden an, oder `acquire_genai`-Vorab-Reject tritt 3-mal in Folge auf |
| `would_fire` | 120 Sekunden seit `draining` vergangen |

Wichtig: In Phase 0.5 wird der Pi auch beim Erreichen von `would_fire` NICHT neu gestartet. Das Ereignis wird lediglich als JSON Lines in `logs/hailo_auto_reboot.log` aufgezeichnet.

---

## 2. Warum der Standardwert `mode = "off"` ist

Der Standardwert von `hailo.auto_reboot.mode` ist `"off"`. Da ein automatischer Neustart die Arbeit des Betreibers unterbrechen kann, wird die Beobachtung nur in Umgebungen gestartet, in denen der Betreiber explizit opt-in vorgenommen hat.

Die empfohlene Konfiguration für Phase 0.5 lautet:

```json
{
  "hailo": {
    "auto_reboot": {
      "mode": "lazy",
      "dry_run": true,
      "prewarn_threshold_mb": 80,
      "prewarn_duration_seconds": 180,
      "drain_threshold_mb": 30,
      "drain_duration_seconds": 60,
      "drain_consecutive_rejects": 3,
      "fire_grace_seconds": 120,
      "poll_interval_seconds": 30
    }
  }
}
```

`dry_run = true` ist eine Voraussetzung für Phase 0.5. Der tatsächliche Neustart-Pfad wird in Phase 4 und später behandelt.

### 2.1 Opt-in-Verfahren

Die Startkonfiguration priorisiert die über `--config` oder `TAGDB_CONFIG` angegebene Datei. Wenn nicht angegeben, wird `config.json` im Repository-Stammverzeichnis gelesen, dann `tagdb_config.json`.

Beispiel:

```bash
cd <repo>
cp config.json config.json.bak.$(date +%Y%m%d-%H%M%S)
```

Fügen Sie die folgenden Einstellungen zu `<repo>/config.json` oder der im Betrieb über `--config` / `TAGDB_CONFIG` angegebenen JSON-Datei hinzu:

```json
{
  "hailo": {
    "auto_reboot": {
      "mode": "lazy",
      "dry_run": true,
      "poll_interval_seconds": 30
    }
  }
}
```

Starten Sie den Server neu, um die Konfiguration anzuwenden. Behalten Sie die tatsächlich verwendeten Argumente gemäß Ihrer Startmethode bei.

```bash
uv run python web_ui.py --config config.json --db data/tags.db
```

Wenn Sie mit systemd betreiben, starten Sie die entsprechende Unit neu:

```bash
sudo systemctl restart yu-ai-manager.service
```

### 2.2 Deaktivierungsverfahren

Setzen Sie `hailo.auto_reboot.mode` in derselben Konfiguration auf `"off"` zurück und starten Sie den Server neu.

```json
{
  "hailo": {
    "auto_reboot": {
      "mode": "off",
      "dry_run": true
    }
  }
}
```

Bei `mode = "off"` bleiben JSON-Lines-Beobachtungsereignisse erhalten, es wird jedoch keine WARN-Zusammenfassung in `error.log` ausgegeben.

---

## 3. Interpretation der Protokolle

Beobachtungsprotokolle werden in folgende Datei geschrieben:

```text
logs/hailo_auto_reboot.log
```

Das Format ist JSON Lines. Die wichtigsten Ereignisse sind:

| Ereignis | Bedeutung |
|---|---|
| `boot_baseline` | Beobachtungsstartpunkt beim Hochfahren |
| `prewarn_entered` | PREWARN-Bedingung erfüllt |
| `drain_entered` | DRAIN-Bedingung erfüllt |
| `would_fire` | Zeitpunkt, der in Phase 1+ zum Neustart-Auslöser würde |
| `drain_cleared` | CMA erholt, DRAIN aufgehoben |

Beispiel:

```json
{"event":"would_fire","cma_free_mb":18,"mode":"lazy","dry_run":true,"state":"would_fire","hailo_runtime_version":"5.3.0"}
```

Beispiele für Bestätigungsbefehle:

```bash
tail -F logs/hailo_auto_reboot.log | jq -r '[.ts, .event, .cma_free_mb, .state] | @tsv'
```

```bash
grep would_fire logs/hailo_auto_reboot.log
grep drain_entered logs/hailo_auto_reboot.log
```

Wenn `would_fire` häufig auftritt, deutet dies darauf hin, dass mit den aktuellen Schwellenwerten im tatsächlichen Betrieb wahrscheinlich ein Pi-Neustart erforderlich sein wird. Wenn hingegen nur `prewarn_entered` erscheint, ohne zu `drain_entered` fortzuschreiten, können die Schwellenwerte oder Toleranzzeiten vor Phase 1 neu angepasst werden.

---

## 4. API-Überprüfungsverfahren

Überprüfen Sie `/api/system/cma` mit dem Admin-API-Schlüssel.

```bash
curl -H "X-API-Key: <admin-key>" \
  http://<host>:<port>/ext/hailo-genai/api/system/cma
```

Sehen Sie sich `cma.auto_reboot.enabled`, `cma.auto_reboot.mode`, `cma.auto_reboot.state` und `cma.auto_reboot.consecutive_rejects` in der Antwort an.

```json
{
  "cma": {
    "auto_reboot": {
      "enabled": true,
      "mode": "lazy",
      "state": "idle",
      "consecutive_rejects": 0
    }
  }
}
```

---

## 5. Beobachtungszeitraum

Das Ziel sind 1–2 Wochen. Stellen Sie sicher, dass der Zeitraum mindestens folgende Muster abdeckt:

- Normaler LLM-Chat-Betrieb
- Langzeit-Chat-Betrieb
- Operationen, die zu Hailo-GenAI-Modell-Ladefehlern oder Vorab-Rejects führen
- Erster Ladevorgang nach Pi-Neustart

Die Beobachtung gilt als abgeschlossen, wenn Häufigkeitsdaten für `prewarn_entered` / `drain_entered` / `would_fire` über 1–2 Wochen aggregiert werden können. Überprüfen Sie nach der Beobachtung die Anzahl der `would_fire`-Vorkommen, den Grund für `drain_entered` (`cma` / `rejects`) und die Rate des `CmaFree`-Rückgangs, um die Schwellenwerte vor der Bereitstellung von Phase 1 endgültig festzulegen.

Aggregationsbeispiel:

```bash
jq -r '.event' logs/hailo_auto_reboot.log | sort | uniq -c
```

---

## 6. Verwandte Dokumente

- `docs/superpowers/specs/2026-05-17-hailo-auto-reboot-design.md`
- `docs/ja/hailo/HAILO_CMA_LEAK_HAILORT_5_3_0.md`
- `logs/hailo_cma.log` (`core/hailo_device_core/device_helpers.py::log_hailo_cma_event`)
- `logs/hailo_auto_reboot.log` (`core/hailo_device_core/auto_reboot_logger.py`)
