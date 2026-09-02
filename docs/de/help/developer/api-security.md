# API-Sicherheitsrichtlinien

Verwenden Sie dieses Dokument, wenn Sie einen API-Endpunkt hinzufügen oder ändern.

## Erste Entscheidung

Jeder Endpunkt muss von Anfang an als einer der folgenden Typen klassifiziert werden:

- `public`
- `session/user`
- `admin`
- `localhost-only`

Falls unsicher, wählen Sie `admin`.

## Kernregeln

1. Nehmen Sie nicht an, dass `GET` sicher ist.
2. `read-only API keys` sind nur für schlanke Lesevorgänge.
3. Interne Pfade, Bestände, Verlauf, Inhalte, Protokolle und Analyseergebnisse sind `admin`.
4. Localhost-Überprüfungen müssen Proxy-aware Helper verwenden.
5. Config-Endpunkte erfordern Allowlists und strikte Validierung.
6. Secrets müssen verschlüsselt und durch gemeinsame Helfer versteckt werden.

## Nicht sicher für Read-Only-Keys

- interne Pfade
- Datei-/Mitglied-ID-Bestände
- Prompts, Annotationen, Transkripte, Chat-Protokolle
- OCR / Analyseergebnisse
- Warteschlange, Verlauf, Audit, Genehmigung, Scheduler, Scannerfehler Zustand
- Erweiterungs- / Profil- / Sicherungs- / Webhook- / Secret-Backend-Zustand
- Ergebnisse, die mit gespeicherten Drittanbieter-Anmeldedaten abgerufen werden

## Localhost-Überprüfungen

Verwenden Sie nicht roh:

```
request.remote_addr == "127.0.0.1"
```

Verwenden Sie stattdessen vorhandene Helper:

- `get_client_ip()`
- `is_local_request()`
- `is_loopback_request()`

## Config-Endpunkt-Regeln

Erforderlich:

- key allowlist
- strikte Typvalidierung
- Bereichs- / Enum- / URL-Validierung
- Secret Redaction bei Lesevorgängen
- verschlüsselte Speicherung für Secrets

Verboten:

- blind `config.update(...)`
- `bool(value)` für Request-Booleans
- generische Zusammenführungen, die Secret-Handling umgehen

## Secrets

- return current secret values nie
- include tokens/headers/secret blobs in list endpoints nie
- overwrite existing secrets with masked placeholders nie
- use always a dedicated store or shared helper

## Ausgehende Anfragen von APIs

Machen Sie keine Upstream-Sonden oder Discovery-Abrufe von `GET` Endpunkten.

Falls unvermeidlich:

- require `admin`
- keep timeouts short
- block localhost / private IP / metadata targets

## Minimale Tests

Für sensitive Endpunkte hinzufügen:

1. `read-only key -> 403`
2. `admin key -> 200`
3. invalid input -> `400`
4. secret redaction checks
5. proxy-aware localhost regression tests where relevant

## Review-Checkliste

- Ist dieses `GET` wirklich sicher für public/read-only Zugriff?
- Macht es Pfade, Bestände, Prompts, Transkripte, Verlauf oder rohe Metadaten verfügbar?
- Offenbart es Secrets?
- Verwendet es Proxy-aware Helper?
- Vermeidet es implizite Boolean-Umwandlung?
- Vermeidet es blinde Config-Zusammenführungen?
- Vermeidet es unbeabsichtigte ausgehende Anfragen?
- Enthält es Admin-Scope Regressionstests?

Standardrichtlinie: Beginnen Sie eng, öffnen Sie dann bewusst nur wenn nötig.
