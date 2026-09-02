# LLM Router WebUI

Ein Admin-Dashboard erreichbar unter `/llm-router`. Es ermöglicht Ihnen, den Status registrierter Backends zu überprüfen und diese zu aktivieren/deaktivieren.

---

## Seiten-Layout

```
┌─────────────────────────────────────┐
│  🤖 LLM Router          [Refresh All] │
├─────────┬─────────┬────────┬─────────┤
│Backends │ Enabled │ Models │ Aliases │  ← Summary cards
├─────────┴─────────┴────────┴─────────┤
│  Backends table                      │
├───────────────────────────────────────┤
│  Routing Aliases table               │
└───────────────────────────────────────┘
```

### Zusammenfassungskarten (4)

| Karte | Inhalt |
|---|---|
| **Backends** | Gesamtanzahl der im Katalog registrierten Backends |
| **Enabled** | Anzahl der Backends, die nicht deaktiviert sind |
| **Models** | Gesamtanzahl der von allen Backends verfügbar gemachten Modelle |
| **Routing aliases** | Anzahl der in der Konfigurationsdatei definierten Aliase |

Die Kartenwerte werden beim Laden der Seite automatisch durch das Abrufen von `/api/llm_router/status` gerendert.

---

## Backends-Tabelle

Jede Zeile entspricht einem einzelnen physischen Backend (z. B. eine Ollama-Instanz).

### Spaltenbeschreibungen

| Spalte | Beschreibung |
|---|---|
| **Alias** | Ein eindeutiger Kurzname, der das Backend identifiziert (z. B. `ollama-mac`, `mdns-pi5-hailo`). Wird als Schlüssel für die Routing-Konfiguration und Alias-Auflösung verwendet |
| **Base URL** | Die Basis-URL des OpenAI-kompatiblen Endpunkts des Backends (z. B. `http://192.168.1.10:11434`) |
| **Status** | Konnektivitätsstatus des Backends. Siehe Details unten |
| **SLO** | Ressourcenlast-Status des Backends (`vision_idle` / `vision_active` / `unknown`). Wird für Hailo Vision Backends verwendet |
| **Models** | Anzahl der Modelle, die bei der letzten Probe abgerufen wurden. Möglicherweise erweiterbar zur Anzeige einer detaillierten Liste je nach Implementierung |
| **Last Seen** | Datum und Uhrzeit der letzten erfolgreichen Antwort (ISO 8601). `null`, wenn noch nie eine erfolgreiche Antwort empfangen wurde |
| **Actions** | Pro-Backend-Aktionsschaltflächen (siehe unten) |

### Status-Werte

| Wert | Bedeutung |
|---|---|
| `ready` | Die letzte Probe war erfolgreich und die Modellliste wurde abgerufen |
| `unreachable` | Ein Verbindungs-Timeout oder Fehler ist aufgetreten |
| `unknown` | Noch keine Probe wurde ausgeführt (z. B. direkt nach dem Start) |
| `probing` | Eine Probe wird gerade ausgeführt (kann kurz in der UI während einer Aktualisierung angezeigt werden) |

> **Hinweis**: `unreachable` Backends werden von Routing ausgeschlossen, bleiben aber im Katalog. Nach Netzwerkwiederherstellung führen Sie "Refresh All" oder eine einzelne Aktualisierung durch, um sie auf `ready` zurückzusetzen.

### SLO-Werte

| Wert | Bedeutung |
|---|---|
| `vision_idle` | Vision-Aufgabe ist untätig. LLM-Last ist niedrig |
| `vision_active` | Eine Vision-Aufgabe wird ausgeführt. Der LLM-Router kann andere Backends bevorzugen |
| `unknown` | SLO-Informationen sind nicht verfügbar (nicht-Hailo Backend, oder Abruf ist fehlgeschlagen) |

---

## Refresh All Schaltfläche

Klicken Sie auf **Refresh All** oben rechts, um eine Probe auf allen Backends zu erzwingen, ihre Modelllisten und Status zu aktualisieren.

- Die Schaltfläche ist während der Ausführung deaktiviert und die Seite wird nach Abschluss neu gerendert
- Internes Verhalten: Ruft `POST /api/llm_router/refresh` (kein Body) auf, um `discover_all` für alle Backends auszuführen
- Einzelne Backend-Aktualisierungen können über eine Refresh-Schaltfläche in der Actions-Spalte verfügbar sein (implementierungsabhängig)

---

## Deaktivieren / Aktivieren einzelner Backends

### Schritte

1. Schauen Sie sich die **Actions**-Spalte in der Backends-Tabelle an
2. Klicken Sie auf die **Disable**-Schaltfläche in der Zeile des Backends, das Sie deaktivieren möchten
3. Die Schaltfläche ändert sich zu **Enable** und die Zeile wird ausgegraut
4. Um es wieder zu aktivieren, klicken Sie auf **Enable**

### Verhalten und Persistierung

- Änderungen werden sofort im In-Memory-Katalog reflektiert
- Gleichzeitig wird ein atomarer Schreibzugriff auf `data/llm_router_state.json` durchgeführt

  ```json
  {
    "version": 1,
    "disabled_aliases": ["ollama-slow", "mdns-pi5"]
  }
  ```

- Der deaktivierte Status wird über Anwendungsneustarts beibehalten
- Falls ein mDNS-entdecktes Backend vor dem Start deaktiviert war, wird der deaktivierte Status nach der Erkennung automatisch angewendet (`_pending_disabled` Mechanismus)
- Falls der Schreibzugriff fehlschlägt, wird der In-Memory-Status auf den vorherigen Stand zurückgerollt, um Inkonsistenz mit der Festplatte zu vermeiden

### Verhalten deaktivierter Backends

- Von Routing in OpenAI-kompatiblen Endpunkten wie `/v1/chat/completions` ausgeschlossen
- Direktes Routing zu einem deaktivierten Backend gibt `503 Service Unavailable` zurück
- Deaktivierte Backends werden weiterhin in der WebUI-Tabelle angezeigt (zur Statusübersicht und Reaktivierung)

---

## Routing Aliases Tabelle

Zeigt die Zuordnung zwischen logischen Modellnamen und physischen Modell-IDs wie in der Konfigurationsdatei definiert an.

| Spalte | Beschreibung |
|---|---|
| **Alias** | Der logische Name, den Clients im `model`-Parameter angeben (z. B. `default-llm`, `fast-chat`) |
| **Physical Model** | Die physische Modell-ID, die die Anfrage tatsächlich verarbeitet (Format: `backend-alias/model-name`, z. B. `ollama-mac/qwen2.5:7b`) |

### Rolle von Aliasen

Aliase ermöglichen es Ihnen, Backends oder Modelle zu wechseln, ohne Client-Code zu ändern.

- Clients senden Anfragen unter Verwendung eines logischen Namens wie `"model": "default-llm"`
- Der LLM Router löst `default-llm → ollama-mac/qwen2.5:7b` auf und leitet die Anfrage weiter
- Bei der Migration eines Backends auf einen anderen Computer ändern Sie einfach das Alias-Ziel

Aliase werden statisch in der Konfigurationsdatei definiert, und die WebUI zeigt sie im Nur-Lesen-Modus an. Änderungen erfordern das Bearbeiten der Konfigurationsdatei und den Neustart der Anwendung.

---

## Häufige Operationen

### Wenn ein Backend unerreichbar ist

1. Überprüfen Sie, ob der Backend-Service (Ollama, usw.) ausgeführt wird
2. Führen Sie **Refresh All** oder eine einzelne Aktualisierung durch
3. Falls das Problem weiterhin besteht, überprüfen Sie die Fehlerdetails in der `last_error`-Spalte (oder API-Antwort)

### Dauerhaftes Deaktivieren eines mDNS-entdeckten Backends

1. Klicken Sie auf **Disable** in der Actions-Spalte des Ziel-Backends
2. Der Alias wird in `data/llm_router_state.json` gespeichert, daher bleibt er auch nach erneuter Erkennung deaktiviert

### Vorübergehendes Stoppen der Last auf einem bestimmten Backend

Verwenden Sie **Disable**, um es sofort von Routing auszuschließen, dann klicken Sie auf **Enable**, um es wieder herzustellen, wenn Sie fertig sind. Ein Neustart ist nicht erforderlich.
