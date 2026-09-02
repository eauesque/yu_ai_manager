# SNS Share & Bluesky Monitor

## Übersicht

SNS Share ist eine Erweiterung, mit der Sie KI-generierte Bilder direkt aus YU AI Manager auf Bluesky oder X (Twitter) teilen können. Der Posttext wird automatisch aus einer anpassbaren Vorlage generiert und Variablen aus den Bildmetadaten werden automatisch expandiert. Bluesky Monitor fügt eine Benachrichtigungsüberwachung hinzu, die KI-basierte Triage und automatische Antworten ermöglicht.

## Einrichtung

### Bluesky App Password erstellen

1. Melden Sie sich bei [bsky.app](https://bsky.app) an und öffnen Sie **Einstellungen > App Passwords**
2. Klicken Sie auf **App Password hinzufügen**
3. Geben Sie einen Namen ein (z. B. „YU AI Manager") und klicken Sie auf **App Password erstellen**
4. Kopieren Sie das angezeigte Passwort

> **Hinweis**: Das App Password wird nur auf diesem Bildschirm angezeigt. Kopieren Sie es unbedingt, bevor Sie den Dialog schließen. Verwenden Sie niemals Ihr Bluesky-Hauptpasswort.

### Einstellungen in YU AI Manager

1. Öffnen Sie über das Navigationsmenü **Settings**
2. Wechseln Sie zum Tab **SNS**
3. Geben Sie folgende Informationen ein:
   - **Bluesky-Handle**: Handle-Name (z. B. `yourname.bsky.social`)
   - **App Password**: Das oben erstellte App Password
   - **Post-Vorlage**: Vorlage für den Posttext (siehe [Vorlagenvariablen](#vorlagenvariablen))
4. Klicken Sie auf **Speichern**

### Verbindungstest

Klicken Sie nach dem Speichern der Anmeldedaten auf **Verbindungstest**, um die Authentifizierung mit Bluesky zu prüfen. Bei Erfolg werden Handle und Anzeigename angezeigt.

## Funktionen

### Auf Bluesky teilen

Aus der Bilddetailansicht können Sie Bilder direkt auf Bluesky teilen.

1. Öffnen Sie das Detail-Modal des Bildes
2. Klicken Sie auf die Schaltfläche **SNS**
3. Überprüfen und bearbeiten Sie den generierten Posttext
4. Klicken Sie auf **Auf Bluesky posten**

- Der Posttext wird aus der konfigurierten Vorlage mit expandierten Metadaten-Variablen generiert
- Bilder werden automatisch entsprechend Blueskys 1-MB-Upload-Limit komprimiert und verkleinert
- Posts werden auf **300 Grapheme** begrenzt (überschüssige Zeichen werden automatisch gekürzt)
- Sie können wählen, ob das Bild angehängt werden soll

### Auf X (Twitter) teilen

Über Web Intent (Öffnen des X-Postbildschirms im Browser) werden Bildinformationen auf X geteilt.

1. Öffnen Sie das Detail-Modal des Bildes
2. Klicken Sie auf die Schaltfläche **SNS**
3. Klicken Sie auf **Auf X teilen**

Ein neuer Browser-Tab öffnet den X-Postbildschirm, in dem der aus der Vorlage generierte Text automatisch eingefügt ist. Sie können den Text vor dem Posten bearbeiten. Auf X werden Bilder nicht automatisch angehängt; Sie müssen sie manuell beifügen.

### Bluesky Monitor

Bluesky Monitor fragt Benachrichtigungen von Bluesky per Polling ab und stellt sie lokal in eine Warteschlange zur Triage und Antwort.

#### Benachrichtigungstypen

- **Mention**: Sie wurden in einem Post erwähnt
- **Reply**: Jemand hat auf Ihren Post geantwortet
- **Quote**: Ihr Post wurde zitiert
- **Follow**: Jemand ist Ihnen gefolgt
- **Like**: Ihr Post wurde geliked
- **Repost**: Ihr Post wurde repostet

#### Polling

Benachrichtigungen werden in konfigurierbaren Intervallen automatisch abgerufen (Standard: 30 Min., Minimum: 5 Min.). Sie können Polling auch sofort über Settings oder MCP-Tools auslösen.

#### Warteschlangensystem

Jede Benachrichtigung wird mit Status **pending** (unverarbeitet) in die Warteschlange eingereiht. Von dort kann sie in folgende Status übergehen:

- **notified** -- MCP-Client (Claude Desktop) wurde benachrichtigt
- **dismissed** -- Als nicht beantwortungsbedürftig abgelehnt

#### Triage

Eine KI-basierte Klassifikation entscheidet, ob jede Benachrichtigung eine Antwort erfordert:

- **valid** -- Antwort erforderlich (Frage, Bugreport, Kollaborationsanfrage usw.)
- **invalid** -- Kann ignoriert werden (allgemeines Lob, Spam, Bot-Inhalte usw.)

Für jeden Benachrichtigungstyp (Mention, Reply, Quote) gibt es anpassbare Triage-Prompts. Standard-Prompts werden bereitgestellt und können jederzeit wiederhergestellt werden.

#### Automatische Antwort

Für als valid eingestufte Mentions, Replies und Quotes können vorlagenbasierte automatische Antworten gesendet werden:

- Automatische Antwort in den Monitor-Einstellungen aktivieren
- Antwortvorlagen je Benachrichtigungstyp anpassen
- Antworten sind auf 300 Grapheme begrenzt

#### Automatisches Ablehnen

Follows, Likes und Reposts können automatisch abgelehnt werden, um die Warteschlange von Rauschen zu befreien. Jeder Typ kann in den Settings einzeln umgeschaltet werden.

#### Benachrichtigung bei MCP-Verbindung

Wenn sich ein MCP-Client (Claude Desktop) verbindet, werden unverarbeitete Benachrichtigungen gebündelt gemeldet, sodass sie während der Entwicklungssitzung überprüft werden können.

### Settings

Die SNS-Einstellungen erfolgen auf der Settings-Seite unter Tab **SNS**:

- **Bluesky-Anmeldedaten**: Handle und App Password (Passwort wird verschlüsselt gespeichert und maskiert angezeigt)
- **Post-Vorlage**: Vorlagentext mit Platzhaltern für Variablen
- **Monitor-Einstellungen**:
  - Polling-Intervall (Min.)
  - Automatisches Ablehnen von Follows, Likes, Reposts
  - Automatische Antwort aktivieren/deaktivieren
  - Triage-Prompts für Mentions, Replies, Quotes
  - Auto-Antwort-Vorlagen für Mentions, Replies, Quotes

## MCP-Anbindung

Für SNS Share & Bluesky Monitor stehen 15 MCP-Tools bereit:

**Teilen (6 Tools)**:
- `share_to_bluesky` -- Bild auf Bluesky posten
- `get_x_share_url` -- X Web Intent URL abrufen
- `get_sns_preview` -- Vorschau der Vorlagenexpansion
- `test_bluesky_connection` -- API-Verbindungstest
- `get_sns_config` / `save_sns_config` -- SNS-Konfiguration abrufen/speichern

**Benachrichtigungswarteschlange (5 Tools)**:
- `bsky_get_pending_notifications` -- Unverarbeitete Benachrichtigungen abrufen
- `bsky_get_notification_queue` -- Warteschlangenelemente gefiltert abrufen
- `bsky_triage_notification` -- Triage-Ergebnis setzen (valid/invalid)
- `bsky_send_auto_response` -- Antwort auf Benachrichtigung senden
- `bsky_poll_notifications` -- Sofortiges Polling auslösen

**Monitor-Einstellungen (4 Tools)**:
- `bsky_get_monitor_config` / `bsky_save_monitor_config` -- Monitor-Konfiguration abrufen/speichern
- `bsky_get_triage_prompts` / `bsky_save_triage_prompts` -- Triage-Prompts und Antwortvorlagen abrufen/speichern

## Vorlagenvariablen

In Post-Vorlagen verfügbare Variablen:

| Variable | Beschreibung |
|---|---|
| `{positive_short}` | Positiver Prompt (erste 100 Zeichen) |
| `{positive}` | Vollständiger positiver Prompt |
| `{negative_short}` | Negativer Prompt (erste 50 Zeichen) |
| `{model}` | Modellname |
| `{seed}` | Seed-Wert |
| `{steps}` | Anzahl Sampling-Schritte |
| `{cfg}` | CFG-Skala |
| `{sampler}` | Sampler-Name |
| `{size}` | Bildgröße |
| `{tags}` | Top 5 Tags |
| `{filename}` | Dateiname |

Standardvorlage: `{positive_short}`

## Tipps

- **Sicherheit des App Passwords**: Verwenden Sie unbedingt das App Password, nicht das Bluesky-Hauptpasswort. Das App Password kann jederzeit in den Einstellungen von bsky.app deaktiviert werden
- **Rate-Limits**: Die Bluesky API hat Rate-Limits. Vermeiden Sie aufeinanderfolgende Posts. Auch Bild-Uploads zählen zum Rate-Limit
- **Grapheme-Zählung**: Bluesky verwendet für das 300-Zeichen-Limit Grapheme-Cluster, nicht Zeichen. CJK-Zeichen zählen als 1 Grapheme
- **Bildkomprimierung**: Bilder über 1 MB werden automatisch verkleinert. Wenn die Bildvorbereitung fehlschlägt, wird nur Text gepostet
- **Monitor-Polling-Intervall**: Stellen Sie das Polling-Intervall entsprechend dem Benachrichtigungsaufkommen ein. Bei vielen Benachrichtigungen sind kurze Intervalle effektiv
- **Automatisches Ablehnen**: Wenn Sie automatisches Ablehnen für Follows, Likes und Reposts aktivieren, können Sie sich auf antwortbedürftige Benachrichtigungen konzentrieren
- **Triage-Prompts**: Passen Sie die Triage-Prompts an Ihren Kommunikationsstil und die Arten der eingehenden Interaktionen an
