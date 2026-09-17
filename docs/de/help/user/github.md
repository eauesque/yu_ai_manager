# GitHub Integration

## Überblick

GitHub Integration ist eine Erweiterung zur zentralen Verwaltung von GitHub-Repositories, Issues, Pull Requests, Discussions und Releases aus YU AI Manager. Unterstützt mehrere GitHub-Konten, Token werden verschlüsselt sicher gespeichert. Dashboard für schnelle Übersicht über Benachrichtigungen und Repository-Statistiken, mit KI-basierter Issue-Triage-Funktion.

## Setup

### GitHub Personal Access Token (PAT) erhalten

1. GitHub anmelden, **Settings > Developer settings > Personal access tokens > Tokens (classic)** öffnen
2. **Generate new token (classic)** klicken
3. Token-Name eingeben und Ablaufdatum setzen
4. Bei Bereichen **`repo`** ankreuzen (für vollständigen Repository-Zugriff erforderlich)
5. **Generate token** klicken und angezeigten Token kopieren

> **Hinweis**: Token wird nur auf diesem Bildschirm angezeigt. Unbedingt kopieren bevor geschlossen wird.

### Konto hinzufügen

1. GitHub-Karte im Extensions-Launcher klicken oder direkt auf `/ext/github` navigieren
2. **Settings**-Tab öffnen
3. **Konto hinzufügen** klicken
4. Folgende Informationen eingeben:
   - **Label**: Anzeigename des Kontos (z.B. "Privat", "Arbeit")
   - **Token**: PAT von oben
   - **Repositories**: Zu überwachende Repositories in `owner/repo`-Format (mehrere möglich)
5. Nach Speichern Konto aus Dropdown auswählen

## Funktionen

### Dashboard

Nach Kontoauswahl lädt das Dashboard automatisch:

- **Benachrichtigungen**: Liste ungelesener GitHub-Benachrichtigungen
- **Repository-Statistiken**: Sterne, Forks, offene Issues als Karten
- **Übersichtskarten**: Schneller Überblick über überwachte Repositories

### Issues

- Filtern nach Repository, Status (open/closed)
- Issue-Details anzeigen (Text, Kommentare, Labels)
- Neue Issues erstellen
- **Triage-Funktion**: KI klassifiziert Issues automatisch
  - `valid_bug` — gültiger Bug-Report
  - `needs_info` — zusätzliche Informationen benötigt
  - `skip` — keine Aktion erforderlich
- **Issue-Warteschlange**: Neue GitHub-Issues automatisch gepollt und lokal eingereiht. MCP-Client (Claude Desktop) bei Verbindung über ungelesene Einträge benachrichtigt.

### Pull Requests

- PR-Liste und Filterung
- Diff-Statistiken (Hinzugefügte/Entfernte Zeilen, Geänderte Dateien)
- Dateiweise Änderungsansicht in Detailansicht

### Discussions

- Diskussionsliste via GraphQL-API
- Kategorie-Badges und "Beantwortet"-Badges anzeigen

### Releases

- Neueste Releases überwachter Repositories
- Release-Notes anzeigen

### Settings

- Konten hinzufügen/bearbeiten/löschen/aktivieren/deaktivieren
- API-Ratenlimit-Anzeige
- Sprachfilter und Planungsintervall-Einstellungen
- Issue-Warteschlangen-Polling-Intervall, automatisches Schließen ungültiger Issues, MCP-Verbindungsbenachrichtigungen
- Triage-Prompts für Issues/PRs/Discussions bearbeiten ([Beispiele ansehen](/help/github-triage-examples))

### Issue-Warteschlange

Issue-Warteschlange pollt GitHub regelmäßig und speichert neue Issues lokal.

- **Polling**: Automatisch per Scheduler (Intervall konfigurierbar, Standard 60 Minuten)
- **Benachrichtigungen**: Unbearbeitete Issues bei MCP-Verbindung an Claude Desktop gemeldet
- **Triage**: Jedes Issue in der Warteschlange als gültig/ungültig klassifizierbar
- **Automatisches Schließen**: Ungültige Issues mit Template-Kommentar auf GitHub automatisch schließen
- **Manuelles Polling**: "Poll Now" in Settings klickt für sofortigen Abruf

### Triage-Prompts

KI-Anweisungstexte für Issue/PR/Discussion-Triage anpassbar:

- Separate bearbeitbare Prompts für jeden Typ (Issue/PR/Discussion)
- Standard-Prompts verfügbar, jederzeit mit "Auf Standard zurücksetzen" wiederherstellbar
- Mehrsprachige und Stil-Vorlagen in [Triage-Prompt-Beispielen](/help/github-triage-examples)
- Prompts werden in config.json gespeichert (keine Verschlüsselung da keine sensiblen Daten)

## MCP-Integration

GitHub Integration bietet 12 MCP-Tools für direkte Bedienung aus Claude Code:

- Issue-Liste/Details
- PR-Liste/Details
- Benachrichtigungen abrufen
- Triage-Prompts abrufen/aktualisieren
- Issue-Warteschlangen-Verwaltung (unbearbeitete Liste, Triage, Ablehnen, Polling)

MCP-Tools ermöglichen GitHub-Informationsabruf ohne IDE-Wechsel.

## Tipps

- **Mehrere Konten**: Privat und Arbeitskonten trennen
- **Token-Berechtigungen**: `repo`-Bereich reicht für Grundfunktionen. Für Organisation-Private-Repos separate SSO-Autorisierung
- **Triage-Nutzung**: Für Repos mit vielen Issues Triage für automatische Priorisierung nutzen
- **Ratenlimit**: GitHub-API hat stündliche Anfragelimits. Verbleib in Settings-Tab prüfbar
- **Token-Sicherheit**: Token serverseitig verschlüsselt gespeichert. Nie im Klartext
- **Dashboard-Aktualisierung**: Bei Kontowechsel werden Daten automatisch neu abgerufen
