# Task-Scheduler

## Überblick

Der Task-Scheduler ist eine Funktion zur automatischen Ausführung regelmäßiger Aufgaben wie Datenbankwartung oder externes Service-Polling. Ein APScheduler-basierter Hintergrund-Scheduler verwaltet Jobs mit Cron/Intervall-Triggern.

Über die WebUI-Scheduler-Seite (`/scheduler`) können Job-Listen anzeigen, hinzufügen, löschen, pausieren und sofort ausführen.

## Setup

Der Scheduler ist standardmäßig aktiviert. Steuerbar über `config.json` `scheduler.enabled`:

```json
{
  "scheduler": {
    "enabled": true,
    "jobs": {
      "db_vacuum": { "enabled": true, "trigger": "cron", "day_of_week": "sun", "hour": 3, "minute": 0 },
      "db_integrity_check": { "enabled": true, "trigger": "cron", "hour": 4, "minute": 0 },
      "thumbnail_cleanup": { "enabled": true, "trigger": "cron", "hour": 5, "minute": 0 }
    }
  }
}
```

In `config.json` eingetragene Jobs werden beim Server-Start automatisch registriert. Über die WebUI hinzugefügte Jobs gelten nur für die aktuelle Server-Session (bei Neustart verschwunden).

## Integrierte Job-Liste

### Datenbank-Wartung

| Job-ID | Beschreibung | Empfohlene Häufigkeit |
|-----------|------|---------|
| `db_vacuum` | SQLite VACUUM ausführen und ungenutzten Speicher zurückgewinnen | Wöchentlich |
| `db_integrity_check` | `PRAGMA integrity_check` für Datenbankintegrität | Täglich |
| `db_backup` | Datenbankbackup erstellen (via builtin-backup Extension) | Täglich |

### Cache und Index-Verwaltung

| Job-ID | Beschreibung | Empfohlene Häufigkeit |
|-----------|------|---------|
| `thumbnail_cleanup` | Abgelaufene Thumbnail-Cache-Dateien löschen | Täglich |
| `prune_unused_tags` | Verwaiste Tag-Einträge ohne Datei-Verknüpfung löschen | Wöchentlich bis Monatlich |
| `refresh_monthly_stats` | Vorberechneten Cache der Monatsstatistiken aktualisieren | Täglich |
| `rebuild_groups_index` | Ordner-/Archiv-Gruppen-Index-Cache neu aufbauen | Wöchentlich |

### Externer Service-Integration

| Job-ID | Beschreibung | Empfohlene Häufigkeit |
|-----------|------|---------|
| `github_issue_poll` | GitHub-API pollen und neue Issues in lokale Warteschlange einreihen | 5 Min. bis 1 Std. |
| `bsky_notification_poll` | Bluesky-API pollen und neue Benachrichtigungen abrufen | 5 Min. bis 1 Std. |

## Trigger-Konfiguration

### Cron-Trigger

Zu bestimmten Zeiten/Wochentagen/Datum ausführen. Ähnlich Unix-Cron.

| Parameter | Wert-Beispiele | Beschreibung |
|-----------|--------|------|
| `hour` | `3`, `*/6`, `1,13` | Stunde (0-23). `*` = stündlich |
| `minute` | `0`, `30`, `0,30` | Minute (0-59). `*` = jede Minute |
| `day` | `1`, `15`, `1,15` | Tag (1-31). `*` = täglich |
| `day_of_week` | `sun`, `mon-fri`, `0-4` | Wochentag. `*` = täglich |

**Beispiel**: Am 1. und 15. jeden Monats um 2:30 Uhr ausführen

```json
{ "trigger": "cron", "day": "1,15", "hour": 2, "minute": 30 }
```

### Intervall-Trigger

In regelmäßigen Abständen wiederholt ausführen.

| Parameter | Wert-Beispiele | Beschreibung |
|-----------|--------|------|
| `hours` | `2` | Stundenintervall |
| `minutes` | `30` | Minutenintervall |

**Beispiel**: Alle 30 Minuten ausführen

```json
{ "trigger": "interval", "minutes": 30 }
```

## WebUI-Verwendung

### Job-Liste

Beim Öffnen der Scheduler-Seite wird die Liste registrierter Jobs angezeigt. Status (aktiv/pausiert), Trigger-Einstellungen und nächste Ausführungszeit pro Job prüfen.

### Job hinzufügen

1. **Job hinzufügen**-Button klicken
2. Job-ID (eindeutiger Name) eingeben
3. Auszuführende Funktion aus Dropdown wählen
4. Trigger-Typ (cron / interval) wählen
5. Zeitplan-Parameter eingeben (`*` für Wildcard)
6. **Hinzufügen** klicken

### Job-Operationen

- **Jetzt ausführen**: Job sofort einmalig außerhalb des Zeitplans ausführen
- **Pausieren / Fortsetzen**: Regelmäßige Ausführung vorübergehend anhalten/fortsetzen
- **Löschen**: Job vollständig entfernen (config.json-Jobs werden beim nächsten Start wiederhergestellt)

### Ausführungshistorie

Unterhalb der Seite werden die letzten Ausführungen (max. 50 Einträge) angezeigt. Status Erfolg/Fehler und Ergebnismeldungen prüfen. Bei Job-Ausführungsabschluss per SSE in Echtzeit aktualisiert.

## MCP-Tools

MCP-Client (Claude Desktop usw.) kann den Scheduler bedienen:

| Tool | Beschreibung |
|--------|------|
| `get_scheduler_status` | Scheduler-Betriebszustand abrufen |
| `list_scheduled_jobs` | Registrierte Job-Liste abrufen |
| `trigger_scheduled_job` | Job sofort ausführen |
| `pause_scheduled_job` | Job pausieren |
| `resume_scheduled_job` | Job fortsetzen |
| `get_scheduler_history` | Ausführungshistorie abrufen |

## Tipps

- **Externe Polling-Jobs** (`github_issue_poll`, `bsky_notification_poll`): Intervall-Trigger geeignet. Cron-Festzeit kann Polling-Intervall zu groß machen
- **`db_vacuum`**: Schreibsperre erforderlich — für ruhige Zeiten (nachts) empfohlen
- **`db_backup`**: Respektiert Cooldown-Einstellungen der builtin-backup Extension. Kurzes Intervall wird während Cooldown-Periode übersprungen
- **Ausführungshistorie** liegt im Speicher (max. 100 Einträge). Bei Server-Neustart wird Historie gelöscht
