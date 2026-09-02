# GitHub-Triage-Prompt-Beispielsammlung

Triage-Prompts sind Anweisungstexte, die bei der Klassifizierung von GitHub Issues / PRs / Discussions an KI gesendet werden. Frei bearbeitbar unter **GitHub Integration > Settings > Triage Prompts**.

Folgende Beispiele kopieren und anpassen.

---

## Issue-Prompts

### Standard (Englisch, streng)

```
Review the following GitHub issue and determine whether it is a technically valid bug report.

Valid (valid) criteria:
- Concrete reproduction steps are provided
- Error log or stack trace is included
- Environment info (OS, version, etc.) is present

Invalid (invalid) criteria:
- Emotional text only, no technical facts
- Feature request, not a bug
- Written in a language other than English
- No actionable technical information

Return your verdict (valid / invalid) and the reason.
```

### Deutsche Version

```
Prüfen Sie das folgende GitHub-Issue und bestimmen Sie, ob es ein technisch gültiger Bug-Report ist.

Gültig (valid) Kriterien:
- Konkrete Reproduktionsschritte sind angegeben
- Fehlerprotokoll oder Stack-Trace ist vorhanden
- Umgebungsinformationen (OS, Version usw.) sind vorhanden

Ungültig (invalid) Kriterien:
- Nur emotionaler Text, keine technischen Fakten
- Feature-Anfrage, kein Bug
- In anderer Sprache als Englisch geschrieben
- Keine verwertbaren technischen Informationen

Geben Sie Ihr Urteil (valid / invalid) und die Begründung zurück.
```

### Lockere Kriterien (akzeptiert auch Feature-Anfragen)

```
Klassifizieren Sie das folgende GitHub-Issue.

Kategorien:
- valid_bug: Reproduktionsschritte, Fehlerinformationen oder klare Beschreibung unerwarteten Verhaltens vorhanden.
- feature_request: Anfrage für neue Funktionen oder Verbesserungen. Als gültig behandeln.
- needs_info: Könnte gültig sein, aber wichtige Informationen fehlen. Als gültig behandeln und Anmerkung hinzufügen.
- invalid: Spam, nicht relevant oder nur emotionaler Text ohne technischen Inhalt.

Kategorie und Begründung in einer Zeile zurückgeben.
```

### Streng (Sicherheitsorientiert)

```
Bewerten Sie dieses GitHub-Issue aus der Perspektive der Sicherheitsauswirkungen und technischen Validität.

CRITICAL (sofortiger Handlungsbedarf):
- Sicherheitslücken, Datenlecks, Authentifizierungs-Bypass-Berichte
- PoC oder Exploit-Details enthalten

VALID (normaler Bug):
- Technischer Bug mit Reproduktionsschritten und Fehlernachweisen

INVALID (ablehnen):
- Feature-Anfragen, Fragen, emotionale Beschwerden, nicht auf Englisch, keine technischen Fakten

CRITICAL / VALID / INVALID und Begründung zurückgeben.
Bei CRITICAL sofortige menschliche Prüfung angeben.
```

### Mehrsprachig (akzeptiert auch Nicht-Englisch)

```
Bestimmen Sie unabhängig von der Sprache, ob dieses GitHub-Issue ein gültiger Bug-Report ist.

Gültig: Reproduktionsschritte, Fehlerprotokoll oder klare technische Erklärung in einer beliebigen Sprache.
Ungültig: Nur emotional, Spam, kein technischer Inhalt.

Urteil und Begründung auf Englisch zurückgeben.
```

---

## PR-Prompts

### Standard (alle ablehnen)

```
Do not accept pull requests. Close automatically.
```

### Mit Review akzeptieren

```
Reviewen Sie die Codequalität und Relevanz dieses Pull Requests.

Akzeptieren (valid):
- Bugfix für dokumentierten Bug oder Antwort auf offenes Issue
- Code folgt Projektkonventionen
- Enthält Tests oder Testplan

Ablehnen (invalid):
- Nicht relevante Änderungen oder Scope-Erweiterung
- Keine Referenz zu einem Issue
- Zerstört bestehende Funktionalität

accept / reject und Begründung zurückgeben.
```

### Nur Bugfixes akzeptieren

```
Nur Bugfix-Pull-Requests akzeptieren.

Gültig: Referenz zu offenem Issue, gezielte Korrektur, minimaler Scope.
Ungültig: Feature-Ergänzungen, Refactoring, nur Dokumentation, nicht relevante Änderungen.

Urteil und Begründung zurückgeben.
```

---

## Discussion-Prompts

### Standard (alle schließen)

```
Discussions are closed. No action required.
```

### Bug-Berichte überwachen

```
Prüfen Sie, ob diese Discussion nicht gemeldete Bugs enthält.

Wenn reproduzierbare Bugs mit Fehlerdetails beschrieben werden,
als "potential_bug" markieren für Issue-Erstellung.
Andernfalls "no_action".

potential_bug / no_action und Begründung zurückgeben.
```

### Community-Unterstützung

```
Klassifizieren Sie diese Discussion:

- question: Benutzer bittet um Hilfe. Antworten wenn klare Antwort in Dokumentation.
- bug_report: Bug-Beschreibung. Für Issue-Erstellung markieren.
- feature_idea: Interessanter Feature-Vorschlag. Für Review markieren.
- off_topic: Nicht projektrelevant. Kein Handlungsbedarf.

Kategorie und empfohlene Maßnahme (falls zutreffend) zurückgeben.
```
